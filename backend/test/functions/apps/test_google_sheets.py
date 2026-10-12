"""Google Sheets: pruebas simuladas (httpx.MockTransport) de la conexion, la whoami y las 7 funciones."""
import json

import httpx
import pytest
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient

from app.core.constants import Collections
from app.functions import connections
from app.functions.registry import get_app, get_function, load_all
from app.functions.runner import execute
from app.functions.spec import ErrorCode
from functions_helpers import connection_doc, unseal

COL = Collections.USER_CONNECTED_ACCOUNTS
EMAIL = "ana@empresa.test"
SID = "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
BASE = f"/v4/spreadsheets/{SID}"
ALL_IDS = ["google_sheets.account.get", "google_sheets.spreadsheets.get", "google_sheets.values.get", "google_sheets.values.append",
           "google_sheets.values.update", "google_sheets.spreadsheets.create", "google_sheets.sheets.add"]


@pytest.fixture(autouse=True, scope="module")
def _registry():
    load_all()


@pytest.fixture(autouse=True)
def _no_retry_delay(monkeypatch):
    monkeypatch.setattr(connections, "RETRY_DELAY_SECONDS", 0)


@pytest_asyncio.fixture
async def db():
    d = AsyncMongoMockClient()["gsheets_test"]
    await d[COL].insert_one(connection_doc(account=EMAIL, provider="google_sheets", token="old-token", refresh="rt-1"))
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


TABS = {"sheets": [{"properties": {"title": "Q3 2026"}}, {"properties": {"title": "Other"}}]}
META = {"spreadsheetId": SID, "spreadsheetUrl": f"https://docs.google.com/spreadsheets/d/{SID}/edit",
        "properties": {"title": "Sales 2026", "locale": "en_US", "timeZone": "America/Mexico_City"},
        "sheets": [{"properties": {"sheetId": 0, "title": "Q3 2026", "index": 0, "sheetType": "GRID", "gridProperties": {"rowCount": 1000, "columnCount": 26}}},
                   {"properties": {"sheetId": 55, "title": "Old", "index": 1, "hidden": True, "gridProperties": {"rowCount": 10, "columnCount": 4}}}]}


# --- conexion y whoami ----------------------------------------------------------------------------

def test_app_spec_reuses_the_legacy_google_login():
    app = get_app("google_sheets")
    assert app.whoami == "google_sheets.account.get" and app.provider_keys == ["google_sheets"]
    assert app.auth.authorize_params == {"access_type": "offline", "prompt": "consent"}
    assert (app.auth.client_id_env, app.auth.client_secret_env) == ("DRIVE_CLIENT_ID", "DRIVE_CLIENT_SECRET")
    assert app.auth.authorize_url == "https://accounts.google.com/o/oauth2/v2/auth" and app.auth.token_url == "https://oauth2.googleapis.com/token"
    assert app.auth.scopes == ["openid", "email", "profile", "https://www.googleapis.com/auth/spreadsheets"]


@pytest.mark.asyncio
async def test_whoami_returns_the_email_as_account_id(db):
    t, seen = api({"/v1/userinfo": ok({"sub": "1122", "name": "Ana Perez", "email": EMAIL, "email_verified": True})})
    res = await run("google_sheets.account.get", {}, db, t)
    assert res.ok and res.data == {"account_id": EMAIL, "email": EMAIL, "name": "Ana Perez", "google_user_id": "1122"}
    assert res.data["account_id"] == res.meta.account_id
    assert seen[0].url.host == "openidconnect.googleapis.com" and seen[0].headers["authorization"] == "Bearer old-token"


@pytest.mark.asyncio
async def test_whoami_without_email_is_upstream_changed(db):
    t, _ = api({"/v1/userinfo": ok({"sub": "1122"})})
    assert (await run("google_sheets.account.get", {}, db, t)).error.code == ErrorCode.upstream_changed


@pytest.mark.asyncio
async def test_expired_token_is_refreshed_with_the_drive_client_and_retried(db, monkeypatch):
    monkeypatch.setenv("DRIVE_CLIENT_ID", "cid")
    monkeypatch.setenv("DRIVE_CLIENT_SECRET", "csecret")

    def userinfo(req):
        if req.headers["authorization"] == "Bearer fresh-token":
            return ok({"email": EMAIL})
        return httpx.Response(401, json={"error": {"status": "UNAUTHENTICATED"}})

    t, seen = api({"/v1/userinfo": userinfo, "/token": ok({"access_token": "fresh-token", "expires_in": 3600})})
    res = await run("google_sheets.account.get", {}, db, t)
    assert res.ok and [r.url.path for r in seen] == ["/v1/userinfo", "/token", "/v1/userinfo"] and seen[1].url.host == "oauth2.googleapis.com"
    assert unseal((await db[COL].find_one({"account_id": EMAIL}))["credentials_enc"]) == {"token": "fresh-token", "refresh_token": "rt-1"}


@pytest.mark.asyncio
async def test_401_without_a_working_refresh_expires_the_account(db, monkeypatch):
    monkeypatch.delenv("DRIVE_CLIENT_ID", raising=False)
    monkeypatch.delenv("DRIVE_CLIENT_SECRET", raising=False)
    t, _ = api({BASE: httpx.Response(401, json={"error": {"status": "UNAUTHENTICATED"}})})
    res = await run("google_sheets.spreadsheets.get", {"spreadsheet_id": SID}, db, t)
    assert res.error.code == ErrorCode.auth_expired and res.error.user_action == "reconnect_app"
    assert (await db[COL].find_one({"account_id": EMAIL}))["status"] != "active"


