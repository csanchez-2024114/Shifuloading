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
GID = "1200000000000001"
WS = "1200000000000002"
PROJECT = "1200000000000100"
SECTION = "1200000000000200"
LIST = "1200000000000300"
TASK = "1200000000000500"
REL = "1200000000000600"
TASK2 = "1200000000000700"
TEAM = "1200000000000800"
TAG = "1200000000000900"

USER = {"gid": GID, "name": "Ana Perez", "email": "ana@empresa.test",
        "workspaces": [{"gid": WS, "name": "Mi equipo"}]}

ALL_TAREA3 = [
    "asana.users.list_favorites",
    "asana.users.get_workspace",
    "asana.tasks.list_project_tasks",
    "asana.tasks.list_section_tasks",
    "asana.tasks.list_user_task_list",
    "asana.tasks.search",
    "asana.tasks.get_by_custom_id",
    "asana.tasks.list_subtasks",
    "asana.tasks.list_dependencies",
    "asana.tasks.list_dependents",
    "asana.tasks.list_projects",
    "asana.projects.list_team_projects",
    "asana.projects.list_workspace_projects",
    "asana.projects.search",
    "asana.projects.get_task_counts",
    "asana.sections.list",
    "asana.sections.get",
    "asana.tags.get",
    "asana.tags.list_task_tags",
    "asana.tags.list_workspace_tags",
]

APP_ERROR_ARGS = {
    "asana.users.list_favorites": {"workspace": WS},
    "asana.users.get_workspace": {"workspace_gid": WS, "user_gid": "me"},
    "asana.tasks.list_project_tasks": {"project_gid": PROJECT},
    "asana.tasks.list_section_tasks": {"section_gid": SECTION},
    "asana.tasks.list_user_task_list": {"user_task_list_gid": LIST},
    "asana.tasks.search": {"workspace_gid": WS, "text": "factura"},
    "asana.tasks.get_by_custom_id": {"workspace_gid": WS, "custom_id": "EX-42"},
    "asana.tasks.list_subtasks": {"task_gid": TASK},
    "asana.tasks.list_dependencies": {"task_gid": REL},
    "asana.tasks.list_dependents": {"task_gid": REL},
    "asana.tasks.list_projects": {"task_gid": TASK2},
    "asana.projects.list_team_projects": {"team_gid": TEAM},
    "asana.projects.list_workspace_projects": {"workspace_gid": WS},
    "asana.projects.search": {"workspace_gid": WS, "text": "web"},
    "asana.projects.get_task_counts": {"project_gid": PROJECT},
    "asana.sections.list": {"project_gid": PROJECT},
    "asana.sections.get": {"section_gid": SECTION},
    "asana.tags.get": {"tag_gid": TAG},
    "asana.tags.list_task_tags": {"task_gid": TASK},
    "asana.tags.list_workspace_tags": {"workspace_gid": WS},
}


@pytest.fixture(autouse=True, scope="module")
def _registry():
    load_all()


@pytest_asyncio.fixture
async def db():
    d = AsyncMongoMockClient()["asana_test"]
    await d[COL].insert_one(connection_doc(account=GID, provider="asana", token="old-token", refresh="rt-1"))
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


# --- whoami (Tarea 2) ----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_whoami_unwraps_data_and_matches_stored_account(db):
    t, seen = api({"/api/1.0/users/me": httpx.Response(200, json={"data": USER})})
    res = await run("asana.users.get", {}, db, t)
    assert res.ok and res.data == {
        "account_id": GID, "display_name": "Ana Perez", "email": "ana@empresa.test", "workspaces": [WS]}
    assert seen[0].method == "GET" and seen[0].url.path == "/api/1.0/users/me"
    assert seen[0].headers["authorization"] == "Bearer old-token"
    assert seen[0].url.params["opt_fields"] == "email,name,workspaces"
    assert res.data["account_id"] == res.meta.account_id


@pytest.mark.asyncio
async def test_missing_scope_is_not_confused_with_an_expired_token(db):
    body = {"errors": [{"message": "Missing scope: the user did not grant users:read"}]}
    t, seen = api({"/api/1.0/users/me": httpx.Response(403, json=body)})
    res = await run("asana.users.get", {}, db, t)
    assert res.error.code == ErrorCode.missing_scope and res.error.user_action == "grant_scopes"
    assert len(seen) == 1 and (await db[COL].find_one({"account_id": GID}))["status"] == "active"


@pytest.mark.asyncio
async def test_unexpected_response_shape_is_upstream_changed(db):
    t, _ = api({"/api/1.0/users/me": httpx.Response(200, json={"data": {"name": "sin gid"}})})
    assert (await run("asana.users.get", {}, db, t)).error.code == ErrorCode.upstream_changed


@pytest.mark.asyncio
async def test_expired_token_is_refreshed_and_retried(db, monkeypatch):
    monkeypatch.setenv("ASANA_CLIENT_ID", "cid")
    monkeypatch.setenv("ASANA_CLIENT_SECRET", "csecret")

    def me(req):
        if req.headers["authorization"] == "Bearer fresh-token":
            return httpx.Response(200, json={"data": USER})
        return httpx.Response(401, json={"errors": [{"message": "The bearer token has expired."}]})

    t, seen = api({"/api/1.0/users/me": me, "/-/oauth_token": httpx.Response(200, json={"access_token": "fresh-token"})})
    res = await run("asana.users.get", {}, db, t)
    assert res.ok and len(seen) == 3  # 401, refresco, reintento
    doc = await db[COL].find_one({"account_id": GID})
    assert unseal(doc["credentials_enc"]) == {"token": "fresh-token", "refresh_token": "rt-1"}


# --- entrada invalida y error de la app, para las 20 funciones (Tarea 3) ---------------------------

@pytest.mark.parametrize("fid", ALL_TAREA3)
@pytest.mark.asyncio
async def test_each_function_validates_its_required_input(fid, db):
    res = await run(fid, {}, db, api({})[0])
    assert res.error.code == ErrorCode.invalid_input


@pytest.mark.parametrize("fid", sorted(APP_ERROR_ARGS))
@pytest.mark.asyncio
async def test_each_function_maps_upstream_404_to_not_found(fid, db):
    res = await run(fid, APP_ERROR_ARGS[fid], db, api({})[0])
    assert res.error.code == ErrorCode.not_found


# --- casos normales ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_users_list_favorites_ok(db):
    body = {"data": [{"gid": PROJECT, "resource_type": "project", "name": "Web 2026"}], "next_page": None}
    t, seen = api({"/api/1.0/users/me/favorites": httpx.Response(200, json=body)})
    res = await run("asana.users.list_favorites", {"workspace": WS}, db, t)
    assert res.ok and res.data == {"items": [{"gid": PROJECT, "resource_type": "project", "name": "Web 2026"}],
                                   "has_more": False, "next_offset": None}
    assert seen[0].url.path == "/api/1.0/users/me/favorites"
    p = seen[0].url.params
    assert p["workspace"] == WS and p["resource_type"] == "project" and p["opt_fields"] == "name,resource_type"


@pytest.mark.asyncio
async def test_users_get_workspace_ok(db):
    body = {"data": {"gid": GID, "name": "Ana Perez", "email": "ana@empresa.test"}}
    t, seen = api({"/api/1.0/workspaces/1200000000000002/users/me": httpx.Response(200, json=body)})
    res = await run("asana.users.get_workspace", {"workspace_gid": WS, "user_gid": "me"}, db, t)
    assert res.ok and res.data == {"gid": GID, "name": "Ana Perez", "email": "ana@empresa.test"}
    assert seen[0].url.path == "/api/1.0/workspaces/1200000000000002/users/me"


@pytest.mark.asyncio
async def test_tasks_list_project_tasks_ok(db):
    body = {"data": [{"gid": "1200000000000110", "name": "Rediseno portada", "assignee": {"gid": GID, "name": "Ana"},
                      "due_on": "2026-03-01", "completed": False}], "next_page": None}
    t, seen = api({"/api/1.0/projects/1200000000000100/tasks": httpx.Response(200, json=body)})
    res = await run("asana.tasks.list_project_tasks", {"project_gid": PROJECT, "limit": 2}, db, t)
    assert res.ok and res.data == {"items": [{"gid": "1200000000000110", "name": "Rediseno portada", "assignee": GID,
                                              "due_on": "2026-03-01", "completed": False}],
                                   "has_more": False, "next_offset": None}
    assert seen[0].url.path == "/api/1.0/projects/1200000000000100/tasks"
    assert seen[0].url.params["limit"] == "2" and seen[0].url.params["opt_fields"] == "name,assignee.name,due_on,completed"


