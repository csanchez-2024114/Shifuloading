"""Pruebas simuladas (sin red) de las funciones de ClickUp: HTTP con httpx.MockTransport y Mongo simulado.

Las rutas esperadas salen de las especificaciones OpenAPI oficiales de ClickUp (v2 y v3), no del catalogo.
"""
import json

import httpx
import pytest
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient

from app.core.constants import Collections
from app.functions.registry import _FUNCS, get_function, load_all
from app.functions.runner import execute
from app.functions.spec import ErrorCode
from functions_helpers import connection_doc

COL = Collections.USER_CONNECTED_ACCOUNTS
V2 = "/api/v2"
V3 = "/api/v3/workspaces/9001"
WS = {"workspace_id": "9001"}


@pytest.fixture(autouse=True, scope="module")
def _registry():
    load_all()


@pytest_asyncio.fixture
async def db():
    d = AsyncMongoMockClient()["clickup_test"]
    await d[COL].insert_one(connection_doc(account="123456", provider="clickup", token="pk_old-token"))
    return d


def api(routes):
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        r = routes.get(req.url.path, httpx.Response(404, json={"err": "Not found", "ECODE": "ITEM_015"}))
        return r(req) if callable(r) else r

    return httpx.MockTransport(handler), seen


async def run(fid, args, db, t, **kw):
    return await execute(get_function(fid), args, db=db, user_id="u1", transport=t, **kw)


def ok(body):
    return httpx.Response(200, json=body)


# --- whoami -----------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_whoami_returns_identity_and_matches_stored_account(db):
    t, seen = api({f"{V2}/user": ok({"user": {"id": 123456, "username": "John", "email": "john@example.com", "color": "#fff", "timezone": "UTC"}})})
    res = await run("clickup.user.get", {}, db, t)
    assert res.ok and res.data["account_id"] == "123456" and res.data["display_name"] == "John" and res.data["email"] == "john@example.com"
    assert res.data["account_id"] == res.meta.account_id  # el id numerico de ClickUp se normaliza a texto
    assert seen[0].method == "GET" and seen[0].headers["authorization"] == "pk_old-token"  # token crudo, sin "Bearer"


@pytest.mark.asyncio
async def test_whoami_without_user_id_is_upstream_changed(db):
    t, _ = api({f"{V2}/user": ok({"user": {}})})
    assert (await run("clickup.user.get", {}, db, t)).error.code == ErrorCode.upstream_changed


@pytest.mark.asyncio
async def test_whoami_non_json_is_upstream_changed(db):
    t, _ = api({f"{V2}/user": httpx.Response(200, text="<html>nope</html>")})
    assert (await run("clickup.user.get", {}, db, t)).error.code == ErrorCode.upstream_changed


@pytest.mark.asyncio
async def test_revoked_token_marks_the_account_expired(db):
    t, _ = api({f"{V2}/user": httpx.Response(401, json={"err": "Token not found", "ECODE": "OAUTH_025"})})
    res = await run("clickup.user.get", {}, db, t)
    assert res.error.code == ErrorCode.auth_expired and res.error.user_action == "reconnect_app"
    assert (await db[COL].find_one({"account_id": "123456"}))["status"] == "expired"


@pytest.mark.asyncio
@pytest.mark.parametrize("ecode", ["OAUTH_023", "OAUTH_026", "OAUTH_027", "OAUTH_029", "OAUTH_033", "OAUTH_045"])
async def test_workspace_not_authorized_is_missing_scope_and_account_stays_active(db, ecode):
    t, seen = api({f"{V2}/team/9001/plan": httpx.Response(401, json={"err": "Team not authorized", "ECODE": ecode})})
    res = await run("clickup.workspace.get_plan", WS, db, t)
    assert res.error.code == ErrorCode.missing_scope and res.error.user_action == "grant_scopes"
    assert len(seen) == 1 and (await db[COL].find_one({"account_id": "123456"}))["status"] == "active"


@pytest.mark.asyncio
async def test_forbidden_by_plan_is_missing_scope(db):
    t, _ = api({f"{V2}/team/9001/customroles": httpx.Response(403, json={"err": "Not available on your plan", "ECODE": "ACCESS_012"})})
    res = await run("clickup.workspace.get_roles", WS, db, t)
    assert res.error.code == ErrorCode.missing_scope and (await db[COL].find_one({"account_id": "123456"}))["status"] == "active"


# --- Todas las funciones: forma de la peticion y de la respuesta ------------------------------------

ID_LIST = {"list_id": "901"}
C = ("comments", [{"id": "c1", "comment_text": "hi", "date": "1767225600000"}])

