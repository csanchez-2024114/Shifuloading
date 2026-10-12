"""Crear workflow por chat en dos etapas (GATHER -> CONFIRM -> activar), de punta a punta con LLM simulado ($0).

Mongo es mongomock (el borrador, el workflow activo y la tarea programada son reales); lo unico simulado es el LLM, la
validacion de apps, el simulador y la cuenta unica. Cada prueba recorre req_investigator_node turno a turno como lo haria
el grafo: el estado de un turno es el del anterior mas lo que el nodo devolvio.
"""
import json
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from bson import ObjectId
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from mongomock_motor import AsyncMongoMockClient
from pydantic import BaseModel

os.environ.setdefault("OPENAI_API_KEY", "sk-fake")

from app.agent.shared.nodes import responder, response_evaluator as ev  # noqa: E402
from app.agent.shifu_base_v1.graph import req_nodes as rn  # noqa: E402
from app.agent.shifu_base_v1.graph.state import REQ_CONFIRM, REQ_FLOW_RESET  # noqa: E402

USER = str(ObjectId())
TZ = "America/Mexico_City"
T1 = ("quiero un workflow: cada lunes a las 9 lee la hoja https://docs.google.com/spreadsheets/d/abc123/edit rango "
      "Ventas!A:B y mandame el total por Gmail a yo@ejemplo.com")


class SheetIn(BaseModel):
    spreadsheet_id: str
    range: str


class SheetOut(BaseModel):
    total: float = 0


class SendIn(BaseModel):
    to: str
    subject: str
    body: str


class Anything(BaseModel):
    ok: bool = True


def _fn(fid, model, out=Anything, verb="read"):
    spec = SimpleNamespace(
        id=fid, app=fid.split(".")[0] if not fid.startswith("google_") else "google_sheets", version=1,
        verb=SimpleNamespace(value=verb), confirmation_policy=SimpleNamespace(value="assume"),
        description="Does something useful with the app. It needs the inputs listed.",
        input_schema=model.model_json_schema(), output_schema=out.model_json_schema())
    return SimpleNamespace(spec=spec, input_model=model)


OFFERED = {f.spec.id: f for f in (_fn("google_sheets.values.get", SheetIn, SheetOut),
                                  _fn("gmail.messages.send", SendIn, verb="create"))}


def plan_json(event="cada lunes a las 9", get_args=None, ttype="schedule"):
    get_args = {"spreadsheet_id": "abc123", "range": "Ventas!A:B"} if get_args is None else get_args
    return json.dumps({
        "goal": "Total semanal de ventas", "apps_needed": ["google_sheets", "gmail"], "trigger_type": ttype,
        "trigger_event": event,
        "steps": [
            {"order": 1, "function_id": "google_sheets.values.get", "args": get_args,
             "description": "Leer la hoja Ventas", "node_type": "ia"},
            {"order": 2, "function_id": "gmail.messages.send", "node_type": "notificacion",
             "args": {"to": "yo@ejemplo.com", "subject": "Total semanal", "body": "Total: {{step_1.total}}"},
             "description": "Enviar el total por correo"}]})


class MiniLlm:
    """Sustituye a req_nodes._llm: contesta segun el prompt de sistema (mensaje de CONFIRM, clasificador, preguntas)."""
    def __init__(self):
        self.decisions: list = []   # respuestas del clasificador de confirmacion (una por llamada; una excepcion = falla)
        self.confirm: str | None = None   # None = el redactor falla y se usa el mensaje de respaldo
        self.questions = "[]"
        self.calls: list = []

    async def ainvoke(self, msgs, **kw):
        system, human = msgs[0].content, msgs[1].content
        self.calls.append((system[:40], human))
        if system.startswith("You write the confirmation"):
            if self.confirm is None:
                raise RuntimeError("sin red")
            return AIMessage(self.confirm)
        if system.startswith("The assistant showed the user"):
            d = self.decisions.pop(0)
            if isinstance(d, Exception):
                raise d
            return AIMessage(json.dumps({"decision": d}))
        if "missing or wrong" in system:
            return AIMessage(self.questions)
        raise AssertionError(f"llamada inesperada al LLM: {system[:60]}")

    def human(self, prefix):
        return [h for s, h in self.calls if s.startswith(prefix)]


