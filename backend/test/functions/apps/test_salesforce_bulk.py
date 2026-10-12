"""Salesforce, Tarea 6: trabajos de consulta Bulk API 2.0 (bulk_query.*) y acciones invocables (actions.*)."""
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
JOB = "750fj00000AbCdEAAV"


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
    d = AsyncMongoMockClient()["salesforce_bulk_test"]
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


def csv_response(text, *, locator="null", status=200):
    return httpx.Response(status, content=text.encode("utf-8"), headers={"content-type": "text/csv", "Sforce-Locator": locator, "Sforce-NumberOfRecords": "2"})


def test_the_four_functions_of_the_task_are_registered_with_the_api_scope():
    funcs = {f.spec.id: f for f in list_functions() if f.spec.app == "salesforce"}
    for w in ("bulk_query.get", "bulk_query.results", "actions.standard_list", "actions.custom_list"):
        spec = funcs[f"salesforce.{w}"].spec
        assert spec.scopes == ["api"] and spec.verb.value == "read" and len(spec.description) >= 200


@pytest.mark.asyncio
async def test_bulk_query_get_maps_the_job_and_not_found(db):
    job = {"id": JOB, "operation": "query", "object": "Account", "state": "Failed", "createdDate": "2026-10-09T15:54:50.000+0000", "systemModstamp": "2026-10-09T15:54:55.000+0000",
           "numberRecordsProcessed": 0, "totalProcessingTime": 10, "contentType": "CSV", "errorMessage": "boom"}
    t, _ = org_api({f"{DATA}/jobs/query/{JOB}": httpx.Response(200, json=job)})
    res = await run(db, "salesforce.bulk_query.get", {"job_id": JOB}, t)
    assert res.ok, res.error
    assert res.data["state"] == "Failed" and res.data["object"] == "Account" and res.data["error_message"] == "boom" and res.data["content_type"] == "CSV"
    assert (await run(db, "salesforce.bulk_query.get", {"job_id": "750" + "0" * 12 + "AAA"}, t)).error.code == ErrorCode.not_found
    assert (await run(db, "salesforce.bulk_query.get", {"job_id": "../x"}, t)).error.code == ErrorCode.invalid_input


@pytest.mark.asyncio
async def test_bulk_query_results_parses_csv_with_quotes_commas_and_multiline_values(db):
    body = '﻿"Id","Name","Description"\n"001A","Acme, Inc.","Line one\nline ""two"""\n"001B","Beta",""\n'
    t, seen = org_api({f"{DATA}/jobs/query/{JOB}/results": csv_response(body)})
    res = await run(db, "salesforce.bulk_query.results", {"job_id": JOB, "max_records": 2}, t)
    assert res.ok, res.error
    assert dict(seen[-1].url.params) == {"maxRecords": "2"} and seen[-1].headers["accept"] == "text/csv"
    assert res.data["columns"] == ["Id", "Name", "Description"] and res.data["number_of_records"] == 2
    assert res.data["records"] == [{"Id": "001A", "Name": "Acme, Inc.", "Description": 'Line one\nline "two"'}, {"Id": "001B", "Name": "Beta", "Description": ""}]
    assert res.data["next_locator"] is None  # Salesforce manda "null" cuando no hay mas paginas


@pytest.mark.asyncio
async def test_bulk_query_results_returns_the_next_locator_and_sends_it_back(db):
    t, seen = org_api({f"{DATA}/jobs/query/{JOB}/results": csv_response('"Id"\n"1"\n"2"\n', locator="MjowR2FmajAwMDAwTlk4NXhDQUQ6MA")})
    res = await run(db, "salesforce.bulk_query.results", {"job_id": JOB, "max_records": 2}, t)
    assert res.data["next_locator"] == "MjowR2FmajAwMDAwTlk4NXhDQUQ6MA"
    await run(db, "salesforce.bulk_query.results", {"job_id": JOB, "locator": res.data["next_locator"]}, t)
    assert dict(seen[-1].url.params) == {"maxRecords": "200", "locator": "MjowR2FmajAwMDAwTlk4NXhDQUQ6MA"}


@pytest.mark.asyncio
async def test_bulk_query_results_empty_result_and_job_not_complete(db):
    t, _ = org_api({f"{DATA}/jobs/query/{JOB}/results": csv_response('"Id","Name"\n')})
    res = await run(db, "salesforce.bulk_query.results", {"job_id": JOB}, t)
    assert res.ok and res.data == {"columns": ["Id", "Name"], "records": [], "number_of_records": 0, "next_locator": None}
    t, _ = org_api({f"{DATA}/jobs/query/{JOB}/results": httpx.Response(400, json=[{"errorCode": "JOB_NOT_COMPLETE", "message": "Current status: IN_PROGRESS"}])})
    res = await run(db, "salesforce.bulk_query.results", {"job_id": JOB}, t)
    assert res.error.code == ErrorCode.invalid_input and "IN_PROGRESS" in res.error.message
    for bad in ({"max_records": 0}, {"max_records": 2001}, {"locator": "bad!"}, {"job_id": "x"}):
        res = await run(db, "salesforce.bulk_query.results", {"job_id": JOB, **bad}, t)
        assert res.error.code == ErrorCode.invalid_input, bad


@pytest.mark.asyncio
async def test_actions_standard_list(db):
    body = {"actions": [{"label": "Post to Chatter", "name": "chatterPost", "type": "CHATTERPOST", "url": f"{DATA}/actions/standard/chatterPost"}, {"label": "sin nombre"}]}
    t, _ = org_api({f"{DATA}/actions/standard": httpx.Response(200, json=body)})
    res = await run(db, "salesforce.actions.standard_list", {}, t)
    assert res.ok, res.error
    assert res.data == {"actions": [{"name": "chatterPost", "label": "Post to Chatter", "type": "CHATTERPOST", "url": f"{DATA}/actions/standard/chatterPost"}]}


@pytest.mark.asyncio
async def test_actions_custom_list_categories_actions_and_quick_actions(db):
    cats = {"flow": f"{DATA}/actions/custom/flow", "apex": f"{DATA}/actions/custom/apex"}
    flows = {"actions": [{"label": "Cancel Order", "name": "Cancel_Order", "type": "FLOW", "url": f"{DATA}/actions/custom/flow/Cancel_Order"}]}
    quick = {"Case": f"{DATA}/actions/custom/quickAction/Case"}
    t, seen = org_api({f"{DATA}/actions/custom": httpx.Response(200, json=cats), f"{DATA}/actions/custom/flow": httpx.Response(200, json=flows),
                       f"{DATA}/actions/custom/apex": httpx.Response(200, json={"actions": []}), f"{DATA}/actions/custom/quickAction": httpx.Response(200, json=quick)})
    assert (await run(db, "salesforce.actions.custom_list", {}, t)).data == {"categories": cats, "actions": []}
    res = await run(db, "salesforce.actions.custom_list", {"action_type": "flow"}, t)
    assert res.data["categories"] == {} and res.data["actions"][0]["name"] == "Cancel_Order" and seen[-1].url.path == f"{DATA}/actions/custom/flow"
    assert (await run(db, "salesforce.actions.custom_list", {"action_type": "apex"}, t)).data == {"categories": {}, "actions": []}
    assert (await run(db, "salesforce.actions.custom_list", {"action_type": "quickAction"}, t)).data == {"categories": quick, "actions": []}
    assert (await run(db, "salesforce.actions.custom_list", {"action_type": "nope"}, t)).error.code == ErrorCode.not_found
    assert (await run(db, "salesforce.actions.custom_list", {"action_type": "a/b"}, t)).error.code == ErrorCode.invalid_input
