import httpx
import pytest
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient

from app.core.constants import Collections
from functions_helpers import connection_doc
from app.functions.registry import get_function, load_all
from app.functions.runner import execute
from app.functions.spec import ErrorCode

COL = Collections.USER_CONNECTED_ACCOUNTS


@pytest.fixture(autouse=True, scope="module")
def _registry():
    load_all()


@pytest_asyncio.fixture
async def db():
    d = AsyncMongoMockClient()["brevo_test"]
    await d[COL].insert_one(connection_doc(account="ana@empresa.test", provider="brevo", token="KEY-1"))
    return d


def api(routes):
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return routes.get(req.url.path, httpx.Response(404))

    return httpx.MockTransport(handler), seen


async def run(fid, args, db, t, **kw):
    return await execute(get_function(fid), args, db=db, user_id="u1", transport=t, **kw)


@pytest.mark.asyncio
async def test_account_get_sends_the_api_key_header_and_returns_the_stored_account_id(db):
    t, seen = api({"/v3/account": httpx.Response(200, json={
        "email": "ana@empresa.test", "companyName": "Empresa", "firstName": "Ana", "lastName": "Perez", "plan": []})})
    res = await run("brevo.account.get", {}, db, t)
    assert res.ok and res.data["account_id"] == "ana@empresa.test" and res.data["company_name"] == "Empresa"
    assert seen[0].headers["api-key"] == "KEY-1" and "authorization" not in seen[0].headers
    assert res.meta.account_id == "ana@empresa.test"  # whoami coincide con la cuenta guardada


@pytest.mark.asyncio
async def test_contacts_list_params_and_parsing(db):
    t, seen = api({"/v3/contacts": httpx.Response(200, json={"count": 120, "contacts": [
        {"id": 1, "email": "c@x.test", "createdAt": "2026-01-01T00:00:00.000Z", "modifiedAt": "2026-01-02T00:00:00.000Z",
         "emailBlacklisted": True, "listIds": [3, 4], "attributes": {"FIRSTNAME": "C"}}, {"id": 2}]})})
    res = await run("brevo.contacts.list", {"limit": 2, "offset": 10, "sort": "asc"}, db, t)
    assert dict(seen[0].url.params) == {"limit": "2", "offset": "10", "sort": "asc"}
    assert res.ok and res.data["count"] == 120 and len(res.data["contacts"]) == 2
    assert res.data["contacts"][0]["email_blacklisted"] is True and res.data["contacts"][1]["email"] is None


@pytest.mark.parametrize("bad", [{"limit": 0}, {"limit": 1001}, {"offset": -1}, {"sort": "random"}])
@pytest.mark.asyncio
async def test_contacts_list_rejects_bad_input(db, bad):
    res = await run("brevo.contacts.list", bad, db, api({})[0])
    assert res.error.code == ErrorCode.invalid_input


@pytest.mark.asyncio
async def test_templates_list_status_filter_and_no_html(db):
    t, seen = api({"/v3/smtp/templates": httpx.Response(200, json={"count": 1, "templates": [
        {"id": 7, "name": "Bienvenida", "subject": "Hola", "htmlContent": "<html>enorme</html>", "isActive": True, "tag": "x",
         "createdAt": "a", "modifiedAt": "b"}]})})
    res = await run("brevo.templates.list", {"only_active": True}, db, t)
    assert seen[0].url.params["templateStatus"] == "true"
    assert res.ok and "html" not in str(res.data).lower() and res.data["templates"][0]["is_active"] is True
    await run("brevo.templates.list", {}, db, t)
    assert "templateStatus" not in seen[1].url.params


@pytest.mark.asyncio
async def test_invalid_key_marks_only_that_account_expired(db):
    t, _ = api({"/v3/account": httpx.Response(401, json={"message": "Key not found"})})
    res = await run("brevo.account.get", {}, db, t)
    assert res.error.code == ErrorCode.auth_expired
    assert (await db[COL].find_one({"account_id": "ana@empresa.test"}))["status"] == "expired"


@pytest.mark.asyncio
async def test_two_brevo_accounts_require_a_choice_and_never_cross(db):
    await db[COL].insert_one(connection_doc(account="bob@otra.test", provider="brevo", token="KEY-2"))
    t, seen = api({"/v3/account": httpx.Response(200, json={"email": "bob@otra.test"})})
    assert (await run("brevo.account.get", {}, db, t)).error.code == ErrorCode.account_selection_required
    res = await run("brevo.account.get", {}, db, t, account_id="bob@otra.test")
    assert res.ok and seen[0].headers["api-key"] == "KEY-2" and res.data["account_id"] == res.meta.account_id
