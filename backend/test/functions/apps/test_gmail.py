"""Gmail: pruebas simuladas de la conexion, la whoami y las 7 funciones (leer, buscar, etiquetas, borrador, envio, cambiar etiquetas)."""
import base64
import email
import json
from email import policy

import httpx
import pytest
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient

from app.core.constants import Collections
from app.core.security import encrypt_data
from app.functions.registry import get_app, get_function, load_all
from app.functions.runner import execute
from app.functions.spec import ConfirmationPolicy, ErrorCode
from functions_helpers import connection_doc

COL = Collections.USER_CONNECTED_ACCOUNTS
EMAIL = "ana@empresa.test"
G = "/gmail/v1/users/me"
MID = "18c3f2a1b9d4e5f6"


@pytest.fixture(autouse=True, scope="module")
def _registry():
    load_all()


@pytest_asyncio.fixture
async def db():
    d = AsyncMongoMockClient()["gmail_test"]
    await d[COL].insert_one(connection_doc(account=EMAIL, provider="gmail", token="old-token", refresh="rt-1"))
    return d


def api(routes):
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        r = routes.get(req.url.path, httpx.Response(404))
        return r(req) if callable(r) else r

    return httpx.MockTransport(handler), seen


async def run(fid, args, db, t, **kw):
    return await execute(get_function(fid), args, db=db, user_id="u1", transport=t, **kw)


def ok(body):
    return httpx.Response(200, json=body)


def b64(text: str, pad: bool = False) -> str:
    s = base64.urlsafe_b64encode(text.encode("utf-8")).decode()
    return s if pad else s.rstrip("=")  # Gmail manda base64url SIN relleno


def parse_raw(req: httpx.Request):
    """Devuelve (cuerpo JSON de la peticion, correo RFC 2822 decodificado de `raw`)."""
    body = json.loads(req.content)
    raw = body["raw"] if "raw" in body else body["message"]["raw"]
    assert "=" not in raw.rstrip("=") and "+" not in raw and "/" not in raw  # es base64url
    msg = email.message_from_bytes(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)), policy=policy.default)
    return body, msg


def meta_msg(mid, subject, labels=("INBOX", "UNREAD")):
    return {"id": mid, "threadId": mid, "labelIds": list(labels), "snippet": f"vista previa {mid}", "payload": {"headers": [
        {"name": "From", "value": "Luis Gomez <luis@proveedor.test>"}, {"name": "To", "value": EMAIL},
        {"name": "Subject", "value": subject}, {"name": "Date", "value": "Mon, 5 Oct 2026 09:30:00 -0500"}]}}


FULL = {"id": MID, "threadId": "T1", "labelIds": ["INBOX"], "snippet": "Hola Ana", "payload": {
    "mimeType": "multipart/mixed",
    "headers": [{"name": "From", "value": "Luis <luis@proveedor.test>"}, {"name": "To", "value": EMAIL}, {"name": "Cc", "value": "bea@empresa.test"},
                {"name": "Subject", "value": "Factura de octubre"}, {"name": "Date", "value": "Mon, 5 Oct 2026 09:30:00 -0500"},
                {"name": "Message-ID", "value": "<CAK123abc@mail.gmail.com>"}],
    "parts": [
        {"mimeType": "multipart/alternative", "body": {"size": 0}, "parts": [
            {"mimeType": "text/html", "headers": [], "body": {"data": b64("<div>Hola <b>Ana</b></div>")}},
            {"mimeType": "text/plain", "headers": [{"name": "Content-Type", "value": 'text/plain; charset="UTF-8"'}],
             "body": {"data": b64("Hola Ana,\r\n\r\n\r\n\r\nAdjunto la factura de octubre. ¡Gracias! ñandú")}}]},
        {"mimeType": "application/pdf", "filename": "factura-octubre.pdf", "body": {"attachmentId": "ANG1", "size": 48213}}]}}


# --- conexion -------------------------------------------------------------------------------------

def test_app_spec_reuses_the_existing_google_login():
    app = get_app("gmail")
    assert app.whoami == "gmail.profile.get" and app.provider_keys == ["gmail"]
    assert app.auth.authorize_params == {"access_type": "offline", "prompt": "consent"}
    assert (app.auth.client_id_env, app.auth.client_secret_env) == ("DRIVE_CLIENT_ID", "DRIVE_CLIENT_SECRET")
    assert app.auth.authorize_url == "https://accounts.google.com/o/oauth2/v2/auth" and app.auth.token_url == "https://oauth2.googleapis.com/token"
    assert app.auth.scopes == ["openid", "email", "profile", "https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.modify"]


