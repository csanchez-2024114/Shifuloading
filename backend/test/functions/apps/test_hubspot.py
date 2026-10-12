import json

import httpx
import pytest
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient

from app.core.constants import Collections
from functions_helpers import unseal
from functions_helpers import connection_doc
from app.functions.registry import get_function, load_all
from app.functions.runner import execute
from app.functions.spec import ErrorCode

COL = Collections.USER_CONNECTED_ACCOUNTS
CRM = "/crm/objects/2026-09"
CONTACT = {"id": "151", "properties": {"email": "ana@empresa.test", "firstname": "Ana", "hs_object_id": "151"},
           "createdAt": "2026-01-02T10:00:00Z", "updatedAt": "2026-03-01T09:00:00Z", "archived": False}
COMPANY = {"id": "901", "properties": {"name": "Empresa Demo", "domain": "empresa.test"}, "createdAt": "2026-01-02T10:00:00Z",
           "updatedAt": "2026-03-01T09:00:00Z", "archived": False}
DEAL = {"id": "3301", "properties": {"dealname": "Licencia", "amount": "1200", "dealstage": "contractsent"},
        "createdAt": "2026-02-01T10:00:00Z", "updatedAt": "2026-03-01T09:00:00Z", "archived": False}


@pytest.fixture(autouse=True, scope="module")
def _registry():
    load_all()


@pytest_asyncio.fixture
async def db():
    d = AsyncMongoMockClient()["hubspot_test"]
    await d[COL].insert_one(connection_doc(account="123456", provider="hubspot", token="old-token", refresh="rt-1"))
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


@pytest.mark.asyncio
async def test_account_get_returns_portal_id_as_account_id(db):
    t, seen = api({"/account-info/2026-09/details": httpx.Response(200, json={
        "portalId": 123456, "accountType": "STANDARD", "timeZone": "US/Eastern", "companyCurrency": "USD", "additionalCurrencies": [],
        "utcOffset": "-05:00", "utcOffsetMilliseconds": -18000000, "uiDomain": "app.hubspot.com", "dataHostingLocation": "na1",
        "portalName": "Empresa Demo"})})
    res = await run("hubspot.account.get", {}, db, t)
    assert res.ok and res.data["account_id"] == "123456" and res.data["display_name"] == "Empresa Demo"
    assert res.data["currency"] == "USD" and res.data["data_hosting_location"] == "na1"
    assert seen[0].method == "GET" and seen[0].headers["authorization"] == "Bearer old-token"
    assert res.data["account_id"] == res.meta.account_id


@pytest.mark.asyncio
async def test_account_get_without_portal_name_uses_portal_id(db):
    t, _ = api({"/account-info/2026-09/details": httpx.Response(200, json={"portalId": 123456, "accountType": "DEVELOPER_TEST"})})
    res = await run("hubspot.account.get", {}, db, t)
    assert res.ok and res.data["display_name"] == "HubSpot 123456"


@pytest.mark.asyncio
async def test_contacts_search_builds_body_and_parses_paging(db):
    t, seen = api({f"{CRM}/contacts/search": httpx.Response(200, json={
        "total": 7, "results": [CONTACT], "paging": {"next": {"after": "1", "link": "https://api.hubapi.com/..."}}})})
    res = await run("hubspot.contacts.search", {
        "query": "ana", "limit": 1, "properties": ["email"], "sort_by": "createdate",
        "filter_groups": [{"filters": [{"property_name": "lifecyclestage", "operator": "IN", "values": ["lead", "customer"]}]}]}, db, t)
    assert json.loads(seen[0].content) == {
        "limit": 1, "query": "ana", "properties": ["email"], "sorts": [{"propertyName": "createdate", "direction": "DESCENDING"}],
        "filterGroups": [{"filters": [{"propertyName": "lifecyclestage", "operator": "IN", "values": ["lead", "customer"]}]}]}
    assert res.ok and res.data["total"] == 7 and res.data["next_after"] == "1"
    assert res.data["results"][0]["id"] == "151" and res.data["results"][0]["properties"]["email"] == "ana@empresa.test"


@pytest.mark.asyncio
async def test_search_sends_only_limit_by_default_and_last_page_has_no_cursor(db):
    t, seen = api({f"{CRM}/companies/search": httpx.Response(200, json={"total": 1, "results": [COMPANY]})})
    res = await run("hubspot.companies.search", {}, db, t)
    assert json.loads(seen[0].content) == {"limit": 10}
    assert res.ok and res.data["next_after"] is None and res.data["results"][0]["properties"]["domain"] == "empresa.test"


@pytest.mark.asyncio
async def test_deals_search_sends_between_filter_and_cursor(db):
    t, seen = api({f"{CRM}/deals/search": httpx.Response(200, json={"total": 1, "results": [DEAL]})})
    res = await run("hubspot.deals.search", {"after": "20", "filter_groups": [{"filters": [
        {"property_name": "amount", "operator": "BETWEEN", "value": "100", "high_value": "5000"}]}]}, db, t)
    body = json.loads(seen[0].content)
    assert body["after"] == "20"
    assert body["filterGroups"] == [{"filters": [{"propertyName": "amount", "operator": "BETWEEN", "value": "100", "highValue": "5000"}]}]
    assert res.ok and res.data["results"][0]["properties"]["dealstage"] == "contractsent"


