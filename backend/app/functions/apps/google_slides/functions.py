"""Funciones de Google Slides (Slides API v1 y Drive API v3): lecturas y escrituras.

Verificado en los Discovery Documents oficiales (slides v1 y drive v3, 2026-10-08). El catalogo ATENCION/tareas/google_slides.md
(generado por una IA) acierta en las rutas, con estas precisiones:
- google_slides.presentations.list (whoami): Drive files.list no acepta presentations.readonly; acepta drive.metadata.readonly, que
  se pide en app_spec.py. La identidad sale de Drive about.get (permissionId = account_id estable, correo y nombre).
- google_slides.slides.get_page: pages.get acepta `commentsViewMode` (INCLUDED devuelve 403 si el usuario no puede ver comentarios) y
  devuelve `comments` (CommentThread) y `commentAnchors` dentro de la pagina. La pagina NO trae `name` ni `shapes` sueltas: trae
  `pageElements` (shape, table, image, video, line, sheetsChart, wordArt, elementGroup...), que aqui se resumen.
- google_slides.slides.get_thumbnail: el unico mimeType admitido es PNG y la URL (`contentUrl`) vive 30 minutos y lleva la identidad
  de la cuenta: quien la tenga ve la imagen. Tamanos: SMALL, MEDIUM, LARGE y WIDTH2000_PX.
- google_slides.comments.get_page_comments: los comentarios los devuelve la misma pages.get con COMMENTS_VIEW_MODE_INCLUDED; cada
  hilo trae headPost y replies con `content`, `author.displayName` y `createTime` (no `id`/`anchor` de Drive); el hilo se ata a la
  pagina por commentId/anchorId.
- presentations.get: GET /v1/presentations/{id} acepta presentations.readonly y devuelve `slides[].pageElements`; el texto se aplana con los
  mismos helpers que get_page. `fields` recorta la respuesta (sin masters ni layouts).
- presentations.create: POST /v1/presentations con `title`; se crea en la raiz del Drive y trae una diapositiva en blanco (`slides[0].objectId`).
  Pide el scope `presentations` (tambien acepta drive y drive.file, que no se piden).
- slides.add / text.replace / slides.duplicate: POST /v1/presentations/{id}:batchUpdate con las solicitudes `createSlide`, `replaceAllText`
  y `duplicateObject`; cada respuesta viene en `replies[i]` en el mismo orden. `replaceAllText` OMITE `occurrencesChanged` cuando es 0.
  `duplicateObject` pone la copia justo despues de la original y devuelve su `objectId`. Un scope insuficiente responde 403.
Las descripciones y los Field(description=...) estan en INGLES y completos a proposito: el agente los usa para buscar la funcion
y para llenar sus argumentos (ver doc/funciones/CONTRATO.md, "Descripciones").
"""
import re
import uuid
from typing import Any, Literal, Optional
from urllib.parse import quote

from pydantic import BaseModel, Field, field_validator, model_validator

from app.functions.apps.google_slides.app_spec import APP  # noqa: F401  (registra la app antes que las funciones)
from app.functions.context import Context
from app.functions.errors import FunctionError
from app.functions.registry import function
from app.functions.spec import ErrorCode, Verb

SLIDES_URL = "https://slides.googleapis.com/v1"
DRIVE_URL = "https://www.googleapis.com/drive/v3"
SLIDES_MIME = "application/vnd.google-apps.presentation"
SCOPE_SLIDES_READ = "https://www.googleapis.com/auth/presentations.readonly"
SCOPE_DRIVE_META = "https://www.googleapis.com/auth/drive.metadata.readonly"
SCOPE_SLIDES_WRITE = "https://www.googleapis.com/auth/presentations"
COMMENTS_INCLUDED = "COMMENTS_VIEW_MODE_INCLUDED"
MAX_TOTAL_CHARS = 20000   # texto total que devuelve presentations.get entre todas las diapositivas

_URL_ID_RE = re.compile(r"/presentation/(?:u/\d+/)?d/([A-Za-z0-9_-]+)")
_BARE_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


async def _json(ctx: Context, url: str, params: Optional[dict] = None) -> dict:
    resp = await ctx.conn.request("GET", url, params=params or None)
    try:
        body = resp.json()
    except ValueError:
        raise FunctionError(ErrorCode.upstream_changed, "Google respondio algo que no es JSON.") from None
    return body if isinstance(body, dict) else {}


def _page_url(presentation_id: str, page_object_id: str, suffix: str = "") -> str:
    return f"{SLIDES_URL}/presentations/{quote(presentation_id, safe='')}/pages/{quote(page_object_id, safe='')}{suffix}"


# --- google_slides.presentations.list (whoami) ----------------------------------------------------