# (id, entrada, ruta esperada, parametros de la query esperados, cuerpo de respuesta, comprobacion sobre res.data)
CASES = [
    ("clickup.workspaces.list", {}, f"{V2}/team", {}, {"teams": [{"id": "1", "name": "A", "members": [{"user": {}}, {"user": {}}]}]},
     lambda d: d["teams"][0]["id"] == "1" and d["teams"][0]["member_count"] == 2 and "members" not in d["teams"][0]),
    ("clickup.workspace.get_plan", WS, f"{V2}/team/9001/plan", {}, {"plan_name": "Business", "plan_id": 3},
     lambda d: d["plan_name"] == "Business" and d["plan_id"] == "3"),
    ("clickup.workspace.get_seats", WS, f"{V2}/team/9001/seats", {}, {"members": {"filled_members_seats": 3, "total_member_seats": 10, "empty_member_seats": 7}, "guests": {}},
     lambda d: d["members"]["empty_member_seats"] == 7),
    ("clickup.spaces.get", {"space_id": "321"}, f"{V2}/space/321", {}, {"id": "321", "name": "Eng", "private": False},
     lambda d: d["name"] == "Eng"),
    ("clickup.spaces.get_views", {"space_id": "321"}, f"{V2}/space/321/view", {}, {"views": [{"id": "v1", "name": "Board", "type": "board"}]},
     lambda d: d["views"][0]["type"] == "board"),
    ("clickup.folders.get", {"folder_id": "456"}, f"{V2}/folder/456", {}, {"id": "456", "name": "Backlog", "task_count": "12", "lists": [{"id": "901"}]},
     lambda d: d["name"] == "Backlog" and d["lists"][0]["id"] == "901"),
    ("clickup.folders.get_views", {"folder_id": "456"}, f"{V2}/folder/456/view", {}, {"views": [{"id": "v2"}]}, lambda d: d["views"][0]["id"] == "v2"),
    ("clickup.lists.list_folderless", {"space_id": "321", "archived": True}, f"{V2}/space/321/list", {"archived": "true"}, {"lists": [{"id": "901", "name": "Inbox"}]},
     lambda d: d["lists"][0]["name"] == "Inbox"),
    ("clickup.lists.get", ID_LIST, f"{V2}/list/901", {}, {"id": "901", "name": "Sprint", "task_count": 10},
     lambda d: d["task_count"] == "10"),
    ("clickup.lists.get_members", ID_LIST, f"{V2}/list/901/member", {}, {"members": [{"id": 12, "username": "ana"}]}, lambda d: d["members"][0]["username"] == "ana"),
    ("clickup.lists.get_comments", ID_LIST, f"{V2}/list/901/comment", {}, dict([C]), lambda d: d["comments"][0]["id"] == "c1" and d["next_start"] is None),
    ("clickup.lists.get_views", ID_LIST, f"{V2}/list/901/view", {}, {"views": [{"id": "v3"}]}, lambda d: d["views"][0]["id"] == "v3"),
    ("clickup.tags.list", {"space_id": "321"}, f"{V2}/space/321/tag", {}, {"tags": [{"name": "bug"}]}, lambda d: d["tags"][0]["name"] == "bug"),
    ("clickup.tasks.list_workspace", {**WS, "page": 2, "statuses": ["to do"], "assignees": ["12"], "include_closed": True, "folder_ids": ["456"], "due_date_lt": 99},
     f"{V2}/team/9001/task", {"page": "2", "statuses[]": "to do", "assignees[]": "12", "include_closed": "true", "project_ids[]": "456", "due_date_lt": "99"},
     {"tasks": [{"id": "t1", "name": "Fix"}], "last_page": True}, lambda d: d["tasks"][0]["id"] == "t1" and d["last_page"] is True),
    ("clickup.tasks.get_time_in_status", {"task_id": "t1"}, f"{V2}/task/t1/time_in_status", {},
     {"current_status": {"status": "open", "total_time": {"by_minute": 5}}, "status_history": [{"status": "to do"}]},
     lambda d: d["current_status"]["status"] == "open" and d["status_history"][0]["status"] == "to do"),
    ("clickup.time_in_status.get_task", {"task_id": "t1"}, f"{V2}/task/t1/time_in_status", {}, {"current_status": {"status": "open"}, "status_history": []},
     lambda d: d["current_status"]["status"] == "open"),
    ("clickup.time_in_status.get_workspace", {"task_ids": ["t1", "t2"]}, f"{V2}/task/bulk_time_in_status/task_ids", {"task_ids": "t1"},
     {"t1": {"current_status": {"status": "open"}, "status_history": []}, "t2": {"current_status": {}, "status_history": []}}, lambda d: set(d["tasks"]) == {"t1", "t2"}),
    ("clickup.comments.list", {"task_id": "t1"}, f"{V2}/task/t1/comment", {}, dict([C]), lambda d: d["comments"][0]["comment_text"] == "hi"),
    ("clickup.comments.list_replies", {"comment_id": "c1"}, f"{V2}/comment/c1/reply", {}, {"comments": [{"id": "c2", "comment_text": "re"}]},
     lambda d: d["replies"][0]["id"] == "c2"),
    ("clickup.attachments.list", {**WS, "entity_id": "t1", "limit": 10}, f"{V3}/tasks/t1/attachments", {"limit": "10"},
     {"data": [{"id": "a1", "title": "spec.pdf"}], "next_cursor": "NXT"}, lambda d: d["attachments"][0]["title"] == "spec.pdf" and d["next_cursor"] == "NXT"),
    ("clickup.task_members.list", {"task_id": "t1"}, f"{V2}/task/t1/member", {}, {"members": [{"id": 1, "username": "ana"}]}, lambda d: d["members"][0]["id"] == 1),
    ("clickup.custom_fields.list_list", {**ID_LIST, "include_applied_objects": True}, f"{V2}/list/901/field", {"include_applied_objects": "true"},
     {"fields": [{"id": "cf1", "name": "Sev", "type": "drop_down"}]}, lambda d: d["fields"][0]["type"] == "drop_down"),
    ("clickup.custom_fields.list_folder", {"folder_id": "456"}, f"{V2}/folder/456/field", {}, {"fields": [{"id": "cf2"}]}, lambda d: d["fields"][0]["id"] == "cf2"),
    ("clickup.custom_fields.list_space", {"space_id": "321"}, f"{V2}/space/321/field", {}, {"fields": [{"id": "cf3"}]}, lambda d: d["fields"][0]["id"] == "cf3"),
    ("clickup.custom_fields.list_workspace", WS, f"{V2}/team/9001/field", {}, {"fields": [{"id": "cf4"}]}, lambda d: d["fields"][0]["id"] == "cf4"),
    ("clickup.custom_items.list", WS, f"{V2}/team/9001/custom_item", {}, {"custom_items": [{"id": 1001, "name": "Bug"}]}, lambda d: d["custom_items"][0]["name"] == "Bug"),
    ("clickup.time_entries.list", {**WS, "start_date": 1, "end_date": 2, "assignee": "12,13", "is_billable": False}, f"{V2}/team/9001/time_entries",
     {"start_date": "1", "end_date": "2", "assignee": "12,13", "is_billable": "false"}, {"data": [{"id": "te1", "duration": "3600000"}]},
     lambda d: d["time_entries"][0]["id"] == "te1"),
    ("clickup.time_entries.get", {**WS, "time_entry_id": "te1"}, f"{V2}/team/9001/time_entries/te1", {}, {"data": {"id": "te1", "billable": True}},
     lambda d: d["time_entry"]["id"] == "te1"),
    ("clickup.time_entries.get", {**WS, "time_entry_id": "te1"}, f"{V2}/team/9001/time_entries/te1", {}, {"data": [{"id": "te1"}]},
     lambda d: d["time_entry"]["id"] == "te1"),
    ("clickup.time_entries.get_history", {**WS, "time_entry_id": "te1"}, f"{V2}/team/9001/time_entries/te1/history", {}, {"data": [{"id": "h1", "field": "duration"}]},
     lambda d: d["changes"][0]["id"] == "h1"),
    ("clickup.timer.get_running", {**WS, "assignee": 12}, f"{V2}/team/9001/time_entries/current", {"assignee": "12"},
     {"data": {"id": "te9", "duration": -5, "task": {"id": "t1"}}}, lambda d: d["running"] is True and d["timer"]["id"] == "te9"),
    ("clickup.timer.get_running", WS, f"{V2}/team/9001/time_entries/current", {}, {"data": None}, lambda d: d["running"] is False and d["timer"] is None),
    ("clickup.time_entries.list_tags", WS, f"{V2}/team/9001/time_entries/tags", {}, {"data": [{"name": "billable", "creator": 12}]}, lambda d: d["tags"][0]["name"] == "billable"),
    ("clickup.views.list_workspace", WS, f"{V2}/team/9001/view", {}, {"views": [{"id": "w1"}]}, lambda d: d["views"][0]["id"] == "w1"),
    ("clickup.views.list_space", {"space_id": "321"}, f"{V2}/space/321/view", {}, {"views": [{"id": "s1"}]}, lambda d: d["views"][0]["id"] == "s1"),
    ("clickup.views.list_folder", {"folder_id": "456"}, f"{V2}/folder/456/view", {}, {"views": [{"id": "f1"}]}, lambda d: d["views"][0]["id"] == "f1"),
    ("clickup.views.list_list", ID_LIST, f"{V2}/list/901/view", {}, {"views": [{"id": "l1"}]}, lambda d: d["views"][0]["id"] == "l1"),
    ("clickup.views.get", {"view_id": "3c-106"}, f"{V2}/view/3c-106", {}, {"view": {"id": "3c-106", "type": "board"}}, lambda d: d["view"]["type"] == "board"),
    ("clickup.views.get_tasks", {"view_id": "3c-106", "page": 1}, f"{V2}/view/3c-106/task", {"page": "1"}, {"tasks": [{"id": "t1"}], "last_page": True},
     lambda d: d["tasks"][0]["id"] == "t1" and d["last_page"] is True),
    ("clickup.goals.list", {**WS, "include_completed": True}, f"{V2}/team/9001/goal", {"include_completed": "true"}, {"goals": [{"id": "g1"}], "folders": []},
     lambda d: d["goals"][0]["id"] == "g1"),
    ("clickup.goals.get", {"goal_id": "e53a033c-900e-462d-a849-4a216b06d930"}, f"{V2}/goal/e53a033c-900e-462d-a849-4a216b06d930", {},
     {"goal": {"id": "g1", "name": "OKR"}}, lambda d: d["goal"]["name"] == "OKR"),
    ("clickup.workspace.get_groups", WS, f"{V2}/group", {"team_id": "9001"}, {"groups": [{"id": "g1", "name": "Design"}]}, lambda d: d["groups"][0]["name"] == "Design"),
    ("clickup.workspace.get_roles", {**WS, "include_members": True}, f"{V2}/team/9001/customroles", {"include_members": "true"},
     {"custom_roles": [{"id": 77, "name": "Contractor"}]}, lambda d: d["custom_roles"][0]["name"] == "Contractor"),
    ("clickup.guests.get", {**WS, "guest_id": "555"}, f"{V2}/team/9001/guest/555", {}, {"guest": {"user": {"id": 555}}}, lambda d: d["guest"]["user"]["id"] == 555),
    ("clickup.workspace.get_shared_hierarchy", WS, f"{V2}/team/9001/shared", {}, {"shared": {"tasks": ["t1"], "lists": [{"id": "901"}], "folders": []}},
     lambda d: d["tasks"] == ["t1"] and d["lists"][0]["id"] == "901"),
    ("clickup.webhooks.list", WS, f"{V2}/team/9001/webhook", {}, {"webhooks": [{"id": "wh1", "endpoint": "https://x.test/h", "secret": "SHH"}]},
     lambda d: d["webhooks"][0]["endpoint"] == "https://x.test/h" and "secret" not in d["webhooks"][0]),
    ("clickup.workspace.get_post_types", WS, f"{V3}/comments/types/post/subtypes", {}, {"Announcement": "sub-1"}, lambda d: d["subtypes"]["Announcement"] == "sub-1"),
    ("clickup.channels.list", {**WS, "limit": 5, "is_follower": True}, f"{V3}/chat/channels", {"limit": "5", "is_follower": "true"},
     {"data": [{"id": "ch1", "name": "general"}], "next_cursor": "N"}, lambda d: d["channels"][0]["id"] == "ch1" and d["next_cursor"] == "N"),
    ("clickup.channels.get", {**WS, "channel_id": "ch1"}, f"{V3}/chat/channels/ch1", {}, {"data": {"id": "ch1", "name": "general"}}, lambda d: d["channel"]["name"] == "general"),
    ("clickup.channels.get_followers", {**WS, "channel_id": "ch1"}, f"{V3}/chat/channels/ch1/followers", {}, {"data": [{"id": "12"}]}, lambda d: d["followers"][0]["id"] == "12"),
    ("clickup.channels.get_members", {**WS, "channel_id": "ch1", "cursor": "C"}, f"{V3}/chat/channels/ch1/members", {"cursor": "C"}, {"data": [{"id": "13"}]},
     lambda d: d["members"][0]["id"] == "13" and d["next_cursor"] is None),
    ("clickup.messages.list", {**WS, "channel_id": "ch1", "content_format": "text/plain"}, f"{V3}/chat/channels/ch1/messages", {"content_format": "text/plain"},
     {"data": [{"id": "m1", "content": "hello"}]}, lambda d: d["messages"][0]["content"] == "hello"),
    ("clickup.messages.get_reactions", {**WS, "message_id": "m1"}, f"{V3}/chat/messages/m1/reactions", {}, {"data": [{"reaction": "thumbsup", "user_id": "12"}]},
     lambda d: d["reactions"][0]["reaction"] == "thumbsup"),
    ("clickup.messages.list_replies", {**WS, "message_id": "m1"}, f"{V3}/chat/messages/m1/replies", {}, {"data": [{"id": "m2"}]}, lambda d: d["replies"][0]["id"] == "m2"),
    ("clickup.messages.get_tagged_users", {**WS, "message_id": "m1"}, f"{V3}/chat/messages/m1/tagged_users", {}, {"data": [{"id": "12"}]},
     lambda d: d["tagged_users"][0]["id"] == "12"),
    ("clickup.docs.get_pages", {**WS, "doc_id": "8cnn-1", "max_page_depth": 1}, f"{V3}/docs/8cnn-1/pages", {"max_page_depth": "1", "content_format": "text/md"},
     [{"id": "p1", "name": "Overview", "pages": []}], lambda d: d["pages"][0]["name"] == "Overview"),
    ("clickup.docs.get_page_listing", {**WS, "doc_id": "8cnn-1"}, f"{V3}/docs/8cnn-1/page_listing", {"max_page_depth": "-1"},
     [{"id": "p1", "name": "Overview", "pages": [{"id": "p2", "name": "Goals"}]}], lambda d: d["pages"][0]["pages"][0]["id"] == "p2"),
    ("clickup.pages.get", {**WS, "doc_id": "8cnn-1", "page_id": "p1"}, f"{V3}/docs/8cnn-1/pages/p1", {"content_format": "text/md"},
     {"id": "p1", "name": "Overview", "content": "# Hi"}, lambda d: d["page"]["content"] == "# Hi"),
    ("clickup.task_templates.list", {**WS, "page": 1}, f"{V2}/team/9001/taskTemplate", {"page": "1"}, {"templates": [{"id": "t-1", "name": "Bug"}]}, lambda d: d["templates"][0]["name"] == "Bug"),
    ("clickup.list_templates.list", WS, f"{V2}/team/9001/list_template", {}, {"templates": [{"id": "lt-1", "name": "Sprint"}]}, lambda d: d["templates"][0]["id"] == "lt-1"),
    ("clickup.folder_templates.list", WS, f"{V2}/team/9001/folder_template", {}, {"templates": [{"id": "ft-1", "name": "Onboarding"}]}, lambda d: d["templates"][0]["id"] == "ft-1"),
    ("clickup.spaces.list", {**WS, "archived": True}, f"{V2}/team/9001/space", {"archived": "true"}, {"spaces": [{"id": "321", "name": "Eng"}]}, lambda d: d["spaces"][0]["name"] == "Eng"),
    ("clickup.folders.list", {"space_id": "321"}, f"{V2}/space/321/folder", {}, {"folders": [{"id": "456", "name": "Backlog"}]}, lambda d: d["folders"][0]["id"] == "456"),
    ("clickup.lists.list", {"folder_id": "456"}, f"{V2}/folder/456/list", {}, {"lists": [{"id": "901", "name": "Sprint 1"}]}, lambda d: d["lists"][0]["name"] == "Sprint 1"),
    ("clickup.tasks.list", {"list_id": "901", "page": 1, "statuses": ["to do"], "assignees": ["12"], "archived": True}, f"{V2}/list/901/task",
     {"page": "1", "statuses[]": "to do", "assignees[]": "12", "archived": "true"}, {"tasks": [{"id": "t1"}], "last_page": False}, lambda d: d["tasks"][0]["id"] == "t1" and d["last_page"] is False),
    ("clickup.tasks.get", {"task_id": "t1", "include_subtasks": True}, f"{V2}/task/t1", {"include_subtasks": "true"}, {"id": "t1", "name": "Fix", "status": {"status": "open"}, "url": "u"},
     lambda d: d["name"] == "Fix" and d["status"]["status"] == "open"),
    ("clickup.members.list", ID_LIST, f"{V2}/list/901/member", {}, {"members": [{"id": 12, "username": "ana"}]}, lambda d: d["members"][0]["id"] == 12),
    ("clickup.docs.get", {**WS, "doc_id": "8cnn-1"}, f"{V3}/docs/8cnn-1", {}, {"id": "8cnn-1", "name": "Guide"}, lambda d: d["doc"]["name"] == "Guide"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("fid,args,path,expect_query,body,check", CASES, ids=[f"{c[0]}#{i}" for i, c in enumerate(CASES)])
async def test_function_builds_the_right_request_and_parses_the_answer(db, fid, args, path, expect_query, body, check):
    t, seen = api({path: ok(body)})
    res = await run(fid, args, db, t)
    assert res.ok, res.error
    assert check(res.data), res.data
    assert len(seen) == 1 and seen[0].method == "GET" and seen[0].url.path == path
    q = seen[0].url.params
    for key, value in expect_query.items():
        assert q.get(key) == value, (key, dict(q))
    assert seen[0].headers["authorization"] == "pk_old-token"


@pytest.mark.asyncio
async def test_audit_logs_posts_a_query_and_is_a_read(db):
    spec = get_function("clickup.audit_logs.create").spec
    assert spec.verb.value == "read" and not spec.exits_outside
    t, seen = api({f"{V3}/auditlogs": ok([{"eventType": "USER_LOGIN", "eventStatus": "success"}])})
    res = await run("clickup.audit_logs.create", {**WS, "event_type": "USER_LOGIN", "user_emails": ["a@x.test"], "page_rows": 5, "page_timestamp": 1700000000000}, db, t)
    assert res.ok and res.data["logs"][0]["eventType"] == "USER_LOGIN"
    sent = json.loads(seen[0].content)
    assert seen[0].method == "POST"
    assert sent == {"filter": {"userEmail": ["a@x.test"], "eventType": "USER_LOGIN"}, "applicability": "auth-and-security",
                    "pagination": {"pageRows": 5, "pageTimestamp": 1700000000000, "pageDirection": "before"}}


# --- Comportamientos concretos ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_comments_page_gives_the_cursor_of_the_oldest_comment_when_the_page_is_full(db):
    full = [{"id": f"c{i}", "comment_text": "x", "date": str(2000 - i)} for i in range(25)]
    t, seen = api({f"{V2}/task/t1/comment": lambda req: ok({"comments": full})})
    res = await run("clickup.comments.list", {"task_id": "t1"}, db, t)
    assert res.data["next_start"] == 2000 - 24 and res.data["next_start_id"] == "c24"
    await run("clickup.comments.list", {"task_id": "t1", "start": 1976, "start_id": "c24"}, db, t)
    assert seen[1].url.params["start"] == "1976" and seen[1].url.params["start_id"] == "c24"


@pytest.mark.asyncio
async def test_tasks_search_filters_by_text_inside_the_page(db):
    tasks = [{"id": "t1", "name": "Fix login BUG"}, {"id": "t2", "name": "Write docs", "text_content": "mentions a bug here"}, {"id": "t3", "name": "Party"}]
    t, seen = api({f"{V2}/team/9001/task": ok({"tasks": tasks, "last_page": False})})
    res = await run("clickup.tasks.search", {**WS, "query": "bug", "tags": ["urgent"]}, db, t)
    assert res.ok and [x["id"] for x in res.data["tasks"]] == ["t1", "t2"] and res.data["scanned"] == 3 and res.data["last_page"] is False
    assert seen[0].url.params["tags[]"] == "urgent" and "query" not in seen[0].url.params  # ClickUp no tiene busqueda por texto: se filtra aqui
    res = await run("clickup.tasks.search", WS, db, t)
    assert len(res.data["tasks"]) == 3


@pytest.mark.asyncio
async def test_multi_value_filters_become_repeated_parameters(db):
    t, seen = api({f"{V2}/team/9001/task": ok({"tasks": []})})
    await run("clickup.tasks.list_workspace", {**WS, "statuses": ["to do", "in progress"]}, db, t)
    assert seen[0].url.params.get_list("statuses[]") == ["to do", "in progress"]


@pytest.mark.asyncio
async def test_bulk_time_in_status_with_custom_ids_sends_the_workspace(db):
    t, seen = api({f"{V2}/task/bulk_time_in_status/task_ids": ok({"DEV-1": {"current_status": {}, "status_history": []}})})
    res = await run("clickup.time_in_status.get_workspace", {"task_ids": ["DEV-1"], "custom_task_ids": True, "workspace_id": "9001"}, db, t)
    assert res.ok and seen[0].url.params["custom_task_ids"] == "true" and seen[0].url.params["team_id"] == "9001"


# --- Entradas invalidas -----------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("fid,args", [
    ("clickup.workspace.get_plan", {}),                                    # falta el id
    ("clickup.workspace.get_plan", {"workspace_id": "../../user"}),        # el id no puede cambiar la ruta
    ("clickup.spaces.get", {"space_id": "1/field"}),
    ("clickup.tasks.list_workspace", {**WS, "page": -1}),
    ("clickup.tasks.list_workspace", {**WS, "order_by": "name"}),
    ("clickup.time_in_status.get_workspace", {"task_ids": []}),
    ("clickup.time_in_status.get_workspace", {"task_ids": ["t"] * 101}),
    ("clickup.attachments.list", {**WS, "entity_id": "t1", "entity_type": "attachments"}),  # el valor viejo (404 en la API real)
    ("clickup.channels.list", {**WS, "limit": 500}),
    ("clickup.messages.list", {**WS, "channel_id": "c", "content_format": "html"}),
    ("clickup.audit_logs.create", {**WS, "applicability": "everything"}),
    ("clickup.views.get_tasks", {"view_id": "v", "page": "x"}),
])
async def test_invalid_input_is_rejected_before_calling_clickup(db, fid, args):
    t, seen = api({})
    res = await run(fid, args, db, t)
    assert res.error.code == ErrorCode.invalid_input and not seen


