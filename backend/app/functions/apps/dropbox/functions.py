"""Funciones de lectura de Dropbox (API v2).

Verificado en la especificacion oficial (dropbox/dropbox-api-spec, 2026-10-06): rutas, argumentos, resultado y scopes de
get_current_account y search_v2, y los argumentos/resultado de list_folder. POR COMPROBAR en una prueba real: el scope de
list_folder (se asume files.metadata.read) y que la etiqueta de union llegue como ".tag".

Las descripciones y los Field(description=...) estan en INGLES y completos a proposito: el agente los usa para buscar la funcion
y para llenar sus argumentos (ver doc/funciones/CONTRATO.md, "Descripciones").
"""
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from app.functions.apps.dropbox.app_spec import APP  # noqa: F401  (registra la app antes que las funciones)
from app.functions.context import Context
from app.functions.errors import FunctionError
from app.functions.registry import function
from app.functions.spec import ErrorCode, Verb

BASE_URL = "https://api.dropboxapi.com/2"


def _path(path: str) -> str:
    """Dropbox quiere "" para la raiz y una ruta con "/" inicial para lo demas."""
    p = (path or "").strip()
    return "" if p in ("", "/") else (p if p.startswith("/") else "/" + p)


def _raise_endpoint_error(resp) -> None:
    """Dropbox responde 409 con el error del endpoint en {"error_summary": "path/not_found/...", "error": {...}}."""
    try:
        summary = str(resp.json().get("error_summary", ""))
    except ValueError:
        summary = resp.text[:120]
    if summary.startswith("path/not_found") or "not_found" in summary.split("/")[:2]:
        raise FunctionError(ErrorCode.not_found, "No existe esa ruta en Dropbox.")
    raise FunctionError(ErrorCode.invalid_input, f"Dropbox rechazo la peticion: {summary[:120] or 'sin detalle'}")


# --- dropbox.account.get (whoami) ----------------------------------------------------------------

class NoArgs(BaseModel):
    pass


class Account(BaseModel):
    account_id: str = Field(description="Dropbox account id (the same value stored when the account was connected)")
    email: Optional[str] = Field(default=None, description="Email address of the Dropbox account")
    display_name: Optional[str] = Field(default=None, description="Display name of the account owner")


@function(
    id="dropbox.account.get", version=1, verb=Verb.read, upstream_api="2", scopes=["account_info.read"],
    description=(
        "Returns the Dropbox account that is connected for the user: the Dropbox account id, the email address and the display name. Use it to confirm which "
        "Dropbox account is being used, to answer questions such as 'which Dropbox do I have connected?', or to check that the connection still works before "
        "reading files. Read-only: it takes no parameters and does not change anything in Dropbox. If the user has several Dropbox accounts connected, "
        "one of them must be chosen first."
    ),
    examples=[{"name": "default", "input": {}, "output": {
        "account_id": "dbid:AAH4f99T0taONIb", "email": "ana@empresa.test", "display_name": "Ana Perez"}}],
)
async def account_get(ctx: Context, args: NoArgs) -> Account:
    body = (await ctx.conn.request("POST", f"{BASE_URL}/users/get_current_account")).json()  # sin cuerpo: el argumento es Void
    return Account(account_id=body["account_id"], email=body.get("email"), display_name=(body.get("name") or {}).get("display_name"))


# --- entradas de archivos y carpetas (compartido) ------------------------------------------------

class Entry(BaseModel):
    type: Literal["file", "folder", "deleted"] = Field(description="Kind of entry: a file, a folder, or a deleted item")
    name: str = Field(description="Name of the file or folder, including the extension for files")
    path_display: Optional[str] = Field(default=None, description="Full path in Dropbox as shown to the user, starting with '/'")
    id: Optional[str] = Field(default=None, description="Dropbox id of the file or folder, usable for later steps")
    size: Optional[int] = Field(default=None, description="Size in bytes; only present for files")
    server_modified: Optional[str] = Field(default=None, description="UTC date and time of the last modification; only present for files")


def _entry(raw: dict[str, Any]) -> Entry:
    return Entry(type=raw[".tag"], name=raw["name"], path_display=raw.get("path_display"), id=raw.get("id"),
                 size=raw.get("size"), server_modified=raw.get("server_modified"))


# --- dropbox.files.list --------------------------------------------------------------------------

class ListFilesIn(BaseModel):
    path: str = Field(default="", description="Folder to list; an empty value or '/' means the root folder of the Dropbox, otherwise a path such as '/Documents/2026'")
    limit: int = Field(default=100, ge=1, le=2000, description="Maximum number of entries to return in this call, from 1 to 2000 (default 100)")
    recursive: bool = Field(default=False, description="True also lists everything inside the subfolders; false lists only the direct contents (default)")


