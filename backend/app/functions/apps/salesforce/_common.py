"""Helpers compartidos por las funciones de Salesforce (f_users.py, f_crm.py).

La API de datos vive en el `instance_url` propio de cada org, que accounts.py no guarda. Se descubre llamando a
/services/oauth2/userinfo (el mismo host fijo que usa la whoami), que devuelve `urls.rest` con la URL de la org; se recuerda en memoria
por cuenta para no repetir esa llamada. Si la cuenta se reconecta a otra org cambia su user_id, asi que la clave nunca se cruza.
Verificado con la API real (2026-10-09).
"""
from typing import Any, Optional

from app.functions.context import Context
from app.functions.errors import FunctionError
from app.functions.spec import ErrorCode

USERINFO_URL = "https://login.salesforce.com/services/oauth2/userinfo"
API_VERSION = "62.0"
UPSTREAM_API = f"v{API_VERSION}"

# Id de Salesforce: 15 o 18 caracteres alfanumericos. Se valida en la entrada: asi nunca viaja texto libre en una ruta.
ID_PATTERN = r"^[a-zA-Z0-9]{15,18}$"

# Nombre de objeto (Account, MiObjeto__c) y de campo (Name, Owner.Name): solo letras, numeros, guion bajo y, en campos, punto.
SOBJECT_PATTERN = r"^[A-Za-z][A-Za-z0-9_]{0,79}$"
FIELD_PATTERN = r"^[A-Za-z][A-Za-z0-9_.]{0,79}$"

_BASES: dict[str, str] = {}  # account_id -> https://<org>.my.salesforce.com/services/data/v62.0


async def api_base(ctx: Context) -> str:
    """URL base de la API de datos de la org de la cuenta conectada (sin barra final)."""
    key = ctx.account_id
    if key and key in _BASES:
        return _BASES[key]
    body = (await ctx.conn.request("GET", USERINFO_URL, headers={"Accept": "application/json"})).json()
    rest = (body.get("urls") or {}).get("rest")
    if not isinstance(rest, str) or "/services/data/" not in rest:
        raise FunctionError(ErrorCode.upstream_changed, "Salesforce no devolvio la URL de la API de la org (urls.rest) en userinfo.")
    base = rest.replace("{version}", API_VERSION).rstrip("/")
    if key:
        _BASES[key] = base
    return base


async def get_json(ctx: Context, path: str, *, params: Optional[dict] = None, headers: Optional[dict] = None) -> Any:
    """GET a la API de datos de la org (`path` empieza por /) y devuelve el JSON."""
    base = await api_base(ctx)
    return (await ctx.conn.request("GET", f"{base}{path}", params=params or None, headers={"Accept": "application/json", **(headers or {})})).json()


async def get_root_json(ctx: Context, path: str = "") -> Any:
    """GET a la raiz de la API de la org (https://<org>/services/data, sin version) mas `path`; sirve para listar las versiones disponibles."""
    root = (await api_base(ctx)).rsplit("/services/data/", 1)[0] + "/services/data"
    return (await ctx.conn.request("GET", f"{root}{path}", headers={"Accept": "application/json"})).json()


async def post_json(ctx: Context, path: str, body: Any) -> Any:
    """POST con cuerpo JSON a la API de datos de la org (`path` empieza por /) y devuelve el JSON."""
    base = await api_base(ctx)
    return (await ctx.conn.request("POST", f"{base}{path}", json=body, headers={"Accept": "application/json"})).json()


def clean_record(raw: dict[str, Any]) -> dict[str, Any]:
    """Registro de Salesforce sin el bloque `attributes` (que solo trae el tipo y una URL interna)."""
    return {k: v for k, v in raw.items() if k != "attributes"}


def locator_of(next_records_url: Optional[str]) -> Optional[str]:
    """Localizador de la pagina siguiente de una consulta: el ultimo tramo de `nextRecordsUrl` (/services/data/v62.0/query/01g...-2000)."""
    return next_records_url.rstrip("/").rsplit("/", 1)[-1] if next_records_url else None


def soql_str(value: str) -> str:
    """Literal de texto SOQL entre comillas simples, con los caracteres especiales escapados."""
    escaped = (value.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')
               .replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t"))
    return f"'{escaped}'"


def soql_like(value: str) -> str:
    """Literal SOQL para `LIKE` que busca el texto en cualquier parte (%texto%); los comodines del usuario se escapan."""
    inner = soql_str(value)[1:-1].replace("%", "\\%").replace("_", "\\_")
    return f"'%{inner}%'"
