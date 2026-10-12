"""Asana: pruebas simuladas de las Tareas 7, 8 (lecturas avanzadas) y 9 (herramientas viejas migradas). Cada funcion tiene su caso normal,
su entrada invalida y un error de la app; las de escritura ademas verifican el cuerpo enviado y que /debug las simula sin llamar a Asana."""
import httpx
import pytest
import pytest_asyncio  # noqa: F401  (los fixtures async vienen de test_asana)

from app.functions.registry import get_function, load_all
from app.functions.spec import ErrorCode, Verb
from test_asana import GID, WS, api, db, run  # noqa: F401

P = "/api/1.0"
PROJECT = "1200000000000100"
TASK = "1200000000000500"
TAG = "1200000000000900"
USER2 = "1200000000000010"


@pytest.fixture(autouse=True, scope="module")
def _registry():
    load_all()


def ok(body, status=200):
    return httpx.Response(status, json=body)


NO_NEXT = {"has_more": False, "next_offset": None}

# (function id, input, path, response body, subset of the expected data, expected query params)
READ_CASES = [
    ("asana.typeahead.search", {"workspace_gid": WS, "resource_type": "project", "query": "web", "count": 5},
     f"{P}/workspaces/{WS}/typeahead", {"data": [{"gid": PROJECT, "resource_type": "project", "name": "Web 2026"}]},
     {"items": [{"gid": PROJECT, "resource_type": "project", "name": "Web 2026"}], **NO_NEXT},
     {"resource_type": "project", "query": "web", "count": "5"}),
    ("asana.reactions.list", {"target": "700", "emoji_base": "👍"}, f"{P}/reactions",
     {"data": [{"gid": "701", "emoji": "👍", "user": {"gid": GID, "resource_type": "user", "name": "Ana"}}], "next_page": {"offset": "abc"}},
     {"items": [{"gid": "701", "emoji": "👍", "user": GID}], "has_more": True, "next_offset": "abc"},
     {"target": "700", "emoji_base": "👍", "limit": "100"}),
    ("asana.allocations.get", {"allocation_gid": "720"}, f"{P}/allocations/720",
     {"data": {"gid": "720", "start_date": "2026-10-01", "end_date": "2026-10-31", "effort": {"type": "hours", "value": 20},
               "assignee": {"gid": GID}, "parent": {"gid": PROJECT}, "created_by": {"gid": GID}, "resource_subtype": "project_allocation"}},
     {"gid": "720", "effort_type": "hours", "effort_value": 20.0, "assignee": GID, "parent": PROJECT}, {}),
    ("asana.allocations.list", {"parent": PROJECT}, f"{P}/allocations",
     {"data": [{"gid": "720", "start_date": "2026-10-01", "end_date": "2026-10-31", "effort": {"type": "percent", "value": 50}}]},
     {"items": [{"gid": "720", "start_date": "2026-10-01", "end_date": "2026-10-31", "effort_type": "percent", "effort_value": 50.0,
                 "assignee": None, "parent": None, "created_by": None, "resource_subtype": None}], **NO_NEXT}, {"parent": PROJECT}),
    ("asana.project_briefs.get", {"project_brief_gid": "730"}, f"{P}/project_briefs/730",
     {"data": {"gid": "730", "title": "Brief", "text": "Hola", "html_text": "<body>Hola</body>", "permalink_url": "https://app.asana.com/x",
               "project": {"gid": PROJECT}}},
     {"gid": "730", "title": "Brief", "project": PROJECT}, {}),
    ("asana.project_portfolio_settings.get", {"project_portfolio_setting_gid": "740"}, f"{P}/project_portfolio_settings/740",
     {"data": {"gid": "740", "project": {"gid": PROJECT}, "portfolio": {"gid": "750"}, "is_access_control_inherited": True, "created_at": "2026-01-01T10:00:00Z"}},
     {"gid": "740", "project": PROJECT, "portfolio": "750", "is_access_control_inherited": True}, {}),
    ("asana.project_portfolio_settings.list_project", {"project_gid": PROJECT}, f"{P}/projects/{PROJECT}/project_portfolio_settings",
     {"data": [{"gid": "740", "project": {"gid": PROJECT}, "portfolio": {"gid": "750"}}]},
     {"items": [{"gid": "740", "project": PROJECT, "portfolio": "750", "is_access_control_inherited": None, "created_at": None}], **NO_NEXT}, {}),
    ("asana.project_portfolio_settings.list_portfolio", {"portfolio_gid": "750"}, f"{P}/portfolios/750/project_portfolio_settings",
     {"data": [{"gid": "740", "project": {"gid": PROJECT}, "portfolio": {"gid": "750"}}]},
     {"items": [{"gid": "740", "project": PROJECT, "portfolio": "750", "is_access_control_inherited": None, "created_at": None}], **NO_NEXT}, {}),
    ("asana.ooo_entries.get", {"ooo_entry_gid": "760"}, f"{P}/ooo_entries/760",
     {"data": {"gid": "760", "start_date": "2026-12-22", "end_date": "2026-12-31", "user": {"gid": GID}, "created_by": {"gid": GID}}},
     {"gid": "760", "start_date": "2026-12-22", "end_date": "2026-12-31", "user": GID, "created_by": GID}, {}),
    ("asana.ooo_entries.list", {"user": GID, "workspace": WS, "start_date": "2026-12-01"}, f"{P}/ooo_entries",
     {"data": [{"gid": "760", "start_date": "2026-12-22", "end_date": "2026-12-31", "user": {"gid": GID}}]},
     {"items": [{"gid": "760", "start_date": "2026-12-22", "end_date": "2026-12-31", "user": GID, "created_by": None}], **NO_NEXT},
     {"user": GID, "workspace": WS, "start_date": "2026-12-01"}),
    ("asana.rates.list", {"workspace": WS, "parent": PROJECT, "resource": GID}, f"{P}/rates",
     {"data": [{"gid": "770", "parent": {"gid": PROJECT}, "resource": {"gid": GID}, "rate": 45, "currency_code": "USD"}]},
     {"items": [{"gid": "770", "parent": PROJECT, "resource": GID, "rate": 45.0, "currency_code": "USD", "created_by": None}], **NO_NEXT},
     {"workspace": WS, "parent": PROJECT, "resource": GID}),
    ("asana.rates.get", {"rate_gid": "770"}, f"{P}/rates/770",
     {"data": {"gid": "770", "parent": {"gid": PROJECT}, "resource": {"gid": GID}, "rate": 45, "currency_code": "USD", "created_by": {"gid": GID}}},
     {"gid": "770", "rate": 45.0, "currency_code": "USD", "created_by": GID}, {}),
    ("asana.roles.list", {"workspace": WS, "archived": True}, f"{P}/roles",
     {"data": [{"gid": "780", "name": "Billing admin", "description": "Billing", "is_standard_role": False}]},
     {"items": [{"gid": "780", "name": "Billing admin", "description": "Billing", "is_standard_role": False}], **NO_NEXT},
     {"workspace": WS, "archived": "true"}),
    ("asana.roles.get", {"role_gid": "780"}, f"{P}/roles/780",
     {"data": {"gid": "780", "name": "Billing admin", "base_role_type": "member", "permissions": {"assign_roles": False}, "workspace": {"gid": WS}}},
     {"gid": "780", "base_role_type": "member", "permissions": {"assign_roles": False}, "workspace": WS}, {}),
    ("asana.access_requests.list", {"target": PROJECT, "user": "me"}, f"{P}/access_requests",
     {"data": [{"gid": "790", "message": "Please", "approval_status": "pending", "requester": {"gid": USER2}, "target": {"gid": PROJECT}}]},
     {"items": [{"gid": "790", "message": "Please", "approval_status": "pending", "requester": USER2, "target": PROJECT}], **NO_NEXT},
     {"target": PROJECT, "user": "me"}),
    ("asana.jobs.get", {"job_gid": "800"}, f"{P}/jobs/800",
     {"data": {"gid": "800", "resource_subtype": "duplicate_task", "status": "succeeded", "new_task": {"gid": "801", "name": "Copia"}}},
     {"gid": "800", "status": "succeeded", "new_task": "801", "new_project": None, "download_url": None}, {}),
    ("asana.agents.list", {"workspace_gid": WS}, f"{P}/workspaces/{WS}/agents",
     {"data": [{"gid": "810", "name": "Triage", "description": "Sorts", "resource_subtype": "asana_teammate"}]},
     {"items": [{"gid": "810", "name": "Triage", "description": "Sorts", "resource_subtype": "asana_teammate"}], **NO_NEXT}, {}),
    ("asana.agents.get", {"agent_gid": "810"}, f"{P}/agents/810",
     {"data": {"gid": "810", "name": "Triage", "behavior_guidance": "Label requests", "workspace": {"gid": WS}}},
     {"gid": "810", "behavior_guidance": "Label requests", "workspace": WS}, {}),
    ("asana.ai_studio_usage.get_runs", {"workspace_gid": WS, "start_at": "2026-10-01T00:00:00Z", "division_gid": "55"},
     f"{P}/workspaces/{WS}/ai_studio/runs",
     {"data": [{"gid": "820", "rule": {"gid": "821", "name": "Triage"}, "triggered_by": {"gid": GID}, "status": "success", "credits_used": 1.5,
                "credit_source": "paid"}], "next_page": None},
     {"items": [{"gid": "820", "rule": "821", "rule_name": "Triage", "rule_owner": None, "triggered_by": GID, "division": None,
                 "run_started_at": None, "run_completed_at": None, "status": "success", "model": None, "credits_used": 1.5,
                 "credit_source": "paid"}], **NO_NEXT},
     {"start_at": "2026-10-01T00:00:00Z", "division_gid": "55"}),
    ("asana.ai_studio_usage.get_seats", {"workspace_gid": WS, "state": "active"}, f"{P}/workspaces/{WS}/ai_studio/seats",
     {"data": [{"gid": "830", "user": {"gid": GID, "email": "ana@empresa.test"}, "license": "ai_studio_pro", "state": "active"}]},
     {"items": [{"gid": "830", "user": GID, "user_email": "ana@empresa.test", "license": "ai_studio_pro", "state": "active", "assigned_at": None,
                 "revoked_at": None, "assigned_by": None}], **NO_NEXT}, {"state": "active"}),
    ("asana.time_periods.get", {"time_period_gid": "840"}, f"{P}/time_periods/840",
     {"data": {"gid": "840", "display_name": "Q3 FY26", "period": "Q3", "start_on": "2026-07-01", "end_on": "2026-09-30", "parent": {"gid": "841"}}},
     {"gid": "840", "display_name": "Q3 FY26", "period": "Q3", "parent": "841"}, {}),
    ("asana.time_periods.list", {"workspace": WS, "start_on": "2026-01-01"}, f"{P}/time_periods",
     {"data": [{"gid": "840", "display_name": "Q3 FY26", "period": "Q3", "start_on": "2026-07-01", "end_on": "2026-09-30"}]},
     {"items": [{"gid": "840", "display_name": "Q3 FY26", "period": "Q3", "start_on": "2026-07-01", "end_on": "2026-09-30", "parent": None}], **NO_NEXT},
     {"workspace": WS, "start_on": "2026-01-01"}),
    ("asana.timesheet_approval_statuses.get", {"timesheet_approval_status_gid": "850"}, f"{P}/timesheet_approval_statuses/850",
     {"data": {"gid": "850", "user": {"gid": GID}, "workspace": {"gid": WS}, "start_date": "2026-10-05", "end_date": "2026-10-11", "approval_status": "SUBMITTED"}},
     {"gid": "850", "user": GID, "workspace": WS, "approval_status": "SUBMITTED"}, {}),
    ("asana.timesheet_approval_statuses.list", {"workspace": WS, "approval_statuses": "submitted", "from_date": "2026-10-01"},
     f"{P}/timesheet_approval_statuses",
     {"data": [{"gid": "850", "user": {"gid": GID}, "approval_status": "SUBMITTED"}]},
     {"items": [{"gid": "850", "user": GID, "workspace": None, "start_date": None, "end_date": None, "approval_status": "SUBMITTED", "created_at": None}],
      **NO_NEXT}, {"workspace": WS, "approval_statuses": "submitted", "from_date": "2026-10-01"}),
    ("asana.custom_types.list", {"workspace": WS}, f"{P}/custom_types",
     {"data": [{"gid": "860", "name": "Bug", "status_options": [{"gid": "861", "name": "Open", "completion_state": "incomplete", "enabled": True}]}]},
     {"items": [{"gid": "860", "name": "Bug", "asana_created_type_identifier": None,
                 "status_options": [{"gid": "861", "name": "Open", "completion_state": "incomplete", "enabled": True, "color": None}]}], **NO_NEXT},
     {"workspace": WS}),
    ("asana.custom_types.get", {"custom_type_gid": "860"}, f"{P}/custom_types/860",
     {"data": {"gid": "860", "name": "Bug", "asana_created_type_identifier": "SERVICE_TICKET", "status_options": []}},
     {"gid": "860", "name": "Bug", "asana_created_type_identifier": "SERVICE_TICKET", "status_options": []}, {}),
    ("asana.user_task_lists.get", {"user_task_list_gid": "870"}, f"{P}/user_task_lists/870",
     {"data": {"gid": "870", "name": "My tasks", "owner": {"gid": GID}, "workspace": {"gid": WS}}},
     {"gid": "870", "name": "My tasks", "owner": GID, "workspace": WS}, {}),
    ("asana.user_task_lists.get_user", {"user_gid": "me", "workspace": WS}, f"{P}/users/me/user_task_list",
     {"data": {"gid": "870", "name": "My tasks", "owner": {"gid": GID}, "workspace": {"gid": WS}}},
     {"gid": "870", "owner": GID}, {"workspace": WS}),
    # --- Tarea 9: lecturas ---
    ("asana.users.list", {"workspace_gid": WS, "limit": 2}, f"{P}/users",
     {"data": [{"gid": GID, "name": "Ana Perez", "email": "ana@empresa.test"}], "next_page": {"offset": "o1"}},
     {"items": [{"gid": GID, "name": "Ana Perez", "email": "ana@empresa.test"}], "has_more": True, "next_offset": "o1"}, {"workspace": WS, "limit": "2"}),
    ("asana.tasks.list", {"project": PROJECT, "modified_since": "2026-10-01T00:00:00Z"}, f"{P}/tasks",
     {"data": [{"gid": TASK, "name": "Propuesta", "assignee": {"gid": GID}, "due_on": "2026-02-01", "completed": False}]},
     {"items": [{"gid": TASK, "name": "Propuesta", "assignee": GID, "due_on": "2026-02-01", "completed": False}], **NO_NEXT},
     {"project": PROJECT, "modified_since": "2026-10-01T00:00:00Z"}),
    ("asana.tasks.get", {"task_gid": TASK}, f"{P}/tasks/{TASK}",
     {"data": {"gid": TASK, "name": "Propuesta", "notes": "Precios", "assignee": {"gid": GID}, "due_on": "2026-02-01", "completed": False,
               "projects": [{"gid": PROJECT, "name": "Web"}], "tags": [{"gid": TAG}], "dependencies": [{"gid": "501"}],
               "permalink_url": "https://app.asana.com/0/1/2"}},
     {"gid": TASK, "description": "Precios", "projects": [PROJECT], "tags": [TAG], "dependencies": ["501"], "assignee": GID}, {}),
    ("asana.tasks.list_tag_tasks", {"tag_gid": TAG}, f"{P}/tags/{TAG}/tasks",
     {"data": [{"gid": TASK, "name": "Propuesta", "assignee": {"gid": GID}, "due_on": None, "completed": True}]},
     {"items": [{"gid": TASK, "name": "Propuesta", "assignee": GID, "due_on": None, "completed": True}], **NO_NEXT}, {}),
    ("asana.tasks.list_completed", {"assignee": "me", "workspace_gid": WS, "completed_since": "2026-10-01T00:00:00Z"}, f"{P}/tasks",
     {"data": [{"gid": "1", "name": "Hecha", "completed": True, "completed_at": "2026-10-03T10:00:00Z", "assignee": {"gid": GID}},
               {"gid": "2", "name": "Abierta", "completed": False}]},
     {"items": [{"gid": "1", "name": "Hecha", "completed_at": "2026-10-03T10:00:00Z", "assignee": GID}], **NO_NEXT},
     {"assignee": "me", "workspace": WS, "completed_since": "2026-10-01T00:00:00Z"}),
    ("asana.tasks.list_incomplete", {"project": PROJECT}, f"{P}/tasks",
     {"data": [{"gid": "2", "name": "Abierta", "completed": False, "due_on": "2026-02-01"}, {"gid": "3", "name": "Cerrada", "completed": True}]},
     {"items": [{"gid": "2", "name": "Abierta", "assignee": None, "due_on": "2026-02-01", "completed": False}], **NO_NEXT},
     {"project": PROJECT, "completed_since": "now"}),
    ("asana.projects.list", {"workspace_gid": WS, "archived": False}, f"{P}/projects",
     {"data": [{"gid": PROJECT, "name": "Web 2026", "owner": {"gid": GID}, "due_on": "2026-12-31"}]},
     {"items": [{"gid": PROJECT, "name": "Web 2026", "owner": GID, "due_on": "2026-12-31"}], **NO_NEXT}, {"workspace": WS, "archived": "false"}),
    ("asana.projects.get", {"project_gid": PROJECT}, f"{P}/projects/{PROJECT}",
     {"data": {"gid": PROJECT, "name": "Web 2026", "owner": {"gid": GID}, "due_on": "2026-12-31", "notes": "Rediseno", "archived": False,
               "members": [{"gid": GID}], "custom_fields": [{"gid": "400", "name": "Priority", "display_value": "High"}]}},
     {"gid": PROJECT, "description": "Rediseno", "members": [GID], "custom_fields": [{"gid": "400", "name": "Priority", "display_value": "High"}]}, {}),
    ("asana.tags.list", {"workspace_gid": WS}, f"{P}/tags",
     {"data": [{"gid": TAG, "name": "Urgente", "color": "red"}]},
     {"items": [{"gid": TAG, "name": "Urgente", "color": "red"}], **NO_NEXT}, {"workspace": WS}),
    ("asana.stories.list_task_stories", {"task_gid": TASK, "only_comments": True, "newest_first": True}, f"{P}/tasks/{TASK}/stories",
     {"data": [{"gid": "900", "type": "comment", "text": "Listo", "created_by": {"gid": GID}, "created_at": "2026-01-20T10:00:00Z"}]},
     {"items": [{"gid": "900", "type": "comment", "text": "Listo", "created_by": GID, "created_at": "2026-01-20T10:00:00Z"}], **NO_NEXT},
     {"resource_subtype": "comment_added", "sort_ascending": "false"}),
    ("asana.teams.list_workspace", {"workspace_gid": WS}, f"{P}/workspaces/{WS}/teams",
     {"data": [{"gid": "800", "name": "Marketing", "organization": {"gid": WS}}]},
     {"items": [{"gid": "800", "name": "Marketing", "organization": WS}], **NO_NEXT}, {}),
    ("asana.team_memberships.list", {"user_gid": "me", "workspace_gid": WS}, f"{P}/team_memberships",
     {"data": [{"gid": "910", "user": {"gid": GID}, "team": {"gid": "800"}, "is_admin": True}]},
     {"items": [{"gid": "910", "user": GID, "team": "800", "is_admin": True}], **NO_NEXT}, {"user": "me", "workspace": WS}),
    ("asana.project_memberships.list_project", {"project_gid": PROJECT, "user_gid": "me"}, f"{P}/projects/{PROJECT}/project_memberships",
     {"data": [{"gid": "920", "user": {"gid": GID}, "project": {"gid": PROJECT}, "access_level": "admin", "write_access": "full_write"}]},
     {"items": [{"gid": "920", "user": GID, "project": PROJECT, "access_level": "admin", "write_access": "full_write"}], **NO_NEXT}, {"user": "me"}),
]

