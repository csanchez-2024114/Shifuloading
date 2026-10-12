"""Google Drive: pruebas simuladas (httpx.MockTransport) de la conexion y las 7 funciones."""
import json

import httpx
import pytest
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient

from app.core.constants import Collections
from app.functions.apps.google_drive.functions import extract_file_id
from app.functions.errors import FunctionError
from app.functions.registry import get_app, get_function, load_all
from app.functions.runner import execute
from app.functions.spec import ConfirmationPolicy, ErrorCode
from functions_helpers import connection_doc, unseal

COL = Collections.USER_CONNECTED_ACCOUNTS
EMAIL = "ana@empresa.test"  # el login viejo de Google guarda el correo como account_id
FID = "1QrStUvWxYz"
FOLDER = "1AbCdEfGhIjKlMnOp"
D = "/drive/v3"
ALL_IDS = ["google_drive.about.get", "google_drive.files.list", "google_drive.files.search", "google_drive.files.get",
           "google_drive.folders.create", "google_drive.files.move", "google_drive.files.share"]


@pytest.fixture(autouse=True, scope="module")
def _registry():
    load_all()


@pytest_asyncio.fixture
async def db():
    d = AsyncMongoMockClient()["gdrive_test"]
    await d[COL].insert_one(connection_doc(account=EMAIL, provider="google_drive", token="old-token", refresh="rt-1"))
    return d


def api(routes):
    """routes: {(metodo, ruta): respuesta o funcion}; lo no listado responde 404."""
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        r = routes.get((req.method, req.url.path), httpx.Response(404))
        return r(req) if callable(r) else r

    return httpx.MockTransport(handler), seen


async def run(fid, args, db, t, **kw):
    return await execute(get_function(fid), args, db=db, user_id="u1", transport=t, **kw)


def ok(body):
    return httpx.Response(200, json=body)


ABOUT = {"user": {"permissionId": "1122", "emailAddress": EMAIL, "displayName": "Ana Perez"},
         "storageQuota": {"limit": "16106127360", "usage": "5368709120", "usageInDrive": "3221225472", "usageInDriveTrash": "104857600"}}
FILE = {"id": FID, "name": "Q3 budget", "mimeType": "application/vnd.google-apps.spreadsheet", "modifiedTime": "2026-09-30T08:30:00.000Z",
        "webViewLink": "https://docs.google.com/spreadsheets/d/1QrStUvWxYz/edit", "parents": [FOLDER]}
FILE_ITEM = {"id": FID, "name": "Q3 budget", "mime_type": "application/vnd.google-apps.spreadsheet", "modified_time": "2026-09-30T08:30:00.000Z",
             "web_view_link": "https://docs.google.com/spreadsheets/d/1QrStUvWxYz/edit", "parents": [FOLDER]}


# --- conexion y fichas ---------------------------------------------------------------------------

def test_app_spec_reuses_the_legacy_google_login():
    app = get_app("google_drive")
    assert app.provider_keys == ["google_drive"] and app.whoami == "google_drive.about.get"
    assert app.auth.authorize_url == "https://accounts.google.com/o/oauth2/v2/auth"
    assert app.auth.token_url == "https://oauth2.googleapis.com/token"
    assert app.auth.authorize_params == {"access_type": "offline", "prompt": "consent"}
    assert (app.auth.client_id_env, app.auth.client_secret_env) == ("DRIVE_CLIENT_ID", "DRIVE_CLIENT_SECRET")
    assert app.auth.scopes == ["openid", "email", "profile", "https://www.googleapis.com/auth/drive"]


def test_verbs_and_confirmation_policies():
    specs = {fid: get_function(fid).spec for fid in ALL_IDS}
    for fid in ("google_drive.about.get", "google_drive.files.list", "google_drive.files.search", "google_drive.files.get"):
        assert specs[fid].verb.value == "read" and not specs[fid].exits_outside
    assert (specs["google_drive.folders.create"].verb.value, specs["google_drive.folders.create"].exits_outside) == ("create", False)
    assert (specs["google_drive.files.move"].verb.value, specs["google_drive.files.move"].exits_outside) == ("update", False)
    assert (specs["google_drive.files.share"].verb.value, specs["google_drive.files.share"].exits_outside) == ("create", True)
    assert specs["google_drive.files.share"].confirmation_policy == ConfirmationPolicy.draft_and_confirm
    assert specs["google_drive.files.move"].confirmation_policy == ConfirmationPolicy.assume
    for s in specs.values():
        assert s.reversible and s.examples[0].output is not None
        assert set(s.scopes) <= set(get_app("google_drive").auth.scopes)


