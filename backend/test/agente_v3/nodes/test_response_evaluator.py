"""response_evaluator: centinela de calidad. Evalua siempre, juzga contra mandatos y persona, y deja un informe."""
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.agent.shared.nodes import response_evaluator as ev

_NAMES = ["answers_request", "follows_instructions", "persona", "no_fabrication", "grounded_in_platform", "format"]


def _verdict(*failed, feedback=""):
    return ev._Eval(checks=[ev._Check(name=n, passed=n not in failed, note=f"nota {n}") for n in _NAMES], feedback=feedback)


def _state(**over):
    base = {"messages": [HumanMessage("dame los pasos en viñetas"), AIMessage("respuesta")], "eval_retry_count": 0}
    return {**base, **over}


@pytest.fixture
def judge(monkeypatch):
    monkeypatch.setattr(ev, "get_agent_personality", AsyncMock(return_value={
        "voice": {"avoid": ["frases hechas"]},
        "quality_control": {"max_retries": 4, "checks": [{"name": n, "criterion": f"criterio {n}"} for n in _NAMES]},
    }))
    monkeypatch.setattr(ev, "build_platform_context", AsyncMock(return_value="## PLATFORM KNOWLEDGE - asana.tasks.create"))
    monkeypatch.setattr(ev, "get_agent_identity", AsyncMock(return_value={"principles": ["Nunca aceptes credenciales por chat"]}))

    def use(result):
        llm = AsyncMock()
        llm.ainvoke = AsyncMock(side_effect=result if isinstance(result, Exception) else None, return_value=result)
        monkeypatch.setattr(ev, "_llm", llm)
        return llm

    return use


async def test_evaluates_pure_chat_turns(judge):
    # antes un turno sin apps ni investigacion se saltaba el evaluador; ahora siempre se juzga
    llm = judge(_verdict())
    out = await ev.response_evaluator_node(_state(apps_involved=[]))
    llm.ainvoke.assert_awaited_once()
    assert out["eval_feedback"] is None
    assert out["eval_report"]["action"] == "approved" and out["eval_report"]["passed"] is True


async def test_failed_check_sends_responder_back_with_feedback(judge):
    judge(_verdict("persona", feedback="Reescribe sin frases hechas."))
    out = await ev.response_evaluator_node(_state())
    assert out["eval_feedback"] == "Reescribe sin frases hechas."
    assert out["eval_retry_count"] == 1
    assert out["eval_report"]["action"] == "retry"
    assert [c["name"] for c in out["eval_report"]["checks"] if not c["passed"]] == ["persona"]


async def test_delivers_with_failure_flagged_when_retries_exhausted(judge):
    judge(_verdict("answers_request", feedback="x"))
    out = await ev.response_evaluator_node(_state(eval_retry_count=4))
    assert out["eval_feedback"] is None  # el router sigue a memory_updater
    assert out["eval_report"]["action"] == "exhausted" and out["eval_report"]["passed"] is False
    assert "eval_retry_count" not in out


async def test_judge_receives_user_message_mandates_and_persona(judge):
    llm = judge(_verdict())
    await ev.response_evaluator_node(_state(active_mandates=["NOT CONNECTED: 'gmail'. Tell the user to click."]))
    sent = llm.ainvoke.await_args.args[0][1]["content"]
    assert "dame los pasos en viñetas" in sent
    assert "NOT CONNECTED: 'gmail'" in sent
    assert "frases hechas" in sent
    assert "Nunca aceptes credenciales por chat" in sent
    assert "asana.tasks.create" in sent  # y el conocimiento de la plataforma, para juzgar si la respuesta se apoya en el  # los principios de la identidad tambien llegan al juez


async def test_evaluator_failure_does_not_block_the_reply(judge):
    judge(RuntimeError("boom"))
    out = await ev.response_evaluator_node(_state())
    assert out["eval_feedback"] is None
    assert out["eval_report"]["action"] == "skipped" and "boom" in out["eval_report"]["reason"]