# --- errores de la API (mismos en todas las funciones de hoja) -------------------------------------

@pytest.mark.parametrize("status,code", [(403, ErrorCode.missing_scope), (404, ErrorCode.not_found), (429, ErrorCode.rate_limited),
                                         (400, ErrorCode.invalid_input), (503, ErrorCode.upstream_down)])
@pytest.mark.asyncio
async def test_api_errors_map_to_contract_codes(db, status, code):
    t, _ = api({BASE: httpx.Response(status, json={"error": {"message": "x"}})})
    res = await run("google_sheets.spreadsheets.get", {"spreadsheet_id": SID}, db, t)
    assert res.error.code == code


@pytest.mark.asyncio
async def test_403_does_not_expire_the_account(db):
    t, _ = api({BASE: httpx.Response(403, json={"error": {"status": "PERMISSION_DENIED"}})})
    assert (await run("google_sheets.spreadsheets.get", {"spreadsheet_id": SID}, db, t)).error.code == ErrorCode.missing_scope
    assert (await db[COL].find_one({"account_id": EMAIL}))["status"] == "active"


@pytest.mark.asyncio
async def test_non_json_answer_is_upstream_changed(db):
    t, _ = api({BASE: httpx.Response(200, text="<html>")})
    assert (await run("google_sheets.spreadsheets.get", {"spreadsheet_id": SID}, db, t)).error.code == ErrorCode.upstream_changed


# --- id desde URL ---------------------------------------------------------------------------------

@pytest.mark.parametrize("raw", [
    SID,
    f"  {SID}  ",
    f"https://docs.google.com/spreadsheets/d/{SID}/edit#gid=0",
    f"https://docs.google.com/spreadsheets/d/{SID}/edit?usp=sharing",
    f"https://docs.google.com/spreadsheets/u/0/d/{SID}/edit",
    f"docs.google.com/spreadsheets/d/{SID}",
])
@pytest.mark.asyncio
async def test_spreadsheet_id_is_extracted_from_a_url(db, raw):
    t, seen = api({BASE: ok(META)})
    res = await run("google_sheets.spreadsheets.get", {"spreadsheet_id": raw}, db, t)
    assert res.ok and seen[0].url.path == BASE


@pytest.mark.parametrize("bad", ["", "   ", "not an id", "https://example.com/foo", "a/b", "id?x=1"])
@pytest.mark.parametrize("fid,extra", [("google_sheets.spreadsheets.get", {}), ("google_sheets.values.get", {}),
                                       ("google_sheets.values.append", {"values": [["a"]]}),
                                       ("google_sheets.values.update", {"range": "A1", "values": [["a"]]}),
                                       ("google_sheets.sheets.add", {"title": "T"})])
@pytest.mark.asyncio
async def test_invalid_spreadsheet_id_is_invalid_input(db, fid, extra, bad):
    t, seen = api({})
    res = await run(fid, {"spreadsheet_id": bad, **extra}, db, t)
    assert res.error.code == ErrorCode.invalid_input and not seen


# --- spreadsheets.get ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_spreadsheets_get_returns_title_and_tabs_without_grid_data(db):
    t, seen = api({BASE: ok(META)})
    res = await run("google_sheets.spreadsheets.get", {"spreadsheet_id": SID}, db, t)
    assert res.ok and res.data["title"] == "Sales 2026" and res.data["locale"] == "en_US" and res.data["time_zone"] == "America/Mexico_City"
    assert res.data["sheets"] == [
        {"sheet_id": 0, "title": "Q3 2026", "index": 0, "row_count": 1000, "column_count": 26, "hidden": False},
        {"sheet_id": 55, "title": "Old", "index": 1, "row_count": 10, "column_count": 4, "hidden": True}]
    q = seen[0].url.params
    assert "includeGridData" not in q and "sheets.properties(" in q["fields"]


@pytest.mark.asyncio
async def test_spreadsheets_get_without_title_is_upstream_changed(db):
    t, _ = api({BASE: ok({"spreadsheetId": SID})})
    assert (await run("google_sheets.spreadsheets.get", {"spreadsheet_id": SID}, db, t)).error.code == ErrorCode.upstream_changed


# --- values.get ------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_values_get_splits_header_and_rows_and_keeps_ragged_rows(db):
    body = {"range": "Q3!A1:C3", "majorDimension": "ROWS", "values": [["Client", "Amount", "Date"], ["Acme", "$1,200.00", "2026-07-03"], ["Globex"], [None, 5]]}
    t, seen = api({f"{BASE}/values/Q3!A1:C3": ok(body)})
    res = await run("google_sheets.values.get", {"spreadsheet_id": SID, "range": "Q3!A1:C3"}, db, t)
    assert res.ok and res.data == {
        "spreadsheet_id": SID, "range": "Q3!A1:C3", "header": ["Client", "Amount", "Date"],
        "rows": [["Acme", "$1,200.00", "2026-07-03"], ["Globex"], ["", "5"]], "returned_rows": 3, "truncated": False}
    q = seen[0].url.params
    assert q["valueRenderOption"] == "FORMATTED_VALUE" and q["majorDimension"] == "ROWS"
    assert b"Q3%21A1%3AC3" in seen[0].url.raw_path  # el rango va codificado en la ruta