@pytest.mark.asyncio
async def test_tasks_list_section_tasks_forwards_offset_and_next_page(db):
    body = {"data": [{"gid": "1200000000000210", "name": "Redactar brief", "assignee": {"gid": GID, "name": "Ana"},
                      "due_on": "2026-02-10", "completed": False}],
            "next_page": {"offset": "eyJpdiI6MSJ9"}}
    t, seen = api({"/api/1.0/sections/1200000000000200/tasks": httpx.Response(200, json=body)})
    res = await run("asana.tasks.list_section_tasks", {"section_gid": SECTION, "offset": "eyJpdiI6MSJ9"}, db, t)
    assert res.ok and res.data["has_more"] is True and res.data["next_offset"] == "eyJpdiI6MSJ9"
    assert res.data["items"][0]["assignee"] == GID
    assert seen[0].url.params["offset"] == "eyJpdiI6MSJ9"


@pytest.mark.asyncio
async def test_tasks_list_user_task_list_ok(db):
    body = {"data": [{"gid": "1200000000000310", "name": "Preparar demo", "assignee": {"gid": GID, "name": "Ana"},
                      "due_on": "2026-02-15", "completed": False}], "next_page": None}
    t, seen = api({"/api/1.0/user_task_lists/1200000000000300/tasks": httpx.Response(200, json=body)})
    res = await run("asana.tasks.list_user_task_list", {"user_task_list_gid": LIST}, db, t)
    assert res.ok and res.data["items"][0]["name"] == "Preparar demo"
    assert seen[0].url.path == "/api/1.0/user_task_lists/1200000000000300/tasks"


@pytest.mark.asyncio
async def test_tasks_search_sends_text(db):
    body = {"data": [{"gid": "1200000000000400", "name": "Revisar factura", "assignee": {"gid": GID, "name": "Ana"},
                      "due_on": "2026-02-20", "completed": False}], "next_page": None}
    t, seen = api({"/api/1.0/workspaces/1200000000000002/tasks/search": httpx.Response(200, json=body)})
    res = await run("asana.tasks.search", {"workspace_gid": WS, "text": "factura"}, db, t)
    assert res.ok and res.data["items"][0]["name"] == "Revisar factura"
    assert seen[0].url.path == "/api/1.0/workspaces/1200000000000002/tasks/search"
    assert seen[0].url.params["text"] == "factura"


@pytest.mark.asyncio
async def test_tasks_get_by_custom_id_uses_underscore_path(db):
    body = {"data": {"gid": "1200000000000420", "name": "Tarea EX-42", "assignee": {"gid": GID, "name": "Ana"}}}
    t, seen = api({"/api/1.0/workspaces/1200000000000002/tasks/custom_id/EX-42": httpx.Response(200, json=body)})
    res = await run("asana.tasks.get_by_custom_id", {"workspace_gid": WS, "custom_id": "EX-42"}, db, t)
    assert res.ok and res.data == {"gid": "1200000000000420", "name": "Tarea EX-42", "assignee": GID}
    assert seen[0].url.path.endswith("/tasks/custom_id/EX-42")


@pytest.mark.asyncio
async def test_tasks_list_subtasks_ok(db):
    body = {"data": [{"gid": "1200000000000510", "name": "Buscar proveedor", "assignee": {"gid": GID, "name": "Ana"},
                      "due_on": "2026-01-30", "completed": True}], "next_page": None}
    t, seen = api({"/api/1.0/tasks/1200000000000500/subtasks": httpx.Response(200, json=body)})
    res = await run("asana.tasks.list_subtasks", {"task_gid": TASK}, db, t)
    assert res.ok and res.data["items"][0]["completed"] is True
    assert seen[0].url.path == "/api/1.0/tasks/1200000000000500/subtasks"


@pytest.mark.asyncio
async def test_tasks_list_dependencies_ok(db):
    body = {"data": [{"gid": "1200000000000610", "name": "Aprobar presupuesto"}], "next_page": None}
    t, seen = api({"/api/1.0/tasks/1200000000000600/dependencies": httpx.Response(200, json=body)})
    res = await run("asana.tasks.list_dependencies", {"task_gid": REL}, db, t)
    assert res.ok and res.data == {"items": [{"gid": "1200000000000610", "name": "Aprobar presupuesto"}],
                                   "has_more": False, "next_offset": None}
    assert seen[0].url.path == "/api/1.0/tasks/1200000000000600/dependencies"


@pytest.mark.asyncio
async def test_tasks_list_dependents_ok(db):
    body = {"data": [{"gid": "1200000000000630", "name": "Publicar landing"}], "next_page": None}
    t, seen = api({"/api/1.0/tasks/1200000000000600/dependents": httpx.Response(200, json=body)})
    res = await run("asana.tasks.list_dependents", {"task_gid": REL}, db, t)
    assert res.ok and res.data["items"][0]["name"] == "Publicar landing"
    assert seen[0].url.path == "/api/1.0/tasks/1200000000000600/dependents"


@pytest.mark.asyncio
async def test_tasks_list_projects_ok(db):
    body = {"data": [{"gid": PROJECT, "name": "Web 2026"}, {"gid": "1200000000000150", "name": "CRM"}], "next_page": None}
    t, seen = api({"/api/1.0/tasks/1200000000000700/projects": httpx.Response(200, json=body)})
    res = await run("asana.tasks.list_projects", {"task_gid": TASK2}, db, t)
    assert res.ok and [i["name"] for i in res.data["items"]] == ["Web 2026", "CRM"]
    assert seen[0].url.path == "/api/1.0/tasks/1200000000000700/projects"


@pytest.mark.asyncio
async def test_projects_list_team_projects_ok(db):
    body = {"data": [{"gid": PROJECT, "name": "Web 2026", "owner": {"gid": GID, "name": "Ana"}}], "next_page": None}
    t, seen = api({"/api/1.0/teams/1200000000000800/projects": httpx.Response(200, json=body)})
    res = await run("asana.projects.list_team_projects", {"team_gid": TEAM}, db, t)
    assert res.ok and res.data["items"][0]["owner"] == GID
    assert seen[0].url.path == "/api/1.0/teams/1200000000000800/projects"


@pytest.mark.asyncio
async def test_projects_list_workspace_projects_ok(db):
    body = {"data": [{"gid": PROJECT, "name": "Web 2026", "owner": {"gid": GID, "name": "Ana"}},
                     {"gid": "1200000000000150", "name": "CRM", "owner": None}], "next_page": None}
    t, seen = api({"/api/1.0/workspaces/1200000000000002/projects": httpx.Response(200, json=body)})
    res = await run("asana.projects.list_workspace_projects", {"workspace_gid": WS}, db, t)
    assert res.ok and res.data["items"][1]["owner"] is None
    assert seen[0].url.path == "/api/1.0/workspaces/1200000000000002/projects"


@pytest.mark.asyncio
async def test_projects_search_sends_text(db):
    body = {"data": [{"gid": PROJECT, "name": "Web 2026", "owner": {"gid": GID, "name": "Ana"}}], "next_page": None}
    t, seen = api({"/api/1.0/workspaces/1200000000000002/projects/search": httpx.Response(200, json=body)})
    res = await run("asana.projects.search", {"workspace_gid": WS, "text": "web"}, db, t)
    assert res.ok and res.data["items"][0]["gid"] == PROJECT
    assert seen[0].url.path == "/api/1.0/workspaces/1200000000000002/projects/search"
    assert seen[0].url.params["text"] == "web"


@pytest.mark.asyncio
async def test_projects_get_task_counts_uses_task_counts_path(db):
    body = {"data": {"num_tasks": 12, "num_incomplete_tasks": 4, "num_completed_tasks": 8, "num_milestones": 1}}
    t, seen = api({"/api/1.0/projects/1200000000000100/task_counts": httpx.Response(200, json=body)})
    res = await run("asana.projects.get_task_counts", {"project_gid": PROJECT}, db, t)
    assert res.ok and res.data == {"num_tasks": 12, "num_incomplete_tasks": 4, "num_completed_tasks": 8, "num_milestones": 1}
    assert seen[0].url.path == "/api/1.0/projects/1200000000000100/task_counts"


@pytest.mark.asyncio
async def test_sections_list_ok(db):
    body = {"data": [{"gid": SECTION, "name": "To do", "created_at": "2026-01-01T10:00:00Z"},
                     {"gid": "1200000000000201", "name": "Doing", "created_at": "2026-01-01T10:00:00Z"}], "next_page": None}
    t, seen = api({"/api/1.0/projects/1200000000000100/sections": httpx.Response(200, json=body)})
    res = await run("asana.sections.list", {"project_gid": PROJECT}, db, t)
    assert res.ok and [i["name"] for i in res.data["items"]] == ["To do", "Doing"]
    assert seen[0].url.params["opt_fields"] == "name,created_at"


