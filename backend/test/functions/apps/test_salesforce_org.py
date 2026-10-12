"""Salesforce, Tarea 5: Chatter, informes y paneles, limites, vistas de lista, tipos de registro, listas desplegables, recursos de la API y Bulk."""
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
REPORT = "00Ofj000005WXcTEAW"
DASH = "01Zfj0000022ug5EAA"
COMP = "01afj000002tJs5AAE"


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
    d = AsyncMongoMockClient()["salesforce_org_test"]
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


def test_the_twenty_functions_of_the_task_are_registered_with_the_api_scope():
    funcs = {f.spec.id: f for f in list_functions() if f.spec.app == "salesforce"}
    wanted = ["chatter.feeds", "chatter.groups", "chatter.group_get", "analytics.reports_list", "analytics.report_get", "analytics.report_run",
              "analytics.dashboards_list", "analytics.dashboard_get", "analytics.dashboard_component", "limits.get", "recent.get", "list_views.describe",
              "list_views.run", "record_type.get", "picklist.get", "metadata.describe", "tooling.describe", "data.version", "data.version_resources", "bulk.job_get"]
    assert len(wanted) == 20
    for w in wanted:
        spec = funcs[f"salesforce.{w}"].spec
        assert spec.scopes == ["api"] and spec.verb.value == "read" and len(spec.description) >= 200


# ---------- chatter ----------

@pytest.mark.asyncio
async def test_chatter_feeds_maps_elements_and_pages_with_the_token(db):
    el = {"id": "0D5fj00000AbCdEAAZ", "type": "TextPost", "body": {"text": "Hola"}, "actor": {"id": USER_ID, "displayName": "Ana"}, "createdDate": "2026-10-08T14:30:00.000Z",
          "parent": {"id": "0F9fj00000AbCdECAV", "name": "Ventas"}, "capabilities": {"comments": {"page": {"total": 2}}, "chatterLikes": {"page": {"total": 5}}}}
    auto = {"id": "0D5fj00000AbCdFAAZ", "type": "TrackedChange", "header": {"text": "Ana changed the stage"}}
    t, seen = org_api({f"{DATA}/chatter/feeds/news/me/feed-elements": httpx.Response(200, json={"elements": [el, auto], "nextPageToken": "2:99", "nextPageUrl": "/x"})})
    res = await run(db, "salesforce.chatter.feeds", {"page_size": 2, "page_token": "1:50"}, t)
    assert res.ok, res.error
    assert dict(seen[-1].url.params) == {"pageSize": "2", "page": "1:50"}
    first, second = res.data["elements"]
    assert first["text"] == "Hola" and first["actor_name"] == "Ana" and first["parent_name"] == "Ventas" and first["comment_count"] == 2 and first["like_count"] == 5
    assert second["text"] == "Ana changed the stage" and second["comment_count"] is None
    assert res.data["has_more"] is True and res.data["next_page_token"] == "2:99"


@pytest.mark.asyncio
async def test_chatter_feeds_empty_and_bad_page_size(db):
    t, _ = org_api({f"{DATA}/chatter/feeds/news/me/feed-elements": httpx.Response(200, json={"elements": [], "nextPageToken": None, "nextPageUrl": None})})
    assert (await run(db, "salesforce.chatter.feeds", {}, t)).data == {"elements": [], "has_more": False, "next_page_token": None}
    assert (await run(db, "salesforce.chatter.feeds", {"page_size": 101}, t)).error.code == ErrorCode.invalid_input


GROUP = {"id": "0F9fj00000AbCdECAV", "name": "Ventas", "description": "Equipo", "visibility": "PublicAccess", "memberCount": 12,
         "owner": {"id": USER_ID, "displayName": "Ana"}, "isArchived": False}


@pytest.mark.asyncio
async def test_chatter_groups_filters_and_pages(db):
    t, seen = org_api({f"{DATA}/chatter/groups": httpx.Response(200, json={"groups": [GROUP], "nextPageUrl": "/x", "nextPageToken": 3})})
    res = await run(db, "salesforce.chatter.groups", {"search_term": "ven", "page_size": 1, "page": 2}, t)
    assert res.ok, res.error
    assert dict(seen[-1].url.params) == {"pageSize": "1", "page": "2", "q": "ven"}
    assert res.data["groups"][0] == {"id": GROUP["id"], "name": "Ventas", "description": "Equipo", "visibility": "PublicAccess", "member_count": 12,
                                     "owner_id": USER_ID, "owner_name": "Ana", "is_archived": False}
    assert res.data["has_more"] is True and res.data["next_page"] == 3
    t, _ = org_api({f"{DATA}/chatter/groups": httpx.Response(200, json={"groups": [], "nextPageUrl": "/x"})})  # sin token: pagina actual + 1
    assert (await run(db, "salesforce.chatter.groups", {"page": 4}, t)).data["next_page"] == 5
    assert (await run(db, "salesforce.chatter.groups", {"search_term": "v"}, t)).error.code == ErrorCode.invalid_input


