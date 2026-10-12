"""Mide la planeacion de workflows con funciones reales (nivel 3 del flujo de requisitos): _build_plan con 4o-mini REAL,
embeddings reales para las candidatas y apps conectadas simuladas. No hay Mongo ni se ejecuta nada.

Por caso: si cada paso esperado quedo con un function_id correcto (basta uno de su grupo), si los argumentos pasan la
validacion (o, en los casos que NO traen todos los datos, que el plan pregunte lo que falta en vez de inventarlo),
y cuantos pasos se descartaron por id inventado. Cuesta centavos (un plan por caso).
    python scripts/eval_workflow_plan.py [--only id1,id2]
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

from app.agent.shifu_base_v1.graph import req_nodes as rn  # noqa: E402

PRICE_IN, PRICE_OUT = 0.15 / 1e6, 0.60 / 1e6  # gpt-4o-mini

# need: un grupo por paso esperado (basta uno de los ids del grupo). complete: el usuario dio TODOS los datos, asi que
# no debe faltar nada; si es false, lo correcto es que falte algo y se pregunte. connected: apps simuladas como conectadas.
CASES = [
    {"id": "hoja_a_correo", "connected": ["google_sheets", "gmail"], "complete": True,
     "q": "cada lunes lee la hoja Ventas (id 1AbCdEf, rango A1:B20) y mándame el total por Gmail a ana@empresa.com",
     "need": [["google_sheets.values.get"], ["gmail.messages.send"]]},
    {"id": "correo_a_hoja", "connected": ["google_sheets", "gmail"], "complete": True, "trigger": "email", "filter": "factura",
     "q": "cuando llegue un correo con la palabra factura, guarda su asunto como una fila nueva en la hoja 1XyZ123 rango A:B",
     "need": [["google_sheets.values.append"]], "never": ["gmail.messages.search"]},
    {"id": "drive_a_correo", "connected": ["google_drive", "gmail"], "complete": True,
     "q": "todos los días busca en mi Drive los archivos que se llamen contrato y mándame la lista por Gmail a luis@empresa.com",
     "need": [["google_drive.files.search", "google_drive.files.list"], ["gmail.messages.send"]]},
    {"id": "asana_tarea", "connected": ["asana"], "complete": True,
     "q": "cada viernes crea una tarea en Asana llamada Revisar métricas en el proyecto 120345 del workspace 99887",
     "need": [["asana.tasks.create"]]},
    {"id": "hoja_nueva_aviso", "connected": ["google_sheets", "gmail"], "complete": True,
     "q": "cada mes crea una hoja de cálculo nueva llamada Reporte y avísame por correo a mi@empresa.com con el asunto Hoja lista",
     "need": [["google_sheets.spreadsheets.create"], ["gmail.messages.send"]]},
    {"id": "no_leidos_a_borrador", "connected": ["gmail"], "complete": True,
     "q": "cada mañana busca mis correos no leídos y deja un borrador para mi@empresa.com con asunto Resumen y texto Revisar pendientes",
     "need": [["gmail.messages.search"], ["gmail.drafts.create"]]},
    {"id": "fila_diaria", "connected": ["google_sheets"], "complete": True,
     "q": "cada día agrega una fila con la fecha de hoy en la hoja 1AbCdEf rango A:B",
     "need": [["google_sheets.values.append"]]},
    {"id": "dos_apps_tareas", "connected": ["asana", "clickup"], "complete": False,
     "q": "cada semana crea la tarea Reunión de equipo en ClickUp y otra igual en Asana",
     "need": [["clickup.tasks.create"], ["asana.tasks.create"]]},
    {"id": "faltan_datos", "connected": ["google_sheets", "gmail"], "complete": False,
     "q": "lee mi hoja de ventas y mándame el total por correo",
     "need": [["google_sheets.values.get"], ["gmail.messages.send"]]},
    # Disparador por correo (v0.7.0): trigger_type email, filtro de Gmail y SIN paso que busque el correo.
    {"id": "correo_a_hoja_reactivo", "connected": ["gmail", "google_sheets"], "complete": True, "trigger": "email", "filter": "ana@empresa.com",
     "q": "cuando me llegue un correo de ana@empresa.com agrega una fila con el remitente y el asunto a mi hoja "
          "https://docs.google.com/spreadsheets/d/1AbCdEf/edit en la pestaña Correos",
     "need": [["google_sheets.values.append"]], "never": ["gmail.messages.search"]},
    {"id": "correo_reenvio", "connected": ["gmail"], "complete": True, "trigger": "email", "filter": "factura",
     "q": "cada vez que llegue un correo con asunto factura, mándale un correo a conta@empresa.com con asunto Nueva factura "
          "y el texto del correo que llegó",
     "need": [["gmail.messages.send"]], "never": ["gmail.messages.search"]},
    # Hoja nombrada sin id ni enlace. META PENDIENTE (v0.8.1): buscarla en Drive y pasar su id por plantilla. Hoy el plan
    # pregunta por la hoja (falla este caso, pero no inventa); la regla de prompt que lo lograba rompia otros dos casos.
    {"id": "hoja_por_nombre", "connected": ["google_drive", "google_sheets", "gmail"], "complete": True,
     "q": "cada lunes lee mi hoja de cálculo llamada Ventas 2026 y mándame el contenido por Gmail a ana@empresa.com",
     "need": [["google_drive.files.search"], ["google_sheets.values.get"], ["gmail.messages.send"]]},
    {"id": "app_sin_funciones", "connected": ["gmail"], "complete": True, "legacy_app": "slack",
     "q": "cada lunes manda un mensaje por Slack al canal general que diga buen inicio de semana",
     "need": []},
]


async def main(only: set) -> None:
    cases = [c for c in CASES if not only or c["id"] in only]
    rn.mongo_manager = SimpleNamespace(db=object())
    tokens = [0, 0]
    real = rn._plan_llm

    class Spy:
        async def ainvoke(self, msgs, **kw):
            ai = await real.ainvoke(msgs, **kw)
            u = ai.usage_metadata or {}
            tokens[0] += u.get("input_tokens", 0)
            tokens[1] += u.get("output_tokens", 0)
            return ai
    rn._plan_llm = Spy()

    need_n = need_ok = args_n = args_ok = dropped = 0
    for c in cases:
        async def connected(db, uid, apps=c["connected"]):
            return set(apps)
        rn.connected_apps = connected
        scope = list(c["connected"]) + ([c["legacy_app"]] if c.get("legacy_app") else [])
        state = {"user_id": "eval", "messages": [HumanMessage(c["q"])], "req_apps_scope": scope}
        plan = await rn._build_plan(state)
        steps = plan.get("steps") or []
        used = {s["function_id"] for s in steps if s.get("function_id")}
        hits = [any(i in used for i in group) for group in c["need"]]
        missing = plan.get("missing") or []
        need_n += len(hits)
        need_ok += sum(hits)
        if c.get("legacy_app"):  # sin funciones para esa app: no debe inventar una funcion de otra app para cubrirla
            good = all(s.get("app") == c["legacy_app"] for s in steps if not s.get("function_id")) and not used
        elif c["complete"]:
            good = not missing and bool(steps)
        else:
            good = bool(missing)  # faltaban datos y el plan lo detecto (no los invento)
        if os.getenv("PLAN_ARGS"):  # PLAN_ARGS=1: ver los argumentos que quedaron (para revisar que no se quito de mas)
            print("     ", [s.get("args") for s in steps])
        if c.get("trigger"):  # el disparador y su filtro tambien cuentan; y no debe haber un paso que busque el correo
            good = (good and plan.get("trigger_type") == c["trigger"] and c["filter"] in str(plan.get("trigger_filter") or "")
                    and not used & set(c.get("never") or []))
            print(f"      disparador={plan.get('trigger_type')} filtro={plan.get('trigger_filter')!r} "
                  f"args={[s.get('args') for s in steps]}")
        args_n += 1
        args_ok += good
        dropped += len(plan.get("notes") or [])
        print(f"  {'✓' if all(hits) else '✗'} {c['id']:22} ids={sorted(used)} args_ok={good} "
              f"faltan={[(m['step'], m['field']) for m in missing]} notas={len(plan.get('notes') or [])}")
    usd = tokens[0] * PRICE_IN + tokens[1] * PRICE_OUT
    print(json.dumps({
        "pasos_con_function_id_correcto": f"{need_ok}/{need_n} ({100 * need_ok // max(need_n, 1)}%)",
        "casos_con_argumentos_validos": f"{args_ok}/{args_n} ({100 * args_ok // max(args_n, 1)}%)",
        "pasos_descartados_por_validacion": dropped, "tokens": tokens, "usd": round(usd, 4)}, ensure_ascii=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    asyncio.run(main({x for x in ap.parse_args().only.split(",") if x}))