@pytest.mark.asyncio
async def test_sections_get_ok(db):
    body = {"data": {"gid": SECTION, "name": "To do", "created_at": "2026-01-01T10:00:00Z",
                     "project": {"gid": PROJECT, "name": "Web 2026"}}}
    t, seen = api({"/api/1.0/sections/1200000000000200": httpx.Response(200, json=body)})
    res = await run("asana.sections.get", {"section_gid": SECTION}, db, t)
    assert res.ok and res.data["project"] == PROJECT and res.data["name"] == "To do"
    assert seen[0].url.path == "/api/1.0/sections/1200000000000200"


@pytest.mark.asyncio
async def test_tags_get_ok(db):
    body = {"data": {"gid": TAG, "name": "Urgente", "color": "red", "workspace": {"gid": WS, "name": "Mi equipo"}}}
    t, seen = api({"/api/1.0/tags/1200000000000900": httpx.Response(200, json=body)})
    res = await run("asana.tags.get", {"tag_gid": TAG}, db, t)
    assert res.ok and res.data == {"gid": TAG, "name": "Urgente", "color": "red", "workspace": WS}
    assert seen[0].url.path == "/api/1.0/tags/1200000000000900"


@pytest.mark.asyncio
async def test_tags_list_task_tags_ok(db):
    body = {"data": [{"gid": TAG, "name": "Urgente", "color": "red"}], "next_page": None}
    t, seen = api({"/api/1.0/tasks/1200000000000500/tags": httpx.Response(200, json=body)})
    res = await run("asana.tags.list_task_tags", {"task_gid": TASK}, db, t)
    assert res.ok and res.data["items"][0]["color"] == "red"
    assert seen[0].url.path == "/api/1.0/tasks/1200000000000500/tags"


@pytest.mark.asyncio
async def test_tags_list_workspace_tags_ok(db):
    body = {"data": [{"gid": TAG, "name": "Urgente", "color": "red"}], "next_page": None}
    t, seen = api({"/api/1.0/workspaces/1200000000000002/tags": httpx.Response(200, json=body)})
    res = await run("asana.tags.list_workspace_tags", {"workspace_gid": WS}, db, t)
    assert res.ok and res.data["items"][0]["name"] == "Urgente"
    assert seen[0].url.path == "/api/1.0/workspaces/1200000000000002/tags"


# --- comportamientos adicionales -----------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_rejects_empty_text(db):
    assert (await run("asana.tasks.search", {"workspace_gid": WS, "text": ""}, db, api({})[0])).error.code == ErrorCode.invalid_input
    assert (await run("asana.projects.search", {"workspace_gid": WS, "text": ""}, db, api({})[0])).error.code == ErrorCode.invalid_input


@pytest.mark.asyncio
async def test_single_get_unexpected_shape_is_upstream_changed(db):
    t, _ = api({"/api/1.0/tags/1200000000000900": httpx.Response(200, json={"data": {"name": "sin gid"}})})
    assert (await run("asana.tags.get", {"tag_gid": TAG}, db, t)).error.code == ErrorCode.upstream_changed


# --- Tarea 4: stories, attachments, custom fields, settings, teams, memberships y workspaces -------

STORY = "1200000000003000"
ATT = "1200000000003100"
CF = "1200000000003200"
CF_SET = "1200000000003300"
PO = "1200000000003400"
TM = "1200000000003500"
PM = "1200000000003600"
GOAL = "1200000000004000"

ALL_TAREA4 = [
    "asana.stories.get",
    "asana.stories.list_goal_stories",
    "asana.attachments.list",
    "asana.attachments.get",
    "asana.custom_fields.list",
    "asana.custom_fields.get",
    "asana.custom_field_settings.list_project",
    "asana.custom_field_settings.list_portfolio",
    "asana.custom_field_settings.list_team",
    "asana.custom_field_settings.list_goal",
    "asana.teams.get",
    "asana.teams.list_user_teams",
    "asana.team_memberships.get",
    "asana.team_memberships.list_team",
    "asana.team_memberships.list_user",
    "asana.project_memberships.get",
    "asana.project_memberships.list",
    "asana.workspaces.list",
    "asana.workspaces.get",
]

APP_ERROR_ARGS4 = {
    "asana.stories.get": {"story_gid": STORY},
    "asana.stories.list_goal_stories": {"goal_gid": GOAL},
    "asana.attachments.list": {"parent_gid": TASK},
    "asana.attachments.get": {"attachment_gid": ATT},
    "asana.custom_fields.list": {"workspace_gid": WS},
    "asana.custom_fields.get": {"custom_field_gid": CF},
    "asana.custom_field_settings.list_project": {"project_gid": PROJECT},
    "asana.custom_field_settings.list_portfolio": {"portfolio_gid": PO},
    "asana.custom_field_settings.list_team": {"team_gid": TEAM},
    "asana.custom_field_settings.list_goal": {"goal_gid": GOAL},
    "asana.teams.get": {"team_gid": TEAM},
    "asana.teams.list_user_teams": {"organization": WS},
    "asana.team_memberships.get": {"team_membership_gid": TM},
    "asana.team_memberships.list_team": {"team_gid": TEAM},
    "asana.team_memberships.list_user": {"workspace": WS},
    "asana.project_memberships.get": {"project_membership_gid": PM},
    "asana.project_memberships.list": {"project_gid": PROJECT},
    "asana.workspaces.list": {},
    "asana.workspaces.get": {"workspace_gid": WS},
}

INVALID_ARGS4 = {fid: {} for fid in ALL_TAREA4}
INVALID_ARGS4["asana.workspaces.list"] = {"limit": 0}  # no hay campo obligatorio; el limite invalido rompe


@pytest.mark.parametrize("fid", ALL_TAREA4)
@pytest.mark.asyncio
async def test_tarea4_each_function_validates_its_input(fid, db):
    res = await run(fid, INVALID_ARGS4[fid], db, api({})[0])
    assert res.error.code == ErrorCode.invalid_input


@pytest.mark.parametrize("fid", sorted(APP_ERROR_ARGS4))
@pytest.mark.asyncio
async def test_tarea4_each_function_maps_upstream_404_to_not_found(fid, db):
    res = await run(fid, APP_ERROR_ARGS4[fid], db, api({})[0])
    assert res.error.code == ErrorCode.not_found


@pytest.mark.asyncio
async def test_stories_get_ok(db):
    body = {"gid": STORY, "type": "comment", "text": "Listo para revision",
            "created_by": {"gid": GID, "name": "Ana"}, "created_at": "2026-02-01T10:00:00Z",
            "task": {"gid": TASK, "name": "Rediseno portada"}}
    t, seen = api({"/api/1.0/stories/1200000000003000": httpx.Response(200, json={"data": body})})
    res = await run("asana.stories.get", {"story_gid": STORY}, db, t)
    assert res.ok and res.data == {"gid": STORY, "type": "comment", "text": "Listo para revision",
                                   "created_by": GID, "created_at": "2026-02-01T10:00:00Z", "task": TASK}
    assert seen[0].url.path == "/api/1.0/stories/1200000000003000"


@pytest.mark.asyncio
async def test_stories_list_goal_stories_ok(db):
    body = {"data": [{"gid": STORY, "type": "comment", "text": "Avanzando bien",
                      "created_by": {"gid": GID, "name": "Ana"}, "created_at": "2026-02-01T10:00:00Z"}], "next_page": None}
    t, seen = api({"/api/1.0/goals/1200000000004000/stories": httpx.Response(200, json=body)})
    res = await run("asana.stories.list_goal_stories", {"goal_gid": GOAL, "resource_subtype": "comment_added"}, db, t)
    assert res.ok and res.data["items"][0]["created_by"] == GID
    assert seen[0].url.path == "/api/1.0/goals/1200000000004000/stories"
    assert seen[0].url.params["resource_subtype"] == "comment_added"


@pytest.mark.asyncio
async def test_attachments_list_uses_parent_query(db):
    body = {"data": [{"gid": ATT, "name": "brief.pdf", "size": 204800, "created_at": "2026-02-01T10:00:00Z",
                      "view_url": "https://app.asana.com/0/attachments/1200000000003100",
                      "download_url": "https://app.asana.com/attachments/1200000000003100/download"}], "next_page": None}
    t, seen = api({"/api/1.0/attachments": httpx.Response(200, json=body)})
    res = await run("asana.attachments.list", {"parent_gid": TASK, "limit": 5}, db, t)
    assert res.ok and res.data["items"][0]["name"] == "brief.pdf" and res.data["items"][0]["size"] == 204800
    assert seen[0].url.path == "/api/1.0/attachments"
    assert seen[0].url.params["parent"] == TASK and seen[0].url.params["limit"] == "5"


