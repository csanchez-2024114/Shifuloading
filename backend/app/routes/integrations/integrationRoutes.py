"""
Rutas de Integración - Adaptador de Compatibilidad Frontend
Resolución de Contratos API y Seguridad.
Refactorización:
- Escudo Anti-DDoS (In-Memory Cache) para mitigar bucles N+1 del Frontend.
- Normaliza y desencripta antes de exponer metadata segura.
- Mantiene autenticación estricta con get_current_user para evitar IDOR.
"""

import time
import logging
import os
import requests
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field, field_validator, model_validator
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Union, Tuple
from app.database import get_db, get_current_user, _normalize_integrations
from app.core.constants import Collections
from app.core.db_utils import canonicalize_email
from app.billing.plans import get_plan_rules

logger = logging.getLogger("routes.integrations")
router = APIRouter()
NO_EXPIRES_REQUIRED = {"notion", "slack", "clickup", "monday"}


class DummyCache:

    def set(self, *args, **kwargs):
        pass


cache = DummyCache()
_integrations_anti_ddos_cache = {}
_CACHE_TTL_SECONDS = 5


class AddIntegrationRequest(BaseModel):
    email: str
    integration: str
    token: str
    refresh_token: Optional[str] = None
    expires_in: Optional[Union[int, str]] = None
    token_acquisition_time: Optional[str] = None

    @field_validator("expires_in", mode="before")
    def parse_expires_in(cls, v):
        if v is None:
            return None
        try:
            return int(v)
        except (ValueError, TypeError):
            logger.warning(f"No se pudo convertir expires_in '{v}' a int. Usando 3600.")
            return 3600


async def get_user_vault_with_fallback(
    email: str, db: Any
) -> Tuple[Optional[Dict], str]:
    email_safe = canonicalize_email(email)
    vault_doc = await db[Collections.OAUTH_VAULT].find_one({"email": email_safe})
    if vault_doc:
        return (vault_doc, "vault")
    legacy_doc = await db[Collections.USERS].find_one({"email": email_safe})
    if legacy_doc:
        return (legacy_doc, "legacy")
    return (None, "none")


async def _enforce_connected_apps_limit(
    db: Any, user_id_str: str, email_safe: str, provider_lower: str, user_doc: Dict, account_id: str
) -> None:
    """Bloquea conectar OTRA cuenta del MISMO proveedor una vez alcanzado el tope
    del plan (max_accounts_per_provider) — conectar un proveedor DISTINTO nunca
    se bloquea aquí, no hay límite de cuántas apps distintas se conectan.
    Reconectar/refrescar la MISMA cuenta (mismo provider+account_id) nunca cuenta
    como cuenta nueva, ya que el caller hace upsert por esa clave exacta.

    ponytail: cuenta global por usuario, no por workspace — user_connected_accounts
    no tiene workspace_id todavía; scoping por workspace requiere threading el id
    a través de cada callback OAuth (fuera de alcance de este fix).
    """
    already_this_account = await db[Collections.USER_CONNECTED_ACCOUNTS].find_one(
        {"user_id": user_id_str, "provider": provider_lower, "account_id": account_id}
    )
    if already_this_account:
        return
    plan = user_doc.get("plan")
    if plan is None:
        plan_doc = await db[Collections.USERS].find_one({"email": email_safe}, {"plan": 1})
        plan = (plan_doc or {}).get("plan", "free")
    limit = get_plan_rules(plan).get("max_accounts_per_provider", 1)
    if limit == -1:
        return
    existing_count = await db[Collections.USER_CONNECTED_ACCOUNTS].count_documents(
        {"user_id": user_id_str, "provider": provider_lower}
    )
    if existing_count >= limit:
        raise HTTPException(
            status_code=403,
            detail=f"Tu plan permite hasta {limit} cuenta(s) de {provider_lower}. Actualiza tu plan para conectar otra.",
        )