EVENT = {"user": {"gid": GID}, "resource": {"gid": TASK, "resource_type": "task", "name": "Propuesta"}, "type": "task", "action": "changed",
         "parent": {"gid": PROJECT}, "created_at": "2026-01-20T10:00:00Z", "change": {"field": "completed", "action": "changed", "new_value": True}}
EVENT_OUT = {"type": "task", "action": "changed", "resource_gid": TASK, "resource_type": "task", "resource_name": "Propuesta",
             "parent_gid": PROJECT, "user_gid": GID, "created_at": "2026-01-20T10:00:00Z",
             "change": {"field": "completed", "action": "changed", "new_value": True}}

# Entradas validas para provocar un 404 de la app en las funciones que no estan en READ_CASES
WRITE_ARGS = {
    "asana.tasks.create": {"name": "Nueva", "projects": [PROJECT]},
    "asana.tasks.update": {"task_gid": TASK, "completed": True},
    "asana.tasks.duplicate": {"task_gid": TASK},
    "asana.tasks.add_tag": {"task_gid": TASK, "tag_gid": TAG},
    "asana.tasks.assign": {"task_gid": TASK, "assignee": "me"},
    "asana.tasks.update_description": {"task_gid": TASK, "description": "Texto"},
    "asana.stories.create_task_story": {"task_gid": TASK, "text": "Hola"},
}
EVENT_ARGS = {"asana.workspaces.get_events": {"workspace_gid": WS}, "asana.events.list": {"resource": PROJECT}}