@pytest.mark.asyncio
async def test_attachments_get_ok(db):
    body = {"gid": ATT, "resource_subtype": "external", "name": "brief.pdf", "size": 204800,
            "created_at": "2026-02-01T10:00:00Z", "view_url": "https://app.asana.com/0/attachments/1200000000003100",
            "download_url": "https://app.asana.com/attachments/1200000000003100/download",
            "parent": {"gid": TASK, "name": "Rediseno portada"}}
    t, seen = api({"/api/1.0/attachments/1200000000003100": httpx.Response(200, json={"data": body})})
    res = await run("asana.attachments.get", {"attachment_gid": ATT}, db, t)
    assert res.ok and res.data["parent"] == TASK and res.data["download_url"].startswith("https://")
    assert seen[0].url.path == "/api/1.0/attachments/1200000000003100"


@pytest.mark.asyncio
async def test_custom_fields_list_ok(db):
    body = {"data": [{"gid": CF, "name": "Prioridad", "type": "enum", "enum_options": [
        {"gid": "1200000000003210", "name": "Alta", "color": "red", "enabled": True}]}], "next_page": None}
    t, seen = api({"/api/1.0/workspaces/1200000000000002/custom_fields": httpx.Response(200, json=body)})
    res = await run("asana.custom_fields.list", {"workspace_gid": WS}, db, t)
    assert res.ok and res.data["items"][0]["enum_options"][0]["name"] == "Alta"
    assert seen[0].url.path == "/api/1.0/workspaces/1200000000000002/custom_fields"


@pytest.mark.asyncio
async def test_custom_fields_get_ok(db):
    body = {"gid": CF, "name": "Prioridad", "type": "enum", "enum_options": [
        {"gid": "1200000000003210", "name": "Alta", "color": "red", "enabled": True}], "is_global_to_workspace": False}
    t, seen = api({"/api/1.0/custom_fields/1200000000003200": httpx.Response(200, json={"data": body})})
    res = await run("asana.custom_fields.get", {"custom_field_gid": CF}, db, t)
    assert res.ok and res.data["is_global_to_workspace"] is False
    assert seen[0].url.path == "/api/1.0/custom_fields/1200000000003200"


@pytest.mark.asyncio
async def test_custom_field_settings_project_ok(db):
    body = {"data": [{"gid": CF_SET, "custom_field": {"gid": CF, "name": "Prioridad"}, "is_important": True}], "next_page": None}
    t, seen = api({"/api/1.0/projects/1200000000000100/custom_field_settings": httpx.Response(200, json=body)})
    res = await run("asana.custom_field_settings.list_project", {"project_gid": PROJECT}, db, t)
    assert res.ok and res.data["items"][0]["custom_field"] == CF and res.data["items"][0]["is_important"] is True
    assert seen[0].url.path == "/api/1.0/projects/1200000000000100/custom_field_settings"


@pytest.mark.asyncio
async def test_custom_field_settings_portfolio_ok(db):
    body = {"data": [{"gid": "1200000000003310", "custom_field": {"gid": CF, "name": "Prioridad"}, "is_important": False}], "next_page": None}
    t, seen = api({"/api/1.0/portfolios/1200000000003400/custom_field_settings": httpx.Response(200, json=body)})
    res = await run("asana.custom_field_settings.list_portfolio", {"portfolio_gid": PO}, db, t)
    assert res.ok and res.data["items"][0]["gid"] == "1200000000003310"
    assert seen[0].url.path == "/api/1.0/portfolios/1200000000003400/custom_field_settings"


@pytest.mark.asyncio
async def test_custom_field_settings_team_ok(db):
    body = {"data": [{"gid": "1200000000003320", "custom_field": {"gid": CF, "name": "Prioridad"}, "is_important": False}], "next_page": None}
    t, seen = api({"/api/1.0/teams/1200000000000800/custom_field_settings": httpx.Response(200, json=body)})
    res = await run("asana.custom_field_settings.list_team", {"team_gid": TEAM}, db, t)
    assert res.ok and res.data["items"][0]["custom_field"] == CF
    assert seen[0].url.path == "/api/1.0/teams/1200000000000800/custom_field_settings"


@pytest.mark.asyncio
async def test_custom_field_settings_goal_ok(db):
    body = {"data": [{"gid": "1200000000003330", "custom_field": {"gid": CF, "name": "Prioridad"}, "is_important": True}], "next_page": None}
    t, seen = api({"/api/1.0/goals/1200000000004000/custom_field_settings": httpx.Response(200, json=body)})
    res = await run("asana.custom_field_settings.list_goal", {"goal_gid": GOAL}, db, t)
    assert res.ok and res.data["items"][0]["is_important"] is True
    assert seen[0].url.path == "/api/1.0/goals/1200000000004000/custom_field_settings"


@pytest.mark.asyncio
async def test_teams_get_ok(db):
    body = {"gid": TEAM, "name": "Producto", "description": "Equipo de producto",
            "organization": {"gid": WS, "name": "Mi equipo"}, "permalink_url": "https://app.asana.com/0/team/1200000000000800/list"}
    t, seen = api({"/api/1.0/teams/1200000000000800": httpx.Response(200, json={"data": body})})
    res = await run("asana.teams.get", {"team_gid": TEAM}, db, t)
    assert res.ok and res.data == {"gid": TEAM, "name": "Producto", "description": "Equipo de producto",
                                   "organization": WS, "permalink_url": "https://app.asana.com/0/team/1200000000000800/list"}
    assert seen[0].url.path == "/api/1.0/teams/1200000000000800"


@pytest.mark.asyncio
async def test_teams_list_user_teams_sends_organization(db):
    body = {"data": [{"gid": TEAM, "name": "Producto", "organization": {"gid": WS, "name": "Mi equipo"}}], "next_page": None}
    t, seen = api({"/api/1.0/users/me/teams": httpx.Response(200, json=body)})
    res = await run("asana.teams.list_user_teams", {"organization": WS}, db, t)
    assert res.ok and res.data["items"][0]["organization"] == WS
    assert seen[0].url.path == "/api/1.0/users/me/teams"
    assert seen[0].url.params["organization"] == WS


@pytest.mark.asyncio
async def test_team_memberships_get_ok(db):
    body = {"gid": TM, "user": {"gid": GID, "name": "Ana"}, "team": {"gid": TEAM, "name": "Producto"},
            "is_admin": True, "is_guest": False, "is_limited_access": False}
    t, seen = api({"/api/1.0/team_memberships/1200000000003500": httpx.Response(200, json={"data": body})})
    res = await run("asana.team_memberships.get", {"team_membership_gid": TM}, db, t)
    assert res.ok and res.data["user"] == GID and res.data["is_admin"] is True
    assert seen[0].url.path == "/api/1.0/team_memberships/1200000000003500"


@pytest.mark.asyncio
async def test_team_memberships_list_team_ok(db):
    body = {"data": [{"gid": TM, "user": {"gid": GID, "name": "Ana"}, "team": {"gid": TEAM, "name": "Producto"},
                      "is_admin": True}], "next_page": None}
    t, seen = api({"/api/1.0/teams/1200000000000800/team_memberships": httpx.Response(200, json=body)})
    res = await run("asana.team_memberships.list_team", {"team_gid": TEAM}, db, t)
    assert res.ok and res.data["items"][0]["team"] == TEAM
    assert seen[0].url.path == "/api/1.0/teams/1200000000000800/team_memberships"


@pytest.mark.asyncio
async def test_team_memberships_list_user_sends_workspace(db):
    body = {"data": [{"gid": "1200000000003510", "user": {"gid": GID, "name": "Ana"}, "team": {"gid": TEAM, "name": "Producto"},
                      "is_admin": True}], "next_page": None}
    t, seen = api({"/api/1.0/users/me/team_memberships": httpx.Response(200, json=body)})
    res = await run("asana.team_memberships.list_user", {"workspace": WS}, db, t)
    assert res.ok and res.data["items"][0]["user"] == GID
    assert seen[0].url.path == "/api/1.0/users/me/team_memberships"
    assert seen[0].url.params["workspace"] == WS


@pytest.mark.asyncio
async def test_project_memberships_get_ok(db):
    body = {"gid": PM, "user": {"gid": GID, "name": "Ana"}, "project": {"gid": PROJECT, "name": "Web 2026"},
            "access_level": "admin", "write_access": "write"}
    t, seen = api({"/api/1.0/project_memberships/1200000000003600": httpx.Response(200, json={"data": body})})
    res = await run("asana.project_memberships.get", {"project_membership_gid": PM}, db, t)
    assert res.ok and res.data["access_level"] == "admin" and res.data["project"] == PROJECT
    assert seen[0].url.path == "/api/1.0/project_memberships/1200000000003600"


