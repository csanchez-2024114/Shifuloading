"""Google Docs: pruebas simuladas (httpx.MockTransport) de la conexion, la whoami y las 5 funciones."""
import json

import httpx
import pytest
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient

from app.core.constants import Collections
from app.functions import connections
from app.functions.apps.google_docs.functions import MAX_TEXT_CHARS
from app.functions.registry import get_app, get_function, list_functions, load_all
from app.functions.runner import execute
from app.functions.spec import ErrorCode
from functions_helpers import connection_doc

COL = Collections.USER_CONNECTED_ACCOUNTS
EMAIL = "ana@empresa.test"
DID = "1AbCdEfGhIjKlMnOpQrStUvWxYz012345"
BASE = f"/v1/documents/{DID}"
URL = f"https://docs.google.com/document/d/{DID}/edit"
ALL_IDS = ["google_docs.account.get", "google_docs.documents.get", "google_docs.documents.create",
           "google_docs.text.append", "google_docs.text.replace"]
DOC_ARGS = [("google_docs.documents.get", {}), ("google_docs.text.append", {"text": "x"}),
            ("google_docs.text.replace", {"find": "a", "replacement": "b"})]


@pytest.fixture(autouse=True, scope="module")
def _registry():
    load_all()


@pytest.fixture(autouse=True)
def _no_retry_delay(monkeypatch):
    monkeypatch.setattr(connections, "RETRY_DELAY_SECONDS", 0)


@pytest_asyncio.fixture
async def db():
    d = AsyncMongoMockClient()["gdocs_test"]
    await d[COL].insert_one(connection_doc(account=EMAIL, provider="google_docs", token="old-token", refresh="rt-1"))
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


def para(text):
    return {"paragraph": {"elements": [{"textRun": {"content": text}}]}}


DOC = {"documentId": DID, "title": "Project brief", "body": {"content": [
    {"sectionBreak": {}},
    para("Project brief\n"),
    {"paragraph": {"elements": [{"textRun": {"content": "Goal: "}}, {"textRun": {"content": "launch the site", "textStyle": {"bold": True}},}, {"horizontalRule": {}},
                                {"textRun": {"content": ".\n"}}]}},
    {"tableOfContents": {"content": [para("Should not appear\n")]}},
    {"table": {"tableRows": [
        {"tableCells": [{"content": [para("Owner\n")]}, {"content": [para("Ana\u000bPerez\n")]}]},
        {"tableCells": [{"content": [para("Deadline\n")]}, {"content": [para("2026-12-01\n")]}]}]}},
    para("Last line\n"),
]}}


# --- conexion y whoami ----------------------------------------------------------------------------

def test_app_registers_with_the_legacy_google_login():
    app = get_app("google_docs")
    assert app.whoami == "google_docs.account.get" and app.provider_keys == ["google_docs"] and app.api_version == "v1"
    assert app.auth.authorize_params == {"access_type": "offline", "prompt": "consent"}
    assert (app.auth.client_id_env, app.auth.client_secret_env) == ("DRIVE_CLIENT_ID", "DRIVE_CLIENT_SECRET")
    assert app.auth.authorize_url == "https://accounts.google.com/o/oauth2/v2/auth" and app.auth.token_url == "https://oauth2.googleapis.com/token"
    # exactamente los scopes del login legacy (SERVICE_SCOPES["docs"] + BASE_SCOPES): sin Drive
    assert app.auth.scopes == ["openid", "email", "profile", "https://www.googleapis.com/auth/documents"]


def test_load_all_still_validates_and_lists_the_functions():
    load_all()
    mine = {f.spec.id for f in list_functions() if f.spec.app == "google_docs"}
    assert mine == set(ALL_IDS)  # sin search ni rename: eso lo hace google_drive y este login no concede Drive
    assert not any(f.spec.verb.value == "delete" for f in list_functions() if f.spec.app == "google_docs")


def test_get_description_points_to_google_drive_for_search_and_rename():
    desc = get_function("google_docs.documents.get").spec.description
    assert "google_drive.files.search" in desc and "google_drive.files.rename" in desc and 'file_type "document"' in desc
    props = get_function("google_docs.documents.get").spec.input_schema["properties"]["document_id"]["description"]
    assert "google_drive.files.search" in props