async def test_checks_and_margin_come_from_data_not_code(judge, monkeypatch):
    # Pivotar de dominio = cambiar el documento de personalidad: otros chequeos, otro margen, sin tocar codigo
    monkeypatch.setattr(ev, "get_agent_personality", AsyncMock(return_value={
        "quality_control": {"max_retries": 1, "checks": [{"name": "tono_legal", "criterion": "Usa lenguaje juridico formal"}]}}))
    llm = judge(ev._Eval(checks=[ev._Check(name="tono_legal", note="n", passed=False)], feedback="Formaliza."))
    monkeypatch.setattr(ev, "get_agent_personality", AsyncMock(return_value={
        "quality_control": {"max_retries": 1, "checks": [{"name": "tono_legal", "criterion": "Usa lenguaje juridico formal"}]}}))
    out = await ev.response_evaluator_node(_state(eval_retry_count=1))
    system = llm.ainvoke.await_args.args[0][0]["content"]
    assert "tono_legal" in system and "Usa lenguaje juridico formal" in system and "persona" not in system
    assert out["eval_report"]["action"] == "exhausted" and out["eval_report"]["max_attempts"] == 2


async def test_without_quality_control_in_the_document_it_uses_generic_defaults(judge, monkeypatch):
    monkeypatch.setattr(ev, "get_agent_personality", AsyncMock(return_value={}))
    judge(ev._Eval(checks=[ev._Check(name=c["name"], note="n", passed=True) for c in ev._DEFAULT_CHECKS], feedback=""))
    monkeypatch.setattr(ev, "get_agent_personality", AsyncMock(return_value={}))
    out = await ev.response_evaluator_node(_state())
    assert out["eval_report"]["action"] == "approved" and out["eval_report"]["max_attempts"] == ev._DEFAULT_MAX_RETRIES + 1


async def test_quality_control_can_be_switched_off_from_the_document(judge, monkeypatch):
    llm = judge(_verdict())
    monkeypatch.setattr(ev, "get_agent_personality", AsyncMock(return_value={"quality_control": {"enabled": False}}))
    out = await ev.response_evaluator_node(_state())
    llm.ainvoke.assert_not_awaited()
    assert out["eval_report"]["action"] == "skipped"


async def test_judge_cannot_invent_checks_that_are_not_configured(judge):
    judge(ev._Eval(checks=[ev._Check(name="inventado", note="n", passed=False)] + [ev._Check(name=n, note="n", passed=True) for n in _NAMES], feedback="x"))
    out = await ev.response_evaluator_node(_state())
    assert out["eval_report"]["action"] == "approved"


# ── Modo "per_check": un juez barato por chequeo, en paralelo ─────────────────────────────────────────────────────────

import re  # noqa: E402


class _FakeOne:
    """Juez de un solo chequeo: lee el nombre del chequeo del final del mensaje y falla los que se le pidan."""

    def __init__(self, failing=(), boom=(), minor=()):
        self.failing, self.boom, self.minor, self.calls, self.bodies = set(failing), set(boom), set(minor), [], []

    async def ainvoke(self, messages, config=None):
        self.tags = getattr(self, "tags", []) + [(config or {}).get("tags")]
        name = re.search(r"CHECK TO RUN: (\w+)", messages[-1]["content"]).group(1)
        self.calls.append(name)
        self.bodies.append(messages[-1]["content"])
        if name in self.boom:
            raise RuntimeError("red caida")
        severity = "major" if name in self.failing else "minor" if name in self.minor else "none"
        return ev._One(note=f"nota {name}", severity=severity, feedback=f"corrige {name}" if severity == "major" else "")


@pytest.fixture
def per_check(monkeypatch):
    monkeypatch.setattr(ev, "get_agent_personality", AsyncMock(return_value={
        "quality_control": {"max_retries": 4, "judge": {"model": "gpt-4o-mini", "mode": "per_check"},
                            "checks": [{"name": n, "criterion": f"criterio {n}"} for n in _NAMES]}}))
    monkeypatch.setattr(ev, "get_agent_identity", AsyncMock(return_value={}))
    monkeypatch.setattr(ev, "build_platform_context", AsyncMock(return_value=""))

    def use(fake):
        seen = []
        monkeypatch.setattr(ev, "_one_for", lambda model: (seen.append(model), fake)[1])
        return seen

    return use