class PresentationsListIn(BaseModel):
    page_size: int = Field(default=10, ge=1, le=100, description="Maximum number of presentations to return in this page, from 1 to 100 (default 10)")
    page_token: Optional[str] = Field(default=None, description="Token returned as next_page_token by a previous call to continue listing from there")


class PresentationItem(BaseModel):
    id: str = Field(description="Google Drive file id of the presentation, also used as presentationId in the Slides API")
    name: Optional[str] = Field(default=None, description="Name (title) of the presentation file in Google Drive")
    web_view_link: Optional[str] = Field(default=None, description="URL that opens the presentation in the Google Slides editor")
    modified_time: Optional[str] = Field(default=None, description="UTC date and time when the presentation was last modified")


class PresentationsList(BaseModel):
    account_id: str = Field(description="Stable Google Drive permission id of the connected account; the same value stored when the account was connected")
    email: Optional[str] = Field(default=None, description="Email address of the connected Google account")
    display_name: Optional[str] = Field(default=None, description="Display name of the connected Google account")
    presentations: list[PresentationItem] = Field(default_factory=list, description="Presentations of the account, most recently modified first")
    next_page_token: Optional[str] = Field(default=None, description="Token to pass as page_token to get the next page; empty when this is the last page")


@function(
    id="google_slides.presentations.list", version=1, verb=Verb.read, upstream_api="v1", scopes=[SCOPE_DRIVE_META],
    description=(
        "Identifies the Google account connected to Google Slides and lists its presentations, most recently modified first: it returns the account id, "
        "the email, the display name and, for each presentation, its id, name, link to open it and last modified time. Use it to answer 'which Google "
        "account do I have connected?', to check that the connection still works, or to find a presentation id before reading it with the other "
        "Google Slides functions. page_size (1 to 100) and page_token paginate the list. Read-only: it does not open, create or change presentations "
        "and it does not search by name. If several Google accounts are connected, one of them must be chosen first."
    ),
    examples=[{"name": "default", "input": {"page_size": 10}, "output": {
        "account_id": "11223344556677889900", "email": "ana@empresa.test", "display_name": "Ana Perez",
        "presentations": [{"id": "1AbCdEfGhIjKlMnOpQrStUvWxYz", "name": "Q3 results",
                           "web_view_link": "https://docs.google.com/presentation/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/edit",
                           "modified_time": "2026-10-01T12:00:00.000Z"}],
        "next_page_token": None}}],
)
async def presentations_list(ctx: Context, args: PresentationsListIn) -> PresentationsList:
    about = await _json(ctx, f"{DRIVE_URL}/about", {"fields": "user(permissionId,emailAddress,displayName)"})
    user = about.get("user") or {}
    if not user.get("permissionId"):
        raise FunctionError(ErrorCode.upstream_changed, "Google no devolvio el id del usuario.")
    params: dict[str, Any] = {
        "q": f"mimeType='{SLIDES_MIME}' and trashed=false", "orderBy": "modifiedTime desc", "pageSize": args.page_size,
        "fields": "nextPageToken,files(id,name,webViewLink,modifiedTime)",
    }
    if args.page_token:
        params["pageToken"] = args.page_token
    files = await _json(ctx, f"{DRIVE_URL}/files", params)
    return PresentationsList(
        account_id=str(user["permissionId"]), email=user.get("emailAddress"), display_name=user.get("displayName"),
        presentations=[PresentationItem(id=str(f["id"]), name=f.get("name"), web_view_link=f.get("webViewLink"), modified_time=f.get("modifiedTime"))
                       for f in files.get("files") or []],
        next_page_token=files.get("nextPageToken"),
    )


# --- comentarios (hilos de Slides) -----------------------------------------------------------------

class CommentPost(BaseModel):
    post_id: Optional[str] = Field(default=None, description="Unique id of the post inside its comment thread")
    content: Optional[str] = Field(default=None, description="Plain text of the post")
    author: Optional[str] = Field(default=None, description="Display name of the person who wrote the post")
    create_time: Optional[str] = Field(default=None, description="UTC date and time when the post was created")
    deleted: bool = Field(default=False, description="True when the post was deleted and its content is no longer available")


class CommentThread(BaseModel):
    comment_id: str = Field(description="Unique id of the comment thread")
    anchor_id: Optional[str] = Field(default=None, description="Id of the comment anchor that ties the thread to a place in the presentation")
    status: Optional[str] = Field(default=None, description="Whether the thread is open or resolved")
    quote: Optional[str] = Field(default=None, description="Text of the page element that was quoted when the comment was created")
    head_post: Optional[CommentPost] = Field(default=None, description="First post of the thread, the original comment")
    replies: list[CommentPost] = Field(default_factory=list, description="Replies to the original comment, oldest first")