@pytest.mark.asyncio
async def test_project_memberships_list_uses_project_path(db):
    body = {"data": [{"gid": PM, "user": {"gid": GID, "name": "Ana"}, "project": {"gid": PROJECT, "name": "Web 2026"},
                      "access_level": "admin", "write_access": "write"}], "next_page": None}
    t, seen = api({"/api/1.0/projects/1200000000000100/project_memberships": httpx.Response(200, json=body)})
    res = await run("asana.project_memberships.list", {"project_gid": PROJECT}, db, t)
    assert res.ok and res.data["items"][0]["user"] == GID
    assert seen[0].url.path == "/api/1.0/projects/1200000000000100/project_memberships"


@pytest.mark.asyncio
async def test_workspaces_list_ok(db):
    body = {"data": [{"gid": WS, "name": "Mi equipo", "is_organization": True}], "next_page": None}
    t, seen = api({"/api/1.0/workspaces": httpx.Response(200, json=body)})
    res = await run("asana.workspaces.list", {}, db, t)
    assert res.ok and res.data["items"][0]["is_organization"] is True
    assert seen[0].url.path == "/api/1.0/workspaces"


@pytest.mark.asyncio
async def test_workspaces_get_ok(db):
    body = {"gid": WS, "name": "Mi equipo", "is_organization": True, "email_domains": ["empresa.test"]}
    t, seen = api({"/api/1.0/workspaces/1200000000000002": httpx.Response(200, json={"data": body})})
    res = await run("asana.workspaces.get", {"workspace_gid": WS}, db, t)
    assert res.ok and res.data == {"gid": WS, "name": "Mi equipo", "is_organization": True, "email_domains": ["empresa.test"]}
    assert seen[0].url.path == "/api/1.0/workspaces/1200000000000002"


# --- Tarea 5: workspace memberships, portfolios, portfolio memberships, goals, goal relationships, ---
# --- project templates y task templates -------------------------------------------------------------

WM = "1200000000005000"
POF = "1200000000005100"
POM = "1200000000005200"
GO = "1200000000005300"
GREL = "1200000000005400"
PT = "1200000000005500"
TT = "1200000000005600"
GO2 = "1200000000005401"

ALL_TAREA5 = [
    "asana.workspace_memberships.get",
    "asana.workspace_memberships.list",
    "asana.workspace_memberships.list_user",
    "asana.portfolios.list",
    "asana.portfolios.get",
    "asana.portfolios.list_items",
    "asana.portfolio_memberships.list",
    "asana.portfolio_memberships.get",
    "asana.portfolio_memberships.list_portfolio",
    "asana.goals.list",
    "asana.goals.get",
    "asana.goals.list_parent_goals",
    "asana.goal_relationships.list",
    "asana.goal_relationships.get",
    "asana.project_templates.list",
    "asana.project_templates.get",
    "asana.project_templates.list_team",
    "asana.task_templates.list",
    "asana.task_templates.get",
]

APP_ERROR_ARGS5 = {
    "asana.workspace_memberships.get": {"workspace_membership_gid": WM},
    "asana.workspace_memberships.list": {"workspace_gid": WS},
    "asana.workspace_memberships.list_user": {},  # el usuario por defecto "me" produce la llamada que da 404
    "asana.portfolios.list": {"workspace": WS},
    "asana.portfolios.get": {"portfolio_gid": POF},
    "asana.portfolios.list_items": {"portfolio_gid": POF},
    "asana.portfolio_memberships.list": {"portfolio": POF},
    "asana.portfolio_memberships.get": {"portfolio_membership_gid": POM},
    "asana.portfolio_memberships.list_portfolio": {"portfolio_gid": POF},
    "asana.goals.list": {"workspace": WS},
    "asana.goals.get": {"goal_gid": GO},
    "asana.goals.list_parent_goals": {"goal_gid": GO},
    "asana.goal_relationships.list": {"supported_goal": GO},
    "asana.goal_relationships.get": {"goal_relationship_gid": GREL},
    "asana.project_templates.list": {"workspace": WS},
    "asana.project_templates.get": {"project_template_gid": PT},
    "asana.project_templates.list_team": {"team_gid": TEAM},
    "asana.task_templates.list": {"project": PROJECT},
    "asana.task_templates.get": {"task_template_gid": TT},
}

INVALID_ARGS5 = {fid: {} for fid in ALL_TAREA5}
INVALID_ARGS5["asana.workspace_memberships.list_user"] = {"limit": 0}  # no hay campo obligatorio; el limite invalido rompe


@pytest.mark.parametrize("fid", ALL_TAREA5)
@pytest.mark.asyncio
async def test_tarea5_each_function_validates_its_input(fid, db):
    res = await run(fid, INVALID_ARGS5[fid], db, api({})[0])
    assert res.error.code == ErrorCode.invalid_input


@pytest.mark.parametrize("fid", sorted(APP_ERROR_ARGS5))
@pytest.mark.asyncio
async def test_tarea5_each_function_maps_upstream_404_to_not_found(fid, db):
    res = await run(fid, APP_ERROR_ARGS5[fid], db, api({})[0])
    assert res.error.code == ErrorCode.not_found


@pytest.mark.asyncio
async def test_workspace_memberships_get_ok(db):
    body = {"gid": WM, "user": {"gid": GID, "name": "Ana"}, "workspace": {"gid": WS, "name": "Mi equipo"},
            "is_admin": True, "is_guest": False, "is_view_only": False, "is_active": True}
    t, seen = api({"/api/1.0/workspace_memberships/1200000000005000": httpx.Response(200, json={"data": body})})
    res = await run("asana.workspace_memberships.get", {"workspace_membership_gid": WM}, db, t)
    assert res.ok and res.data == {"gid": WM, "user": GID, "workspace": WS, "is_admin": True, "is_guest": False,
                                   "is_view_only": False, "is_active": True, "created_at": None}
    assert seen[0].url.path == "/api/1.0/workspace_memberships/1200000000005000"


@pytest.mark.asyncio
async def test_workspace_memberships_list_ok(db):
    body = {"data": [{"gid": WM, "user": {"gid": GID, "name": "Ana"}, "workspace": {"gid": WS, "name": "Mi equipo"},
                      "is_admin": True}], "next_page": None}
    t, seen = api({"/api/1.0/workspaces/1200000000000002/workspace_memberships": httpx.Response(200, json=body)})
    res = await run("asana.workspace_memberships.list", {"workspace_gid": WS, "user": GID}, db, t)
    assert res.ok and res.data["items"][0]["is_admin"] is True
    assert seen[0].url.path == "/api/1.0/workspaces/1200000000000002/workspace_memberships"
    assert seen[0].url.params["user"] == GID and seen[0].url.params["limit"] == "100"


@pytest.mark.asyncio
async def test_workspace_memberships_list_user_defaults_to_me(db):
    body = {"data": [{"gid": WM, "user": {"gid": GID, "name": "Ana"}, "workspace": {"gid": WS, "name": "Mi equipo"},
                      "is_admin": True}], "next_page": None}
    t, seen = api({"/api/1.0/users/me/workspace_memberships": httpx.Response(200, json=body)})
    res = await run("asana.workspace_memberships.list_user", {}, db, t)
    assert res.ok and res.data["items"][0]["workspace"] == WS
    assert seen[0].url.path == "/api/1.0/users/me/workspace_memberships"


@pytest.mark.asyncio
async def test_portfolios_list_ok(db):
    body = {"data": [{"gid": POF, "name": "Programa 2026", "owner": {"gid": GID, "name": "Ana"}}], "next_page": None}
    t, seen = api({"/api/1.0/portfolios": httpx.Response(200, json=body)})
    res = await run("asana.portfolios.list", {"workspace": WS}, db, t)
    assert res.ok and res.data["items"][0]["owner"] == GID
    assert seen[0].url.path == "/api/1.0/portfolios"
    assert seen[0].url.params["workspace"] == WS


@pytest.mark.asyncio
async def test_portfolios_get_ok(db):
    body = {"gid": POF, "name": "Programa 2026", "owner": {"gid": GID, "name": "Ana"},
            "members": [{"gid": GID, "name": "Ana"}], "created_at": "2026-01-01T10:00:00Z",
            "workspace": {"gid": WS, "name": "Mi equipo"}, "permalink_url": "https://app.asana.com/0/portfolio/1200000000005100/list"}
    t, seen = api({"/api/1.0/portfolios/1200000000005100": httpx.Response(200, json={"data": body})})
    res = await run("asana.portfolios.get", {"portfolio_gid": POF}, db, t)
    assert res.ok and res.data == {"gid": POF, "name": "Programa 2026", "owner": GID, "members": [GID],
                                   "created_at": "2026-01-01T10:00:00Z", "workspace": WS,
                                   "permalink_url": "https://app.asana.com/0/portfolio/1200000000005100/list"}
    assert seen[0].url.path == "/api/1.0/portfolios/1200000000005100"


