"""
/api/v1/me/secrets — Secrets Vault (dual: real API-key connector vs personal secret).

Not a generic vault disconnected from Connectors: SecretsView is also the UI for
connecting catalog apps that authenticate via API key (no OAuth). On create, the
`service` the user types is resolved against the app catalog:

  - Matches a catalog app with authType="apikey" (APIKEY_APPS, see
    app/agent/shared/utils/login_paths.py) → real connection. Reuses
    add_integration()'s logic (same encryption, same user_connected_accounts
    upsert, same plan quota enforcement) — it also shows up in Connectors.
  - Matches a catalog app with authType="oauth1"/"oauth2" → rejected, that app
    must be connected from Connectors (OAuth flow), not via a pasted secret.
  - Doesn't match any catalog app → personal secret, encrypted with the
    SEPARATE SECRETS_ENCRYPTION_KEY (see app/core/security.py encrypt_secret/
    decrypt_secret) and stored in the new `user_secrets` collection.

GET / returns a unified list of both kinds, never the real value — only a
`secret_preview` (last 4 chars). Each item's `id` carries a synthetic prefix so
PATCH/DELETE/reveal can route without an extra lookup:
  - `conn_{provider}`   → a row in user_connected_accounts (is_connector: true)
  - `sec_{ObjectId}`    → a row in user_secrets (is_connector: false)

Router is mounted with prefix "/api/v1/me/secrets" in main.py; paths below are
relative to that.

Endpoints:
  POST   /                — Create (routes to connector or personal secret)
  GET    /                — Unified list (connectors ⊂ APIKEY_APPS + personal secrets)
  PATCH  /{id}             — Edit metadata / rotate the secret value
  DELETE /{id}             — Disconnect (connector) or hard-delete (personal secret)
  POST   /{id}/reveal      — Decrypt and return the real value (rate-limited 10/min)
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.database import get_current_user
from app.core.constants import Collections
from app.core.limiter import limiter
from app.core.security import encrypt_secret, decrypt_secret, decrypt_data
from app.agent.shared.utils.login_paths import get_auth_type, APIKEY_APPS
from app.services.catalog_apps import get_by_name
from app.services.audit_service import log_event as _audit
from app.routes.integrations.integrationRoutes import (
    add_integration,
    delete_integration,
    AddIntegrationRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_COL_SECRETS = Collections.USER_SECRETS
_COL_ACCOUNTS = Collections.USER_CONNECTED_ACCOUNTS

# API keys don't expire — pass a long-lived placeholder so add_integration's
# "expires_in is required" validation (built for OAuth tokens) doesn't block us.
_APIKEY_EXPIRES_IN_PLACEHOLDER = 315360000  # 10 years


def _normalize_name_api(raw: str) -> str:
    return (raw or "").lower().strip().replace(" ", "_")


def _preview(value: str) -> str:
    if not value:
        return "****"
    tail = value[-4:] if len(value) >= 4 else value
    return f"****{tail}"


def _client_ip(request: Request) -> str:
    return request.headers.get("x-forwarded-for", request.client.host if request.client else "")


def _parse_id(item_id: str) -> tuple[str, str]:
    """Splits a synthetic id into (kind, key). kind is 'conn' or 'sec'."""
    if item_id.startswith("conn_"):
        return "conn", item_id[len("conn_"):]
    if item_id.startswith("sec_"):
        return "sec", item_id[len("sec_"):]
    raise HTTPException(status_code=400, detail="Invalid secret id format.")


def _user_email(user: dict) -> str:
    return (user.get("email") or user.get("correo") or "").strip()


# ── POST / (create) ─────────────────────────────────────────────────────────


class SecretCreateRequest(BaseModel):
    name: str
    service: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    secret_value: str


@router.post("")
async def create_secret(
    body: SecretCreateRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """
    Creates either a real connector (if `service` matches a catalog app with
    authType="apikey") or a personal secret (encrypted with SECRETS_ENCRYPTION_KEY).
    """
    db = request.app.state.db
    user_id = current_user.get("id", "")
    ip = _client_ip(request)

    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required.")
    if not body.secret_value:
        raise HTTPException(status_code=400, detail="secret_value is required.")

    service_raw = (body.service or "").strip()
    catalog_app = await get_by_name(service_raw, db) if service_raw else None

    if catalog_app:
        name_api = _normalize_name_api(catalog_app.get("nameApi") or catalog_app.get("name"))
        auth_type = get_auth_type(name_api)

        if auth_type in ("oauth1", "oauth2"):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"'{catalog_app.get('name', service_raw)}' se conecta por OAuth, "
                    "no por API key. Conectala desde Connectors."
                ),
            )

        if auth_type == "apikey":
            payload = AddIntegrationRequest(
                email=_user_email(current_user),
                integration=name_api,
                token=body.secret_value,
                expires_in=_APIKEY_EXPIRES_IN_PLACEHOLDER,
            )
            result = await add_integration(payload, db=db)

            # add_integration's own upsert doesn't carry name/category/description —
            # merge those into metadata so PATCH/GET can surface them.
            await db[_COL_ACCOUNTS].update_one(
                {"user_id": user_id, "provider": name_api},
                {"$set": {
                    "metadata.name": name,
                    "metadata.category": body.category or "",
                    "metadata.description": body.description or "",
                    "reveal_count": 0,
                }},
            )

            _audit(user_id, "secret_connector_created", name_api, db, ip=ip,
                   extra={"name": name, "service": name_api})

            return JSONResponse(status_code=201, content=jsonable_encoder({
                "is_connector": True,
                "id": f"conn_{name_api}",
                "provider": name_api,
                "message": result.get("message"),
            }))

    # No catalog match (or matched but auth type unresolved) → personal secret.
    now = datetime.now(timezone.utc)
    doc = {
        "user_id": user_id,
        "name": name,
        "service": service_raw or name,
        "category": body.category or "",
        "description": body.description or "",
        "secret_ciphertext": encrypt_secret(body.secret_value),
        "secret_preview": _preview(body.secret_value),
        "created_at": now,
        "updated_at": now,
        "last_used_at": None,
        "reveal_count": 0,
    }
    res = await db[_COL_SECRETS].insert_one(doc)

    _audit(user_id, "secret_created", str(res.inserted_id), db, ip=ip,
           extra={"name": name, "service": doc["service"]})

    return JSONResponse(status_code=201, content=jsonable_encoder({
        "is_connector": False,
        "id": f"sec_{res.inserted_id}",
        "name": name,
        "service": doc["service"],
        "category": doc["category"],
        "description": doc["description"],
        "secret_preview": doc["secret_preview"],
        "created_at": now.isoformat(),
    }))


# ── GET / (unified list) ────────────────────────────────────────────────────


@router.get("")
async def list_secrets(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Unified list: API-key connectors (user_connected_accounts ∩ APIKEY_APPS) + personal secrets."""
    db = request.app.state.db
    user_id = current_user.get("id", "")

    items: list[dict] = []

    if APIKEY_APPS:
        conn_docs = await db[_COL_ACCOUNTS].find(
            {"user_id": user_id, "provider": {"$in": list(APIKEY_APPS)}}
        ).to_list(length=200)
        for d in conn_docs:
            token = d.get("token") or d.get("access_token") or ""
            try:
                plain_tail = decrypt_data(token) if token else ""
            except Exception:
                plain_tail = ""
            metadata = d.get("metadata", {}) or {}
            items.append({
                "id": f"conn_{d.get('provider')}",
                "is_connector": True,
                "name": metadata.get("name") or f"Cuenta de {d.get('provider')}",
                "service": d.get("provider"),
                "category": metadata.get("category") or "Conectores",
                "description": metadata.get("description") or "",
                "secret_preview": _preview(plain_tail),
                "created_at": metadata.get("connected_at"),
                "updated_at": metadata.get("connected_at"),
                "last_used_at": d.get("last_used_at").isoformat() if isinstance(d.get("last_used_at"), datetime) else d.get("last_used_at"),
                "reveal_count": d.get("reveal_count", 0),
            })

    sec_docs = await db[_COL_SECRETS].find({"user_id": user_id}).to_list(length=200)
    for d in sec_docs:
        items.append({
            "id": f"sec_{d['_id']}",
            "is_connector": False,
            "name": d.get("name"),
            "service": d.get("service"),
            "category": d.get("category"),
            "description": d.get("description"),
            "secret_preview": d.get("secret_preview"),
            "created_at": d.get("created_at").isoformat() if isinstance(d.get("created_at"), datetime) else d.get("created_at"),
            "updated_at": d.get("updated_at").isoformat() if isinstance(d.get("updated_at"), datetime) else d.get("updated_at"),
            "last_used_at": d.get("last_used_at").isoformat() if isinstance(d.get("last_used_at"), datetime) else d.get("last_used_at"),
            "reveal_count": d.get("reveal_count", 0),
        })

    items.sort(key=lambda x: x.get("created_at") or "", reverse=True)

    return JSONResponse(content=jsonable_encoder({"secrets": items, "total": len(items)}))