ALL_IDS = [c[0] for c in READ_CASES] + sorted(WRITE_ARGS) + sorted(EVENT_ARGS)
ARGS_BY_ID = {c[0]: c[1] for c in READ_CASES} | WRITE_ARGS | EVENT_ARGS
# funciones cuyos campos son todos opcionales: se prueban con un limit fuera de rango
NO_REQUIRED = {"asana.rates.list": {"limit": 0}, "asana.custom_types.list": {"limit": 0}, "asana.users.list": {"limit": 0},
               "asana.projects.list": {"limit": 0}}


V2_IDS = {"asana.rates.list"}  # subio a v2: Asana pide `parent` o `workspace` y la v1 no podia mandar `workspace`


def test_the_three_tasks_cover_the_fifty_functions():
    assert len(ALL_IDS) == 50 and len(set(ALL_IDS)) == 50
    for fid in ALL_IDS:
        assert get_function(fid).spec.version == (2 if fid in V2_IDS else 1)


@pytest.mark.parametrize("fid", ALL_IDS)
@pytest.mark.asyncio
async def test_each_function_validates_its_input(fid, db):
    res = await run(fid, NO_REQUIRED.get(fid, {}), db, api({})[0])
    assert res.error.code == ErrorCode.invalid_input


@pytest.mark.parametrize("fid", ALL_IDS)
@pytest.mark.asyncio
async def test_each_function_maps_upstream_404_to_not_found(fid, db):
    res = await run(fid, ARGS_BY_ID[fid], db, api({})[0])
    assert res.error.code == ErrorCode.not_found


