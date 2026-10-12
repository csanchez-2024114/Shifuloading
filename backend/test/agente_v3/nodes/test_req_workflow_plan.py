"""Etapa 3: el flujo de requisitos PLANEA con ids de funcion reales y argumentos, y los valida en codigo ($0, LLM simulado).

Cubre: candidatas sin `ask`/delete, id inventado descartado, dato faltante -> pregunta, plantilla no rechazada,
respaldo estilo viejo y lo que guarda el nivel 4.
"""
import json
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel

import app.agent.shifu_base_v1.graph.req_nodes as rn
from app.functions import registry, select


class SheetIn(BaseModel):
    spreadsheet_id: str
    range: str


class SheetOut(BaseModel):
    values: list[list[str]]
    total: float


class SendIn(BaseModel):
    to: str
    subject: str
    body: str


class AppendIn(BaseModel):
    spreadsheet_id: str
    values: list[list[str]]


class Anything(BaseModel):
    ok: bool = True


def _fn(fid, model, out=Anything, verb="read", policy="assume"):
    spec = SimpleNamespace(
        id=fid, app=fid.split(".")[0], version=1, verb=SimpleNamespace(value=verb),
        confirmation_policy=SimpleNamespace(value=policy),
        description="Does something useful with the app. It needs the inputs listed.",
        input_schema=model.model_json_schema(), output_schema=out.model_json_schema())
    return SimpleNamespace(spec=spec, input_model=model)


GET = _fn("google_sheets.values.get", SheetIn, SheetOut)
SEND = _fn("gmail.messages.send", SendIn, verb="create", policy="draft_and_confirm")
APPEND = _fn("google_sheets.values.append", AppendIn, verb="update")
OFFERED = {f.spec.id: f for f in (GET, SEND, APPEND)}


class _Llm:
    """Devuelve las respuestas en orden y guarda los mensajes que recibio."""
    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    async def ainvoke(self, msgs, **kw):
        self.calls.append(msgs)
        return AIMessage(self.answers.pop(0) if self.answers else "[]")


def _state(**kw):
    return {"user_id": "u1", "messages": [HumanMessage("cada lunes lee la hoja Ventas y mandame el total por Gmail")], **kw}


def _plan(*steps):
    return json.dumps({"goal": "Total semanal", "apps_needed": ["google_sheets", "gmail"], "trigger_type": "schedule",
                       "trigger_event": "cada lunes", "steps": list(steps)})


def _patch(monkeypatch, offered=OFFERED, no_functions=(), plan_llm=None, llm=None):
    async def cands(state, query):
        return dict(offered), list(no_functions)
    monkeypatch.setattr(rn, "_plan_candidates", cands)
    if plan_llm is not None:
        monkeypatch.setattr(rn, "_plan_llm", plan_llm)
    if llm is not None:
        monkeypatch.setattr(rn, "_llm", llm)


# ── candidatas ───────────────────────────────────────────────────────────────

def test_pool_can_exclude_functions_that_need_a_person(monkeypatch):
    monkeypatch.setenv("SHIFU_FUNCTIONS_STATUSES", "active,testing,draft")
    apps = {a.app for a in (registry.load_all() or registry.list_apps())}
    everything = select.function_pool(apps, verbs={"read", "create", "update", "delete"})
    assert any(f.spec.confirmation_policy.value == "ask" for f in everything.values())  # si no, la prueba no probaria nada
    fenced = select.function_pool(apps, exclude_ask=True)
    assert fenced and all(f.spec.confirmation_policy.value != "ask" for f in fenced.values())
    assert all(f.spec.verb.value != "delete" for f in fenced.values())