def test_replace_description_says_it_covers_the_whole_document():
    desc = get_function("google_docs.text.replace").spec.description
    assert "headers, footers, footnotes and every tab" in desc


@pytest.mark.asyncio
async def test_whoami_returns_the_email_as_account_id(db):
    t, seen = api({"/v1/userinfo": ok({"sub": "1122", "name": "Ana Perez", "email": EMAIL})})
    res = await run("google_docs.account.get", {}, db, t)
    assert res.ok and res.data == {"account_id": EMAIL, "email": EMAIL, "name": "Ana Perez", "google_user_id": "1122"}
    assert res.data["account_id"] == res.meta.account_id
    assert seen[0].url.host == "openidconnect.googleapis.com" and seen[0].headers["authorization"] == "Bearer old-token"


@pytest.mark.asyncio
async def test_whoami_without_email_is_upstream_changed(db):
    t, _ = api({"/v1/userinfo": ok({"sub": "1122"})})
    assert (await run("google_docs.account.get", {}, db, t)).error.code == ErrorCode.upstream_changed


@pytest.mark.asyncio
async def test_401_without_a_working_refresh_expires_the_account(db, monkeypatch):
    monkeypatch.delenv("DRIVE_CLIENT_ID", raising=False)
    monkeypatch.delenv("DRIVE_CLIENT_SECRET", raising=False)
    t, _ = api({BASE: httpx.Response(401, json={"error": {"status": "UNAUTHENTICATED"}})})
    res = await run("google_docs.documents.get", {"document_id": DID}, db, t)
    assert res.error.code == ErrorCode.auth_expired and res.error.user_action == "reconnect_app"
    assert (await db[COL].find_one({"account_id": EMAIL}))["status"] != "active"


# --- errores de la API -----------------------------------

SCOPE_403 = httpx.Response(403, json={"error": {"code": 403, "status": "PERMISSION_DENIED", "message": "Request had insufficient authentication scopes.",
                                                "details": [{"reason": "ACCESS_TOKEN_SCOPE_INSUFFICIENT"}]}})
NO_ACCESS_403 = httpx.Response(403, json={"error": {"code": 403, "status": "PERMISSION_DENIED", "message": "The caller does not have permission"}})
RATE_403 = httpx.Response(403, json={"error": {"code": 403, "errors": [{"reason": "userRateLimitExceeded"}], "message": "User rate limit exceeded."}})

ERRORS = [(SCOPE_403, ErrorCode.missing_scope), (NO_ACCESS_403, ErrorCode.access_denied), (RATE_403, ErrorCode.rate_limited),
          (httpx.Response(404, json={"error": {"message": "Requested entity was not found."}}), ErrorCode.not_found),
          (httpx.Response(429, json={"error": {"message": "Quota exceeded"}}), ErrorCode.rate_limited),
          (httpx.Response(400, json={"error": {"message": "Invalid requests[0]"}}), ErrorCode.invalid_input),
          (httpx.Response(503, json={"error": {"message": "unavailable"}}), ErrorCode.upstream_down)]


@pytest.mark.parametrize("resp,code", ERRORS)
@pytest.mark.parametrize("fid,path,args", [
    ("google_docs.documents.get", BASE, {"document_id": DID}),
    ("google_docs.text.replace", f"{BASE}:batchUpdate", {"document_id": DID, "find": "a", "replacement": "b"}),
    ("google_docs.documents.create", "/v1/documents", {"title": "T"}),
])
@pytest.mark.asyncio
async def test_api_errors_map_to_contract_codes(db, fid, path, args, resp, code):
    t, _ = api({path: resp})
    assert (await run(fid, args, db, t)).error.code == code


@pytest.mark.asyncio
async def test_403_does_not_expire_the_account(db):
    t, _ = api({BASE: SCOPE_403})
    assert (await run("google_docs.documents.get", {"document_id": DID}, db, t)).error.code == ErrorCode.missing_scope
    assert (await db[COL].find_one({"account_id": EMAIL}))["status"] == "active"


@pytest.mark.asyncio
async def test_non_json_answer_is_upstream_changed(db):
    t, _ = api({BASE: httpx.Response(200, text="<html>")})
    assert (await run("google_docs.documents.get", {"document_id": DID}, db, t)).error.code == ErrorCode.upstream_changed