# --- about.get (whoami) --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_about_returns_identity_and_quota_and_account_id_is_the_email(db):
    t, seen = api({("GET", f"{D}/about"): ok(ABOUT)})
    res = await run("google_drive.about.get", {}, db, t)
    assert res.ok and res.data == {
        "account_id": EMAIL, "email": EMAIL, "display_name": "Ana Perez", "permission_id": "1122", "storage_limit_bytes": 16106127360,
        "storage_used_bytes": 5368709120, "storage_used_in_drive_bytes": 3221225472, "storage_used_in_trash_bytes": 104857600}
    assert res.data["account_id"] == res.meta.account_id  # coincide con la cuenta guardada por el login viejo
    assert seen[0].headers["authorization"] == "Bearer old-token" and "storageQuota" in seen[0].url.params["fields"]


@pytest.mark.asyncio
async def test_about_unlimited_storage_has_no_limit(db):
    body = {"user": {"emailAddress": EMAIL}, "storageQuota": {"usage": "10"}}
    res = await run("google_drive.about.get", {}, db, api({("GET", f"{D}/about"): ok(body)})[0])
    assert res.ok and res.data["storage_limit_bytes"] is None and res.data["storage_used_bytes"] == 10


@pytest.mark.asyncio
async def test_about_without_email_is_upstream_changed(db):
    res = await run("google_drive.about.get", {}, db, api({("GET", f"{D}/about"): ok({"user": {}})})[0])
    assert res.error.code == ErrorCode.upstream_changed


# --- files.list ----------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_defaults_to_the_root_folder(db):
    t, seen = api({("GET", f"{D}/files"): ok({"files": [FILE], "nextPageToken": "tok2"})})
    res = await run("google_drive.files.list", {}, db, t)
    assert res.ok and res.data == {"files": [FILE_ITEM], "next_page_token": "tok2"}
    q = seen[0].url.params
    assert q["q"] == "'root' in parents and trashed=false" and q["pageSize"] == "20" and q["orderBy"] == "modifiedTime desc"
    assert q["supportsAllDrives"] == "true" and q["includeItemsFromAllDrives"] == "true" and "pageToken" not in q
    assert q["fields"] == "nextPageToken,files(id,name,mimeType,modifiedTime,webViewLink,parents)"


@pytest.mark.asyncio
async def test_list_folder_by_url_and_page_token(db):
    t, seen = api({("GET", f"{D}/files"): ok({"files": []})})
    url = f"https://drive.google.com/drive/folders/{FOLDER}?usp=sharing"
    res = await run("google_drive.files.list", {"folder_id": url, "page_size": 5, "page_token": "tok2"}, db, t)
    assert res.ok and res.data == {"files": [], "next_page_token": None}
    q = seen[0].url.params
    assert q["q"] == f"'{FOLDER}' in parents and trashed=false" and q["pageSize"] == "5" and q["pageToken"] == "tok2"


@pytest.mark.asyncio
async def test_list_recent_ignores_the_folder(db):
    t, seen = api({("GET", f"{D}/files"): ok({"files": [FILE]})})
    res = await run("google_drive.files.list", {"recent": True, "folder_id": FOLDER}, db, t)
    assert res.ok and seen[0].url.params["q"] == "trashed=false"


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [{"page_size": 0}, {"page_size": 101}, {"folder_id": "bad id!"}])
async def test_list_rejects_invalid_input(db, bad):
    assert (await run("google_drive.files.list", bad, db, api({})[0])).error.code == ErrorCode.invalid_input


# --- files.search --------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_builds_q_with_name_fulltext_and_type(db):
    t, seen = api({("GET", f"{D}/files"): ok({"files": [FILE]})})
    res = await run("google_drive.files.search", {"name_contains": "budget", "text_contains": "forecast", "file_type": "spreadsheet"}, db, t)
    assert res.ok and res.data["files"] == [FILE_ITEM]
    assert seen[0].url.params["q"] == ("name contains 'budget' and fullText contains 'forecast' and "
                                       "mimeType = 'application/vnd.google-apps.spreadsheet' and trashed=false")


