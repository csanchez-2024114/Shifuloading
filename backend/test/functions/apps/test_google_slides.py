"""Google Slides: pruebas simuladas de la conexion, la whoami (Tarea 2), las 3 lecturas de la Tarea 3 y las funciones de contenido y escritura."""
import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient

from app.core.constants import Collections
from functions_helpers import unseal
from app.functions.registry import get_app, get_function, list_functions, load_all
from app.functions.runner import execute
from app.functions.spec import ErrorCode
from functions_helpers import connection_doc

COL = Collections.USER_CONNECTED_ACCOUNTS
PERMISSION_ID = "11223344556677889900"
PRES = "1AbCdEfGhIjKlMnOpQrStUvWxYz"
PAGE = "g1234abcd_0_0"
D = "/drive/v3"
S = "/v1/presentations"


@pytest.fixture(autouse=True, scope="module")
def _registry():
    load_all()


@pytest_asyncio.fixture
async def db():
    d = AsyncMongoMockClient()["gslides_test"]
    await d[COL].insert_one(connection_doc(account=PERMISSION_ID, provider="google_slides", token="old-token", refresh="rt-1"))
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


ABOUT = {"user": {"permissionId": PERMISSION_ID, "emailAddress": "ana@empresa.test", "displayName": "Ana Perez"}}
FILES = {"files": [{"id": PRES, "name": "Q3 results", "webViewLink": "https://docs.google.com/presentation/d/x/edit", "modifiedTime": "2026-10-01T12:00:00.000Z"}],
         "nextPageToken": "tok2"}
THREAD = {"commentId": "AAAAx1", "anchorId": "kix.abc", "status": "OPEN", "plainTextQuote": "Q3 results",
          "headPost": {"postId": "p1", "content": "Add the chart", "author": {"displayName": "Ana Perez"}, "createTime": "2026-10-01T12:00:00Z"},
          "replies": [{"postId": "p2", "content": "Done", "author": {"displayName": "Luis"}, "createTime": "2026-10-02T09:00:00Z", "deleted": True}]}
PAGE_BODY = {"objectId": PAGE, "pageType": "SLIDE", "revisionId": "ALm37BX", "pageElements": [
    {"objectId": "t1", "shape": {"text": {"textElements": [{"textRun": {"content": "Q3 "}}, {"textRun": {"content": "results\n"}}]}}},
    {"objectId": "tb1", "table": {"tableRows": [{"tableCells": [{"text": {"textElements": [{"textRun": {"content": "Ventas"}}]}},
                                                              {"text": {"textElements": [{"textRun": {"content": "10"}}]}}]}]}},
    {"objectId": "im1", "title": "Logo", "image": {"contentUrl": "https://x"}},
    {"objectId": "g1", "elementGroup": {"children": [{"objectId": "g1a", "shape": {"text": {"textElements": [{"textRun": {"content": "Dentro"}}]}}}]}},
    {"objectId": "zz"}],
    "comments": [THREAD]}

PAGE_ARGS = {"presentation_id": PRES, "page_object_id": PAGE}
READ_IDS = ["google_slides.slides.get_page", "google_slides.slides.get_thumbnail", "google_slides.comments.get_page_comments"]


# --- conexion ------------------------------------------------------------------------------------

def test_app_spec_asks_for_offline_access_and_minimal_scopes():
    app = get_app("google_slides")
    assert app.whoami == "google_slides.presentations.list" and app.provider_keys == ["google_slides"]
    assert app.auth.authorize_params == {"access_type": "offline", "prompt": "consent"}
    assert app.auth.scopes == ["https://www.googleapis.com/auth/presentations.readonly", "https://www.googleapis.com/auth/drive.metadata.readonly",
                               "https://www.googleapis.com/auth/presentations"]


# --- whoami (Tarea 2) ----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_whoami_returns_identity_and_lists_presentations(db):
    t, seen = api({f"{D}/about": ok(ABOUT), f"{D}/files": ok(FILES)})
    res = await run("google_slides.presentations.list", {}, db, t)
    assert res.ok and res.data == {
        "account_id": PERMISSION_ID, "email": "ana@empresa.test", "display_name": "Ana Perez", "next_page_token": "tok2",
        "presentations": [{"id": PRES, "name": "Q3 results", "web_view_link": "https://docs.google.com/presentation/d/x/edit",
                           "modified_time": "2026-10-01T12:00:00.000Z"}]}
    assert res.data["account_id"] == res.meta.account_id
    assert seen[0].headers["authorization"] == "Bearer old-token"
    q = seen[1].url.params
    assert "application/vnd.google-apps.presentation" in q["q"] and "trashed=false" in q["q"] and q["pageSize"] == "10"
    assert q["orderBy"] == "modifiedTime desc" and "pageToken" not in q