@pytest.mark.asyncio
async def test_values_get_without_range_reads_the_first_tab_quoted_and_limited(db):
    def values(req):
        return ok({"range": "'Q3 2026'!A1:B2", "values": [["h1", "h2"], ["a", "b"]]})

    t, seen = api({BASE: ok(TABS), f"{BASE}/values/'Q3 2026'!1:202": values})
    res = await run("google_sheets.values.get", {"spreadsheet_id": SID}, db, t)
    assert res.ok and res.data["header"] == ["h1", "h2"] and res.data["rows"] == [["a", "b"]] and res.data["range"] == "'Q3 2026'!A1:B2"
    assert seen[0].url.params["fields"] == "sheets.properties.title"


@pytest.mark.asyncio
async def test_values_get_quotes_a_tab_title_with_an_apostrophe(db):
    t, seen = api({BASE: ok({"sheets": [{"properties": {"title": "Ana's"}}]}), f"{BASE}/values/'Ana''s'!1:202": ok({"values": []})})
    res = await run("google_sheets.values.get", {"spreadsheet_id": SID}, db, t)
    assert res.ok and len(seen) == 2


@pytest.mark.asyncio
async def test_values_get_caps_rows_at_200(db):
    rows = [["h"]] + [[str(i)] for i in range(250)]
    t, _ = api({f"{BASE}/values/Big": ok({"range": "Big!A1:A251", "values": rows})})
    res = await run("google_sheets.values.get", {"spreadsheet_id": SID, "range": "Big"}, db, t)
    assert res.ok and res.data["returned_rows"] == 200 and len(res.data["rows"]) == 200 and res.data["truncated"] is True
    assert res.data["rows"][0] == ["0"] and res.data["rows"][-1] == ["199"]


@pytest.mark.asyncio
async def test_values_get_exactly_200_rows_is_not_truncated_and_empty_range_is_ok(db):
    rows = [["h"]] + [[str(i)] for i in range(200)]
    t, _ = api({f"{BASE}/values/A": ok({"values": rows}), f"{BASE}/values/B": ok({"range": "B!A1:A1"})})
    res = await run("google_sheets.values.get", {"spreadsheet_id": SID, "range": "A"}, db, t)
    assert res.data["returned_rows"] == 200 and res.data["truncated"] is False
    empty = await run("google_sheets.values.get", {"spreadsheet_id": SID, "range": "B"}, db, t)
    assert empty.ok and empty.data["header"] == [] and empty.data["rows"] == [] and empty.data["returned_rows"] == 0


@pytest.mark.asyncio
async def test_values_get_bad_range_is_invalid_input(db):
    t, _ = api({f"{BASE}/values/Nope!ZZ": httpx.Response(400, json={"error": {"message": "Unable to parse range: Nope!ZZ"}})})
    assert (await run("google_sheets.values.get", {"spreadsheet_id": SID, "range": "Nope!ZZ"}, db, t)).error.code == ErrorCode.invalid_input


# --- values.append ---------------------------------------------------------------------------------

APPEND_OK = {"spreadsheetId": SID, "tableRange": "Q3!A1:C3", "updates": {
    "spreadsheetId": SID, "updatedRange": "Q3!A4:C4", "updatedRows": 1, "updatedColumns": 3, "updatedCells": 3}}


@pytest.mark.asyncio
async def test_values_append_sends_rows_as_user_entered_and_inserts_them(db):
    t, seen = api({f"{BASE}/values/Q3:append": ok(APPEND_OK)})
    res = await run("google_sheets.values.append", {"spreadsheet_id": SID, "range": "Q3", "values": [["Initech", 450, True, None]]}, db, t)
    assert res.ok and res.data == {"spreadsheet_id": SID, "updated_range": "Q3!A4:C4", "updated_rows": 1, "updated_columns": 3, "updated_cells": 3}
    req = seen[0]
    assert req.method == "POST" and req.url.params["valueInputOption"] == "USER_ENTERED" and req.url.params["insertDataOption"] == "INSERT_ROWS"
    assert json.loads(req.content) == {"majorDimension": "ROWS", "values": [["Initech", 450, True, None]]}
    assert req.url.raw_path.split(b"?")[0].endswith(b"/values/Q3:append")


@pytest.mark.asyncio
async def test_values_append_without_range_uses_the_first_tab(db):
    t, seen = api({BASE: ok(TABS), f"{BASE}/values/'Q3 2026':append": ok(APPEND_OK)})
    res = await run("google_sheets.values.append", {"spreadsheet_id": SID, "values": [["x"]]}, db, t)
    assert res.ok and [r.method for r in seen] == ["GET", "POST"]


@pytest.mark.asyncio
async def test_values_append_without_updates_is_upstream_changed(db):
    t, _ = api({f"{BASE}/values/Q3:append": ok({"spreadsheetId": SID})})
    assert (await run("google_sheets.values.append", {"spreadsheet_id": SID, "range": "Q3", "values": [["x"]]}, db, t)).error.code == ErrorCode.upstream_changed