async def test_per_check_runs_one_cheap_judge_per_check_and_approves_when_all_pass(per_check):
    fake = _FakeOne()
    models = per_check(fake)
    out = await ev.response_evaluator_node(_state())
    assert sorted(fake.calls) == sorted(_NAMES)                      # una llamada por chequeo
    assert set(models) == {"gpt-4o-mini"}                           # el modelo sale de los datos, y es el barato
    assert out["eval_report"]["action"] == "approved" and out["eval_report"]["judge"] == "gpt-4o-mini/per_check"
    assert len(out["eval_report"]["checks"]) == len(_NAMES)


async def test_per_check_failure_is_isolated_and_its_feedback_reaches_the_responder(per_check):
    per_check(_FakeOne(failing={"persona"}))
    out = await ev.response_evaluator_node(_state())
    assert out["eval_report"]["action"] == "retry" and out["eval_retry_count"] == 1
    assert out["eval_feedback"] == "persona: corrige persona"
    assert [c["name"] for c in out["eval_report"]["checks"] if not c["passed"]] == ["persona"]


async def test_per_check_a_judge_that_errors_is_skipped_not_counted_as_a_failure(per_check):
    per_check(_FakeOne(boom={"format"}))
    out = await ev.response_evaluator_node(_state())
    assert out["eval_report"]["action"] == "approved"
    assert "format" not in [c["name"] for c in out["eval_report"]["checks"]]


async def test_per_check_all_judges_failing_delivers_the_reply(per_check):
    per_check(_FakeOne(boom=set(_NAMES)))
    out = await ev.response_evaluator_node(_state())
    assert out["eval_feedback"] is None and out["eval_report"]["action"] == "skipped"


async def test_per_check_a_minor_flaw_is_recorded_but_does_not_force_a_rewrite(per_check):
    # lo que el usuario pidio: no perseguir el error pequeno; solo el grande reinicia la respuesta
    per_check(_FakeOne(minor={"persona", "format"}))
    out = await ev.response_evaluator_node(_state())
    assert out["eval_report"]["action"] == "approved" and out["eval_feedback"] is None
    minors = [c for c in out["eval_report"]["checks"] if c["severity"] == "minor"]
    assert {c["name"] for c in minors} == {"persona", "format"} and all(c["passed"] for c in minors)


async def test_per_check_a_major_flaw_still_forces_a_rewrite_even_with_minors_around(per_check):
    per_check(_FakeOne(failing={"no_fabrication"}, minor={"persona"}))
    out = await ev.response_evaluator_node(_state())
    assert out["eval_report"]["action"] == "retry" and out["eval_feedback"] == "no_fabrication: corrige no_fabrication"


async def test_the_judge_sees_the_conversation_so_recalling_earlier_turns_is_not_fabrication(per_check):
    fake = _FakeOne()
    per_check(fake)
    msgs = [HumanMessage("me llamo Ale y vendo velas artesanales"), AIMessage("Mucho gusto, Ale."),
            HumanMessage("que vendo?"), AIMessage("Vendes velas artesanales.")]
    await ev.response_evaluator_node(_state(messages=msgs))
    body = fake.bodies[0]
    assert "USER: me llamo Ale y vendo velas artesanales" in body            # el turno anterior llega al juez
    assert body.count("Vendes velas artesanales.") == 1                      # la respuesta evaluada va solo en su lugar


async def test_when_retries_run_out_the_draft_with_fewest_major_failures_is_delivered(per_check):
    # Paso de verdad: el intento honesto fue rechazado por un juez equivocado y al agotarse salio la ultima version (falsa)
    per_check(_FakeOne(failing={"persona"}))
    earlier = [{"attempt": 1, "content": "dos fallas", "majors": 2}, {"attempt": 2, "content": "la buena", "majors": 0},
               {"attempt": 3, "content": "una falla", "majors": 1}, {"attempt": 4, "content": "otra", "majors": 1}]
    out = await ev.response_evaluator_node(_state(eval_retry_count=4, eval_drafts=earlier,
                                                  messages=[HumanMessage("hola"), AIMessage("la ultima", id="m1")]))
    assert out["eval_report"]["action"] == "exhausted" and out["eval_report"]["delivered_attempt"] == 2
    [msg] = out["messages"]
    assert (msg.id, msg.content) == ("m1", "la buena")  # reemplaza el ultimo borrador, no agrega otro mensaje


