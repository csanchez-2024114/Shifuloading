"""Conexiones: resuelven que cuenta del usuario se usa y hacen las peticiones HTTP con su credencial.

Unica puerta a las credenciales de las funciones. Lee SOLO user_connected_accounts (almacen unico decidido).
Los handlers reciben una Connection ya lista y llaman a conn.request(); nunca tocan el vault ni el secreto.

Reglas de cuenta (get_connection):
  ninguna cuenta usable           -> missing_connection
  una                             -> esa
  varias y sin account_id         -> account_selection_required
  account_id dado                 -> esa (si existe pero esta vencida/revocada -> auth_expired)
El account_id lo inyecta quien ejecuta, nunca el modelo.
"""
import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from app.core.constants import Collections, ConnectedAccountStatus
from app.core.security import decrypt_data, encrypt_data
from app.functions.auth import Credentials, RequestParts, get_strategy
from app.functions.errors import FunctionError
from app.functions.spec import AppSpec, AuthType, ErrorCode

logger = logging.getLogger("functions.connection")

DEFAULT_TIMEOUT = 15.0
RETRY_STATUSES = {429, 502, 503, 504}
MAX_RETRIES = 1
RETRY_DELAY_SECONDS = 1.0
_EMPTY = {"", "n/a", None}


def _unreadable() -> FunctionError:
    return FunctionError(ErrorCode.auth_expired, "No se pudieron leer las credenciales guardadas; hay que reconectar la cuenta.")


def _decrypt(value: Any) -> str:
    # Estricto a proposito: si no descifra, NO se manda el texto cifrado como si fuera un token.
    try:
        return decrypt_data(str(value))
    except Exception:
        raise _unreadable() from None


def credentials_from_doc(doc: dict) -> Credentials:
    """Un campo: access_token (y refresh_token). Varios campos: credentials_enc (JSON cifrado con el mismo Fernet)."""
    if doc.get("credentials_enc"):
        try:
            data = json.loads(_decrypt(doc["credentials_enc"]))
        except ValueError:
            raise _unreadable() from None
        if not isinstance(data, dict):
            raise _unreadable()
        return Credentials(fields={str(k): str(v) for k, v in data.items()})
    fields: dict[str, str] = {}
    if doc.get("access_token") not in _EMPTY:
        fields["token"] = _decrypt(doc["access_token"])
    if doc.get("refresh_token") not in _EMPTY:
        fields["refresh_token"] = _decrypt(doc["refresh_token"])
    if not fields:
        raise FunctionError(ErrorCode.auth_expired, "La cuenta no tiene credenciales guardadas; hay que reconectarla.")
    return Credentials(fields=fields)


# Google (Gmail, Drive, Sheets) usa 403 tambien para el limite de ritmo: sin separarlo, el agente pedia reconectar con
# mas permisos cuando bastaba esperar. "Sin acceso a ESE archivo" es access_denied (reconectar no lo arregla: hay que
# pedir acceso al dueno), pero SOLO con las marcas explicitas de Google; cualquier otro 403 sigue siendo missing_scope.
_RATE_403 = re.compile(r"rateLimitExceeded|userRateLimitExceeded|sharingRateLimitExceeded|RATE_LIMIT_EXCEEDED", re.I)


_NO_ACCESS_403 = re.compile(r"insufficientFilePermissions|do(?:es)? not have (?:sufficient )?permission", re.I)
_SCOPE_403 = re.compile(r"scope", re.I)


def _code_for_403(text: str) -> ErrorCode:
    if _RATE_403.search(text):
        return ErrorCode.rate_limited
    if _NO_ACCESS_403.search(text) and not _SCOPE_403.search(text):
        return ErrorCode.access_denied
    return ErrorCode.missing_scope


def _raise_for_status(resp: httpx.Response) -> None:
    sc = resp.status_code
    if sc == 403:
        code = _code_for_403(resp.text)
    elif sc == 404:
        code = ErrorCode.not_found
    elif sc == 429:
        code = ErrorCode.rate_limited
    elif sc >= 500:
        code = ErrorCode.upstream_down
    else:
        code = ErrorCode.invalid_input
    raise FunctionError(code, f"HTTP {sc}: {resp.text[:200]}")