@pytest.mark.asyncio
async def test_whoami_forwards_the_page_token(db):
    t, seen = api({f"{D}/about": ok(ABOUT), f"{D}/files": ok({"files": []})})
    res = await run("google_slides.presentations.list", {"page_size": 5, "page_token": "tok2"}, db, t)
    assert res.ok and res.data["presentations"] == [] and res.data["next_page_token"] is None
    assert seen[1].url.params["pageToken"] == "tok2" and seen[1].url.params["pageSize"] == "5"


@pytest.mark.asyncio
async def test_whoami_rejects_a_page_size_out_of_range(db):
    assert (await run("google_slides.presentations.list", {"page_size": 0}, db, api({})[0])).error.code == ErrorCode.invalid_input


@pytest.mark.asyncio
async def test_missing_scope_is_403_and_does_not_expire_the_account(db):
    body = {"error": {"code": 403, "status": "PERMISSION_DENIED", "message": "Request had insufficient authentication scopes.",
                      "details": [{"reason": "ACCESS_TOKEN_SCOPE_INSUFFICIENT"}]}}
    t, seen = api({f"{D}/about": httpx.Response(403, json=body)})
    res = await run("google_slides.presentations.list", {}, db, t)
    assert res.error.code == ErrorCode.missing_scope and res.error.user_action == "grant_scopes"
    assert len(seen) == 1 and (await db[COL].find_one({"account_id": PERMISSION_ID}))["status"] == "active"


@pytest.mark.asyncio
async def test_unexpected_response_shape_is_upstream_changed(db):
    t, _ = api({f"{D}/about": ok({"user": {}})})
    assert (await run("google_slides.presentations.list", {}, db, t)).error.code == ErrorCode.upstream_changed


@pytest.mark.asyncio
async def test_expired_token_is_refreshed_with_google_token_endpoint_and_retried(db, monkeypatch):
    monkeypatch.setenv("GOOGLE_SLIDES_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_SLIDES_CLIENT_SECRET", "csecret")

    def about(req):
        if req.headers["authorization"] == "Bearer fresh-token":
            return ok(ABOUT)
        return httpx.Response(401, json={"error": {"code": 401, "status": "UNAUTHENTICATED"}})

    t, seen = api({f"{D}/about": about, f"{D}/files": ok(FILES), "/token": ok({"access_token": "fresh-token", "expires_in": 3600})})
    res = await run("google_slides.presentations.list", {}, db, t)
    assert res.ok and [r.url.path for r in seen[:3]] == [f"{D}/about", "/token", f"{D}/about"]
    assert seen[1].url.host == "oauth2.googleapis.com"
    doc = await db[COL].find_one({"account_id": PERMISSION_ID})
    assert unseal(doc["credentials_enc"]) == {"token": "fresh-token", "refresh_token": "rt-1"}


# --- Tarea 3: entrada invalida y error de la app --------------------------------------------------

@pytest.mark.parametrize("fid", READ_IDS)
@pytest.mark.asyncio
async def test_each_read_validates_its_required_input(fid, db):
    for bad in ({}, {"presentation_id": PRES}, {"presentation_id": "", "page_object_id": PAGE}):
        assert (await run(fid, bad, db, api({})[0])).error.code == ErrorCode.invalid_input


@pytest.mark.parametrize("fid", READ_IDS)
@pytest.mark.asyncio
async def test_each_read_maps_upstream_404_to_not_found(fid, db):
    assert (await run(fid, PAGE_ARGS, db, api({})[0])).error.code == ErrorCode.not_found


@pytest.mark.parametrize("fid", READ_IDS)
@pytest.mark.asyncio
async def test_each_read_maps_403_to_missing_scope(fid, db):
    t, _ = api({f"{S}/{PRES}/pages/{PAGE}": httpx.Response(403, json={"error": {"status": "PERMISSION_DENIED"}}),
                f"{S}/{PRES}/pages/{PAGE}/thumbnail": httpx.Response(403, json={})})
    assert (await run(fid, PAGE_ARGS, db, t)).error.code == ErrorCode.missing_scope