@pytest.mark.asyncio
@pytest.mark.parametrize("args", [
    {"filter_groups": [{"filters": [{"property_name": "email", "operator": "EQ"}]}]},                    # EQ sin value
    {"filter_groups": [{"filters": [{"property_name": "x", "operator": "IN"}]}]},                        # IN sin values
    {"filter_groups": [{"filters": [{"property_name": "x", "operator": "BETWEEN", "value": "1"}]}]},     # BETWEEN sin high_value
    {"filter_groups": [{"filters": [{"property_name": "x", "operator": "HAS_PROPERTY"}] * 6}] * 4},      # 24 filtros > 18
    {"limit": 201},
])
async def test_search_rejects_invalid_input_without_calling_hubspot(db, args):
    t, seen = api({})
    assert (await run("hubspot.contacts.search", args, db, t)).error.code == ErrorCode.invalid_input
    assert seen == []


@pytest.mark.asyncio
async def test_search_validation_error_from_hubspot_is_invalid_input(db):
    t, _ = api({f"{CRM}/contacts/search": httpx.Response(400, json={
        "status": "error", "category": "VALIDATION_ERROR", "message": "There was a problem with the request."})})
    assert (await run("hubspot.contacts.search", {"query": "x"}, db, t)).error.code == ErrorCode.invalid_input


@pytest.mark.asyncio
async def test_contacts_batch_read_by_email_reports_not_found(db):
    t, seen = api({f"{CRM}/contacts/batch/read": httpx.Response(207, json={
        "status": "COMPLETE", "results": [CONTACT], "numErrors": 1,
        "errors": [{"status": "error", "category": "OBJECT_NOT_FOUND", "message": "Could not get some CONTACT objects",
                    "context": {"ids": ["nadie@empresa.test"]}}]})})
    res = await run("hubspot.contacts.batch_read", {"ids": ["ana@empresa.test", "nadie@empresa.test"], "properties": ["email"],
                                                    "id_property": "email"}, db, t)
    assert json.loads(seen[0].content) == {
        "inputs": [{"id": "ana@empresa.test"}, {"id": "nadie@empresa.test"}], "properties": ["email"], "idProperty": "email"}
    assert res.ok and res.data["not_found"] == ["nadie@empresa.test"] and res.data["results"][0]["id"] == "151"


@pytest.mark.asyncio
async def test_companies_batch_read_sends_default_properties(db):
    t, seen = api({f"{CRM}/companies/batch/read": httpx.Response(200, json={"status": "COMPLETE", "results": [COMPANY]})})
    res = await run("hubspot.companies.batch_read", {"ids": ["901"]}, db, t)
    body = json.loads(seen[0].content)
    assert body["inputs"] == [{"id": "901"}] and "name" in body["properties"] and "idProperty" not in body
    assert res.ok and res.data == {"results": [{"id": "901", "properties": COMPANY["properties"], "created_at": COMPANY["createdAt"],
                                                "updated_at": COMPANY["updatedAt"], "archived": False}], "not_found": []}


@pytest.mark.asyncio
@pytest.mark.parametrize("ids", [[], [str(i) for i in range(101)]])
async def test_batch_read_accepts_1_to_100_ids(db, ids):
    assert (await run("hubspot.contacts.batch_read", {"ids": ids}, db, api({})[0])).error.code == ErrorCode.invalid_input


@pytest.mark.asyncio
async def test_expired_token_is_refreshed_and_retried(db, monkeypatch):
    monkeypatch.setenv("HUBSPOT_CLIENT_ID", "cid")
    monkeypatch.setenv("HUBSPOT_CLIENT_SECRET", "csecret")

    def search(req):
        if req.headers["authorization"] == "Bearer fresh-token":
            return httpx.Response(200, json={"total": 0, "results": []})
        return httpx.Response(401, json={"status": "error", "category": "EXPIRED_AUTHENTICATION", "message": "The OAuth token used to make this call expired"})

    t, seen = api({f"{CRM}/contacts/search": search,
                   "/oauth/v1/token": httpx.Response(200, json={"access_token": "fresh-token", "refresh_token": "rt-1", "expires_in": 1800})})
    res = await run("hubspot.contacts.search", {}, db, t)
    assert res.ok and len(seen) == 3  # 401, refresco, reintento
    refresh_form = dict(httpx.QueryParams(seen[1].content.decode()))
    assert refresh_form == {"grant_type": "refresh_token", "refresh_token": "rt-1", "client_id": "cid", "client_secret": "csecret"}
    doc = await db[COL].find_one({"account_id": "123456"})
    assert unseal(doc["credentials_enc"]) == {"token": "fresh-token", "refresh_token": "rt-1"}


@pytest.mark.asyncio
async def test_missing_scope_403_does_not_expire_the_account(db):
    t, seen = api({f"{CRM}/deals/search": httpx.Response(403, json={
        "status": "error", "category": "MISSING_SCOPES", "message": "This app hasn't been granted all required scopes to make this call.",
        "errors": [{"message": "One or more of the following scopes are required.", "context": {"requiredGranularScopes": ["crm.objects.deals.read"]}}]})})
    res = await run("hubspot.deals.search", {}, db, t)
    assert res.error.code == ErrorCode.missing_scope and res.error.user_action == "grant_scopes"
    assert len(seen) == 1 and (await db[COL].find_one({"account_id": "123456"}))["status"] == "active"


@pytest.mark.asyncio
async def test_unexpected_response_shape_is_upstream_changed(db):
    t, _ = api({f"{CRM}/contacts/search": httpx.Response(200, json={"total": 1, "results": [{"properties": {}}]})})
    assert (await run("hubspot.contacts.search", {}, db, t)).error.code == ErrorCode.upstream_changed