@pytest.mark.asyncio
async def test_portfolios_list_items_ok(db):
    body = {"data": [{"gid": PROJECT, "name": "Web 2026", "resource_type": "project"}], "next_page": None}
    t, seen = api({"/api/1.0/portfolios/1200000000005100/items": httpx.Response(200, json=body)})
    res = await run("asana.portfolios.list_items", {"portfolio_gid": POF}, db, t)
    assert res.ok and res.data["items"][0]["resource_type"] == "project"
    assert seen[0].url.path == "/api/1.0/portfolios/1200000000005100/items"


@pytest.mark.asyncio
async def test_portfolio_memberships_list_uses_portfolio_filter(db):
    body = {"data": [{"gid": POM, "user": {"gid": GID, "name": "Ana"}, "portfolio": {"gid": POF, "name": "Programa 2026"},
                      "access_level": "admin"}], "next_page": None}
    t, seen = api({"/api/1.0/portfolio_memberships": httpx.Response(200, json=body)})
    res = await run("asana.portfolio_memberships.list", {"portfolio": POF}, db, t)
    assert res.ok and res.data["items"][0]["access_level"] == "admin"
    assert seen[0].url.path == "/api/1.0/portfolio_memberships"
    assert seen[0].url.params["portfolio"] == POF


@pytest.mark.asyncio
async def test_portfolio_memberships_get_ok(db):
    body = {"gid": POM, "user": {"gid": GID, "name": "Ana"}, "portfolio": {"gid": POF, "name": "Programa 2026"}, "access_level": "editor"}
    t, seen = api({"/api/1.0/portfolio_memberships/1200000000005200": httpx.Response(200, json={"data": body})})
    res = await run("asana.portfolio_memberships.get", {"portfolio_membership_gid": POM}, db, t)
    assert res.ok and res.data["access_level"] == "editor" and res.data["portfolio"] == POF
    assert seen[0].url.path == "/api/1.0/portfolio_memberships/1200000000005200"


@pytest.mark.asyncio
async def test_portfolio_memberships_list_portfolio_path_ok(db):
    body = {"data": [{"gid": POM, "user": {"gid": GID, "name": "Ana"}, "portfolio": {"gid": POF, "name": "Programa 2026"},
                      "access_level": "admin"}], "next_page": None}
    t, seen = api({"/api/1.0/portfolios/1200000000005100/portfolio_memberships": httpx.Response(200, json=body)})
    res = await run("asana.portfolio_memberships.list_portfolio", {"portfolio_gid": POF}, db, t)
    assert res.ok and res.data["items"][0]["user"] == GID
    assert seen[0].url.path == "/api/1.0/portfolios/1200000000005100/portfolio_memberships"


@pytest.mark.asyncio
async def test_goals_list_ok(db):
    body = {"data": [{"gid": GO, "name": "Crecer 20%", "owner": {"gid": GID, "name": "Ana"}, "due_on": "2026-12-31",
                      "status": "on_track", "team": {"gid": TEAM, "name": "Producto"}}], "next_page": None}
    t, seen = api({"/api/1.0/goals": httpx.Response(200, json=body)})
    res = await run("asana.goals.list", {"workspace": WS}, db, t)
    assert res.ok and res.data["items"][0]["status"] == "on_track" and res.data["items"][0]["team"] == TEAM
    assert seen[0].url.path == "/api/1.0/goals"
    assert seen[0].url.params["workspace"] == WS


@pytest.mark.asyncio
async def test_goals_get_ok(db):
    body = {"gid": GO, "name": "Crecer 20%", "owner": {"gid": GID, "name": "Ana"}, "team": {"gid": TEAM, "name": "Producto"},
            "due_on": "2026-12-31", "start_on": "2026-01-01", "status": "on_track", "workspace": {"gid": WS, "name": "Mi equipo"}}
    t, seen = api({"/api/1.0/goals/1200000000005300": httpx.Response(200, json={"data": body})})
    res = await run("asana.goals.get", {"goal_gid": GO}, db, t)
    assert res.ok and res.data == {"gid": GO, "name": "Crecer 20%", "owner": GID, "team": TEAM, "due_on": "2026-12-31",
                                   "start_on": "2026-01-01", "status": "on_track", "workspace": WS}
    assert seen[0].url.path == "/api/1.0/goals/1200000000005300"


@pytest.mark.asyncio
async def test_goals_list_parent_goals_uses_camel_case_path(db):
    body = {"data": [{"gid": GO2, "name": "Objetivo anual", "owner": {"gid": GID, "name": "Ana"}, "due_on": "2026-12-31"}], "next_page": None}
    t, seen = api({"/api/1.0/goals/1200000000005300/parentGoals": httpx.Response(200, json=body)})
    res = await run("asana.goals.list_parent_goals", {"goal_gid": GO}, db, t)
    assert res.ok and res.data["items"][0]["name"] == "Objetivo anual"
    assert seen[0].url.path == "/api/1.0/goals/1200000000005300/parentGoals"


@pytest.mark.asyncio
async def test_goal_relationships_list_uses_supported_goal(db):
    body = {"data": [{"gid": GREL, "resource_subtype": "subgoal", "supported_goal": {"gid": GO, "name": "Crecer 20%"},
                      "supporting_resource": {"gid": GO2, "name": "Objetivo anual"}, "contribution_weight": 1.0}], "next_page": None}
    t, seen = api({"/api/1.0/goal_relationships": httpx.Response(200, json=body)})
    res = await run("asana.goal_relationships.list", {"supported_goal": GO}, db, t)
    assert res.ok and res.data["items"][0]["supported_goal"] == GO and res.data["items"][0]["contribution_weight"] == 1.0
    assert seen[0].url.path == "/api/1.0/goal_relationships"
    assert seen[0].url.params["supported_goal"] == GO


@pytest.mark.asyncio
async def test_goal_relationships_get_ok(db):
    body = {"gid": GREL, "resource_subtype": "subgoal", "supported_goal": {"gid": GO, "name": "Crecer 20%"},
            "supporting_resource": {"gid": GO2, "name": "Objetivo anual"}, "contribution_weight": 1.0}
    t, seen = api({"/api/1.0/goal_relationships/1200000000005400": httpx.Response(200, json={"data": body})})
    res = await run("asana.goal_relationships.get", {"goal_relationship_gid": GREL}, db, t)
    assert res.ok and res.data["supporting_resource"] == GO2
    assert seen[0].url.path == "/api/1.0/goal_relationships/1200000000005400"


@pytest.mark.asyncio
async def test_project_templates_list_ok(db):
    body = {"data": [{"gid": PT, "name": "Onboarding", "team": {"gid": TEAM, "name": "Producto"}}], "next_page": None}
    t, seen = api({"/api/1.0/project_templates": httpx.Response(200, json=body)})
    res = await run("asana.project_templates.list", {"workspace": WS}, db, t)
    assert res.ok and res.data["items"][0]["team"] == TEAM
    assert seen[0].url.path == "/api/1.0/project_templates"
    assert seen[0].url.params["workspace"] == WS


@pytest.mark.asyncio
async def test_project_templates_get_ok(db):
    body = {"gid": PT, "name": "Onboarding", "team": {"gid": TEAM, "name": "Producto"}, "description": "Plantilla de onboarding",
            "public": True, "color": "light-blue"}
    t, seen = api({"/api/1.0/project_templates/1200000000005500": httpx.Response(200, json={"data": body})})
    res = await run("asana.project_templates.get", {"project_template_gid": PT}, db, t)
    assert res.ok and res.data["public"] is True and res.data["color"] == "light-blue"
    assert seen[0].url.path == "/api/1.0/project_templates/1200000000005500"


@pytest.mark.asyncio
async def test_project_templates_list_team_path_ok(db):
    body = {"data": [{"gid": PT, "name": "Onboarding", "team": {"gid": TEAM, "name": "Producto"}}], "next_page": None}
    t, seen = api({"/api/1.0/teams/1200000000000800/project_templates": httpx.Response(200, json=body)})
    res = await run("asana.project_templates.list_team", {"team_gid": TEAM}, db, t)
    assert res.ok and res.data["items"][0]["gid"] == PT
    assert seen[0].url.path == "/api/1.0/teams/1200000000000800/project_templates"


@pytest.mark.asyncio
async def test_task_templates_list_uses_project_filter(db):
    body = {"data": [{"gid": TT, "name": "Bug reporte", "created_at": "2026-01-01T10:00:00Z", "project": {"gid": PROJECT, "name": "Web 2026"}}], "next_page": None}
    t, seen = api({"/api/1.0/task_templates": httpx.Response(200, json=body)})
    res = await run("asana.task_templates.list", {"project": PROJECT}, db, t)
    assert res.ok and res.data["items"][0]["project"] == PROJECT
    assert seen[0].url.path == "/api/1.0/task_templates"
    assert seen[0].url.params["project"] == PROJECT


