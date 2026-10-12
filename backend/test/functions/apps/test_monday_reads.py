import json

import pytest

from app.functions.spec import ErrorCode
from test_monday import _registry, api, db, gql, run  # noqa: F401  (fixtures)

P = {"id": 4012689, "name": "Ana Perez"}


def sent(seen, i=0):
    return json.loads(seen[i].content)


@pytest.mark.asyncio
@pytest.mark.parametrize("fid,args,data,expected", [
    ("monday.team.list", {}, {"teams": [{"id": 1, "name": "Ventas", "picture_url": None, "owners": [P], "users": [P]}]},
     {"teams": [{"id": "1", "name": "Ventas", "picture_url": None, "owners": [{"id": "4012689", "name": "Ana Perez"}],
                 "members": [{"id": "4012689", "name": "Ana Perez"}]}]}),
    ("monday.board.export_status", {"job_id": "j1"}, {"export_job_status": {"status": "RUNNING", "download_url": None}},
     {"status": "RUNNING", "download_url": None, "failure_reason": None, "failure_message": None}),
    ("monday.subitem.list", {"item_id": "987"}, {"items": [{"subitems": [{"id": 5, "name": "Sub", "state": "active", "column_values": []}]}]},
     {"subitems": [{"id": "5", "name": "Sub", "state": "active", "created_at": None, "updated_at": None, "column_values": []}]}),
    ("monday.column.list", {"board_id": "123"}, {"boards": [{"columns": [{"id": "status", "title": "Status", "type": "status",
                                                                          "settings": {"labels": {"1": "Done"}}}]}]},
     {"columns": [{"id": "status", "title": "Status", "type": "status", "description": None, "width": None, "archived": False,
                   "settings": {"labels": {"1": "Done"}}}]}),
    ("monday.group.list", {"board_id": "123"}, {"boards": [{"groups": [{"id": "topics", "title": "Nuevos", "position": 65536}]}]},
     {"groups": [{"id": "topics", "title": "Nuevos", "color": None, "position": "65536", "archived": False}]}),
    ("monday.webhook.list", {"board_id": "123"}, {"webhooks": [{"id": 12, "board_id": 123, "event": "create_item", "config": None}]},
     {"webhooks": [{"id": "12", "board_id": "123", "event": "create_item", "config": None}]}),
    ("monday.template.install_status", {"process_id": "p1"},
     {"template_installation_status": {"status": "IN_PROGRESS", "is_complete": False, "is_failed": False, "board_ids": [111]}},
     {"status": "IN_PROGRESS", "is_complete": False, "is_failed": False, "board_ids": ["111"]}),
    ("monday.object_relation.list", {"object_id": "123"},
     {"object_relations": [{"id": 27, "source_object_id": 123, "target_id": 456, "target_object_type": "BOARD", "kind": "dependency"}]},
     {"relations": [{"id": "27", "source_object_id": "123", "target_id": "456", "target_object_type": "BOARD", "kind": "dependency"}]}),
])
async def test_reads_map_the_response(db, fid, args, data, expected):
    t, _ = api(gql(data))
    res = await run(fid, args, db, t)
    assert res.ok, res.error
    assert res.data == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("fid,args,data", [
    ("monday.subitem.list", {"item_id": "999"}, {"items": []}),
    ("monday.column.list", {"board_id": "999"}, {"boards": []}),
    ("monday.group.list", {"board_id": "999"}, {"boards": []}),
    ("monday.activity.list_board", {"board_id": "999"}, {"boards": []}),
    ("monday.update.list", {"board_id": "999"}, {"boards": []}),
    ("monday.board.export_status", {"job_id": "x"}, {"export_job_status": None}),
    ("monday.template.install_status", {"process_id": "x"}, {"template_installation_status": None}),
    ("monday.form.get", {"form_token": "x"}, {"form": None}),
    ("monday.doc.version_history", {"doc_id": "1"}, {"doc_version_history": None}),
    ("monday.doc.version_diff", {"doc_id": "1", "date": "2026-02-10", "prev_date": "2026-02-01"}, {"doc_version_diff": None}),
])
async def test_missing_object_is_not_found(db, fid, args, data):
    t, _ = api(gql(data))
    assert (await run(fid, args, db, t)).error.code == ErrorCode.not_found


@pytest.mark.asyncio
@pytest.mark.parametrize("fid,args", [
    ("monday.update.list", {"item_id": "1", "board_id": "2"}),
    ("monday.update.list", {"limit": 101}),
    ("monday.aggregate.calculate", {"board_id": "123", "function": "SUM"}),
    ("monday.aggregate.calculate", {"board_id": "123", "column_id": "bad id"}),
    ("monday.search.query", {"query": "x", "limit": 21}),
    ("monday.form.get", {"form_token": "a b"}),
    ("monday.column.list", {"board_id": "abc"}),
])
async def test_invalid_input_never_calls_monday(db, fid, args):
    t, seen = api(gql({}))
    assert (await run(fid, args, db, t)).error.code == ErrorCode.invalid_input
    assert seen == []


