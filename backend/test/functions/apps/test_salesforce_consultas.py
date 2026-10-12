"""Salesforce, Tarea 4: objetos genericos (sobject.*), consultas SOQL (soql.*) y busquedas SOSL (sosl.*)."""
import httpx
import pytest
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient

from app.functions.apps.salesforce import _common
from app.core.constants import Collections
from app.functions.registry import get_function, list_functions, load_all
from app.functions.runner import execute
from app.functions.spec import ErrorCode
from functions_helpers import connection_doc

COL = Collections.USER_CONNECTED_ACCOUNTS
USER_ID = "005xx000001SvogAAC"
ORG = "https://acme.my.salesforce.com"
DATA = "/services/data/v62.0"
USERINFO = {"user_id": USER_ID, "urls": {"rest": f"{ORG}/services/data/v" + "{version}/"}}
NOT_FOUND = [{"errorCode": "NOT_FOUND", "message": "The requested resource does not exist"}]
ACCOUNT_ID = "001fj00000WTSTKAA5"

SOBJECTS = {"encoding": "UTF-8", "maxBatchSize": 200, "sobjects": [
    {"name": "Account", "label": "Cuenta", "labelPlural": "Cuentas", "keyPrefix": "001", "custom": False, "queryable": True, "searchable": True,
     "createable": True, "updateable": True, "deletable": True},
    {"name": "Invoice__c", "label": "Factura", "labelPlural": "Facturas", "keyPrefix": "a01", "custom": True, "queryable": True, "searchable": False,
     "createable": True, "updateable": True, "deletable": True},
    {"name": "AccountHistory", "label": "Historial de cuenta", "labelPlural": "Historiales", "keyPrefix": None, "custom": False, "queryable": False,
     "searchable": False, "createable": False, "updateable": False, "deletable": False},
]}
DESCRIBE = {**SOBJECTS["sobjects"][0], "fields": [
    {"name": "Id", "label": "Id", "type": "id", "length": 18, "nillable": False, "custom": False, "createable": False, "updateable": False, "filterable": True,
     "externalId": False, "referenceTo": [], "relationshipName": None, "nameField": False},
    {"name": "Name", "label": "Nombre", "type": "string", "length": 255, "nillable": False, "custom": False, "createable": True, "updateable": True,
     "filterable": True, "externalId": False, "referenceTo": [], "relationshipName": None, "nameField": True},
    {"name": "OwnerId", "label": "Propietario", "type": "reference", "length": 18, "nillable": False, "custom": False, "createable": True, "updateable": True,
     "filterable": True, "externalId": True, "referenceTo": ["User"], "relationshipName": "Owner", "nameField": False}],
    "childRelationships": [{"childSObject": "Contact", "field": "AccountId", "relationshipName": "Contacts"}],
    "recordTypeInfos": [{"recordTypeId": "012000000000000AAA", "name": "Master", "developerName": "Master", "available": True, "defaultRecordTypeMapping": True, "master": True}]}


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
    d = AsyncMongoMockClient()["salesforce_query_test"]
    await d[COL].insert_one(connection_doc(account=USER_ID, provider="salesforce", token="tok-1"))
    return d


def org_api(routes):
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        if req.url.host == "login.salesforce.com":
            return httpx.Response(200, json=USERINFO)
        r = routes.get(req.url.path, httpx.Response(404, json=NOT_FOUND))
        return r(req) if callable(r) else r

    return httpx.MockTransport(handler), seen


async def run(db, fid, args, t):
    return await execute(get_function(fid), args, db=db, user_id="u1", transport=t)


def test_the_eighteen_functions_of_the_task_are_registered_with_the_api_scope():
    funcs = {f.spec.id: f for f in list_functions() if f.spec.app == "salesforce"}
    wanted = (["event.list", "event.get", "campaign.list", "campaign.get", "note.get"]
              + [f"sobject.{n}" for n in ("describe_global", "describe", "get_metadata", "list_by_type", "get_by_type", "get_by_external_id", "get_deleted", "get_updated")]
              + ["soql.query", "soql.query_more", "soql.query_all", "sosl.search", "sosl.search_parameterized"])
    assert len(wanted) == 18
    for w in wanted:
        spec = funcs[f"salesforce.{w}"].spec
        assert spec.scopes == ["api"] and spec.verb.value == "read" and len(spec.description) >= 200


# ---------- sobject.describe_global / describe / get_metadata ----------