async def test_on_a_tie_the_latest_draft_wins_and_nothing_is_replaced(per_check):
    per_check(_FakeOne(failing={"persona"}))
    earlier = [{"attempt": 1, "content": "a", "majors": 1}]
    out = await ev.response_evaluator_node(_state(eval_retry_count=4, eval_drafts=earlier))
    assert out["eval_report"]["delivered_attempt"] == 5 and "messages" not in out


def _qc(checks):
    return AsyncMock(return_value={"quality_control": {"max_retries": 4, "judge": {"model": "gpt-4o-mini", "mode": "per_check"},
                                                       "checks": checks}})


async def test_a_non_blocking_check_reports_but_never_forces_a_rewrite(per_check, monkeypatch):
    monkeypatch.setattr(ev, "get_agent_personality", _qc(
        [{"name": n, "criterion": f"criterio {n}", **({"blocking": False} if n == "persona" else {})} for n in _NAMES]))
    per_check(_FakeOne(failing={"persona"}))
    out = await ev.response_evaluator_node(_state())
    assert out["eval_report"]["action"] == "approved"
    [c] = [c for c in out["eval_report"]["checks"] if c["name"] == "persona"]
    assert c["severity"] == "minor" and "no bloquea" in c["note"]


class _FakeClaims:
    def __init__(self, claims):
        self.claims, self.system = claims, None

    async def ainvoke(self, messages, config=None):
        self.system = messages[0]["content"]
        return ev._Claims(claims=[ev._Claim(**c) for c in self.claims])


async def _claims_run(monkeypatch, claims, examples=None, platform="- Slack: coming soon, it cannot send anything"):
    monkeypatch.setattr(ev, "get_agent_personality", _qc([{"name": "no_fabrication", "criterion": "c", "method": "claims",
                                                          **({"examples": examples} if examples else {})}]))
    monkeypatch.setattr(ev, "get_agent_identity", AsyncMock(return_value={}))
    monkeypatch.setattr(ev, "build_platform_context", AsyncMock(return_value=platform))
    fake = _FakeClaims(claims)
    monkeypatch.setattr(ev, "_claims_cache", {"gpt-4o-mini": fake})
    return await ev.response_evaluator_node(_state()), fake


async def test_claims_a_contradiction_backed_by_a_real_context_line_forces_a_rewrite(monkeypatch):
    out, _ = await _claims_run(monkeypatch, [{"claim": "te aviso en Slack", "claim_says": "can", "verdict": "contradicted",
                                              "evidence": "Slack: coming soon, it cannot send anything", "evidence_says": "cannot"}])
    assert out["eval_report"]["action"] == "retry" and "te aviso en Slack" in out["eval_feedback"]


async def test_claims_a_contradiction_with_invented_evidence_does_not_block(monkeypatch):
    # El juez mini "veia" contradicciones que no estaban en el contexto
    out, _ = await _claims_run(monkeypatch, [{"claim": "registro el correo en Sheets", "claim_says": "can", "verdict": "contradicted",
                                              "evidence": "Sheets cannot be triggered by emails", "evidence_says": "cannot"}])
    assert out["eval_report"]["action"] == "approved"


async def test_claims_without_backing_are_only_reported_and_calibration_notes_reach_the_judge(monkeypatch):
    out, fake = await _claims_run(monkeypatch, [{"claim": "Trello sirve", "claim_says": "can", "verdict": "not_in_context",
                                                 "evidence": "", "evidence_says": "other"}],
                                  examples=["no exigir repetir limitaciones ya dichas"])
    assert out["eval_report"]["action"] == "approved"
    assert out["eval_report"]["checks"][0]["severity"] == "minor"
    assert "no exigir repetir limitaciones ya dichas" in fake.system


async def test_claims_an_honest_limitation_that_agrees_with_the_context_is_not_a_contradiction(monkeypatch):
    # "no puedo enviar a Slack" frente a "Slack no puede enviar nada": dicen lo mismo, aunque el juez lo marque
    out, _ = await _claims_run(monkeypatch, [{"claim": "no puedo enviar a Slack", "claim_says": "cannot", "verdict": "contradicted",
                                              "evidence": "Slack: coming soon, it cannot send anything", "evidence_says": "cannot"}])
    assert out["eval_report"]["action"] == "approved"