@pytest.mark.asyncio
async def test_search_escapes_quotes_and_backslashes(db):
    t, seen = api({("GET", f"{D}/files"): ok({"files": []})})
    await run("google_drive.files.search", {"name_contains": "Ana's \\ file' or name contains 'x"}, db, t)
    q = seen[0].url.params["q"]
    assert q == "name contains 'Ana\\'s \\\\ file\\' or name contains \\'x' and trashed=false"


@pytest.mark.asyncio
@pytest.mark.parametrize("friendly,mime", [("folder", "application/vnd.google-apps.folder"), ("document", "application/vnd.google-apps.document"),
                                           ("presentation", "application/vnd.google-apps.presentation"), ("pdf", "application/pdf")])
async def test_search_maps_friendly_types(db, friendly, mime):
    t, seen = api({("GET", f"{D}/files"): ok({"files": []})})
    assert (await run("google_drive.files.search", {"file_type": friendly}, db, t)).ok
    assert seen[0].url.params["q"] == f"mimeType = '{mime}' and trashed=false"


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [{}, {"name_contains": "   "}, {"file_type": "video"}, {"page_size": 500, "name_contains": "x"}])
async def test_search_rejects_invalid_input(db, bad):
    assert (await run("google_drive.files.search", bad, db, api({})[0])).error.code == ErrorCode.invalid_input


# --- files.get y extraccion de id desde una URL --------------------------------------------------

@pytest.mark.parametrize("value", [
    FID,
    f"https://docs.google.com/spreadsheets/d/{FID}/edit#gid=0",
    f"https://docs.google.com/document/d/{FID}/edit?usp=sharing",
    f"https://drive.google.com/file/d/{FID}/view?usp=drive_link",
    f"https://drive.google.com/drive/folders/{FID}",
    f"https://drive.google.com/drive/u/0/folders/{FID}?usp=sharing",
    f"https://drive.google.com/open?id={FID}",
    f"drive.google.com/uc?id={FID}&export=download",
])
def test_extract_file_id(value):
    assert extract_file_id(value) == FID


@pytest.mark.parametrize("value", ["", "   ", "has space", "a/b", "https://drive.google.com/drive/my-drive", "https://example.com/?x=1"])
def test_extract_file_id_rejects_garbage(value):
    with pytest.raises(FunctionError) as exc:
        extract_file_id(value)
    assert exc.value.code == ErrorCode.invalid_input


@pytest.mark.asyncio
async def test_get_accepts_a_url_and_returns_details(db):
    raw = {**FILE, "createdTime": "2026-07-01T09:00:00.000Z", "size": "2048", "owners": [{"emailAddress": EMAIL, "displayName": "Ana"}, {"displayName": "x"}],
           "trashed": False, "shared": True}
    t, seen = api({("GET", f"{D}/files/{FID}"): ok(raw)})
    res = await run("google_drive.files.get", {"file_id": f"https://docs.google.com/spreadsheets/d/{FID}/edit"}, db, t)
    assert res.ok and res.data == {**FILE_ITEM, "created_time": "2026-07-01T09:00:00.000Z", "size_bytes": 2048, "owners": [EMAIL], "trashed": False, "shared": True}
    assert seen[0].url.params["supportsAllDrives"] == "true" and "owners(displayName,emailAddress)" in seen[0].url.params["fields"]


@pytest.mark.asyncio
async def test_get_native_google_file_has_no_size(db):
    t, _ = api({("GET", f"{D}/files/{FID}"): ok(FILE)})
    res = await run("google_drive.files.get", {"file_id": FID}, db, t)
    assert res.ok and res.data["size_bytes"] is None and res.data["owners"] == [] and res.data["shared"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [{}, {"file_id": ""}, {"file_id": "not an id!"}])
async def test_get_rejects_invalid_input(db, bad):
    assert (await run("google_drive.files.get", bad, db, api({})[0])).error.code == ErrorCode.invalid_input


# --- folders.create ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_folder_in_a_parent(db):
    t, seen = api({("POST", f"{D}/files"): ok({"id": "NEW1", "name": "Invoices 2026", "webViewLink": "https://drive.google.com/drive/folders/NEW1", "parents": [FOLDER]})})
    res = await run("google_drive.folders.create", {"name": " Invoices 2026 ", "parent_folder_id": f"https://drive.google.com/drive/folders/{FOLDER}"}, db, t)
    assert res.ok and res.data == {"id": "NEW1", "name": "Invoices 2026", "web_view_link": "https://drive.google.com/drive/folders/NEW1", "parents": [FOLDER]}
    assert json.loads(seen[0].content) == {"name": "Invoices 2026", "mimeType": "application/vnd.google-apps.folder", "parents": [FOLDER]}
    assert seen[0].url.params["supportsAllDrives"] == "true"