def _post(raw: dict) -> CommentPost:
    return CommentPost(post_id=raw.get("postId"), content=raw.get("content"), author=(raw.get("author") or {}).get("displayName"),
                       create_time=raw.get("createTime"), deleted=bool(raw.get("deleted")))


def _thread(raw: dict) -> CommentThread:
    return CommentThread(comment_id=str(raw.get("commentId") or ""), anchor_id=raw.get("anchorId"), status=raw.get("status"),
                         quote=raw.get("plainTextQuote"), head_post=_post(raw["headPost"]) if raw.get("headPost") else None,
                         replies=[_post(r) for r in raw.get("replies") or []])


# --- google_slides.slides.get_page ----------------------------------------------------------------

class PageIn(BaseModel):
    presentation_id: str = Field(min_length=1, description="Id of the presentation, the long string in its Google Slides URL; find it with google_slides.presentations.list")
    page_object_id: str = Field(min_length=1, description="Object id of the slide (page) to read, for example 'p' or 'g1234abcd_0_0'")


class GetPageIn(PageIn):
    include_comments: bool = Field(default=False, description="When true, also returns the comment threads of the page; Google answers 403 if the account cannot view comments")


class PageElement(BaseModel):
    object_id: str = Field(description="Object id of the element inside the page")
    kind: str = Field(description="Kind of element: shape, table, image, video, line, sheetsChart, wordArt, elementGroup, speakerSpotlight or unknown")
    title: Optional[str] = Field(default=None, description="Alt text title of the element, when one is set")
    text: Optional[str] = Field(default=None, description="Text inside the element (all text runs of a shape, or all cells of a table), when it has any")


class PageContent(BaseModel):
    object_id: str = Field(description="Object id of the page")
    page_type: Optional[str] = Field(default=None, description="Kind of page: SLIDE, MASTER, LAYOUT, NOTES or NOTES_MASTER")
    revision_id: Optional[str] = Field(default=None, description="Revision id of the presentation when the page was read")
    elements: list[PageElement] = Field(default_factory=list, description="Summary of the elements of the page (shapes, tables, images, videos...) with their text")
    text: str = Field(default="", description="All the text of the page joined with line breaks, in element order")
    comments: list[CommentThread] = Field(default_factory=list, description="Comment threads of the page; empty unless include_comments was true")


_KINDS = ("shape", "table", "image", "video", "line", "sheetsChart", "wordArt", "elementGroup", "speakerSpotlight")


# pages.get de la API real NO manda `pageType` (verificado 2026-10-09): el tipo se deduce de la propiedad que trae cada pagina.
_PAGE_PROPERTIES = (("slideProperties", "SLIDE"), ("layoutProperties", "LAYOUT"), ("masterProperties", "MASTER"), ("notesProperties", "NOTES"))


def _page_type(page: dict) -> Optional[str]:
    if page.get("pageType"):
        return str(page["pageType"])
    return next((kind for key, kind in _PAGE_PROPERTIES if page.get(key) is not None), None)


def _runs(text: dict) -> str:
    return "".join((e.get("textRun") or {}).get("content", "") for e in text.get("textElements") or [])


def _element_text(el: dict) -> str:
    if el.get("shape"):
        return _runs(el["shape"].get("text") or {})
    if el.get("table"):
        cells = [_runs(c.get("text") or {}) for row in el["table"].get("tableRows") or [] for c in row.get("tableCells") or []]
        return "\n".join(c.strip() for c in cells if c.strip())
    if el.get("elementGroup"):
        return "\n".join(t for t in (_element_text(c) for c in el["elementGroup"].get("children") or []) if t.strip())
    return ""


def _elements(raw: list[dict]) -> list[PageElement]:
    out = []
    for el in raw:
        text = _element_text(el).strip()
        out.append(PageElement(object_id=str(el.get("objectId", "")), kind=next((k for k in _KINDS if el.get(k) is not None), "unknown"),
                               title=el.get("title"), text=text or None))
    return out