@pytest.mark.parametrize("values", [[], [[]] * 501, [["x"] * 201], "abc", [["a", {"k": 1}]]])
@pytest.mark.asyncio
async def test_values_append_rejects_invalid_values(db, values):
    t, seen = api({})
    res = await run("google_sheets.values.append", {"spreadsheet_id": SID, "values": values}, db, t)
    assert res.error.code == ErrorCode.invalid_input and not seen


@pytest.mark.asyncio
async def test_values_append_accepts_the_maximum_size(db):
    t, seen = api({f"{BASE}/values/Q3:append": ok(APPEND_OK)})
    res = await run("google_sheets.values.append", {"spreadsheet_id": SID, "range": "Q3", "values": [["x"] * 200] * 500}, db, t)
    assert res.ok and len(json.loads(seen[0].content)["values"]) == 500


# --- values.update ---------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_values_update_puts_the_range_and_values(db):
    out = {"spreadsheetId": SID, "updatedRange": "Q3!B2:B3", "updatedRows": 2, "updatedColumns": 1, "updatedCells": 2}
    t, seen = api({f"{BASE}/values/Q3!B2:B3": ok(out)})
    res = await run("google_sheets.values.update", {"spreadsheet_id": SID, "range": "Q3!B2:B3", "values": [[1300], [""]]}, db, t)
    assert res.ok and res.data == {"spreadsheet_id": SID, "updated_range": "Q3!B2:B3", "updated_rows": 2, "updated_columns": 1, "updated_cells": 2}
    req = seen[0]
    assert req.method == "PUT" and req.url.params["valueInputOption"] == "USER_ENTERED"
    assert json.loads(req.content) == {"range": "Q3!B2:B3", "majorDimension": "ROWS", "values": [[1300], [""]]}


@pytest.mark.asyncio
async def test_values_update_requires_a_range_and_values(db):
    t, seen = api({})
    for bad in ({"values": [["a"]]}, {"range": "", "values": [["a"]]}, {"range": "A1"}, {"range": "A1", "values": []}):
        assert (await run("google_sheets.values.update", {"spreadsheet_id": SID, **bad}, db, t)).error.code == ErrorCode.invalid_input
    assert not seen


@pytest.mark.asyncio
async def test_values_update_without_range_in_answer_is_upstream_changed(db):
    t, _ = api({f"{BASE}/values/A1": ok({})})
    assert (await run("google_sheets.values.update", {"spreadsheet_id": SID, "range": "A1", "values": [["a"]]}, db, t)).error.code == ErrorCode.upstream_changed


# --- spreadsheets.create ---------------------------------------------------------------------------

CREATED = {"spreadsheetId": "NEWID123", "spreadsheetUrl": "https://docs.google.com/spreadsheets/d/NEWID123/edit", "properties": {"title": "Budget 2027"},
           "sheets": [{"properties": {"sheetId": 0, "title": "Income", "index": 0, "gridProperties": {"rowCount": 1000, "columnCount": 26}}},
                      {"properties": {"sheetId": 77, "title": "Expenses", "index": 1}}]}


@pytest.mark.asyncio
async def test_spreadsheets_create_sends_title_and_tabs(db):
    t, seen = api({"/v4/spreadsheets": ok(CREATED)})
    res = await run("google_sheets.spreadsheets.create", {"title": "Budget 2027", "sheet_titles": ["Income", "Expenses"]}, db, t)
    assert res.ok and res.data["spreadsheet_id"] == "NEWID123" and res.data["url"].endswith("/NEWID123/edit")
    assert [s["title"] for s in res.data["sheets"]] == ["Income", "Expenses"]
    assert seen[0].method == "POST" and json.loads(seen[0].content) == {
        "properties": {"title": "Budget 2027"}, "sheets": [{"properties": {"title": "Income"}}, {"properties": {"title": "Expenses"}}]}


@pytest.mark.asyncio
async def test_spreadsheets_create_with_only_a_title_leaves_tabs_to_google(db):
    t, seen = api({"/v4/spreadsheets": ok({**CREATED, "sheets": [CREATED["sheets"][0]]})})
    assert (await run("google_sheets.spreadsheets.create", {"title": "Budget 2027"}, db, t)).ok
    assert json.loads(seen[0].content) == {"properties": {"title": "Budget 2027"}}


@pytest.mark.parametrize("bad", [{}, {"title": ""}, {"title": "x" * 256}, {"title": "T", "sheet_titles": ["A", "a"]}, {"title": "T", "sheet_titles": [" "]}])
@pytest.mark.asyncio
async def test_spreadsheets_create_rejects_invalid_input(db, bad):
    t, seen = api({})
    assert (await run("google_sheets.spreadsheets.create", bad, db, t)).error.code == ErrorCode.invalid_input and not seen


@pytest.mark.asyncio
async def test_spreadsheets_create_without_id_is_upstream_changed(db):
    t, _ = api({"/v4/spreadsheets": ok({})})
    assert (await run("google_sheets.spreadsheets.create", {"title": "T"}, db, t)).error.code == ErrorCode.upstream_changed


# --- sheets.add ------------------------------------------------------------------------------------