class PlanLlm:
    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    async def ainvoke(self, msgs, **kw):
        self.calls.append(msgs[1].content)
        return AIMessage(self.answers.pop(0) if len(self.answers) > 1 else self.answers[0])


class FakeExec:
    def __init__(self, run, db, dry_run=False):
        self.run = run

    async def execute_dry_run(self):
        return {"trace": [{"order": s["order"], "type": "action", "name": s["name"], "function_id": s.get("function_id"),
                           "mock_result": "{}"} for s in self.run["steps"]]}


@pytest.fixture
def env(monkeypatch):
    db = AsyncMongoMockClient()["req_confirm_flow"]
    e = SimpleNamespace(db=db, llm=MiniLlm(), plan=PlanLlm(plan_json()), failures=[])
    reports = [{"source": "auth", "app": a, "status": "ok", "account": {"email": "a@b.c"}} for a in ("google_sheets", "gmail")]

    async def candidates(state, query):
        return dict(OFFERED), []

    async def single(db_, uid, app):
        return {"google_sheets": "acc-1"}.get(app)  # gmail tiene varias cuentas

    monkeypatch.setattr(rn, "mongo_manager", SimpleNamespace(db=db))
    monkeypatch.setattr(rn, "_llm", e.llm)
    monkeypatch.setattr(rn, "_plan_llm", e.plan)
    monkeypatch.setattr(rn, "_plan_candidates", candidates)
    monkeypatch.setattr(rn, "single_account_id", single)
    monkeypatch.setattr(rn, "WorkflowExecutor", FakeExec)
    monkeypatch.setattr(rn, "_extract_apps_scope", AsyncMock(return_value=["google_sheets", "gmail"]))
    monkeypatch.setattr(rn, "_catalog_auth_failures", AsyncMock(side_effect=lambda apps, uid: list(e.failures)))
    monkeypatch.setattr(rn, "_app_reports", AsyncMock(return_value=reports))
    return e


def start(text=T1, **kw):
    # lo que deja semantic_intake al detectar la intencion create_workflow
    return {**REQ_FLOW_RESET, "req_level": 1, "user_id": USER, "user_email": "a@b.test", "conversation_id": "c1",
            "user_timezone": TZ, "messages": [HumanMessage(text)], **kw}


async def turn(state, user_text=None):
    """Un turno del flujo: (estado siguiente, lo que devolvio el nodo)."""
    if user_text:
        state = {**state, "messages": [*state["messages"], HumanMessage(user_text)]}
    out = await rn.req_investigator_node(state)
    state = {**state, **out}
    if out.get("structured_prompt"):
        state["messages"] = [*state["messages"], AIMessage(out["structured_prompt"])]
    return state, out


async def workflows(env):
    return await env.db["workflows"].find({}).to_list(length=10)


# ── T1: pedido completo -> CONFIRM en el mismo turno ──────────────────────────

async def test_t1_complete_request_confirms_in_the_same_turn_with_plan_schedule_and_question(env):
    state, out = await turn(start())
    assert out["req_level"] == REQ_CONFIRM and out["req_relay"] is True
    msg = out["structured_prompt"]  # redactor caido: mensaje de respaldo, que ya debe traer todo
    assert "Leer la hoja Ventas" in msg and "Enviar el total por correo" in msg  # el plan, paso a paso
    assert "Ventas!A:B" in msg and "yo@ejemplo.com" in msg                       # con sus valores clave
    assert "Simulé" in msg                                                        # lo que mostro la simulacion
    assert "cada lunes a las 9:00" in msg and TZ in msg                           # cuando correra, en espanol y con zona
    assert msg.rstrip().endswith("¿Lo activo así?")
    assert "google_sheets.values.get" not in msg and "{{" not in msg              # nunca ids ni plantillas crudas
    # el borrador queda guardado con pasos reales, y todavia no se activa ni se programa nada
    (wf,) = await workflows(env)
    assert wf["status"] == "creating" and str(wf["_id"]) == out["req_workflow_id"]
    a, b = wf["steps"]
    assert a["function_id"] == "google_sheets.values.get" and a["account_id"] == "acc-1"
    assert a["config"]["spreadsheet_id"] == "abc123" and b["function_id"] == "gmail.messages.send" and b["account_id"] is None
    assert b["config"]["body"] == "Total: {{step_1.total}}"
    assert await env.db["scheduled_tasks"].count_documents({}) == 0
    assert out["req_schedule"]["cron"] == "0 9 * * 1" and "google_sheets" in out["user_connected_apps"]