async def test_candidates_come_from_connected_named_apps_without_delete(monkeypatch):
    monkeypatch.setenv("SHIFU_FUNCTIONS_STATUSES", "active,testing,draft")

    async def connected(db, uid):
        return {"gmail", "google_sheets", "asana"}

    async def search(pool, query, apps, k=5):
        return sorted(pool)[:k]

    monkeypatch.setattr(rn, "mongo_manager", SimpleNamespace(db=object()))
    monkeypatch.setattr(rn, "connected_apps", connected)
    monkeypatch.setattr(rn, "search_functions", search)
    offered, no_functions = await rn._plan_candidates(
        _state(req_apps_scope=["google_sheets", "gmail", "slack"]), "lee la hoja y manda correo")
    assert offered and len(offered) <= 20
    assert {f.spec.app for f in offered.values()} == {"google_sheets", "gmail"}  # asana conectada pero no nombrada
    # Lo irreversible que no borra (enviar correo) SI se ofrece: el usuario confirma el plan paso por paso en el nivel 3.
    assert all(f.spec.verb.value != "delete" for f in offered.values())
    assert no_functions == ["slack"]  # sin funciones: conserva el paso estilo viejo


async def test_candidates_use_every_connected_app_when_none_is_named(monkeypatch):
    monkeypatch.setenv("SHIFU_FUNCTIONS_STATUSES", "active,testing,draft")

    async def connected(db, uid):
        return {"gmail", "asana"}

    async def search(pool, query, apps, k=5):
        return sorted(pool)[:k]

    monkeypatch.setattr(rn, "mongo_manager", SimpleNamespace(db=object()))
    monkeypatch.setattr(rn, "connected_apps", connected)
    monkeypatch.setattr(rn, "search_functions", search)
    offered, _ = await rn._plan_candidates(_state(), "algo")
    assert {f.spec.app for f in offered.values()} == {"gmail", "asana"}


# ── validacion en codigo ─────────────────────────────────────────────────────

async def test_invented_function_id_is_dropped_and_noted(monkeypatch):
    llm = _Llm(_plan(
        {"order": 1, "function_id": "google_sheets.values.leer", "args": {"spreadsheet_id": "S1", "range": "Ventas!A:B"}, "description": "Leer hoja"},
        {"order": 2, "function_id": "gmail.messages.send", "args": {"to": "a@b.com", "subject": "Total", "body": "x"}, "description": "Enviar correo"}))
    _patch(monkeypatch, plan_llm=llm)
    plan = await rn._build_plan(_state())
    assert [s["function_id"] for s in plan["steps"]] == ["gmail.messages.send"]
    assert "Leer hoja" in plan["notes"][0] and plan["missing"] == []


async def test_missing_required_arg_is_reported_not_saved(monkeypatch):
    _patch(monkeypatch, plan_llm=_Llm(_plan(
        {"order": 1, "function_id": "google_sheets.values.get", "args": {"range": "Ventas!A:B", "spreadsheet_id": ""}, "description": "Leer ventas"})))
    plan = await rn._build_plan(_state())
    assert [(m["field"], m["kind"]) for m in plan["missing"]] == [("spreadsheet_id", "missing")]  # "" cuenta como no dado
    assert plan["steps"][0]["args"] == {"range": "Ventas!A:B"}


async def test_unknown_arg_names_are_stripped(monkeypatch):
    _patch(monkeypatch, plan_llm=_Llm(_plan(
        {"order": 1, "function_id": "google_sheets.values.get", "args": {"spreadsheet_id": "S1", "range": "Ventas!A:B", "sheet_name": "Ventas"}, "description": "Leer"})))
    plan = await rn._build_plan(_state())
    assert plan["steps"][0]["args"] == {"spreadsheet_id": "S1", "range": "Ventas!A:B"} and plan["missing"] == []


async def test_a_cell_range_the_user_never_said_is_asked_not_invented(monkeypatch):
    # A1:B1 sin que el usuario lo dijera es un invento del modelo: se quita y se pregunta. Si lo dijo, se conserva.
    step = {"order": 1, "function_id": "google_sheets.values.get", "args": {"spreadsheet_id": "S1", "range": "A1:B1"}, "description": "Leer"}
    _patch(monkeypatch, plan_llm=_Llm(_plan(step)))
    plan = await rn._build_plan(_state())
    assert "range" not in plan["steps"][0]["args"] and [m["field"] for m in plan["missing"]] == ["range"]
    _patch(monkeypatch, plan_llm=_Llm(_plan(step)))
    said = _state(messages=[HumanMessage("cada lunes lee el rango a1:b1 de la hoja Ventas y mandame el total")])
    assert (await rn._build_plan(said))["steps"][0]["args"]["range"] == "A1:B1"
    assert rn._unsaid_range("range", "Ventas!A:B", "lee mi hoja Ventas") is False   # columnas enteras: no es invento
    assert rn._unsaid_range("q", "A1:B1", "lee mi hoja") is False                    # solo campos de rango