def test_marks_and_confirmation_policy_of_every_function():
    marks = {  # id -> (verbo, sale al exterior, reversible, politica)
        "gmail.profile.get": ("read", False, True, ConfirmationPolicy.assume),
        "gmail.messages.search": ("read", False, True, ConfirmationPolicy.assume),
        "gmail.messages.get": ("read", False, True, ConfirmationPolicy.assume),
        "gmail.labels.list": ("read", False, True, ConfirmationPolicy.assume),
        "gmail.drafts.create": ("create", False, True, ConfirmationPolicy.assume),
        "gmail.messages.send": ("create", True, False, ConfirmationPolicy.ask),
        "gmail.messages.modify_labels": ("update", False, True, ConfirmationPolicy.assume),
    }
    for fid, (verb, outside, reversible, pol) in marks.items():
        spec = get_function(fid).spec
        assert (spec.verb.value, spec.exits_outside, spec.reversible, spec.confirmation_policy) == (verb, outside, reversible, pol), fid
        assert spec.scopes and set(spec.scopes) <= set(get_app("gmail").auth.scopes), fid
        assert spec.examples[0].output is not None, fid


# --- whoami: gmail.profile.get --------------------------------------------------------------------

@pytest.mark.asyncio
async def test_profile_get_is_the_whoami(db):
    t, seen = api({f"{G}/profile": ok({"emailAddress": EMAIL, "messagesTotal": 4821, "threadsTotal": 2310, "historyId": "99"})})
    res = await run("gmail.profile.get", {}, db, t)
    assert res.ok and res.data == {"account_id": EMAIL, "email": EMAIL, "messages_total": 4821, "threads_total": 2310}
    assert res.data["account_id"] == res.meta.account_id
    assert seen[0].method == "GET" and seen[0].headers["authorization"] == "Bearer old-token"


@pytest.mark.asyncio
async def test_profile_without_email_is_upstream_changed(db):
    t, _ = api({f"{G}/profile": ok({})})
    assert (await run("gmail.profile.get", {}, db, t)).error.code == ErrorCode.upstream_changed


@pytest.mark.asyncio
async def test_account_saved_by_the_legacy_google_login_works_without_reconnecting():
    d = AsyncMongoMockClient()["gmail_legacy"]  # el login viejo guarda access_token / refresh_token cifrados por separado
    await d[COL].insert_one({"user_id": "u1", "provider": "gmail", "account_id": EMAIL, "status": "active",
                             "access_token": encrypt_data("legacy-token"), "refresh_token": encrypt_data("legacy-rt"),
                             "scopes": ["openid", "email", "profile", "https://www.googleapis.com/auth/gmail.readonly",
                                        "https://www.googleapis.com/auth/gmail.modify"]})
    t, seen = api({f"{G}/profile": ok({"emailAddress": EMAIL})})
    res = await run("gmail.profile.get", {}, d, t)
    assert res.ok and res.meta.account_id == EMAIL and seen[0].headers["authorization"] == "Bearer legacy-token"


@pytest.mark.asyncio
async def test_expired_token_is_refreshed_with_the_drive_client_and_retried(db, monkeypatch):
    monkeypatch.setenv("DRIVE_CLIENT_ID", "cid")
    monkeypatch.setenv("DRIVE_CLIENT_SECRET", "csecret")

    def profile(req):
        if req.headers["authorization"] == "Bearer fresh-token":
            return ok({"emailAddress": EMAIL})
        return httpx.Response(401, json={"error": {"code": 401, "status": "UNAUTHENTICATED"}})

    t, seen = api({f"{G}/profile": profile, "/token": ok({"access_token": "fresh-token", "expires_in": 3600})})
    res = await run("gmail.profile.get", {}, db, t)
    assert res.ok and [r.url.path for r in seen] == [f"{G}/profile", "/token", f"{G}/profile"]
    assert seen[1].url.host == "oauth2.googleapis.com" and b"cid" in seen[1].content