async def test_confirm_writer_gets_only_facts_and_the_reply_always_ends_with_the_question(env):
    env.llm.confirm = "Armé tu workflow: lees la hoja y mandas el total."
    _, out = await turn(start())
    facts = json.loads(env.llm.human("You write the confirmation")[0])
    text = json.dumps(facts, ensure_ascii=False)
    assert "Ventas!A:B" in text and "cada lunes a las 9:00" in text and TZ in text
    assert "google_sheets.values.get" not in text and "{{" not in text  # el redactor tampoco ve ids ni plantillas
    assert out["structured_prompt"].endswith("¿Lo activo así?")  # si el redactor olvida la pregunta, el codigo la pone


# ── T2: "si, activalo" -> activo y programado ─────────────────────────────────

async def test_t2_yes_activates_and_schedules_in_the_user_timezone(env):
    state, _ = await turn(start())
    env.llm.decisions = ["confirm"]
    state, out = await turn(state, "si, actívalo")
    (wf,) = await workflows(env)
    assert wf["status"] == "active"
    task = await env.db["scheduled_tasks"].find_one({})
    assert task["workflow_id"] == str(wf["_id"]) and task["schedule_type"] == "cron"
    assert task["schedule_config"] == {"cron_expression": "0 9 * * 1", "timezone": TZ}
    assert task["next_run_at"].hour == 15  # 9:00 de Mexico = 15:00 UTC
    assert out["req_level"] is None and out["req_deployed"] is True and out["req_relay"] is True
    assert "cada lunes a las 9:00" in out["structured_prompt"] and "activo" in out["structured_prompt"]
    assert len(out["req_deployed_steps"]) == 2  # la UI pinta la tarjeta del workflow


async def test_plain_yes_needs_no_classifier_call(env):
    state, _ = await turn(start())
    state, out = await turn(state, "sí")
    assert out["req_deployed"] is True and not env.llm.human("The assistant showed")


# ── datos faltantes: una pregunta por turno, sin guardar nada ─────────────────

async def test_missing_data_asks_one_question_per_turn_then_confirms(env):
    env.plan.answers = [plan_json(get_args={}), plan_json()]
    env.llm.questions = json.dumps(["¿Cuál es el enlace de la hoja?", "¿Qué rango leo?"])
    state, out = await turn(start("cada lunes a las 9 lee mi hoja de ventas y mandame el total a yo@ejemplo.com por Gmail"))
    assert out["structured_prompt"] == "¿Cuál es el enlace de la hoja?" and "req_level" not in out
    assert await workflows(env) == []  # con datos faltantes no hay borrador
    state, out = await turn(state, "https://docs.google.com/spreadsheets/d/abc123/edit")  # el usuario contesta; sigue la cola
    assert out["structured_prompt"] == "¿Qué rango leo?" and await workflows(env) == []
    state, out = await turn(state, "Ventas!A:B")  # cola vacia: se rearma el plan con todo y se confirma
    assert out["req_level"] == REQ_CONFIRM and out["structured_prompt"].endswith("¿Lo activo así?")
    assert len(await workflows(env)) == 1
    assert "PREVIOUS PLAN" in env.plan.calls[1]  # al rearmar conserva lo que ya sabia


# ── cambio: "cambia la hora a las 10" -> plan y horario nuevos ────────────────