@pytest.mark.asyncio
async def test_every_function_maps_http_errors(db, monkeypatch):
    """Para cada funcion: 404 -> not_found, 429 -> rate_limited, 500 -> upstream_down (con la entrada de su ejemplo)."""
    monkeypatch.setattr("app.functions.connections.RETRY_DELAY_SECONDS", 0)
    for (fid, _), fn in sorted(_FUNCS.items()):
        if not fid.startswith("clickup."):
            continue
        example = fn.spec.examples[0].input
        for status, code in ((404, ErrorCode.not_found), (429, ErrorCode.rate_limited), (500, ErrorCode.upstream_down)):
            t = httpx.MockTransport(lambda req, s=status: httpx.Response(s, json={"err": "boom"}))
            res = await run(fid, example, db, t)
            assert res.error is not None and res.error.code == code, (fid, status, res)
    assert (await db[COL].find_one({"account_id": "123456"}))["status"] == "active"


def test_clickup_has_all_the_functions_of_tasks_2_to_7():
    wanted = """
    user.get workspaces.list workspace.get_plan workspace.get_seats spaces.get spaces.get_views folders.get folders.get_views lists.list_folderless lists.get
    lists.get_members lists.get_comments lists.get_views tasks.list_workspace tasks.search tasks.get_time_in_status comments.list comments.list_replies
    attachments.list tags.list custom_fields.list_list custom_fields.list_folder custom_fields.list_space custom_fields.list_workspace custom_items.list
    time_entries.list time_entries.get time_entries.get_history timer.get_running time_in_status.get_task time_in_status.get_workspace time_entries.list_tags
    views.list_workspace views.list_space views.list_folder views.list_list views.get views.get_tasks goals.list goals.get workspace.get_groups
    workspace.get_roles guests.get workspace.get_shared_hierarchy task_members.list channels.list channels.get channels.get_followers channels.get_members
    messages.list messages.get_reactions messages.list_replies messages.get_tagged_users workspace.get_post_types docs.get_pages docs.get_page_listing
    pages.get webhooks.list audit_logs.create task_templates.list list_templates.list folder_templates.list spaces.list folders.list folders.create
    lists.list lists.create tasks.list tasks.get tasks.create tasks.assign tasks.update_due_date comments.create members.list docs.search docs.get
    """.split()
    have = {fid for (fid, _) in _FUNCS if fid.startswith("clickup.")}
    assert {f"clickup.{w}" for w in wanted} == have
    assert len(have) == 76


