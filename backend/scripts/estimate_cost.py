"""
estimate_cost.py — estima cuanto cuesta una peticion al agente SIN llamar a OpenAI (no gasta credito).

Ejecuta los nodos reales (responder, evaluador, semantic_intake) con un modelo falso que solo CAPTURA los mensajes que
enviarian, cuenta los tokens de entrada con el tokenizador de OpenAI (exacto) y calcula el costo con app/billing/model_prices.json.
Los tokens de SALIDA no se pueden conocer sin llamar al modelo: se estiman con respuestas reales guardadas por el arnes de
evaluacion (eval_results/) y se marcan como supuesto. La medicion real por peticion la da `usage` en el chat (ver chat.py).

    python scripts/estimate_cost.py
"""
import asyncio
import glob
import json
import os
import statistics
import sys
from pathlib import Path

import tiktoken
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage
from motor.motor_asyncio import AsyncIOMotorClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")
sys.stdout.reconfigure(encoding="utf-8")

from langchain_openai import ChatOpenAI  # noqa: E402
from app.billing.pricing import cost_usd  # noqa: E402
from app.core.mongo import mongo_manager  # noqa: E402

ENC = tiktoken.get_encoding("o200k_base")  # gpt-4o-mini y gpt-4.1-nano
SEMANTIC_INTAKE_OBSERVED_TOTAL = 3160       # tokens totales reportados por OpenAI en trazas reales (entrada + salida), 4 muestras 3158-3173


def toks(text: str) -> int:
    return len(ENC.encode(text or ""))


def msg_tokens(messages) -> int:
    total = 0
    for m in messages:
        content = m["content"] if isinstance(m, dict) else m.content
        total += toks(content if isinstance(content, str) else json.dumps(content)) + 4  # ~4 tokens de formato por mensaje
    return total


async def capture(coro_factory) -> list[tuple[str, list]]:
    """Corre un nodo con ChatOpenAI.ainvoke falso y devuelve [(modelo, mensajes)] de cada llamada que habria hecho."""
    seen: list[tuple[str, list]] = []
    original = ChatOpenAI.ainvoke

    async def fake(self, messages, *a, **k):
        seen.append((getattr(self, "model_name", "?"), list(messages)))
        return AIMessage(content="{}")

    ChatOpenAI.ainvoke = fake
    try:
        await coro_factory()
    except Exception:
        pass  # solo importa lo capturado antes del fallo del parseo
    finally:
        ChatOpenAI.ainvoke = original
    return seen


def real_reply_stats() -> dict:
    """Tamano real de mensajes y respuestas, y numero de intentos, de las corridas guardadas por el arnes."""
    rows = [r for f in glob.glob(str(ROOT / "eval_results" / "*.json")) for r in json.loads(Path(f).read_text(encoding="utf-8"))["rows"] if r.get("reply")]
    if not rows:
        return {"reply": 110, "user": 35, "judge_evidence": 30, "attempts": 1.4, "n": 0}
    ev = [toks(e["evidence"]) for r in rows if r.get("verdict") for e in r["verdict"]["expectations"] + r["verdict"]["forbidden"]]
    return {"reply": statistics.mean(toks(r["reply"]) for r in rows), "user": statistics.mean(toks(r["user"]) for r in rows),
            "judge_evidence": statistics.mean(ev) if ev else 30, "attempts": statistics.mean(r["attempts"] for r in rows), "n": len(rows)}