async def test_change_at_confirm_rebuilds_the_plan_and_the_schedule(env):
    state, first = await turn(start())
    env.plan.answers = [plan_json(event="cada lunes a las 10")]
    env.llm.decisions = ["change"]
    state, out = await turn(state, "cambia la hora a las 10")
    assert out["req_level"] == REQ_CONFIRM and "10:00" in out["structured_prompt"]
    assert out["req_schedule"]["cron"] == "0 10 * * 1"
    assert "The user wants this adjustment" in env.plan.calls[-1] and "cambia la hora a las 10" in env.plan.calls[-1]
    assert "PREVIOUS PLAN" in env.plan.calls[-1] and "abc123" in env.plan.calls[-1]  # no re-pregunta lo que ya tenia
    (wf,) = await workflows(env)  # el borrador viejo se descartó: queda uno solo
    assert str(wf["_id"]) == out["req_workflow_id"] and out["req_workflow_id"] != first["req_workflow_id"]
    env.llm.decisions = ["confirm"]
    _, done = await turn(state, "dale")
    task = await env.db["scheduled_tasks"].find_one({})
    assert task["schedule_config"]["cron_expression"] == "0 10 * * 1" and "10:00" in done["structured_prompt"]


# ── cancelar ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("reply", ["no", "no, mejor no"])
async def test_cancel_discards_the_draft_and_schedules_nothing(env, reply):
    state, _ = await turn(start())
    state, out = await turn(state, reply)
    assert await workflows(env) == [] and await env.db["scheduled_tasks"].count_documents({}) == 0
    assert out["req_level"] is None and "no activé nada" in out["structured_prompt"]
    assert out["req_workflow_id"] is None and out["req_plan"] is None  # el siguiente flujo no hereda nada


async def test_cancel_never_touches_an_already_active_workflow(env):
    active = await env.db["workflows"].insert_one({"user_id": USER, "status": "active", "steps": []})
    await rn._discard_draft(USER, str(active.inserted_id))
    assert await env.db["workflows"].count_documents({"status": "active"}) == 1


# ── clasificador caido: nunca se activa por defecto ───────────────────────────

async def test_classifier_failure_is_not_a_confirmation_and_asks_once_more(env):
    state, _ = await turn(start())
    env.llm.decisions = [RuntimeError("sin red"), RuntimeError("sin red")]
    state, out = await turn(state, "bueno pues como veas mejor")
    assert "req_level" not in out  # sigue en CONFIRM
    assert "¿Lo activo así" in out["structured_prompt"] and out["req_confirm_unclear"] == 1
    (wf,) = await workflows(env)
    assert wf["status"] == "creating" and await env.db["scheduled_tasks"].count_documents({}) == 0
    state, out = await turn(state, "mmm no sé")  # segunda vez sin entender: tampoco se activa, y no se atrapa al usuario
    assert out["req_level"] is None and "no activé nada" in out["structured_prompt"]
    assert await workflows(env) == [] and await env.db["scheduled_tasks"].count_documents({}) == 0


# ── app sin conectar ──────────────────────────────────────────────────────────

async def test_not_connected_app_asks_to_connect_and_persists_nothing(env):
    env.failures = ["No tienes conectada una cuenta de 'gmail' (el botón para conectarla está en pantalla)."]
    state, out = await turn(start())
    assert "gmail" in out["structured_prompt"] and out["req_preflight_passed"] is False
    assert out["req_compose"] is True and out["req_relay"] is False  # hechos: el responder arma la respuesta con ellos
    assert out["validation_reports"] and "req_level" not in out  # los reportes alimentan los botones de conectar
    assert await workflows(env) == [] and not env.plan.calls  # ni borrador ni plan hasta que conecte
    env.failures = []  # lo conecto
    state, out = await turn(state, "ya conecté Gmail")
    assert out["req_level"] == REQ_CONFIRM and len(await workflows(env)) == 1


async def test_asking_to_connect_a_read_only_app_says_it_can_only_read(env, monkeypatch):
    monkeypatch.setattr(rn, "_extract_apps_scope", AsyncMock(return_value=["instagram", "gmail"]))
    monkeypatch.setattr(rn, "app_has_actions", lambda a: True)
    monkeypatch.setattr(rn, "app_capability", lambda a: "read" if a == "instagram" else "write")
    env.failures = ["No tienes conectada una cuenta de 'instagram' (el botón para conectarla está en pantalla)."]
    _, out = await turn(start("publica mis fotos en instagram cada lunes"))
    msg = out["structured_prompt"]
    assert "con Instagram por ahora solo puedo leer" in msg and "con Gmail" not in msg