@pytest.mark.parametrize("fid,args,path,body,expected,params", READ_CASES, ids=[c[0] for c in READ_CASES])
@pytest.mark.asyncio
async def test_read_function_ok(fid, args, path, body, expected, params, db):
    t, seen = api({path: ok(body)})
    res = await run(fid, args, db, t)
    assert res.ok, res.error
    for key, value in expected.items():
        assert res.data[key] == value, key
    assert len(seen) == 1 and seen[0].method == "GET" and seen[0].url.path == path
    assert seen[0].headers["authorization"] == "Bearer old-token"
    for key, value in params.items():
        assert seen[0].url.params[key] == value, key


def test_read_functions_are_read_and_writes_are_marked():
    for fid in [c[0] for c in READ_CASES] + sorted(EVENT_ARGS):
        spec = get_function(fid).spec
        assert spec.verb == Verb.read and not spec.exits_outside
    assert get_function("asana.tasks.create").spec.verb == Verb.create
    assert get_function("asana.tasks.duplicate").spec.verb == Verb.create
    for fid in ("asana.tasks.update", "asana.tasks.add_tag", "asana.tasks.update_description"):
        assert get_function(fid).spec.verb == Verb.update and not get_function(fid).spec.exits_outside
    # asignar y comentar notifican a otras personas: salen al exterior (marca E del catalogo)
    for fid in ("asana.tasks.assign", "asana.stories.create_task_story"):
        assert get_function(fid).spec.exits_outside