@pytest.mark.asyncio
async def test_update_list_by_item_board_or_account(db):
    upd = {"id": 1, "text_body": "Hola", "item_id": 987, "creator": P, "replies": [{"id": 2, "text_body": "Ok", "creator": None}]}

    def respond(body):
        if "items(ids" in body["query"]:
            return gql({"items": [{"updates": [upd]}]})
        if "boards(ids" in body["query"]:
            return gql({"boards": [{"updates": [upd]}]})
        return gql({"updates": [upd]})

    t, seen = api(respond)
    by_item = await run("monday.update.list", {"item_id": "987", "limit": 5}, db, t)
    assert sent(seen, 0)["variables"] == {"limit": 5, "page": 1, "ids": ["987"]}
    assert by_item.ok and by_item.data["updates"][0]["text"] == "Hola" and by_item.data["updates"][0]["item_id"] == "987"
    assert by_item.data["updates"][0]["replies"] == [{"id": "2", "text": "Ok", "created_at": None, "creator": None}]
    assert (await run("monday.update.list", {"board_id": "123"}, db, t)).ok and "boards(ids" in sent(seen, 1)["query"]
    assert (await run("monday.update.list", {}, db, t)).ok and sent(seen, 2)["query"].startswith("query ($limit: Int, $page: Int) { updates(")


@pytest.mark.asyncio
async def test_doc_list_inlines_enum_and_filters(db):
    t, seen = api(gql({"docs": [{"id": 5544, "object_id": 1234500000, "name": "Plan", "workspace_id": None, "created_by": P}]}))
    res = await run("monday.doc.list", {"workspace_ids": ["551234"], "order_by": "used_at"}, db, t)
    query = sent(seen)["query"]
    assert 'docs(limit: 25, page: 1, workspace_ids: ["551234"], order_by: used_at)' in query
    assert res.ok and res.data["docs"][0]["object_id"] == "1234500000" and res.data["docs"][0]["workspace_id"] is None


@pytest.mark.asyncio
async def test_doc_history_and_diff(db):
    def respond(body):
        if "doc_version_diff" in body["query"]:
            return gql({"doc_version_diff": {"doc_id": "1", "blocks": [{"id": "b1", "type": "title", "summary": "Edited",
                                                                          "changes": {"added": False, "deleted": False, "changed": True}}]}})
        return gql({"doc_version_history": {"doc_id": "1", "restoring_points": [{"date": "2026-02-10T10:05:00Z", "user_ids": [4012689], "type": None}]}})

    t, seen = api(respond)
    hist = await run("monday.doc.version_history", {"doc_id": "1", "since": "2026-01-01T00:00:00Z"}, db, t)
    assert 'doc_version_history(doc_id: "1", since: "2026-01-01T00:00:00Z")' in sent(seen, 0)["query"]
    assert hist.ok and hist.data["restoring_points"][0]["user_ids"] == ["4012689"]
    diff = await run("monday.doc.version_diff", {"doc_id": "1", "date": "2026-02-10T10:05:00Z", "prev_date": "2026-02-01T10:00:00Z"}, db, t)
    assert sent(seen, 1)["variables"] == {"doc": "1", "date": "2026-02-10T10:05:00Z", "prev": "2026-02-01T10:00:00Z"}
    assert diff.ok and diff.data["blocks"][0]["changed"] is True and diff.data["blocks"][0]["summary"] == "Edited"


@pytest.mark.asyncio
async def test_folder_list_flattens_relations(db):
    t, seen = api(gql({"folders": [{"id": 7788, "name": "Clientes", "workspace": {"id": 551234}, "parent": None, "owner_id": 4012689,
                                    "children": [{"id": 123, "name": "Pipeline"}, None], "sub_folders": []}]}))
    res = await run("monday.folder.list", {"workspace_ids": ["551234"]}, db, t)
    assert sent(seen)["variables"] == {"limit": 25, "page": 1, "workspace_ids": ["551234"]}
    folder = res.data["folders"][0]
    assert folder["workspace_id"] == "551234" and folder["parent_id"] is None and folder["boards"] == [{"id": "123", "name": "Pipeline"}]


@pytest.mark.asyncio
async def test_notification_list_unread_only(db):
    t, seen = api(gql({"notifications": [{"id": 9, "title": "Hola", "text": "x", "read": False, "board": {"id": 123, "name": "P"}, "item": None}]}))
    res = await run("monday.notification.list", {"unread_only": True, "limit": 5}, db, t)
    assert "notifications(limit: 5, filter_read: true)" in sent(seen)["query"]
    assert res.ok and res.data["notifications"][0]["board"] == {"id": "123", "name": "P"} and res.data["notifications"][0]["item"] is None


@pytest.mark.asyncio
async def test_form_get_maps_camel_case(db):
    t, seen = api(gql({"form": {"id": 1, "token": "tok", "title": "Encuesta", "active": True, "isAnonymous": True, "ownerId": 4012689,
                                "questions": [{"id": "q1", "title": "Nombre", "type": "Name", "required": True, "visible": None}]}}))
    res = await run("monday.form.get", {"form_token": "tok"}, db, t)
    assert sent(seen)["variables"] == {"token": "tok"}
    assert res.ok and res.data["is_anonymous"] is True and res.data["owner_id"] == "4012689" and res.data["questions"][0]["visible"] is True


