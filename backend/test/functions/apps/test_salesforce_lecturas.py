"""Salesforce, Tarea 3: las 20 lecturas de usuarios (Chatter) y de CRM (SOQL: Account, Contact, Lead, Opportunity, Case, Task)."""
import httpx
import pytest
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient

from app.functions.apps.salesforce import _common
from app.functions.apps.salesforce.f_crm import OBJECTS
from app.core.constants import Collections
from app.functions.registry import get_function, list_functions, load_all
from app.functions.runner import execute
from app.functions.spec import ErrorCode
from functions_helpers import connection_doc

COL = Collections.USER_CONNECTED_ACCOUNTS
USER_ID = "005xx000001SvogAAC"
ORG = "https://acme.my.salesforce.com"
DATA = "/services/data/v62.0"
USERINFO = {"user_id": USER_ID, "organization_id": "00Dxx0000001gPLEAY", "name": "Ana Perez", "email": "ana@empresa.test",
            "urls": {"rest": f"{ORG}/services/data/v" + "{version}/"}}
CHATTER_USER = {"id": USER_ID, "name": "Ana Perez", "firstName": "Ana", "lastName": "Perez", "email": "ana@empresa.test", "title": "Manager",
                "companyName": "Acme", "username": "ana@empresa.test", "isActive": True, "userType": "Standard", "aboutMe": "Hola",
                "managerId": "005xx000001SvohAAC", "managerName": "Luis", "address": {"city": "Guatemala", "country": "GT"}}
NOT_FOUND = [{"errorCode": "NOT_FOUND", "message": "The requested resource does not exist"}]
BY_KEY = {o["key"]: o for o in OBJECTS}


@pytest.fixture(autouse=True, scope="module")
def _registry():
    load_all()


@pytest.fixture(autouse=True)
def _clear_org_cache():
    _common._BASES.clear()
    yield
    _common._BASES.clear()


@pytest_asyncio.fixture
async def db():
    d = AsyncMongoMockClient()["salesforce_reads_test"]
    await d[COL].insert_one(connection_doc(account=USER_ID, provider="salesforce", token="tok-1"))
    return d


def org_api(routes):
    """Salesforce simulado: userinfo (que dice donde vive la org) y las rutas de la org por ruta -> respuesta o funcion."""
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        if req.url.host == "login.salesforce.com":
            return httpx.Response(200, json=USERINFO)
        r = routes.get(req.url.path, httpx.Response(404, json=NOT_FOUND))
        return r(req) if callable(r) else r

    return httpx.MockTransport(handler), seen


def sf_record(cfg, **over):
    """El registro como lo manda Salesforce (nombres de campo de Salesforce), a partir del ejemplo de la ficha."""
    raw = {sf: cfg["example"][name] for sf, name, _, _ in cfg["fields"]}
    return {"attributes": {"type": cfg["sobject"]}, **raw, **over}


def soql_of(req):
    return req.url.params["q"]


async def run(db, fid, args, t):
    return await execute(get_function(fid), args, db=db, user_id="u1", transport=t)


KEYS = [o["key"] for o in OBJECTS]
LIST_KEYS = [o["key"] for o in OBJECTS if o.get("list", True)]
SEARCH_KEYS = [o["key"] for o in OBJECTS if o["filters"]]


def test_the_crm_reads_are_registered_with_the_api_scope():
    funcs = {f.spec.id: f for f in list_functions() if f.spec.app == "salesforce"}
    wanted = (["user.describe", "user.search", "user.get_by_id", "task.list", "task.get", "event.list", "event.get", "campaign.list", "campaign.get", "note.get"]
              + [f"{o}.{v}" for o in ("account", "contact", "lead", "opportunity", "case") for v in ("list", "get", "search")])
    assert len(wanted) == 25
    for w in wanted:
        spec = funcs[f"salesforce.{w}"].spec
        assert spec.scopes == ["api"] and spec.verb.value == "read" and len(spec.description) >= 200


@pytest.mark.asyncio
async def test_org_url_is_discovered_once_and_reused(db):
    t, seen = org_api({f"{DATA}/query": httpx.Response(200, json={"records": []})})
    for _ in range(2):
        assert (await run(db, "salesforce.account.list", {}, t)).ok
    assert [r.url.host for r in seen] == ["login.salesforce.com", "acme.my.salesforce.com", "acme.my.salesforce.com"]
    assert seen[1].headers["authorization"] == "Bearer tok-1"