def test_extra_validators_reject_unscoped_requests():
    from pydantic import ValidationError
    for fid, args in (("asana.allocations.list", {}), ("asana.tasks.list", {"assignee": "me"}), ("asana.tasks.list_incomplete", {"workspace_gid": WS}),
                      ("asana.tasks.create", {"name": "x"}), ("asana.tasks.update", {"task_gid": TASK}),
                      ("asana.team_memberships.list", {"user_gid": "me"})):
        with pytest.raises(ValidationError):
            get_function(fid).input_model.model_validate(args)


# --- Tarea 9: escritura -----------------------------------------------------------------------

import json  # noqa: E402

TASK_BODY = {"data": {"gid": TASK, "name": "Nueva", "notes": "Texto", "assignee": {"gid": GID}, "due_on": "2026-02-01", "completed": True,
                      "created_at": "2026-01-20T10:00:00Z", "permalink_url": "https://app.asana.com/0/1/2"}}


@pytest.mark.asyncio
async def test_tasks_create_sends_projects_and_hides_workspace(db):
    t, seen = api({f"{P}/tasks": ok(TASK_BODY, 201)})
    res = await run("asana.tasks.create", {"name": "Nueva", "projects": [PROJECT], "workspace_gid": WS, "assignee": "me", "due_on": "2026-02-01",
                                           "notes": "Texto"}, db, t)
    assert res.ok and res.data["gid"] == TASK and res.data["description"] == "Texto" and res.data["assignee"] == GID
    assert seen[0].method == "POST" and json.loads(seen[0].content) == {
        "data": {"name": "Nueva", "projects": [PROJECT], "assignee": "me", "due_on": "2026-02-01", "notes": "Texto"}}