# --- gmail.messages.search ------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_lists_ids_then_fetches_metadata_for_each(db):
    t, seen = api({f"{G}/messages": ok({"messages": [{"id": "m1", "threadId": "m1"}, {"id": "m2", "threadId": "m2"}], "nextPageToken": "tok2", "resultSizeEstimate": 40}),
                   f"{G}/messages/m1": ok(meta_msg("m1", "Factura de octubre")),
                   f"{G}/messages/m2": ok(meta_msg("m2", "Reunion", labels=("INBOX",)))})
    res = await run("gmail.messages.search", {"q": " is:unread from:luis ", "max_results": 2, "label_ids": ["INBOX", "UNREAD"]}, db, t)
    assert res.ok and res.data["count"] == 2 and res.data["next_page_token"] == "tok2" and res.data["result_size_estimate"] == 40
    assert [m["id"] for m in res.data["messages"]] == ["m1", "m2"]  # conserva el orden de la lista
    first = res.data["messages"][0]
    assert first == {"id": "m1", "thread_id": "m1", "sender": "Luis Gomez <luis@proveedor.test>", "to": EMAIL, "subject": "Factura de octubre",
                     "date": "Mon, 5 Oct 2026 09:30:00 -0500", "snippet": "vista previa m1", "label_ids": ["INBOX", "UNREAD"], "unread": True}
    assert res.data["messages"][1]["unread"] is False
    # 1 llamada de lista + 1 de metadatos por mensaje
    assert seen[0].url.path == f"{G}/messages" and sorted(r.url.path for r in seen[1:]) == [f"{G}/messages/m1", f"{G}/messages/m2"]
    q = seen[0].url.params
    assert q["q"] == "is:unread from:luis" and q["maxResults"] == "2" and q.get_list("labelIds") == ["INBOX", "UNREAD"] and "pageToken" not in q
    for r in seen[1:]:
        assert r.url.params["format"] == "metadata" and r.url.params.get_list("metadataHeaders") == ["From", "To", "Subject", "Date"]


@pytest.mark.asyncio
async def test_search_without_results_makes_a_single_call(db):
    t, seen = api({f"{G}/messages": ok({"resultSizeEstimate": 0})})
    res = await run("gmail.messages.search", {}, db, t)
    assert res.ok and res.data == {"messages": [], "count": 0, "result_size_estimate": 0, "next_page_token": None}
    assert len(seen) == 1 and "q" not in seen[0].url.params and seen[0].url.params["maxResults"] == "10"


@pytest.mark.asyncio
async def test_search_forwards_the_page_token_and_skips_messages_deleted_in_between(db):
    t, seen = api({f"{G}/messages": ok({"messages": [{"id": "m1"}, {"id": "gone"}]}), f"{G}/messages/m1": ok(meta_msg("m1", "Hola"))})
    res = await run("gmail.messages.search", {"page_token": "tok2"}, db, t)  # `gone` responde 404
    assert res.ok and [m["id"] for m in res.data["messages"]] == ["m1"] and res.data["count"] == 1
    assert seen[0].url.params["pageToken"] == "tok2"


@pytest.mark.asyncio
async def test_search_failure_while_reading_a_message_is_reported(db):
    t, _ = api({f"{G}/messages": ok({"messages": [{"id": "m1"}]}), f"{G}/messages/m1": httpx.Response(403, json={"error": {"status": "PERMISSION_DENIED"}})})
    assert (await run("gmail.messages.search", {}, db, t)).error.code == ErrorCode.missing_scope


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [{"max_results": 0}, {"max_results": 51}, {"label_ids": "INBOX"}])
async def test_search_rejects_invalid_input(db, bad):
    t, seen = api({})
    assert (await run("gmail.messages.search", bad, db, t)).error.code == ErrorCode.invalid_input and not seen


# --- gmail.messages.get ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_decodes_the_base64url_plain_body_and_lists_attachments(db):
    t, seen = api({f"{G}/messages/{MID}": ok(FULL)})
    res = await run("gmail.messages.get", {"message_id": MID}, db, t)
    assert res.ok and seen[0].url.params["format"] == "full"
    d = res.data
    assert d["body"] == "Hola Ana,\n\nAdjunto la factura de octubre. ¡Gracias! ñandú"  # prefiere text/plain; sin relleno "=" y con acentos
    assert d["body_format"] == "plain" and d["body_truncated"] is False
    assert (d["sender"], d["to"], d["cc"], d["subject"]) == ("Luis <luis@proveedor.test>", EMAIL, "bea@empresa.test", "Factura de octubre")
    assert d["message_id_header"] == "<CAK123abc@mail.gmail.com>" and d["thread_id"] == "T1" and d["label_ids"] == ["INBOX"]
    assert d["attachments"] == [{"filename": "factura-octubre.pdf", "mime_type": "application/pdf", "size": 48213}]


@pytest.mark.asyncio
async def test_get_falls_back_to_html_without_tags(db):
    html = "<html><head><style>p{color:red}</style></head><body><p>Hola&nbsp;<b>Ana</b></p><p>Total: 5 &amp; 6</p><script>x()</script></body></html>"
    msg = {"id": MID, "payload": {"mimeType": "text/html", "headers": [], "body": {"data": b64(html)}}}
    t, _ = api({f"{G}/messages/{MID}": ok(msg)})
    res = await run("gmail.messages.get", {"message_id": MID}, db, t)
    assert res.ok and res.data["body_format"] == "html_stripped" and res.data["body"] == "Hola Ana\nTotal: 5 & 6"
    assert "<" not in res.data["body"] and "color" not in res.data["body"] and "x()" not in res.data["body"]