@pytest.mark.asyncio
async def test_describe_global_filters_and_pages(db):
    t, seen = org_api({f"{DATA}/sobjects": httpx.Response(200, json=SOBJECTS)})
    res = await run(db, "salesforce.sobject.describe_global", {}, t)
    assert res.ok, res.error
    assert res.data["total"] == 3 and [o["name"] for o in res.data["sobjects"]] == ["Account", "Invoice__c", "AccountHistory"] and res.data["has_more"] is False
    res = await run(db, "salesforce.sobject.describe_global", {"name_contains": "ACCOUNT", "queryable_only": True}, t)
    assert [o["name"] for o in res.data["sobjects"]] == ["Account"]
    res = await run(db, "salesforce.sobject.describe_global", {"name_contains": "factura"}, t)  # tambien busca en la etiqueta
    assert [o["name"] for o in res.data["sobjects"]] == ["Invoice__c"]
    res = await run(db, "salesforce.sobject.describe_global", {"custom_only": True}, t)
    assert [o["name"] for o in res.data["sobjects"]] == ["Invoice__c"]
    res = await run(db, "salesforce.sobject.describe_global", {"limit": 2}, t)
    assert res.data["has_more"] is True and res.data["next_offset"] == 2 and res.data["total"] == 3
    res = await run(db, "salesforce.sobject.describe_global", {"limit": 2, "offset": 2}, t)
    assert [o["name"] for o in res.data["sobjects"]] == ["AccountHistory"] and res.data["next_offset"] is None
    assert (await run(db, "salesforce.sobject.describe_global", {"limit": 501}, t)).error.code == ErrorCode.invalid_input


@pytest.mark.asyncio
async def test_describe_returns_fields_record_types_and_optional_children(db):
    t, _ = org_api({f"{DATA}/sobjects/Account/describe": httpx.Response(200, json=DESCRIBE)})
    res = await run(db, "salesforce.sobject.describe", {"sobject_type": "Account"}, t)
    assert res.ok, res.error
    assert res.data["field_count"] == 3 and res.data["fields"][2]["reference_to"] == ["User"] and res.data["fields"][2]["external_id"] is True
    assert res.data["record_types"][0]["default"] is True and res.data["child_relationships"] == []
    res = await run(db, "salesforce.sobject.describe", {"sobject_type": "Account", "include_child_relationships": True}, t)
    assert res.data["child_relationships"] == [{"child_sobject": "Contact", "field": "AccountId", "relationship_name": "Contacts"}]
    assert (await run(db, "salesforce.sobject.describe", {"sobject_type": "Nope__c"}, t)).error.code == ErrorCode.not_found


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["", "Account/describe", "../x", "Acc ount", "1Account", "A" * 81])
async def test_sobject_type_must_be_an_api_name(db, bad):
    t, seen = org_api({})
    res = await run(db, "salesforce.sobject.describe", {"sobject_type": bad}, t)
    assert res.error.code == ErrorCode.invalid_input and not seen


@pytest.mark.asyncio
async def test_get_metadata_returns_info_and_recent_items(db):
    body = {"objectDescribe": SOBJECTS["sobjects"][0], "recentItems": [{"attributes": {"type": "Account"}, "Id": ACCOUNT_ID, "Name": "Acme"}]}
    t, _ = org_api({f"{DATA}/sobjects/Account": httpx.Response(200, json=body)})
    res = await run(db, "salesforce.sobject.get_metadata", {"sobject_type": "Account"}, t)
    assert res.ok, res.error
    assert res.data["object_info"]["key_prefix"] == "001" and res.data["recent_items"] == [{"id": ACCOUNT_ID, "name": "Acme"}]


# ---------- sobject.list_by_type / get_by_type / get_by_external_id ----------

@pytest.mark.asyncio
async def test_list_by_type_without_fields_uses_id_and_the_name_field(db):
    rows = [{"attributes": {"type": "Account"}, "Id": "a", "Name": "Uno"}, {"attributes": {"type": "Account"}, "Id": "b", "Name": "Dos"}]
    t, seen = org_api({f"{DATA}/sobjects/Account/describe": httpx.Response(200, json=DESCRIBE), f"{DATA}/query": httpx.Response(200, json={"records": rows})})
    res = await run(db, "salesforce.sobject.list_by_type", {"sobject_type": "Account", "limit": 1, "offset": 4}, t)
    assert res.ok, res.error
    assert seen[-1].url.params["q"] == "SELECT Id,Name FROM Account ORDER BY CreatedDate DESC LIMIT 2 OFFSET 4"
    assert res.data == {"records": [{"Id": "a", "Name": "Uno"}], "has_more": True, "next_offset": 5}