# ── horario sin hora ──────────────────────────────────────────────────────────

async def test_schedule_without_an_hour_is_asked_once_and_the_answer_is_used(env):
    env.plan.answers = [plan_json(event="cada lunes")]
    state, out = await turn(start("cada lunes lee mi hoja Ventas y mandame el total a yo@ejemplo.com por Gmail"))
    assert "qué día y a qué hora" in out["structured_prompt"].lower() and await workflows(env) == []
    state, out = await turn(state, "a las 18")
    assert out["req_level"] == REQ_CONFIRM and out["req_schedule"]["cron"] == "0 18 * * 1"
    assert "18:00" in out["structured_prompt"]


async def test_webhook_flow_confirms_without_a_schedule_and_activates_with_a_url(env):
    env.plan.answers = [plan_json(event="cuando llegue un POST", ttype="webhook")]
    state, out = await turn(start("cuando llegue un POST lee la hoja Ventas y mandame el total a yo@ejemplo.com"))
    assert "webhook" in out["structured_prompt"] and out["req_schedule"] is None
    state, done = await turn(state, "sí")
    assert "/api/v1/webhooks/" in done["structured_prompt"] and await env.db["scheduled_tasks"].count_documents({}) == 0


# ── responder: entrega el mensaje del flujo tal cual ──────────────────────────

@pytest.fixture
def sent_to_llm(monkeypatch):
    platform = AsyncMock(return_value="PLATFORM KNOWLEDGE: slack has no actions")
    monkeypatch.setattr(responder, "get_agent_identity", AsyncMock(return_value={}))
    monkeypatch.setattr(responder, "get_agent_personality", AsyncMock(return_value={}))
    monkeypatch.setattr(responder, "build_system_messages", MagicMock(return_value=[SystemMessage("You are Shifu.")]))
    monkeypatch.setattr(responder, "build_platform_context", platform)
    llm = AsyncMock(return_value=AIMessage("ok"))
    monkeypatch.setattr(responder.ChatOpenAI, "ainvoke", llm)

    async def run(state):
        await responder.responder_node({"apps_involved": [], "effort_level": "low", "model_name": "gpt-4o-mini",
                                        "messages": [HumanMessage("sí")], **state})
        return "\n---\n".join(str(m.content) for m in llm.await_args.args[0])
    run.platform = platform
    return run


async def test_relay_turn_delivers_the_flow_message_verbatim_without_the_llm(monkeypatch):
    # Aun con la orden de "transmitir fiel" el modelo quitaba el horario y la pregunta e inventaba requisitos (v065_wf):
    # el mensaje del flujo se entrega tal cual, sin llamar al modelo.
    llm = AsyncMock(return_value=AIMessage("reescrito"))
    monkeypatch.setattr(responder.ChatOpenAI, "ainvoke", llm)
    monkeypatch.setattr(responder, "get_agent_identity", AsyncMock(return_value={}))
    monkeypatch.setattr(responder, "get_agent_personality", AsyncMock(return_value={}))
    monkeypatch.setattr(responder, "build_system_messages", MagicMock(return_value=[SystemMessage("You are Shifu.")]))
    for level in (4, None):  # None: activacion / cancelacion, el flujo ya termino pero el mensaje es suyo
        out = await responder.responder_node({"apps_involved": [], "effort_level": "low", "model_name": "gpt-4o-mini",
                                              "messages": [HumanMessage("sí")], "req_relay": True, "req_level": level,
                                              "structured_prompt": "Plan: leer la hoja. ¿Lo activo así?"})
        assert out["messages"][-1].content == "Plan: leer la hoja. ¿Lo activo así?"
    llm.assert_not_awaited()