@pytest.mark.asyncio
async def test_missing_org_url_is_upstream_changed(db):
    t = httpx.MockTransport(lambda req: httpx.Response(200, json={"user_id": USER_ID}))  # userinfo sin urls
    assert (await run(db, "salesforce.account.list", {}, t)).error.code == ErrorCode.upstream_changed


@pytest.mark.asyncio
@pytest.mark.parametrize("key", LIST_KEYS)
async def test_list_builds_soql_and_asks_one_extra_record_for_has_more(db, key):
    cfg = BY_KEY[key]
    rows = [sf_record(cfg), sf_record(cfg, Id="X" * 15 + "AAA")]
    t, seen = org_api({f"{DATA}/query": httpx.Response(200, json={"totalSize": 2, "done": True, "records": rows})})
    res = await run(db, f"salesforce.{key}.list", {"limit": 1, "offset": 10}, t)
    assert res.ok, res.error
    q = soql_of(seen[-1])
    assert q.startswith("SELECT Id,") and f"FROM {cfg['sobject']}" in q and q.endswith("ORDER BY CreatedDate DESC LIMIT 2 OFFSET 10")
    assert len(res.data["records"]) == 1 and res.data["has_more"] is True and res.data["next_offset"] == 11
    assert res.data["records"][0] == cfg["example"]


@pytest.mark.asyncio
async def test_list_has_no_next_offset_beyond_the_soql_limit_or_at_the_end(db):
    rows = [sf_record(BY_KEY["account"]), sf_record(BY_KEY["account"])]
    t, _ = org_api({f"{DATA}/query": httpx.Response(200, json={"records": rows})})
    res = await run(db, "salesforce.account.list", {"limit": 1, "offset": 2000}, t)
    assert res.data["has_more"] is True and res.data["next_offset"] is None
    res = await run(db, "salesforce.account.list", {"limit": 5}, t)
    assert res.data["has_more"] is False and res.data["next_offset"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("args", [{"limit": 0}, {"limit": 201}, {"offset": 2001}, {"offset": -1}])
async def test_list_rejects_out_of_range_paging(db, args):
    t, seen = org_api({})
    res = await run(db, "salesforce.account.list", args, t)
    assert res.error.code == ErrorCode.invalid_input and not seen


@pytest.mark.asyncio
@pytest.mark.parametrize("key", KEYS)
async def test_get_reads_the_record_by_id_and_maps_not_found(db, key):
    cfg = BY_KEY[key]
    t, seen = org_api({f"{DATA}/sobjects/{cfg['sobject']}/{cfg['example']['id']}": httpx.Response(200, json=sf_record(cfg))})
    res = await run(db, f"salesforce.{key}.get", {f"{key}_id": cfg["example"]["id"]}, t)
    assert res.ok, res.error
    assert res.data == cfg["example"] and seen[-1].url.params["fields"].startswith("Id,")
    res = await run(db, f"salesforce.{key}.get", {f"{key}_id": "0" * 15 + "AAA"}, t)
    assert res.error.code == ErrorCode.not_found


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["", "abc", "001/../../x", "001fj00000WTSTK'--", "x" * 19])
async def test_get_rejects_ids_that_are_not_salesforce_ids(db, bad):
    t, seen = org_api({})
    res = await run(db, "salesforce.account.get", {"account_id": bad}, t)
    assert res.error.code == ErrorCode.invalid_input and not seen


@pytest.mark.asyncio
async def test_search_builds_where_with_escaped_text(db):
    t, seen = org_api({f"{DATA}/query": httpx.Response(200, json={"records": [sf_record(BY_KEY["account"])]})})
    res = await run(db, "salesforce.account.search", {"name": "O'Brien \\ 50%_", "industry": "Tech", "limit": 5}, t)
    assert res.ok, res.error
    q = soql_of(seen[-1])
    assert q.split(" WHERE ")[1].split(" ORDER BY ")[0] == "Name LIKE '%O\\'Brien \\\\ 50\\%\\_%' AND Industry = 'Tech'"
    assert q.endswith("LIMIT 6 OFFSET 0")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", SEARCH_KEYS)