@pytest.mark.asyncio
async def test_tasks_create_with_workspace_only(db):
    t, seen = api({f"{P}/tasks": ok(TASK_BODY, 201)})
    res = await run("asana.tasks.create", {"name": "Nueva", "workspace_gid": WS}, db, t)
    assert res.ok and json.loads(seen[0].content) == {"data": {"name": "Nueva", "workspace": WS}}


@pytest.mark.asyncio
async def test_tasks_update_sends_only_given_fields_and_maps_description_to_notes(db):
    t, seen = api({f"{P}/tasks/{TASK}": ok(TASK_BODY)})
    res = await run("asana.tasks.update", {"task_gid": TASK, "completed": False, "description": "Texto", "name": "Nueva"}, db, t)
    assert res.ok and res.data["completed"] is True
    assert seen[0].method == "PUT" and json.loads(seen[0].content) == {"data": {"name": "Nueva", "notes": "Texto", "completed": False}}


@pytest.mark.asyncio
async def test_tasks_assign_and_update_description(db):
    t, seen = api({f"{P}/tasks/{TASK}": ok(TASK_BODY)})
    assert (await run("asana.tasks.assign", {"task_gid": TASK, "assignee": "ana@empresa.test"}, db, t)).ok
    assert json.loads(seen[0].content) == {"data": {"assignee": "ana@empresa.test"}}
    assert (await run("asana.tasks.update_description", {"task_gid": TASK, "description": "Agenda"}, db, t)).ok
    assert seen[1].method == "PUT" and json.loads(seen[1].content) == {"data": {"notes": "Agenda"}}