@pytest.mark.asyncio
async def test_task_templates_get_ok(db):
    body = {"gid": TT, "name": "Bug reporte", "created_at": "2026-01-01T10:00:00Z",
            "created_by": {"gid": GID, "name": "Ana"}, "project": {"gid": PROJECT, "name": "Web 2026"}}
    t, seen = api({"/api/1.0/task_templates/1200000000005600": httpx.Response(200, json={"data": body})})
    res = await run("asana.task_templates.get", {"task_template_gid": TT}, db, t)
    assert res.ok and res.data["created_by"] == GID and res.data["project"] == PROJECT
    assert seen[0].url.path == "/api/1.0/task_templates/1200000000005600"


# --- Tarea 6: status updates, memberships, time tracking, webhooks, audit log y organization exports ---

SU = "1200000000006000"
MEM = "1200000000006100"
TTE = "1200000000006200"
TTC = "1200000000006300"
WH = "1200000000006400"
AUD = "1200000000006500"
OEX = "1200000000006600"

ALL_TAREA6 = [
    "asana.status_updates.list",
    "asana.status_updates.get",
    "asana.memberships.list",
    "asana.memberships.get",
    "asana.time_tracking_entries.list_task",
    "asana.time_tracking_entries.get",
    "asana.time_tracking_entries.list",
    "asana.time_tracking_categories.list",
    "asana.time_tracking_categories.get",
    "asana.time_tracking_categories.list_entries",
    "asana.webhooks.list",
    "asana.webhooks.get",
    "asana.audit_log.list",
    "asana.organization_exports.get",
]

APP_ERROR_ARGS6 = {
    "asana.status_updates.list": {"parent": PROJECT},
    "asana.status_updates.get": {"status_update_gid": SU},
    "asana.memberships.list": {"parent": PROJECT},
    "asana.memberships.get": {"membership_gid": MEM},
    "asana.time_tracking_entries.list_task": {"task_gid": TASK},
    "asana.time_tracking_entries.get": {"entry_gid": TTE},
    "asana.time_tracking_entries.list": {"workspace_gid": WS, "user_gid": GID},
    "asana.time_tracking_categories.list": {"workspace": WS},
    "asana.time_tracking_categories.get": {"category_gid": TTC},
    "asana.time_tracking_categories.list_entries": {"category_gid": TTC},
    "asana.webhooks.list": {"workspace": WS},
    "asana.webhooks.get": {"webhook_gid": WH},
    "asana.audit_log.list": {"workspace_gid": WS},
    "asana.organization_exports.get": {"organization_export_gid": OEX},
}


@pytest.mark.parametrize("fid", ALL_TAREA6)
@pytest.mark.asyncio
async def test_tarea6_each_function_validates_its_required_input(fid, db):
    res = await run(fid, {}, db, api({})[0])
    assert res.error.code == ErrorCode.invalid_input


@pytest.mark.parametrize("fid", sorted(APP_ERROR_ARGS6))
@pytest.mark.asyncio
async def test_tarea6_each_function_maps_upstream_404_to_not_found(fid, db):
    res = await run(fid, APP_ERROR_ARGS6[fid], db, api({})[0])
    assert res.error.code == ErrorCode.not_found


@pytest.mark.asyncio
async def test_status_updates_list_uses_parent_query(db):
    body = {"data": [{"gid": SU, "title": "Ronda 1", "resource_subtype": "project_status_update", "status_type": "on_track",
                      "text": "Todo en fecha", "html_text": "<body>Todo en fecha</body>", "author": {"gid": GID, "name": "Ana"},
                      "created_at": "2026-01-01T10:00:00Z", "parent": {"gid": PROJECT, "name": "Web 2026"}}], "next_page": None}
    t, seen = api({"/api/1.0/status_updates": httpx.Response(200, json=body)})
    res = await run("asana.status_updates.list", {"parent": PROJECT, "created_since": "2026-01-01T00:00:00Z"}, db, t)
    assert res.ok and res.data["items"][0]["author"] == GID and res.data["items"][0]["parent"] == PROJECT
    assert seen[0].url.path == "/api/1.0/status_updates"
    assert seen[0].url.params["parent"] == PROJECT and seen[0].url.params["created_since"] == "2026-01-01T00:00:00Z"
    assert seen[0].url.params["limit"] == "100"


@pytest.mark.asyncio
async def test_status_updates_get_ok(db):
    body = {"gid": SU, "title": "Ronda 1", "resource_subtype": "project_status_update", "status_type": "on_track",
            "text": "Todo en fecha", "author": {"gid": GID, "name": "Ana"}, "created_at": "2026-01-01T10:00:00Z",
            "modified_at": "2026-01-01T10:00:00Z", "parent": {"gid": PROJECT, "name": "Web 2026"}}
    t, seen = api({"/api/1.0/status_updates/1200000000006000": httpx.Response(200, json={"data": body})})
    res = await run("asana.status_updates.get", {"status_update_gid": SU}, db, t)
    assert res.ok and res.data["modified_at"] == "2026-01-01T10:00:00Z" and res.data["parent"] == PROJECT
    assert seen[0].url.path == "/api/1.0/status_updates/1200000000006000"


@pytest.mark.asyncio
async def test_memberships_list_uses_parent_filter(db):
    body = {"data": [{"gid": MEM, "resource_type": "membership", "resource_subtype": "project_membership",
                      "member": {"gid": GID, "name": "Ana", "resource_type": "user"},
                      "parent": {"gid": PROJECT, "name": "Web 2026"}, "access_level": "admin"}], "next_page": None}
    t, seen = api({"/api/1.0/memberships": httpx.Response(200, json=body)})
    res = await run("asana.memberships.list", {"parent": PROJECT}, db, t)
    assert res.ok and res.data["items"][0]["member"]["gid"] == GID and res.data["items"][0]["access_level"] == "admin"
    assert seen[0].url.path == "/api/1.0/memberships"
    assert seen[0].url.params["parent"] == PROJECT and seen[0].url.params["opt_fields"] != ""


@pytest.mark.asyncio
async def test_memberships_get_ok(db):
    body = {"gid": MEM, "resource_type": "membership", "resource_subtype": "project_membership",
            "member": {"gid": GID, "name": "Ana", "resource_type": "user"},
            "parent": {"gid": PROJECT, "name": "Web 2026"}, "access_level": "editor"}
    t, seen = api({"/api/1.0/memberships/1200000000006100": httpx.Response(200, json={"data": body})})
    res = await run("asana.memberships.get", {"membership_gid": MEM}, db, t)
    assert res.ok and res.data["member"]["gid"] == GID and res.data["access_level"] == "editor"
    assert seen[0].url.path == "/api/1.0/memberships/1200000000006100"


@pytest.mark.asyncio
async def test_time_tracking_entries_list_task_path_and_categories(db):
    body = {"data": [{"gid": TTE, "duration_minutes": 150, "entered_on": "2026-10-05", "created_by": {"gid": GID, "name": "Ana"},
                      "attributable_to": {"gid": PROJECT, "name": "Web 2026", "resource_subtype": "project"},
                      "categories": [{"gid": TTC, "name": "Development", "color": "blue"}]}], "next_page": None}
    t, seen = api({"/api/1.0/tasks/1200000000000500/time_tracking_entries": httpx.Response(200, json=body)})
    res = await run("asana.time_tracking_entries.list_task", {"task_gid": TASK}, db, t)
    assert res.ok and res.data["items"][0]["created_by"] == GID
    assert res.data["items"][0]["categories"][0]["color"] == "blue"
    assert seen[0].url.path == "/api/1.0/tasks/1200000000000500/time_tracking_entries"


@pytest.mark.asyncio
async def test_time_tracking_entries_get_ok(db):
    body = {"gid": TTE, "description": "Payment flow design", "duration_minutes": 150, "entered_on": "2026-10-05",
            "created_at": "2026-10-05T12:00:00Z", "approval_status": "approved", "billable_status": "billable",
            "created_by": {"gid": GID, "name": "Ana"}, "task": {"gid": TASK, "name": "Pagos", "resource_subtype": "default_task"},
            "attributable_to": {"gid": PROJECT, "name": "Web 2026", "resource_subtype": "project"},
            "categories": [{"gid": TTC, "name": "Development", "color": "blue"}]}
    t, seen = api({"/api/1.0/time_tracking_entries/1200000000006200": httpx.Response(200, json={"data": body})})
    res = await run("asana.time_tracking_entries.get", {"entry_gid": TTE}, db, t)
    assert res.ok and res.data["task"] == TASK and res.data["duration_minutes"] == 150
    assert seen[0].url.path == "/api/1.0/time_tracking_entries/1200000000006200"