# --- get_page ------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_page_summarizes_elements_and_text(db):
    t, seen = api({f"{S}/{PRES}/pages/{PAGE}": ok(PAGE_BODY)})
    res = await run("google_slides.slides.get_page", PAGE_ARGS, db, t)
    assert res.ok and res.data["object_id"] == PAGE and res.data["page_type"] == "SLIDE" and res.data["revision_id"] == "ALm37BX"
    assert [(e["object_id"], e["kind"], e["text"]) for e in res.data["elements"]] == [
        ("t1", "shape", "Q3 results"), ("tb1", "table", "Ventas\n10"), ("im1", "image", None), ("g1", "elementGroup", "Dentro"), ("zz", "unknown", None)]
    assert res.data["elements"][2]["title"] == "Logo"
    assert res.data["text"] == "Q3 results\nVentas\n10\nDentro"
    assert res.data["comments"] == [] and "commentsViewMode" not in seen[0].url.params


@pytest.mark.asyncio
async def test_get_page_with_comments_asks_for_them(db):
    t, seen = api({f"{S}/{PRES}/pages/{PAGE}": ok(PAGE_BODY)})
    res = await run("google_slides.slides.get_page", {**PAGE_ARGS, "include_comments": True}, db, t)
    assert res.ok and res.data["comments"][0]["comment_id"] == "AAAAx1"
    assert seen[0].url.params["commentsViewMode"] == "COMMENTS_VIEW_MODE_INCLUDED"


@pytest.mark.asyncio
async def test_get_page_without_object_id_is_upstream_changed(db):
    t, _ = api({f"{S}/{PRES}/pages/{PAGE}": ok({})})
    assert (await run("google_slides.slides.get_page", PAGE_ARGS, db, t)).error.code == ErrorCode.upstream_changed


@pytest.mark.asyncio
async def test_ids_are_url_encoded_in_the_path(db):
    t, seen = api({f"{S}/{PRES}/pages/a/b": ok({"objectId": "a/b"})})
    res = await run("google_slides.slides.get_page", {"presentation_id": PRES, "page_object_id": "a/b"}, db, t)
    assert res.ok and res.data["object_id"] == "a/b" and seen[0].url.raw_path.split(b"?")[0].endswith(b"/pages/a%2Fb")


# --- get_thumbnail -------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_thumbnail_returns_the_png_url(db):
    t, seen = api({f"{S}/{PRES}/pages/{PAGE}/thumbnail": ok({"contentUrl": "https://lh3.googleusercontent.com/abc", "width": 800, "height": 450})})
    res = await run("google_slides.slides.get_thumbnail", {**PAGE_ARGS, "thumbnail_size": "LARGE"}, db, t)
    assert res.ok and res.data == {"content_url": "https://lh3.googleusercontent.com/abc", "width": 800, "height": 450, "mime_type": "PNG"}
    q = seen[0].url.params
    assert q["thumbnailProperties.thumbnailSize"] == "LARGE" and q["thumbnailProperties.mimeType"] == "PNG"


@pytest.mark.asyncio
async def test_get_thumbnail_defaults_to_medium_and_rejects_unknown_sizes(db):
    t, seen = api({f"{S}/{PRES}/pages/{PAGE}/thumbnail": ok({"contentUrl": "https://x"})})
    assert (await run("google_slides.slides.get_thumbnail", PAGE_ARGS, db, t)).ok
    assert seen[0].url.params["thumbnailProperties.thumbnailSize"] == "MEDIUM"
    assert (await run("google_slides.slides.get_thumbnail", {**PAGE_ARGS, "thumbnail_size": "HUGE"}, db, t)).error.code == ErrorCode.invalid_input


@pytest.mark.asyncio
async def test_get_thumbnail_without_url_is_upstream_changed(db):
    t, _ = api({f"{S}/{PRES}/pages/{PAGE}/thumbnail": ok({})})
    assert (await run("google_slides.slides.get_thumbnail", PAGE_ARGS, db, t)).error.code == ErrorCode.upstream_changed


# --- get_page_comments ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_page_comments_returns_threads_with_replies(db):
    t, seen = api({f"{S}/{PRES}/pages/{PAGE}": ok(PAGE_BODY)})
    res = await run("google_slides.comments.get_page_comments", PAGE_ARGS, db, t)
    assert res.ok and res.data["count"] == 1 and res.data["page_object_id"] == PAGE
    thread = res.data["comments"][0]
    assert thread["status"] == "OPEN" and thread["quote"] == "Q3 results" and thread["anchor_id"] == "kix.abc"
    assert thread["head_post"] == {"post_id": "p1", "content": "Add the chart", "author": "Ana Perez", "create_time": "2026-10-01T12:00:00Z", "deleted": False}
    assert thread["replies"][0]["author"] == "Luis" and thread["replies"][0]["deleted"] is True
    assert seen[0].url.params["commentsViewMode"] == "COMMENTS_VIEW_MODE_INCLUDED"