@pytest.mark.asyncio
async def test_list_by_type_with_fields_skips_describe_and_rejects_bad_names(db):
    t, seen = org_api({f"{DATA}/query": httpx.Response(200, json={"records": []})})
    res = await run(db, "salesforce.sobject.list_by_type", {"sobject_type": "Account", "fields": ["Id", "Owner.Name"]}, t)
    assert res.ok and [r.url.path for r in seen if r.url.host != "login.salesforce.com"] == [f"{DATA}/query"]
    assert seen[-1].url.params["q"].startswith("SELECT Id,Owner.Name FROM Account")
    for bad in (["Id; DROP"], ["Id", "Name FROM Account--"], ["1x"]):
        assert (await run(db, "salesforce.sobject.list_by_type", {"sobject_type": "Account", "fields": bad}, t)).error.code == ErrorCode.invalid_input, bad


@pytest.mark.asyncio
async def test_get_by_type_returns_the_record_without_attributes(db):
    t, seen = org_api({f"{DATA}/sobjects/Account/{ACCOUNT_ID}": httpx.Response(200, json={"attributes": {"type": "Account"}, "Id": ACCOUNT_ID, "Name": "Acme"})})
    res = await run(db, "salesforce.sobject.get_by_type", {"sobject_type": "Account", "record_id": ACCOUNT_ID, "fields": ["Id", "Name"]}, t)
    assert res.ok, res.error
    assert res.data == {"id": ACCOUNT_ID, "record": {"Id": ACCOUNT_ID, "Name": "Acme"}} and seen[-1].url.params["fields"] == "Id,Name"
    assert (await run(db, "salesforce.sobject.get_by_type", {"sobject_type": "Account", "record_id": "0" * 15 + "AAA"}, t)).error.code == ErrorCode.not_found
    assert (await run(db, "salesforce.sobject.get_by_type", {"sobject_type": "Account", "record_id": "x/../y"}, t)).error.code == ErrorCode.invalid_input


@pytest.mark.asyncio
async def test_get_by_external_id_encodes_the_value_and_handles_300_and_404(db):
    path = f"{DATA}/sobjects/Account/Legacy_Id__c/CUST%2F42%20x"  # lo que viaja por el cable
    decoded = f"{DATA}/sobjects/Account/Legacy_Id__c/CUST/42 x"   # lo que httpx expone en url.path
    t, seen = org_api({decoded: httpx.Response(200, json={"attributes": {}, "Id": ACCOUNT_ID, "Name": "Acme"})})
    res = await run(db, "salesforce.sobject.get_by_external_id", {"sobject_type": "Account", "external_id_field": "Legacy_Id__c", "external_id_value": "CUST/42 x"}, t)
    assert res.ok, res.error
    assert res.data["id"] == ACCOUNT_ID and seen[-1].url.raw_path.decode().split("?")[0] == path
    t, _ = org_api({decoded: httpx.Response(300, json=[f"{DATA}/sobjects/Account/a", f"{DATA}/sobjects/Account/b"])})
    res = await run(db, "salesforce.sobject.get_by_external_id", {"sobject_type": "Account", "external_id_field": "Legacy_Id__c", "external_id_value": "CUST/42 x"}, t)
    assert res.error.code == ErrorCode.invalid_input and "More than one" in res.error.message
    t, _ = org_api({})
    res = await run(db, "salesforce.sobject.get_by_external_id", {"sobject_type": "Account", "external_id_field": "Name", "external_id_value": "x"}, t)
    assert res.error.code == ErrorCode.not_found
    res = await run(db, "salesforce.sobject.get_by_external_id", {"sobject_type": "Account", "external_id_field": "A/B", "external_id_value": "x"}, t)
    assert res.error.code == ErrorCode.invalid_input


# ---------- sobject.get_deleted / get_updated ----------

