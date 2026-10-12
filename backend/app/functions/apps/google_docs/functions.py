"""Funciones de Google Docs (Docs API v1) y la identidad de la cuenta (OpenID userinfo).

Verificado contra la referencia oficial de Docs API v1 (developers.google.com/docs/api/reference/rest, 2026-10-11):
- documents.get: GET /v1/documents/{id}; `fields` recorta la respuesta. El cuerpo es body.content[], una lista de elementos
  estructurales: `paragraph` (elements[].textRun.content, el texto de cada parrafo ya trae su "\\n" final; hay otros elementos sin texto
  como pageBreak, inlineObjectElement o horizontalRule), `table` (tableRows[].tableCells[].content[], cada celda es otra lista de
  elementos estructurales), `tableOfContents` (indice generado, repite los titulos) y `sectionBreak`. Sin `includeTabsContent` el
  cuerpo es el de la primera pestana. Un salto de linea suave dentro de un parrafo llega como U+000B.
- documents.create: POST /v1/documents con `title`; devuelve el Document (documentId, title). Se crea en la raiz del Drive del usuario
  y vacio: el texto inicial se agrega con una segunda llamada.
- documents.batchUpdate: POST /v1/documents/{id}:batchUpdate con `requests`.
  insertText con `endOfSegmentLocation: {}` inserta al final del cuerpo, ANTES del salto de linea final del ultimo parrafo: por eso
  un texto sin "\\n" inicial se pega al ultimo parrafo. replaceAllText lleva `containsText {text, matchCase}` y `replaceText`; la
  respuesta es replies[0].replaceAllText.occurrencesChanged, que se OMITE cuando no hubo coincidencias.
- Buscar documentos por nombre y renombrarlos es Drive API y el login legacy de "docs" solo concede `documents`: esas funciones viven
  en la app google_drive (files.search con file_type "document", files.rename) y aqui NO existen.
- Identidad: GET https://openidconnect.googleapis.com/v1/userinfo (scopes openid/email/profile) devuelve sub, name, email.
- replaceAllText actua sobre TODO el documento (encabezados, pies, notas al pie y todas las pestanas), no solo el cuerpo que devuelve documents.get.
- Errores: 403 (falta de scope, documento no compartido o limite de ritmo) lo separa connections._code_for_403; 404 -> not_found;
  400 (id mal formado, texto no valido) -> invalid_input; 429 -> rate_limited; 5xx -> upstream_down.
No hay funcion para borrar documentos. Las descripciones y los Field(description=...) estan en INGLES y completos a proposito: el
agente los usa para buscar la funcion y para llenar sus argumentos (ver doc/funciones/CONTRATO.md, "Descripciones").
"""
import re
from typing import Any, Optional
from urllib.parse import quote

from pydantic import BaseModel, Field, field_validator

from app.functions.apps.google_docs.app_spec import APP  # noqa: F401  (registra la app antes que las funciones)
from app.functions.context import Context
from app.functions.errors import FunctionError
from app.functions.registry import function
from app.functions.spec import ErrorCode, Verb

DOCS_URL = "https://docs.googleapis.com/v1/documents"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
SCOPE_DOCS = "https://www.googleapis.com/auth/documents"
SCOPES_IDENTITY = ["openid", "email"]

MAX_TEXT_CHARS = 30000     # caracteres de texto que devuelve documents.get (mas de eso se corta y se marca truncated)
MAX_WRITE_CHARS = 100000   # caracteres que se aceptan por escritura
MAX_FIND_CHARS = 2000      # largo del texto a buscar en un reemplazo

_URL_ID_RE = re.compile(r"/document/(?:u/\d+/)?d/([A-Za-z0-9_-]+)")
_BARE_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def extract_document_id(raw: str) -> str:
    """Acepta el id solo o la URL completa del documento (docs.google.com/document/d/<id>/edit) y devuelve el id."""
    text = str(raw).strip()
    match = _URL_ID_RE.search(text)
    if match:
        return match.group(1)
    if _BARE_ID_RE.match(text):
        return text
    raise ValueError("document_id must be the document id or its full Google Docs URL (https://docs.google.com/document/d/<id>/edit)")


class _DocIn(BaseModel):
    document_id: str = Field(
        min_length=1,
        description=("Id of the Google Doc, or its full URL (the id is extracted from it): the long string between /d/ and /edit in "
                     "https://docs.google.com/document/d/<id>/edit. To find the id of a document by its name use google_drive.files.search with file_type "
                     "\"document\" (needs the Google Drive app connected); a document created with google_docs.documents.create returns its id"))

    @field_validator("document_id", mode="before")
    @classmethod
    def _to_id(cls, v: Any) -> str:
        return extract_document_id(v)


def _doc_url(document_id: str) -> str:
    return f"https://docs.google.com/document/d/{document_id}/edit"