@function(
    id="google_slides.slides.get_page", version=1, verb=Verb.read, upstream_api="v1", scopes=[SCOPE_SLIDES_READ],
    description=(
        "Reads one slide (page) of a Google Slides presentation: its object id, page type, revision id, a summary of every element on it (shapes, tables, "
        "images, videos, lines, charts) with the element kind, alt-text title and the text it contains, and all the page text joined together. Use it when "
        "the user asks what a specific slide says or contains, once the presentation id and the slide object id are known. Set include_comments to true to "
        "also get the comment threads of that slide. Read-only: it does not return the image pixels (use google_slides.slides.get_thumbnail for a picture), "
        "it does not edit the slide and it needs the exact object id of the slide."
    ),
    examples=[{"name": "default", "input": {"presentation_id": "1AbCdEfGhIjKlMnOpQrStUvWxYz", "page_object_id": "g1234abcd_0_0"}, "output": {
        "object_id": "g1234abcd_0_0", "page_type": "SLIDE", "revision_id": "ALm37BX",
        "elements": [{"object_id": "g1234abcd_0_1", "kind": "shape", "title": None, "text": "Q3 results"}],
        "text": "Q3 results", "comments": []}}],
)
async def slides_get_page(ctx: Context, args: GetPageIn) -> PageContent:
    params = {"commentsViewMode": COMMENTS_INCLUDED} if args.include_comments else None
    page = await _json(ctx, _page_url(args.presentation_id, args.page_object_id), params)
    if not page.get("objectId"):
        raise FunctionError(ErrorCode.upstream_changed, "Google no devolvio el objectId de la pagina.")
    elements = _elements(page.get("pageElements") or [])
    return PageContent(object_id=str(page["objectId"]), page_type=_page_type(page), revision_id=page.get("revisionId"), elements=elements,
                       text="\n".join(e.text for e in elements if e.text), comments=[_thread(t) for t in page.get("comments") or []] if args.include_comments else [])


# --- google_slides.slides.get_thumbnail -----------------------------------------------------------

class ThumbnailIn(PageIn):
    thumbnail_size: Literal["SMALL", "MEDIUM", "LARGE", "WIDTH2000_PX"] = Field(
        default="MEDIUM", description="Size of the image: SMALL (200 px wide), MEDIUM (800 px), LARGE (1600 px) or WIDTH2000_PX (2000 px wide)")


class Thumbnail(BaseModel):
    content_url: str = Field(description="URL of the PNG image of the slide; it expires after about 30 minutes and works for anyone who has it")
    width: Optional[int] = Field(default=None, description="Width of the image in pixels")
    height: Optional[int] = Field(default=None, description="Height of the image in pixels")
    mime_type: str = Field(default="PNG", description="Image format of the thumbnail; Google Slides only produces PNG")


@function(
    id="google_slides.slides.get_thumbnail", version=1, verb=Verb.read, upstream_api="v1", scopes=[SCOPE_SLIDES_READ],
    description=(
        "Generates a thumbnail image of one slide of a Google Slides presentation and returns the URL of the PNG together with its width and height in "
        "pixels. Use it when the user wants to see how a slide looks, to show a preview, or to attach a picture of the slide. It requires the presentation "
        "id and the slide object id; thumbnail_size picks SMALL, MEDIUM (default), LARGE or WIDTH2000_PX. Read-only. The URL expires after about 30 minutes "
        "and anyone holding it can view the image, so share it with care. It does not return the slide text or elements (use google_slides.slides.get_page) "
        "and Google rate-limits thumbnails more strictly than normal reads."
    ),
    examples=[{"name": "default", "input": {"presentation_id": "1AbCdEfGhIjKlMnOpQrStUvWxYz", "page_object_id": "g1234abcd_0_0", "thumbnail_size": "MEDIUM"}, "output": {
        "content_url": "https://lh3.googleusercontent.com/abc123", "width": 800, "height": 450, "mime_type": "PNG"}}],
)
async def slides_get_thumbnail(ctx: Context, args: ThumbnailIn) -> Thumbnail:
    body = await _json(ctx, _page_url(args.presentation_id, args.page_object_id, "/thumbnail"),
                       {"thumbnailProperties.thumbnailSize": args.thumbnail_size, "thumbnailProperties.mimeType": "PNG"})
    if not body.get("contentUrl"):
        raise FunctionError(ErrorCode.upstream_changed, "Google no devolvio la URL de la miniatura.")
    return Thumbnail(content_url=body["contentUrl"], width=body.get("width"), height=body.get("height"))


# --- google_slides.comments.get_page_comments -----------------------------------------------------

class PageComments(BaseModel):
    page_object_id: str = Field(description="Object id of the page the comments belong to")
    comments: list[CommentThread] = Field(description="Comment threads anchored to the page, each with its original post and replies")
    count: int = Field(description="Number of comment threads returned")


@function(
    id="google_slides.comments.get_page_comments", version=1, verb=Verb.read, upstream_api="v1", scopes=[SCOPE_SLIDES_READ],
    description=(
        "Returns the comment threads of one slide of a Google Slides presentation: for each thread its id, whether it is open or resolved, the quoted text "
        "it refers to, the original comment and every reply with the author's display name and time. Use it when the user asks what feedback or review "
        "comments a specific slide has. It requires the presentation id and the slide object id. Read-only: it does not add, resolve or delete comments and it "
        "does not return the slide content (use google_slides.slides.get_page). Google answers a permission error when the connected account is not allowed "
        "to view comments on the presentation."
    ),
    examples=[{"name": "default", "input": {"presentation_id": "1AbCdEfGhIjKlMnOpQrStUvWxYz", "page_object_id": "g1234abcd_0_0"}, "output": {
        "page_object_id": "g1234abcd_0_0", "count": 1, "comments": [{
            "comment_id": "AAAAx1", "anchor_id": "kix.abc", "status": "OPEN", "quote": "Q3 results",
            "head_post": {"post_id": "p1", "content": "Add the chart", "author": "Ana Perez", "create_time": "2026-10-01T12:00:00Z", "deleted": False},
            "replies": []}]}}],
)
async def comments_get_page_comments(ctx: Context, args: PageIn) -> PageComments:
    page = await _json(ctx, _page_url(args.presentation_id, args.page_object_id), {"commentsViewMode": COMMENTS_INCLUDED})
    threads = [_thread(t) for t in page.get("comments") or []]
    return PageComments(page_object_id=str(page.get("objectId") or args.page_object_id), comments=threads, count=len(threads))


