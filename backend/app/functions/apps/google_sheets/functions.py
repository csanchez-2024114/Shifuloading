"""Funciones de Google Sheets (Sheets API v4) y la identidad de la cuenta (OpenID userinfo).

Verificado contra la referencia oficial de Sheets API v4 (developers.google.com/sheets/api/reference/rest/v4/spreadsheets, 2026-10-10):
- spreadsheets.get: GET /v4/spreadsheets/{id}; `includeGridData` es false por defecto (no baja celdas) y `fields` recorta la respuesta.
- spreadsheets.values.get: GET /v4/spreadsheets/{id}/values/{range}; `valueRenderOption=FORMATTED_VALUE` (texto como se ve en la hoja) y
  `majorDimension=ROWS`. La API OMITE las celdas vacias del final de cada fila y las filas vacias del final: las filas pueden tener largos distintos.
- spreadsheets.values.append: POST .../values/{range}:append con `valueInputOption` (obligatorio) e `insertDataOption=INSERT_ROWS`
  (inserta filas nuevas en vez de pisar las siguientes). Respuesta: `updates` con updatedRange/updatedRows/updatedColumns/updatedCells.
- spreadsheets.values.update: PUT .../values/{range} con `valueInputOption` obligatorio; en ValueRange.values las celdas vacias (null) se
  saltan, y para vaciar una celda hay que mandar la cadena vacia. Respuesta: updatedRange/updatedRows/updatedColumns/updatedCells.
- spreadsheets.create: POST /v4/spreadsheets con `properties.title` y `sheets[].properties.title`; devuelve spreadsheetId y spreadsheetUrl.
  Se crea en la raiz del Drive del usuario.
- spreadsheets.batchUpdate: POST /v4/spreadsheets/{id}:batchUpdate con la solicitud `addSheet`; la respuesta trae replies[0].addSheet.properties.
  Un titulo de pestana repetido responde 400.
- spreadsheets.values.clear: POST .../values/{range}:clear con cuerpo vacio; solo borra valores (no formato). Respuesta: spreadsheetId y clearedRange.
- batchUpdate con `updateSheetProperties` (properties{sheetId, title}, fields="title") renombra una pestana; su respuesta es una lista de respuestas vacias.
  Un titulo repetido responde 400. Todas estas llamadas aceptan el scope `spreadsheets` que la app ya pide.
- Identidad: GET https://openidconnect.googleapis.com/v1/userinfo (scopes openid/email/profile) devuelve sub, name, email, email_verified.
- Sin scope de Drive no se pueden listar las hojas del usuario: las funciones piden la URL o el id (se extrae el id de una URL completa).
- Errores: 403 (permiso, hoja no compartida o limite de ritmo) lo separa connections._code_for_403 en missing_scope / access_denied / rate_limited; 404 -> not_found; 400 (rango mal escrito, pestana repetida) -> invalid_input.
Las descripciones y los Field(description=...) estan en INGLES y completos a proposito: el agente los usa para buscar la funcion
y para llenar sus argumentos (ver doc/funciones/CONTRATO.md, "Descripciones").
"""
import re
from typing import Any, Optional, Union
from urllib.parse import quote

from pydantic import BaseModel, Field, field_validator

from app.functions.apps.google_sheets.app_spec import APP  # noqa: F401  (registra la app antes que las funciones)
from app.functions.context import Context
from app.functions.errors import FunctionError
from app.functions.registry import function
from app.functions.spec import ErrorCode, Verb

SHEETS_URL = "https://sheets.googleapis.com/v4/spreadsheets"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
SCOPE_SHEETS = "https://www.googleapis.com/auth/spreadsheets"
SCOPES_IDENTITY = ["openid", "email"]

MAX_READ_ROWS = 200       # filas de datos que devuelve values.get (sin contar la fila de encabezado)
MAX_WRITE_ROWS = 500      # filas que se aceptan por escritura
MAX_ROW_CELLS = 200       # celdas por fila en una escritura
VALUE_INPUT = "USER_ENTERED"  # los textos se interpretan como si el usuario los tecleara (formulas, fechas, numeros)

_URL_ID_RE = re.compile(r"/spreadsheets/(?:u/\d+/)?d/([A-Za-z0-9_-]+)")
_BARE_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")

Cell = Union[str, int, float, bool, None]


def extract_spreadsheet_id(raw: str) -> str:
    """Acepta el id solo o la URL completa de la hoja (docs.google.com/spreadsheets/d/<id>/edit#gid=0) y devuelve el id."""
    text = str(raw).strip()
    match = _URL_ID_RE.search(text)
    if match:
        return match.group(1)
    if _BARE_ID_RE.match(text):
        return text
    raise ValueError("spreadsheet_id must be the spreadsheet id or its full Google Sheets URL (https://docs.google.com/spreadsheets/d/<id>/edit)")


class _SheetIn(BaseModel):
    spreadsheet_id: str = Field(
        min_length=1,
        description=("Id of the spreadsheet, or its full Google Sheets URL (the id is extracted from it): the long string between /d/ and /edit "
                     "in https://docs.google.com/spreadsheets/d/<id>/edit. The user has to provide it because spreadsheets cannot be listed"))

    @field_validator("spreadsheet_id", mode="before")
    @classmethod
    def _to_id(cls, v: Any) -> str:
        return extract_spreadsheet_id(v)