# --- Tarea 7: escritura y migradas ------------------------------------------------------------------

def body_of(req):
    return json.loads(req.content)


@pytest.mark.asyncio
async def test_folders_create_posts_name_and_parent(db):
    t, seen = api({f"{V2}/space/321/folder": ok({"id": "457", "name": "Q4", "lists": []})})
    res = await run("clickup.folders.create", {"space_id": "321", "name": "Q4", "parent_folder_id": "456"}, db, t)
    assert res.ok and res.data["id"] == "457" and seen[0].method == "POST"
    assert body_of(seen[0]) == {"name": "Q4", "parent_folder_id": "456"}


@pytest.mark.asyncio
async def test_lists_create_sends_only_the_given_fields(db):
    t, seen = api({f"{V2}/folder/456/list": ok({"id": "902", "name": "Sprint 12", "task_count": 0})})
    res = await run("clickup.lists.create", {"folder_id": "456", "name": "Sprint 12", "priority": 2, "assignee": 12}, db, t)
    assert res.ok and res.data["id"] == "902" and res.data["task_count"] == "0"
    assert body_of(seen[0]) == {"name": "Sprint 12", "priority": 2, "assignee": 12}


@pytest.mark.asyncio
async def test_tasks_create_builds_the_body(db):
    t, seen = api({f"{V2}/list/901/task": ok({"id": "t9", "name": "Fix login", "status": {"status": "to do"}, "url": "u"})})
    args = {"list_id": "901", "name": "Fix login", "assignees": [12], "tags": ["bug"], "priority": 1, "due_date": 5,
            "custom_fields": [{"id": "cf1", "value": "high"}]}
    res = await run("clickup.tasks.create", args, db, t)
    assert res.ok and res.data["id"] == "t9"
    assert body_of(seen[0]) == {"name": "Fix login", "priority": 1, "due_date": 5, "assignees": [12], "tags": ["bug"],
                                "custom_fields": [{"id": "cf1", "value": "high"}]}