# --- escrituras y lectura de contenido: utilidades comunes ------------------------------------------

def extract_presentation_id(raw: str) -> str:
    """Acepta el id solo o la URL completa (docs.google.com/presentation/d/<id>/edit) y devuelve el id."""
    text = str(raw).strip()
    match = _URL_ID_RE.search(text)
    if match:
        return match.group(1)
    if _BARE_ID_RE.match(text):
        return text
    raise ValueError("presentation_id must be the presentation id or its full Google Slides URL (https://docs.google.com/presentation/d/<id>/edit)")


class _PresentationIn(BaseModel):
    presentation_id: str = Field(
        min_length=1,
        description=("Id of the presentation, or its full Google Slides URL (the id is extracted from it): the long string between /d/ and /edit in "
                     "https://docs.google.com/presentation/d/<id>/edit. Find it with google_slides.presentations.list when the user does not give it"))

    @field_validator("presentation_id", mode="before")
    @classmethod
    def _to_id(cls, v: Any) -> str:
        return extract_presentation_id(v)


def _presentation_url(presentation_id: str) -> str:
    return f"https://docs.google.com/presentation/d/{presentation_id}/edit"


def _new_id(prefix: str) -> str:
    """Object id nuevo para createSlide y sus placeholders (la API pide 5 a 50 caracteres, letras, numeros, _ - :)."""
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


async def _send(ctx: Context, method: str, url: str, *, params: Optional[dict] = None, body: Any = None) -> dict:
    resp = await ctx.conn.request(method, url, params=params or None, json=body)
    try:
        data = resp.json()
    except ValueError:
        raise FunctionError(ErrorCode.upstream_changed, "Google respondio algo que no es JSON.") from None
    return data if isinstance(data, dict) else {}


async def _batch_update(ctx: Context, presentation_id: str, requests: list[dict]) -> list[dict]:
    """Manda las solicitudes en UN batchUpdate (la API las aplica todas o ninguna) y devuelve replies en el mismo orden."""
    url = f"{SLIDES_URL}/presentations/{quote(presentation_id, safe='')}:batchUpdate"
    data = await _send(ctx, "POST", url, body={"requests": requests})
    replies = data.get("replies")
    if not isinstance(replies, list) or len(replies) != len(requests):
        raise FunctionError(ErrorCode.upstream_changed, "Google no devolvio una respuesta por cada solicitud.")
    return [r if isinstance(r, dict) else {} for r in replies]


# --- google_slides.presentations.get --------------------------------------------------------------

class SlideText(BaseModel):
    object_id: str = Field(description="Object id of the slide; use it with the other Google Slides functions that take a slide")
    index: int = Field(description="Zero-based position of the slide in the presentation")
    text: str = Field(description="Plain text of the slide: text boxes, tables and groups joined with line breaks, in element order; empty when the slide has no text or the text limit was reached")


class PresentationGetOut(BaseModel):
    presentation_id: str = Field(description="Id of the presentation")
    title: str = Field(description="Title of the presentation file")
    url: str = Field(description="URL that opens the presentation in Google Slides")
    revision_id: Optional[str] = Field(default=None, description="Revision id of the presentation when it was read")
    slide_count: int = Field(description="Number of slides of the presentation")
    slides: list[SlideText] = Field(default_factory=list, description="Every slide in order with its object id, position and plain text")
    truncated: bool = Field(description="True when the total text passed 20000 characters and the text of the last slides was cut or left empty")