@pytest.mark.asyncio
async def test_get_cuts_long_bodies_to_2000_chars_and_honours_the_charset(db):
    big = {"id": MID, "payload": {"mimeType": "text/plain", "headers": [], "body": {"data": b64("a" * 5000)}}}
    t, _ = api({f"{G}/messages/{MID}": ok(big)})
    res = await run("gmail.messages.get", {"message_id": MID}, db, t)
    assert len(res.data["body"]) == 2000 and res.data["body_truncated"] is True
    latin = base64.urlsafe_b64encode("camión".encode("latin-1")).decode().rstrip("=")
    msg = {"id": MID, "payload": {"mimeType": "text/plain", "headers": [{"name": "Content-Type", "value": "text/plain; charset=ISO-8859-1"}], "body": {"data": latin}}}
    t, _ = api({f"{G}/messages/{MID}": ok(msg)})
    assert (await run("gmail.messages.get", {"message_id": MID}, db, t)).data["body"] == "camión"


@pytest.mark.asyncio
async def test_get_message_without_body_and_validation(db):
    t, _ = api({f"{G}/messages/{MID}": ok({"id": MID, "payload": {"mimeType": "multipart/mixed", "headers": []}})})
    res = await run("gmail.messages.get", {"message_id": MID}, db, t)
    assert res.ok and res.data["body"] == "" and res.data["body_format"] == "none" and res.data["attachments"] == []
    assert (await run("gmail.messages.get", {"message_id": ""}, db, t)).error.code == ErrorCode.invalid_input
    t, _ = api({f"{G}/messages/{MID}": ok({})})
    assert (await run("gmail.messages.get", {"message_id": MID}, db, t)).error.code == ErrorCode.upstream_changed


@pytest.mark.asyncio
async def test_message_id_is_url_encoded_in_the_path(db):
    t, seen = api({f"{G}/messages/a/b": ok({"id": "a/b"})})
    res = await run("gmail.messages.get", {"message_id": "a/b"}, db, t)
    assert res.ok and seen[0].url.raw_path.split(b"?")[0].endswith(b"/messages/a%2Fb")


# --- gmail.labels.list ----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_labels_list(db):
    t, seen = api({f"{G}/labels": ok({"labels": [{"id": "INBOX", "name": "INBOX", "type": "system", "labelListVisibility": "labelShow"},
                                                  {"id": "Label_17", "name": "Clientes", "type": "user"}]})})
    res = await run("gmail.labels.list", {}, db, t)
    assert res.ok and res.data == {"count": 2, "labels": [{"id": "INBOX", "name": "INBOX", "type": "system"},
                                                           {"id": "Label_17", "name": "Clientes", "type": "user"}]}
    assert seen[0].method == "GET"
    t, _ = api({f"{G}/labels": ok({})})
    assert (await run("gmail.labels.list", {}, db, t)).data == {"labels": [], "count": 0}


# --- gmail.drafts.create --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_drafts_create_builds_a_base64url_rfc2822_message(db):
    t, seen = api({f"{G}/drafts": ok({"id": "r-1", "message": {"id": "m9", "threadId": "t9"}})})
    res = await run("gmail.drafts.create", {"to": ["luis@proveedor.test", "bea@empresa.test"], "cc": ["jefe@empresa.test"],
                                            "subject": "Reunión de cierre", "body": "Hola,\nnos vemos mañana.\n\nAna"}, db, t)
    assert res.ok and res.data == {"draft_id": "r-1", "message_id": "m9", "thread_id": "t9"}
    assert seen[0].method == "POST"
    _, msg = parse_raw(seen[0])
    assert msg["To"] == "luis@proveedor.test, bea@empresa.test" and msg["Cc"] == "jefe@empresa.test" and msg["Subject"] == "Reunión de cierre"
    assert msg["In-Reply-To"] is None and msg["From"] is None  # el From lo pone Gmail
    assert msg.get_content().strip() == "Hola,\nnos vemos mañana.\n\nAna"
    assert "threadId" not in json.loads(seen[0].content)["message"]


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [
    {"to": [], "subject": "x", "body": "x"},
    {"to": ["no-es-correo"], "subject": "x", "body": "x"},
    {"to": ["a@b.co"], "subject": "x", "body": "x", "cc": ["roto@"]},
    {"to": ["a@b.co"], "subject": "", "body": "x"},
    {"to": ["a@b.co"], "subject": "x", "body": ""},
    {"to": ["a@b.co"], "subject": "x\nBcc: otro@x.co", "body": "x"},   # inyeccion de cabeceras
    {"to": ["a@b.co\nBcc: otro@x.co"], "subject": "x", "body": "x"},
])
async def test_drafts_create_rejects_invalid_input_without_calling_gmail(db, bad):
    t, seen = api({})
    assert (await run("gmail.drafts.create", bad, db, t)).error.code == ErrorCode.invalid_input and not seen