# ── PATCH /{id} (edit metadata / rotate value) ──────────────────────────────


class SecretUpdateRequest(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    secret_value: Optional[str] = None


@router.patch("/{item_id}")
async def update_secret(
    item_id: str,
    body: SecretUpdateRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    db = request.app.state.db
    user_id = current_user.get("id", "")
    ip = _client_ip(request)
    kind, key = _parse_id(item_id)

    if kind == "conn":
        provider = key
        existing = await db[_COL_ACCOUNTS].find_one({"user_id": user_id, "provider": provider})
        if not existing:
            raise HTTPException(status_code=404, detail="Connector not found.")

        metadata_updates: dict = {}
        if body.name is not None:
            metadata_updates["metadata.name"] = body.name.strip()
        if body.category is not None:
            metadata_updates["metadata.category"] = body.category
        if body.description is not None:
            metadata_updates["metadata.description"] = body.description

        if body.secret_value:
            payload = AddIntegrationRequest(
                email=_user_email(current_user),
                integration=provider,
                token=body.secret_value,
                expires_in=_APIKEY_EXPIRES_IN_PLACEHOLDER,
            )
            await add_integration(payload, db=db)
            metadata_updates["reveal_count"] = 0

        if not metadata_updates:
            raise HTTPException(status_code=400, detail="No fields were provided to update.")

        await db[_COL_ACCOUNTS].update_one(
            {"user_id": user_id, "provider": provider}, {"$set": metadata_updates}
        )
        _audit(user_id, "secret_connector_updated", provider, db, ip=ip,
               extra={"rotated": bool(body.secret_value)})
        return JSONResponse(content={"status": "updated", "id": item_id})

    # kind == "sec"
    try:
        oid = ObjectId(key)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid secret id format.")

    updates: dict = {}
    if body.name is not None:
        updates["name"] = body.name.strip()
    if body.category is not None:
        updates["category"] = body.category
    if body.description is not None:
        updates["description"] = body.description
    if body.secret_value:
        updates["secret_ciphertext"] = encrypt_secret(body.secret_value)
        updates["secret_preview"] = _preview(body.secret_value)
        updates["reveal_count"] = 0

    if not updates:
        raise HTTPException(status_code=400, detail="No fields were provided to update.")
    updates["updated_at"] = datetime.now(timezone.utc)

    result = await db[_COL_SECRETS].update_one(
        {"_id": oid, "user_id": user_id}, {"$set": updates}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Secret not found.")

    _audit(user_id, "secret_updated", key, db, ip=ip,
           extra={"rotated": bool(body.secret_value)})
    return JSONResponse(content={"status": "updated", "id": item_id})


# ── DELETE /{id} ─────────────────────────────────────────────────────────────


@router.delete("/{item_id}")
async def delete_secret(
    item_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    db = request.app.state.db
    user_id = current_user.get("id", "")
    ip = _client_ip(request)
    kind, key = _parse_id(item_id)

    if kind == "conn":
        result = await delete_integration(key, user=current_user, db=db)
        _audit(user_id, "secret_connector_deleted", key, db, ip=ip, extra={})
        return JSONResponse(content=jsonable_encoder({"status": "deleted", "id": item_id, **result}))

    try:
        oid = ObjectId(key)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid secret id format.")

    result = await db[_COL_SECRETS].delete_one({"_id": oid, "user_id": user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Secret not found.")

    _audit(user_id, "secret_deleted", key, db, ip=ip, extra={})
    return JSONResponse(content={"status": "deleted", "id": item_id})


# ── POST /{id}/reveal ────────────────────────────────────────────────────────


@router.post("/{item_id}/reveal")
@limiter.limit("10/minute")
async def reveal_secret(
    item_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Decrypts and returns the real value. Never logged. Rate-limited to 10/min per IP."""
    db = request.app.state.db
    user_id = current_user.get("id", "")
    ip = _client_ip(request)
    kind, key = _parse_id(item_id)
    now = datetime.now(timezone.utc)

    if kind == "conn":
        provider = key
        doc = await db[_COL_ACCOUNTS].find_one({"user_id": user_id, "provider": provider})
        if not doc:
            raise HTTPException(status_code=404, detail="Connector not found.")
        token = doc.get("token") or doc.get("access_token") or ""
        try:
            value = decrypt_data(token) if token else ""
        except Exception:
            logger.error("Failed to decrypt connector token for provider=%s", provider, exc_info=True)
            raise HTTPException(status_code=500, detail="Could not decrypt the stored value.")

        await db[_COL_ACCOUNTS].update_one(
            {"user_id": user_id, "provider": provider},
            {"$set": {"last_used_at": now}, "$inc": {"reveal_count": 1}},
        )
        _audit(user_id, "secret_connector_revealed", provider, db, ip=ip, extra={})
        return JSONResponse(content={"id": item_id, "value": value, "revealed_at": now.isoformat()})

    try:
        oid = ObjectId(key)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid secret id format.")

    doc = await db[_COL_SECRETS].find_one({"_id": oid, "user_id": user_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Secret not found.")

    try:
        value = decrypt_secret(doc.get("secret_ciphertext", ""))
    except Exception:
        logger.error("Failed to decrypt personal secret id=%s", key, exc_info=True)
        raise HTTPException(status_code=500, detail="Could not decrypt the stored value.")

    await db[_COL_SECRETS].update_one(
        {"_id": oid, "user_id": user_id},
        {"$set": {"last_used_at": now}, "$inc": {"reveal_count": 1}},
    )
    _audit(user_id, "secret_revealed", key, db, ip=ip, extra={})
    return JSONResponse(content={"id": item_id, "value": value, "revealed_at": now.isoformat()})