@function(
    id="google_slides.presentations.get", version=1, verb=Verb.read, upstream_api="v1", scopes=[SCOPE_SLIDES_READ],
    description=(
        "Reads a whole Google Slides presentation and returns its title, link, number of slides and, for every slide in order, its object id, position and "
        "plain text (the text of shapes and text boxes, tables and groups joined with line breaks). Use it when the user asks what a presentation says, "
        "to summarize or review a deck, to find which slide mentions something, or to get the slide object ids before duplicating a slide or reading one "
        "with google_slides.slides.get_page. It needs the presentation id or its full Google Slides URL. The total text is capped at 20000 characters: "
        "when it is longer, truncated is true and the last slides come back cut or empty. Read-only: it does not return images, speaker notes, comments or "
        "formatting (use google_slides.slides.get_thumbnail for a picture of a slide) and it changes nothing."
    ),
    examples=[{"name": "default", "input": {"presentation_id": "https://docs.google.com/presentation/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/edit"}, "output": {
        "presentation_id": "1AbCdEfGhIjKlMnOpQrStUvWxYz", "title": "Q3 results",
        "url": "https://docs.google.com/presentation/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/edit", "revision_id": "ALm37BX", "slide_count": 2,
        "slides": [{"object_id": "p", "index": 0, "text": "Q3 results\nSales grew 12%"}, {"object_id": "g1234abcd_0_0", "index": 1, "text": "Next steps"}],
        "truncated": False}}],
)
async def presentations_get(ctx: Context, args: _PresentationIn) -> PresentationGetOut:
    url = f"{SLIDES_URL}/presentations/{quote(args.presentation_id, safe='')}"
    data = await _json(ctx, url, {"fields": "presentationId,title,revisionId,slides(objectId,pageElements)"})
    if not data.get("presentationId") or data.get("title") is None:
        raise FunctionError(ErrorCode.upstream_changed, "Google no devolvio el id ni el titulo de la presentacion.")
    budget, truncated, slides = MAX_TOTAL_CHARS, False, []
    for i, raw in enumerate(data.get("slides") or []):
        text = "\n".join(t for t in (_element_text(el).strip() for el in raw.get("pageElements") or []) if t)
        if len(text) > budget:  # tope del texto total: lo que no cabe se corta y las diapositivas siguientes quedan sin texto
            text, truncated = text[:budget], True
        budget -= len(text)
        slides.append(SlideText(object_id=str(raw.get("objectId", "")), index=i, text=text))
    return PresentationGetOut(presentation_id=str(data["presentationId"]), title=str(data["title"]), url=_presentation_url(str(data["presentationId"])),
                              revision_id=data.get("revisionId"), slide_count=len(slides), slides=slides, truncated=truncated)


# --- google_slides.presentations.create -----------------------------------------------------------

class PresentationCreateIn(BaseModel):
    title: str = Field(min_length=1, max_length=255, description="Title of the new presentation file, for example 'Q4 plan'")


class PresentationCreateOut(BaseModel):
    presentation_id: str = Field(description="Id of the new presentation; use it with the other Google Slides functions")
    title: str = Field(description="Title of the new presentation")
    url: str = Field(description="URL that opens the new presentation in Google Slides")
    slide_ids: list[str] = Field(default_factory=list, description="Object ids of the slides the presentation was created with (Google adds one blank slide)")


@function(
    id="google_slides.presentations.create", version=1, verb=Verb.create, exits_outside=False, reversible=True, upstream_api="v1", scopes=[SCOPE_SLIDES_WRITE],
    description=(
        "Creates a new Google Slides presentation in the root of the user's Google Drive and returns its id, title, link and the object ids of its slides "
        "(Google creates it with one blank slide). Use it when the user asks to start a new deck or presentation from scratch, for example 'create a "
        "presentation called Q4 plan'. The title is required. The file is private to the account. Afterwards add slides with google_slides.slides.add and "
        "fill them there. It does not copy an existing presentation, choose a Drive folder, share the file or delete it; the user can remove it from Drive."
    ),
    examples=[{"name": "default", "input": {"title": "Q4 plan"}, "output": {
        "presentation_id": "1NewPresentationIdAbCdEfGhIjKlMnOpQrSt", "title": "Q4 plan",
        "url": "https://docs.google.com/presentation/d/1NewPresentationIdAbCdEfGhIjKlMnOpQrSt/edit", "slide_ids": ["p"]}}],
)
async def presentations_create(ctx: Context, args: PresentationCreateIn) -> PresentationCreateOut:
    data = await _send(ctx, "POST", f"{SLIDES_URL}/presentations", body={"title": args.title.strip()})
    if not data.get("presentationId"):
        raise FunctionError(ErrorCode.upstream_changed, "Google no devolvio el id de la presentacion creada.")
    pid = str(data["presentationId"])
    return PresentationCreateOut(presentation_id=pid, title=str(data.get("title") or args.title.strip()), url=_presentation_url(pid),
                                 slide_ids=[str(s["objectId"]) for s in data.get("slides") or [] if s.get("objectId")])


# --- google_slides.slides.add ---------------------------------------------------------------------