@pytest.mark.asyncio
async def test_chatter_group_get(db):
    t, _ = org_api({f"{DATA}/chatter/groups/{GROUP['id']}": httpx.Response(200, json=GROUP)})
    res = await run(db, "salesforce.chatter.group_get", {"group_id": GROUP["id"]}, t)
    assert res.ok and res.data["member_count"] == 12
    assert (await run(db, "salesforce.chatter.group_get", {"group_id": "0F9" + "0" * 12 + "AAA"}, t)).error.code == ErrorCode.not_found
    assert (await run(db, "salesforce.chatter.group_get", {"group_id": "../x"}, t)).error.code == ErrorCode.invalid_input


# ---------- analytics ----------

REPORT_ROW = {"attributes": {"type": "Report"}, "Id": REPORT, "Name": "Pipeline", "DeveloperName": "Pipeline", "Format": "Summary", "FolderName": "Public",
              "Description": None, "LastRunDate": None, "LastModifiedDate": "2026-09-01T10:00:00.000+0000"}


@pytest.mark.asyncio
async def test_reports_and_dashboards_list_use_soql_with_escaped_filter_and_paging(db):
    rows = [REPORT_ROW, {**REPORT_ROW, "Id": "00Ofj000005WXcUEAW"}]
    t, seen = org_api({f"{DATA}/query": httpx.Response(200, json={"records": rows})})
    res = await run(db, "salesforce.analytics.reports_list", {"name_contains": "O'Neil_", "limit": 1, "offset": 3}, t)
    assert res.ok, res.error
    q = seen[-1].url.params["q"]
    assert q.startswith("SELECT Id,Name,DeveloperName,Format,FolderName,Description,LastRunDate,LastModifiedDate FROM Report WHERE Name LIKE '%O\\'Neil\\_%'")
    assert q.endswith("ORDER BY LastModifiedDate DESC LIMIT 2 OFFSET 3")
    assert res.data["reports"][0]["name"] == "Pipeline" and res.data["has_more"] is True and res.data["next_offset"] == 4
    drow = {"attributes": {}, "Id": DASH, "Title": "Ventas", "DeveloperName": "Ventas", "FolderName": "Public", "Description": None, "Type": "LoggedInUser", "LastModifiedDate": "x"}
    t, seen = org_api({f"{DATA}/query": httpx.Response(200, json={"records": [drow]})})
    res = await run(db, "salesforce.analytics.dashboards_list", {}, t)
    assert " FROM Dashboard ORDER BY" in seen[-1].url.params["q"] and res.data["dashboards"][0]["title"] == "Ventas" and res.data["has_more"] is False
    assert (await run(db, "salesforce.analytics.dashboards_list", {"offset": 2001}, t)).error.code == ErrorCode.invalid_input


@pytest.mark.asyncio
async def test_report_get_returns_results_and_maps_forbidden(db):
    body = {"reportMetadata": {"name": "Pipeline"}, "factMap": {"T!T": {"aggregates": [{"label": "3", "value": 3}]}}, "groupingsDown": {"groupings": []},
            "groupingsAcross": {"groupings": []}, "allData": True, "hasDetailRows": False, "picklistColors": {}, "reportExtendedMetadata": {}}
    t, seen = org_api({f"{DATA}/analytics/reports/{REPORT}": httpx.Response(200, json=body)})
    res = await run(db, "salesforce.analytics.report_get", {"report_id": REPORT, "include_details": True}, t)
    assert res.ok, res.error
    assert seen[-1].url.params["includeDetails"] == "true"
    assert res.data["fact_map"]["T!T"]["aggregates"][0]["value"] == 3 and res.data["all_data"] is True and "picklistColors" not in res.data
    t, _ = org_api({f"{DATA}/analytics/reports/{REPORT}": httpx.Response(403, json=[{"errorCode": "FORBIDDEN", "specificErrorCode": 103}])})
    res = await run(db, "salesforce.analytics.report_get", {"report_id": REPORT}, t)
    assert res.error.code == ErrorCode.missing_scope
    assert (await db[COL].find_one({"account_id": USER_ID}))["status"] == "active"