@pytest.mark.asyncio
async def test_get_deleted_and_updated_send_utc_dates_and_default_the_end(db):
    deleted = {"deletedRecords": [{"id": ACCOUNT_ID, "deletedDate": "2026-10-03T10:15:00.000+0000"}], "earliestDateAvailable": "2025-12-16T15:01:00.000+0000",
               "latestDateCovered": "2026-10-09T00:48:00.000+0000"}
    t, seen = org_api({f"{DATA}/sobjects/Account/deleted": httpx.Response(200, json=deleted), f"{DATA}/sobjects/Account/updated": httpx.Response(200, json={"ids": [ACCOUNT_ID], "latestDateCovered": "x"})})
    res = await run(db, "salesforce.sobject.get_deleted", {"sobject_type": "Account", "start": "2026-10-01T00:00:00-06:00", "end": "2026-10-05T00:00:00Z"}, t)
    assert res.ok, res.error
    assert dict(seen[-1].url.params) == {"start": "2026-10-01T06:00:00Z", "end": "2026-10-05T00:00:00Z"}
    assert res.data["deleted_records"] == [{"id": ACCOUNT_ID, "deleted_date": "2026-10-03T10:15:00.000+0000"}] and res.data["latest_date_covered"].startswith("2026-10-09")
    res = await run(db, "salesforce.sobject.get_updated", {"sobject_type": "Account", "start": "2026-10-01T00:00:00"}, t)  # sin zona = UTC
    assert res.data["ids"] == [ACCOUNT_ID] and seen[-1].url.params["start"] == "2026-10-01T00:00:00Z" and seen[-1].url.params["end"].endswith("Z")


@pytest.mark.asyncio
async def test_changes_reject_a_reversed_period_and_map_the_30_day_limit(db):
    t, seen = org_api({f"{DATA}/sobjects/Account/updated": httpx.Response(400, json=[{"errorCode": "INVALID_REPLICATION_DATE", "message": "startDate cannot be more than 30 days ago"}])})
    res = await run(db, "salesforce.sobject.get_updated", {"sobject_type": "Account", "start": "2026-10-05T00:00:00Z", "end": "2026-10-01T00:00:00Z"}, t)
    assert res.error.code == ErrorCode.invalid_input and not seen
    res = await run(db, "salesforce.sobject.get_updated", {"sobject_type": "Account", "start": "2026-01-01T00:00:00Z"}, t)
    assert res.error.code == ErrorCode.invalid_input and "30 days" in res.error.message


# ---------- soql.* ----------

@pytest.mark.asyncio
async def test_soql_query_returns_clean_records_and_a_locator(db):
    body = {"totalSize": 450, "done": False, "nextRecordsUrl": f"{DATA}/query/01gfj00000AbCdEAAZ-200",
            "records": [{"attributes": {"type": "Account"}, "Id": ACCOUNT_ID, "Name": "Acme"}]}
    t, seen = org_api({f"{DATA}/query": httpx.Response(200, json=body)})
    res = await run(db, "salesforce.soql.query", {"soql_query": "SELECT Id, Name FROM Account", "batch_size": 500}, t)
    assert res.ok, res.error
    assert res.data == {"records": [{"Id": ACCOUNT_ID, "Name": "Acme"}], "total_size": 450, "done": False, "query_locator": "01gfj00000AbCdEAAZ-200"}
    assert seen[-1].url.params["q"] == "SELECT Id, Name FROM Account" and seen[-1].headers["sforce-query-options"] == "batchSize=500"


@pytest.mark.asyncio
async def test_soql_count_and_malformed_query(db):
    t, _ = org_api({f"{DATA}/query": httpx.Response(200, json={"totalSize": 13, "done": True, "records": []})})
    res = await run(db, "salesforce.soql.query", {"soql_query": "SELECT COUNT() FROM Account"}, t)
    assert res.data == {"records": [], "total_size": 13, "done": True, "query_locator": None}
    t, _ = org_api({f"{DATA}/query": httpx.Response(400, json=[{"errorCode": "MALFORMED_QUERY", "message": "unexpected token"}])})
    assert (await run(db, "salesforce.soql.query", {"soql_query": "SELECT FROM"}, t)).error.code == ErrorCode.invalid_input
    for bad in ({"soql_query": "x"}, {"soql_query": "SELECT Id FROM Account", "batch_size": 100}, {"soql_query": "SELECT Id FROM Account", "batch_size": 2001}):
        assert (await run(db, "salesforce.soql.query", bad, t)).error.code == ErrorCode.invalid_input