class SlideAddIn(_PresentationIn):
    layout: Literal["TITLE_AND_BODY", "TITLE_ONLY", "BLANK"] = Field(
        default="TITLE_AND_BODY",
        description="Predefined layout of the new slide: TITLE_AND_BODY (a title and a body text box, default), TITLE_ONLY (just a title) or BLANK (no placeholders)")
    title: Optional[str] = Field(default=None, min_length=1, max_length=2000, description="Text of the title of the new slide, for example 'Next steps'; only for the layouts TITLE_AND_BODY and TITLE_ONLY")
    body: Optional[str] = Field(default=None, min_length=1, max_length=20000, description="Text of the body of the new slide, lines separated by line breaks; only for the layout TITLE_AND_BODY")
    index: Optional[int] = Field(default=None, ge=0, description="Zero-based position where the slide is inserted, 0 meaning the very first slide; when omitted the slide goes at the end of the presentation")

    @model_validator(mode="after")
    def _text_needs_its_placeholder(self) -> "SlideAddIn":
        if self.title and self.layout == "BLANK":
            raise ValueError("title needs the layout TITLE_AND_BODY or TITLE_ONLY; BLANK has no title")
        if self.body and self.layout != "TITLE_AND_BODY":
            raise ValueError("body needs the layout TITLE_AND_BODY")
        return self


class SlideAddOut(BaseModel):
    presentation_id: str = Field(description="Id of the presentation that received the slide")
    slide_object_id: str = Field(description="Object id of the new slide; use it with google_slides.slides.get_page, get_thumbnail or slides.duplicate")
    layout: str = Field(description="Predefined layout the slide was created with")
    index: Optional[int] = Field(default=None, description="Zero-based position the slide was inserted at; null when it was added at the end")


@function(
    id="google_slides.slides.add", version=1, verb=Verb.update, exits_outside=False, reversible=True, upstream_api="v1", scopes=[SCOPE_SLIDES_WRITE],
    description=(
        "Adds a new slide to an existing Google Slides presentation, at the end or at a given position, with a predefined layout (TITLE_AND_BODY, TITLE_ONLY "
        "or BLANK) and optionally the title and body text, and returns the object id of the new slide. Use it when the user asks to add a slide or a page to "
        "a deck, for example 'add a slide called Next steps with these three bullet points'. It needs the presentation id or full URL; layout defaults to "
        "TITLE_AND_BODY, title only works with TITLE_AND_BODY or TITLE_ONLY, body only with TITLE_AND_BODY, and index (zero-based) is optional. Existing slides "
        "are not touched. Google answers an invalid input error when the deck's theme does not have that layout. It does not create a presentation (use "
        "google_slides.presentations.create), add images, charts or tables, or edit text of existing slides (use google_slides.text.replace)."
    ),
    examples=[{"name": "default", "input": {"presentation_id": "1AbCdEfGhIjKlMnOpQrStUvWxYz", "layout": "TITLE_AND_BODY", "title": "Next steps", "body": "Hire two engineers\nLaunch in November"}, "output": {
        "presentation_id": "1AbCdEfGhIjKlMnOpQrStUvWxYz", "slide_object_id": "slide_0123456789abcdef", "layout": "TITLE_AND_BODY", "index": None}}],
)
async def slides_add(ctx: Context, args: SlideAddIn) -> SlideAddOut:
    # Un solo batchUpdate basta: createSlide acepta placeholderIdMappings, que fija el objectId de cada placeholder, y asi los insertText
    # de la misma solicitud ya conocen su destino (no hace falta leer la diapositiva para descubrir los ids). Solo se mapean los que llevan texto.
    slide_id = _new_id("slide")
    texts = [(kind, text) for kind, text in (("TITLE", args.title), ("BODY", args.body)) if text]
    mapped = [(kind, _new_id(kind.lower()), text) for kind, text in texts]
    create: dict[str, Any] = {"objectId": slide_id, "slideLayoutReference": {"predefinedLayout": args.layout}}
    if args.index is not None:
        create["insertionIndex"] = args.index
    if mapped:
        create["placeholderIdMappings"] = [{"layoutPlaceholder": {"type": kind, "index": 0}, "objectId": oid} for kind, oid, _ in mapped]
    requests: list[dict] = [{"createSlide": create}]
    requests += [{"insertText": {"objectId": oid, "insertionIndex": 0, "text": text}} for _, oid, text in mapped]
    replies = await _batch_update(ctx, args.presentation_id, requests)
    created = (replies[0].get("createSlide") or {}).get("objectId")
    if not created:
        raise FunctionError(ErrorCode.upstream_changed, "Google no devolvio el id de la diapositiva creada.")
    return SlideAddOut(presentation_id=args.presentation_id, slide_object_id=str(created), layout=args.layout, index=args.index)


# --- google_slides.text.replace -------------------------------------------------------------------