class ListFilesOut(BaseModel):
    entries: list[Entry] = Field(description="Files and folders found in the folder")
    has_more: bool = Field(description="True if there are more entries than were returned")
    cursor: Optional[str] = Field(default=None, description="Opaque marker to request the next page of results")


@function(
    id="dropbox.files.list", version=1, verb=Verb.read, upstream_api="2", scopes=["files.metadata.read"],
    description=(
        "Lists the files and folders directly inside a Dropbox folder, or everything below it when recursive is turned on. Each entry reports whether it is a file, "
        "folder or deleted item, its name, its display path, its id and, for files, the size in bytes and the last server modification time. Use it when the user "
        "wants to browse a folder, see what is in their Dropbox, find the exact path of something, or needs paths and ids for a later step. An empty path or '/' "
        "means the root folder. It returns up to the requested limit (maximum 2000) and tells whether more entries exist. Read-only. It does not search by name or "
        "content (use dropbox.files.search for that) and it does not download file contents."
    ),
    examples=[{"name": "default", "input": {"path": "", "limit": 2}, "output": {"entries": [
        {"type": "folder", "name": "Fotos", "path_display": "/Fotos", "id": "id:abc"},
        {"type": "file", "name": "nota.txt", "path_display": "/nota.txt", "id": "id:def", "size": 120,
         "server_modified": "2026-01-02T10:00:00Z"}], "has_more": False, "cursor": "AAH"}}],
)
async def files_list(ctx: Context, args: ListFilesIn) -> ListFilesOut:
    resp = await ctx.conn.request("POST", f"{BASE_URL}/files/list_folder", ok_statuses=(409,),
                                  json={"path": _path(args.path), "limit": args.limit, "recursive": args.recursive})
    if resp.status_code == 409:
        _raise_endpoint_error(resp)
    body = resp.json()
    return ListFilesOut(entries=[_entry(e) for e in body.get("entries", [])], has_more=bool(body.get("has_more")), cursor=body.get("cursor"))


# --- dropbox.files.search ------------------------------------------------------------------------

class SearchFilesIn(BaseModel):
    query: str = Field(min_length=1, max_length=1000, description="Text to look for in file and folder names and in file contents, up to 1000 characters")
    path: str = Field(default="", description="Restrict the search to this folder, for example '/Documents'; leave empty to search the whole Dropbox")
    max_results: int = Field(default=20, ge=1, le=1000, description="Maximum number of matches to return, from 1 to 1000 (default 20)")


class SearchFilesOut(BaseModel):
    matches: list[Entry] = Field(description="Files and folders that match the query")
    has_more: bool = Field(description="True if there are more matches than were returned")


@function(
    id="dropbox.files.search", version=1, verb=Verb.read, upstream_api="2", scopes=["files.metadata.read"],
    description=(
        "Searches the connected Dropbox for files and folders whose name or content matches a text query, optionally restricted to one folder. Each match reports "
        "whether it is a file or a folder, its name, its display path, its id and, for files, the size in bytes and the last modification time. Use it when the "
        "user asks to find a document, photo or folder by its name or by words it contains and does not know the exact path. It returns up to the requested number "
        "of results (maximum 1000) and tells whether there are more. Read-only. To browse a folder whose path is known use dropbox.files.list instead; this "
        "function does not download file contents."
    ),
    examples=[{"name": "default", "input": {"query": "factura"}, "output": {"matches": [
        {"type": "file", "name": "factura-enero.pdf", "path_display": "/Docs/factura-enero.pdf", "id": "id:xyz", "size": 5000,
         "server_modified": "2026-01-05T09:00:00Z"}], "has_more": False}}],
)
async def files_search(ctx: Context, args: SearchFilesIn) -> SearchFilesOut:
    options: dict[str, Any] = {"max_results": args.max_results}
    if _path(args.path):
        options["path"] = _path(args.path)
    resp = await ctx.conn.request("POST", f"{BASE_URL}/files/search_v2", ok_statuses=(409,),
                                  json={"query": args.query, "options": options})
    if resp.status_code == 409:
        _raise_endpoint_error(resp)
    body = resp.json()
    # cada match: {"metadata": {".tag": "metadata", "metadata": {".tag": "file", ...}}}
    found = [_entry(m["metadata"]["metadata"]) for m in body.get("matches", [])]
    return SearchFilesOut(matches=found, has_more=bool(body.get("has_more")))