@pytest.mark.asyncio
async def test_create_folder_at_the_root_sends_no_parents(db):
    t, seen = api({("POST", f"{D}/files"): ok({"id": "NEW2", "name": "Top"})})
    res = await run("google_drive.folders.create", {"name": "Top"}, db, t)
    assert res.ok and res.data["parents"] == [] and "parents" not in json.loads(seen[0].content)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [{}, {"name": ""}, {"name": "   "}, {"name": "x" * 256}])
async def test_create_folder_rejects_invalid_input(db, bad):
    assert (await run("google_drive.folders.create", bad, db, api({})[0])).error.code == ErrorCode.invalid_input


# --- files.move ----------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_move_adds_the_destination_and_removes_old_parents(db):
    def patch(req):
        return ok({**FILE, "parents": ["DEST"]})

    t, seen = api({("GET", f"{D}/files/{FID}"): ok({"parents": ["OLD1", "OLD2"]}), ("PATCH", f"{D}/files/{FID}"): patch})
    res = await run("google_drive.files.move", {"file_id": FID, "destination_folder_id": "https://drive.google.com/drive/folders/DEST"}, db, t)
    assert res.ok and res.data["parents"] == ["DEST"] and res.data["name"] == "Q3 budget"
    assert [r.method for r in seen] == ["GET", "PATCH"] and seen[0].url.params["fields"] == "parents"
    q = seen[1].url.params
    assert q["addParents"] == "DEST" and q["removeParents"] == "OLD1,OLD2" and q["supportsAllDrives"] == "true"


@pytest.mark.asyncio
async def test_move_when_already_in_the_destination_does_not_remove_it(db):
    t, seen = api({("GET", f"{D}/files/{FID}"): ok({"parents": ["DEST", "OTHER"]}), ("PATCH", f"{D}/files/{FID}"): ok({**FILE, "parents": ["DEST"]})})
    assert (await run("google_drive.files.move", {"file_id": FID, "destination_folder_id": "DEST"}, db, t)).ok
    q = seen[1].url.params
    assert "addParents" not in q and q["removeParents"] == "OTHER"


@pytest.mark.asyncio
async def test_move_a_file_without_parents_only_adds(db):
    t, seen = api({("GET", f"{D}/files/{FID}"): ok({}), ("PATCH", f"{D}/files/{FID}"): ok({**FILE, "parents": ["root"]})})
    assert (await run("google_drive.files.move", {"file_id": FID, "destination_folder_id": "root"}, db, t)).ok
    q = seen[1].url.params
    assert q["addParents"] == "root" and "removeParents" not in q


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [{}, {"file_id": FID}, {"file_id": FID, "destination_folder_id": FID}, {"file_id": "bad id!", "destination_folder_id": "D"}])
async def test_move_rejects_invalid_input(db, bad):
    assert (await run("google_drive.files.move", bad, db, api({})[0])).error.code == ErrorCode.invalid_input


@pytest.mark.asyncio
async def test_move_missing_file_is_not_found(db):
    assert (await run("google_drive.files.move", {"file_id": FID, "destination_folder_id": "D"}, db, api({})[0])).error.code == ErrorCode.not_found


# --- files.share ---------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_share_creates_a_user_permission_and_notifies(db):
    t, seen = api({("POST", f"{D}/files/{FID}/permissions"): ok({"id": "perm1", "type": "user", "role": "writer", "emailAddress": "luis@empresa.test"})})
    res = await run("google_drive.files.share", {"file_id": f"https://drive.google.com/file/d/{FID}/view", "email": "luis@empresa.test",
                                                 "role": "writer", "message": "Take a look"}, db, t)
    assert res.ok and res.data == {"permission_id": "perm1", "file_id": FID, "email": "luis@empresa.test", "role": "writer", "notification_sent": True}
    assert json.loads(seen[0].content) == {"type": "user", "role": "writer", "emailAddress": "luis@empresa.test"}
    q = seen[0].url.params
    assert q["sendNotificationEmail"] == "true" and q["emailMessage"] == "Take a look" and q["supportsAllDrives"] == "true"