@pytest.mark.asyncio
async def test_soql_query_more_follows_the_locator_and_validates_it(db):
    t, seen = org_api({f"{DATA}/query/01gfj00000AbCdEAAZ-200": httpx.Response(200, json={"totalSize": 201, "done": True, "records": [{"attributes": {}, "Id": "x"}]})})
    res = await run(db, "salesforce.soql.query_more", {"query_locator": "01gfj00000AbCdEAAZ-200"}, t)
    assert res.ok and res.data == {"records": [{"Id": "x"}], "total_size": 201, "done": True, "query_locator": None}
    for bad in ("abc", "01gfj00000AbCdEAAZ", "../query?q=x-1", "01gfj00000AbCdEAAZ-200/x"):
        res = await run(db, "salesforce.soql.query_more", {"query_locator": bad}, t)
        assert res.error.code == ErrorCode.invalid_input, bad
    t, _ = org_api({f"{DATA}/query/01gfj00000AbCdEAAZ-9": httpx.Response(400, json=[{"errorCode": "INVALID_QUERY_LOCATOR", "message": "invalid"}])})
    assert (await run(db, "salesforce.soql.query_more", {"query_locator": "01gfj00000AbCdEAAZ-9"}, t)).error.code == ErrorCode.invalid_input


@pytest.mark.asyncio
async def test_soql_query_all_uses_the_query_all_endpoint(db):
    t, seen = org_api({f"{DATA}/queryAll": httpx.Response(200, json={"totalSize": 1, "done": True, "records": [{"attributes": {}, "Id": ACCOUNT_ID}]})})
    res = await run(db, "salesforce.soql.query_all", {"soql_query": "SELECT Id FROM Account WHERE IsDeleted = true"}, t)
    assert res.ok and res.data["records"] == [{"Id": ACCOUNT_ID}] and seen[-1].url.path == f"{DATA}/queryAll"


# ---------- sosl.* ----------

@pytest.mark.asyncio
async def test_sosl_search_tags_each_record_with_its_object_type(db):
    body = {"searchRecords": [{"attributes": {"type": "Account"}, "Id": ACCOUNT_ID, "Name": "sForce"}, {"attributes": {"type": "Contact"}, "Id": "003x", "LastName": "Llorrac"}]}
    t, seen = org_api({f"{DATA}/search": httpx.Response(200, json=body)})
    res = await run(db, "salesforce.sosl.search", {"sosl_query": "find {sforce} returning Account(Id, Name), Contact(Id, LastName)"}, t)
    assert res.ok, res.error
    assert res.data["records"] == [{"sobject_type": "Account", "Id": ACCOUNT_ID, "Name": "sForce"}, {"sobject_type": "Contact", "Id": "003x", "LastName": "Llorrac"}]
    assert seen[-1].url.params["q"].lower().startswith("find {sforce}")
    res = await run(db, "salesforce.sosl.search", {"sosl_query": "SELECT Id FROM Account"}, t)
    assert res.error.code == ErrorCode.invalid_input


@pytest.mark.asyncio
async def test_sosl_search_parameterized_builds_the_object_prefixed_params(db):
    t, seen = org_api({f"{DATA}/parameterizedSearch": httpx.Response(200, json={"searchRecords": [{"attributes": {"type": "Account"}, "Id": ACCOUNT_ID, "Name": "sForce"}]})})
    args = {"search_term": "sforce", "sobject_type": "Account", "fields": ["Id", "Name"], "where": "Name != null", "search_in": "NAME", "limit": 5}
    res = await run(db, "salesforce.sosl.search_parameterized", args, t)
    assert res.ok, res.error
    assert dict(seen[-1].url.params) == {"q": "sforce", "sobject": "Account", "Account.fields": "Id,Name", "Account.limit": "5", "Account.where": "Name != null", "in": "NAME"}
    assert res.data["records"] == [{"sobject_type": "Account", "Id": ACCOUNT_ID, "Name": "sForce"}]
    res = await run(db, "salesforce.sosl.search_parameterized", {"search_term": "x", "sobject_type": "Account"}, t)
    assert dict(seen[-1].url.params) == {"q": "x", "sobject": "Account", "Account.fields": "Id", "Account.limit": "25"}
    for bad in ({"search_term": "x", "sobject_type": "A/B"}, {"search_term": "x", "sobject_type": "Account", "fields": ["Id,Name"]},
                {"search_term": "x", "sobject_type": "Account", "search_in": "EVERYTHING"}, {"search_term": "", "sobject_type": "Account"}):
        assert (await run(db, "salesforce.sosl.search_parameterized", bad, t)).error.code == ErrorCode.invalid_input, bad
