"""Funciones de Google Drive (Drive API v3): about, listar, buscar, leer metadatos, crear carpeta, mover y compartir.

Verificado en el Discovery Document oficial de Drive v3 (www.googleapis.com/discovery/v1/apis/drive/v3/rest, 2026-10-10):
- about.get: GET /about, sin parametros propios; `fields` es obligatorio en la practica. storageQuota trae limit, usage, usageInDrive y
  usageInDriveTrash como cadenas int64 (`limit` no viene en cuentas con almacenamiento ilimitado).
- files.list: GET /files; pageSize 1..1000 (aqui max 100), orderBy (modifiedTime desc, recency...), corpora (user por defecto),
  supportsAllDrives e includeItemsFromAllDrives (default false). El `q` usa literales entre comillas simples.
- files.get / files.create / files.update aceptan supportsAllDrives; files.update mueve con addParents / removeParents (listas
  separadas por coma). `File.parents` solo se cambia asi, y `size` es una cadena int64 que NO existe en archivos nativos de Google.
- permissions.create: POST /files/{fileId}/permissions; body {type, role, emailAddress}; sendNotificationEmail (default true) y
  emailMessage son parametros de query. Roles utiles: reader, commenter, writer.
- files.update (renombrar): PATCH /files/{fileId} con cuerpo {name}; files.copy: POST /files/{fileId}/copy con cuerpo {name, parents} (ambos opcionales;
  sin parents la copia queda junto al original) y los mismos `fields` / `supportsAllDrives`. Los dos aceptan el scope `drive` que la app ya pide.
  Drive no permite copiar carpetas (files.copy es solo para archivos; el codigo de error exacto no se verifico).
- Drive responde 403 tanto por falta de permiso como por limite de ritmo (reason rateLimitExceeded / userRateLimitExceeded /
  sharingRateLimitExceeded): `_call` separa los dos casos porque connections.py traduciria todo 403 a missing_scope.
Nunca se descarga el contenido de un archivo: solo metadatos. Las descripciones y los Field(description=...) estan en INGLES y
completos a proposito: el agente los usa para buscar la funcion y para llenar sus argumentos (doc/funciones/CONTRATO.md).
"""
import re
from typing import Any, Literal, Optional
from urllib.parse import parse_qs, quote, urlparse

from pydantic import BaseModel, Field, model_validator

from app.functions.apps.google_drive.app_spec import APP  # noqa: F401  (registra la app antes que las funciones)
from app.functions.connections import _code_for_403
from app.functions.context import Context
from app.functions.errors import FunctionError
from app.functions.registry import function
from app.functions.spec import ErrorCode, Verb

DRIVE_URL = "https://www.googleapis.com/drive/v3"
SCOPE_DRIVE = "https://www.googleapis.com/auth/drive"
FOLDER_MIME = "application/vnd.google-apps.folder"
FILE_FIELDS = "id,name,mimeType,modifiedTime,webViewLink,parents"
DETAIL_FIELDS = "id,name,mimeType,size,createdTime,modifiedTime,webViewLink,parents,owners(displayName,emailAddress),trashed,shared"

# tipo amigable -> mimeType de Drive
FRIENDLY_TYPES = {
    "folder": FOLDER_MIME,
    "spreadsheet": "application/vnd.google-apps.spreadsheet",
    "document": "application/vnd.google-apps.document",
    "presentation": "application/vnd.google-apps.presentation",
    "pdf": "application/pdf",
}
_RATE_REASONS = {"ratelimitexceeded", "userratelimitexceeded", "sharingratelimitexceeded"}
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,200}$")
_URL_ID_RE = re.compile(r"/(?:d|folders)/([A-Za-z0-9_-]+)")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# --- utilidades ------------------------------------------------------------------------------------

def _reasons(resp) -> set[str]:
    """Razones del error de Google (errors[].reason y details[].reason), en minusculas."""
    try:
        err = (resp.json() or {}).get("error") or {}
    except ValueError:
        return set()
    if not isinstance(err, dict):
        return set()
    found = [e.get("reason") for e in err.get("errors") or [] if isinstance(e, dict)]
    found += [d.get("reason") for d in err.get("details") or [] if isinstance(d, dict)]
    return {str(r).lower() for r in found if r}