async def test_template_args_are_not_rejected(monkeypatch):
    _patch(monkeypatch, plan_llm=_Llm(_plan(
        {"order": 1, "function_id": "google_sheets.values.get", "args": {"spreadsheet_id": "S1", "range": "Ventas!A:B"}, "description": "Leer"},
        # lista que solo se conoce al correr: "{{step_1.values}}" no es list[list[str]] y aun asi es valido
        {"order": 2, "function_id": "google_sheets.values.append", "args": {"spreadsheet_id": "S2", "values": "{{step_1.values}}"}, "description": "Copiar"},
        {"order": 3, "function_id": "gmail.messages.send", "args": {"to": "a@b.com", "subject": "Total", "body": "Total: {{step_1.total}}"}, "description": "Avisar"})))
    plan = await rn._build_plan(_state())
    assert [s["order"] for s in plan["steps"]] == [1, 2, 3] and plan["missing"] == [] and plan["notes"] == []
    assert plan["steps"][1]["args"]["values"] == "{{step_1.values}}"


async def test_template_pointing_to_a_dropped_step_drops_the_dependent(monkeypatch):
    _patch(monkeypatch, plan_llm=_Llm(_plan(
        {"order": 1, "function_id": "inventada.x.y", "args": {}, "description": "Paso raro"},
        {"order": 2, "function_id": "gmail.messages.send", "args": {"to": "a@b.com", "subject": "S", "body": "{{step_1.total}}"}, "description": "Avisar"})))
    plan = await rn._build_plan(_state())
    assert plan["steps"] == [] and len(plan["notes"]) == 2


async def test_template_to_a_later_step_is_dropped(monkeypatch):
    _patch(monkeypatch, plan_llm=_Llm(_plan(
        {"order": 1, "function_id": "gmail.messages.send", "args": {"to": "a@b.com", "subject": "S", "body": "{{step_2.total}}"}, "description": "Avisar"},
        {"order": 2, "function_id": "google_sheets.values.get", "args": {"spreadsheet_id": "S1", "range": "Ventas!A:B"}, "description": "Leer"})))
    plan = await rn._build_plan(_state())
    assert [s["order"] for s in plan["steps"]] == [2]


async def test_give_up_drops_incomplete_step_instead_of_asking_again(monkeypatch):
    _patch(monkeypatch, plan_llm=_Llm(_plan(
        {"order": 1, "function_id": "google_sheets.values.get", "args": {"range": "Ventas!A:B"}, "description": "Leer ventas"})))
    plan = await rn._build_plan(_state(), give_up=True)
    assert plan["steps"] == [] and plan["missing"] == [] and "Leer ventas" in plan["notes"][0]


async def test_offered_candidates_reach_the_prompt_without_inventing_extras(monkeypatch):
    llm = _Llm(_plan())
    _patch(monkeypatch, plan_llm=llm, no_functions=["slack"])
    await rn._build_plan(_state())
    system, human = llm.calls[0][0].content, llm.calls[0][1].content
    assert "google_sheets.values.get [read]" in human and "spreadsheet_id*:string" in human and "out: total:number, values:array<array>" in human
    assert "APPS WITHOUT FUNCTIONS: slack" in human
    assert "{{step_N.field}}" in system and "MUST be copied exactly" in system


# ── respaldo estilo viejo ────────────────────────────────────────────────────

async def test_no_plan_and_no_model_call_when_no_app_has_functions(monkeypatch):
    llm = _Llm(_plan({"order": 1, "app": "slack", "action": "send_message", "description": "Avisar", "node_type": "notificacion"}))
    _patch(monkeypatch, offered={}, no_functions=["slack"], plan_llm=llm)
    plan = await rn._build_plan(_state())
    assert llm.calls == [] and plan["steps"] == [] and "slack" in plan["notes"][0]  # v0.8.0: ya no hay plan del sistema viejo