ADDED = {"spreadsheetId": SID, "replies": [{"addSheet": {"properties": {
    "sheetId": 987, "title": "Q4 2026", "index": 1, "sheetType": "GRID", "gridProperties": {"rowCount": 1000, "columnCount": 26}}}}]}


@pytest.mark.asyncio
async def test_sheets_add_uses_batch_update_add_sheet(db):
    t, seen = api({f"{BASE}:batchUpdate": ok(ADDED)})
    res = await run("google_sheets.sheets.add", {"spreadsheet_id": SID, "title": " Q4 2026 "}, db, t)
    assert res.ok and res.data == {"spreadsheet_id": SID, "sheet": {"sheet_id": 987, "title": "Q4 2026", "index": 1, "row_count": 1000, "column_count": 26, "hidden": False}}
    assert seen[0].method == "POST" and json.loads(seen[0].content) == {
        "requests": [{"addSheet": {"properties": {"title": "Q4 2026"}}}], "includeSpreadsheetInResponse": False}


@pytest.mark.asyncio
async def test_sheets_add_sends_the_grid_size(db):
    t, seen = api({f"{BASE}:batchUpdate": ok(ADDED)})
    assert (await run("google_sheets.sheets.add", {"spreadsheet_id": SID, "title": "T", "rows": 50, "columns": 5}, db, t)).ok
    assert json.loads(seen[0].content)["requests"][0]["addSheet"]["properties"] == {"title": "T", "gridProperties": {"rowCount": 50, "columnCount": 5}}


@pytest.mark.asyncio
async def test_sheets_add_duplicate_title_is_invalid_input(db):
    err = httpx.Response(400, json={"error": {"code": 400, "message": "Invalid requests[0].addSheet: A sheet with the name \"Q4 2026\" already exists."}})
    t, _ = api({f"{BASE}:batchUpdate": err})
    assert (await run("google_sheets.sheets.add", {"spreadsheet_id": SID, "title": "Q4 2026"}, db, t)).error.code == ErrorCode.invalid_input


@pytest.mark.parametrize("bad", [{}, {"title": ""}, {"title": "T", "rows": 0}, {"title": "T", "columns": 703}])
@pytest.mark.asyncio
async def test_sheets_add_rejects_invalid_input(db, bad):
    t, seen = api({})
    assert (await run("google_sheets.sheets.add", {"spreadsheet_id": SID, **bad}, db, t)).error.code == ErrorCode.invalid_input and not seen


@pytest.mark.asyncio
async def test_sheets_add_without_reply_is_upstream_changed(db):
    t, _ = api({f"{BASE}:batchUpdate": ok({"replies": [{}]})})
    assert (await run("google_sheets.sheets.add", {"spreadsheet_id": SID, "title": "T"}, db, t)).error.code == ErrorCode.upstream_changed


# --- fichas ----------------------------------------------------------------------------------------

def test_contract_marks_of_every_function():
    marks = {fid: (get_function(fid).spec.verb.value, get_function(fid).spec.exits_outside, get_function(fid).spec.reversible) for fid in ALL_IDS}
    assert marks == {
        "google_sheets.account.get": ("read", False, True), "google_sheets.spreadsheets.get": ("read", False, True),
        "google_sheets.values.get": ("read", False, True), "google_sheets.values.append": ("create", False, True),
        "google_sheets.values.update": ("update", False, False), "google_sheets.spreadsheets.create": ("create", False, True),
        "google_sheets.sheets.add": ("update", False, True)}
    policy = {fid: get_function(fid).spec.confirmation_policy.value for fid in ALL_IDS}
    assert policy["google_sheets.values.update"] == "ask" and policy["google_sheets.values.append"] == "assume"


def test_scopes_are_declared_by_the_app_and_examples_have_output():
    declared = set(get_app("google_sheets").auth.scopes)
    for fid in ALL_IDS:
        spec = get_function(fid).spec
        assert spec.scopes and set(spec.scopes) <= declared
        assert spec.examples[0].output is not None
        assert "account_id" not in spec.input_schema.get("properties", {})


@pytest.mark.asyncio
async def test_simulated_run_returns_the_example_output(db):
    res = await run("google_sheets.values.update", {"spreadsheet_id": SID, "range": "Q3!B2:B3", "values": [[1]]}, db, api({})[0], simulate=True)
    assert res.ok and res.meta.simulated and res.data == get_function("google_sheets.values.update").spec.examples[0].output


# --- funciones agregadas despues: values.clear, sheets.rename, values.find --------------------------

NEW_IDS = ["google_sheets.values.clear", "google_sheets.sheets.rename", "google_sheets.values.find"]


def test_marks_policy_and_scopes_of_the_added_functions():
    marks = {  # id -> (verbo, sale al exterior, reversible, politica)
        "google_sheets.values.clear": ("update", False, False, "ask"),     # borra valores sin vuelta atras: igual que values.update
        "google_sheets.sheets.rename": ("update", False, True, "assume"),
        "google_sheets.values.find": ("read", False, True, "assume"),
    }
    declared = set(get_app("google_sheets").auth.scopes)
    for fid, (verb, outside, reversible, policy) in marks.items():
        spec = get_function(fid).spec
        assert (spec.verb.value, spec.exits_outside, spec.reversible, spec.confirmation_policy.value) == (verb, outside, reversible, policy), fid
        assert spec.version == 1 and spec.scopes == ["https://www.googleapis.com/auth/spreadsheets"] and set(spec.scopes) <= declared, fid  # ningun scope nuevo
        assert spec.examples[0].output is not None and "account_id" not in spec.input_schema.get("properties", {}), fid