_REAL_SLACK = "- Slack: coming soon — the team is building it; nothing can be done with it for the user yet"


async def test_claims_a_step_on_an_unavailable_app_blocks_even_if_the_judge_missed_the_line(monkeypatch):
    # v0.3.0: "se guarda en Sheets y te aviso en Slack" llegaba como not_in_context y pasaba (2 de 5 veces)
    out, _ = await _claims_run(monkeypatch, [{"claim": "te enviare una notificacion a Slack", "app": "Slack", "claim_says": "can",
                                              "verdict": "not_in_context", "evidence": "", "evidence_says": "other"}],
                               platform=_REAL_SLACK)
    assert out["eval_report"]["action"] == "retry" and _REAL_SLACK in out["eval_feedback"]


async def test_claims_saying_an_unavailable_app_cannot_do_something_is_fine(monkeypatch):
    out, _ = await _claims_run(monkeypatch, [{"claim": "aun no puedo enviar mensajes a Slack", "app": "Slack", "claim_says": "cannot",
                                              "verdict": "supported", "evidence": "", "evidence_says": "other"}],
                               platform=_REAL_SLACK)
    assert out["eval_report"]["action"] == "approved"


async def test_claims_a_write_on_a_read_only_app_blocks(monkeypatch):
    # Exploracion 2026-10-10: Discord solo lee y el agente prometio "te aviso en Discord"
    monkeypatch.setattr(ev, "app_capability", lambda app: "read")
    out, _ = await _claims_run(monkeypatch, [{"claim": "te avisare en Discord", "app": "Discord", "actions": ["connect", "write"], "claim_says": "can",
                                              "verdict": "supported", "evidence": "", "evidence_says": "other"}])
    assert out["eval_report"]["action"] == "retry" and "read-only" in out["eval_feedback"]


async def test_claims_reading_from_a_read_only_app_is_fine(monkeypatch):
    monkeypatch.setattr(ev, "app_capability", lambda app: "read")
    out, _ = await _claims_run(monkeypatch, [{"claim": "puedo leer tus mensajes de Discord", "app": "Discord", "actions": ["read"],
                                              "claim_says": "can", "verdict": "supported", "evidence": "", "evidence_says": "other"}])
    assert out["eval_report"]["action"] == "approved"


def test_format_is_checked_by_code():
    check = {"name": "format"}
    assert ev._format_check(check, "Hola, todo bien.")[0].passed
    assert not ev._format_check(check, "mira:\n```python\nprint(1)")[0].passed            # bloque sin cerrar
    assert not ev._format_check(check, '{"respuesta": "hola"}')[0].passed                  # JSON crudo
    p = "Este es un parrafo largo que se repite por error en la respuesta del agente."
    assert not ev._format_check(check, f"{p}\n\n{p}")[0].passed                          # parrafo duplicado


async def test_a_mandates_only_check_does_not_run_without_mandates(monkeypatch):
    calls = []

    async def fake_one(model, check, body, reply=""):
        calls.append(check["name"])
        return ev._Check(name=check["name"], note="ok", passed=True, severity="none"), ""
    monkeypatch.setattr(ev, "_judge_one", fake_one)
    monkeypatch.setattr(ev, "get_agent_personality", _qc([{"name": "follows_instructions", "criterion": "c", "only_with_mandates": True},
                                                          {"name": "credentials", "criterion": "c"}]))
    monkeypatch.setattr(ev, "get_agent_identity", AsyncMock(return_value={}))
    monkeypatch.setattr(ev, "build_platform_context", AsyncMock(return_value=""))
    await ev.response_evaluator_node(_state())
    assert calls == ["credentials"]
    calls.clear()
    await ev.response_evaluator_node({**_state(), "active_mandates": ["max 2 frases"]})
    assert sorted(calls) == ["credentials", "follows_instructions"]


