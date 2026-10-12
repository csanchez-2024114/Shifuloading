"""Funciones de Gmail (Gmail API v1): perfil, buscar, leer, etiquetas, borradores, enviar y cambiar etiquetas.

Verificado en el Discovery Document oficial (gmail.googleapis.com/$discovery/rest?version=v1, 2026-10-10):
- users.getProfile        GET  /gmail/v1/users/me/profile            -> {emailAddress, messagesTotal, threadsTotal, historyId}
- users.messages.list     GET  /gmail/v1/users/me/messages           q, maxResults (def. 100, max 500), labelIds (repetido), pageToken,
                          includeSpamTrash (def. false) -> {messages:[{id,threadId}], nextPageToken, resultSizeEstimate}. Solo devuelve ids:
                          por eso la busqueda hace una llamada extra por mensaje.
- users.messages.get      GET  /gmail/v1/users/me/messages/{id}      format = minimal | full (def.) | raw | metadata; metadataHeaders (repetido,
                          solo con format=metadata). Message: id, threadId, labelIds, snippet, internalDate, sizeEstimate, payload (MessagePart:
                          mimeType, filename, headers[{name,value}], body{size,data,attachmentId}, parts[]). `data` es base64url.
- users.labels.list       GET  /gmail/v1/users/me/labels             -> {labels:[{id,name,type,...}]}; la lista solo trae id, name, type y visibilidad.
- users.drafts.create     POST /gmail/v1/users/me/drafts             body {message:{raw, threadId}} (raw = RFC 2822 en base64url) -> Draft{id, message}.
- users.messages.send     POST /gmail/v1/users/me/messages/send      body {raw, threadId} -> Message{id, threadId, labelIds}.
- users.messages.modify   POST /gmail/v1/users/me/messages/{id}/modify  body {addLabelIds, removeLabelIds} (hasta 100 cada uno) -> Message.
- users.labels.create      POST /gmail/v1/users/me/labels             body {name, labelListVisibility, messageListVisibility} -> Label{id, name, type}.
                          Un nombre repetido responde 409 («Label name exists or conflicts»). Scopes: gmail.modify entre otros.
- users.drafts.send        POST /gmail/v1/users/me/drafts/send        body {id} (el Draft con su id) -> Message{id, threadId, labelIds}. Scopes: gmail.compose o gmail.modify.
- users.drafts.list        GET  /gmail/v1/users/me/drafts             q, maxResults (def. 100, max 500), pageToken -> {drafts:[{id, message:{id, threadId}}], nextPageToken,
                          resultSizeEstimate}. Solo trae ids: asunto y destinatarios salen de messages.get (format=metadata) del mensaje del borrador.
- Scopes aceptados (Discovery): lectura -> gmail.readonly; drafts.create, messages.send y messages.modify aceptan gmail.modify (los dos que
  el login de Google ya pide, ver app_spec.py). Los ids de etiquetas del sistema son fijos: INBOX, UNREAD, STARRED, IMPORTANT, SENT, DRAFT, SPAM, TRASH.
- Gmail responde 403 tanto por scope insuficiente como por limite de ritmo (rateLimitExceeded / userRateLimitExceeded); `_request` distingue el segundo.
- Salidas recortadas a proposito: nunca se devuelve el cuerpo crudo ni el HTML; el texto se corta a 2000 caracteres.
Las descripciones y los Field(description=...) estan en INGLES y completos a proposito: el agente los usa para buscar la funcion
y para llenar sus argumentos (ver doc/funciones/CONTRATO.md, "Descripciones").
"""
import asyncio
import base64
import html as html_lib
import re
from email.message import EmailMessage
from typing import Any, Optional
from urllib.parse import quote

from pydantic import BaseModel, Field, field_validator, model_validator

from app.functions.apps.gmail.app_spec import APP  # noqa: F401  (registra la app antes que las funciones)
from app.functions.context import Context
from app.functions.errors import FunctionError
from app.functions.registry import function
from app.functions.spec import ErrorCode, Verb

BASE_URL = "https://gmail.googleapis.com/gmail/v1/users/me"
SCOPE_READ = "https://www.googleapis.com/auth/gmail.readonly"
SCOPE_MODIFY = "https://www.googleapis.com/auth/gmail.modify"
BODY_LIMIT = 2000          # caracteres de cuerpo que se devuelven
MAX_PARALLEL_GETS = 8      # Gmail limita las peticiones concurrentes por usuario (10)
META_HEADERS = ["From", "To", "Subject", "Date"]
_RATE_RE = re.compile(r"rate[ _-]?limit", re.IGNORECASE)
_EMAIL_RE = re.compile(r"^[^@\s<>,;\"]+@[^@\s<>,;\"]+\.[^@\s<>,;\"]+$")


# --- acceso a la API --------------------------------------------------------------------------------