# google_sheets.values.clear

@pytest.mark.asyncio
async def test_values_clear_posts_an_empty_body_to_the_clear_endpoint(db):
    t, seen = api({f"{BASE}/values/Q3!A2:C50:clear": ok({"spreadsheetId": SID, "clearedRange": "Q3!A2:C50"})})
    res = await run("google_sheets.values.clear", {"spreadsheet_id": SID, "range": " Q3!A2:C50 "}, db, t)
    assert res.ok and res.data == {"spreadsheet_id": SID, "cleared_range": "Q3!A2:C50"}
    req = seen[0]
    assert req.method == "POST" and json.loads(req.content) == {} and len(seen) == 1
    assert req.url.raw_path.split(b"?")[0].endswith(b"/values/Q3%21A2%3AC50:clear")  # el rango va codificado y :clear va pegado


@pytest.mark.asyncio
async def test_values_clear_without_a_range_is_rejected_and_never_defaults_to_a_whole_tab(db):
    t, seen = api({})
    for bad in ({}, {"range": ""}, {"range": "   "}):
        assert (await run("google_sheets.values.clear", {"spreadsheet_id": SID, **bad}, db, t)).error.code == ErrorCode.invalid_input
    assert not seen  # ni siquiera pregunto por la primera pestana


@pytest.mark.parametrize("bad", ["Sales", "A2:D50", "Q3", "Sales!", "!A2:D50", "'  '!A1", "Sales!   "])
@pytest.mark.asyncio
async def test_values_clear_requires_both_the_tab_and_the_cells(db, bad):
    t, seen = api({})
    res = await run("google_sheets.values.clear", {"spreadsheet_id": SID, "range": bad}, db, t)
    assert res.error.code == ErrorCode.invalid_input and not seen  # rechazado antes de cualquier llamada HTTP
    assert "tab" in res.error.message and "cells" in res.error.message


@pytest.mark.parametrize("good", ["Sales!A2:D50", "'Q3 2026'!B:B", "Q3!A1"])
@pytest.mark.asyncio
async def test_values_clear_accepts_tab_and_cells(db, good):
    t, seen = api({f"{BASE}/values/{good}:clear": ok({"spreadsheetId": SID, "clearedRange": good})})
    res = await run("google_sheets.values.clear", {"spreadsheet_id": SID, "range": good}, db, t)
    assert res.ok and len(seen) == 1


@pytest.mark.asyncio
async def test_values_clear_without_cleared_range_is_upstream_changed(db):
    t, _ = api({f"{BASE}/values/Q3!A1:clear": ok({"spreadsheetId": SID})})
    assert (await run("google_sheets.values.clear", {"spreadsheet_id": SID, "range": "Q3!A1"}, db, t)).error.code == ErrorCode.upstream_changed


@pytest.mark.asyncio
async def test_values_clear_is_simulated_and_writes_nothing_when_asked(db):
    t, seen = api({})
    res = await run("google_sheets.values.clear", {"spreadsheet_id": SID, "range": "Q3!A2:C50"}, db, t, simulate=True)
    assert res.ok and res.meta.simulated and not seen


# google_sheets.sheets.rename

RENAME_META = {"sheets": [{"properties": {"sheetId": 0, "title": "Sheet1", "index": 0, "gridProperties": {"rowCount": 1000, "columnCount": 26}}},
                          {"properties": {"sheetId": 55, "title": "Old", "index": 1, "hidden": True}}]}


@pytest.mark.asyncio
async def test_sheets_rename_looks_up_the_tab_id_and_sends_update_sheet_properties(db):
    def batch(req):
        return ok({"spreadsheetId": SID, "replies": [{}]})

    t, seen = api({BASE: ok(RENAME_META), f"{BASE}:batchUpdate": batch})
    res = await run("google_sheets.sheets.rename", {"spreadsheet_id": SID, "sheet_title": " Sheet1 ", "new_title": " Sales "}, db, t)
    assert res.ok and res.data == {"spreadsheet_id": SID, "previous_title": "Sheet1", "sheet": {
        "sheet_id": 0, "title": "Sales", "index": 0, "row_count": 1000, "column_count": 26, "hidden": False}}
    assert [r.method for r in seen] == ["GET", "POST"] and "sheets.properties(" in seen[0].url.params["fields"]
    assert json.loads(seen[1].content) == {
        "requests": [{"updateSheetProperties": {"properties": {"sheetId": 0, "title": "Sales"}, "fields": "title"}}], "includeSpreadsheetInResponse": False}


@pytest.mark.asyncio
async def test_sheets_rename_matches_the_current_title_ignoring_case(db):
    t, seen = api({BASE: ok(RENAME_META), f"{BASE}:batchUpdate": ok({"replies": [{}]})})
    res = await run("google_sheets.sheets.rename", {"spreadsheet_id": SID, "sheet_title": "old", "new_title": "Archive"}, db, t)
    assert res.ok and res.data["previous_title"] == "Old" and res.data["sheet"]["hidden"] is True
    assert json.loads(seen[1].content)["requests"][0]["updateSheetProperties"]["properties"] == {"sheetId": 55, "title": "Archive"}