@pytest.mark.asyncio
async def test_get_page_comments_without_comments_is_empty(db):
    t, _ = api({f"{S}/{PRES}/pages/{PAGE}": ok({"objectId": PAGE})})
    res = await run("google_slides.comments.get_page_comments", PAGE_ARGS, db, t)
    assert res.ok and res.data == {"page_object_id": PAGE, "comments": [], "count": 0}


def test_all_functions_are_reads_with_declared_scopes():
    for fid in READ_IDS + ["google_slides.presentations.list"]:
        spec = get_function(fid).spec
        assert spec.verb.value == "read" and not spec.exits_outside and spec.scopes
        assert set(spec.scopes) <= set(get_app("google_slides").auth.scopes)


@pytest.mark.asyncio
@pytest.mark.parametrize("prop,kind", [("slideProperties", "SLIDE"), ("layoutProperties", "LAYOUT"), ("masterProperties", "MASTER"), ("notesProperties", "NOTES")])
async def test_get_page_deduces_the_type_when_google_does_not_send_page_type(db, prop, kind):
    body = {"objectId": PAGE, prop: {}, "pageElements": [], "pageProperties": {}}  # la forma real de pages.get: sin pageType
    t, _ = api({f"{S}/{PRES}/pages/{PAGE}": ok(body)})
    res = await run("google_slides.slides.get_page", PAGE_ARGS, db, t)
    assert res.ok and res.data["page_type"] == kind and res.data["revision_id"] is None
    t, _ = api({f"{S}/{PRES}/pages/{PAGE}": ok({"objectId": PAGE})})
    assert (await run("google_slides.slides.get_page", PAGE_ARGS, db, t)).data["page_type"] is None


@pytest.mark.asyncio
async def test_comments_on_a_view_only_presentation_are_access_denied_without_expiring_the_account(db):
    err = httpx.Response(403, json={"error": {"code": 403, "message": "You do not have permission to view comments on this presentation.", "status": "PERMISSION_DENIED"}})
    t, _ = api({f"{S}/{PRES}/pages/{PAGE}": err})
    res = await run("google_slides.comments.get_page_comments", PAGE_ARGS, db, t)
    assert res.error.code == ErrorCode.access_denied
    assert (await db[COL].find_one({"account_id": PERMISSION_ID}))["status"] == "active"


# --- contenido y escrituras: presentations.get / create, slides.add / duplicate, text.replace -------

FN = "app.functions.apps.google_slides.functions"
SCOPE_W = "https://www.googleapis.com/auth/presentations"
SCOPE_R = "https://www.googleapis.com/auth/presentations.readonly"
URL_EDIT = f"https://docs.google.com/presentation/d/{PRES}/edit"
BATCH = f"{S}/{PRES}:batchUpdate"


def text_box(oid, *runs):
    return {"objectId": oid, "shape": {"text": {"textElements": [{"textRun": {"content": r}} for r in runs]}}}


PRESENTATION = {"presentationId": PRES, "title": "Q3 results", "revisionId": "ALm37BX", "slides": [
    {"objectId": "p", "pageElements": [text_box("t1", "Q3 ", "results\n"), text_box("t2", "Sales grew 12%"), {"objectId": "im1", "image": {}}]},
    {"objectId": PAGE, "pageElements": [{"objectId": "tb1", "table": {"tableRows": [{"tableCells": [
        {"text": {"textElements": [{"textRun": {"content": "Ventas"}}]}}, {"text": {"textElements": [{"textRun": {"content": "10"}}]}}]}]}}]},
    {"objectId": "empty", "pageElements": []}]}


def sent(req):
    return json.loads(req.content)


@pytest.fixture
def _no_retry_delay(monkeypatch):
    monkeypatch.setattr("app.functions.connections.RETRY_DELAY_SECONDS", 0)


@pytest.fixture
def ids(monkeypatch):
    """Ids nuevos predecibles: slide_1, title_2, body_3..."""
    n = iter(range(1, 100))
    monkeypatch.setattr(f"{FN}._new_id", lambda prefix: f"{prefix}_{next(n)}")