def _quote_tab(title: str) -> str:
    """Titulo de pestana listo para A1: entre comillas simples, duplicando las comillas internas."""
    return "'" + title.replace("'", "''") + "'"


def _sheet_url(spreadsheet_id: str, suffix: str = "") -> str:
    return f"{SHEETS_URL}/{quote(spreadsheet_id, safe='')}{suffix}"


def _values_url(spreadsheet_id: str, a1_range: str, suffix: str = "") -> str:
    return f"{SHEETS_URL}/{quote(spreadsheet_id, safe='')}/values/{quote(a1_range, safe='')}{suffix}"


async def _json(ctx: Context, method: str, url: str, *, params: Optional[dict] = None, body: Any = None) -> dict:
    resp = await ctx.conn.request(method, url, params=params or None, json=body)
    try:
        data = resp.json()
    except ValueError:
        raise FunctionError(ErrorCode.upstream_changed, "Google respondio algo que no es JSON.") from None
    return data if isinstance(data, dict) else {}


async def _first_tab(ctx: Context, spreadsheet_id: str) -> str:
    data = await _json(ctx, "GET", _sheet_url(spreadsheet_id), params={"fields": "sheets.properties.title"})
    for sheet in data.get("sheets") or []:
        title = (sheet.get("properties") or {}).get("title")
        if title:
            return str(title)
    raise FunctionError(ErrorCode.upstream_changed, "Google no devolvio ninguna pestana de la hoja.")


class _SheetTab(BaseModel):
    sheet_id: Optional[int] = Field(default=None, description="Numeric id of the tab inside the spreadsheet (the gid shown in the URL)")
    title: str = Field(description="Title of the tab, exactly as shown on the tab at the bottom of the spreadsheet")
    index: Optional[int] = Field(default=None, description="Zero-based position of the tab among the tabs of the spreadsheet")
    row_count: Optional[int] = Field(default=None, description="Number of rows of the tab grid, including empty ones")
    column_count: Optional[int] = Field(default=None, description="Number of columns of the tab grid, including empty ones")
    hidden: bool = Field(default=False, description="True when the tab is hidden in the spreadsheet")


def _tab(raw: dict) -> _SheetTab:
    props = raw.get("properties") or {}
    grid = props.get("gridProperties") or {}
    return _SheetTab(sheet_id=props.get("sheetId"), title=str(props.get("title") or ""), index=props.get("index"),
                     row_count=grid.get("rowCount"), column_count=grid.get("columnCount"), hidden=bool(props.get("hidden")))


# --- google_sheets.account.get (whoami) ------------------------------------------------------------

class AccountGetIn(BaseModel):
    pass


class AccountGetOut(BaseModel):
    account_id: str = Field(description="Email address of the connected Google account; the same value stored when the account was connected")
    email: str = Field(description="Email address of the connected Google account")
    name: Optional[str] = Field(default=None, description="Full display name of the Google account owner, when the profile has one")
    google_user_id: Optional[str] = Field(default=None, description="Stable numeric id (the OpenID sub claim) of the Google account")


@function(
    id="google_sheets.account.get", version=1, verb=Verb.read, upstream_api="v4", scopes=SCOPES_IDENTITY,
    description=(
        "Identifies the Google account that is connected to Google Sheets: it returns the account id (the email address), the email, the display name and "
        "the stable Google user id. Use it to answer 'which Google account do I have connected for spreadsheets?', to confirm that the connection still "
        "works, or to tell several connected accounts apart. It takes no parameters. Read-only: it does not list, open or change any spreadsheet. Spreadsheets "
        "cannot be listed with the permissions granted to this connection, so the user must provide the URL or the id of the spreadsheet to work on."
    ),
    examples=[{"name": "default", "input": {}, "output": {
        "account_id": "ana@empresa.test", "email": "ana@empresa.test", "name": "Ana Perez", "google_user_id": "112233445566778899001"}}],
)
async def account_get(ctx: Context, args: AccountGetIn) -> AccountGetOut:
    info = await _json(ctx, "GET", USERINFO_URL)
    email = info.get("email")
    if not email:
        raise FunctionError(ErrorCode.upstream_changed, "Google no devolvio el correo de la cuenta.")
    return AccountGetOut(account_id=str(email), email=str(email), name=info.get("name"), google_user_id=info.get("sub"))


# --- google_sheets.spreadsheets.get ----------------------------------------------------------------

class SpreadsheetGetOut(BaseModel):
    spreadsheet_id: str = Field(description="Id of the spreadsheet")
    title: str = Field(description="Title of the spreadsheet file")
    url: Optional[str] = Field(default=None, description="URL that opens the spreadsheet in Google Sheets")
    locale: Optional[str] = Field(default=None, description="Locale of the spreadsheet, for example en_US or es_MX; it drives number and date formats")
    time_zone: Optional[str] = Field(default=None, description="Time zone of the spreadsheet, for example America/Mexico_City")
    sheets: list[_SheetTab] = Field(default_factory=list, description="Tabs of the spreadsheet in order, each with its title, id, position and grid size")