@pytest.mark.asyncio
async def test_sheets_rename_unknown_tab_is_not_found_and_lists_the_tabs_without_writing(db):
    t, seen = api({BASE: ok(RENAME_META)})
    res = await run("google_sheets.sheets.rename", {"spreadsheet_id": SID, "sheet_title": "Nope", "new_title": "X"}, db, t)
    assert res.error.code == ErrorCode.not_found and "'Sheet1'" in res.error.message and "'Old'" in res.error.message
    assert [r.method for r in seen] == ["GET"]  # no se llego a escribir


@pytest.mark.asyncio
async def test_sheets_rename_duplicate_new_title_is_invalid_input(db):
    err = httpx.Response(400, json={"error": {"code": 400, "message": "Invalid requests[0].updateSheetProperties: A sheet with the name \"Old\" already exists."}})
    t, _ = api({BASE: ok(RENAME_META), f"{BASE}:batchUpdate": err})
    assert (await run("google_sheets.sheets.rename", {"spreadsheet_id": SID, "sheet_title": "Sheet1", "new_title": "Old"}, db, t)).error.code == ErrorCode.invalid_input


@pytest.mark.parametrize("bad", [{}, {"sheet_title": "Sheet1"}, {"new_title": "X"}, {"sheet_title": "", "new_title": "X"}, {"sheet_title": "Sheet1", "new_title": ""},
                                 {"sheet_title": "Sheet1", "new_title": "x" * 101}, {"sheet_title": "Sheet1", "new_title": "Sheet1"}, {"sheet_title": "  ", "new_title": "X"}])
@pytest.mark.asyncio
async def test_sheets_rename_rejects_invalid_input(db, bad):
    t, _ = api({BASE: ok(RENAME_META)})
    assert (await run("google_sheets.sheets.rename", {"spreadsheet_id": SID, **bad}, db, t)).error.code == ErrorCode.invalid_input


@pytest.mark.asyncio
async def test_sheets_rename_tab_without_id_is_upstream_changed(db):
    t, _ = api({BASE: ok({"sheets": [{"properties": {"title": "Sheet1"}}]})})
    assert (await run("google_sheets.sheets.rename", {"spreadsheet_id": SID, "sheet_title": "Sheet1", "new_title": "X"}, db, t)).error.code == ErrorCode.upstream_changed


# google_sheets.values.find

FIND_VALUES = {"range": "Q3!A1:C6", "values": [
    ["Client", "Amount", "Note"],
    ["Acme", "$1,200.00", "paid"],
    ["Globex", "$980.50", "ask ACME for the invoice"],     # Acme en otra columna
    ["ACME Corp", "$50.00"],                                  # fila corta
    [],                                                      # fila vacia en medio: cuenta para el numero de fila
    ["acme ltd", "$10.00", "x"]]}


@pytest.mark.asyncio
async def test_values_find_matches_case_insensitively_in_a_column_by_header_with_row_numbers(db):
    t, seen = api({f"{BASE}/values/Q3!A1:C6": ok(FIND_VALUES)})
    res = await run("google_sheets.values.find", {"spreadsheet_id": SID, "range": "Q3!A1:C6", "text": " acme ", "column": "client"}, db, t)
    assert res.ok and res.data == {
        "spreadsheet_id": SID, "range": "Q3!A1:C6", "header": ["Client", "Amount", "Note"], "match_count": 3, "scanned_rows": 5, "truncated": False,
        "matches": [{"row_number": 2, "values": ["Acme", "$1,200.00", "paid"]}, {"row_number": 4, "values": ["ACME Corp", "$50.00"]},
                    {"row_number": 6, "values": ["acme ltd", "$10.00", "x"]}]}
    assert len(seen) == 1 and seen[0].method == "GET" and seen[0].url.params["valueRenderOption"] == "FORMATTED_VALUE"  # misma lectura que values.get


@pytest.mark.asyncio
async def test_values_find_without_column_checks_every_cell(db):
    t, _ = api({f"{BASE}/values/Q3!A1:C6": ok(FIND_VALUES)})
    res = await run("google_sheets.values.find", {"spreadsheet_id": SID, "range": "Q3!A1:C6", "text": "ACME"}, db, t)
    assert res.ok and [m["row_number"] for m in res.data["matches"]] == [2, 3, 4, 6]  # ahora tambien la nota de la fila 3


@pytest.mark.asyncio
async def test_values_find_column_by_letter_and_row_numbers_follow_the_range_start(db):
    body = {"range": "Q3!B5:D8", "values": [["Amount", "Note", "Who"], ["10", "acme", "ana"], ["20", "other", "acme"], ["30", "Acme!", "luis"]]}
    t, _ = api({f"{BASE}/values/Q3!B5:D8": ok(body)})
    res = await run("google_sheets.values.find", {"spreadsheet_id": SID, "range": "Q3!B5:D8", "text": "acme", "column": "C"}, db, t)  # C = segunda columna del rango
    assert res.ok and [(m["row_number"], m["values"][1]) for m in res.data["matches"]] == [(6, "acme"), (8, "Acme!")]