async def test_step_without_a_real_function_is_always_left_out_with_a_note(monkeypatch):
    _patch(monkeypatch, no_functions=["slack"], plan_llm=_Llm(_plan(
        {"order": 1, "function_id": "google_sheets.values.get", "args": {"spreadsheet_id": "S1", "range": "Ventas!A:B"}, "description": "Leer"},
        {"order": 2, "app": "slack", "action": "send_message", "description": "Avisar al canal", "node_type": "notificacion"},
        {"order": 3, "app": "gmail", "action": "send_email", "description": "Correo inventado"})))
    plan = await rn._build_plan(_state())
    assert [s["order"] for s in plan["steps"]] == [1]
    assert "slack todavía no está disponible" in plan["notes"][0] and "Correo inventado" in plan["notes"][1]


# ── preguntas por datos faltantes ────────────────────────────────────────────

async def test_missing_arg_becomes_one_question_and_the_flow_stays_gathering(monkeypatch):
    plan_llm = _Llm(_plan(
        {"order": 1, "function_id": "google_sheets.values.get", "args": {}, "description": "Leer ventas"}))
    llm = _Llm('["¿Cuál es el enlace de la hoja Ventas?", "¿Qué rango leo?"]')
    _patch(monkeypatch, plan_llm=plan_llm, llm=llm)
    out = await rn._gather(_state(req_preflight_passed=True, req_plan_rounds=0))
    assert out["structured_prompt"] == "¿Cuál es el enlace de la hoja Ventas?"
    assert out["req_pending_questions"] == ["¿Qué rango leo?"]  # una por campo faltante, una por turno
    assert out["req_plan_rounds"] == 1 and out["req_level_entered"] == 1
    assert "req_level" not in out  # se queda reuniendo: no pasa a CONFIRM con datos faltantes


async def test_question_wording_falls_back_when_the_model_returns_the_wrong_count(monkeypatch):
    _patch(monkeypatch, plan_llm=_Llm(_plan(
        {"order": 1, "function_id": "google_sheets.values.get", "args": {"range": "Ventas!A:B"}, "description": "Leer ventas"})),
        llm=_Llm('["una", "dos", "tres"]'))
    out = await rn._gather(_state(req_preflight_passed=True))
    assert "Leer ventas" in out["structured_prompt"]  # plantilla de respaldo, no el arreglo roto


async def test_after_answers_the_plan_is_rebuilt_and_goes_to_confirm(monkeypatch):
    plan_llm = _Llm(_plan(
        {"order": 1, "function_id": "google_sheets.values.get", "args": {"spreadsheet_id": "S1", "range": "Ventas!A:B"}, "description": "Leer ventas"}))
    _patch(monkeypatch, plan_llm=plan_llm)
    seen = {}

    async def present(state, plan, schedule):
        seen["plan"], seen["schedule"] = plan, schedule
        return {"req_level": 4, "structured_prompt": "mensaje de confirmacion"}

    monkeypatch.setattr(rn, "_present", present)
    msgs = [HumanMessage("cada lunes a las 9 lee la hoja Ventas y mandame el total por Gmail")]
    out = await rn._gather(_state(req_preflight_passed=True, req_level_entered=1, req_plan_rounds=1, messages=msgs))
    assert seen["plan"]["steps"][0]["args"] == {"spreadsheet_id": "S1", "range": "Ventas!A:B"} and "missing" not in seen["plan"]
    assert seen["schedule"]["cron"] == "0 9 * * 1"  # "cada lunes" del plan + "a las 9" del pedido original
    assert out["req_level"] == 4 and out["structured_prompt"] == "mensaje de confirmacion"