def test_new_functions_declare_verb_scope_and_confirmation_policy():
    expected = {
        "google_slides.presentations.get": ("read", [SCOPE_R], "assume"),
        "google_slides.presentations.create": ("create", [SCOPE_W], "assume"),
        "google_slides.slides.add": ("update", [SCOPE_W], "assume"),
        "google_slides.slides.duplicate": ("create", [SCOPE_W], "assume"),
        "google_slides.text.replace": ("update", [SCOPE_W], "ask"),
    }
    for fid, (verb, scopes, policy) in expected.items():
        spec = get_function(fid).spec
        assert (spec.verb.value, spec.scopes, spec.confirmation_policy.value, spec.version) == (verb, scopes, policy, 1), fid
        assert not spec.exits_outside and set(spec.scopes) <= set(get_app("google_slides").auth.scopes)
    # sin funciones de borrado, a proposito
    assert not [f.spec.id for f in list_functions() if f.spec.app == "google_slides" and (f.spec.verb.value == "delete" or f.spec.id.endswith(".delete"))]


# presentations.get

@pytest.mark.asyncio
@pytest.mark.parametrize("given", [PRES, URL_EDIT, f"https://docs.google.com/presentation/u/0/d/{PRES}/edit#slide=id.p", f"  {PRES}  "])
async def test_presentations_get_accepts_the_id_or_the_full_url(db, given):
    t, seen = api({f"{S}/{PRES}": ok(PRESENTATION)})
    res = await run("google_slides.presentations.get", {"presentation_id": given}, db, t)
    assert res.ok and res.data["presentation_id"] == PRES
    assert seen[0].method == "GET" and seen[0].url.path == f"{S}/{PRES}"
    assert seen[0].url.params["fields"] == "presentationId,title,revisionId,slides(objectId,pageElements)"


@pytest.mark.asyncio
async def test_presentations_get_flattens_the_text_of_every_slide(db):
    t, _ = api({f"{S}/{PRES}": ok(PRESENTATION)})
    res = await run("google_slides.presentations.get", {"presentation_id": PRES}, db, t)
    assert res.data == {
        "presentation_id": PRES, "title": "Q3 results", "url": URL_EDIT, "revision_id": "ALm37BX", "slide_count": 3, "truncated": False,
        "slides": [{"object_id": "p", "index": 0, "text": "Q3 results\nSales grew 12%"}, {"object_id": PAGE, "index": 1, "text": "Ventas\n10"},
                   {"object_id": "empty", "index": 2, "text": ""}]}


@pytest.mark.asyncio
async def test_presentations_get_caps_the_total_text_and_flags_truncated(db, monkeypatch):
    monkeypatch.setattr(f"{FN}.MAX_TOTAL_CHARS", 30)
    body = {"presentationId": PRES, "title": "Long", "slides": [
        {"objectId": "a", "pageElements": [text_box("x", "A" * 20)]}, {"objectId": "b", "pageElements": [text_box("y", "B" * 20)]},
        {"objectId": "c", "pageElements": [text_box("z", "C" * 20)]}, {"objectId": "d", "pageElements": []}]}
    t, _ = api({f"{S}/{PRES}": ok(body)})
    res = await run("google_slides.presentations.get", {"presentation_id": PRES}, db, t)
    assert res.ok and res.data["truncated"] is True and res.data["slide_count"] == 4
    assert [s["text"] for s in res.data["slides"]] == ["A" * 20, "B" * 10, "", ""]
    assert sum(len(s["text"]) for s in res.data["slides"]) == 30


@pytest.mark.asyncio
async def test_presentations_get_exactly_at_the_cap_is_not_truncated(db, monkeypatch):
    monkeypatch.setattr(f"{FN}.MAX_TOTAL_CHARS", 20)
    t, _ = api({f"{S}/{PRES}": ok({"presentationId": PRES, "title": "T", "slides": [{"objectId": "a", "pageElements": [text_box("x", "A" * 20)]}]})})
    res = await run("google_slides.presentations.get", {"presentation_id": PRES}, db, t)
    assert res.ok and res.data["truncated"] is False and res.data["slides"][0]["text"] == "A" * 20


@pytest.mark.asyncio
async def test_presentations_get_rejects_a_bad_id_and_a_malformed_answer(db):
    for bad in ("", "not an id!", "https://example.com/doc/d/abc"):
        assert (await run("google_slides.presentations.get", {"presentation_id": bad}, db, api({})[0])).error.code == ErrorCode.invalid_input
    t, _ = api({f"{S}/{PRES}": ok({"slides": []})})
    assert (await run("google_slides.presentations.get", {"presentation_id": PRES}, db, t)).error.code == ErrorCode.upstream_changed