@pytest.mark.asyncio
async def test_report_run_posts_an_instance_with_optional_overrides(db):
    resp = {"id": "0LGfj0000016hEbGAI", "status": "New", "requestDate": "2026-10-09T15:42:07Z", "ownerId": USER_ID, "url": f"{DATA}/analytics/reports/{REPORT}/instances/0LGfj0000016hEbGAI"}
    t, seen = org_api({f"{DATA}/analytics/reports/{REPORT}/instances": httpx.Response(200, json=resp)})
    res = await run(db, "salesforce.analytics.report_run", {"report_id": REPORT}, t)
    assert res.ok, res.error
    assert seen[-1].method == "POST" and seen[-1].content == b"{}" and res.data["instance_id"] == "0LGfj0000016hEbGAI" and res.data["status"] == "New"
    override = {"reportFilters": [{"column": "STAGE_NAME", "operator": "equals", "value": "Closed Won"}]}
    await run(db, "salesforce.analytics.report_run", {"report_id": REPORT, "report_metadata": override}, t)
    import json
    assert json.loads(seen[-1].content) == {"reportMetadata": override}
    t, _ = org_api({f"{DATA}/analytics/reports/{REPORT}/instances": httpx.Response(200, json={})})
    assert (await run(db, "salesforce.analytics.report_run", {"report_id": REPORT}, t)).error.code == ErrorCode.upstream_changed


DESCRIBE = {"id": DASH, "name": "Ventas", "description": None, "developerName": "Ventas", "folderName": "Public", "dashboardType": "LoggedInUser",
            "runningUser": {"displayName": "Ana"}, "components": [{"id": COMP, "header": "Pipeline", "title": None, "footer": None, "type": "Report", "reportId": REPORT,
                                                                   "lastModifiedDate": "2026-09-01T10:00:00Z"}]}


@pytest.mark.asyncio
async def test_dashboard_get_and_component(db):
    data = {"componentData": [{"componentId": COMP, "reportResult": {"factMap": {"T!T": {}}}, "status": {"componentDataStatus": "DATA", "refreshStatus": "IDLE", "refreshDate": "2026-10-09T12:00:00Z"}},
                              {"componentId": "01afj000002tJs8AAE", "reportResult": None, "status": {"componentDataStatus": "NO_DATA", "errorMessage": "sin acceso"}}]}
    t, _ = org_api({f"{DATA}/analytics/dashboards/{DASH}/describe": httpx.Response(200, json=DESCRIBE), f"{DATA}/analytics/dashboards/{DASH}": httpx.Response(200, json=data)})
    res = await run(db, "salesforce.analytics.dashboard_get", {"dashboard_id": DASH}, t)
    assert res.ok, res.error
    assert res.data["running_user"] == "Ana" and res.data["component_count"] == 1 and res.data["components"][0]["report_id"] == REPORT
    res = await run(db, "salesforce.analytics.dashboard_component", {"dashboard_id": DASH, "component_id": COMP}, t)
    assert res.ok and res.data["data_status"] == "DATA" and res.data["report_result"] == {"factMap": {"T!T": {}}}
    res = await run(db, "salesforce.analytics.dashboard_component", {"dashboard_id": DASH, "component_id": "01afj000002tJs8AAE"}, t)
    assert res.data["data_status"] == "NO_DATA" and res.data["error_message"] == "sin acceso" and res.data["report_result"] is None
    res = await run(db, "salesforce.analytics.dashboard_component", {"dashboard_id": DASH, "component_id": "01a" + "0" * 12 + "AAA"}, t)
    assert res.error.code == ErrorCode.not_found
    assert (await run(db, "salesforce.analytics.dashboard_get", {"dashboard_id": "bad id"}, t)).error.code == ErrorCode.invalid_input


# ---------- limites, recientes, vistas de lista ----------