@pytest.mark.asyncio
async def test_share_silently_defaults_to_reader_and_drops_the_message(db):
    t, seen = api({("POST", f"{D}/files/{FID}/permissions"): ok({"id": "perm2", "role": "reader"})})
    res = await run("google_drive.files.share", {"file_id": FID, "email": "luis@empresa.test", "send_notification_email": False, "message": "ignored"}, db, t)
    assert res.ok and res.data["role"] == "reader" and res.data["notification_sent"] is False
    q = seen[0].url.params
    assert q["sendNotificationEmail"] == "false" and "emailMessage" not in q
    assert json.loads(seen[0].content)["role"] == "reader"


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [{}, {"file_id": FID}, {"file_id": FID, "email": "not-an-email"}, {"file_id": FID, "email": "a@b.co", "role": "owner"},
                                 {"file_id": FID, "email": "a@b.co", "role": "anyone"}])
async def test_share_rejects_invalid_input(db, bad):
    assert (await run("google_drive.files.share", bad, db, api({})[0])).error.code == ErrorCode.invalid_input


# --- errores de la app ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_401_without_refresh_is_auth_expired_and_marks_the_account(db):
    t, _ = api({("GET", f"{D}/about"): httpx.Response(401, json={"error": {"status": "UNAUTHENTICATED"}})})
    res = await run("google_drive.about.get", {}, db, t)
    assert res.error.code == ErrorCode.auth_expired and res.error.user_action == "reconnect_app"
    assert (await db[COL].find_one({"account_id": EMAIL}))["status"] != "active"


@pytest.mark.asyncio
async def test_expired_token_is_refreshed_with_the_drive_client_and_retried(db, monkeypatch):
    monkeypatch.setenv("DRIVE_CLIENT_ID", "cid")
    monkeypatch.setenv("DRIVE_CLIENT_SECRET", "csecret")

    def about(req):
        return ok(ABOUT) if req.headers["authorization"] == "Bearer fresh-token" else httpx.Response(401, json={})

    t, seen = api({("GET", f"{D}/about"): about, ("POST", "/token"): ok({"access_token": "fresh-token", "expires_in": 3600})})
    res = await run("google_drive.about.get", {}, db, t)
    assert res.ok and seen[1].url.host == "oauth2.googleapis.com"
    doc = await db[COL].find_one({"account_id": EMAIL})
    assert unseal(doc["credentials_enc"]) == {"token": "fresh-token", "refresh_token": "rt-1"}


@pytest.mark.asyncio
async def test_403_no_access_to_the_file_is_access_denied_and_does_not_expire_the_account(db):
    body = {"error": {"code": 403, "message": "insufficient permissions", "errors": [{"reason": "insufficientFilePermissions"}], "status": "PERMISSION_DENIED"}}
    t, _ = api({("GET", f"{D}/files/{FID}"): httpx.Response(403, json=body)})
    res = await run("google_drive.files.get", {"file_id": FID}, db, t)
    assert res.error.code == ErrorCode.access_denied and res.error.user_action == "request_access"
    assert (await db[COL].find_one({"account_id": EMAIL}))["status"] == "active"


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["rateLimitExceeded", "userRateLimitExceeded", "sharingRateLimitExceeded"])
async def test_403_rate_limit_reasons_are_rate_limited(db, reason):
    body = {"error": {"code": 403, "errors": [{"reason": reason}], "status": "RESOURCE_EXHAUSTED"}}
    t, _ = api({("GET", f"{D}/files"): httpx.Response(403, json=body)})
    res = await run("google_drive.files.list", {}, db, t)
    assert res.error.code == ErrorCode.rate_limited and res.error.retryable


@pytest.mark.asyncio
async def test_403_with_a_non_json_body_is_still_missing_scope(db):
    t, _ = api({("GET", f"{D}/files"): httpx.Response(403, text="Forbidden")})
    assert (await run("google_drive.files.list", {}, db, t)).error.code == ErrorCode.missing_scope


@pytest.mark.asyncio
async def test_404_is_not_found(db):
    t, _ = api({("GET", f"{D}/files/{FID}"): httpx.Response(404, json={"error": {"code": 404, "message": "File not found"}})})
    res = await run("google_drive.files.get", {"file_id": FID}, db, t)
    assert res.error.code == ErrorCode.not_found and res.error.user_action == "fix_input"