# presentations.create

@pytest.mark.asyncio
async def test_presentations_create_posts_the_title(db):
    t, seen = api({S: ok({"presentationId": "NEWID123", "title": "Q4 plan", "slides": [{"objectId": "p"}]})})
    res = await run("google_slides.presentations.create", {"title": " Q4 plan "}, db, t)
    assert res.ok and res.data == {"presentation_id": "NEWID123", "title": "Q4 plan", "slide_ids": ["p"],
                                   "url": "https://docs.google.com/presentation/d/NEWID123/edit"}
    assert seen[0].method == "POST" and seen[0].url.path == S and sent(seen[0]) == {"title": "Q4 plan"}
    assert seen[0].headers["authorization"] == "Bearer old-token"


@pytest.mark.asyncio
async def test_presentations_create_validates_input_and_answer(db):
    assert (await run("google_slides.presentations.create", {"title": ""}, db, api({})[0])).error.code == ErrorCode.invalid_input
    t, _ = api({S: ok({})})
    assert (await run("google_slides.presentations.create", {"title": "x"}, db, t)).error.code == ErrorCode.upstream_changed


# slides.add

def created(sid="slide_1"):
    return ok({"presentationId": PRES, "replies": [{"createSlide": {"objectId": sid}}]})


@pytest.mark.asyncio
async def test_slides_add_with_title_and_body_is_one_batch_update(db, ids):
    t, seen = api({BATCH: ok({"replies": [{"createSlide": {"objectId": "slide_1"}}, {}, {}]})})
    res = await run("google_slides.slides.add", {"presentation_id": URL_EDIT, "title": "Next steps", "body": "Hire two\nLaunch"}, db, t)
    assert res.ok and res.data == {"presentation_id": PRES, "slide_object_id": "slide_1", "layout": "TITLE_AND_BODY", "index": None}
    assert len(seen) == 1 and seen[0].method == "POST" and seen[0].url.path == BATCH
    assert sent(seen[0]) == {"requests": [
        {"createSlide": {"objectId": "slide_1", "slideLayoutReference": {"predefinedLayout": "TITLE_AND_BODY"}, "placeholderIdMappings": [
            {"layoutPlaceholder": {"type": "TITLE", "index": 0}, "objectId": "title_2"},
            {"layoutPlaceholder": {"type": "BODY", "index": 0}, "objectId": "body_3"}]}},
        {"insertText": {"objectId": "title_2", "insertionIndex": 0, "text": "Next steps"}},
        {"insertText": {"objectId": "body_3", "insertionIndex": 0, "text": "Hire two\nLaunch"}}]}


@pytest.mark.asyncio
async def test_slides_add_title_only_layout(db, ids):
    t, seen = api({BATCH: ok({"replies": [{"createSlide": {"objectId": "slide_1"}}, {}]})})
    res = await run("google_slides.slides.add", {"presentation_id": PRES, "layout": "TITLE_ONLY", "title": "Thanks"}, db, t)
    assert res.ok and res.data["layout"] == "TITLE_ONLY"
    assert sent(seen[0])["requests"] == [
        {"createSlide": {"objectId": "slide_1", "slideLayoutReference": {"predefinedLayout": "TITLE_ONLY"},
                         "placeholderIdMappings": [{"layoutPlaceholder": {"type": "TITLE", "index": 0}, "objectId": "title_2"}]}},
        {"insertText": {"objectId": "title_2", "insertionIndex": 0, "text": "Thanks"}}]


@pytest.mark.asyncio
async def test_slides_add_blank_layout_has_no_placeholders(db, ids):
    t, seen = api({BATCH: created()})
    res = await run("google_slides.slides.add", {"presentation_id": PRES, "layout": "BLANK"}, db, t)
    assert res.ok and res.data["layout"] == "BLANK"
    assert sent(seen[0])["requests"] == [{"createSlide": {"objectId": "slide_1", "slideLayoutReference": {"predefinedLayout": "BLANK"}}}]


@pytest.mark.asyncio
async def test_slides_add_defaults_to_title_and_body_without_text(db, ids):
    t, seen = api({BATCH: created()})
    res = await run("google_slides.slides.add", {"presentation_id": PRES}, db, t)
    assert res.ok and res.data["layout"] == "TITLE_AND_BODY"
    assert sent(seen[0])["requests"] == [{"createSlide": {"objectId": "slide_1", "slideLayoutReference": {"predefinedLayout": "TITLE_AND_BODY"}}}]