@pytest.mark.asyncio
async def test_assign_and_due_date_are_put_on_the_task(db):
    t, seen = api({f"{V2}/task/t1": ok({"id": "t1", "name": "Fix", "assignees": [{"id": 12}]})})
    res = await run("clickup.tasks.assign", {"task_id": "t1", "user_id": 12, "remove_user_ids": [7]}, db, t)
    assert res.ok and seen[0].method == "PUT" and body_of(seen[0]) == {"assignees": {"add": [12], "rem": [7]}}
    res = await run("clickup.tasks.update_due_date", {"task_id": "t1", "due_date": 1767225600000, "due_date_time": True}, db, t)
    assert res.ok and seen[1].method == "PUT" and body_of(seen[1]) == {"due_date": 1767225600000, "due_date_time": True}


@pytest.mark.asyncio
async def test_comment_create(db):
    t, seen = api({f"{V2}/task/t1/comment": ok({"id": 458, "hist_id": "h1", "date": 1767225600000})})
    res = await run("clickup.comments.create", {"task_id": "t1", "comment_text": "Done", "assignee": 12}, db, t)
    assert res.ok and res.data == {"id": "458", "hist_id": "h1", "date": "1767225600000"}
    assert body_of(seen[0]) == {"comment_text": "Done", "notify_all": False, "assignee": 12}