async def _request(ctx: Context, method: str, url: str, **kw: Any) -> dict:
    """Llama a Gmail y devuelve el JSON. Gmail usa 403 tambien para el limite de ritmo: aqui se separa de «falta un permiso»."""
    try:
        resp = await ctx.conn.request(method, url, **kw)
    except FunctionError as exc:
        if exc.code == ErrorCode.missing_scope and _RATE_RE.search(exc.message):
            raise FunctionError(ErrorCode.rate_limited, "Gmail limito el ritmo de peticiones; hay que reintentar en unos segundos.") from None
        raise
    try:
        body = resp.json()
    except ValueError:
        raise FunctionError(ErrorCode.upstream_changed, "Gmail respondio algo que no es JSON.") from None
    return body if isinstance(body, dict) else {}


def _msg_url(message_id: str, suffix: str = "") -> str:
    return f"{BASE_URL}/messages/{quote(message_id, safe='')}{suffix}"


def _header_map(part: dict) -> dict[str, str]:
    """Cabeceras de una parte con el nombre en minusculas (si se repite una, gana la primera)."""
    out: dict[str, str] = {}
    for h in part.get("headers") or []:
        out.setdefault(str(h.get("name", "")).lower(), str(h.get("value", "")))
    return out


# --- decodificacion del cuerpo ----------------------------------------------------------------------

def _b64url_decode(data: str, charset: Optional[str] = None) -> str:
    raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))  # Gmail manda base64url sin relleno
    try:
        return raw.decode(charset or "utf-8", errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def _charset(part: dict) -> Optional[str]:
    m = re.search(r"charset=\"?([\w.:-]+)", _header_map(part).get("content-type", ""), re.IGNORECASE)
    return m.group(1) if m else None


def _html_to_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|head)\b.*?</\1>", " ", html)
    html = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h[1-6])>", "\n", html)
    return html_lib.unescape(re.sub(r"<[^>]+>", " ", html))