@pytest.mark.asyncio
async def test_slides_add_at_an_index(db, ids):
    t, seen = api({BATCH: created()})
    res = await run("google_slides.slides.add", {"presentation_id": PRES, "layout": "BLANK", "index": 0}, db, t)
    assert res.ok and res.data["index"] == 0 and sent(seen[0])["requests"][0]["createSlide"]["insertionIndex"] == 0
    t, seen = api({BATCH: created()})
    res = await run("google_slides.slides.add", {"presentation_id": PRES, "layout": "BLANK", "index": 2}, db, t)
    assert res.data["index"] == 2 and sent(seen[0])["requests"][0]["createSlide"]["insertionIndex"] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [
    {"layout": "BLANK", "title": "x"}, {"layout": "BLANK", "body": "x"}, {"layout": "TITLE_ONLY", "body": "x"},
    {"layout": "TWO_COLUMNS"}, {"index": -1}, {"title": ""},
])
async def test_slides_add_rejects_text_without_placeholder_unknown_layout_and_bad_index(db, bad):
    t, seen = api({})
    assert (await run("google_slides.slides.add", {"presentation_id": PRES, **bad}, db, t)).error.code == ErrorCode.invalid_input
    assert not seen


@pytest.mark.asyncio
async def test_slides_add_without_created_slide_or_replies_is_upstream_changed(db):
    for body in ({"replies": [{}]}, {}, {"replies": []}):
        t, _ = api({BATCH: ok(body)})
        assert (await run("google_slides.slides.add", {"presentation_id": PRES, "layout": "BLANK"}, db, t)).error.code == ErrorCode.upstream_changed


@pytest.mark.asyncio
async def test_slides_add_with_a_layout_the_deck_lacks_is_invalid_input(db):
    t, _ = api({BATCH: httpx.Response(400, json={"error": {"status": "INVALID_ARGUMENT", "message": "Invalid layout"}})})
    assert (await run("google_slides.slides.add", {"presentation_id": PRES}, db, t)).error.code == ErrorCode.invalid_input


# text.replace

@pytest.mark.asyncio
async def test_text_replace_sends_replace_all_text_and_returns_the_count(db):
    t, seen = api({BATCH: ok({"replies": [{"replaceAllText": {"occurrencesChanged": 3}}]})})
    res = await run("google_slides.text.replace", {"presentation_id": PRES, "find": "2025", "replace_with": "2026"}, db, t)
    assert res.ok and res.data == {"presentation_id": PRES, "occurrences_changed": 3}
    assert seen[0].method == "POST" and seen[0].url.path == BATCH
    assert sent(seen[0]) == {"requests": [{"replaceAllText": {"containsText": {"text": "2025", "matchCase": True}, "replaceText": "2026"}}]}


@pytest.mark.asyncio
async def test_text_replace_with_no_matches_returns_zero(db):
    t, _ = api({BATCH: ok({"replies": [{"replaceAllText": {}}]})})
    res = await run("google_slides.text.replace", {"presentation_id": PRES, "find": "zzz", "replace_with": "y"}, db, t)
    assert res.ok and res.data["occurrences_changed"] == 0


@pytest.mark.asyncio
async def test_text_replace_can_ignore_case_and_delete_text(db):
    t, seen = api({BATCH: ok({"replies": [{"replaceAllText": {"occurrencesChanged": 1}}]})})
    res = await run("google_slides.text.replace", {"presentation_id": PRES, "find": "draft", "replace_with": "", "match_case": False}, db, t)
    assert res.ok and sent(seen[0])["requests"][0]["replaceAllText"] == {"containsText": {"text": "draft", "matchCase": False}, "replaceText": ""}


@pytest.mark.asyncio
async def test_text_replace_requires_a_text_to_find(db):
    for bad in ({"find": "", "replace_with": "x"}, {"find": "x"}, {"replace_with": "x"}):
        assert (await run("google_slides.text.replace", {"presentation_id": PRES, **bad}, db, api({})[0])).error.code == ErrorCode.invalid_input