async def test_the_judge_sees_what_the_user_said_before_its_window(monkeypatch):
    seen = {}

    async def fake_one(model, check, body, reply=""):
        seen["body"] = body
        return ev._Check(name=check["name"], note="ok", passed=True, severity="none"), ""
    monkeypatch.setattr(ev, "_judge_one", fake_one)
    monkeypatch.setattr(ev, "get_agent_personality", _qc([{"name": "no_fabrication", "criterion": "c"}]))
    monkeypatch.setattr(ev, "get_agent_identity", AsyncMock(return_value={}))
    monkeypatch.setattr(ev, "build_platform_context", AsyncMock(return_value=""))
    msgs = [HumanMessage("cambie a Excel")] + [m for i in range(6) for m in (AIMessage(f"r{i}"), HumanMessage(f"u{i}"))] \
        + [AIMessage("Usas Excel.")]
    await ev.response_evaluator_node({**_state(), "messages": msgs})
    assert "WHAT THE USER SAID EARLIER" in seen["body"] and "cambie a Excel" in seen["body"]


def test_an_unavailable_app_the_user_asked_for_must_be_mentioned():
    ctx = "- Slack: coming soon — the team is building it\n"
    body = lambda earlier, user: f"{earlier}USER MESSAGE:\n{user}\n\nUSER INTENT (normalized): x\n\n{ctx}REPLY TO EVALUATE:\n"  # noqa: E731
    chk = {"name": "mentions_limits"}
    ask = "guardalo en Sheets y avisame por Slack"
    assert not ev._limits_check(chk, body("", ask), "Conecta Google Sheets y lo guardamos.")[0].passed      # calla Slack
    assert ev._limits_check(chk, body("", ask), "Lo guardo en Sheets; Slack aun no esta disponible.")[0].passed
    assert ev._limits_check(chk, body("USER: y Slack?\n", ask), "Conecta Google Sheets.")[0].passed        # ya se dijo antes
    assert ev._limits_check(chk, body("", "guardalo en Sheets"), "Conecta Google Sheets.")[0].passed       # no lo pidio

    assert not ev._limits_check(chk, body("", ask), "Lo guardo en Sheets y te aviso por Slack.")[0].passed  # como si funcionara
    assert not ev._limits_check(chk, body("", ask), "Te aviso por Slack. Slack aun no esta disponible.")[0].passed  # se contradice


def test_an_unavailable_app_offered_unprompted_must_say_it_is_not_available():
    body = "USER MESSAGE:\nmanda un mensaje a Discord\n\nUSER INTENT (normalized): x\n\nREPLY TO EVALUATE:\n"
    chk = {"name": "mentions_limits"}
    assert not ev._limits_check(chk, body, "No puedo enviar a Discord. Podríamos avisarte por Slack.", {"Slack"})[0].passed
    assert ev._limits_check(chk, body, "No puedo enviar a Discord. Podemos avisarte por Gmail.", {"Slack"})[0].passed
    assert ev._limits_check(chk, body, "Slack aún no está disponible; te aviso por Gmail.", {"Slack"})[0].passed
    assert ev._limits_check(chk, body, "Revisa tu Slackware.", {"Slack"})[0].passed  # palabra completa
    assert ev._limits_check(chk, body, "Our teams keep adding integrations.", {"Teams"})[0].passed  # palabra comun, no la app
    assert not ev._limits_check(chk, body, "Te aviso por Teams.", {"Teams"})[0].passed


def test_credentials_by_code_flags_only_leaks_and_requests():
    chk = {"name": "credentials"}
    body = "USER: hola\nUSER MESSAGE:\nmi contraseña de gmail es Abc12345, conectalo tu\n\nUSER INTENT (normalized): x"
    assert not ev._credentials_check(chk, body, "Listo, usaré Abc12345 para entrar.")[0].passed            # repite
    assert not ev._credentials_check(chk, body, "Para seguir, compárteme tu contraseña de Gmail.")[0].passed  # la pide
    assert ev._credentials_check(chk, body, "No la compartas aquí; cámbiala y usa el botón Conectar Gmail.")[0].passed
    other = "USER MESSAGE:\n¿qué banco te dije que uso? ya tengo las palabras clave listas\n\nUSER INTENT (normalized): x"
    assert ev._credentials_check(chk, other, "No tengo información sobre el banco que usas.")[0].passed     # falso positivo real del juez LLM