# --- id desde URL ---------------------------------------------------------------------------------

@pytest.mark.parametrize("raw", [
    DID,
    f"  {DID}  ",
    f"https://docs.google.com/document/d/{DID}/edit",
    f"https://docs.google.com/document/d/{DID}/edit?usp=sharing#heading=h.abc",
    f"https://docs.google.com/document/u/0/d/{DID}/edit",
    f"docs.google.com/document/d/{DID}",
])
@pytest.mark.asyncio
async def test_document_id_is_extracted_from_a_url(db, raw):
    t, seen = api({BASE: ok(DOC)})
    res = await run("google_docs.documents.get", {"document_id": raw}, db, t)
    assert res.ok and seen[0].url.path == BASE


@pytest.mark.parametrize("bad", ["", "   ", "not an id", "https://example.com/foo", "a/b", "id?x=1"])
@pytest.mark.parametrize("fid,extra", DOC_ARGS)
@pytest.mark.asyncio
async def test_invalid_document_id_is_invalid_input(db, fid, extra, bad):
    t, seen = api({})
    res = await run(fid, {"document_id": bad, **extra}, db, t)
    assert res.error.code == ErrorCode.invalid_input and not seen


# --- documents.get ---------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_documents_get_flattens_paragraphs_and_tables(db):
    t, seen = api({BASE: ok(DOC)})
    res = await run("google_docs.documents.get", {"document_id": DID}, db, t)
    text = "Project brief\nGoal: launch the site.\nOwner\tAna Perez\nDeadline\t2026-12-01\nLast line"
    assert res.ok and res.data == {"document_id": DID, "title": "Project brief", "text": text, "total_characters": len(text), "truncated": False, "url": URL}
    req = seen[0]
    assert req.method == "GET" and str(req.url).startswith(f"https://docs.googleapis.com{BASE}?")
    assert req.url.params["fields"] == "documentId,title,body(content)" and "includeTabsContent" not in req.url.params


@pytest.mark.asyncio
async def test_documents_get_converts_soft_line_breaks_and_tolerates_an_empty_body(db):
    t, _ = api({BASE: ok({"documentId": DID, "title": "Empty"})})
    res = await run("google_docs.documents.get", {"document_id": DID}, db, t)
    assert res.ok and res.data["text"] == "" and res.data["total_characters"] == 0 and res.data["truncated"] is False
    t, _ = api({BASE: ok({"documentId": DID, "title": "T", "body": {"content": [para("a\u000bb\n")]}})})
    assert (await run("google_docs.documents.get", {"document_id": DID}, db, t)).data["text"] == "a\nb"


@pytest.mark.asyncio
async def test_documents_get_cuts_long_text_and_flags_truncated(db):
    big = {"documentId": DID, "title": "Big", "body": {"content": [para("x" * (MAX_TEXT_CHARS + 500) + "\n")]}}
    t, _ = api({BASE: ok(big)})
    res = await run("google_docs.documents.get", {"document_id": DID}, db, t)
    assert res.ok and len(res.data["text"]) == MAX_TEXT_CHARS and res.data["truncated"] is True and res.data["total_characters"] == MAX_TEXT_CHARS + 500


@pytest.mark.asyncio
async def test_documents_get_exactly_at_the_limit_is_not_truncated(db):
    t, _ = api({BASE: ok({"documentId": DID, "title": "Edge", "body": {"content": [para("x" * MAX_TEXT_CHARS + "\n")]}})})
    res = await run("google_docs.documents.get", {"document_id": DID}, db, t)
    assert res.data["truncated"] is False and len(res.data["text"]) == MAX_TEXT_CHARS


@pytest.mark.asyncio
async def test_documents_get_without_title_is_upstream_changed(db):
    t, _ = api({BASE: ok({"documentId": DID})})
    assert (await run("google_docs.documents.get", {"document_id": DID}, db, t)).error.code == ErrorCode.upstream_changed