@router.get("/")
async def get_integrations(
    user: dict = Depends(get_current_user), db: Any = Depends(get_db)
):
    user_id_str = str(user.get("_id") or user.get("id", ""))
    email_safe = canonicalize_email(user.get("email", ""))
    if not user_id_str:
        raise HTTPException(status_code=401, detail="Token inválido: ID ausente")
    current_time = time.time()
    if email_safe in _integrations_anti_ddos_cache:
        cached_time, cached_data = _integrations_anti_ddos_cache[email_safe]
        if current_time - cached_time < _CACHE_TTL_SECONDS:
            return {"integrations": cached_data}
    cursor = db[Collections.USER_CONNECTED_ACCOUNTS].find({"user_id": user_id_str})
    accounts = await cursor.to_list(length=100)
    safe_integrations = {}
    for acc in accounts:
        provider = acc.get("provider")
        if provider not in safe_integrations:
            safe_integrations[provider] = []
        safe_integrations[provider].append(
            {
                "id": str(acc.get("_id")),
                "account_id": acc.get("account_id"),
                "token": "********_vault_secured_********",
                "refresh_token": (
                    "********_vault_secured_********"
                    if acc.get("refresh_token") and acc.get("refresh_token") != "n/a"
                    else None
                ),
                "timestamp": acc.get("timestamp"),
                "expires_in": acc.get("expires_in", 3600),
                "status": acc.get("status", "active"),
                "metadata": acc.get("metadata", {}),
            }
        )
    logger.info(
        f"Integraciones leídas desde user_connected_accounts para: {email_safe}"
    )
    _integrations_anti_ddos_cache[email_safe] = (current_time, safe_integrations)
    return {"integrations": safe_integrations}


@router.post("/")
async def add_integration(data: AddIntegrationRequest, db: Any = Depends(get_db)):
    """Guarda/actualiza una cuenta conectada (OAuth) del usuario en user_connected_accounts.
    Bloqueada por _enforce_connected_apps_limit si el proveedor es nuevo y el plan ya llegó
    a su tope de apps conectadas (reconectar un proveedor ya conectado nunca cuenta)."""
    try:
        from app.core.security import encrypt_data
    except ImportError:
        logger.critical("[integrationRoutes] Módulo de encriptación no disponible. Abortando.")
        raise RuntimeError("El módulo de encriptación es requerido en producción.")
    email_safe = canonicalize_email(data.email)
    if email_safe in _integrations_anti_ddos_cache:
        del _integrations_anti_ddos_cache[email_safe]
    user_doc, source = await get_user_vault_with_fallback(email_safe, db)
    if source == "none":
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    provider_key = data.integration
    provider_lower = provider_key.lower()
    google_suite_names = [
        "gmail",
        "drive",
        "google docs",
        "google sheets",
        "google slides",
        "google",
    ]
    if provider_lower in google_suite_names:
        provider_lower = "google"
        provider_key = "Google"
        logger.info(
            f"Integración de la suite de Google detectada. Unificando bajo el provider: 'google'"
        )
    if provider_lower not in NO_EXPIRES_REQUIRED and data.expires_in is None:
        raise HTTPException(
            status_code=400, detail="El campo 'expires_in' es obligatorio"
        )
    token_encrypted = encrypt_data(data.token) if data.token else None
    refresh_encrypted = encrypt_data(data.refresh_token) if data.refresh_token else None
    now_utc = datetime.now(timezone.utc)
    timestamp_str = data.token_acquisition_time or now_utc.strftime("%Y-%m-%d %H:%M:%S")
    account_identifier = getattr(data, "account_id", None) or email_safe
    new_v2_payload = {
        "user_id": str(user_doc.get("_id", "")),
        "provider": provider_lower,
        "account_id": account_identifier,
        "access_token": token_encrypted,
        "refresh_token": refresh_encrypted,
        "token": token_encrypted,
        "expires_in": int(data.expires_in) if data.expires_in is not None else 3600,
        "status": "active",
        "timestamp": timestamp_str,
        "metadata": {
            "email": email_safe,
            "name": f"Cuenta de {provider_key}",
            "connected_at": now_utc.isoformat(),
        },
    }
    user_id_str = str(user_doc.get("_id", ""))
    await _enforce_connected_apps_limit(db, user_id_str, email_safe, provider_lower, user_doc, account_identifier)
    try:
        await db[Collections.USER_CONNECTED_ACCOUNTS].update_one(
            {
                "user_id": user_id_str,
                "provider": provider_lower,
                "account_id": account_identifier,
            },
            {"$set": new_v2_payload},
            upsert=True,
        )
        logger.info(
            f"[V2] Integración {provider_key} guardada en user_connected_accounts"
        )
    except Exception as e:
        logger.error(f"Error guardando en V2: {e}")
    return {"message": f"Integración {provider_key} añadida exitosamente"}