async def _call(ctx: Context, method: str, path: str, *, params: Optional[dict] = None, json: Any = None) -> dict:
    """Peticion a Drive. Un 403 por limite de ritmo es rate_limited; sin acceso al archivo, access_denied; cualquier otro, missing_scope."""
    resp = await ctx.conn.request(method, f"{DRIVE_URL}{path}", params=params or None, json=json, ok_statuses=(403,))
    if resp.status_code == 403:
        if _reasons(resp) & _RATE_REASONS:
            raise FunctionError(ErrorCode.rate_limited, "Google Drive limito el ritmo de peticiones; reintenta mas tarde.")
        raise FunctionError(_code_for_403(resp.text), f"HTTP 403: {resp.text[:200]}")
    try:
        body = resp.json()
    except ValueError:
        raise FunctionError(ErrorCode.upstream_changed, "Google respondio algo que no es JSON.") from None
    return body if isinstance(body, dict) else {}


def _escape(value: str) -> str:
    """Escapa un literal del `q` de Drive: barra invertida primero, luego la comilla simple."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


def extract_file_id(value: str) -> str:
    """Acepta un id de Drive o una URL (drive.google.com / docs.google.com) y devuelve solo el id."""
    text = (value or "").strip()
    if not text:
        raise FunctionError(ErrorCode.invalid_input, "Falta el id o la URL del archivo de Drive.")
    if "://" in text or text.startswith(("drive.google.com", "docs.google.com")):
        url = urlparse(text if "://" in text else f"https://{text}")
        m = _URL_ID_RE.search(url.path)
        found = m.group(1) if m else (parse_qs(url.query).get("id") or [""])[0]
        if not found or not _ID_RE.match(found):
            raise FunctionError(ErrorCode.invalid_input, "No se pudo sacar el id de Drive de esa URL.")
        return found
    if not _ID_RE.match(text):
        raise FunctionError(ErrorCode.invalid_input, "El id de Drive solo lleva letras, numeros, '-' y '_'.")
    return text


def _fid(file_id: str) -> str:
    return quote(extract_file_id(file_id), safe="")


# --- modelos compartidos ---------------------------------------------------------------------------

class NoArgs(BaseModel):
    pass


class FileItem(BaseModel):
    id: str = Field(description="Google Drive id of the file or folder, usable in later steps")
    name: Optional[str] = Field(default=None, description="Name of the file or folder")
    mime_type: Optional[str] = Field(default=None, description="MIME type; folders are 'application/vnd.google-apps.folder' and Google Docs, Sheets and Slides start with 'application/vnd.google-apps.'")
    modified_time: Optional[str] = Field(default=None, description="UTC date and time of the last modification")
    web_view_link: Optional[str] = Field(default=None, description="URL that opens the file or folder in the browser")
    parents: list[str] = Field(default_factory=list, description="Ids of the folders that contain this item; empty when the item has no visible parent")


def _item(raw: dict) -> FileItem:
    return FileItem(id=str(raw["id"]), name=raw.get("name"), mime_type=raw.get("mimeType"), modified_time=raw.get("modifiedTime"),
                    web_view_link=raw.get("webViewLink"), parents=[str(p) for p in raw.get("parents") or []])


class FilePage(BaseModel):
    files: list[FileItem] = Field(description="Files and folders found, in the order requested")
    next_page_token: Optional[str] = Field(default=None, description="Token to pass as page_token to get the next page; empty on the last page")


def _int(value: Any) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


# --- google_drive.about.get (whoami) ---------------------------------------------------------------

class About(BaseModel):
    account_id: str = Field(description="Account id: the Google email address, the same value stored when the account was connected")
    email: str = Field(description="Email address of the connected Google account")
    display_name: Optional[str] = Field(default=None, description="Display name of the connected Google account")
    permission_id: Optional[str] = Field(default=None, description="Stable Google Drive permission id of the user")
    storage_limit_bytes: Optional[int] = Field(default=None, description="Total storage allowed in bytes; empty when the account has unlimited storage")
    storage_used_bytes: Optional[int] = Field(default=None, description="Storage used in bytes across Drive, Gmail and Photos")
    storage_used_in_drive_bytes: Optional[int] = Field(default=None, description="Storage used by files in Google Drive in bytes")
    storage_used_in_trash_bytes: Optional[int] = Field(default=None, description="Storage used by files in the Drive trash in bytes")


@function(
    id="google_drive.about.get", version=1, verb=Verb.read, upstream_api="v3", scopes=[SCOPE_DRIVE],
    description=(
        "Returns the Google account connected to Google Drive: its email address (used as the account id), display name, Drive permission id and storage "
        "quota in bytes (limit, total used, used by Drive files and used by the trash). Use it to confirm which Google account is connected, to check "
        "that the connection still works, or to answer 'how much Drive space do I have left?'. Read-only: it takes no parameters and changes nothing. "
        "The limit is empty for accounts with unlimited storage. It does not list files (use google_drive.files.list). If several Google accounts are "
        "connected, one of them must be chosen first."
    ),
    examples=[{"name": "default", "input": {}, "output": {
        "account_id": "ana@empresa.test", "email": "ana@empresa.test", "display_name": "Ana Perez", "permission_id": "11223344556677889900",
        "storage_limit_bytes": 16106127360, "storage_used_bytes": 5368709120, "storage_used_in_drive_bytes": 3221225472,
        "storage_used_in_trash_bytes": 104857600}}],
)
async def about_get(ctx: Context, args: NoArgs) -> About:
    body = await _call(ctx, "GET", "/about", params={
        "fields": "user(displayName,emailAddress,permissionId),storageQuota(limit,usage,usageInDrive,usageInDriveTrash)"})
    user, quota = body.get("user") or {}, body.get("storageQuota") or {}
    if not user.get("emailAddress"):
        raise FunctionError(ErrorCode.upstream_changed, "Google no devolvio el correo del usuario.")
    return About(account_id=str(user["emailAddress"]), email=str(user["emailAddress"]), display_name=user.get("displayName"),
                 permission_id=user.get("permissionId"), storage_limit_bytes=_int(quota.get("limit")), storage_used_bytes=_int(quota.get("usage")),
                 storage_used_in_drive_bytes=_int(quota.get("usageInDrive")), storage_used_in_trash_bytes=_int(quota.get("usageInDriveTrash")))


# --- google_drive.files.list -----------------------------------------------------------------------

class ListFilesIn(BaseModel):
    folder_id: str = Field(default="root", description="Folder to list: its Drive id or URL, or 'root' (default) for My Drive's top level; ignored when recent is true")
    recent: bool = Field(default=False, description="True lists the most recently modified files anywhere in Drive instead of one folder; false (default) lists the folder")
    page_size: int = Field(default=20, ge=1, le=100, description="Maximum number of items to return in this call, from 1 to 100 (default 20)")
    page_token: Optional[str] = Field(default=None, description="Token returned as next_page_token by a previous call to continue from there")


@function(
    id="google_drive.files.list", version=1, verb=Verb.read, upstream_api="v3", scopes=[SCOPE_DRIVE],
    description=(
        "Lists the files and folders directly inside a Google Drive folder (the top level of My Drive by default), or the most recently modified files "
        "anywhere in Drive when recent is true. Each item reports its id, name, MIME type, last modified time, link to open it and parent folder ids. "
        "Use it when the user wants to browse a folder, see what is in their Drive, or find the latest files; folder ids can come from earlier results. "
        "Items in the trash are excluded. It returns up to page_size items (maximum 100) newest first and a next_page_token for more. Read-only. It does "
        "not search by name or content (use google_drive.files.search) and it never downloads file contents."
    ),
    examples=[{"name": "default", "input": {"folder_id": "root", "page_size": 2}, "output": {"files": [
        {"id": "1AbCdEfGhIjKlMnOp", "name": "Reports", "mime_type": "application/vnd.google-apps.folder", "modified_time": "2026-10-01T12:00:00.000Z",
         "web_view_link": "https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOp", "parents": ["0AEXAMPLEROOT"]},
        {"id": "1QrStUvWxYz", "name": "Q3 budget", "mime_type": "application/vnd.google-apps.spreadsheet", "modified_time": "2026-09-30T08:30:00.000Z",
         "web_view_link": "https://docs.google.com/spreadsheets/d/1QrStUvWxYz/edit", "parents": ["0AEXAMPLEROOT"]}],
        "next_page_token": None}}],
)
async def files_list(ctx: Context, args: ListFilesIn) -> FilePage:
    if args.recent:
        q = "trashed=false"
    else:
        folder = extract_file_id(args.folder_id)
        q = f"'{_escape(folder)}' in parents and trashed=false"
    params: dict[str, Any] = {
        "q": q, "pageSize": args.page_size, "orderBy": "modifiedTime desc", "fields": f"nextPageToken,files({FILE_FIELDS})",
        "supportsAllDrives": True, "includeItemsFromAllDrives": True,
    }
    if args.page_token:
        params["pageToken"] = args.page_token
    body = await _call(ctx, "GET", "/files", params=params)
    return FilePage(files=[_item(f) for f in body.get("files") or []], next_page_token=body.get("nextPageToken"))


# --- google_drive.files.search ---------------------------------------------------------------------

class SearchFilesIn(BaseModel):
    name_contains: Optional[str] = Field(default=None, min_length=1, max_length=500, description="Text that must appear in the file or folder name, for example 'invoice'")
    text_contains: Optional[str] = Field(default=None, min_length=1, max_length=500, description="Text that must appear in the file content or name (full-text search), for example 'quarterly forecast'")
    file_type: Optional[Literal["folder", "spreadsheet", "document", "presentation", "pdf"]] = Field(
        default=None, description="Restrict results to one kind of item: folder, spreadsheet (Google Sheets), document (Google Docs), presentation (Google Slides) or pdf")
    page_size: int = Field(default=20, ge=1, le=100, description="Maximum number of items to return in this call, from 1 to 100 (default 20)")
    page_token: Optional[str] = Field(default=None, description="Token returned as next_page_token by a previous call to continue from there")

    @model_validator(mode="after")
    def _needs_a_criterion(self) -> "SearchFilesIn":
        if not any([(self.name_contains or "").strip(), (self.text_contains or "").strip(), self.file_type]):
            raise ValueError("indica al menos name_contains, text_contains o file_type")
        return self


def build_search_query(args: SearchFilesIn) -> str:
    """Arma el `q` de Drive escapando cada texto del usuario; siempre excluye la papelera."""
    parts = []
    if (args.name_contains or "").strip():
        parts.append(f"name contains '{_escape(args.name_contains.strip())}'")
    if (args.text_contains or "").strip():
        parts.append(f"fullText contains '{_escape(args.text_contains.strip())}'")
    if args.file_type:
        parts.append(f"mimeType = '{FRIENDLY_TYPES[args.file_type]}'")
    parts.append("trashed=false")
    return " and ".join(parts)


@function(
    id="google_drive.files.search", version=1, verb=Verb.read, upstream_api="v3", scopes=[SCOPE_DRIVE],
    description=(
        "Searches Google Drive for files and folders by part of the name, by words inside the content (full-text) and/or by kind: folder, spreadsheet, "
        "document, presentation or pdf. At least one criterion is required and they are combined with AND; the trash is excluded. Each match reports its id, "
        "name, MIME type, last modified time, link and parent folder ids, newest first. Use it when the user asks to find a file, for example 'find the Q3 "
        "budget spreadsheet', without knowing its folder. It returns up to page_size matches (maximum 100) and a next_page_token. Read-only. To browse one "
        "folder use google_drive.files.list; it never downloads file contents."
    ),
    examples=[{"name": "default", "input": {"name_contains": "budget", "file_type": "spreadsheet"}, "output": {"files": [
        {"id": "1QrStUvWxYz", "name": "Q3 budget", "mime_type": "application/vnd.google-apps.spreadsheet", "modified_time": "2026-09-30T08:30:00.000Z",
         "web_view_link": "https://docs.google.com/spreadsheets/d/1QrStUvWxYz/edit", "parents": ["1AbCdEfGhIjKlMnOp"]}],
        "next_page_token": None}}],
)
async def files_search(ctx: Context, args: SearchFilesIn) -> FilePage:
    params: dict[str, Any] = {
        "q": build_search_query(args), "pageSize": args.page_size, "orderBy": "modifiedTime desc",
        "fields": f"nextPageToken,files({FILE_FIELDS})", "supportsAllDrives": True, "includeItemsFromAllDrives": True,
    }
    if args.page_token:
        params["pageToken"] = args.page_token
    body = await _call(ctx, "GET", "/files", params=params)
    return FilePage(files=[_item(f) for f in body.get("files") or []], next_page_token=body.get("nextPageToken"))


# --- google_drive.files.get ------------------------------------------------------------------------

class GetFileIn(BaseModel):
    file_id: str = Field(min_length=1, description="Drive id of the file or folder, or a Google Drive / Docs / Sheets / Slides URL from which the id is extracted")


class FileDetails(FileItem):
    created_time: Optional[str] = Field(default=None, description="UTC date and time when the file was created")
    size_bytes: Optional[int] = Field(default=None, description="Size in bytes; empty for Google Docs, Sheets, Slides and folders, which have no stored size")
    owners: list[str] = Field(default_factory=list, description="Email addresses of the owners of the file")
    trashed: bool = Field(default=False, description="True when the file is in the trash")
    shared: bool = Field(default=False, description="True when the file is shared with other people")


@function(
    id="google_drive.files.get", version=1, verb=Verb.read, upstream_api="v3", scopes=[SCOPE_DRIVE],
    description=(
        "Returns the metadata of one Google Drive file or folder, given its id or any Drive, Docs, Sheets or Slides URL: name, MIME type, size in bytes (not "
        "available for Google-native files), created and modified times, link to open it, parent folder ids, owner emails, and whether it is trashed or shared. "
        "Use it when the user pastes a Drive link and asks what it is, who owns it, when it changed, or whether it is shared, or to check a file before moving "
        "or sharing it. Read-only. It never downloads or reads the file contents and does not list who it is shared with. Fails with not found when the id does "
        "not exist or the account cannot see it."
    ),
    examples=[{"name": "default", "input": {"file_id": "https://docs.google.com/spreadsheets/d/1QrStUvWxYz/edit"}, "output": {
        "id": "1QrStUvWxYz", "name": "Q3 budget", "mime_type": "application/vnd.google-apps.spreadsheet", "modified_time": "2026-09-30T08:30:00.000Z",
        "web_view_link": "https://docs.google.com/spreadsheets/d/1QrStUvWxYz/edit", "parents": ["1AbCdEfGhIjKlMnOp"], "created_time": "2026-07-01T09:00:00.000Z",
        "size_bytes": None, "owners": ["ana@empresa.test"], "trashed": False, "shared": True}}],
)
async def files_get(ctx: Context, args: GetFileIn) -> FileDetails:
    raw = await _call(ctx, "GET", f"/files/{_fid(args.file_id)}", params={"fields": DETAIL_FIELDS, "supportsAllDrives": True})
    base = _item(raw)
    return FileDetails(**base.model_dump(), created_time=raw.get("createdTime"), size_bytes=_int(raw.get("size")),
                       owners=[str(o["emailAddress"]) for o in raw.get("owners") or [] if o.get("emailAddress")],
                       trashed=bool(raw.get("trashed")), shared=bool(raw.get("shared")))


# --- google_drive.folders.create -------------------------------------------------------------------

class CreateFolderIn(BaseModel):
    name: str = Field(min_length=1, max_length=255, description="Name of the new folder, for example 'Invoices 2026'")
    parent_folder_id: Optional[str] = Field(default=None, description="Drive id or URL of the folder that will contain the new one; leave empty to create it at the top level of My Drive")


class CreatedFolder(BaseModel):
    id: str = Field(description="Drive id of the new folder")
    name: str = Field(description="Name of the new folder")
    web_view_link: Optional[str] = Field(default=None, description="URL that opens the new folder in the browser")
    parents: list[str] = Field(default_factory=list, description="Id of the folder that contains the new one")


@function(
    id="google_drive.folders.create", version=1, verb=Verb.create, reversible=True, upstream_api="v3", scopes=[SCOPE_DRIVE],
    description=(
        "Creates a new, empty folder in Google Drive with the given name, either at the top level of My Drive or inside a parent folder identified by id or "
        "URL. Returns the new folder id, name, link and parent id. Use it when the user asks to create or set up a folder, for example before moving files "
        "into it. Drive allows several folders with the same name, so this does not check for duplicates: use google_drive.files.search first if that matters. "
        "It only creates the folder (reversible by trashing it in Drive); it does not move files into it (use google_drive.files.move), does not share it "
        "and sends nothing outside Drive."
    ),
    examples=[{"name": "default", "input": {"name": "Invoices 2026", "parent_folder_id": "1AbCdEfGhIjKlMnOp"}, "output": {
        "id": "1NewFolderId", "name": "Invoices 2026", "web_view_link": "https://drive.google.com/drive/folders/1NewFolderId", "parents": ["1AbCdEfGhIjKlMnOp"]}}],
)
async def folders_create(ctx: Context, args: CreateFolderIn) -> CreatedFolder:
    body: dict[str, Any] = {"name": args.name.strip(), "mimeType": FOLDER_MIME}
    if not body["name"]:
        raise FunctionError(ErrorCode.invalid_input, "El nombre de la carpeta no puede estar vacio.")
    if args.parent_folder_id and args.parent_folder_id.strip():
        body["parents"] = [extract_file_id(args.parent_folder_id)]
    raw = await _call(ctx, "POST", "/files", params={"fields": "id,name,webViewLink,parents", "supportsAllDrives": True}, json=body)
    if not raw.get("id"):
        raise FunctionError(ErrorCode.upstream_changed, "Google no devolvio el id de la carpeta creada.")
    return CreatedFolder(id=str(raw["id"]), name=str(raw.get("name") or body["name"]), web_view_link=raw.get("webViewLink"),
                         parents=[str(p) for p in raw.get("parents") or []])


# --- google_drive.files.move -----------------------------------------------------------------------

class MoveFileIn(BaseModel):
    file_id: str = Field(min_length=1, description="Drive id or URL of the file or folder to move")
    destination_folder_id: str = Field(min_length=1, description="Drive id or URL of the folder to move it into, or 'root' for the top level of My Drive")


class MovedFile(BaseModel):
    id: str = Field(description="Drive id of the moved file or folder")
    name: Optional[str] = Field(default=None, description="Name of the moved file or folder")
    web_view_link: Optional[str] = Field(default=None, description="URL that opens the moved item in the browser")
    parents: list[str] = Field(default_factory=list, description="Ids of the folders that contain the item after the move")


@function(
    id="google_drive.files.move", version=1, verb=Verb.update, reversible=True, upstream_api="v3", scopes=[SCOPE_DRIVE],
    description=(
        "Moves a Google Drive file or folder into another folder: it reads the current parent folders, adds the destination and removes the old parents in "
        "one update. Both the item and the destination can be given as an id or a Drive URL, and 'root' means the top level of My Drive. Returns the id, "
        "name, link and the new parent ids. Use it when the user asks to move or reorganize a file or folder, for example 'move the budget into Reports'. "
        "It is reversible by moving the item back. It moves the same item (it does not copy, rename, trash or share anything) and fails with not found when "
        "the item or destination does not exist or is not visible to the account."
    ),
    examples=[{"name": "default", "input": {"file_id": "1QrStUvWxYz", "destination_folder_id": "1AbCdEfGhIjKlMnOp"}, "output": {
        "id": "1QrStUvWxYz", "name": "Q3 budget", "web_view_link": "https://docs.google.com/spreadsheets/d/1QrStUvWxYz/edit", "parents": ["1AbCdEfGhIjKlMnOp"]}}],
)
async def files_move(ctx: Context, args: MoveFileIn) -> MovedFile:
    file_id, dest = extract_file_id(args.file_id), extract_file_id(args.destination_folder_id)
    if file_id == dest:
        raise FunctionError(ErrorCode.invalid_input, "No se puede mover una carpeta dentro de si misma.")
    current = await _call(ctx, "GET", f"/files/{quote(file_id, safe='')}", params={"fields": "parents", "supportsAllDrives": True})
    old = [str(p) for p in current.get("parents") or []]
    params: dict[str, Any] = {"fields": "id,name,webViewLink,parents", "supportsAllDrives": True}
    if dest not in old:
        params["addParents"] = dest
    remove = [p for p in old if p != dest]
    if remove:
        params["removeParents"] = ",".join(remove)
    raw = await _call(ctx, "PATCH", f"/files/{quote(file_id, safe='')}", params=params, json={})
    if not raw.get("id"):
        raise FunctionError(ErrorCode.upstream_changed, "Google no devolvio el archivo movido.")
    return MovedFile(id=str(raw["id"]), name=raw.get("name"), web_view_link=raw.get("webViewLink"), parents=[str(p) for p in raw.get("parents") or []])


# --- google_drive.files.share ----------------------------------------------------------------------

class ShareFileIn(BaseModel):
    file_id: str = Field(min_length=1, description="Drive id or URL of the file or folder to share")
    email: str = Field(min_length=3, max_length=320, description="Email address of the person to share with, for example 'luis@empresa.test'")
    role: Literal["reader", "commenter", "writer"] = Field(default="reader", description="Access level to grant: reader (view only, default), commenter (view and comment) or writer (view and edit)")
    send_notification_email: bool = Field(default=True, description="True (default) emails the person that the item was shared; false shares silently")
    message: Optional[str] = Field(default=None, max_length=1000, description="Optional plain-text message included in the notification email; ignored when send_notification_email is false")

    @model_validator(mode="after")
    def _email_ok(self) -> "ShareFileIn":
        if not _EMAIL_RE.match(self.email.strip()):
            raise ValueError("email no parece una direccion valida")
        return self


class SharedFile(BaseModel):
    permission_id: str = Field(description="Id of the permission that was created; it identifies this grant of access")
    file_id: str = Field(description="Drive id of the file or folder that was shared")
    email: Optional[str] = Field(default=None, description="Email address that now has access")
    role: Optional[str] = Field(default=None, description="Access level granted: reader, commenter or writer")
    notification_sent: bool = Field(description="True when Drive emailed the person about the share")


@function(
    id="google_drive.files.share", version=1, verb=Verb.create, exits_outside=True, reversible=True, upstream_api="v3", scopes=[SCOPE_DRIVE],
    description=(
        "Shares a Google Drive file or folder with one person by email, granting reader (view), commenter or writer (edit) access. By default Drive sends that "
        "person a notification email, optionally with a custom message; set send_notification_email to false to share without emailing. Returns the permission "
        "id, the email, the role and whether a notification was sent. Use it when the user asks to share, give access to, or send a file to someone. It "
        "gives access outside the user's control, so it should be confirmed first; access can be revoked later in Drive. It shares with one person per "
        "call (no public links, groups or ownership transfer) and may fail if the organization blocks sharing outside its domain."
    ),
    examples=[{"name": "default", "input": {"file_id": "1QrStUvWxYz", "email": "luis@empresa.test", "role": "reader", "send_notification_email": True}, "output": {
        "permission_id": "09876543210987654321", "file_id": "1QrStUvWxYz", "email": "luis@empresa.test", "role": "reader", "notification_sent": True}}],
)
async def files_share(ctx: Context, args: ShareFileIn) -> SharedFile:
    file_id = extract_file_id(args.file_id)
    params: dict[str, Any] = {"fields": "id,type,role,emailAddress", "supportsAllDrives": True, "sendNotificationEmail": args.send_notification_email}
    if args.send_notification_email and args.message and args.message.strip():
        params["emailMessage"] = args.message.strip()
    raw = await _call(ctx, "POST", f"/files/{quote(file_id, safe='')}/permissions", params=params,
                      json={"type": "user", "role": args.role, "emailAddress": args.email.strip()})
    if not raw.get("id"):
        raise FunctionError(ErrorCode.upstream_changed, "Google no devolvio el permiso creado.")
    return SharedFile(permission_id=str(raw["id"]), file_id=file_id, email=raw.get("emailAddress") or args.email.strip(),
                      role=raw.get("role") or args.role, notification_sent=args.send_notification_email)


# --- google_drive.files.rename ---------------------------------------------------------------------

class RenameFileIn(BaseModel):
    file_id: str = Field(min_length=1, description="Drive id or URL of the file or folder to rename")
    new_name: str = Field(min_length=1, max_length=255, description="New name for the file or folder, for example 'Q3 budget (final)'; include the extension for uploaded files, such as 'report.pdf'")


@function(
    id="google_drive.files.rename", version=1, verb=Verb.update, reversible=True, upstream_api="v3", scopes=[SCOPE_DRIVE],
    description=(
        "Renames a Google Drive file or folder, given as an id or any Drive, Docs, Sheets or Slides URL, and returns its id, new name, MIME type, last modified "
        "time, link and parent folder ids. Use it when the user asks to rename a file or folder, for example 'rename the budget to Q3 budget (final)'. Only the name "
        "changes: content, location and sharing stay the same, and it is reversible by renaming it back. Drive allows several items with the same name in a folder, "
        "so no duplicate check is made. It does not move (use google_drive.files.move), copy (use google_drive.files.copy), trash or share anything, and fails "
        "with not found when the item does not exist or is not visible to the account."
    ),
    examples=[{"name": "default", "input": {"file_id": "1QrStUvWxYz", "new_name": "Q3 budget (final)"}, "output": {
        "id": "1QrStUvWxYz", "name": "Q3 budget (final)", "mime_type": "application/vnd.google-apps.spreadsheet", "modified_time": "2026-10-10T15:00:00.000Z",
        "web_view_link": "https://docs.google.com/spreadsheets/d/1QrStUvWxYz/edit", "parents": ["1AbCdEfGhIjKlMnOp"]}}],
)
async def files_rename(ctx: Context, args: RenameFileIn) -> FileItem:
    name = args.new_name.strip()
    if not name:
        raise FunctionError(ErrorCode.invalid_input, "El nombre nuevo no puede estar vacio.")
    raw = await _call(ctx, "PATCH", f"/files/{_fid(args.file_id)}", params={"fields": FILE_FIELDS, "supportsAllDrives": True}, json={"name": name})
    if not raw.get("id"):
        raise FunctionError(ErrorCode.upstream_changed, "Google no devolvio el archivo renombrado.")
    return _item(raw)


# --- google_drive.files.copy -----------------------------------------------------------------------

class CopyFileIn(BaseModel):
    file_id: str = Field(min_length=1, description="Drive id or URL of the file to copy; folders cannot be copied")
    new_name: Optional[str] = Field(default=None, max_length=255, description="Name for the copy; when omitted Drive names it 'Copy of <original name>'")
    destination_folder_id: Optional[str] = Field(default=None, description="Drive id or URL of the folder that will hold the copy, or 'root' for the top level of My Drive; when omitted the copy goes in the same folder as the original")


@function(
    id="google_drive.files.copy", version=1, verb=Verb.create, reversible=True, upstream_api="v3", scopes=[SCOPE_DRIVE],
    description=(
        "Makes a copy of a Google Drive file (a Google Doc, Sheet or Slides file or an uploaded file such as a PDF), given as an id or any Drive, Docs, Sheets or "
        "Slides URL, and returns the id, name, MIME type, link and parent folder ids of the new file. The copy gets the optional new_name (otherwise 'Copy of' "
        "followed by the original name) and goes into the optional destination folder (otherwise next to the original). Use it when the user asks to duplicate a "
        "file, make a copy of a template, or save a copy in another folder. The original is untouched and the copy can be trashed in Drive to undo it. It does not "
        "copy folders, move (use google_drive.files.move), rename (use google_drive.files.rename) or share anything."
    ),
    examples=[{"name": "default", "input": {"file_id": "1QrStUvWxYz", "new_name": "Q4 budget", "destination_folder_id": "1AbCdEfGhIjKlMnOp"}, "output": {
        "id": "1CopyOfQ3Budget", "name": "Q4 budget", "mime_type": "application/vnd.google-apps.spreadsheet", "modified_time": "2026-10-10T15:00:00.000Z",
        "web_view_link": "https://docs.google.com/spreadsheets/d/1CopyOfQ3Budget/edit", "parents": ["1AbCdEfGhIjKlMnOp"]}}],
)
async def files_copy(ctx: Context, args: CopyFileIn) -> FileItem:
    body: dict[str, Any] = {}
    if args.new_name is not None:
        name = args.new_name.strip()
        if not name:
            raise FunctionError(ErrorCode.invalid_input, "El nombre de la copia no puede estar vacio; omitelo para usar el nombre por defecto.")
        body["name"] = name
    if args.destination_folder_id and args.destination_folder_id.strip():
        body["parents"] = [extract_file_id(args.destination_folder_id)]
    raw = await _call(ctx, "POST", f"/files/{_fid(args.file_id)}/copy", params={"fields": FILE_FIELDS, "supportsAllDrives": True}, json=body)
    if not raw.get("id"):
        raise FunctionError(ErrorCode.upstream_changed, "Google no devolvio la copia creada.")
    return _item(raw)