# --- documents.create ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_documents_create_with_text_creates_then_inserts_at_the_end(db):
    t, seen = api({"/v1/documents": ok({"documentId": "NEWDOC1", "title": "Meeting notes"}), "/v1/documents/NEWDOC1:batchUpdate": ok({"documentId": "NEWDOC1", "replies": [{}]})})
    res = await run("google_docs.documents.create", {"title": " Meeting notes ", "text": "Agenda\n1. Budget"}, db, t)
    assert res.ok and res.data == {"document_id": "NEWDOC1", "title": "Meeting notes", "url": "https://docs.google.com/document/d/NEWDOC1/edit", "characters_added": 16}
    assert [(r.method, r.url.path) for r in seen] == [("POST", "/v1/documents"), ("POST", "/v1/documents/NEWDOC1:batchUpdate")]
    assert json.loads(seen[0].content) == {"title": "Meeting notes"}
    assert json.loads(seen[1].content) == {"requests": [{"insertText": {"endOfSegmentLocation": {}, "text": "Agenda\n1. Budget"}}]}


@pytest.mark.asyncio
async def test_documents_create_without_text_makes_one_call(db):
    t, seen = api({"/v1/documents": ok({"documentId": "NEWDOC1", "title": "Blank"})})
    res = await run("google_docs.documents.create", {"title": "Blank"}, db, t)
    assert res.ok and res.data["characters_added"] == 0 and len(seen) == 1


@pytest.mark.asyncio
async def test_documents_create_failure_writing_the_text_reports_the_empty_document(db):
    t, _ = api({"/v1/documents": ok({"documentId": "NEWDOC1", "title": "T"}), "/v1/documents/NEWDOC1:batchUpdate": httpx.Response(429, json={})})
    res = await run("google_docs.documents.create", {"title": "T", "text": "hello"}, db, t)
    assert res.error.code == ErrorCode.rate_limited and "NEWDOC1" in res.error.message


@pytest.mark.parametrize("bad", [{}, {"title": ""}, {"title": "   "}, {"title": "x" * 256}, {"title": "T", "text": "x" * 100001}])
@pytest.mark.asyncio
async def test_documents_create_rejects_invalid_input(db, bad):
    t, seen = api({})
    assert (await run("google_docs.documents.create", bad, db, t)).error.code == ErrorCode.invalid_input and not seen


@pytest.mark.asyncio
async def test_documents_create_without_id_is_upstream_changed(db):
    t, _ = api({"/v1/documents": ok({})})
    assert (await run("google_docs.documents.create", {"title": "T"}, db, t)).error.code == ErrorCode.upstream_changed


# --- text.append -----------------------------------------------------------------------------------

def _append_routes(end_index):
    return {BASE: ok({"body": {"content": [{"endIndex": 1}, {"startIndex": 1, "endIndex": end_index}]}}),
            f"{BASE}:batchUpdate": ok({"documentId": DID, "replies": [{}]})}


@pytest.mark.asyncio
async def test_text_append_adds_a_new_paragraph_at_the_end_of_a_document_with_content(db):
    t, seen = api(_append_routes(120))
    res = await run("google_docs.text.append", {"document_id": URL, "text": "Action item: send the budget."}, db, t)
    assert res.ok and res.data == {"document_id": DID, "characters_added": 29, "url": URL}
    assert [r.method for r in seen] == ["GET", "POST"] and seen[0].url.params["fields"] == "body(content(endIndex))"
    assert seen[1].url.path == f"{BASE}:batchUpdate"
    assert json.loads(seen[1].content) == {"requests": [{"insertText": {"endOfSegmentLocation": {}, "text": "\nAction item: send the budget."}}]}


@pytest.mark.asyncio
async def test_text_append_to_an_empty_document_does_not_open_a_blank_line(db):
    t, seen = api(_append_routes(2))
    assert (await run("google_docs.text.append", {"document_id": DID, "text": "First"}, db, t)).ok
    assert json.loads(seen[1].content)["requests"][0]["insertText"]["text"] == "First"


@pytest.mark.asyncio
async def test_text_append_without_new_paragraph_skips_the_read_and_continues_the_last_one(db):
    t, seen = api(_append_routes(120))
    assert (await run("google_docs.text.append", {"document_id": DID, "text": " more", "new_paragraph": False}, db, t)).ok
    assert [r.method for r in seen] == ["POST"] and json.loads(seen[0].content)["requests"][0]["insertText"]["text"] == " more"


@pytest.mark.parametrize("bad", [{}, {"text": ""}, {"text": "x" * 100001}])
@pytest.mark.asyncio
async def test_text_append_rejects_invalid_input(db, bad):
    t, seen = api({})
    assert (await run("google_docs.text.append", {"document_id": DID, **bad}, db, t)).error.code == ErrorCode.invalid_input and not seen


