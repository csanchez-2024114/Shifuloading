"""
Shifu Memory Test Runner
Corre los 14 escenarios de MEMORY_TEST.md contra el WebSocket de agente_v3
y determina PASS/FAIL con un juez LLM (gpt-4o-mini).

Uso:
  python scripts/memory_test_runner.py --user-id <mongodb_user_id>
  python scripts/memory_test_runner.py --user-id <id> --scenario 3-C
  python scripts/memory_test_runner.py --user-id <id> --host staging.hypershifu.com

Requiere en .env: SECRET_KEY, OPENAI_API_KEY
"""

import argparse
import asyncio
import json
import os
import sys
import uuid

import websockets
from dotenv import load_dotenv
from jose import jwt
from openai import AsyncOpenAI

load_dotenv()

_SECRET = os.getenv("SECRET_KEY", "")
_oai    = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))

# ── Escenarios (mirroring MEMORY_TEST.md) ─────────────────────────────────────
# check=None → turno de setup, no se evalúa.
# check=str  → criterio que el juez LLM evalúa.

SCENARIOS = [
    {
        "id": "1-A", "level": "Fácil",
        "turns": [
            {"msg": "Quiero conectar Gmail con Slack", "check": None},
            {"msg": "¿cuántas apps me pediste conectar?",
             "check": "Must answer 2 (Gmail and Slack) without asking which apps again."},
        ],
    },
    {
        "id": "1-B", "level": "Fácil",
        "turns": [
            {"msg": "conectar Notion con Trello", "check": None},
            {"msg": "no, me refería a Jira, no a Trello",
             "check": "Must work with Notion + Jira. Must NOT treat Trello as an active app."},
        ],
    },
    {
        "id": "1-C", "level": "Fácil",
        "turns": [
            {"msg": "conecta el correo con el calendario", "check": None},
            {"msg": "¿qué apps vas a usar?",
             "check": "Must answer Gmail and Google Calendar by their canonical names, without asking for clarification."},
        ],
    },
    {
        "id": "2-A", "level": "Medio",
        "turns": [
            {"msg": "¿qué apps puedo conectar?", "check": None},
            {"msg": "¿cuáles son de Google?", "check": None},
            {"msg": "quiero usar la primera que mencionaste",
             "check": "Must identify and use the first Google app listed in the previous turn, without asking the user to repeat it."},
        ],
    },
    {
        "id": "2-B", "level": "Medio",
        "turns": [
            {"msg": "Estoy armando un sistema para gestionar leads de ventas", "check": None},
            {"msg": "¿qué apps me recomiendas?", "check": None},
            {"msg": "ok conecta la primera", "check": None},
            {"msg": "¿para qué me servía esa?",
             "check": "Must explain the app's use case in the context of lead/sales management, without the user repeating that context."},
        ],
    },
    {
        "id": "2-C", "level": "Medio",
        "turns": [
            {"msg": "conectar Gmail con HubSpot", "check": None},
            {"msg": "la de trabajo", "check": None},
            {"msg": "¿cuál cuenta de Gmail elegí?",
             "check": "Must reply with the exact email of the work account without asking again."},
        ],
    },
    {
        "id": "3-A", "level": "Difícil",
        "turns": [
            {"msg": "quiero automatizar mis publicaciones en Instagram", "check": None},
            {"msg": "olvida eso, mejor conecta Slack con Notion", "check": None},
            {"msg": "¿y qué me habías dicho de Instagram?",
             "check": "Must recall the Instagram publishing automation intent from turn 1, even though the topic changed in between."},
        ],
    },
    {
        "id": "3-B", "level": "Difícil",
        "turns": [
            {"msg": "solo quiero usar apps gratis", "check": None},
            {"msg": "¿qué CRM me recomiendas?", "check": None},
            {"msg": "¿y herramientas de gestión de proyectos?",
             "check": "Must recommend only free tools, applying the constraint from turn 1 without the user repeating it."},
        ],
    },
    {
        "id": "3-C", "level": "Difícil",
        "turns": [
            {"msg": "quiero conectar la app donde hago hojas de cálculo", "check": None},
            {"msg": "y también la de presentaciones de Google", "check": None},
            {"msg": "¿cuáles van a estar conectadas?",
             "check": "Must list Google Sheets and Google Slides by name, without asking what those descriptions refer to."},
        ],
    },
    {
        "id": "3-D", "level": "Difícil",
        "turns": [
            {"msg": "conectar Gmail con Trello", "check": None},
            {"msg": "la personal", "check": None},
            {"msg": "ahora conecta también Slack", "check": None},
            {"msg": "¿qué cuenta de Gmail quedó seleccionada?",
             "check": "Must recall and reply with the email of the personal Gmail account without asking again."},
        ],
    },
    {
        "id": "4-A", "level": "Extremo",
        "turns": [
            {"msg": "quiero conectar Slack", "check": None},
            {"msg": "en realidad prefiero Discord", "check": None},
            {"msg": "no, Slack está bien", "check": None},
            {"msg": "¿con qué app quedamos?",
             "check": "Must answer Slack (the last decision). Must NOT say Discord or both."},
        ],
    },
    {
        "id": "4-B", "level": "Extremo",
        "turns": [
            {"msg": "mi empresa se llama TechFlow y vendemos software B2B", "check": None},
            {"msg": "usamos HubSpot para clientes y Slack para el equipo", "check": None},
            {"msg": "quiero automatizar notificaciones cuando un lead cambia de etapa", "check": None},
            {"msg": "¿qué me propones?",
             "check": "Must propose HubSpot → Slack, contextualized for B2B lead management at TechFlow, without the user repeating that context."},
        ],
    },
    {
        "id": "4-C", "level": "Extremo",
        "turns": [
            {"msg": "tengo dos cuentas de Gmail: trabajo y personal", "check": None},
            {"msg": "¿qué apps puedo conectar?", "check": None},
            {"msg": "¿cuáles son de comunicación?", "check": None},
            {"msg": "conecta Slack", "check": None},
            {"msg": "y también Gmail",
             "check": "Must ask which of the two Gmail accounts (work or personal) the user wants, recalling that two accounts were mentioned in turn 1."},
        ],
    },
    {
        "id": "4-D", "level": "Extremo",
        "turns": [
            {"msg": "solo trabajo con apps de Google y Slack", "check": None},
            {"msg": "quiero un flujo que me avise en Slack cuando alguien edite un doc", "check": None},
            {"msg": "la cuenta de Slack es la del equipo de marketing", "check": None},
            {"msg": "y el doc es uno de Google Docs", "check": None},
            {"msg": "arma el flujo",
             "check": "Must propose Google Docs → Slack (marketing account) without suggesting apps outside the Google/Slack ecosystem established in turn 1."},
        ],
    },
]