@pytest.mark.asyncio
async def test_tasks_duplicate_returns_the_job(db):
    job = {"data": {"gid": "800", "status": "in_progress", "new_task": {"gid": "501", "name": "Copia"}}}
    t, seen = api({f"{P}/tasks/{TASK}/duplicate": ok(job, 201)})
    res = await run("asana.tasks.duplicate", {"task_gid": TASK, "name": "Copia", "include": "notes,subtasks"}, db, t)
    assert res.ok and res.data == {"job_gid": "800", "status": "in_progress", "new_task": "501", "new_task_name": "Copia"}
    assert json.loads(seen[0].content) == {"data": {"include": "notes,subtasks", "name": "Copia"}}


@pytest.mark.asyncio
async def test_tasks_add_tag_posts_the_tag(db):
    t, seen = api({f"{P}/tasks/{TASK}/addTag": ok({"data": {}})})
    res = await run("asana.tasks.add_tag", {"task_gid": TASK, "tag_gid": TAG}, db, t)
    assert res.ok and res.data == {"task_gid": TASK, "tag_gid": TAG, "added": True}
    assert seen[0].method == "POST" and json.loads(seen[0].content) == {"data": {"tag": TAG}}


@pytest.mark.asyncio
async def test_stories_create_task_story_posts_text(db):
    body = {"data": {"gid": "900", "type": "comment", "text": "Hola", "created_by": {"gid": GID}, "created_at": "2026-01-20T10:00:00Z"}}
    t, seen = api({f"{P}/tasks/{TASK}/stories": ok(body, 201)})
    res = await run("asana.stories.create_task_story", {"task_gid": TASK, "text": "Hola"}, db, t)
    assert res.ok and res.data["gid"] == "900" and res.data["created_by"] == GID
    assert seen[0].method == "POST" and json.loads(seen[0].content) == {"data": {"text": "Hola"}}