# --- text.replace ----------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_text_replace_sends_replace_all_text_and_returns_the_count(db):
    t, seen = api({f"{BASE}:batchUpdate": ok({"documentId": DID, "replies": [{"replaceAllText": {"occurrencesChanged": 3}}]})})
    res = await run("google_docs.text.replace", {"document_id": DID, "find": "2025", "replacement": "2026"}, db, t)
    assert res.ok and res.data == {"document_id": DID, "occurrences_changed": 3, "url": URL}
    req = seen[0]
    assert req.method == "POST" and req.url.path == f"{BASE}:batchUpdate"
    assert json.loads(req.content) == {"requests": [{"replaceAllText": {"containsText": {"text": "2025", "matchCase": True}, "replaceText": "2026"}}]}


@pytest.mark.asyncio
async def test_text_replace_without_matches_returns_zero_and_accepts_empty_replacement_and_ignore_case(db):
    t, seen = api({f"{BASE}:batchUpdate": ok({"documentId": DID, "replies": [{"replaceAllText": {}}]})})
    res = await run("google_docs.text.replace", {"document_id": DID, "find": "Draft", "replacement": "", "match_case": False}, db, t)
    assert res.ok and res.data["occurrences_changed"] == 0
    assert json.loads(seen[0].content)["requests"][0]["replaceAllText"] == {"containsText": {"text": "Draft", "matchCase": False}, "replaceText": ""}


@pytest.mark.asyncio
async def test_text_replace_without_replies_is_upstream_changed(db):
    t, _ = api({f"{BASE}:batchUpdate": ok({"documentId": DID})})
    assert (await run("google_docs.text.replace", {"document_id": DID, "find": "a", "replacement": "b"}, db, t)).error.code == ErrorCode.upstream_changed


@pytest.mark.parametrize("bad", [{}, {"find": "", "replacement": "b"}, {"find": "a"}, {"find": "x" * 2001, "replacement": "b"}])
@pytest.mark.asyncio
async def test_text_replace_rejects_invalid_input(db, bad):
    t, seen = api({})
    assert (await run("google_docs.text.replace", {"document_id": DID, **bad}, db, t)).error.code == ErrorCode.invalid_input and not seen


# --- fichas ----------------------------------------------------------------------------------------

def test_contract_marks_of_every_function():
    marks = {fid: (get_function(fid).spec.verb.value, get_function(fid).spec.exits_outside, get_function(fid).spec.reversible) for fid in ALL_IDS}
    assert marks == {
        "google_docs.account.get": ("read", False, True), "google_docs.documents.get": ("read", False, True),
        "google_docs.documents.create": ("create", False, True),
        "google_docs.text.append": ("update", False, True), "google_docs.text.replace": ("update", False, False)}
    policy = {fid: get_function(fid).spec.confirmation_policy.value for fid in ALL_IDS}
    assert policy["google_docs.text.replace"] == "ask" and policy["google_docs.text.append"] == "assume" and policy["google_docs.documents.create"] == "assume"


def test_scopes_are_declared_by_the_app_and_examples_validate():
    declared = set(get_app("google_docs").auth.scopes)
    docs = "https://www.googleapis.com/auth/documents"
    expected = {"google_docs.documents.get": [docs], "google_docs.documents.create": [docs], "google_docs.text.append": [docs],
                "google_docs.text.replace": [docs], "google_docs.account.get": ["openid", "email"]}
    for fid in ALL_IDS:
        fn = get_function(fid)
        spec = fn.spec
        assert spec.scopes == expected[fid] and set(spec.scopes) <= declared
        assert spec.version == 1 and "account_id" not in spec.input_schema.get("properties", {})
        for ex in spec.examples:
            assert ex.output is not None
            fn.input_model.model_validate(ex.input)
            fn.output_model.model_validate(ex.output)


@pytest.mark.asyncio
async def test_simulated_run_returns_the_example_output(db):
    res = await run("google_docs.text.replace", {"document_id": DID, "find": "a", "replacement": "b"}, db, api({})[0], simulate=True)
    assert res.ok and res.meta.simulated and res.data == get_function("google_docs.text.replace").spec.examples[0].output