class Connection:
    def __init__(self, *, db: Any, app: AppSpec, doc: Optional[dict], creds: Credentials,
                 transport: Optional[httpx.AsyncBaseTransport] = None):
        self._db = db
        self.app = app
        self._doc = doc
        self.creds = creds
        self._transport = transport
        self._strategy = get_strategy(app.auth.type)

    @property
    def account_id(self) -> Optional[str]:
        return str(self._doc["account_id"]) if self._doc and self._doc.get("account_id") is not None else None

    async def request(self, method: str, url: str, *, params: Optional[dict] = None, json: Any = None,
                      data: Any = None, headers: Optional[dict] = None, timeout: float = DEFAULT_TIMEOUT,
                      ok_statuses: tuple[int, ...] = ()) -> httpx.Response:
        """Hace la peticion con la credencial aplicada. Devuelve la respuesta si es 2xx/3xx (o esta en ok_statuses);
        si no, lanza FunctionError con el codigo del contrato."""
        refreshed = False
        retries = 0
        async with httpx.AsyncClient(transport=self._transport) as client:
            while True:
                parts = RequestParts(headers=dict(headers or {}), params=dict(params or {}))
                self._strategy.apply(parts, self.creds, self.app.auth)
                try:
                    resp = await client.request(method, url, params=parts.params or None, headers=parts.headers,
                                                json=json, data=data, timeout=timeout)
                except httpx.TimeoutException:
                    raise FunctionError(ErrorCode.upstream_down, "La app externa no respondio a tiempo.") from None
                except httpx.HTTPError as exc:
                    raise FunctionError(ErrorCode.upstream_down, f"Error de red: {type(exc).__name__}") from None
                status = resp.status_code
                marker = self.app.auth.scope_error_marker
                tmarker = self.app.auth.token_invalid_marker
                if status in (400, 401) and marker and re.search(marker, resp.text):  # falta un permiso: no es un token vencido, no se refresca ni se marca la cuenta
                    raise FunctionError(ErrorCode.missing_scope, f"La cuenta no concedio el permiso necesario: {resp.text[:200]}")
                # un 401 es token vencido; algunas plataformas lo dicen con un 403 y un texto (token_invalid_marker), y se trata igual
                token_invalid = status == 401 or (status == 403 and bool(tmarker) and bool(re.search(tmarker, resp.text)))
                if token_invalid and self._strategy.can_refresh and not refreshed:
                    refreshed = True
                    new = await self._strategy.refresh(client, self.creds, self.app.auth)
                    if new:
                        await self._apply_refresh(new)
                        continue
                if status in RETRY_STATUSES and retries < MAX_RETRIES:
                    retries += 1
                    await asyncio.sleep(RETRY_DELAY_SECONDS)
                    continue
                break
        if token_invalid:
            await self._mark_expired()
            raise FunctionError(ErrorCode.auth_expired, "La app rechazo la credencial; hay que reconectar la cuenta.")
        if status < 400 or status in ok_statuses:
            return resp
        _raise_for_status(resp)
        raise AssertionError("inalcanzable")  # _raise_for_status siempre lanza

    # -- persistencia: siempre por el _id exacto del documento, nunca por usuario+proveedor (evita cruzar cuentas) --

    async def _apply_refresh(self, new: dict[str, str]) -> None:
        self.creds.fields["token"] = new["access_token"]
        if new.get("refresh_token"):
            self.creds.fields["refresh_token"] = new["refresh_token"]
        if not self._doc:
            return
        now = datetime.now(timezone.utc)
        if self._doc.get("credentials_enc"):
            update: dict[str, Any] = {"credentials_enc": encrypt_data(json.dumps(self.creds.fields))}
        else:
            update = {"access_token": encrypt_data(new["access_token"])}
            if new.get("refresh_token"):
                update["refresh_token"] = encrypt_data(new["refresh_token"])
        update.update({"status": ConnectedAccountStatus.ACTIVE, "last_refreshed_at": now})
        await self._db[Collections.USER_CONNECTED_ACCOUNTS].update_one({"_id": self._doc["_id"]}, {"$set": update})

    async def _mark_expired(self) -> None:
        if not self._doc:
            return
        try:
            await self._db[Collections.USER_CONNECTED_ACCOUNTS].update_one(
                {"_id": self._doc["_id"]},
                {"$set": {"status": ConnectedAccountStatus.EXPIRED, "last_health_check": datetime.now(timezone.utc)}},
            )
        except Exception as exc:  # nunca tapar el error real con uno de escritura
            logger.warning("No se pudo marcar la cuenta como vencida: %s", type(exc).__name__)


async def get_connection(db: Any, user_id: str, app: AppSpec, account_id: Optional[str] = None, *,
                         transport: Optional[httpx.AsyncBaseTransport] = None) -> Connection:
    if app.auth.type == AuthType.none:
        return Connection(db=db, app=app, doc=None, creds=Credentials(), transport=transport)
    docs = await db[Collections.USER_CONNECTED_ACCOUNTS].find(
        {"user_id": str(user_id), "provider": {"$in": app.provider_keys}}
    ).to_list(length=100)
    usable = [d for d in docs if d.get("status", ConnectedAccountStatus.ACTIVE) in ConnectedAccountStatus.USABLE]

    if account_id is not None:
        wanted = str(account_id)
        match = [d for d in docs if str(d.get("account_id")) == wanted]
        if not match:
            raise FunctionError(ErrorCode.missing_connection, f"No hay una cuenta '{wanted}' conectada de {app.app}.")
        chosen = [d for d in match if d in usable]
        if not chosen:
            raise FunctionError(ErrorCode.auth_expired, f"La cuenta '{wanted}' de {app.app} esta vencida o revocada.")
        doc = chosen[0]
    elif not usable:
        if docs:
            raise FunctionError(ErrorCode.auth_expired, f"Las cuentas de {app.app} estan vencidas o revocadas.")
        raise FunctionError(ErrorCode.missing_connection, f"El usuario no tiene {app.app} conectado.")
    elif len(usable) > 1:
        ids = ", ".join(str(d.get("account_id")) for d in usable[:10])
        raise FunctionError(ErrorCode.account_selection_required, f"Hay {len(usable)} cuentas de {app.app} ({ids}); falta elegir una.")
    else:
        doc = usable[0]
    return Connection(db=db, app=app, doc=doc, creds=credentials_from_doc(doc), transport=transport)