async def main():
    agent_id = os.getenv("SHIFU_AGENT_ID", "shifu_v1")
    mongo_manager.db = AsyncIOMotorClient(os.getenv("MONGO_URI"))[os.getenv("MONGO_DB_NAME")]
    from app.agent.shared.nodes import responder, response_evaluator as ev, semantic_intake
    stats = real_reply_stats()
    reply_t, user_t = stats["reply"], stats["user"]

    base_state = {
        "messages": [HumanMessage("sí eso me serviría, los pedidos me llegan al gmail siempre con el mismo asunto. ¿qué más se puede automatizar?")],
        "user_id": "est", "conversation_id": "est", "user_name": "Prueba", "effort_level": "medio",
        "structured_prompt": "Yes, that would help; orders arrive in Gmail with the same subject. What else can be automated?",
        "apps_involved": ["gmail"], "semantic_intake_debug": {"detected_intent": "question"}, "user_sentiment": "neutral",
        "validation_reports": [{"source": "auth", "app": "gmail", "status": "ok"}, {"source": "catalog", "app": "gmail", "status": "ok"}],
        "current_time_utc": "2026-10-10T00:00:00Z", "user_connected_apps": {"gmail": ["a@b.c"]},
    }

    # 1) Responder y evaluador reales (sin historial)
    resp = await capture(lambda: responder.responder_node(dict(base_state)))
    model_resp, resp_msgs = resp[-1]
    resp_in = msg_tokens(resp_msgs)
    judged_state = dict(base_state, messages=base_state["messages"] + [AIMessage("x " * int(reply_t * 0.7))], active_mandates=["x"])
    qc = (await ev.get_agent_personality()).get("quality_control") or {}
    n_checks = len(qc.get("checks") or ev._DEFAULT_CHECKS)

    class FakeJudge:
        async def ainvoke(self, messages):
            seen_eval.append(messages)
            return ev._Eval(checks=[ev._Check(name=c["name"], note="n", passed=True) for c in (qc.get("checks") or ev._DEFAULT_CHECKS)], feedback="")

    class FakeOne:
        async def ainvoke(self, messages, config=None):
            seen_eval.append(messages)
            return ev._One(note="n", severity="none", feedback="")

    seen_eval: list = []
    per_check = (qc.get("judge") or {}).get("mode") == "per_check"
    if per_check:   # un juez barato por chequeo: n_checks llamadas, cada una con UN criterio
        original_one, ev._one_for = ev._one_for, (lambda model: FakeOne())
        await ev.response_evaluator_node(judged_state)
        ev._one_for = original_one
        eval_calls = len(seen_eval) or n_checks
        eval_in = int(sum(msg_tokens(m) for m in seen_eval) / max(len(seen_eval), 1))
        eval_out = int(stats["judge_evidence"] + 22)
    else:           # un solo juez con todos los chequeos
        original_llm, ev._llm = ev._llm, FakeJudge()
        await ev.response_evaluator_node(judged_state)
        ev._llm = original_llm
        eval_calls = 1
        eval_in = msg_tokens(seen_eval[-1]) if seen_eval else 0
        eval_out = int(n_checks * (stats["judge_evidence"] + 14) + 20)

    # 2) semantic_intake real (entrada capturada; salida = lo observado en trazas reales menos la entrada)
    si = await capture(lambda: semantic_intake.semantic_intake_node(dict(base_state)))
    si_in = msg_tokens(si[0][1]) if si else int(SEMANTIC_INTAKE_OBSERVED_TOTAL * 0.93)
    si_out = max(SEMANTIC_INTAKE_OBSERVED_TOTAL - si_in, 120)

    eval_model = (qc.get("judge") or {}).get("model") or ev._DEFAULT_EVAL_MODEL
    retry_extra = 140  # tokens que suma el mensaje [CORRECCION] en un reintento del responder
    pair = user_t + reply_t  # tokens que añade cada turno previo al historial (el responder recibe TODO el historial)

    def turn(attempts: float, history_turns: int = 0, resp_model: str = model_resp, evaluator: bool = True, ev_model: str = eval_model):
        r_in = resp_in + history_turns * pair
        c_si = cost_usd("gpt-4o-mini", si_in, si_out)
        c_r = attempts * cost_usd(resp_model, r_in, reply_t) + (attempts - 1) * cost_usd(resp_model, retry_extra, 0)
        c_e = attempts * eval_calls * cost_usd(ev_model, eval_in, eval_out) if evaluator else 0.0
        return c_si, c_r, c_e, c_si + c_r + c_e

    print(f"Agente: {agent_id} | responder: {model_resp} (tope de salida por esfuerzo: 300/600/1500/4000) | evaluador: {eval_model}\n")
    print("=== LLAMADAS DE UN TURNO DE CHAT (tokens de entrada: reales; salida: ver supuestos) ===")
    print(f"{'nodo':<20}{'modelo':<14}{'entrada':>9}{'salida':>9}{'USD/llamada':>13}")
    for name, model, i, o in (("semantic_intake", "gpt-4o-mini", si_in, si_out), ("responder", model_resp, resp_in, int(reply_t)),
                              ("response_evaluator", eval_model, eval_in, eval_out)):
        mult = eval_calls if name == "response_evaluator" else 1
        print(f"{name + (f' x{mult}' if mult > 1 else ''):<20}{model:<14}{i:>9,}{o:>9,}{mult * cost_usd(model, i, o):>13.5f}")
    print(f"\nSupuestos de salida: respuesta={reply_t:.0f} tok (media de {stats['n']} respuestas reales guardadas), "
          f"evaluador={eval_out} tok ({n_checks} chequeos x ~{stats['judge_evidence'] + 14:.0f}), intentos medios medidos={stats['attempts']:.2f}\n")

    A = stats["attempts"]
    cases = [
        ("Turno 1, 1 intento (sin reintentos)", turn(1)),
        (f"Turno 1, intentos medios medidos ({A:.2f})", turn(A)),
        ("Turno 1, peor caso (5 intentos)", turn(5)),
        (f"Conversacion de 6 turnos previos, {A:.2f} intentos", turn(A, 6)),
        (f"Conversacion de 20 turnos previos, {A:.2f} intentos", turn(A, 20)),
        ("Sin evaluador (apagado en la personalidad)", turn(1, evaluator=False)),
        (f"Evaluador en gpt-4o-mini, {A:.2f} intentos", turn(A, ev_model="gpt-4o-mini")),
        (f"Usuario elige responder gpt-4.1-nano, {A:.2f} intentos", turn(A, resp_model="gpt-4.1-nano")),
    ]
    print("=== COSTO DE UNA LLAMADA SEGUN EL MODELO QUE USE CADA ROL (USD; tokens reales de entrada) ===")
    models = ["gpt-4.1-nano", "gpt-4o-mini"]
    print(f"{'rol':<20}" + "".join(f"{m:>15}" for m in models))
    for role, i, o in (("semantic_intake", si_in, si_out), ("responder", resp_in, int(reply_t)), ("response_evaluator", eval_in, eval_out)):
        k = eval_calls if role == "response_evaluator" else 1
        print(f"{role:<20}" + "".join(f"{k * cost_usd(m, i, o):>15.5f}" for m in models))
    print("(cada llamada x intentos; ver el desglose por peticion mas abajo)\n")

    print("=== COSTO POR PETICION (USD) ===")
    print(f"{'caso':<54}{'intake':>9}{'responder':>11}{'evaluador':>11}{'TOTAL':>10}{'x1000':>9}")
    for label, (a, b, c, t) in cases:
        print(f"{label:<54}{a:>9.5f}{b:>11.5f}{c:>11.5f}{t:>10.5f}{t * 1000:>9.2f}")


asyncio.run(main())