@function(
    id="google_sheets.spreadsheets.get", version=1, verb=Verb.read, upstream_api="v4", scopes=[SCOPE_SHEETS],
    description=(
        "Reads the structure of one Google Sheets spreadsheet without downloading its cells: the title, the link, the locale, the time zone and every tab "
        "(sheet) with its title, numeric id, position, hidden flag and number of rows and columns. Use it when the user asks what tabs a spreadsheet has, "
        "how big a tab is, or before reading or writing a tab whose exact name is not known. It requires the spreadsheet id or its full URL, which the user "
        "must provide. Read-only: it does not return cell values (use google_sheets.values.get), it does not search spreadsheets by name and it changes nothing."
    ),
    examples=[{"name": "default", "input": {"spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"}, "output": {
        "spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms", "title": "Sales 2026",
        "url": "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit",
        "locale": "en_US", "time_zone": "America/Mexico_City",
        "sheets": [{"sheet_id": 0, "title": "Q3", "index": 0, "row_count": 1000, "column_count": 26, "hidden": False}]}}],
)
async def spreadsheets_get(ctx: Context, args: _SheetIn) -> SpreadsheetGetOut:
    fields = ("spreadsheetId,spreadsheetUrl,properties(title,locale,timeZone),"
              "sheets.properties(sheetId,title,index,hidden,gridProperties(rowCount,columnCount))")
    data = await _json(ctx, "GET", _sheet_url(args.spreadsheet_id), params={"fields": fields})
    props = data.get("properties") or {}
    if not data.get("spreadsheetId") or props.get("title") is None:
        raise FunctionError(ErrorCode.upstream_changed, "Google no devolvio el id ni el titulo de la hoja.")
    return SpreadsheetGetOut(spreadsheet_id=str(data["spreadsheetId"]), title=str(props["title"]), url=data.get("spreadsheetUrl"),
                             locale=props.get("locale"), time_zone=props.get("timeZone"), sheets=[_tab(s) for s in data.get("sheets") or []])


# --- google_sheets.values.get ----------------------------------------------------------------------

class ValuesGetIn(_SheetIn):
    range: Optional[str] = Field(
        default=None,
        description=("A1 range to read, for example 'Sales!A1:D50', 'A1:D50' (first tab) or just a tab name 'Sales'. Tab names with spaces or symbols go in single "
                     "quotes: \"'Q3 2026'!A:C\". When omitted, the first rows of the first tab are read"))


class ValuesGetOut(BaseModel):
    spreadsheet_id: str = Field(description="Id of the spreadsheet that was read")
    range: str = Field(description="A1 range that was actually read, including the tab name, as normalized by Google")
    header: list[str] = Field(default_factory=list, description="First row of the range as text, usually the column titles; empty when the range has no values")
    rows: list[list[str]] = Field(default_factory=list, description="Rows after the header as lists of formatted text; trailing empty cells are omitted so rows can have different lengths")
    returned_rows: int = Field(description="Number of rows in rows (the header is not counted); at most 200")
    truncated: bool = Field(description="True when the range had more than 200 rows after the header and the rest were left out")


async def _read_grid(ctx: Context, spreadsheet_id: str, a1: Optional[str], default_last_row: int) -> tuple[str, list[list[str]]]:
    """Lee un rango como texto formateado y devuelve (rango normalizado por Google, filas). Sin rango: primera pestana hasta `default_last_row`."""
    if a1 and a1.strip():
        a1 = a1.strip()
    else:  # sin rango: primera pestana, solo las filas necesarias
        a1 = f"{_quote_tab(await _first_tab(ctx, spreadsheet_id))}!1:{default_last_row}"
    data = await _json(ctx, "GET", _values_url(spreadsheet_id, a1),
                       params={"valueRenderOption": "FORMATTED_VALUE", "majorDimension": "ROWS"})
    raw = [[("" if c is None else str(c)) for c in (row or [])] for row in data.get("values") or [] if isinstance(row, list)]
    return str(data.get("range") or a1), raw


@function(
    id="google_sheets.values.get", version=1, verb=Verb.read, upstream_api="v4", scopes=[SCOPE_SHEETS],
    description=(
        "Reads the cell values of a range of a Google Sheets spreadsheet and returns the first row as the header plus the following rows as lists of text, "
        "exactly as the cells look in the sheet (formatted values: dates, currencies and percentages as displayed, formulas as their result). Use it when the "
        "user asks to see, summarize, search or analyze the data of a sheet, for example 'show me the Sales tab' or 'what is in A1:D20'. It needs the spreadsheet "
        "id or full URL; the range is optional and defaults to the first tab. It returns at most 200 rows after the header and flags truncated when there are more. "
        "Read-only: it does not return formulas, formatting or charts, does not write cells and cannot list the spreadsheets of the user."
    ),
    examples=[{"name": "default", "input": {"spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms", "range": "Q3!A1:C3"}, "output": {
        "spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms", "range": "Q3!A1:C3",
        "header": ["Client", "Amount", "Date"], "rows": [["Acme", "$1,200.00", "2026-07-03"], ["Globex", "$980.50", "2026-07-09"]],
        "returned_rows": 2, "truncated": False}}],
)
async def values_get(ctx: Context, args: ValuesGetIn) -> ValuesGetOut:
    # encabezado + tope + 1 para saber si hay mas
    a1, raw = await _read_grid(ctx, args.spreadsheet_id, args.range, MAX_READ_ROWS + 2)
    body = raw[1:]
    return ValuesGetOut(spreadsheet_id=args.spreadsheet_id, range=a1, header=raw[0] if raw else [],
                        rows=body[:MAX_READ_ROWS], returned_rows=min(len(body), MAX_READ_ROWS), truncated=len(body) > MAX_READ_ROWS)