@pytest.mark.parametrize("fid", sorted(WRITE_ARGS))
@pytest.mark.asyncio
async def test_writes_are_simulated_and_never_reach_asana(fid, db):
    t, seen = api({})
    fn = get_function(fid)
    res = await run(fid, fn.spec.examples[0].input, db, t, simulate=True)
    assert res.ok and res.meta.simulated and res.data == fn.spec.examples[0].output and seen == []


# --- eventos (sync token) ---------------------------------------------------------------------

@pytest.mark.asyncio
async def test_events_without_token_returns_the_starting_token(db):
    t, seen = api({f"{P}/events": ok({"errors": [{"message": "Sync token invalid or too old"}], "sync": "tok1"}, 412)})
    res = await run("asana.events.list", {"resource": PROJECT}, db, t)
    assert res.ok and res.data == {"items": [], "sync": "tok1", "has_more": False, "sync_reset": True}
    assert seen[0].url.params["resource"] == PROJECT and "sync" not in seen[0].url.params


@pytest.mark.asyncio
async def test_events_with_token_returns_events_and_the_next_token(db):
    t, seen = api({f"{P}/events": ok({"data": [EVENT], "sync": "tok2", "has_more": True})})
    res = await run("asana.events.list", {"resource": PROJECT, "sync_token": "tok1"}, db, t)
    assert res.ok and res.data == {"items": [EVENT_OUT], "sync": "tok2", "has_more": True, "sync_reset": False}
    assert seen[0].url.params["sync"] == "tok1"


@pytest.mark.asyncio
async def test_workspace_events_use_the_workspace_path(db):
    t, seen = api({f"{P}/workspaces/{WS}/events": ok({"data": [EVENT], "sync": "tok2", "has_more": False})})
    res = await run("asana.workspaces.get_events", {"workspace_gid": WS, "sync_token": "tok1"}, db, t)
    assert res.ok and res.data["items"] == [EVENT_OUT] and res.data["sync"] == "tok2"
    assert seen[0].url.path == f"{P}/workspaces/{WS}/events" and seen[0].url.params["sync"] == "tok1"


@pytest.mark.asyncio
async def test_a_412_does_not_expire_the_account(db):
    from app.core.constants import Collections
    t, _ = api({f"{P}/events": ok({"sync": "tok1"}, 412)})
    await run("asana.events.list", {"resource": PROJECT}, db, t)
    assert (await db[Collections.USER_CONNECTED_ACCOUNTS].find_one({"account_id": GID}))["status"] == "active"


@pytest.mark.asyncio
async def test_rates_list_needs_parent_or_workspace_and_sends_workspace(db):
    t, seen = api({f"{P}/rates": httpx.Response(200, json={"data": [], "next_page": None})})
    res = await run("asana.rates.list", {"resource": GID}, db, t)  # sin parent ni workspace Asana responde 400, asi que ni se llama
    assert res.error.code == ErrorCode.invalid_input and not seen
    res = await run("asana.rates.list", {"workspace": WS}, db, t)
    assert res.ok and seen[0].url.params["workspace"] == WS and "parent" not in seen[0].url.params