class TextReplaceIn(_PresentationIn):
    find: str = Field(min_length=1, max_length=1000, description="Text to look for in every slide of the presentation, for example '2025'")
    replace_with: str = Field(max_length=10000, description="Text that takes the place of every match; an empty string deletes the matched text")
    match_case: bool = Field(default=True, description="When true (default) 'Q3' does not match 'q3'; set false to ignore upper and lower case")


class TextReplaceOut(BaseModel):
    presentation_id: str = Field(description="Id of the presentation that was changed")
    occurrences_changed: int = Field(description="Number of places where the text was replaced; 0 means the text was not found and nothing changed")


@function(
    id="google_slides.text.replace", version=1, verb=Verb.update, exits_outside=False, reversible=False, upstream_api="v1", scopes=[SCOPE_SLIDES_WRITE],
    description=(
        "Replaces every occurrence of a text with another text in a whole Google Slides presentation (shapes, text boxes and tables of all slides) and returns "
        "how many occurrences were changed. Use it when the user asks to change a word, name, date or figure everywhere in a deck, for example 'replace 2025 "
        "with 2026 in the presentation' or 'change Acme to Globex'. It needs the presentation id or full URL, the text to find and the replacement; matching is "
        "case sensitive unless match_case is false. The old text is overwritten and this function cannot restore it (the user can use the version history of "
        "the file), so confirm the change with the user first. A result of 0 means nothing matched. It replaces everywhere in the presentation, which may "
        "include speaker notes and layouts, and it cannot limit the change to one slide, change formatting or add slides (use google_slides.slides.add)."
    ),
    examples=[{"name": "default", "input": {"presentation_id": "1AbCdEfGhIjKlMnOpQrStUvWxYz", "find": "2025", "replace_with": "2026"}, "output": {
        "presentation_id": "1AbCdEfGhIjKlMnOpQrStUvWxYz", "occurrences_changed": 3}}],
)
async def text_replace(ctx: Context, args: TextReplaceIn) -> TextReplaceOut:
    replies = await _batch_update(ctx, args.presentation_id, [{"replaceAllText": {
        "containsText": {"text": args.find, "matchCase": args.match_case}, "replaceText": args.replace_with}}])
    # replaceAllText omite occurrencesChanged cuando no cambio nada
    return TextReplaceOut(presentation_id=args.presentation_id, occurrences_changed=int((replies[0].get("replaceAllText") or {}).get("occurrencesChanged") or 0))


# --- google_slides.slides.duplicate ---------------------------------------------------------------

class SlideDuplicateIn(_PresentationIn):
    slide_object_id: str = Field(min_length=1, description="Object id of the slide (page) to duplicate, for example 'p' or 'g1234abcd_0_0'; it must be a slide's object id, not that of an element inside a slide; get it from google_slides.presentations.get")


class SlideDuplicateOut(BaseModel):
    presentation_id: str = Field(description="Id of the presentation that received the copy")
    source_slide_object_id: str = Field(description="Object id of the slide that was duplicated")
    new_slide_object_id: str = Field(description="Object id of the new slide, which sits right after the original")


@function(
    id="google_slides.slides.duplicate", version=1, verb=Verb.create, exits_outside=False, reversible=True, upstream_api="v1", scopes=[SCOPE_SLIDES_WRITE],
    description=(
        "Duplicates one slide of a Google Slides presentation, with all its content, and returns the object id of the copy, which Google places right after "
        "the original. Use it when the user asks to copy, clone or repeat a slide, for example 'duplicate the pricing slide' or when a slide is needed as a "
        "template for a new one. It needs the presentation id or full URL and slide_object_id, which must be the object id of a slide (a page of the "
        "presentation, as google_slides.presentations.get lists them), not the id of a shape, text box or other element inside a slide. "
        "Afterwards the copy can be edited with google_slides.text.replace (that function changes the whole presentation, not only the copy). It does not "
        "move slides, copy a slide to another presentation or delete anything."
    ),
    examples=[{"name": "default", "input": {"presentation_id": "1AbCdEfGhIjKlMnOpQrStUvWxYz", "slide_object_id": "g1234abcd_0_0"}, "output": {
        "presentation_id": "1AbCdEfGhIjKlMnOpQrStUvWxYz", "source_slide_object_id": "g1234abcd_0_0", "new_slide_object_id": "g1234abcd_0_9"}}],
)
async def slides_duplicate(ctx: Context, args: SlideDuplicateIn) -> SlideDuplicateOut:
    replies = await _batch_update(ctx, args.presentation_id, [{"duplicateObject": {"objectId": args.slide_object_id}}])
    new_id = (replies[0].get("duplicateObject") or {}).get("objectId")
    if not new_id:
        raise FunctionError(ErrorCode.upstream_changed, "Google no devolvio el id de la diapositiva duplicada.")
    return SlideDuplicateOut(presentation_id=args.presentation_id, source_slide_object_id=args.slide_object_id, new_slide_object_id=str(new_id))