def _tidy(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(re.sub(r"[ \t\xa0]+", " ", line).strip() for line in text.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _walk(part: dict):
    yield part
    for child in part.get("parts") or []:
        yield from _walk(child)


def _extract_body(payload: dict) -> tuple[str, str, bool]:
    """(texto, formato, recortado). Prefiere text/plain; si no hay, usa el text/html sin etiquetas."""
    plain: list[str] = []
    html: list[str] = []
    for part in _walk(payload):
        data = (part.get("body") or {}).get("data")
        if not data or part.get("filename"):
            continue
        mime = str(part.get("mimeType", "")).lower()
        if mime == "text/plain":
            plain.append(_b64url_decode(data, _charset(part)))
        elif mime == "text/html":
            html.append(_b64url_decode(data, _charset(part)))
    if plain:
        text, fmt = _tidy("\n\n".join(plain)), "plain"
    elif html:
        text, fmt = _tidy(_html_to_text("\n".join(html))), "html_stripped"
    else:
        return "", "none", False
    return text[:BODY_LIMIT], fmt, len(text) > BODY_LIMIT


# --- gmail.profile.get (whoami) ---------------------------------------------------------------------

class ProfileIn(BaseModel):
    """Sin parametros: siempre consulta la cuenta conectada."""


class Profile(BaseModel):
    account_id: str = Field(description="Email address of the connected Gmail account; it is the same value stored when the account was connected")
    email: str = Field(description="Email address of the connected Gmail account (same as account_id)")
    messages_total: Optional[int] = Field(default=None, description="Total number of messages in the mailbox, including archived, spam and trash")
    threads_total: Optional[int] = Field(default=None, description="Total number of conversation threads in the mailbox")


@function(
    id="gmail.profile.get", version=1, verb=Verb.read, upstream_api="v1", scopes=[SCOPE_READ],
    description=(
        "Identifies the Gmail account connected to Shifu and returns its email address together with the total number of messages and conversation threads in "
        "the mailbox. Use it to answer 'which Gmail account do I have connected?', to check that the connection still works, or to learn the address that "
        "outgoing mail will be sent from. It takes no parameters. Read-only: it does not list, search or open any message (use gmail.messages.search for "
        "that) and it does not change anything. If several Gmail accounts are connected, one of them must be chosen first."
    ),
    examples=[{"name": "default", "input": {}, "output": {
        "account_id": "ana@empresa.test", "email": "ana@empresa.test", "messages_total": 4821, "threads_total": 2310}}],
)
async def profile_get(ctx: Context, args: ProfileIn) -> Profile:
    body = await _request(ctx, "GET", f"{BASE_URL}/profile")
    email = body.get("emailAddress")
    if not email:
        raise FunctionError(ErrorCode.upstream_changed, "Gmail no devolvio el correo de la cuenta.")
    return Profile(account_id=str(email), email=str(email), messages_total=body.get("messagesTotal"), threads_total=body.get("threadsTotal"))


# --- gmail.messages.search --------------------------------------------------------------------------

class SearchIn(BaseModel):
    q: Optional[str] = Field(default=None, description=(
        "Gmail search query, the same syntax as the Gmail search box, for example 'from:ana@empresa.test', 'subject:invoice', 'newer_than:7d', 'is:unread', "
        "'has:attachment' or 'from:ana newer_than:2d is:unread'; leave empty to get the most recent messages"))
    max_results: int = Field(default=10, ge=1, le=50, description="Maximum number of messages to return, from 1 to 50 (default 10)")
    label_ids: Optional[list[str]] = Field(default=None, description=(
        "Only return messages that have ALL of these label ids, for example ['INBOX', 'UNREAD']; system label ids are INBOX, UNREAD, STARRED, "
        "IMPORTANT, SENT, DRAFT, SPAM and TRASH, and user label ids come from gmail.labels.list"))
    page_token: Optional[str] = Field(default=None, description="Token returned as next_page_token by a previous call to continue the same search from there")


class MessageRow(BaseModel):
    id: str = Field(description="Message id, to pass to gmail.messages.get or gmail.messages.modify_labels")
    thread_id: Optional[str] = Field(default=None, description="Id of the conversation thread the message belongs to")
    sender: Optional[str] = Field(default=None, description="From header: who sent the message, usually 'Name <address>'")
    to: Optional[str] = Field(default=None, description="To header: the recipients as written in the message")
    subject: Optional[str] = Field(default=None, description="Subject line of the message")
    date: Optional[str] = Field(default=None, description="Date header as written by the sender, for example 'Mon, 5 Oct 2026 09:30:00 -0500'")
    snippet: Optional[str] = Field(default=None, description="Short preview of the message text produced by Gmail")
    label_ids: list[str] = Field(default_factory=list, description="Ids of the labels on the message, for example INBOX, UNREAD, STARRED")
    unread: bool = Field(default=False, description="True when the message carries the UNREAD label")


class SearchOut(BaseModel):
    messages: list[MessageRow] = Field(description="Matching messages, newest first, each with sender, recipients, subject, date and snippet")
    count: int = Field(description="Number of messages returned in this page")
    result_size_estimate: Optional[int] = Field(default=None, description="Gmail's rough estimate of how many messages match in total, not exact")
    next_page_token: Optional[str] = Field(default=None, description="Token to pass as page_token to get the next page; empty when this is the last page")


def _row(raw: dict) -> MessageRow:
    h = _header_map(raw.get("payload") or {})
    labels = [str(x) for x in raw.get("labelIds") or []]
    return MessageRow(id=str(raw.get("id", "")), thread_id=raw.get("threadId"), sender=h.get("from"), to=h.get("to"), subject=h.get("subject"),
                      date=h.get("date"), snippet=raw.get("snippet"), label_ids=labels, unread="UNREAD" in labels)


@function(
    id="gmail.messages.search", version=1, verb=Verb.read, upstream_api="v1", scopes=[SCOPE_READ],
    description=(
        "Searches the connected Gmail mailbox with Gmail search syntax and returns, in a single call, one row per matching message: id, thread id, sender, "
        "recipients, subject, date, snippet, label ids and an unread flag, newest first. Use it when the user asks to find, list or check email, for example "
        "'do I have unread mail from Ana?' or 'show the invoices from last week'. q accepts Gmail operators such as from:, to:, subject:, newer_than:7d, "
        "older_than:1m, is:unread, is:starred, has:attachment and label:; max_results is 1 to 50 (default 10) and next_page_token pages through more. "
        "Spam and trash are excluded. Read-only: it returns only a preview, not the full body (use gmail.messages.get for that) and it changes nothing."
    ),
    examples=[{"name": "default", "input": {"q": "is:unread newer_than:2d", "max_results": 10}, "output": {
        "messages": [{"id": "18c3f2a1b9d4e5f6", "thread_id": "18c3f2a1b9d4e5f6", "sender": "Luis Gomez <luis@proveedor.test>",
                      "to": "ana@empresa.test", "subject": "Factura de octubre", "date": "Mon, 5 Oct 2026 09:30:00 -0500",
                      "snippet": "Hola Ana, adjunto la factura del mes...", "label_ids": ["INBOX", "UNREAD"], "unread": True}],
        "count": 1, "result_size_estimate": 1, "next_page_token": None}}],
)
async def messages_search(ctx: Context, args: SearchIn) -> SearchOut:
    params: dict[str, Any] = {"maxResults": args.max_results}
    if args.q and args.q.strip():
        params["q"] = args.q.strip()
    if args.label_ids:
        params["labelIds"] = args.label_ids
    if args.page_token:
        params["pageToken"] = args.page_token
    listing = await _request(ctx, "GET", f"{BASE_URL}/messages", params=params)  # primero la lista: si el token vencio, se refresca una sola vez
    ids = [str(m["id"]) for m in listing.get("messages") or [] if m.get("id")]
    gate = asyncio.Semaphore(MAX_PARALLEL_GETS)

    async def fetch(mid: str) -> dict:
        async with gate:
            return await _request(ctx, "GET", _msg_url(mid), params={"format": "metadata", "metadataHeaders": META_HEADERS})

    fetched = await asyncio.gather(*(fetch(i) for i in ids), return_exceptions=True)
    rows: list[MessageRow] = []
    for res in fetched:
        if isinstance(res, FunctionError) and res.code == ErrorCode.not_found:
            continue  # el mensaje se borro entre la lista y la lectura
        if isinstance(res, BaseException):
            raise res
        rows.append(_row(res))
    return SearchOut(messages=rows, count=len(rows), result_size_estimate=listing.get("resultSizeEstimate"), next_page_token=listing.get("nextPageToken"))


# --- gmail.messages.get -----------------------------------------------------------------------------

class GetIn(BaseModel):
    message_id: str = Field(min_length=1, description="Id of the message to read, as returned by gmail.messages.search in the id field")


class Attachment(BaseModel):
    filename: str = Field(description="File name of the attachment")
    mime_type: Optional[str] = Field(default=None, description="MIME type of the attachment, for example application/pdf")
    size: Optional[int] = Field(default=None, description="Size of the attachment in bytes")


class MessageOut(BaseModel):
    id: str = Field(description="Message id")
    thread_id: Optional[str] = Field(default=None, description="Id of the conversation thread; pass it as thread_id when replying with gmail.messages.send")
    sender: Optional[str] = Field(default=None, description="From header: who sent the message")
    to: Optional[str] = Field(default=None, description="To header: the recipients as written in the message")
    cc: Optional[str] = Field(default=None, description="Cc header, when the message has one")
    subject: Optional[str] = Field(default=None, description="Subject line of the message")
    date: Optional[str] = Field(default=None, description="Date header as written by the sender")
    message_id_header: Optional[str] = Field(default=None, description="RFC 2822 Message-ID header (like '<abc@mail.gmail.com>'); pass it as in_reply_to when replying with gmail.messages.send")
    snippet: Optional[str] = Field(default=None, description="Short preview of the message text produced by Gmail")
    label_ids: list[str] = Field(default_factory=list, description="Ids of the labels on the message, for example INBOX, UNREAD, STARRED")
    body: str = Field(default="", description="Plain-text body of the message, decoded and cut to about 2000 characters")
    body_format: str = Field(default="none", description="Where the body came from: plain (a text/plain part), html_stripped (HTML with tags removed because no plain part existed) or none")
    body_truncated: bool = Field(default=False, description="True when the body was longer than 2000 characters and was cut")
    attachments: list[Attachment] = Field(default_factory=list, description="Names, types and sizes of the attachments; their content is not downloaded")


@function(
    id="gmail.messages.get", version=1, verb=Verb.read, upstream_api="v1", scopes=[SCOPE_READ],
    description=(
        "Reads one Gmail message by id: sender, recipients, cc, subject, date, RFC Message-ID, thread id, label ids, snippet and the readable text body "
        "(the text/plain part when it exists, otherwise the HTML with its tags removed), cut to about 2000 characters, plus the name, type and size of any "
        "attachments. Use it after gmail.messages.search when the user wants to read a specific email, summarise it or reply to it; message_id_header and "
        "thread_id are what gmail.messages.send needs to reply in the same conversation. Read-only: it does not mark the message as read, does not return raw "
        "HTML or attachment content, and does not read a whole thread."
    ),
    examples=[{"name": "default", "input": {"message_id": "18c3f2a1b9d4e5f6"}, "output": {
        "id": "18c3f2a1b9d4e5f6", "thread_id": "18c3f2a1b9d4e5f6", "sender": "Luis Gomez <luis@proveedor.test>", "to": "ana@empresa.test", "cc": None,
        "subject": "Factura de octubre", "date": "Mon, 5 Oct 2026 09:30:00 -0500", "message_id_header": "<CAK123abc@mail.gmail.com>",
        "snippet": "Hola Ana, adjunto la factura del mes...", "label_ids": ["INBOX", "UNREAD"],
        "body": "Hola Ana,\n\nAdjunto la factura de octubre. Quedo atento.\n\nLuis", "body_format": "plain", "body_truncated": False,
        "attachments": [{"filename": "factura-octubre.pdf", "mime_type": "application/pdf", "size": 48213}]}}],
)
async def messages_get(ctx: Context, args: GetIn) -> MessageOut:
    raw = await _request(ctx, "GET", _msg_url(args.message_id), params={"format": "full"})
    if not raw.get("id"):
        raise FunctionError(ErrorCode.upstream_changed, "Gmail no devolvio el id del mensaje.")
    payload = raw.get("payload") or {}
    h = _header_map(payload)
    body, fmt, cut = _extract_body(payload)
    files = [Attachment(filename=str(p["filename"]), mime_type=p.get("mimeType"), size=(p.get("body") or {}).get("size"))
             for p in _walk(payload) if p.get("filename")]
    return MessageOut(
        id=str(raw["id"]), thread_id=raw.get("threadId"), sender=h.get("from"), to=h.get("to"), cc=h.get("cc"), subject=h.get("subject"),
        date=h.get("date"), message_id_header=h.get("message-id"), snippet=raw.get("snippet"), label_ids=[str(x) for x in raw.get("labelIds") or []],
        body=body, body_format=fmt, body_truncated=cut, attachments=files)


# --- gmail.labels.list ------------------------------------------------------------------------------

class LabelsIn(BaseModel):
    """Sin parametros: lista todas las etiquetas de la cuenta."""


class LabelItem(BaseModel):
    id: str = Field(description="Label id, to use in label_ids of gmail.messages.search or add_label_ids / remove_label_ids of gmail.messages.modify_labels")
    name: str = Field(description="Display name of the label as the user sees it in Gmail")
    type: Optional[str] = Field(default=None, description="'system' for built-in labels (INBOX, UNREAD, SENT...) or 'user' for labels the person created")


class LabelsOut(BaseModel):
    labels: list[LabelItem] = Field(description="All labels of the account, system labels and user labels")
    count: int = Field(description="Number of labels returned")


@function(
    id="gmail.labels.list", version=1, verb=Verb.read, upstream_api="v1", scopes=[SCOPE_READ],
    description=(
        "Lists every label of the connected Gmail account, both the built-in system labels (INBOX, UNREAD, STARRED, IMPORTANT, SENT, DRAFT, SPAM, TRASH...) "
        "and the labels the person created, each with its id, display name and type. Use it to find the id of a label by its name before filtering a search "
        "with label_ids or before adding or removing a label with gmail.messages.modify_labels, or when the user asks 'which labels do I have?'. "
        "It takes no parameters. Read-only: it does not return message counts per label, does not create, rename or delete labels, and does not list messages."
    ),
    examples=[{"name": "default", "input": {}, "output": {
        "labels": [{"id": "INBOX", "name": "INBOX", "type": "system"}, {"id": "UNREAD", "name": "UNREAD", "type": "system"},
                   {"id": "Label_17", "name": "Clientes", "type": "user"}], "count": 3}}],
)
async def labels_list(ctx: Context, args: LabelsIn) -> LabelsOut:
    body = await _request(ctx, "GET", f"{BASE_URL}/labels")
    labels = [LabelItem(id=str(x["id"]), name=str(x.get("name", x["id"])), type=x.get("type")) for x in body.get("labels") or [] if x.get("id")]
    return LabelsOut(labels=labels, count=len(labels))


# --- redaccion de correos (borrador y envio) --------------------------------------------------------

def _clean_addresses(values: Optional[list[str]]) -> Optional[list[str]]:
    if values is None:
        return None
    out = [v.strip() for v in values]
    for v in out:
        if not _EMAIL_RE.match(v):
            raise ValueError(f"'{v}' no es una direccion de correo valida (se espera algo como ana@empresa.com)")
    return out


class ComposeIn(BaseModel):
    to: list[str] = Field(min_length=1, max_length=50, description="Recipient email addresses, plain addresses such as 'ana@empresa.com' (at least one, at most 50)")
    subject: str = Field(min_length=1, max_length=500, description="Subject line of the email, on one line")
    body: str = Field(min_length=1, max_length=100000, description="Body of the email as plain text; line breaks are kept and no HTML is sent")
    cc: Optional[list[str]] = Field(default=None, max_length=50, description="Optional carbon-copy email addresses, plain addresses such as 'luis@empresa.com'")

    @field_validator("to", "cc")
    @classmethod
    def _addresses(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        return _clean_addresses(v)

    @field_validator("subject")
    @classmethod
    def _one_line(cls, v: str) -> str:
        if "\r" in v or "\n" in v:
            raise ValueError("el asunto debe estar en una sola linea")
        return v


class SendIn(ComposeIn):
    thread_id: Optional[str] = Field(default=None, description="Id of the Gmail thread to reply into, from gmail.messages.get; use together with in_reply_to and keep the same subject so Gmail threads the reply")
    in_reply_to: Optional[str] = Field(default=None, description="Message-ID header of the email being answered (message_id_header from gmail.messages.get, like '<abc@mail.gmail.com>'); makes the email a reply")

    @field_validator("in_reply_to")
    @classmethod
    def _header_ok(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and ("\r" in v or "\n" in v):
            raise ValueError("in_reply_to debe estar en una sola linea")
        return v.strip() if v else None


def _raw_message(args: ComposeIn, in_reply_to: Optional[str] = None) -> str:
    """Arma el correo RFC 2822 y lo codifica en base64url (lo que pide el campo `raw` de Gmail). El From lo pone Gmail."""
    msg = EmailMessage()
    msg["To"] = ", ".join(args.to)
    if args.cc:
        msg["Cc"] = ", ".join(args.cc)
    msg["Subject"] = args.subject
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to
    msg.set_content(args.body)
    return base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")


# --- gmail.drafts.create ----------------------------------------------------------------------------

class DraftOut(BaseModel):
    draft_id: str = Field(description="Id of the created draft")
    message_id: Optional[str] = Field(default=None, description="Id of the message that backs the draft")
    thread_id: Optional[str] = Field(default=None, description="Id of the thread the draft belongs to")


@function(
    id="gmail.drafts.create", version=1, verb=Verb.create, exits_outside=False, reversible=True, upstream_api="v1", scopes=[SCOPE_MODIFY],
    description=(
        "Creates a draft email in the connected Gmail account, with the recipients (to, optional cc), subject and plain-text body given, and returns the draft "
        "id, the message id and the thread id. Use it when the user wants to prepare, write or save an email to review before sending, or when the agent "
        "should show a proposed email first. The draft only appears in the Drafts folder of Gmail: nothing is delivered to anyone and the person can edit or "
        "delete it there. It does not send the email (use gmail.messages.send), does not accept attachments or HTML, and does not reply inside an existing "
        "thread."
    ),
    examples=[{"name": "default", "input": {"to": ["luis@proveedor.test"], "subject": "Re: Factura de octubre", "body": "Hola Luis,\n\nRecibida, gracias.\n\nAna"}, "output": {
        "draft_id": "r-8891245560021", "message_id": "18c3f3b2c0e5f6a7", "thread_id": "18c3f3b2c0e5f6a7"}}],
)
async def drafts_create(ctx: Context, args: ComposeIn) -> DraftOut:
    body = await _request(ctx, "POST", f"{BASE_URL}/drafts", json={"message": {"raw": _raw_message(args)}})
    if not body.get("id"):
        raise FunctionError(ErrorCode.upstream_changed, "Gmail no devolvio el id del borrador.")
    msg = body.get("message") or {}
    return DraftOut(draft_id=str(body["id"]), message_id=msg.get("id"), thread_id=msg.get("threadId"))


# --- gmail.messages.send ----------------------------------------------------------------------------

class SentOut(BaseModel):
    id: str = Field(description="Id of the sent message")
    thread_id: Optional[str] = Field(default=None, description="Id of the thread the sent message belongs to")
    label_ids: list[str] = Field(default_factory=list, description="Labels on the sent message, normally SENT")


@function(
    id="gmail.messages.send", version=1, verb=Verb.create, exits_outside=True, reversible=False, upstream_api="v1", scopes=[SCOPE_MODIFY],
    description=(
        "Sends an email right now from the connected Gmail account to the given recipients (to, optional cc) with the subject and plain-text body provided, "
        "and returns the id, thread id and labels of the sent message. To reply inside an existing conversation pass thread_id and in_reply_to (both come "
        "from gmail.messages.get) and keep the original subject. Use it only when the user clearly asks to send or reply. It is irreversible: once sent, the "
        "email cannot be recalled, so the recipients and text should be confirmed first (gmail.drafts.create saves a draft without sending). It does not "
        "support attachments, HTML bodies or scheduled sending."
    ),
    examples=[{"name": "default", "input": {"to": ["luis@proveedor.test"], "subject": "Re: Factura de octubre", "body": "Hola Luis,\n\nRecibida, gracias.\n\nAna",
                                            "thread_id": "18c3f2a1b9d4e5f6", "in_reply_to": "<CAK123abc@mail.gmail.com>"}, "output": {
        "id": "18c3f4c3d1f6a7b8", "thread_id": "18c3f2a1b9d4e5f6", "label_ids": ["SENT"]}}],
)
async def messages_send(ctx: Context, args: SendIn) -> SentOut:
    payload: dict[str, Any] = {"raw": _raw_message(args, args.in_reply_to)}
    if args.thread_id:
        payload["threadId"] = args.thread_id
    body = await _request(ctx, "POST", f"{BASE_URL}/messages/send", json=payload)
    if not body.get("id"):
        raise FunctionError(ErrorCode.upstream_changed, "Gmail no devolvio el id del mensaje enviado.")
    return SentOut(id=str(body["id"]), thread_id=body.get("threadId"), label_ids=[str(x) for x in body.get("labelIds") or []])


# --- gmail.messages.modify_labels -------------------------------------------------------------------

class ModifyIn(BaseModel):
    message_id: str = Field(min_length=1, description="Id of the message whose labels change, as returned by gmail.messages.search")
    add_label_ids: list[str] = Field(default_factory=list, max_length=100, description="Label ids to add, for example ['STARRED'] or a user label id such as 'Label_17' from gmail.labels.list (up to 100)")
    remove_label_ids: list[str] = Field(default_factory=list, max_length=100, description="Label ids to remove, for example ['UNREAD'] to mark as read or ['INBOX'] to archive (up to 100)")

    @model_validator(mode="after")
    def _something_to_change(self) -> "ModifyIn":
        if not self.add_label_ids and not self.remove_label_ids:
            raise ValueError("hay que indicar al menos una etiqueta en add_label_ids o remove_label_ids")
        return self


class ModifiedOut(BaseModel):
    id: str = Field(description="Id of the message that was changed")
    thread_id: Optional[str] = Field(default=None, description="Id of the thread the message belongs to")
    label_ids: list[str] = Field(default_factory=list, description="Ids of the labels the message has after the change")


@function(
    id="gmail.messages.modify_labels", version=1, verb=Verb.update, exits_outside=False, reversible=True, upstream_api="v1", scopes=[SCOPE_MODIFY],
    description=(
        "Adds and/or removes labels on one Gmail message and returns its id, thread id and the resulting label ids. Use it to mark a message as read "
        "(remove UNREAD) or unread (add UNREAD), archive it (remove INBOX), star it (add STARRED), mark it important, or file it under a user label whose id "
        "comes from gmail.labels.list. Up to 100 label ids can be added and 100 removed per call, and at least one is required. It is reversible by applying "
        "the opposite change. It does not send, delete or permanently remove messages, does not create labels, and works on one message at a time."
    ),
    examples=[{"name": "default", "input": {"message_id": "18c3f2a1b9d4e5f6", "remove_label_ids": ["UNREAD"]}, "output": {
        "id": "18c3f2a1b9d4e5f6", "thread_id": "18c3f2a1b9d4e5f6", "label_ids": ["INBOX"]}}],
)
async def messages_modify_labels(ctx: Context, args: ModifyIn) -> ModifiedOut:
    body = await _request(ctx, "POST", _msg_url(args.message_id, "/modify"),
                          json={"addLabelIds": args.add_label_ids, "removeLabelIds": args.remove_label_ids})
    if not body.get("id"):
        raise FunctionError(ErrorCode.upstream_changed, "Gmail no devolvio el mensaje modificado.")
    return ModifiedOut(id=str(body["id"]), thread_id=body.get("threadId"), label_ids=[str(x) for x in body.get("labelIds") or []])


# --- gmail.labels.create ----------------------------------------------------------------------------

class LabelCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=225, description=(
        "Name of the new label as it should appear in Gmail, for example 'Clientes'; a slash makes it a sub-label, so 'Clientes/VIP' is nested inside 'Clientes'. "
        "It must not already exist"))

    @field_validator("name")
    @classmethod
    def _clean_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("el nombre de la etiqueta no puede estar vacio")
        return v


@function(
    id="gmail.labels.create", version=1, verb=Verb.create, exits_outside=False, reversible=True, upstream_api="v1", scopes=[SCOPE_MODIFY],
    description=(
        "Creates a new user label in the connected Gmail account and returns its id, name and type. Use it when the user wants a new label or folder to file mail "
        "under, for example 'create a label called Clientes', and then pass the returned id as add_label_ids to gmail.messages.modify_labels to apply it. The "
        "name must be new: if a label with that name already exists (or conflicts with a system label) the call fails with an invalid input error, so check "
        "gmail.labels.list first when unsure. A slash in the name creates a nested label. It only creates the label; it does not apply it to any message, "
        "rename it or delete it, and it sends nothing outside the account."
    ),
    examples=[{"name": "default", "input": {"name": "Clientes"}, "output": {"id": "Label_42", "name": "Clientes", "type": "user"}}],
)
async def labels_create(ctx: Context, args: LabelCreateIn) -> LabelItem:
    try:
        body = await _request(ctx, "POST", f"{BASE_URL}/labels",
                              json={"name": args.name, "labelListVisibility": "labelShow", "messageListVisibility": "show"})
    except FunctionError as exc:
        if exc.code == ErrorCode.invalid_input and exc.message.startswith("HTTP 409"):  # Gmail responde 409 cuando el nombre ya existe
            raise FunctionError(ErrorCode.invalid_input, f"Ya existe una etiqueta llamada '{args.name}' (o choca con una del sistema); usa otro nombre o busca la existente con gmail.labels.list.") from None
        raise
    if not body.get("id"):
        raise FunctionError(ErrorCode.upstream_changed, "Gmail no devolvio el id de la etiqueta creada.")
    return LabelItem(id=str(body["id"]), name=str(body.get("name") or args.name), type=body.get("type") or "user")


# --- gmail.drafts.send ------------------------------------------------------------------------------

class DraftSendIn(BaseModel):
    draft_id: str = Field(min_length=1, description="Id of the draft that already exists in Gmail, as returned in draft_id by gmail.drafts.list (which also shows its recipients and subject)")


@function(
    id="gmail.drafts.send", version=1, verb=Verb.create, exits_outside=True, reversible=False, upstream_api="v1", scopes=[SCOPE_MODIFY],
    description=(
        # La primera frase es lo unico que ve el planificador de workflows (_candidate_line): debe bastar para no elegirla
        # al enviar un correo nuevo (con la frase larga armaba "crear borrador -> enviar borrador", eval_workflow_plan).
        "Sends a draft that ALREADY EXISTS in Gmail, by its id; NOT for sending a new email (that is gmail.messages.send, one step). "
        "It sends the draft exactly as saved (written earlier by the person or saved in a previous conversation) and returns the id, "
        "thread id and labels of the sent message; the draft is consumed and no longer appears in Drafts. Use it only when the user asks to send a specific "
        "draft that is already saved, for example 'send the draft I left for Luis'; find it with gmail.drafts.list. Never create a draft just to send it: to send "
        "a new email use gmail.messages.send, which is one step. Before proposing to send a draft the agent must show the user its recipients and subject "
        "(from gmail.drafts.list), because the confirmation only shows the draft id. It is irreversible: once sent, the email cannot be recalled. "
        "It does not edit the draft (the person can do that in Gmail), does not accept new recipients or text and fails with not found when the draft id "
        "does not exist."
    ),
    examples=[{"name": "default", "input": {"draft_id": "r-8891245560021"}, "output": {
        "id": "18c3f5d4e2a7b8c9", "thread_id": "18c3f3b2c0e5f6a7", "label_ids": ["SENT"]}}],
)
async def drafts_send(ctx: Context, args: DraftSendIn) -> SentOut:
    body = await _request(ctx, "POST", f"{BASE_URL}/drafts/send", json={"id": args.draft_id})
    if not body.get("id"):
        raise FunctionError(ErrorCode.upstream_changed, "Gmail no devolvio el id del mensaje enviado.")
    return SentOut(id=str(body["id"]), thread_id=body.get("threadId"), label_ids=[str(x) for x in body.get("labelIds") or []])


# --- gmail.drafts.list ------------------------------------------------------------------------------

class DraftsListIn(BaseModel):
    q: Optional[str] = Field(default=None, description=(
        "Optional Gmail search query to narrow the drafts, the same syntax as the Gmail search box, for example 'subject:invoice' or 'to:luis@proveedor.test'; "
        "leave empty to list the most recent drafts"))
    max_results: int = Field(default=10, ge=1, le=50, description="Maximum number of drafts to return, from 1 to 50 (default 10)")
    page_token: Optional[str] = Field(default=None, description="Token returned as next_page_token by a previous call to continue the same listing from there")


class DraftRow(BaseModel):
    draft_id: str = Field(description="Draft id, to pass to gmail.drafts.send")
    message_id: Optional[str] = Field(default=None, description="Id of the message that backs the draft")
    thread_id: Optional[str] = Field(default=None, description="Id of the thread the draft belongs to")
    subject: Optional[str] = Field(default=None, description="Subject line of the draft; empty when none was written")
    to: Optional[str] = Field(default=None, description="To header: the recipients as written in the draft; empty when none were set")
    snippet: Optional[str] = Field(default=None, description="Short preview of the draft text produced by Gmail")


class DraftsListOut(BaseModel):
    drafts: list[DraftRow] = Field(description="Drafts found, each with its draft id, subject, recipients and a snippet")
    count: int = Field(description="Number of drafts returned in this page")
    next_page_token: Optional[str] = Field(default=None, description="Token to pass as page_token to get the next page; empty when this is the last page")


@function(
    id="gmail.drafts.list", version=1, verb=Verb.read, upstream_api="v1", scopes=[SCOPE_READ],
    description=(
        "Lists the drafts saved in the connected Gmail account and returns one row per draft: draft id, message id, thread id, subject, recipients and a snippet "
        "of the text. Use it to find a draft before sending it with gmail.drafts.send, or when the user asks 'which drafts do I have?' or 'find my draft about "
        "the invoice'. q optionally filters with Gmail search syntax; max_results is 1 to 50 (default 10) and next_page_token pages through more. Read-only: it "
        "does not return the full body of a draft (the snippet is a short preview), does not edit or send anything and does not list sent or received mail "
        "(use gmail.messages.search)."
    ),
    examples=[{"name": "default", "input": {"q": "subject:factura", "max_results": 10}, "output": {
        "drafts": [{"draft_id": "r-8891245560021", "message_id": "18c3f3b2c0e5f6a7", "thread_id": "18c3f3b2c0e5f6a7",
                    "subject": "Re: Factura de octubre", "to": "luis@proveedor.test", "snippet": "Hola Luis, Recibida, gracias."}],
        "count": 1, "next_page_token": None}}],
)
async def drafts_list(ctx: Context, args: DraftsListIn) -> DraftsListOut:
    params: dict[str, Any] = {"maxResults": args.max_results}
    if args.q and args.q.strip():
        params["q"] = args.q.strip()
    if args.page_token:
        params["pageToken"] = args.page_token
    listing = await _request(ctx, "GET", f"{BASE_URL}/drafts", params=params)
    items = [(str(d["id"]), str((d.get("message") or {}).get("id") or "")) for d in listing.get("drafts") or [] if d.get("id")]
    gate = asyncio.Semaphore(MAX_PARALLEL_GETS)

    async def fetch(mid: str) -> dict:
        if not mid:
            return {}
        async with gate:
            return await _request(ctx, "GET", _msg_url(mid), params={"format": "metadata", "metadataHeaders": ["To", "Subject"]})

    fetched = await asyncio.gather(*(fetch(mid) for _, mid in items), return_exceptions=True)
    rows: list[DraftRow] = []
    for (draft_id, mid), res in zip(items, fetched):
        if isinstance(res, FunctionError) and res.code == ErrorCode.not_found:
            continue  # el borrador se envio o se borro entre la lista y la lectura
        if isinstance(res, BaseException):
            raise res
        h = _header_map(res.get("payload") or {})
        rows.append(DraftRow(draft_id=draft_id, message_id=mid or None, thread_id=res.get("threadId"), subject=h.get("subject"), to=h.get("to"),
                             snippet=res.get("snippet")))
    return DraftsListOut(drafts=rows, count=len(rows), next_page_token=listing.get("nextPageToken"))
