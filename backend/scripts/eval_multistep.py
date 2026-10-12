"""Mide tareas de VARIOS pasos en una sola peticion del modo act: leer en una app, transformar y escribir en otra.

Funciones simuladas con datos fijos y 4o-mini real. Un caso pasa si la ultima escritura lleva los datos correctos que
salieron de los pasos anteriores (no inventados). ~$0.01 por corrida.
    python scripts/eval_multistep.py [--repeats 2]
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


def _msg(i, sender, subject):
    return {"id": f"m{i}", "thread_id": f"t{i}", "sender": sender, "to": "yo@empresa.test", "subject": subject,
            "date": "Mon, 5 Oct 2026 09:30:00 -0500", "snippet": "…", "label_ids": ["INBOX"], "unread": False}


DATA = {
    "gmail.messages.search": {"messages": [_msg(1, "Luis Gomez <luis@proveedor.test>", "Factura 1042"),
                                           _msg(2, "Luis Gomez <luis@proveedor.test>", "Cotizacion de noviembre"),
                                           _msg(3, "Luis Gomez <luis@proveedor.test>", "Cambio de cuenta bancaria")],
                              "count": 3, "result_size_estimate": 3, "next_page_token": None},
    "google_sheets.values.get": {"spreadsheet_id": SID, "range": "Ventas!A1:B4", "header": ["Cliente", "Monto"],
                                 "rows": [["Acme", "1,250.00"], ["Globex", "980.50"], ["Initech", "2,300.25"]],
                                 "row_count": 3, "truncated": False},
}

# must: textos que deben aparecer en los argumentos de la escritura `write` (prueban que uso lo que leyo).
CASES = [
    {"id": "correos_a_hoja", "apps": ["gmail", "google_sheets"], "write": "google_sheets.values.append",
     "must": ["Factura 1042", "Cotizacion de noviembre", "Cambio de cuenta bancaria"],
     "q": f"busca los correos de Luis y agrega a mi hoja {URL} en la pestaña Correos una fila por cada correo con el remitente y el asunto"},
    {"id": "total_a_borrador", "apps": ["gmail", "google_sheets"], "write": "gmail.drafts.create", "must": ["4530.75|4,530.75"],
     "q": f"lee la hoja {URL}, suma la columna Monto y déjame un borrador para ana@empresa.test con asunto Total de ventas que diga el total"},
    {"id": "tres_pasos", "apps": ["gmail", "google_sheets"], "write": "google_sheets.values.append", "must": ["3", "4530.75|4,530.75"],
     "q": f"cuenta cuántos correos tengo de Luis, suma la columna Monto de la hoja {URL} y agrega una fila en la pestaña Resumen "
          "con esos dos números"},
]


async def main(repeats: int) -> None:
    registry.load_all()
    ar.mongo_manager = SimpleNamespace(db=object())

    async def personality():
        return {}
    ar.get_agent_personality = personality

    async def fake_execute(fn, raw_input, **kw):
        return Result.success(DATA.get(fn.spec.id) or fn.spec.examples[0].output or {})
    runner.execute = fake_execute  # action_runner lo importa al llamar

    passed = total = 0
    for case in CASES:
        async def connected(db, uid, apps=case["apps"]):
            return set(apps)
        ar._connected = connected
        for _ in range(repeats):
            out = await ar.action_runner_node({"user_id": "eval", "messages": [HumanMessage(case["q"])], "apps_involved": case["apps"]})
            writes = [r for r in out["action_results"] if r["fn"] == case["write"]]
            dumped = json.dumps([r["args"] for r in writes], ensure_ascii=False)
            ok = bool(writes) and all(any(alt in dumped for alt in m.split("|")) for m in case["must"])
            total += 1
            passed += ok
            print(f"  {'✓' if ok else '✗'} {case['id']:18} llamadas={[r['fn'].split('.', 1)[1] for r in out['action_results']]} "
                  f"stop={out.get('action_stop')}\n      escritura: {dumped[:330]}")
    print(json.dumps({"tareas_completas": f"{passed}/{total}"}, ensure_ascii=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=2)
    asyncio.run(main(ap.parse_args().repeats))