# --- gmail.messages.send --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_builds_the_rfc2822_message_and_posts_it(db):
    t, seen = api({f"{G}/messages/send": ok({"id": "s1", "threadId": "T1", "labelIds": ["SENT"]})})
    res = await run("gmail.messages.send", {"to": ["luis@proveedor.test"], "subject": "Hola", "body": "Texto simple"}, db, t)
    assert res.ok and res.data == {"id": "s1", "thread_id": "T1", "label_ids": ["SENT"]}
    body, msg = parse_raw(seen[0])
    assert seen[0].method == "POST" and msg["To"] == "luis@proveedor.test" and msg["Subject"] == "Hola" and msg["Cc"] is None
    assert msg["In-Reply-To"] is None and msg.get_content().strip() == "Texto simple" and "threadId" not in body


@pytest.mark.asyncio
async def test_send_reply_sets_thread_id_and_reply_headers(db):
    t, seen = api({f"{G}/messages/send": ok({"id": "s2", "threadId": "T1", "labelIds": ["SENT"]})})
    res = await run("gmail.messages.send", {"to": ["luis@proveedor.test"], "subject": "Re: Factura de octubre", "body": "Recibida, gracias.",
                                            "thread_id": "T1", "in_reply_to": "<CAK123abc@mail.gmail.com>"}, db, t)
    assert res.ok and res.data["thread_id"] == "T1"
    body, msg = parse_raw(seen[0])
    assert body["threadId"] == "T1" and msg["In-Reply-To"] == "<CAK123abc@mail.gmail.com>" and msg["References"] == "<CAK123abc@mail.gmail.com>"


@pytest.mark.asyncio
async def test_send_rejects_bad_input_without_calling_gmail(db):
    t, seen = api({})
    for bad in ({"to": ["x"], "subject": "s", "body": "b"}, {"to": ["a@b.co"], "subject": "s", "body": "b", "in_reply_to": "<a@b>\nBcc: z@z.co"},
                {"subject": "s", "body": "b"}):
        assert (await run("gmail.messages.send", bad, db, t)).error.code == ErrorCode.invalid_input
    assert not seen


@pytest.mark.asyncio
async def test_send_without_message_id_is_upstream_changed(db):
    t, _ = api({f"{G}/messages/send": ok({})})
    assert (await run("gmail.messages.send", {"to": ["a@b.co"], "subject": "s", "body": "b"}, db, t)).error.code == ErrorCode.upstream_changed


@pytest.mark.asyncio
async def test_writes_are_simulated_not_sent_when_asked_to_simulate(db):
    t, seen = api({})
    res = await run("gmail.messages.send", {"to": ["a@b.co"], "subject": "s", "body": "b"}, db, t, simulate=True)
    assert res.ok and res.meta.simulated and res.data["label_ids"] == ["SENT"] and not seen


# --- gmail.messages.modify_labels -----------------------------------------------------------------

@pytest.mark.asyncio
async def test_modify_labels_posts_add_and_remove(db):
    t, seen = api({f"{G}/messages/{MID}/modify": ok({"id": MID, "threadId": "T1", "labelIds": ["INBOX", "STARRED"]})})
    res = await run("gmail.messages.modify_labels", {"message_id": MID, "add_label_ids": ["STARRED"], "remove_label_ids": ["UNREAD"]}, db, t)
    assert res.ok and res.data == {"id": MID, "thread_id": "T1", "label_ids": ["INBOX", "STARRED"]}
    assert seen[0].method == "POST" and json.loads(seen[0].content) == {"addLabelIds": ["STARRED"], "removeLabelIds": ["UNREAD"]}


@pytest.mark.asyncio
async def test_modify_labels_mark_as_read_only_removes_unread(db):
    t, seen = api({f"{G}/messages/{MID}/modify": ok({"id": MID, "labelIds": ["INBOX"]})})
    assert (await run("gmail.messages.modify_labels", {"message_id": MID, "remove_label_ids": ["UNREAD"]}, db, t)).ok
    assert json.loads(seen[0].content) == {"addLabelIds": [], "removeLabelIds": ["UNREAD"]}


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [{"message_id": MID}, {"message_id": MID, "add_label_ids": [], "remove_label_ids": []},
                                 {"message_id": "", "add_label_ids": ["STARRED"]}, {"add_label_ids": ["STARRED"]}])