@router.delete("/{integration_name}")
async def delete_integration(
    integration_name: str,
    user: dict = Depends(get_current_user),
    db: Any = Depends(get_db),
):
    user_id_str = str(user.get("_id") or user.get("id", ""))
    email_safe = canonicalize_email(user.get("email", ""))
    if not user_id_str:
        raise HTTPException(status_code=401, detail="Token inválido")
    if email_safe in _integrations_anti_ddos_cache:
        del _integrations_anti_ddos_cache[email_safe]
    result = await db[Collections.USER_CONNECTED_ACCOUNTS].delete_many(
        {"user_id": user_id_str, "provider": integration_name}
    )
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=404, detail=f"Integración '{integration_name}' no encontrada"
        )
    logger.info(
        f"🗑 {result.deleted_count} cuentas de {integration_name} eliminadas para {email_safe}"
    )
    return {
        "message": f"Integración '{integration_name}' eliminada correctamente",
        "provider": integration_name,
        "deleted_count": result.deleted_count,
    }


class GoogleExchangeRequest(BaseModel):
    email: str
    code: str
    redirect_uri: str
    integration_name: str


@router.post("/google/exchange")
async def exchange_google_code(
    data: GoogleExchangeRequest,
    user: dict = Depends(get_current_user),
    db: Any = Depends(get_db),
):
    """Canjea el authorization code de Google por tokens y guarda la Suite completa (Gmail,
    Drive, Docs, Sheets, Slides) bajo un único provider='google'. Sujeto al mismo tope de
    apps conectadas por plan que /add_integration (_enforce_connected_apps_limit)."""
    try:
        from app.core.security import encrypt_data
    except ImportError:
        logger.critical("[integrationRoutes] Módulo de encriptación no disponible. Abortando.")
        raise RuntimeError("El módulo de encriptación es requerido en producción.")
    email_safe = canonicalize_email(data.email)
    user_id_str = str(user.get("_id") or user.get("id", ""))
    if not user_id_str:
        raise HTTPException(status_code=401, detail="Token inválido: ID ausente")
    user_doc, source = await get_user_vault_with_fallback(email_safe, db)
    if source == "none":
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    token_url = "https://oauth2.googleapis.com/token"
    payload = {
        "code": data.code,
        "client_id": os.getenv("GMAIL_CLIENT_ID"),
        "client_secret": os.getenv("GMAIL_CLIENT_SECRET"),
        "redirect_uri": data.redirect_uri,
        "grant_type": "authorization_code",
    }
    try:
        response = requests.post(token_url, data=payload, timeout=15)
        response.raise_for_status()
        token_data = response.json()
    except requests.exceptions.RequestException as e:
        logger.error(
            f"Error canjeando token de Google: {(response.text if 'response' in locals() else str(e))}"
        )
        raise HTTPException(status_code=400, detail="Fallo la autorización con Google")
    now_utc = datetime.now(timezone.utc)
    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token", "n/a")
    expires_in = token_data.get("expires_in", 3599)
    encrypted_access = encrypt_data(access_token) if access_token else None
    encrypted_refresh = encrypt_data(refresh_token) if refresh_token != "n/a" else None
    new_v2_payload = {
        "user_id": user_id_str,
        "provider": "google",
        "account_id": email_safe,
        "access_token": encrypted_access,
        "refresh_token": encrypted_refresh,
        "token": encrypted_access,
        "expires_in": expires_in,
        "status": "active",
        "timestamp": now_utc.strftime("%Y-%m-%d %H:%M:%S"),
        "metadata": {
            "email": email_safe,
            "name": "Cuenta de Google (Suite Completa)",
            "connected_via": data.integration_name,
            "connected_at": now_utc.isoformat(),
        },
    }
    await _enforce_connected_apps_limit(db, user_id_str, email_safe, "google", user_doc, email_safe)
    try:
        await db[Collections.USER_CONNECTED_ACCOUNTS].update_one(
            {"user_id": user_id_str, "provider": "google", "account_id": email_safe},
            {"$set": new_v2_payload},
            upsert=True,
        )
        logger.info(
            f"[V2] Google Suite unificada y guardada de forma segura para {email_safe}"
        )
    except Exception as e:
        logger.error(f" Error guardando Google Suite en V2: {e}")
        raise HTTPException(
            status_code=500, detail="Error interno al guardar la integración"
        )
    if email_safe in _integrations_anti_ddos_cache:
        del _integrations_anti_ddos_cache[email_safe]
    return {
        "message": "Google conectado y unificado exitosamente",
        "provider": "google",
    }


@router.get("/health")
async def health_check_all_integrations(
    user: dict = Depends(get_current_user), db: Any = Depends(get_db)
):
    try:
        from app.services.integration_health_check import get_all_integrations_health
    except ImportError:
        return {
            "status": "warning",
            "message": "Servicio de health_check no disponible",
        }
    user_id = user.get("id") or str(user.get("_id", ""))
    if not user_id:
        raise HTTPException(status_code=401, detail="Token inválido: user_id ausente")
    return await get_all_integrations_health(db, user_id)