# --- escrituras: modelos comunes --------------------------------------------------------------------

def _check_rows(rows: list[list[Cell]]) -> list[list[Cell]]:
    for row in rows:
        if len(row) > MAX_ROW_CELLS:
            raise ValueError(f"each row can have at most {MAX_ROW_CELLS} cells")
    return rows


class WriteOut(BaseModel):
    spreadsheet_id: str = Field(description="Id of the spreadsheet that was written")
    updated_range: str = Field(description="A1 range of the cells that were written, including the tab name")
    updated_rows: int = Field(description="Number of rows written")
    updated_columns: int = Field(description="Number of columns written")
    updated_cells: int = Field(description="Number of cells written")


def _write_out(spreadsheet_id: str, block: dict) -> WriteOut:
    if not block.get("updatedRange"):
        raise FunctionError(ErrorCode.upstream_changed, "Google no devolvio el rango escrito.")
    return WriteOut(spreadsheet_id=spreadsheet_id, updated_range=str(block["updatedRange"]), updated_rows=int(block.get("updatedRows") or 0),
                    updated_columns=int(block.get("updatedColumns") or 0), updated_cells=int(block.get("updatedCells") or 0))


# --- google_sheets.values.append -------------------------------------------------------------------

class ValuesAppendIn(_SheetIn):
    values: list[list[Cell]] = Field(
        min_length=1, max_length=MAX_WRITE_ROWS,
        description=("Rows to add, as a list of rows and each row a list of cell values (text, numbers, true/false or null for an empty cell), for example "
                     "[[\"Acme\", 1200, \"2026-07-03\"]]. Up to 500 rows of 200 cells. Text starting with = is entered as a formula"))
    range: Optional[str] = Field(
        default=None,
        description=("Tab name or A1 range whose table receives the rows, for example 'Sales' or 'Sales!A1:C1'; the rows go after the last row with data. "
                     "Tab names with spaces go in single quotes: \"'Q3 2026'\". When omitted, the first tab is used"))

    @field_validator("values")
    @classmethod
    def _limit_cells(cls, v: list[list[Cell]]) -> list[list[Cell]]:
        return _check_rows(v)


@function(
    id="google_sheets.values.append", version=1, verb=Verb.create, exits_outside=False, reversible=True, upstream_api="v4", scopes=[SCOPE_SHEETS],
    description=(
        "Appends one or more rows after the last row with data of a table in a Google Sheets spreadsheet and returns the range written, with the number of "
        "rows, columns and cells added. Use it when the user asks to add a record, log an entry or save new rows in a sheet, for example 'add a row with this "
        "client and amount to the Sales tab'. It needs the spreadsheet id or full URL and the rows as lists of cells; the tab or range is optional and defaults to "
        "the first tab. Values are entered as if typed (numbers, dates and formulas starting with = are interpreted) and new rows are inserted, so existing data "
        "is not overwritten. At most 500 rows of 200 cells per call. It does not edit existing cells (use google_sheets.values.update), delete rows or share the sheet."
    ),
    examples=[{"name": "default", "input": {"spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms", "range": "Q3",
                                            "values": [["Initech", 450, "2026-07-15"]]}, "output": {
        "spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms", "updated_range": "Q3!A4:C4",
        "updated_rows": 1, "updated_columns": 3, "updated_cells": 3}}],
)
async def values_append(ctx: Context, args: ValuesAppendIn) -> WriteOut:
    a1 = args.range.strip() if args.range else _quote_tab(await _first_tab(ctx, args.spreadsheet_id))
    data = await _json(ctx, "POST", _values_url(args.spreadsheet_id, a1, ":append"),
                       params={"valueInputOption": VALUE_INPUT, "insertDataOption": "INSERT_ROWS"},
                       body={"majorDimension": "ROWS", "values": args.values})
    return _write_out(args.spreadsheet_id, data.get("updates") or {})


# --- google_sheets.values.update -------------------------------------------------------------------

class ValuesUpdateIn(_SheetIn):
    range: str = Field(
        min_length=1,
        description=("A1 range whose cells are overwritten, always including the tab name, for example 'Sales!B2:D3' or \"'Q3 2026'!A1\". "
                     "The values fill the range starting at its top-left cell"))
    values: list[list[Cell]] = Field(
        min_length=1, max_length=MAX_WRITE_ROWS,
        description=("New content as a list of rows and each row a list of cell values (text, numbers, true/false). A null leaves that cell unchanged and an empty "
                     "string clears it. Up to 500 rows of 200 cells. Text starting with = is entered as a formula"))

    @field_validator("values")
    @classmethod
    def _limit_cells(cls, v: list[list[Cell]]) -> list[list[Cell]]:
        return _check_rows(v)