def _doc_path(document_id: str, suffix: str = "") -> str:
    return f"{DOCS_URL}/{quote(document_id, safe='')}{suffix}"


async def _json(ctx: Context, method: str, url: str, *, params: Optional[dict] = None, body: Any = None) -> dict:
    resp = await ctx.conn.request(method, url, params=params or None, json=body)
    try:
        data = resp.json()
    except ValueError:
        raise FunctionError(ErrorCode.upstream_changed, "Google respondio algo que no es JSON.") from None
    return data if isinstance(data, dict) else {}


async def _insert_at_end(ctx: Context, document_id: str, text: str) -> dict:
    return await _json(ctx, "POST", _doc_path(document_id, ":batchUpdate"),
                       body={"requests": [{"insertText": {"endOfSegmentLocation": {}, "text": text}}]})


# --- aplanado del cuerpo ---------------------------------------------------------------------------

def _paragraph_text(paragraph: dict) -> str:
    text = "".join(str((el.get("textRun") or {}).get("content") or "") for el in paragraph.get("elements") or [] if isinstance(el, dict))
    return text.replace("\u000b", "\n")


def _flatten(content: list) -> str:
    """Texto plano de una lista de elementos estructurales: parrafos tal cual; tablas con celdas separadas por tabulador y filas por salto de linea.
    El indice generado (tableOfContents) se omite porque repite los titulos."""
    out: list[str] = []
    for element in content or []:
        if not isinstance(element, dict):
            continue
        if isinstance(element.get("paragraph"), dict):
            out.append(_paragraph_text(element["paragraph"]))
        elif isinstance(element.get("table"), dict):
            for row in element["table"].get("tableRows") or []:
                cells = [_flatten(cell.get("content") or []).rstrip("\n").replace("\n", " ") for cell in row.get("tableCells") or []]
                out.append("\t".join(cells) + "\n")
    return "".join(out)


# --- google_docs.account.get (whoami) --------------------------------------------------------------

class AccountGetIn(BaseModel):
    pass


class AccountGetOut(BaseModel):
    account_id: str = Field(description="Email address of the connected Google account; the same value stored when the account was connected")
    email: str = Field(description="Email address of the connected Google account")
    name: Optional[str] = Field(default=None, description="Full display name of the Google account owner, when the profile has one")
    google_user_id: Optional[str] = Field(default=None, description="Stable numeric id (the OpenID sub claim) of the Google account")


