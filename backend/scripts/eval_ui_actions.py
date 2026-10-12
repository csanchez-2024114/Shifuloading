"""
eval_ui_actions.py — ¿elige semantic_intake la accion de interfaz correcta, y ninguna cuando no se pidio?

    python scripts/eval_ui_actions.py [repeticiones]     # solo el intake, sin servidor: ~$0.01

Lee el catalogo real de Mongo (ui_actions_catalog; se carga con scripts/seed_ui_actions.py). Al agregar una accion al
catalogo, agregar aqui una fila que la pida y otra parecida que NO deba dispararla.
"""
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REPS = int(sys.argv[1]) if len(sys.argv) > 1 else 2
sys.path.insert(0, str(REPO))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO / ".env")
from langchain_core.messages import HumanMessage  # noqa: E402

from app.core.mongo import mongo_manager  # noqa: E402

CASES = [  # (mensaje, id esperado o None, params esperados)
    ("abreme mis workflows", "open_workflows", {}),
    ("show me my automations", "open_workflows", {}),
    ("quiero ver que apps tengo conectadas", "open_connections", {}),
    ("donde veo lo que recuerdas de mi? abrelo", "open_memory", {}),
    ("llevame a ajustes", "open_settings", {}),
    ("muestrame mi plan y cuanto llevo gastado", "open_billing", {}),
    ("abre la pagina de gmail", "open_app", {"app": "gmail"}),
    ("ensename mis avisos", "open_notifications", {}),
    ("empecemos una conversacion nueva", "new_conversation", {}),
    ("donde esta el centro de ayuda? abrelo", "open_help", {}),
    # no son peticiones de abrir una pantalla
    ("pausa mi workflow de los lunes", None, {}),
    ("que es un workflow?", None, {}),
    ("conecta mi gmail", None, {}),
    ("cuantas tareas tengo en asana", None, {}),
    ("que recuerdas de mi?", None, {}),
    ("hola", None, {}),
    ("quiero crear un workflow que lea mi hoja cada lunes", None, {}),
]


sys.stdout.reconfigure(encoding="utf-8")


async def main():
    await mongo_manager.connect() if hasattr(mongo_manager, "connect") else None
    from app.agent.shared.nodes.semantic_intake import semantic_intake_node
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    sem = asyncio.Semaphore(6)
    from app.agent.shared.helpers import ui_actions
    offer = [a["id"] for a in await ui_actions.get_catalog() if a.get("source") == "user"]  # un cliente que soporta todo

    async def one(q):
        async with sem:
            out = await semantic_intake_node({"user_id": "eval", "messages": [HumanMessage(q)], "user_message": q,
                                              "current_time_utc": now, "effort_level": "medio", "ui_offer": offer})
        return out.get("requested_ui_actions") or []

    good = 0
    for q, want, params in CASES:
        res = await asyncio.gather(*(one(q) for _ in range(REPS)))
        ok = [(r[0]["id"] if r else None) == want and (not want or r[0]["params"] == params) and len(r) <= 1 for r in res]
        good += sum(ok)
        got = sorted({(r[0]["id"] + str(r[0]["params"] or "")) if r else "-" for r in res})
        print(f"{'OK' if all(ok) else '✗ '} {sum(ok)}/{REPS} esperado={want or '-'} obtuvo={got}  {q}")
    print(f"correctos: {good}/{len(CASES) * REPS}")


asyncio.run(main())