@pytest.mark.asyncio
async def test_429_is_rate_limited_after_one_retry(db, monkeypatch):
    monkeypatch.setattr("app.functions.connections.RETRY_DELAY_SECONDS", 0)
    t, seen = api({("GET", f"{D}/files"): httpx.Response(429, json={"error": {"code": 429}})})
    res = await run("google_drive.files.search", {"name_contains": "x"}, db, t)
    assert res.error.code == ErrorCode.rate_limited and len(seen) == 2


@pytest.mark.asyncio
async def test_400_bad_query_is_invalid_input(db):
    t, _ = api({("GET", f"{D}/files"): httpx.Response(400, json={"error": {"code": 400, "message": "Invalid Value"}})})
    assert (await run("google_drive.files.search", {"name_contains": "x"}, db, t)).error.code == ErrorCode.invalid_input


@pytest.mark.asyncio
async def test_non_json_success_is_upstream_changed(db):
    t, _ = api({("GET", f"{D}/files"): httpx.Response(200, text="<html>")})
    assert (await run("google_drive.files.list", {}, db, t)).error.code == ErrorCode.upstream_changed


# --- funciones agregadas despues: files.rename y files.copy --------------------------------------

NEW_IDS = ["google_drive.files.rename", "google_drive.files.copy"]


def test_marks_policy_and_scopes_of_the_added_functions():
    rename, copy = get_function("google_drive.files.rename").spec, get_function("google_drive.files.copy").spec
    assert (rename.verb.value, rename.exits_outside, rename.reversible, rename.confirmation_policy) == ("update", False, True, ConfirmationPolicy.assume)
    assert (copy.verb.value, copy.exits_outside, copy.reversible, copy.confirmation_policy) == ("create", False, True, ConfirmationPolicy.assume)
    for s in (rename, copy):
        assert s.version == 1 and s.scopes == ["https://www.googleapis.com/auth/drive"] and set(s.scopes) <= set(get_app("google_drive").auth.scopes)  # ningun scope nuevo
        assert s.examples[0].output is not None and "account_id" not in s.input_schema.get("properties", {})


# files.rename

@pytest.mark.asyncio
async def test_rename_patches_only_the_name_and_returns_the_item(db):
    renamed = {**FILE, "name": "Q3 budget (final)"}
    t, seen = api({("PATCH", f"{D}/files/{FID}"): ok(renamed)})
    res = await run("google_drive.files.rename", {"file_id": f"https://docs.google.com/spreadsheets/d/{FID}/edit", "new_name": "  Q3 budget (final) "}, db, t)
    assert res.ok and res.data == {**FILE_ITEM, "name": "Q3 budget (final)"}
    assert len(seen) == 1 and seen[0].method == "PATCH" and json.loads(seen[0].content) == {"name": "Q3 budget (final)"}
    q = seen[0].url.params
    assert q["supportsAllDrives"] == "true" and q["fields"] == "id,name,mimeType,modifiedTime,webViewLink,parents" and "addParents" not in q


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [{}, {"file_id": FID}, {"file_id": FID, "new_name": ""}, {"file_id": FID, "new_name": "   "},
                                 {"file_id": FID, "new_name": "x" * 256}, {"file_id": "bad id!", "new_name": "ok"}])
async def test_rename_rejects_invalid_input_without_calling_drive(db, bad):
    t, seen = api({})
    assert (await run("google_drive.files.rename", bad, db, t)).error.code == ErrorCode.invalid_input and not seen


@pytest.mark.asyncio
async def test_rename_unknown_file_is_not_found_and_without_id_in_answer_is_upstream_changed(db):
    assert (await run("google_drive.files.rename", {"file_id": FID, "new_name": "x"}, db, api({})[0])).error.code == ErrorCode.not_found
    t, _ = api({("PATCH", f"{D}/files/{FID}"): ok({})})
    assert (await run("google_drive.files.rename", {"file_id": FID, "new_name": "x"}, db, t)).error.code == ErrorCode.upstream_changed


# files.copy

COPY = {"id": "COPY1", "name": "Q4 budget", "mimeType": "application/vnd.google-apps.spreadsheet", "modifiedTime": "2026-10-10T15:00:00.000Z",
        "webViewLink": "https://docs.google.com/spreadsheets/d/COPY1/edit", "parents": ["DEST"]}