def test_descriptions_state_the_real_scope_and_replace_behaviour():
    create = get_function("google_slides.presentations.create").spec.description
    assert "reconnect" not in create.lower()
    replace = get_function("google_slides.text.replace").spec.description
    assert "cannot limit the change to one slide" in replace and "speaker notes and layouts" in replace and "edit speaker" not in replace
    dup = get_function("google_slides.slides.duplicate").spec
    assert "must be the object id of a slide" in dup.description and "not the id of a shape" in dup.description
    assert "must be a slide's object id" in dup.input_schema["properties"]["slide_object_id"]["description"]


# slides.duplicate

@pytest.mark.asyncio
async def test_slides_duplicate_returns_the_new_slide_id(db):
    t, seen = api({BATCH: ok({"replies": [{"duplicateObject": {"objectId": "g1234abcd_0_9"}}]})})
    res = await run("google_slides.slides.duplicate", {"presentation_id": URL_EDIT, "slide_object_id": PAGE}, db, t)
    assert res.ok and res.data == {"presentation_id": PRES, "source_slide_object_id": PAGE, "new_slide_object_id": "g1234abcd_0_9"}
    assert seen[0].method == "POST" and seen[0].url.path == BATCH
    assert sent(seen[0]) == {"requests": [{"duplicateObject": {"objectId": PAGE}}]}


@pytest.mark.asyncio
async def test_slides_duplicate_validates_input_and_answer(db):
    assert (await run("google_slides.slides.duplicate", {"presentation_id": PRES, "slide_object_id": ""}, db, api({})[0])).error.code == ErrorCode.invalid_input
    t, _ = api({BATCH: ok({"replies": [{}]})})
    assert (await run("google_slides.slides.duplicate", {"presentation_id": PRES, "slide_object_id": PAGE}, db, t)).error.code == ErrorCode.upstream_changed


# errores de la app (403 por scope, 403 sin acceso, 404, 429) en las cinco funciones nuevas

NEW_CALLS = [
    ("google_slides.presentations.get", {"presentation_id": PRES}, f"{S}/{PRES}"),
    ("google_slides.presentations.create", {"title": "Q4 plan"}, S),
    ("google_slides.slides.add", {"presentation_id": PRES, "layout": "BLANK"}, BATCH),
    ("google_slides.text.replace", {"presentation_id": PRES, "find": "a", "replace_with": "b"}, BATCH),
    ("google_slides.slides.duplicate", {"presentation_id": PRES, "slide_object_id": PAGE}, BATCH),
]
SCOPE_BODY = {"error": {"code": 403, "status": "PERMISSION_DENIED", "message": "Request had insufficient authentication scopes.",
                        "details": [{"reason": "ACCESS_TOKEN_SCOPE_INSUFFICIENT"}]}}
NO_ACCESS_BODY = {"error": {"code": 403, "status": "PERMISSION_DENIED", "message": "The caller does not have permission"}}


@pytest.mark.asyncio
@pytest.mark.parametrize("fid,args,path", NEW_CALLS)
async def test_new_functions_map_403_without_the_scope_to_missing_scope_and_keep_the_account(db, fid, args, path):
    t, seen = api({path: httpx.Response(403, json=SCOPE_BODY)})
    res = await run(fid, args, db, t)
    assert res.error.code == ErrorCode.missing_scope and res.error.user_action == "grant_scopes"
    assert len(seen) == 1 and (await db[COL].find_one({"account_id": PERMISSION_ID}))["status"] == "active"


@pytest.mark.asyncio
@pytest.mark.parametrize("fid,args,path", NEW_CALLS)
async def test_new_functions_map_403_without_access_to_access_denied(db, fid, args, path):
    t, _ = api({path: httpx.Response(403, json=NO_ACCESS_BODY)})
    assert (await run(fid, args, db, t)).error.code == ErrorCode.access_denied


@pytest.mark.asyncio
@pytest.mark.parametrize("fid,args,path", NEW_CALLS)
async def test_new_functions_map_404_to_not_found(db, fid, args, path):
    t, _ = api({path: httpx.Response(404, json={"error": {"code": 404, "status": "NOT_FOUND"}})})
    assert (await run(fid, args, db, t)).error.code == ErrorCode.not_found


@pytest.mark.asyncio
@pytest.mark.parametrize("fid,args,path", NEW_CALLS)
async def test_new_functions_map_429_to_rate_limited_after_one_retry(db, fid, args, path, _no_retry_delay):
    t, seen = api({path: httpx.Response(429, json={"error": {"code": 429, "status": "RESOURCE_EXHAUSTED"}})})
    res = await run(fid, args, db, t)
    assert res.error.code == ErrorCode.rate_limited and res.error.retryable and len(seen) == 2