async def test_after_two_rounds_it_stops_asking_and_reports_what_was_left_out(monkeypatch):
    _patch(monkeypatch, plan_llm=_Llm(_plan(
        {"order": 1, "function_id": "google_sheets.values.get", "args": {}, "description": "Leer ventas"})),
        llm=_Llm("Resumen"))
    out = await rn._gather(_state(req_preflight_passed=True, req_level_entered=1, req_plan_rounds=2))
    assert "No pude armar un plan" in out["structured_prompt"] and "Leer ventas" in out["structured_prompt"]
    assert out["req_plan"] is None  # sin pasos no se guarda ni se confirma nada


def test_summary_view_never_shows_function_ids_or_raw_templates():
    view = rn._plan_view({"goal": "g", "steps": [
        {"order": 2, "app": "gmail", "function_id": "gmail.messages.send", "description": "Enviar correo",
         "args": {"body": "Total: {{step_1.total}}", "to": "a@b.com"}}], "notes": ["No pude armar X"]})
    text = json.dumps(view, ensure_ascii=False)
    assert "gmail.messages.send" not in text and "{{" not in text and "paso 1" in text and "No pude armar X" in text


# ── CONFIRM: lo que se guarda ────────────────────────────────────────────────

async def test_pretest_persists_function_id_config_and_single_account(monkeypatch):
    saved, run = [], {}

    async def create_workflow(**kw):
        return "wf1"

    async def add_step(wid, step, db):
        saved.append(step)
        return True

    async def single(db, uid, app):
        return {"google_sheets": "acc-1", "gmail": None}[app]  # gmail tiene varias cuentas

    class Exec:
        def __init__(self, fake_run, db, dry_run=False):
            run.update(fake_run)

        async def execute_dry_run(self):
            return {"trace": []}

    monkeypatch.setattr(rn, "mongo_manager", SimpleNamespace(db=object()))
    monkeypatch.setattr(rn, "create_workflow", create_workflow)
    monkeypatch.setattr(rn, "add_step_to_workflow", add_step)
    monkeypatch.setattr(rn, "single_account_id", single)
    monkeypatch.setattr(rn, "WorkflowExecutor", Exec)
    plan = {"goal": "Total semanal", "steps": [
        {"order": 1, "function_id": "google_sheets.values.get", "function_version": 1, "app": "google_sheets",
         "args": {"spreadsheet_id": "S1", "range": "Ventas!A:B"}, "description": "Leer ventas", "node_type": "ia"},
        {"order": 2, "function_id": "gmail.messages.send", "function_version": 1, "app": "gmail",
         "args": {"to": "a@b.com", "subject": "Total", "body": "{{step_1.total}}"}, "description": "Enviar el total", "node_type": "notificacion"},
        {"order": 3, "app": "slack", "action": "send_message", "description": "Avisar", "node_type": "raro"}]}
    out = await rn._persist_and_simulate({"user_id": "u1", "req_plan": plan, "conversation_id": "c1"})
    a, b, legacy = saved
    assert a["function_id"] == "google_sheets.values.get" and a["account_id"] == "acc-1" and a["function_version"] == 1
    assert {k: v for k, v in a["config"].items() if k != "nodeType"} == {"spreadsheet_id": "S1", "range": "Ventas!A:B"}
    assert a["metadata"] == {"nodeType": "ia"} and a["app"] == "google_sheets" and a["name"] == "Leer ventas"
    assert b["account_id"] is None and b["config"]["body"] == "{{step_1.total}}" and b["metadata"]["nodeType"] == "notificacion"
    assert "function_id" not in legacy and legacy["config"] == {"nodeType": "ia"} and legacy["account_id"] == ""  # paso viejo igual que antes
    assert [s["function_id"] for s in run["steps"] if "function_id" in s] == ["google_sheets.values.get", "gmail.messages.send"]
    assert out["req_workflow_id"] == "wf1" and len(out["req_deployed_steps"]) == 3


def test_dry_run_summary_shows_errors_instead_of_ok():
    text = rn._format_dry_run_summary({"trace": [
        {"order": 1, "type": "action", "name": "Borrar", "function_id": "x.y.z", "error": "necesita confirmacion"},
        {"order": 2, "type": "action", "name": "Leer", "function_id": "a.b.c", "mock_result": "{\"big\": \"json\"}"}]})
    assert "no se pudo simular (necesita confirmacion)" in text and "simulado OK con datos de ejemplo" in text
    assert "big" not in text