async def test_judge_does_not_rewrite_a_relayed_flow_message():
    out = await ev.response_evaluator_node({"req_relay": True, "messages": [HumanMessage("sí"), AIMessage("Plan… ¿Lo activo así?")]})
    assert out["eval_feedback"] is None and out["eval_report"]["action"] == "skipped"


async def test_a_digression_inside_the_flow_is_answered_normally(sent_to_llm):
    sent = await sent_to_llm({"structured_prompt": "otra cosa", "req_relay": True, "req_level": 4, "req_flow_action": "digress"})
    assert "FLOW MESSAGE" not in sent and "about something else" in sent


async def test_flow_messages_are_delivered_in_the_users_language_only_if_no_fact_is_lost(monkeypatch):
    original = "Plan: leer A1:B y enviar el total a yo@ejemplo.com cada lunes a las 9:00. ¿Lo activo así?"
    llm = AsyncMock(return_value=AIMessage("Plan: read A1:B and send the total to yo@ejemplo.com every Monday at 9:00. Activate it?"))
    monkeypatch.setattr(rn, "_llm", SimpleNamespace(ainvoke=llm))
    assert (await rn._in_user_language({"user_language": "English"}, original)).startswith("Plan: read A1:B")
    assert await rn._in_user_language({"user_language": "Spanish"}, original) == original   # ya esta en su idioma
    assert await rn._in_user_language({}, original) == original                              # idioma desconocido
    assert llm.await_count == 1
    for broken in ("Plan: read A1:B and send the total every Monday at 9:00. Activate it?",          # perdio el correo
                   "Plan: read A1:B and send the total to yo@ejemplo.com every Monday at 10:00. Activate it?",  # cambio la hora
                   "Plan: read A1:B and send the total to yo@ejemplo.com every Monday at 9:00."):     # perdio la pregunta
        llm.return_value = AIMessage(broken)
        assert await rn._in_user_language({"user_language": "English"}, original) == original
    llm.side_effect = RuntimeError("caido")
    assert await rn._in_user_language({"user_language": "English"}, original) == original


async def test_connect_facts_go_to_the_model_so_one_reply_also_answers_the_user(sent_to_llm):
    sent = await sent_to_llm({"structured_prompt": "No tienes conectada una cuenta de 'gmail'", "req_compose": True, "req_level": 1})
    assert "FACTS FOR THIS TURN" in sent and "No tienes conectada una cuenta de 'gmail'" in sent
    assert "answers whatever the user" in sent and "Clarified user intent" not in sent
    block = ev._intent_block({"structured_prompt": "No tienes conectada una cuenta de 'gmail'", "req_compose": True})
    assert block.startswith("USER INTENT") and "NOT inventions" in block


async def test_remembered_preferences_go_last_in_the_prompt_as_a_standing_instruction(sent_to_llm):
    facts = [{"key": "language", "value": "English only"}, {"key": "tools", "value": "Gmail"}]
    sent = await sent_to_llm({"structured_prompt": "x", "raw_memories": {"semantic": facts}})
    last = sent.split("\n---\n")[-1]
    assert last.startswith("STANDING PREFERENCES") and "- language: English only" in last and "tools" not in last
    assert "STANDING PREFERENCES" not in await sent_to_llm({"structured_prompt": "x", "raw_memories": {"semantic": facts[1:]}})


async def test_without_relay_the_normal_prompt_is_unchanged(sent_to_llm):
    sent = await sent_to_llm({"structured_prompt": "send an email", "req_relay": False})
    assert "FLOW MESSAGE" not in sent and "Clarified user intent" in sent and "ANTI-LOOPING" in sent


# ── juez: el mensaje del flujo es evidencia ───────────────────────────────────

def test_judge_sees_the_flow_message_as_verified_evidence():
    block = ev._intent_block({"structured_prompt": "Va a correr cada lunes a las 9:00", "req_relay": True})
    assert block.startswith("USER INTENT") and "Va a correr cada lunes a las 9:00" in block
    assert "NOT inventions" in block and "IS a failure" in block
    assert ev._intent_block({"structured_prompt": "x", "req_relay": False}) == "USER INTENT (normalized): x"