# ── Core helpers ───────────────────────────────────────────────────────────────

def _make_token(user_id: str) -> str:
    return jwt.encode({"user_id": user_id}, _SECRET, algorithm="HS256")


async def _send_and_wait(ws, text: str) -> str:
    """Send one user message, collect tokens until 'done'."""
    await ws.send(json.dumps({"type": "user_message", "text": text, "model": "gpt-4o-mini"}, ensure_ascii=False))
    accumulated = ""
    async for raw in ws:
        msg = json.loads(raw)
        t = msg.get("type")
        if t == "token":
            accumulated += msg.get("text", "")
        elif t == "done":
            return msg.get("text") or accumulated
        elif t == "error":
            return f"[WS ERROR] {msg.get('message', '')}"
    return accumulated


async def _judge(response: str, criterion: str) -> tuple[bool, str]:
    """LLM judge: does the response meet the criterion?"""
    r = await _oai.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        max_tokens=80,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a strict test evaluator. "
                    "Decide if the agent response meets the criterion. "
                    "Reply with exactly PASS or FAIL on the first word, "
                    "then one short sentence explaining why."
                ),
            },
            {
                "role": "user",
                "content": f"Criterion: {criterion}\n\nAgent response:\n{response[:800]}",
            },
        ],
    )
    verdict = r.choices[0].message.content.strip()
    passed  = verdict.upper().startswith("PASS")
    return passed, verdict


# ── Scenario runner ────────────────────────────────────────────────────────────