async def test_search_example_input_runs_and_needs_at_least_one_filter(db, key):
    t, seen = org_api({f"{DATA}/query": httpx.Response(200, json={"records": [sf_record(BY_KEY[key])]})})
    res = await run(db, f"salesforce.{key}.search", BY_KEY[key]["example_search"], t)
    assert res.ok and res.data["records"][0]["id"] == BY_KEY[key]["example"]["id"] and " WHERE " in soql_of(seen[-1])
    seen.clear()
    res = await run(db, f"salesforce.{key}.search", {"limit": 10}, t)
    assert res.error.code == ErrorCode.invalid_input and not seen


@pytest.mark.asyncio
async def test_search_numeric_and_id_filters(db):
    t, seen = org_api({f"{DATA}/query": httpx.Response(200, json={"records": []})})
    res = await run(db, "salesforce.opportunity.search", {"min_amount": 10000, "account_id": "001fj00000WTSTBAA5"}, t)
    assert res.ok and res.data == {"records": [], "has_more": False}
    assert "Amount >= 10000.0 AND AccountId = '001fj00000WTSTBAA5'" in soql_of(seen[-1])
    for bad in ({"min_amount": -1}, {"account_id": "x'; DROP"}):
        assert (await run(db, "salesforce.opportunity.search", bad, t)).error.code == ErrorCode.invalid_input, bad


@pytest.mark.asyncio
async def test_only_the_asked_functions_exist_for_task_event_campaign_and_note():
    ids = {f.spec.id for f in list_functions() if f.spec.app == "salesforce"}
    assert {"salesforce.task.list", "salesforce.task.get", "salesforce.event.list", "salesforce.event.get", "salesforce.campaign.list",
            "salesforce.campaign.get", "salesforce.note.get"} <= ids
    assert not ids & {"salesforce.task.search", "salesforce.event.search", "salesforce.campaign.search", "salesforce.note.search", "salesforce.note.list"}


@pytest.mark.asyncio
async def test_malformed_soql_from_salesforce_is_invalid_input(db):
    t, _ = org_api({f"{DATA}/query": httpx.Response(400, json=[{"errorCode": "MALFORMED_QUERY", "message": "unexpected token"}])})
    assert (await run(db, "salesforce.lead.list", {}, t)).error.code == ErrorCode.invalid_input


@pytest.mark.asyncio
async def test_expired_org_token_is_401_and_expires_the_account(db):
    t, _ = org_api({f"{DATA}/query": httpx.Response(401, json=[{"errorCode": "INVALID_SESSION_ID", "message": "Session expired or invalid"}])})
    assert (await run(db, "salesforce.case.list", {}, t)).error.code == ErrorCode.auth_expired
    assert (await db[COL].find_one({"account_id": USER_ID}))["status"] == "expired"


@pytest.mark.asyncio
async def test_user_list_and_search_use_chatter_paging(db):
    page = {"users": [CHATTER_USER], "nextPageUrl": f"{DATA}/chatter/users?page=1", "nextPageToken": 1}
    t, seen = org_api({f"{DATA}/chatter/users": httpx.Response(200, json=page)})
    res = await run(db, "salesforce.user.describe", {"page_size": 10, "page": 0}, t)
    assert res.ok, res.error
    assert dict(seen[-1].url.params) == {"pageSize": "10", "page": "0"}
    assert res.data["has_more"] is True and res.data["next_page"] == 1
    assert res.data["users"][0]["name"] == "Ana Perez" and res.data["users"][0]["is_active"] is True
    t, seen = org_api({f"{DATA}/chatter/users": httpx.Response(200, json={"users": [CHATTER_USER], "nextPageUrl": None, "nextPageToken": None})})
    res = await run(db, "salesforce.user.search", {"search_term": "perez"}, t)
    assert seen[-1].url.params["q"] == "perez" and res.data["has_more"] is False and res.data["next_page"] is None
    assert (await run(db, "salesforce.user.search", {"search_term": "p"}, t)).error.code == ErrorCode.invalid_input


@pytest.mark.asyncio
async def test_user_get_by_id_returns_detail_and_not_found(db):
    t, _ = org_api({f"{DATA}/chatter/users/{USER_ID}": httpx.Response(200, json=CHATTER_USER)})
    res = await run(db, "salesforce.user.get_by_id", {"user_id": USER_ID}, t)
    assert res.ok, res.error
    assert res.data["manager_name"] == "Luis" and res.data["city"] == "Guatemala" and res.data["about"] == "Hola"
    assert (await run(db, "salesforce.user.get_by_id", {"user_id": "005" + "0" * 12 + "AAA"}, t)).error.code == ErrorCode.not_found