@pytest.mark.asyncio
async def test_time_tracking_entries_list_sends_workspace_user_and_dates(db):
    body = {"data": [{"gid": TTE, "duration_minutes": 150, "entered_on": "2026-10-05", "created_by": {"gid": GID, "name": "Ana"},
                      "attributable_to": {"gid": PROJECT, "name": "Web 2026", "resource_subtype": "project"},
                      "categories": [{"gid": TTC, "name": "Development", "color": "blue"}]}], "next_page": None}
    t, seen = api({"/api/1.0/time_tracking_entries": httpx.Response(200, json=body)})
    res = await run("asana.time_tracking_entries.list",
                    {"workspace_gid": WS, "user_gid": "me", "entered_on_start_date": "2026-10-01", "entered_on_end_date": "2026-10-31"}, db, t)
    assert res.ok and res.data["items"][0]["entered_on"] == "2026-10-05"
    assert seen[0].url.path == "/api/1.0/time_tracking_entries"
    assert seen[0].url.params["user"] == "me" and seen[0].url.params["workspace"] == WS and "task" not in seen[0].url.params
    assert seen[0].url.params["entered_on_start_date"] == "2026-10-01"
    assert seen[0].url.params["entered_on_end_date"] == "2026-10-31"


@pytest.mark.asyncio
async def test_time_tracking_entries_list_needs_a_workspace_or_a_task(db):
    t, seen = api({"/api/1.0/time_tracking_entries": httpx.Response(200, json={"data": [], "next_page": None})})
    res = await run("asana.time_tracking_entries.list", {"user_gid": "me"}, db, t)  # solo user: Asana responde 400, asi que ni se llama
    assert res.error.code == ErrorCode.invalid_input and not seen
    res = await run("asana.time_tracking_entries.list", {"task_gid": TASK}, db, t)
    assert res.ok and seen[0].url.params["task"] == TASK and "user" not in seen[0].url.params


@pytest.mark.asyncio
async def test_project_templates_list_accepts_team_only_and_needs_one_of_them(db):
    t, seen = api({"/api/1.0/project_templates": httpx.Response(200, json={"data": [], "next_page": None})})
    res = await run("asana.project_templates.list", {"team": TEAM}, db, t)  # una organizacion solo admite team
    assert res.ok and seen[0].url.params["team"] == TEAM and "workspace" not in seen[0].url.params
    res = await run("asana.project_templates.list", {}, db, t)
    assert res.error.code == ErrorCode.invalid_input and len(seen) == 1


@pytest.mark.asyncio
async def test_time_tracking_categories_list_uses_workspace_query(db):
    body = {"data": [{"gid": TTC, "name": "Development", "color": "blue", "is_archived": False}], "next_page": None}
    t, seen = api({"/api/1.0/time_tracking_categories": httpx.Response(200, json=body)})
    res = await run("asana.time_tracking_categories.list", {"workspace": WS, "is_archived": True}, db, t)
    assert res.ok and res.data["items"][0]["is_archived"] is False
    assert seen[0].url.path == "/api/1.0/time_tracking_categories"
    assert seen[0].url.params["workspace"] == WS and seen[0].url.params["is_archived"] == "true"


@pytest.mark.asyncio
async def test_time_tracking_categories_get_ok(db):
    body = {"gid": TTC, "name": "Development", "color": "blue", "is_archived": False}
    t, seen = api({"/api/1.0/time_tracking_categories/1200000000006300": httpx.Response(200, json={"data": body})})
    res = await run("asana.time_tracking_categories.get", {"category_gid": TTC}, db, t)
    assert res.ok and res.data["color"] == "blue"
    assert seen[0].url.path == "/api/1.0/time_tracking_categories/1200000000006300"


@pytest.mark.asyncio
async def test_time_tracking_categories_list_entries_ok(db):
    body = {"data": [{"gid": TTE, "duration_minutes": 150, "entered_on": "2026-10-05", "created_by": {"gid": GID, "name": "Ana"},
                      "attributable_to": {"gid": PROJECT, "name": "Web 2026", "resource_subtype": "project"},
                      "categories": [{"gid": TTC, "name": "Development", "color": "blue"}]}], "next_page": None}
    t, seen = api({"/api/1.0/time_tracking_categories/1200000000006300/time_tracking_entries": httpx.Response(200, json=body)})
    res = await run("asana.time_tracking_categories.list_entries", {"category_gid": TTC, "start_date": "2026-10-01"}, db, t)
    assert res.ok and res.data["items"][0]["duration_minutes"] == 150
    assert seen[0].url.path == "/api/1.0/time_tracking_categories/1200000000006300/time_tracking_entries"
    assert seen[0].url.params["start_date"] == "2026-10-01"


@pytest.mark.asyncio
async def test_webhooks_list_requires_workspace_and_forwards_offset(db):
    body = {"data": [{"gid": WH, "target": "https://hooks.ejemplo.com/asana", "resource": {"gid": PROJECT, "name": "Web 2026"},
                      "active": True, "created_at": "2026-01-01T10:00:00Z", "last_success_at": "2026-01-01T11:00:00Z",
                      "last_failure_at": None, "filters": [{"action": "add", "fields": [], "resource_subtype": "task"}]}],
            "next_page": {"offset": "eyJpdiI6MSJ9"}}
    t, seen = api({"/api/1.0/webhooks": httpx.Response(200, json=body)})
    res = await run("asana.webhooks.list", {"workspace": WS, "resource": PROJECT, "offset": "eyJpdiI6MSJ9"}, db, t)
    assert res.ok and res.data["has_more"] is True and res.data["next_offset"] == "eyJpdiI6MSJ9"
    assert res.data["items"][0]["resource"] == PROJECT and res.data["items"][0]["filters"][0]["action"] == "add"
    assert seen[0].url.path == "/api/1.0/webhooks"
    assert seen[0].url.params["workspace"] == WS and seen[0].url.params["resource"] == PROJECT
    assert seen[0].url.params["offset"] == "eyJpdiI6MSJ9"


@pytest.mark.asyncio
async def test_webhooks_get_ok(db):
    body = {"gid": WH, "target": "https://hooks.ejemplo.com/asana", "resource": {"gid": PROJECT, "name": "Web 2026"},
            "active": True, "created_at": "2026-01-01T10:00:00Z", "last_success_at": "2026-01-01T11:00:00Z",
            "last_failure_at": None, "next_attempt_after": None, "delivery_retry_count": 0,
            "filters": [{"action": "add", "fields": [], "resource_subtype": "task"}]}
    t, seen = api({"/api/1.0/webhooks/1200000000006400": httpx.Response(200, json={"data": body})})
    res = await run("asana.webhooks.get", {"webhook_gid": WH}, db, t)
    assert res.ok and res.data["active"] is True and res.data["delivery_retry_count"] == 0
    assert seen[0].url.path == "/api/1.0/webhooks/1200000000006400"


@pytest.mark.asyncio
async def test_audit_log_list_path_and_actor(db):
    body = {"data": [{"gid": AUD, "created_at": "2026-10-05T12:00:00.000Z", "event_type": "task_deleted",
                      "event_category": "deletion",
                      "actor": {"actor_type": "user", "gid": GID, "name": "Ana Perez", "email": "ana@empresa.test"},
                      "resource": {"resource_type": "task", "resource_subtype": "default_task", "gid": TASK, "name": "Rediseno portada"}}],
            "next_page": None}
    t, seen = api({"/api/1.0/workspaces/1200000000000002/audit_log_events": httpx.Response(200, json=body)})
    res = await run("asana.audit_log.list", {"workspace_gid": WS, "event_type": "task_deleted"}, db, t)
    assert res.ok and res.data["items"][0]["actor"]["email"] == "ana@empresa.test"
    assert res.data["items"][0]["resource"]["gid"] == TASK
    assert seen[0].url.path == "/api/1.0/workspaces/1200000000000002/audit_log_events"
    assert seen[0].url.params["event_type"] == "task_deleted" and seen[0].url.params["limit"] == "100"


@pytest.mark.asyncio
async def test_organization_exports_get_ok(db):
    body = {"gid": OEX, "state": "started", "created_at": "2026-01-01T10:00:00Z", "download_url": None,
            "organization": {"gid": WS, "name": "Mi equipo"}}
    t, seen = api({"/api/1.0/organization_exports/1200000000006600": httpx.Response(200, json={"data": body})})
    res = await run("asana.organization_exports.get", {"organization_export_gid": OEX}, db, t)
    assert res.ok and res.data["organization"] == WS and res.data["state"] == "started"
    assert seen[0].url.path == "/api/1.0/organization_exports/1200000000006600"