@pytest.mark.asyncio
async def test_copy_with_a_new_name_and_a_destination_folder(db):
    t, seen = api({("POST", f"{D}/files/{FID}/copy"): ok(COPY)})
    res = await run("google_drive.files.copy", {"file_id": FID, "new_name": " Q4 budget ", "destination_folder_id": "https://drive.google.com/drive/folders/DEST"}, db, t)
    assert res.ok and res.data == {"id": "COPY1", "name": "Q4 budget", "mime_type": "application/vnd.google-apps.spreadsheet", "modified_time": "2026-10-10T15:00:00.000Z",
                                   "web_view_link": "https://docs.google.com/spreadsheets/d/COPY1/edit", "parents": ["DEST"]}
    assert len(seen) == 1 and seen[0].method == "POST" and json.loads(seen[0].content) == {"name": "Q4 budget", "parents": ["DEST"]}
    q = seen[0].url.params
    assert q["supportsAllDrives"] == "true" and q["fields"] == "id,name,mimeType,modifiedTime,webViewLink,parents"


@pytest.mark.asyncio
async def test_copy_without_name_or_destination_sends_an_empty_body_so_drive_keeps_the_folder(db):
    t, seen = api({("POST", f"{D}/files/{FID}/copy"): ok({**COPY, "name": "Copy of Q3 budget", "parents": [FOLDER]})})
    res = await run("google_drive.files.copy", {"file_id": FID}, db, t)
    assert res.ok and res.data["name"] == "Copy of Q3 budget" and res.data["parents"] == [FOLDER]
    assert json.loads(seen[0].content) == {}  # ni name ni parents: Drive pone "Copy of ..." junto al original


@pytest.mark.asyncio
async def test_copy_to_root_and_blank_destination_is_ignored(db):
    t, seen = api({("POST", f"{D}/files/{FID}/copy"): ok(COPY)})
    assert (await run("google_drive.files.copy", {"file_id": FID, "destination_folder_id": "root"}, db, t)).ok
    assert (await run("google_drive.files.copy", {"file_id": FID, "destination_folder_id": "   "}, db, t)).ok
    assert [json.loads(r.content) for r in seen] == [{"parents": ["root"]}, {}]


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [{}, {"file_id": ""}, {"file_id": FID, "new_name": "   "}, {"file_id": FID, "new_name": "x" * 256},
                                 {"file_id": FID, "destination_folder_id": "bad id!"}, {"file_id": "bad id!"}])
async def test_copy_rejects_invalid_input_without_calling_drive(db, bad):
    t, seen = api({})
    assert (await run("google_drive.files.copy", bad, db, t)).error.code == ErrorCode.invalid_input and not seen


@pytest.mark.asyncio
async def test_copy_without_id_in_answer_is_upstream_changed(db):
    t, _ = api({("POST", f"{D}/files/{FID}/copy"): ok({})})
    assert (await run("google_drive.files.copy", {"file_id": FID}, db, t)).error.code == ErrorCode.upstream_changed


# errores de la API en las funciones agregadas

@pytest.mark.asyncio
@pytest.mark.parametrize("fid", NEW_IDS)
async def test_added_functions_map_api_errors_to_contract_codes(fid, db, monkeypatch):
    monkeypatch.setattr("app.functions.connections.RETRY_DELAY_SECONDS", 0)
    example = get_function(fid).spec.examples[0].input
    cases = ((404, {"error": {"code": 404}}, ErrorCode.not_found), (429, {"error": {"code": 429}}, ErrorCode.rate_limited),
             (500, {"error": {"code": 500}}, ErrorCode.upstream_down), (400, {"error": {"code": 400}}, ErrorCode.invalid_input),
             (403, {"error": {"code": 403, "errors": [{"reason": "insufficientFilePermissions"}]}}, ErrorCode.access_denied),
             (403, {"error": {"code": 403, "message": "Request had insufficient authentication scopes."}}, ErrorCode.missing_scope),
             (403, {"error": {"code": 403, "errors": [{"reason": "userRateLimitExceeded"}]}}, ErrorCode.rate_limited))
    for status, body, code in cases:
        resp = httpx.Response(status, json=body)
        t = httpx.MockTransport(lambda req, resp=resp: resp)
        res = await run(fid, example, db, t)
        assert not res.ok and res.error.code == code, (fid, status, res.error)
    assert (await db[COL].find_one({"account_id": EMAIL}))["status"] == "active"