async def _run_scenario(scenario: dict, host: str, user_id: str) -> dict:
    conv_id = str(uuid.uuid4())
    token   = _make_token(user_id)
    url     = f"ws://{host}/api/v4/ws/chat-debug?token={token}&conversation_id={conv_id}"

    turn_results = []
    try:
        async with websockets.connect(url, open_timeout=10) as ws:
            for i, turn in enumerate(scenario["turns"], 1):
                response = await asyncio.wait_for(_send_and_wait(ws, turn["msg"]), timeout=30)
                if turn["check"]:
                    passed, reason = await _judge(response, turn["check"])
                    turn_results.append({"turn": i, "passed": passed, "reason": reason, "preview": response[:200]})
                else:
                    turn_results.append({"turn": i, "passed": None})
    except Exception as exc:
        return {"id": scenario["id"], "level": scenario["level"], "passed": False,
                "error": str(exc), "turns": turn_results}

    evaluated = [t for t in turn_results if t["passed"] is not None]
    overall   = all(t["passed"] for t in evaluated) if evaluated else True
    return {"id": scenario["id"], "level": scenario["level"], "passed": overall, "turns": turn_results}


# ── Output helpers ─────────────────────────────────────────────────────────────

COLORS = {
    "green":  "\033[92m",
    "red":    "\033[91m",
    "yellow": "\033[93m",
    "reset":  "\033[0m",
    "bold":   "\033[1m",
}

def _c(text: str, color: str) -> str:
    return f"{COLORS[color]}{text}{COLORS['reset']}"


def _print_result(result: dict) -> None:
    icon    = "✅" if result.get("passed") else "❌"
    color   = "green" if result.get("passed") else "red"
    err     = result.get("error")
    print(f"  {icon} {_c(result['id'], color)}  [{result['level']}]" + (f"  💥 {err}" if err else ""))
    for t in result.get("turns", []):
        if t.get("passed") is None:
            continue
        t_icon  = "    ✅" if t["passed"] else "    ❌"
        t_color = "green" if t["passed"] else "red"
        print(f"{t_icon} turno {t['turn']}: {_c(t['reason'], t_color)}")


def _print_summary(results: list) -> None:
    print(f"\n{_c('='*60, 'bold')}")
    print(f"  {_c('RESULTADOS FINALES', 'bold')}")
    print(_c("="*60, "bold"))

    level_order = ["Fácil", "Medio", "Difícil", "Extremo"]
    by_level: dict[str, list] = {}
    for r in results:
        by_level.setdefault(r["level"], []).append(r)

    total_pass = total = 0
    for level in level_order:
        if level not in by_level:
            continue
        lvl  = by_level[level]
        ok   = sum(1 for r in lvl if r.get("passed"))
        n    = len(lvl)
        total_pass += ok
        total      += n
        bar   = _c("█" * ok, "green") + _c("░" * (n - ok), "red")
        label = _c(f"{ok}/{n}", "green" if ok == n else ("yellow" if ok else "red"))
        print(f"  {level:<10} [{bar}]  {label}")

    pct   = 100 * total_pass // total if total else 0
    color = "green" if pct == 100 else ("yellow" if pct >= 50 else "red")
    print(f"\n  TOTAL: {_c(f'{total_pass}/{total}  ({pct}%)', color)}\n")


# ── Entry point ────────────────────────────────────────────────────────────────

async def main() -> None:
    parser = argparse.ArgumentParser(description="Shifu Memory Test Runner")
    parser.add_argument("--user-id",  required=True, help="MongoDB user _id")
    parser.add_argument("--host",     default="localhost:8000", help="host:port of the backend")
    parser.add_argument("--scenario", default=None, help="Run only this scenario ID (e.g. 3-C)")
    args = parser.parse_args()

    if not _SECRET:
        sys.exit("❌  SECRET_KEY not found in .env")
    if not os.getenv("OPENAI_API_KEY"):
        sys.exit("❌  OPENAI_API_KEY not found in .env")

    scenarios = SCENARIOS
    if args.scenario:
        scenarios = [s for s in SCENARIOS if s["id"] == args.scenario]
        if not scenarios:
            sys.exit(f"❌  Scenario '{args.scenario}' not found. Valid IDs: {[s['id'] for s in SCENARIOS]}")

    print(f"\n{_c('='*60, 'bold')}")
    print(f"  {_c('Shifu Memory Test Runner', 'bold')}")
    print(f"  host={args.host}  user={args.user_id}  scenarios={len(scenarios)}")
    print(f"{_c('='*60, 'bold')}\n")

    results = []
    for scenario in scenarios:
        turns_n = len(scenario["turns"])
        print(f"▶  [{scenario['id']}] {scenario['level']} — {turns_n} turnos...")
        result = await _run_scenario(scenario, args.host, args.user_id)
        _print_result(result)
        results.append(result)
        print()

    _print_summary(results)


if __name__ == "__main__":
    asyncio.run(main())