@pytest.mark.asyncio
async def test_values_find_truncates_at_max_results_and_flags_it(db):
    rows = [["h"]] + [[f"foo {i}"] for i in range(30)] + [["bar"]]
    t, _ = api({f"{BASE}/values/Big": ok({"range": "Big!A1:A32", "values": rows})})
    res = await run("google_sheets.values.find", {"spreadsheet_id": SID, "range": "Big", "text": "FOO", "max_results": 5}, db, t)
    assert res.ok and res.data["match_count"] == 5 and len(res.data["matches"]) == 5 and res.data["truncated"] is True
    assert [m["row_number"] for m in res.data["matches"]] == [2, 3, 4, 5, 6] and res.data["scanned_rows"] == 31
    exact = await run("google_sheets.values.find", {"spreadsheet_id": SID, "range": "Big", "text": "foo", "max_results": 30}, db, t)
    assert exact.data["match_count"] == 30 and exact.data["truncated"] is False  # justo en el tope: no hay recorte


@pytest.mark.asyncio
async def test_values_find_without_range_reads_the_first_5000_rows_of_the_first_tab(db):
    t, seen = api({BASE: ok(TABS), f"{BASE}/values/'Q3 2026'!1:5001": ok({"range": "'Q3 2026'!A1:B3", "values": [["k", "v"], ["a", "x"], ["b", "xx"]]})})
    res = await run("google_sheets.values.find", {"spreadsheet_id": SID, "text": "x"}, db, t)
    assert res.ok and res.data["range"] == "'Q3 2026'!A1:B3" and [m["row_number"] for m in res.data["matches"]] == [2, 3]
    assert [r.method for r in seen] == ["GET", "GET"] and seen[0].url.params["fields"] == "sheets.properties.title"


@pytest.mark.asyncio
async def test_values_find_no_matches_and_empty_range(db):
    t, _ = api({f"{BASE}/values/A": ok({"values": [["h"], ["x"]]}), f"{BASE}/values/B": ok({"range": "B!A1:A1"})})
    none = await run("google_sheets.values.find", {"spreadsheet_id": SID, "range": "A", "text": "zzz"}, db, t)
    assert none.ok and none.data["matches"] == [] and none.data["match_count"] == 0 and none.data["truncated"] is False
    empty = await run("google_sheets.values.find", {"spreadsheet_id": SID, "range": "B", "text": "zzz"}, db, t)
    assert empty.ok and empty.data["header"] == [] and empty.data["scanned_rows"] == 0


@pytest.mark.asyncio
async def test_values_find_unknown_column_is_invalid_input(db):
    t, _ = api({f"{BASE}/values/Q3!A1:C6": ok(FIND_VALUES)})
    res = await run("google_sheets.values.find", {"spreadsheet_id": SID, "range": "Q3!A1:C6", "text": "acme", "column": "Nothing"}, db, t)
    assert res.error.code == ErrorCode.invalid_input and "Nothing" in res.error.message


@pytest.mark.asyncio
async def test_values_find_column_letter_beyond_the_header_width_is_invalid_not_zero_matches(db):
    body = {"range": "Q3!A1:B3", "values": [["Name", "Phone"], ["Ana", "555-1"], ["Luis", "555-2"]]}
    t, _ = api({f"{BASE}/values/Q3!A1:B3": ok(body)})
    res = await run("google_sheets.values.find", {"spreadsheet_id": SID, "range": "Q3!A1:B3", "text": "ana", "column": "Tel"}, db, t)
    assert res.error.code == ErrorCode.invalid_input and "Tel" in res.error.message and "'Name'" in res.error.message and "'Phone'" in res.error.message
    ok_res = await run("google_sheets.values.find", {"spreadsheet_id": SID, "range": "Q3!A1:B3", "text": "555-2", "column": "B"}, db, t)
    assert ok_res.ok and [m["row_number"] for m in ok_res.data["matches"]] == [3]
    third = await run("google_sheets.values.find", {"spreadsheet_id": SID, "range": "Q3!A1:B3", "text": "x", "column": "C"}, db, t)
    assert third.error.code == ErrorCode.invalid_input  # C = tercera columna y el rango solo tiene dos


@pytest.mark.parametrize("bad", [{}, {"text": ""}, {"text": "   "}, {"text": "x", "max_results": 0}, {"text": "x", "max_results": 101}])
@pytest.mark.asyncio
async def test_values_find_rejects_invalid_input_without_calling_google(db, bad):
    t, seen = api({})
    assert (await run("google_sheets.values.find", {"spreadsheet_id": SID, **bad}, db, t)).error.code == ErrorCode.invalid_input and not seen


# errores de la API en las funciones agregadas

@pytest.mark.parametrize("status,code", [(403, ErrorCode.missing_scope), (404, ErrorCode.not_found), (429, ErrorCode.rate_limited),
                                         (400, ErrorCode.invalid_input), (503, ErrorCode.upstream_down)])
@pytest.mark.parametrize("fid", NEW_IDS)
@pytest.mark.asyncio
async def test_added_functions_map_api_errors_to_contract_codes(db, fid, status, code):
    seen = []

    def handler(req):
        seen.append(req)
        return httpx.Response(status, json={"error": {"message": "x"}})

    res = await run(fid, get_function(fid).spec.examples[0].input, db, httpx.MockTransport(handler))
    assert not res.ok and res.error.code == code and seen