async def test_modify_labels_rejects_invalid_input(db, bad):
    t, seen = api({})
    assert (await run("gmail.messages.modify_labels", bad, db, t)).error.code == ErrorCode.invalid_input and not seen


# --- errores de la API mapeados a codigos del contrato ---------------------------------------------

ALL_IDS = ["gmail.profile.get", "gmail.messages.search", "gmail.messages.get", "gmail.labels.list", "gmail.drafts.create",
           "gmail.messages.send", "gmail.messages.modify_labels"]


def everything(resp: httpx.Response):
    """Transporte que responde lo mismo a cualquier ruta."""
    seen = []

    def handler(req):
        seen.append(req)
        return resp

    return httpx.MockTransport(handler), seen


@pytest.mark.asyncio
@pytest.mark.parametrize("fid", ALL_IDS)
async def test_each_function_maps_404_429_5xx_and_403_to_contract_codes(fid, db, monkeypatch):
    monkeypatch.setattr("app.functions.connections.RETRY_DELAY_SECONDS", 0)
    example = get_function(fid).spec.examples[0].input
    scope_body = {"error": {"code": 403, "status": "PERMISSION_DENIED", "message": "Request had insufficient authentication scopes."}}
    for status, body, code in ((404, {"error": {"code": 404}}, ErrorCode.not_found), (429, {"error": {"code": 429}}, ErrorCode.rate_limited),
                               (500, {"error": {"code": 500}}, ErrorCode.upstream_down), (403, scope_body, ErrorCode.missing_scope)):
        t, _ = everything(httpx.Response(status, json=body))
        res = await run(fid, example, db, t)
        assert not res.ok and res.error.code == code, (fid, status, res.error)
    assert (await db[COL].find_one({"account_id": EMAIL}))["status"] == "active"  # un 403 de scope no vence la cuenta


@pytest.mark.asyncio
async def test_403_for_rate_limit_is_rate_limited_not_missing_scope(db):
    body = {"error": {"code": 403, "message": "User-rate limit exceeded. Retry after 2026-10-10T10:00:00.000Z", "errors": [
        {"domain": "usageLimits", "reason": "userRateLimitExceeded"}], "status": "RESOURCE_EXHAUSTED"}}
    t, _ = everything(httpx.Response(403, json=body))
    res = await run("gmail.messages.search", {}, db, t)
    assert res.error.code == ErrorCode.rate_limited and res.error.retryable is True


@pytest.mark.asyncio
async def test_401_without_refresh_token_expires_the_account():
    d = AsyncMongoMockClient()["gmail_401"]
    await d[COL].insert_one(connection_doc(account=EMAIL, provider="gmail", token="old-token"))  # sin refresh_token
    t, _ = everything(httpx.Response(401, json={"error": {"code": 401, "status": "UNAUTHENTICATED"}}))
    res = await run("gmail.labels.list", {}, d, t)
    assert res.error.code == ErrorCode.auth_expired and (await d[COL].find_one({"account_id": EMAIL}))["status"] == "expired"


@pytest.mark.asyncio
async def test_400_from_gmail_is_invalid_input(db):
    t, _ = everything(httpx.Response(400, json={"error": {"code": 400, "message": "Invalid label: NOPE", "status": "INVALID_ARGUMENT"}}))
    res = await run("gmail.messages.modify_labels", {"message_id": MID, "add_label_ids": ["NOPE"]}, db, t)
    assert res.error.code == ErrorCode.invalid_input


# --- funciones agregadas despues: labels.create, drafts.send, drafts.list ---------------------------

NEW_IDS = ["gmail.labels.create", "gmail.drafts.send", "gmail.drafts.list"]


def test_marks_and_confirmation_policy_of_the_added_functions():
    marks = {  # id -> (verbo, sale al exterior, reversible, politica, scope)
        "gmail.labels.create": ("create", False, True, ConfirmationPolicy.assume, "gmail.modify"),
        "gmail.drafts.send": ("create", True, False, ConfirmationPolicy.ask, "gmail.modify"),  # igual que gmail.messages.send
        "gmail.drafts.list": ("read", False, True, ConfirmationPolicy.assume, "gmail.readonly"),
    }
    for fid, (verb, outside, reversible, pol, scope) in marks.items():
        spec = get_function(fid).spec
        assert (spec.verb.value, spec.exits_outside, spec.reversible, spec.confirmation_policy) == (verb, outside, reversible, pol), fid
        assert spec.version == 1 and spec.scopes == [f"https://www.googleapis.com/auth/{scope}"], fid  # ningun scope nuevo en la app
        assert set(spec.scopes) <= set(get_app("gmail").auth.scopes) and spec.examples[0].output is not None, fid
    send, plain = get_function("gmail.drafts.send").spec, get_function("gmail.messages.send").spec
    assert (send.exits_outside, send.reversible, send.confirmation_policy) == (plain.exits_outside, plain.reversible, plain.confirmation_policy)