@pytest.mark.asyncio
async def test_docs_search_filters_names_in_the_page(db):
    docs = {"docs": [{"id": "d1", "name": "Onboarding guide"}, {"id": "d2", "name": "Budget"}], "next_cursor": "N"}
    t, seen = api({f"{V3}/docs": ok(docs)})
    res = await run("clickup.docs.search", {**WS, "query": "ONBOARD", "parent_type": "SPACE", "parent_id": "321"}, db, t)
    assert [d["id"] for d in res.data["docs"]] == ["d1"] and res.data["scanned"] == 2 and res.data["next_cursor"] == "N"
    assert seen[0].url.params["parent_type"] == "SPACE" and seen[0].url.params["parent_id"] == "321"


@pytest.mark.asyncio
@pytest.mark.parametrize("fid,args", [
    ("clickup.folders.create", {"space_id": "321", "name": ""}),
    ("clickup.lists.create", {"folder_id": "456", "name": "x", "priority": 9}),
    ("clickup.tasks.create", {"list_id": "901", "name": "x", "priority": 0}),
    ("clickup.tasks.create", {"list_id": "901"}),
    ("clickup.tasks.assign", {"task_id": "t1"}),
    ("clickup.tasks.assign", {"task_id": "t1", "user_id": "ana"}),
    ("clickup.tasks.update_due_date", {"task_id": "t1", "due_date": "tomorrow"}),
    ("clickup.comments.create", {"task_id": "t1", "comment_text": ""}),
    ("clickup.docs.search", {**WS, "parent_type": "PLANET"}),
])
async def test_write_functions_reject_invalid_input(db, fid, args):
    t, seen = api({})
    res = await run(fid, args, db, t)
    assert res.error.code == ErrorCode.invalid_input and not seen


@pytest.mark.asyncio
async def test_writes_are_simulated_and_never_reach_clickup(db):
    t, seen = api({})
    for fid in ("clickup.folders.create", "clickup.lists.create", "clickup.tasks.create", "clickup.tasks.assign",
                "clickup.tasks.update_due_date", "clickup.comments.create"):
        fn = get_function(fid)
        res = await run(fid, fn.spec.examples[0].input, db, t, simulate=True)
        assert res.ok and res.meta.simulated and res.data == fn.spec.examples[0].output
    assert not seen


def test_write_functions_are_flagged_like_the_catalog():
    flags = {fid: (fn.spec.verb.value, fn.spec.exits_outside) for (fid, _), fn in _FUNCS.items() if fid.startswith("clickup.")}
    assert flags["clickup.tasks.assign"] == ("update", True) and flags["clickup.comments.create"] == ("create", True)
    assert flags["clickup.folders.create"] == ("create", False) and flags["clickup.tasks.update_due_date"] == ("update", False)
    assert sum(1 for v, _ in flags.values() if v != "read") == 6