@function(
    id="google_docs.account.get", version=1, verb=Verb.read, upstream_api="v1", scopes=SCOPES_IDENTITY,
    description=(
        "Identifies the Google account that is connected to Google Docs: it returns the account id (the email address), the email, the display name and "
        "the stable Google user id. Use it to answer 'which Google account do I have connected for documents?', to confirm that the connection still "
        "works, or to tell several connected accounts apart. It takes no parameters. Read-only: it does not list, open or change any document."
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


# --- google_docs.documents.get ---------------------------------------------------------------------

class DocumentGetOut(BaseModel):
    document_id: str = Field(description="Id of the document")
    title: str = Field(description="Title of the document, as shown at the top of Google Docs and in Drive")
    text: str = Field(description="Plain text of the document body: paragraphs separated by line breaks and table cells separated by tabs, without formatting, images or comments; cut at 30000 characters")
    total_characters: int = Field(description="Number of characters of the full plain text, including any part that was cut")
    truncated: bool = Field(description="True when the document has more than 30000 characters and the end of the text was left out")
    url: str = Field(description="URL that opens the document in Google Docs")


@function(
    id="google_docs.documents.get", version=1, verb=Verb.read, upstream_api="v1", scopes=[SCOPE_DOCS],
    description=(
        "Reads one Google Docs document and returns its title, its link and the plain text of the body: paragraphs and the text of tables (cells separated "
        "by tabs), without formatting, images, comments or suggestions. Use it when the user asks to read, summarize, quote, proofread or find something "
        "inside a document, for example 'what does the project brief say?'. It needs the document id or its full URL. This app cannot search by name: to find a "
        "document by its name the agent uses google_drive.files.search with file_type \"document\", and to rename it google_drive.files.rename (both need the "
        "Google Drive app connected). The text is cut at 30000 characters and truncated is true when there was more (total_characters tells the full size). "
        "Read-only: it does not edit the document, does not return headers, footers, footnotes or other tabs, and cannot read files that are not Google Docs."
    ),
    examples=[{"name": "default", "input": {"document_id": "https://docs.google.com/document/d/1AbCdEfGhIjKlMnOpQrStUvWxYz012345/edit"}, "output": {
        "document_id": "1AbCdEfGhIjKlMnOpQrStUvWxYz012345", "title": "Project brief",
        "text": "Project brief\nGoal: launch the new site in Q4.\nOwner\tAna Perez\nDeadline\t2026-12-01",
        "total_characters": 82, "truncated": False,
        "url": "https://docs.google.com/document/d/1AbCdEfGhIjKlMnOpQrStUvWxYz012345/edit"}}],
)
async def documents_get(ctx: Context, args: _DocIn) -> DocumentGetOut:
    data = await _json(ctx, "GET", _doc_path(args.document_id), params={"fields": "documentId,title,body(content)"})
    if not data.get("documentId") or data.get("title") is None:
        raise FunctionError(ErrorCode.upstream_changed, "Google no devolvio el id ni el titulo del documento.")
    full = _flatten((data.get("body") or {}).get("content") or []).rstrip("\n")
    return DocumentGetOut(document_id=str(data["documentId"]), title=str(data["title"]), text=full[:MAX_TEXT_CHARS], total_characters=len(full),
                          truncated=len(full) > MAX_TEXT_CHARS, url=_doc_url(str(data["documentId"])))


# --- google_docs.documents.create ------------------------------------------------------------------

class DocumentCreateIn(BaseModel):
    title: str = Field(min_length=1, max_length=255, description="Title of the new document, for example 'Meeting notes 2026-10-12'")
    text: Optional[str] = Field(
        default=None, max_length=MAX_WRITE_CHARS,
        description="Optional initial plain text for the body; line breaks start new paragraphs. Up to 100000 characters. When omitted the document is created empty")


class DocumentCreateOut(BaseModel):
    document_id: str = Field(description="Id of the new document; use it with the other Google Docs functions")
    title: str = Field(description="Title of the new document")
    url: str = Field(description="URL that opens the new document in Google Docs")
    characters_added: int = Field(description="Number of characters of initial text written into the body; 0 when the document was created empty")


@function(
    id="google_docs.documents.create", version=1, verb=Verb.create, exits_outside=False, reversible=True, upstream_api="v1", scopes=[SCOPE_DOCS],
    description=(
        "Creates a new Google Docs document in the root of the user's Google Drive with the given title and, optionally, some initial plain text, and returns "
        "its id, title and link. Use it when the user asks to start a new document, note or draft, for example 'create a doc called Meeting notes with this "
        "agenda'. The title is required; the text is written as unformatted paragraphs. The document is private to the account. Afterwards add more content with "
        "google_docs.text.append. It does not copy an existing document, choose a Drive folder, apply formatting or templates, share the file or delete it; the "
        "user can remove it from Drive. Drive allows several documents with the same title, so it does not check for duplicates."
    ),
    examples=[{"name": "default", "input": {"title": "Meeting notes", "text": "Agenda\n1. Budget\n2. Hiring"}, "output": {
        "document_id": "1NewDocIdAbCdEfGhIjKlMnOpQrStUv", "title": "Meeting notes",
        "url": "https://docs.google.com/document/d/1NewDocIdAbCdEfGhIjKlMnOpQrStUv/edit", "characters_added": 26}}],
)
async def documents_create(ctx: Context, args: DocumentCreateIn) -> DocumentCreateOut:
    title = args.title.strip()
    if not title:
        raise FunctionError(ErrorCode.invalid_input, "El titulo del documento no puede estar vacio.")
    data = await _json(ctx, "POST", DOCS_URL, body={"title": title})
    if not data.get("documentId"):
        raise FunctionError(ErrorCode.upstream_changed, "Google no devolvio el id del documento creado.")
    doc_id = str(data["documentId"])
    added = 0
    if args.text:
        try:
            await _insert_at_end(ctx, doc_id, args.text)
        except FunctionError as exc:  # el documento ya existe vacio: el error debe decirlo para que no se cree otro
            raise FunctionError(exc.code, f"El documento se creo vacio ({_doc_url(doc_id)}) pero no se pudo escribir el texto: {exc.message}") from None
        added = len(args.text)
    return DocumentCreateOut(document_id=doc_id, title=str(data.get("title") or title), url=_doc_url(doc_id), characters_added=added)


# --- google_docs.text.append -----------------------------------------------------------------------

class TextAppendIn(_DocIn):
    text: str = Field(min_length=1, max_length=MAX_WRITE_CHARS, description="Plain text to add at the end of the document; line breaks inside it start new paragraphs. Up to 100000 characters")
    new_paragraph: bool = Field(
        default=True,
        description="True (default) starts the text on a new line after the current last paragraph; false continues the last paragraph directly after its final character")


class TextAppendOut(BaseModel):
    document_id: str = Field(description="Id of the document that was edited")
    characters_added: int = Field(description="Number of characters of text that were added, not counting the line break that starts a new paragraph")
    url: str = Field(description="URL that opens the document in Google Docs")


@function(
    id="google_docs.text.append", version=1, verb=Verb.update, exits_outside=False, reversible=True, upstream_api="v1", scopes=[SCOPE_DOCS],
    description=(
        "Adds plain text at the end of an existing Google Docs document, on a new line by default, and returns how many characters were added and the link. "
        "Use it when the user asks to add a note, a paragraph, a log entry or the next section to a document, for example 'add these action items to the "
        "meeting notes'. It needs the document id or full URL and the text; existing content is never changed or removed, and the text takes the formatting of "
        "the last paragraph. At most 100000 characters per call. It does not insert in the middle or at the beginning of the document (nor format text, add images or "
        "tables), does not replace text (use google_docs.text.replace) and does not create documents (use google_docs.documents.create)."
    ),
    examples=[{"name": "default", "input": {"document_id": "1AbCdEfGhIjKlMnOpQrStUvWxYz012345", "text": "Action item: send the budget to Luis."}, "output": {
        "document_id": "1AbCdEfGhIjKlMnOpQrStUvWxYz012345", "characters_added": 37,
        "url": "https://docs.google.com/document/d/1AbCdEfGhIjKlMnOpQrStUvWxYz012345/edit"}}],
)
async def text_append(ctx: Context, args: TextAppendIn) -> TextAppendOut:
    prefix = ""
    if args.new_paragraph:
        # un documento vacio solo tiene el parrafo final (endIndex 2): ahi no hay que abrir un parrafo nuevo
        info = await _json(ctx, "GET", _doc_path(args.document_id), params={"fields": "body(content(endIndex))"})
        end = max([int(e.get("endIndex") or 0) for e in (info.get("body") or {}).get("content") or [] if isinstance(e, dict)] or [0])
        if end > 2:
            prefix = "\n"
    await _insert_at_end(ctx, args.document_id, prefix + args.text)
    return TextAppendOut(document_id=args.document_id, characters_added=len(args.text), url=_doc_url(args.document_id))


# --- google_docs.text.replace ----------------------------------------------------------------------

class TextReplaceIn(_DocIn):
    find: str = Field(min_length=1, max_length=MAX_FIND_CHARS, description="Exact text to look for in the whole document, for example '2025' or '{{client_name}}'")
    replacement: str = Field(max_length=MAX_WRITE_CHARS, description="Text that takes the place of every match; an empty string deletes the matches")
    match_case: bool = Field(default=True, description="True (default) matches upper and lower case exactly; false ignores the case of the letters")


class TextReplaceOut(BaseModel):
    document_id: str = Field(description="Id of the document that was edited")
    occurrences_changed: int = Field(description="Number of places where the text was replaced; 0 means the text was not found and nothing changed")
    url: str = Field(description="URL that opens the document in Google Docs")


@function(
    id="google_docs.text.replace", version=1, verb=Verb.update, exits_outside=False, reversible=False, upstream_api="v1", scopes=[SCOPE_DOCS],
    description=(
        "Replaces every occurrence of a text with another text throughout a Google Docs document (including the text inside tables) and returns how many "
        "occurrences were changed. It replaces in the whole document, including headers, footers, footnotes and every tab, not only the body text that "
        "google_docs.documents.get returns, so it can change text the user did not see in a read. Use it when the user asks to change a name, a date, a figure or a placeholder everywhere in a document, for example 'replace "
        "2025 with 2026' or 'fill in {{client_name}} with Acme'; an empty replacement deletes the text. It needs the document id or full URL, the exact text to find "
        "and the new text; matching is case sensitive unless match_case is false. All matches are changed at once and this function cannot undo it (the "
        "document version history in Google Docs can), so confirm the change with the user first. It does not change only one occurrence, use patterns or wildcards, "
        "or touch formatting."
    ),
    examples=[{"name": "default", "input": {"document_id": "1AbCdEfGhIjKlMnOpQrStUvWxYz012345", "find": "2025", "replacement": "2026"}, "output": {
        "document_id": "1AbCdEfGhIjKlMnOpQrStUvWxYz012345", "occurrences_changed": 3,
        "url": "https://docs.google.com/document/d/1AbCdEfGhIjKlMnOpQrStUvWxYz012345/edit"}}],
)
async def text_replace(ctx: Context, args: TextReplaceIn) -> TextReplaceOut:
    data = await _json(ctx, "POST", _doc_path(args.document_id, ":batchUpdate"), body={"requests": [{"replaceAllText": {
        "containsText": {"text": args.find, "matchCase": args.match_case}, "replaceText": args.replacement}}]})
    replies = data.get("replies")
    if not isinstance(replies, list) or not replies:
        raise FunctionError(ErrorCode.upstream_changed, "Google no devolvio el resultado del reemplazo.")
    changed = ((replies[0] or {}).get("replaceAllText") or {}).get("occurrencesChanged")  # se omite cuando no hubo coincidencias
    return TextReplaceOut(document_id=args.document_id, occurrences_changed=int(changed or 0), url=_doc_url(args.document_id))
