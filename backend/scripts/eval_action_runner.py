"""Mide action_runner SOLO (sin grafo, sin responder ni juez): funciones simuladas (example.output) y 4o-mini real.

Por caso de eval_actions_cases.json: si llamo una funcion de cada grupo necesario, si las independientes salieron en la
PRIMERA vuelta (paralelo), cuantas vueltas uso, y en los casos sin funcion, que no ejecutara nada. ~$0.03 por corrida.
    python scripts/eval_action_runner.py [--only id1,id2]
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")
os.environ["SHIFU_FUNCTIONS_SIMULATE"] = "1"
os.environ["SHIFU_FUNCTIONS_STATUSES"] = "active,testing,draft"

from langchain_core.messages import HumanMessage  # noqa: E402

from app.agent.shared.nodes import action_runner as ar  # noqa: E402

PRICE_IN, PRICE_OUT = 0.15 / 1e6, 0.60 / 1e6  # gpt-4o-mini


async def main(only: set) -> None:
    cases = json.loads((ROOT / "scripts" / "eval_actions_cases.json").read_text(encoding="utf-8"))["cases"]
    cases = [c for c in cases if not only or c["id"] in only]
    ar.mongo_manager = SimpleNamespace(db=object())

    async def personality():
        return {}
    ar.get_agent_personality = personality
    real_llm = ar._llm
    tokens = [0, 0]
    rounds_log: list = []

    class Spy:
        def __init__(self, llm):
            self.llm = llm

        def bind_tools(self, tools):
            self.bound = self.llm.bind_tools(tools)
            return self

        async def ainvoke(self, msgs, config=None):
            ai = await self.bound.ainvoke(msgs, config=config)
            u = ai.usage_metadata or {}
            tokens[0] += u.get("input_tokens", 0)
            tokens[1] += u.get("output_tokens", 0)
            rounds_log.append([c["name"].replace("__", ".") for c in ai.tool_calls or []])
            return ai
    ar._llm = lambda model: Spy(real_llm(model))

    ok = parallel_ok = parallel_n = 0
    for c in cases:
        async def connected(db, uid, apps=c["apps"]):
            return set(apps)
        ar._connected = connected
        rounds_log.clear()
        out = await ar.action_runner_node({"user_id": "eval", "messages": [HumanMessage(c["q"])], "apps_involved": c["apps"]})
        called = {r["fn"] for r in out["action_results"]}
        if c["need"]:
            hit = all(any(i in called for i in g) for g in c["need"])
        else:
            hit = not called
        ok += hit
        first = set(rounds_log[0]) if rounds_log else set()
        if len(c["need"]) > 1 and not c.get("depends"):
            parallel_n += 1
            par = all(any(i in first for i in g) for g in c["need"])
            parallel_ok += par
        else:
            par = None
        mark = "✓" if hit else "✗"
        print(f"  {mark} {c['id']:28} vueltas={len(rounds_log)} paralelo={par} llamadas={rounds_log} stop={out.get('action_stop')}")
    usd = tokens[0] * PRICE_IN + tokens[1] * PRICE_OUT
    print(json.dumps({"acierto": f"{ok}/{len(cases)}", "paralelo_en_primera_vuelta": f"{parallel_ok}/{parallel_n}",
                      "tokens": tokens, "usd": round(usd, 4)}, ensure_ascii=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    asyncio.run(main({x for x in ap.parse_args().only.split(",") if x}))