@function(
    id="google_sheets.values.update", version=1, verb=Verb.update, exits_outside=False, reversible=False, upstream_api="v4", scopes=[SCOPE_SHEETS],
    description=(
        "Overwrites the cells of an A1 range of a Google Sheets spreadsheet with new values and returns the range written, with the number of rows, columns and "
        "cells changed. Use it when the user asks to change, correct, fill in or clear specific cells, for example 'set B2 to 500' or 'replace the totals in "
        "D2:D10'. It needs the spreadsheet id or full URL, the range with its tab name and the values; the previous content of those cells is lost and cannot be "
        "restored by this function, so confirm the range with the user first. Values are entered as if typed (numbers, dates and formulas starting with = are "
        "interpreted). At most 500 rows of 200 cells. It does not add rows after the data (use google_sheets.values.append), insert or delete rows, or change formatting."
    ),
    examples=[{"name": "default", "input": {"spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms", "range": "Q3!B2:B3",
                                            "values": [[1300], [1000]]}, "output": {
        "spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms", "updated_range": "Q3!B2:B3",
        "updated_rows": 2, "updated_columns": 1, "updated_cells": 2}}],
)
async def values_update(ctx: Context, args: ValuesUpdateIn) -> WriteOut:
    a1 = args.range.strip()
    data = await _json(ctx, "PUT", _values_url(args.spreadsheet_id, a1), params={"valueInputOption": VALUE_INPUT},
                       body={"range": a1, "majorDimension": "ROWS", "values": args.values})
    return _write_out(args.spreadsheet_id, data)


# --- google_sheets.spreadsheets.create -------------------------------------------------------------