# gmail.labels.create

@pytest.mark.asyncio
async def test_labels_create_posts_the_name_and_returns_id_and_name(db):
    t, seen = api({f"{G}/labels": ok({"id": "Label_42", "name": "Clientes", "type": "user", "labelListVisibility": "labelShow"})})
    res = await run("gmail.labels.create", {"name": "  Clientes "}, db, t)
    assert res.ok and res.data == {"id": "Label_42", "name": "Clientes", "type": "user"}
    assert seen[0].method == "POST" and json.loads(seen[0].content) == {"name": "Clientes", "labelListVisibility": "labelShow", "messageListVisibility": "show"}


@pytest.mark.asyncio
async def test_labels_create_with_an_existing_name_is_invalid_input_with_a_clear_message(db):
    err = httpx.Response(409, json={"error": {"code": 409, "message": "Label name exists or conflicts", "status": "ALREADY_EXISTS"}})
    t, _ = api({f"{G}/labels": err})
    res = await run("gmail.labels.create", {"name": "Clientes"}, db, t)
    assert res.error.code == ErrorCode.invalid_input and res.error.user_action == "fix_input"
    assert "Ya existe una etiqueta llamada 'Clientes'" in res.error.message and "HTTP 409" not in res.error.message


@pytest.mark.asyncio
async def test_labels_create_other_400_keeps_the_gmail_message(db):
    t, _ = api({f"{G}/labels": httpx.Response(400, json={"error": {"code": 400, "message": "Invalid label name"}})})
    res = await run("gmail.labels.create", {"name": "bad"}, db, t)
    assert res.error.code == ErrorCode.invalid_input and "HTTP 400" in res.error.message


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [{}, {"name": ""}, {"name": "   "}, {"name": "x" * 226}])
async def test_labels_create_rejects_invalid_input_without_calling_gmail(db, bad):
    t, seen = api({})
    assert (await run("gmail.labels.create", bad, db, t)).error.code == ErrorCode.invalid_input and not seen


@pytest.mark.asyncio
async def test_labels_create_without_id_is_upstream_changed(db):
    t, _ = api({f"{G}/labels": ok({})})
    assert (await run("gmail.labels.create", {"name": "X"}, db, t)).error.code == ErrorCode.upstream_changed


# gmail.drafts.send

def test_drafts_send_description_steers_away_from_sending_a_new_email():
    desc = get_function("gmail.drafts.send").spec.description
    assert desc.startswith("Sends a draft that ALREADY EXISTS in Gmail")
    assert "Never create a draft just to send it" in desc and "gmail.messages.send" in desc and "one step" in desc
    assert "recipients and subject" in desc and "gmail.drafts.list" in desc and "only shows the draft id" in desc


@pytest.mark.asyncio
async def test_drafts_send_posts_the_draft_id(db):
    t, seen = api({f"{G}/drafts/send": ok({"id": "s7", "threadId": "T7", "labelIds": ["SENT"]})})
    res = await run("gmail.drafts.send", {"draft_id": "r-1"}, db, t)
    assert res.ok and res.data == {"id": "s7", "thread_id": "T7", "label_ids": ["SENT"]}
    assert seen[0].method == "POST" and json.loads(seen[0].content) == {"id": "r-1"}


@pytest.mark.asyncio
async def test_drafts_send_unknown_draft_is_not_found(db):
    t, _ = api({f"{G}/drafts/send": httpx.Response(404, json={"error": {"code": 404, "message": "Requested entity was not found."}})})
    assert (await run("gmail.drafts.send", {"draft_id": "r-nope"}, db, t)).error.code == ErrorCode.not_found


@pytest.mark.asyncio
async def test_drafts_send_requires_a_draft_id_and_is_simulated_when_asked(db):
    t, seen = api({})
    assert (await run("gmail.drafts.send", {}, db, t)).error.code == ErrorCode.invalid_input
    assert (await run("gmail.drafts.send", {"draft_id": ""}, db, t)).error.code == ErrorCode.invalid_input
    res = await run("gmail.drafts.send", {"draft_id": "r-1"}, db, t, simulate=True)
    assert res.ok and res.meta.simulated and res.data["label_ids"] == ["SENT"] and not seen  # nunca sale un correo real en simulacion