@pytest.mark.asyncio
async def test_limits_get_computes_used_and_filters(db):
    body = {"DailyApiRequests": {"Max": 15000, "Remaining": 14980}, "DataStorageMB": {"Max": 5, "Remaining": 4}, "Weird": "no-es-dict"}
    t, _ = org_api({f"{DATA}/limits": httpx.Response(200, json=body)})
    res = await run(db, "salesforce.limits.get", {}, t)
    assert [x["name"] for x in res.data["limits"]] == ["DailyApiRequests", "DataStorageMB"] and res.data["limits"][0]["used"] == 20
    res = await run(db, "salesforce.limits.get", {"name_contains": "STORAGE"}, t)
    assert res.data["limits"] == [{"name": "DataStorageMB", "max": 5, "remaining": 4, "used": 1}]


@pytest.mark.asyncio
async def test_recent_get_reads_the_list(db):
    t, seen = org_api({f"{DATA}/recent": httpx.Response(200, json=[{"attributes": {"type": "Account"}, "Id": "001fj00000WTSTKAA5", "Name": "Acme"}, {"attributes": {}, "Name": "sin id"}])})
    res = await run(db, "salesforce.recent.get", {"limit": 5}, t)
    assert res.ok and seen[-1].url.params["limit"] == "5" and res.data["items"] == [{"id": "001fj00000WTSTKAA5", "name": "Acme", "sobject_type": "Account"}]
    assert (await run(db, "salesforce.recent.get", {"limit": 0}, t)).error.code == ErrorCode.invalid_input


@pytest.mark.asyncio
async def test_list_views_describe_and_run(db):
    views = {"done": True, "listviews": [{"id": "00Bfj00000HjWmCEAV", "label": "New", "developerName": "NewThisWeek", "soqlCompatible": True}]}
    cols = [{"fieldNameOrPath": "Name", "label": "Name", "type": "string", "hidden": False}, {"fieldNameOrPath": "Id", "label": "Id", "type": "id", "hidden": True}]
    rec = lambda n: {"columns": [{"fieldNameOrPath": "Name", "value": n}, {"fieldNameOrPath": "Id", "value": "001" + n}]}
    results = {"label": "All", "columns": cols, "records": [rec("a"), rec("b"), rec("c")], "size": 3, "done": True}
    t, seen = org_api({f"{DATA}/sobjects/Account/listviews": httpx.Response(200, json=views), f"{DATA}/sobjects/Account/listviews/00Bfj00000HjWmCEAV/results": httpx.Response(200, json=results)})
    res = await run(db, "salesforce.list_views.describe", {"sobject_type": "Account"}, t)
    assert res.ok and res.data["list_views"][0]["developer_name"] == "NewThisWeek" and res.data["done"] is True
    res = await run(db, "salesforce.list_views.run", {"sobject_type": "Account", "list_view_id": "00Bfj00000HjWmCEAV", "limit": 2, "offset": 4}, t)
    assert res.ok, res.error
    assert dict(seen[-1].url.params) == {"limit": "3", "offset": "4"}
    assert res.data["columns"] == [{"field_name": "Name", "label": "Name", "type": "string"}]  # la columna oculta no sale
    assert res.data["records"] == [{"Name": "a", "Id": "001a"}, {"Name": "b", "Id": "001b"}] and res.data["has_more"] is True and res.data["next_offset"] == 6
    assert (await run(db, "salesforce.list_views.describe", {"sobject_type": "Nope"}, t)).error.code == ErrorCode.not_found
    assert (await run(db, "salesforce.list_views.run", {"sobject_type": "Account", "list_view_id": "x/y"}, t)).error.code == ErrorCode.invalid_input


# ---------- tipos de registro y listas desplegables ----------

LEAD = {"recordTypeInfos": [{"recordTypeId": "012000000000000AAA", "name": "Master", "developerName": "Master", "available": True, "defaultRecordTypeMapping": True, "master": True}],
        "fields": [
            {"name": "Status", "label": "Status", "type": "picklist", "restrictedPicklist": False, "controllerName": None,
             "picklistValues": [{"value": "Open", "label": "Open", "active": True, "defaultValue": True}, {"value": "Old", "label": "Old", "active": False, "defaultValue": False}]},
            {"name": "Email", "label": "Email", "type": "email", "picklistValues": []}]}