def test_invalid_value_in_an_optional_arg_is_dropped_not_asked():
    from typing import Literal, Optional

    class SearchIn(BaseModel):
        name_contains: str
        file_type: Optional[Literal["folder", "pdf"]] = None

    fn = _fn("google_drive.files.search", SearchIn)
    plan = rn._check_plan({"steps": [{"order": 1, "function_id": fn.spec.id, "description": "Buscar",
                                      "args": {"name_contains": "contrato", "file_type": "*"}}]}, {fn.spec.id: fn})
    assert plan["missing"] == [] and plan["steps"][0]["args"] == {"name_contains": "contrato"}
    # en un campo obligatorio el valor invalido SI se pregunta
    plan = rn._check_plan({"steps": [{"order": 1, "function_id": fn.spec.id, "description": "Buscar", "args": {"name_contains": 5}}]},
                          {fn.spec.id: fn})
    assert [(m["field"], m["kind"]) for m in plan["missing"]] == [("name_contains", "invalid")]


def test_trigger_template_without_a_webhook_counts_as_missing():
    step = {"order": 1, "function_id": GET.spec.id, "description": "Leer", "args": {"spreadsheet_id": "{{trigger.spreadsheet_id}}", "range": "Ventas!A:B"}}
    plan = rn._check_plan({"trigger_type": "schedule", "steps": [dict(step)]}, OFFERED)
    assert [m["field"] for m in plan["missing"]] == ["spreadsheet_id"]
    assert rn._check_plan({"trigger_type": "webhook", "steps": [dict(step)]}, OFFERED)["missing"] == []


def test_email_trigger_allows_only_the_fields_an_email_has():
    def plan(value):
        return rn._check_plan({"trigger_type": "email", "steps": [{"order": 1, "function_id": SEND.spec.id, "description": "Avisar",
                               "args": {"to": "a@b.com", "subject": value, "body": "x"}}]}, OFFERED)
    assert plan("Llego: {{trigger.subject}} de {{ trigger.sender }}")["missing"] == []
    assert [m["field"] for m in plan("Total {{trigger.total}}")["missing"]] == ["subject"]  # campo que un correo no trae


def test_when_fact_for_an_email_trigger_says_it_is_not_instant():
    when = rn._when_fact({"trigger_type": "email", "trigger_filter": "from:ana@x.com"}, None, None)
    assert when["kind"] == "email" and when["emails_that_start_it"] == "from:ana@x.com" and "every few minutes" in when["note"]
    assert "de ana@x.com" in rn._when_es(when) and "from:" not in rn._when_es(when)


def test_gmail_filter_is_said_in_plain_words():
    assert rn._filter_es('from:ana@x.com subject:"factura mayo" has:attachment') == "de ana@x.com, con asunto «factura mayo», con archivo adjunto"
    assert rn._filter_es("urgente newer_than:2d") == "que mencione «urgente», newer_than:2d"  # operador desconocido: tal cual
    assert rn._filter_es("") == ""


async def test_app_named_without_functions_is_noted_even_if_the_model_wrote_no_step_for_it(monkeypatch):
    _patch(monkeypatch, no_functions=["slack"], plan_llm=_Llm(_plan(
        {"order": 1, "function_id": "google_sheets.values.get", "args": {"spreadsheet_id": "S1", "range": "Ventas!A:B"}, "description": "Leer"})))
    plan = await rn._build_plan(_state())
    assert len(plan["steps"]) == 1 and "Slack todavía no está disponible" in plan["notes"][0]


def test_template_with_an_unknown_root_counts_as_missing():
    step = {"order": 1, "function_id": GET.spec.id, "description": "Leer", "args": {"spreadsheet_id": "{{spreadsheet_id}}", "range": "Ventas!A:B"}}
    assert [m["field"] for m in rn._check_plan({"steps": [step]}, OFFERED)["missing"]] == ["spreadsheet_id"]