@pytest.mark.asyncio
async def test_search_queries_only_requested_kinds_and_escapes_text(db):
    t, seen = api(gql({"search": {"items": {"results": [{"id": 987, "indexed_data": {"name": "Cliente", "board_id": 123, "url": "u"}}]},
                                  "updates": {"results": [{"id": 3, "indexed_data": {"body": "texto", "item_id": 987, "board_id": 123}}]}}}))
    res = await run("monday.search.query", {"query": 'Cliente "Demo"', "types": ["items", "updates"], "board_ids": ["123"], "workspace_ids": ["9"]}, db, t)
    query = sent(seen)["query"]
    assert 'items(query: "Cliente \\"Demo\\"", limit: 10, board_ids: ["123"], workspace_ids: ["9"])' in query
    assert 'updates(query: "Cliente \\"Demo\\"", limit: 10, board_ids: ["123"])' in query and "boards(" not in query and "docs(" not in query
    assert res.ok and [h["type"] for h in res.data["hits"]] == ["item", "update"]
    assert res.data["hits"][0]["board_id"] == "123" and res.data["hits"][1]["name"] == "texto" and res.data["hits"][1]["item_id"] == "987"


@pytest.mark.asyncio
async def test_aggregate_builds_query_input_and_reads_groups(db):
    t, seen = api(gql({"aggregate": {"results": [
        {"entries": [{"alias": "result", "value": {"result": 1500}}, {"alias": "group", "value": {"value": "#00c875"}}]},
        {"entries": [{"alias": "result", "value": {"result": None}}, {"alias": "group", "value": {"value": None}}]}]}}))
    res = await run("monday.aggregate.calculate", {"board_id": "123", "function": "SUM", "column_id": "numbers", "group_by_column_id": "status"}, db, t)
    q = sent(seen)["variables"]["q"]
    assert q["from"] == {"type": "TABLE", "id": "123"} and q["group_by"] == [{"column_id": "status", "limit": 10}]
    assert q["select"][0] == {"type": "FUNCTION", "as": "result", "function": {"function": "SUM", "params": [
        {"type": "COLUMN", "column": {"column_id": "numbers"}, "as": "numbers"}]}}
    assert q["select"][1] == {"type": "COLUMN", "column": {"column_id": "status"}, "as": "group"}
    assert res.ok and res.data["groups"] == [{"group": "#00c875", "result": 1500.0}, {"group": None, "result": None}]


@pytest.mark.asyncio
async def test_aggregate_count_items_without_grouping(db):
    t, seen = api(gql({"aggregate": {"results": [{"entries": [{"alias": "result", "value": {"result": 12}}]}]}}))
    res = await run("monday.aggregate.calculate", {"board_id": "123"}, db, t)
    q = sent(seen)["variables"]["q"]
    assert "group_by" not in q and q["select"] == [{"type": "FUNCTION", "function": {"function": "COUNT_ITEMS"}, "as": "result"}]
    assert res.data["groups"] == [{"group": None, "result": 12.0}]


@pytest.mark.asyncio
async def test_activity_list_inlines_filters(db):
    t, seen = api(gql({"boards": [{"activity_logs": [{"id": "a1", "event": "create_pulse", "entity": "pulse", "user_id": 4012689,
                                                      "created_at": "17409456000000000", "data": "{}"}]}]}))
    res = await run("monday.activity.list_board", {"board_id": "123", "from_date": "2026-03-01T00:00:00Z", "user_ids": ["4012689"]}, db, t)
    body = sent(seen)
    assert body["variables"] == {"ids": ["123"]}
    assert 'activity_logs(from: "2026-03-01T00:00:00Z", user_ids: ["4012689"], limit: 25, page: 1)' in body["query"]
    assert res.ok and res.data["events"][0]["user_id"] == "4012689"


@pytest.mark.asyncio
async def test_audit_list_pagination(db):
    t, seen = api(gql({"audit_logs": {"logs": [{"timestamp": "2026-03-02T09:00:00Z", "event": "login", "ip_address": "203.0.113.5",
                                                "user_agent": "Chrome", "user": {"id": 1, "name": "Ana", "email": "ana@empresa.test"}}],
                                      "pagination": {"has_more_pages": True, "next_page_number": 2}}}))
    res = await run("monday.audit.list", {"events": ["login"]}, db, t)
    assert 'audit_logs(events: ["login"], limit: 25, page: 1)' in sent(seen)["query"]
    assert res.ok and res.data["next_page"] == 2 and res.data["logs"][0]["user_email"] == "ana@empresa.test"


@pytest.mark.asyncio
async def test_object_relation_list_inlines_enums(db):
    t, seen = api(gql({"object_relations": []}))
    await run("monday.object_relation.list", {"object_id": "123", "kind": "DEPENDENCY", "direction": "INCOMING"}, db, t)
    assert 'object_relations(object_id: "123", kind: DEPENDENCY, direction: INCOMING)' in sent(seen)["query"]
