"""Mide si la busqueda web trae informacion VIGENTE, rotando temas: cada corrida sortea preguntas de un banco variado.

Corre semantic_intake (4o-mini real) y tavily_searcher (Tavily real) sueltos, sin responder ni jueces. Un caso pasa si
  - el intake pidio buscar y eligio una ventana de fechas aceptable para esa pregunta (`ok`),
  - la consulta no trae un año que no sea el actual ni uno que el usuario haya escrito,
  - la busqueda devolvio resultados.
Imprime la ventana usada y las fuentes con su fecha para leerlas a ojo. ~$0.001 de OpenAI y 1-2 creditos de Tavily por caso.
    python scripts/eval_web.py [--n 6] [--seed 7] [--all] [--judge]   (--judge agrega el juicio del analista, ~$0.001 mas por caso)
"""
import argparse
import asyncio
import json
import random
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from langchain_core.messages import HumanMessage  # noqa: E402

from app.agent.shared.nodes.semantic_intake import semantic_intake_node  # noqa: E402
from app.agent.shared.nodes.research_analyst import research_analyst_node  # noqa: E402
from app.agent.shared.nodes.tavily_searcher import tavily_searcher_node  # noqa: E402

# ok: ventanas aceptables. Para agregar temas, se agregan filas aqui.
BANK = [
    {"q": "¿a cuánto está el dólar hoy en México?", "ok": ["day"]},
    {"q": "¿cuánto vale el bitcoin ahorita?", "ok": ["day"]},
    {"q": "¿qué clima va a hacer mañana en Guadalajara?", "ok": ["day"]},
    {"q": "¿cómo quedó el último partido de la selección mexicana?", "ok": ["day", "week"]},
    {"q": "¿qué noticias hay de inteligencia artificial esta semana?", "ok": ["day", "week"]},
    {"q": "busca en internet las novedades de la API de Gmail este mes", "ok": ["week", "month"]},
    {"q": "¿qué cambió en Shopify últimamente?", "ok": ["week", "month"]},
    {"q": "¿cuál es el último modelo de iPhone que salió?", "ok": ["week", "month", "any"]},
    {"q": "¿cuáles son los límites de la API de Slack?", "ok": ["any"]},
    {"q": "¿cuánto cuesta el plan de pago de Notion?", "ok": ["month", "any"]},
    {"q": "¿cuál es la tasa de IVA en México?", "ok": ["any"]},
    {"q": "busca cómo configurar un webhook en HubSpot", "ok": ["any"]},
    {"q": "¿qué herramientas recomiendan para email marketing?", "ok": ["any"]},
    {"q": "¿quién es el presidente de Argentina?", "ok": ["month", "any"]},
    {"q": "busca cuáles eran los límites de la API de Twitter en 2022", "ok": ["any"]},
    {"q": "busca en internet la historia de cómo se fundó Mercado Libre", "ok": ["any"]},
    {"q": "busca en internet cuántos días de vacaciones marca la ley en México", "ok": ["any"]},
    {"q": "busca qué es el interés compuesto", "ok": ["any"]},  # tema conocido: aun asi pidio buscar
]


async def main(n: int, seed: int | None, run_all: bool, judge: bool, match: str = "") -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    cases = BANK if run_all else random.Random(seed).sample(BANK, min(n, len(BANK)))
    if match:
        cases = [c for c in BANK if match.lower() in c["q"].lower()]
    passed = 0
    for case in cases:
        state = {"user_id": "eval", "messages": [HumanMessage(case["q"])], "user_message": case["q"],
                 "current_time_utc": now, "effort_level": "medio", "user_location": "Guadalajara, Mexico"}
        intake = await semantic_intake_node(state)
        query, recency = intake.get("optimized_search_query") or "", intake.get("search_recency")
        years = set(re.findall(r"\b20\d{2}\b", query)) - {now[:4]} - set(re.findall(r"\b20\d{2}\b", case["q"]))
        found = await tavily_searcher_node({**state, **intake}) if intake.get("needs_external_info") else {}
        sources = found.get("retrieved_sources") or []
        ok = bool(intake.get("needs_external_info")) and recency in case["ok"] and not years and bool(sources)
        passed += ok
        print(f"{'✓' if ok else '✗'} {case['q']}\n    ventana={recency} (aceptable {case['ok']})  tema={intake.get('search_topic')}  consulta={query!r}"
              f"{'  AÑO VIEJO ' + str(sorted(years)) if years else ''}\n    {found.get('research_freshness')}")
        for s in sources[:5]:
            print(f"      {s.get('published', '(sin fecha)'):32} {s['url'][:100]}")
        if judge and found.get("retrieved_research"):  # el juicio del analista, para leerlo a ojo
            thought = await research_analyst_node({**state, **intake, **found})
            print("    " + (thought.get("curated_research") or "(sin juicio)").split("## Search results")[0].strip().replace(chr(10), chr(10) + "    "))
    print(json.dumps({"vigentes": f"{passed}/{len(cases)}"}, ensure_ascii=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=6)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--match", default="", help="solo las preguntas que contienen este texto")
    ap.add_argument("--judge", action="store_true", help="corre tambien research_analyst e imprime su juicio")
    a = ap.parse_args()
    asyncio.run(main(a.n, a.seed, a.all, a.judge, a.match))