class SpreadsheetCreateIn(BaseModel):
    title: str = Field(min_length=1, max_length=255, description="Title of the new spreadsheet file, for example 'Budget 2027'")
    sheet_titles: Optional[list[str]] = Field(
        default=None, max_length=50,
        description="Titles of the tabs to create, in order, for example ['Income', 'Expenses']; each must be unique. When omitted Google creates one tab named Sheet1")

    @field_validator("sheet_titles")
    @classmethod
    def _unique_titles(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v is None:
            return v
        clean = [t.strip() for t in v]
        if any(not t for t in clean) or len({t.lower() for t in clean}) != len(clean):
            raise ValueError("sheet_titles must be non-empty and unique")
        return clean


class SpreadsheetCreateOut(BaseModel):
    spreadsheet_id: str = Field(description="Id of the new spreadsheet; use it with the other Google Sheets functions")
    title: str = Field(description="Title of the new spreadsheet")
    url: Optional[str] = Field(default=None, description="URL that opens the new spreadsheet in Google Sheets")
    sheets: list[_SheetTab] = Field(default_factory=list, description="Tabs the new spreadsheet was created with")


@function(
    id="google_sheets.spreadsheets.create", version=1, verb=Verb.create, exits_outside=False, reversible=True, upstream_api="v4", scopes=[SCOPE_SHEETS],
    description=(
        "Creates a new, empty Google Sheets spreadsheet in the root of the user's Google Drive and returns its id, title, link and tabs. Use it when the user asks "
        "to start a new spreadsheet, tracker or table from scratch, for example 'create a sheet called Budget 2027 with tabs Income and Expenses'. The title is "
        "required and sheet_titles optionally names the tabs (up to 50, unique); without it Google creates one tab called Sheet1. The sheet is private to the "
        "account. Afterwards fill it with google_sheets.values.append or google_sheets.values.update. It does not copy an existing spreadsheet, choose a Drive "
        "folder, share the file or delete it; the user can remove it from Drive."
    ),
    examples=[{"name": "default", "input": {"title": "Budget 2027", "sheet_titles": ["Income", "Expenses"]}, "output": {
        "spreadsheet_id": "1NewSpreadsheetIdAbCdEfGhIjKlMnOpQrStUv", "title": "Budget 2027",
        "url": "https://docs.google.com/spreadsheets/d/1NewSpreadsheetIdAbCdEfGhIjKlMnOpQrStUv/edit",
        "sheets": [{"sheet_id": 0, "title": "Income", "index": 0, "row_count": 1000, "column_count": 26, "hidden": False},
                   {"sheet_id": 1234567, "title": "Expenses", "index": 1, "row_count": 1000, "column_count": 26, "hidden": False}]}}],
)
async def spreadsheets_create(ctx: Context, args: SpreadsheetCreateIn) -> SpreadsheetCreateOut:
    body: dict[str, Any] = {"properties": {"title": args.title}}
    if args.sheet_titles:
        body["sheets"] = [{"properties": {"title": t}} for t in args.sheet_titles]
    data = await _json(ctx, "POST", SHEETS_URL, body=body)
    if not data.get("spreadsheetId"):
        raise FunctionError(ErrorCode.upstream_changed, "Google no devolvio el id de la hoja creada.")
    return SpreadsheetCreateOut(spreadsheet_id=str(data["spreadsheetId"]), title=str((data.get("properties") or {}).get("title") or args.title),
                                url=data.get("spreadsheetUrl"), sheets=[_tab(s) for s in data.get("sheets") or []])


# --- google_sheets.sheets.add ----------------------------------------------------------------------

class SheetAddIn(_SheetIn):
    title: str = Field(min_length=1, max_length=100, description="Title of the new tab; it must not already exist in the spreadsheet, for example 'Q4 2026'")
    rows: Optional[int] = Field(default=None, ge=1, le=10000, description="Number of rows of the new tab (1 to 10000); Google uses 1000 when omitted")
    columns: Optional[int] = Field(default=None, ge=1, le=702, description="Number of columns of the new tab (1 to 702, up to column ZZ); Google uses 26 when omitted")


class SheetAddOut(BaseModel):
    spreadsheet_id: str = Field(description="Id of the spreadsheet that received the tab")
    sheet: _SheetTab = Field(description="The tab that was created, with its numeric id, title, position and grid size")


@function(
    id="google_sheets.sheets.add", version=1, verb=Verb.update, exits_outside=False, reversible=True, upstream_api="v4", scopes=[SCOPE_SHEETS],
    description=(
        "Adds a new empty tab (sheet) at the end of an existing Google Sheets spreadsheet and returns its numeric id, title, position and grid size. Use it when "
        "the user asks to create a new tab, page or sheet inside a spreadsheet, for example 'add a tab called Q4 2026'. It needs the spreadsheet id or full URL and "
        "the title, which must be unique inside the spreadsheet (Google rejects a duplicate with an invalid input error); rows and columns optionally set the size. "
        "Existing data is not touched. It does not create a new spreadsheet file (use google_sheets.spreadsheets.create), and it cannot rename, copy, hide or delete tabs."
    ),
    examples=[{"name": "default", "input": {"spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms", "title": "Q4 2026"}, "output": {
        "spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
        "sheet": {"sheet_id": 987654321, "title": "Q4 2026", "index": 1, "row_count": 1000, "column_count": 26, "hidden": False}}}],
)
async def sheets_add(ctx: Context, args: SheetAddIn) -> SheetAddOut:
    props: dict[str, Any] = {"title": args.title.strip()}
    grid = {k: v for k, v in (("rowCount", args.rows), ("columnCount", args.columns)) if v is not None}
    if grid:
        props["gridProperties"] = grid
    data = await _json(ctx, "POST", _sheet_url(args.spreadsheet_id, ":batchUpdate"),
                       body={"requests": [{"addSheet": {"properties": props}}], "includeSpreadsheetInResponse": False})
    added = ((data.get("replies") or [{}])[0].get("addSheet")) or {}
    if not added.get("properties"):
        raise FunctionError(ErrorCode.upstream_changed, "Google no devolvio la pestana creada.")
    return SheetAddOut(spreadsheet_id=args.spreadsheet_id, sheet=_tab(added))


# --- google_sheets.values.clear --------------------------------------------------------------------

class ValuesClearIn(_SheetIn):
    range: str = Field(
        min_length=1,
        description=("A1 range whose cell values are erased, always required and written as <tab name>!<cells>, for example 'Sales!A2:D50' or \"'Q3 2026'!B:B\". "
                     "Both parts are mandatory: a bare tab name such as 'Sales' (it would erase the whole tab) or bare cells such as 'A2:D50' are rejected"))

    @field_validator("range")
    @classmethod
    def _tab_and_cells(cls, v: str) -> str:
        tab, bang, cells = v.strip().rpartition("!")
        if not bang or not tab.strip().strip("'").strip() or not cells.strip():
            raise ValueError("range must name both the tab and the cells, as <tab>!<cells>, for example 'Sales!A2:D50'; "
                             "a bare tab name ('Sales') or bare cells ('A2:D50') are not accepted so a whole tab is never erased by mistake")
        return v


class ValuesClearOut(BaseModel):
    spreadsheet_id: str = Field(description="Id of the spreadsheet that was cleared")
    cleared_range: str = Field(description="A1 range whose values were erased, including the tab name, as normalized by Google")


@function(
    id="google_sheets.values.clear", version=1, verb=Verb.update, exits_outside=False, reversible=False, upstream_api="v4", scopes=[SCOPE_SHEETS],
    description=(
        "Erases the values of an A1 range of a Google Sheets spreadsheet and returns the range that was cleared. Use it when the user asks to empty, wipe or reset "
        "some cells, a column or a block of rows, for example 'clear A2:D50 in the Sales tab'. It needs the spreadsheet id or full URL and the range, which is "
        "mandatory and must have both the tab name and the cells, written as <tab>!<cells> such as 'Sales!A2:D50' (a bare tab name, bare cells or a range "
        "without the tab are rejected); the previous values cannot be restored by this function, so confirm the exact range with the user first. "
        "Only values are erased: formatting, data validation, notes and the rows and columns themselves stay as they are. It does not delete rows or tabs, "
        "does not write new values (use google_sheets.values.update) and does not work without a full tab-and-cells range."
    ),
    examples=[{"name": "default", "input": {"spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms", "range": "Q3!A2:C50"}, "output": {
        "spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms", "cleared_range": "Q3!A2:C50"}}],
)
async def values_clear(ctx: Context, args: ValuesClearIn) -> ValuesClearOut:
    a1 = args.range.strip()
    if not a1:
        raise FunctionError(ErrorCode.invalid_input, "El rango a borrar no puede estar vacio.")
    data = await _json(ctx, "POST", _values_url(args.spreadsheet_id, a1, ":clear"), body={})
    if not data.get("clearedRange"):
        raise FunctionError(ErrorCode.upstream_changed, "Google no devolvio el rango borrado.")
    return ValuesClearOut(spreadsheet_id=args.spreadsheet_id, cleared_range=str(data["clearedRange"]))


# --- google_sheets.sheets.rename -------------------------------------------------------------------

class SheetRenameIn(_SheetIn):
    sheet_title: str = Field(min_length=1, max_length=100, description="Current title of the tab to rename, exactly as shown on the tab at the bottom of the spreadsheet, for example 'Sheet1'")
    new_title: str = Field(min_length=1, max_length=100, description="New title for the tab, for example 'Q4 2026'; it must not be used by another tab of the spreadsheet")


class SheetRenameOut(BaseModel):
    spreadsheet_id: str = Field(description="Id of the spreadsheet that contains the renamed tab")
    previous_title: str = Field(description="Title the tab had before the change")
    sheet: _SheetTab = Field(description="The tab after the change, with its numeric id, new title, position and grid size")


@function(
    id="google_sheets.sheets.rename", version=1, verb=Verb.update, exits_outside=False, reversible=True, upstream_api="v4", scopes=[SCOPE_SHEETS],
    description=(
        "Renames one tab (sheet) of an existing Google Sheets spreadsheet, found by its current title, and returns the previous title and the tab with its new title, "
        "numeric id and position. Use it when the user asks to rename a tab or page, for example 'rename Sheet1 to Sales'. It needs the spreadsheet id or full URL, "
        "the current tab title and the new title; the new title must not be taken by another tab (Google rejects a duplicate with an invalid input error) and an "
        "unknown current title fails with not found. Cell data is untouched and formulas that point to the tab follow the new name; it is reversible by renaming "
        "it back. It does not rename the spreadsheet file, and it cannot add (use google_sheets.sheets.add), copy, hide or delete tabs."
    ),
    examples=[{"name": "default", "input": {"spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms", "sheet_title": "Sheet1", "new_title": "Sales"}, "output": {
        "spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms", "previous_title": "Sheet1",
        "sheet": {"sheet_id": 0, "title": "Sales", "index": 0, "row_count": 1000, "column_count": 26, "hidden": False}}}],
)
async def sheets_rename(ctx: Context, args: SheetRenameIn) -> SheetRenameOut:
    current, new = args.sheet_title.strip(), args.new_title.strip()
    if not current or not new:
        raise FunctionError(ErrorCode.invalid_input, "El titulo actual y el nuevo no pueden estar vacios.")
    data = await _json(ctx, "GET", _sheet_url(args.spreadsheet_id), params={
        "fields": "sheets.properties(sheetId,title,index,hidden,gridProperties(rowCount,columnCount))"})
    tabs = [s.get("properties") or {} for s in data.get("sheets") or []]
    found = next((p for p in tabs if p.get("title") == current), None) or next((p for p in tabs if str(p.get("title", "")).casefold() == current.casefold()), None)
    if found is None:
        raise FunctionError(ErrorCode.not_found, f"No hay ninguna pestana llamada '{current}'. Pestanas de la hoja: " + ", ".join(f"'{p.get('title')}'" for p in tabs) + ".")
    if found.get("sheetId") is None:
        raise FunctionError(ErrorCode.upstream_changed, "Google no devolvio el id de la pestana.")
    if found["title"] == new:
        raise FunctionError(ErrorCode.invalid_input, f"La pestana ya se llama '{new}'.")
    await _json(ctx, "POST", _sheet_url(args.spreadsheet_id, ":batchUpdate"), body={
        "requests": [{"updateSheetProperties": {"properties": {"sheetId": found["sheetId"], "title": new}, "fields": "title"}}],
        "includeSpreadsheetInResponse": False})
    return SheetRenameOut(spreadsheet_id=args.spreadsheet_id, previous_title=str(found["title"]), sheet=_tab({"properties": {**found, "title": new}}))


# --- google_sheets.values.find ---------------------------------------------------------------------

MAX_FIND_ROWS = 5000      # filas de datos que se revisan cuando no se indica rango (el encabezado va aparte)
_CELL_RE = re.compile(r"\$?([A-Za-z]{1,3})?\$?(\d+)?")


def _col_number(letters: str) -> int:
    """Letras de columna a numero (A=1, Z=26, AA=27)."""
    n = 0
    for ch in letters.upper():
        n = n * 26 + (ord(ch) - 64)
    return n


def _range_start(a1: str) -> tuple[int, int]:
    """(fila, columna) de la primera celda del rango que devolvio Google ('Q3!B5:D9' -> (5, 2)); sin dato, (1, 1)."""
    m = _CELL_RE.fullmatch(a1.rsplit("!", 1)[-1].split(":")[0])
    return (int(m.group(2)) if m and m.group(2) else 1, _col_number(m.group(1)) if m and m.group(1) else 1)


class ValuesFindIn(_SheetIn):
    text: str = Field(min_length=1, max_length=500, description="Text to look for inside the cells; the match is a case-insensitive 'contains', for example 'acme' also finds 'Acme Corp'")
    range: Optional[str] = Field(
        default=None,
        description=("A1 range to search, for example 'Sales!A1:F500' or just a tab name 'Sales'; its first row is the header and is not searched. Tab names with "
                     f"spaces go in single quotes. When omitted, the first {MAX_FIND_ROWS} rows of the first tab are searched"))
    column: Optional[str] = Field(
        default=None,
        description=("Only look in this column, given as its header text in the first row (for example 'Client') or its letter in the sheet (for example 'B'); "
                     "when omitted every cell of the row is checked"))
    max_results: int = Field(default=20, ge=1, le=100, description="Maximum number of matching rows to return, from 1 to 100 (default 20)")


class FoundRow(BaseModel):
    row_number: int = Field(description="Row number in the sheet (1-based, as shown at the left of the grid), usable to build a range for google_sheets.values.update")
    values: list[str] = Field(description="Full row as formatted text; trailing empty cells are omitted so rows can have different lengths")


class ValuesFindOut(BaseModel):
    spreadsheet_id: str = Field(description="Id of the spreadsheet that was searched")
    range: str = Field(description="A1 range that was actually read, including the tab name, as normalized by Google")
    header: list[str] = Field(default_factory=list, description="First row of the range as text, usually the column titles; it is not searched")
    matches: list[FoundRow] = Field(default_factory=list, description="Rows that contain the text, in sheet order, each with its row number and values")
    match_count: int = Field(description="Number of rows in matches (at most max_results)")
    scanned_rows: int = Field(description="Number of rows after the header that were checked")
    truncated: bool = Field(description="True when more rows matched than max_results and the rest were left out")


def _find_column(column: str, header: list[str], first_col: int, width: int = 0) -> int:
    """Posicion (desde 0) de la columna dentro de cada fila: primero por texto del encabezado, luego por letra de la hoja.
    `width` es el ancho del encabezado o de la fila mas ancha: una letra que cae mas alla de ese ancho no es una columna del rango leido
    (p. ej. 'Tel' con encabezado Name/Phone se leeria como la columna TEL y daria 0 resultados sin avisar)."""
    wanted = column.strip()
    for i, h in enumerate(header):
        if h.strip().casefold() == wanted.casefold():
            return i
    if re.fullmatch(r"[A-Za-z]{1,3}", wanted) and _col_number(wanted) >= first_col and _col_number(wanted) - first_col < max(width, len(header)):
        return _col_number(wanted) - first_col
    names = ", ".join(f"'{h}'" for h in header) or "(sin encabezado)"
    raise FunctionError(ErrorCode.invalid_input, f"No se encontro la columna '{wanted}' (ni como encabezado ni como letra dentro del rango leido). Encabezados: {names}.")


@function(
    id="google_sheets.values.find", version=1, verb=Verb.read, upstream_api="v4", scopes=[SCOPE_SHEETS],
    description=(
        "Finds the rows of a Google Sheets range that contain a text, matching case-insensitively anywhere inside a cell, either in one column (given by its header "
        "text or its letter) or in any cell of the row, and returns each matching row with its sheet row number plus the header. Use it when the user asks to look "
        "up a record, for example 'which row has Acme?' or 'find the invoices from Luis', and then, if needed, change that row with google_sheets.values.update. "
        "It needs the spreadsheet id or full URL and the text; the range defaults to the first 5000 rows of the first tab and its first row is treated as the "
        "header and not searched. It returns at most max_results rows (1 to 100, default 20) and flags truncated when more matched. Read-only: it matches plain "
        "text only, not regular expressions or numeric conditions, and it changes nothing."
    ),
    examples=[{"name": "default", "input": {"spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms", "text": "acme", "range": "Q3!A1:C50", "column": "Client"}, "output": {
        "spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms", "range": "Q3!A1:C50", "header": ["Client", "Amount", "Date"],
        "matches": [{"row_number": 2, "values": ["Acme", "$1,200.00", "2026-07-03"]}], "match_count": 1, "scanned_rows": 49, "truncated": False}}],
)
async def values_find(ctx: Context, args: ValuesFindIn) -> ValuesFindOut:
    needle = args.text.strip().casefold()
    if not needle:
        raise FunctionError(ErrorCode.invalid_input, "El texto a buscar no puede estar vacio.")
    a1, raw = await _read_grid(ctx, args.spreadsheet_id, args.range, MAX_FIND_ROWS + 1)
    header, body = (raw[0] if raw else []), raw[1:]
    first_row, first_col = _range_start(a1)
    width = max((len(r) for r in raw), default=0)
    col = _find_column(args.column, header, first_col, width) if args.column and args.column.strip() else None
    hits: list[FoundRow] = []
    total = 0
    for i, row in enumerate(body):
        cells = row[col:col + 1] if col is not None else row
        if any(needle in c.casefold() for c in cells):
            total += 1
            if len(hits) < args.max_results:
                hits.append(FoundRow(row_number=first_row + 1 + i, values=row))
    return ValuesFindOut(spreadsheet_id=args.spreadsheet_id, range=a1, header=header, matches=hits, match_count=len(hits),
                         scanned_rows=len(body), truncated=total > len(hits))
