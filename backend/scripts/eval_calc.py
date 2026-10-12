"""Mide si action_runner hace las cuentas con las herramientas de calculo (y si el numero sale bien) en vez de de cabeza.

La hoja simulada tiene 80 filas: no cabe en lo que el modelo ve del resultado, asi que un total de cabeza sale mal.
Pasa un caso si llamo a la herramienta esperada y el valor es el correcto. ~$0.01 por corrida (4o-mini real).
    python scripts/eval_calc.py [--repeats 2]
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
os.environ["SHIFU_FUNCTIONS_STATUSES"] = "active,testing,draft"

from langchain_core.messages import HumanMessage  # noqa: E402

from app.agent.shared.nodes import action_runner as ar  # noqa: E402
from app.functions import registry, runner  # noqa: E402
from app.functions.spec import Result  # noqa: E402

SID = "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
URL = f"https://docs.google.com/spreadsheets/d/{SID}/edit"
ROWS = [[f"Cliente {i}", f"${(i * 37) % 900 + 100:,}.50", "enero" if i % 2 else "febrero"] for i in range(1, 81)]
AMOUNTS = [(i * 37) % 900 + 100.5 for i in range(1, 81)]
SHEET = {"spreadsheet_id": SID, "range": "Ventas!A1:C81", "header": ["Cliente", "Monto", "Mes"], "rows": ROWS,
         "row_count": len(ROWS), "truncated": False}

CASES = [
    {"id": "total_columna", "tool": "aggregate_column", "expect": round(sum(AMOUNTS), 2),
     "q": f"lee la hoja {URL} y dime el total de la columna Monto"},
    {"id": "promedio_filtrado", "tool": "aggregate_column", "expect": round(sum(AMOUNTS[0::2]) / 40, 2),
     "q": f"de la hoja {URL}, ¿cuál es el promedio del Monto de enero?"},
    {"id": "cuantas_filas", "tool": "aggregate_column", "expect": 40,
     "q": f"en la hoja {URL}, ¿cuántas ventas hubo en febrero?"},
    {"id": "porcentaje", "tool": "calculate", "expect": round(sum(AMOUNTS) * 0.16, 2),
     "q": f"lee la hoja {URL}, suma la columna Monto y dime cuánto sería el 16% de ese total"},
]


async def main(repeats: int) -> None:
    registry.load_all()
    ar.mongo_manager = SimpleNamespace(db=object())

    async def personality():
        return {}
    ar.get_agent_personality = personality

    async def connected(db, uid):
        return {"google_sheets"}
    ar._connected = connected

    async def fake_execute(fn, raw_input, **kw):
        return Result.success(SHEET if fn.spec.id == "google_sheets.values.get" else (fn.spec.examples[0].output or {}))
    runner.execute = fake_execute  # action_runner lo importa al llamar

    passed = total = 0
    for case in CASES:
        for _ in range(repeats):
            out = await ar.action_runner_node({"user_id": "eval", "messages": [HumanMessage(case["q"])], "apps_involved": ["google_sheets"]})
            calc = [r for r in out["action_results"] if r["fn"] == f"shifu.calc.{case['tool']}" and r["ok"]]
            values = [json.loads(r["data"]).get("value") for r in calc]
            ok = any(isinstance(v, (int, float)) and abs(v - case["expect"]) < 0.01 for v in values)
            total += 1
            passed += ok
            print(f"  {'✓' if ok else '✗'} {case['id']:18} esperado={case['expect']} obtenido={values} "
                  f"llamadas={[r['fn'].split('.')[-1] for r in out['action_results']]}")
    print(json.dumps({"cuentas_correctas": f"{passed}/{total}"}, ensure_ascii=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=2)
    asyncio.run(main(ap.parse_args().repeats))