@pytest.mark.asyncio
async def test_drafts_send_without_message_id_is_upstream_changed(db):
    t, _ = api({f"{G}/drafts/send": ok({})})
    assert (await run("gmail.drafts.send", {"draft_id": "r-1"}, db, t)).error.code == ErrorCode.upstream_changed


# gmail.drafts.list

@pytest.mark.asyncio
async def test_drafts_list_reads_each_draft_message_for_subject_and_recipients(db):
    t, seen = api({f"{G}/drafts": ok({"drafts": [{"id": "r-1", "message": {"id": "m1", "threadId": "t1"}}, {"id": "r-2", "message": {"id": "m2", "threadId": "t2"}}],
                                      "nextPageToken": "tok2", "resultSizeEstimate": 2}),
                   f"{G}/messages/m1": ok({**meta_msg("m1", "Re: Factura"), "threadId": "t1", "snippet": "Hola Luis"}),
                   f"{G}/messages/m2": ok({"id": "m2", "threadId": "t2", "snippet": "sin destinatario", "payload": {"headers": []}})})
    res = await run("gmail.drafts.list", {"q": " subject:factura ", "max_results": 2}, db, t)
    assert res.ok and res.data == {"count": 2, "next_page_token": "tok2", "drafts": [
        {"draft_id": "r-1", "message_id": "m1", "thread_id": "t1", "subject": "Re: Factura", "to": EMAIL, "snippet": "Hola Luis"},
        {"draft_id": "r-2", "message_id": "m2", "thread_id": "t2", "subject": None, "to": None, "snippet": "sin destinatario"}]}
    assert seen[0].method == "GET" and seen[0].url.path == f"{G}/drafts"
    assert seen[0].url.params["q"] == "subject:factura" and seen[0].url.params["maxResults"] == "2" and "pageToken" not in seen[0].url.params
    for r in seen[1:]:
        assert r.url.params["format"] == "metadata" and r.url.params.get_list("metadataHeaders") == ["To", "Subject"]


@pytest.mark.asyncio
async def test_drafts_list_without_drafts_makes_a_single_call_and_forwards_the_page_token(db):
    t, seen = api({f"{G}/drafts": ok({"resultSizeEstimate": 0})})
    res = await run("gmail.drafts.list", {"page_token": "tok9"}, db, t)
    assert res.ok and res.data == {"drafts": [], "count": 0, "next_page_token": None}
    assert len(seen) == 1 and seen[0].url.params["pageToken"] == "tok9" and seen[0].url.params["maxResults"] == "10" and "q" not in seen[0].url.params


@pytest.mark.asyncio
async def test_drafts_list_skips_a_draft_sent_between_the_list_and_the_read(db):
    t, _ = api({f"{G}/drafts": ok({"drafts": [{"id": "r-1", "message": {"id": "m1"}}, {"id": "r-gone", "message": {"id": "gone"}}]}),
                f"{G}/messages/m1": ok(meta_msg("m1", "Hola"))})  # `gone` responde 404
    res = await run("gmail.drafts.list", {}, db, t)
    assert res.ok and [d["draft_id"] for d in res.data["drafts"]] == ["r-1"] and res.data["count"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [{"max_results": 0}, {"max_results": 51}, {"q": ["a"]}])
async def test_drafts_list_caps_max_results_and_rejects_invalid_input(db, bad):
    t, seen = api({})
    assert (await run("gmail.drafts.list", bad, db, t)).error.code == ErrorCode.invalid_input and not seen


# errores de la API en las funciones agregadas

@pytest.mark.asyncio
@pytest.mark.parametrize("fid", NEW_IDS)
async def test_added_functions_map_404_429_5xx_and_403_to_contract_codes(fid, db, monkeypatch):
    monkeypatch.setattr("app.functions.connections.RETRY_DELAY_SECONDS", 0)
    example = get_function(fid).spec.examples[0].input
    scope_body = {"error": {"code": 403, "status": "PERMISSION_DENIED", "message": "Request had insufficient authentication scopes."}}
    for status, body, code in ((404, {"error": {"code": 404}}, ErrorCode.not_found), (429, {"error": {"code": 429}}, ErrorCode.rate_limited),
                               (500, {"error": {"code": 500}}, ErrorCode.upstream_down), (403, scope_body, ErrorCode.missing_scope)):
        t, _ = everything(httpx.Response(status, json=body))
        res = await run(fid, example, db, t)
        assert not res.ok and res.error.code == code, (fid, status, res.error)
    assert (await db[COL].find_one({"account_id": EMAIL}))["status"] == "active"