@pytest.mark.asyncio
async def test_record_type_get_and_picklist_get(db):
    t, _ = org_api({f"{DATA}/sobjects/Lead/describe": httpx.Response(200, json=LEAD)})
    res = await run(db, "salesforce.record_type.get", {"sobject_type": "Lead"}, t)
    assert res.ok and res.data["record_types"][0]["master"] is True
    res = await run(db, "salesforce.picklist.get", {"sobject_type": "Lead", "field_name": "status"}, t)  # sin distinguir mayusculas
    assert res.ok, res.error
    assert res.data["field_name"] == "Status" and [v["value"] for v in res.data["values"]] == ["Open", "Old"] and res.data["values"][1]["active"] is False
    assert (await run(db, "salesforce.picklist.get", {"sobject_type": "Lead", "field_name": "Email"}, t)).error.code == ErrorCode.invalid_input
    assert (await run(db, "salesforce.picklist.get", {"sobject_type": "Lead", "field_name": "Nope"}, t)).error.code == ErrorCode.not_found
    assert (await run(db, "salesforce.picklist.get", {"sobject_type": "Lead", "field_name": "A.B"}, t)).error.code == ErrorCode.invalid_input
    assert (await run(db, "salesforce.record_type.get", {"sobject_type": "Nope"}, t)).error.code == ErrorCode.not_found


# ---------- recursos de la API, versiones y Bulk ----------

@pytest.mark.asyncio
async def test_metadata_and_tooling_describe(db):
    t, _ = org_api({f"{DATA}/metadata": httpx.Response(200, json={"deployRequest": f"{DATA}/metadata/deployRequest"}),
                    f"{DATA}/tooling": httpx.Response(200, json={"query": f"{DATA}/tooling/query"})})
    assert (await run(db, "salesforce.metadata.describe", {}, t)).data == {"resources": {"deployRequest": f"{DATA}/metadata/deployRequest"}}
    assert (await run(db, "salesforce.tooling.describe", {}, t)).data == {"resources": {"query": f"{DATA}/tooling/query"}}


@pytest.mark.asyncio
async def test_data_version_lists_versions_from_the_org_root(db):
    versions = [{"label": "Summer '14", "url": "/services/data/v31.0", "version": "31.0"}, {"label": "Winter '25", "url": "/services/data/v62.0", "version": "62.0"}]
    t, seen = org_api({"/services/data": httpx.Response(200, json=versions), f"{DATA}": httpx.Response(200, json={"sobjects": f"{DATA}/sobjects"}),
                       "/services/data/v50.0": httpx.Response(200, json={"query": "/services/data/v50.0/query"})})
    res = await run(db, "salesforce.data.version", {}, t)
    assert res.ok, res.error
    assert res.data["in_use"] == "62.0" and [v["version"] for v in res.data["versions"]] == ["31.0", "62.0"] and seen[-1].url.host == "acme.my.salesforce.com"
    assert (await run(db, "salesforce.data.version_resources", {}, t)).data == {"resources": {"sobjects": f"{DATA}/sobjects"}, "version": "62.0"}
    assert (await run(db, "salesforce.data.version_resources", {"version": "50.0"}, t)).data["resources"] == {"query": "/services/data/v50.0/query"}
    assert (await run(db, "salesforce.data.version_resources", {"version": "99.0"}, t)).error.code == ErrorCode.not_found
    assert (await run(db, "salesforce.data.version_resources", {"version": "latest"}, t)).error.code == ErrorCode.invalid_input


@pytest.mark.asyncio
async def test_bulk_job_get(db):
    job = {"id": "750fj00000AbCdEAAV", "state": "Failed", "operation": "insert", "object": "Contact", "createdDate": "2026-10-08T10:00:00.000+0000",
           "systemModstamp": "2026-10-08T10:01:00.000+0000", "numberRecordsProcessed": 10, "numberRecordsFailed": 10, "totalProcessingTime": 90, "errorMessage": "boom"}
    t, _ = org_api({f"{DATA}/jobs/ingest/750fj00000AbCdEAAV": httpx.Response(200, json=job)})
    res = await run(db, "salesforce.bulk.job_get", {"job_id": "750fj00000AbCdEAAV"}, t)
    assert res.ok, res.error
    assert res.data["state"] == "Failed" and res.data["number_records_failed"] == 10 and res.data["error_message"] == "boom" and res.data["object"] == "Contact"
    assert (await run(db, "salesforce.bulk.job_get", {"job_id": "750" + "0" * 12 + "AAA"}, t)).error.code == ErrorCode.not_found
    assert (await run(db, "salesforce.bulk.job_get", {"job_id": "x"}, t)).error.code == ErrorCode.invalid_input
