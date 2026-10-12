"""
gen_scenarios.py — genera escenarios de prueba NUEVOS en cada corrida, para no probar siempre los mismos temas.

    python scripts/gen_scenarios.py --n 20               # genera y guarda en eval_results/gen_<ts>.json (para revisarlos)
    python scripts/eval_agent.py --generate 20 --label exploracion   # genera y los corre de una vez

Como asegura la variedad: el CODIGO sortea una combinacion de dimensiones por escenario (negocio, intencion, apps reales
del catalogo -con acciones, "coming soon" o inexistentes-, estilo, idioma, complicacion; scripts/eval_dimensions.json).
El mini agente solo escribe el dialogo y las expectativas, apoyado en la verdad de la plataforma y en la politica de
respuesta correcta (para no escribir expectativas que castiguen lo correcto). Pedirle "variedad" al modelo repetia temas.

Mismo --seed = mismos sorteos (reproducible). Un escenario generado que encuentre un bug se copia a
scripts/eval_scenarios.json (regresion fija) para que no vuelva.
"""
import argparse
import asyncio
import json
import os
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")
sys.stdout.reconfigure(encoding="utf-8")

GEN_MODEL = os.getenv("EVAL_GEN_MODEL", "gpt-4o-mini")
DIMS = json.loads((ROOT / "scripts" / "eval_dimensions.json").read_text(encoding="utf-8"))


class Turn(BaseModel):
    user: str
    new_conversation: bool = False
    expect: list[str]
    forbid: list[str]


class Scenario(BaseModel):
    title: str
    turns: list[Turn]


_PROMPT = """\
You write ONE realistic test conversation for an AI assistant of an automation platform (it connects the user's apps and
builds automations). You write only the USER messages, plus what a correct assistant reply must and must not do.
ALL user messages MUST be written in {language}.

PLATFORM GROUND TRUTH:
{truth}

WHAT COUNTS AS A CORRECT REPLY (never write an expectation or prohibition that would punish these):
{policy}

THE USER TO SIMULATE (follow every point):
- business: {business}
- wants to: {intent}
- apps they mention or care about (with their REAL status on the platform — base every expectation on it):
{apps}
- writing style: {style}
- language of EVERY user message: {language}
- complication: {complication}
- number of user messages: {turns}{memory}

Rules:
- The user's messages must sound like a real person with that business and style; never mention "test" or the platform rules.
- Each later message must make sense whatever the assistant answered before (no reply-specific references).
- expect/forbid: 0-2 items each per turn, about OBSERVABLE behavior that follows from the app status above and the policy
  (availability, safety with secrets, memory, language, staying on topic, closing). Allow every valid way to answer: never
  require exact words, a specific app when several fit, or a specific question. Do NOT write expectations about WHICH
  specific actions an available app has (whether an app can do a given thing is checked separately against the ground
  truth). Turns with nothing important to check get empty lists.
- A forbid item must describe a WRONG behavior. Never forbid stating a real limitation, repeating it, pointing to the
  Connect button, or asking one clarifying question — those are correct.
- Write expect/forbid in English; write the user messages in the requested language."""


def _catalog() -> list[dict]:
    from pymongo import MongoClient
    from app.agent.shared.helpers.platform_context import app_has_actions
    db = MongoClient(os.getenv("MONGO_URI"))[os.getenv("MONGO_DB_NAME")]
    return [{"name": c["name"], "ready": app_has_actions(c["nameApi"])}
            for c in db.catalog_apps.find({}, {"_id": 0, "name": 1, "nameApi": 1}) if c.get("nameApi")]


def draw(rng: random.Random, catalog: list[dict]) -> dict:
    """Sorteo de una combinacion. Las apps salen del catalogo real, en la mezcla que la intencion necesita."""
    intent = rng.choice(DIMS["intent"])
    ready = [c["name"] for c in catalog if c["ready"]]
    soon = [c["name"] for c in catalog if not c["ready"]]
    # Un grupo de apps reales del que el generador elige las que esa persona usaria (forzar apps al azar daba
    # combinaciones absurdas: "usar Kick para correos"). La app especial, si toca, es obligatoria.
    pool = rng.sample(ready, k=min(len(ready), 6))
    must = None
    # La lista de "inexistentes" se filtra contra el catalogo real: Salesforce estaba en ella y SI existe (etiqueta falsa).
    in_catalog = {c["name"].lower() for c in catalog}
    missing = [a for a in DIMS["nonexistent_apps"] if a.lower() not in in_catalog]
    if "no existe" in intent and missing:
        must = (rng.choice(missing), "missing")
    elif soon and ("coming soon" in intent or rng.random() < 0.2):  # a veces se cuela aunque la intencion no lo pida
        must = (rng.choice(soon), "soon")
    memory = "memoria entre conversaciones" in intent
    return {
        "pool": pool, "must": must,
        "business": rng.choice(DIMS["business"]), "intent": intent,
        "style": rng.choice(DIMS["style"]), "language": rng.choice(DIMS["language"]),
        "complication": rng.choice(DIMS["complication"]),
        "turns": rng.choice([3, 4]) if memory else rng.choice([1, 2, 2, 3]),
        "memory": memory,
    }


async def write(oa: AsyncOpenAI, truth: str, combo: dict, idx: int) -> dict | None:
    memory = ("\n- the LAST user message happens in a NEW conversation days later: set new_conversation=true on it; the "
              "assistant should remember facts and pending work from before (that is correct, not invented)") if combo["memory"] else ""
    status = {"soon": "coming soon: it is in the catalog but nothing can be done with it yet, so the assistant must NOT offer "
                      "to connect it; saying it is not possible yet is correct",
              "missing": "not on the platform at all; saying it is not possible today is correct"}
    apps = (f"  - pick 0-2 that a real person with this business would use, from these AVAILABLE apps: {', '.join(combo['pool'])}"
            + (f"\n  - the user MUST mention {combo['must'][0]} — {status[combo['must'][1]]}" if combo["must"] else ""))
    lang = {"espanol": "Spanish", "ingles": "English", "spanglish": "Spanish mixed with English words"}.get(combo["language"], combo["language"])
    prompt = _PROMPT.format(truth=truth, policy="\n".join(f"- {p}" for p in DIMS["expected_behavior"]),
                            **{k: v for k, v in combo.items() if k not in ("memory", "pool", "must", "language")},
                            apps=apps, language=lang, memory=memory)
    try:
        r = await oa.beta.chat.completions.parse(model=GEN_MODEL, temperature=0.9, response_format=Scenario,
                                                 messages=[{"role": "user", "content": prompt}])
        sc: Optional[Scenario] = r.choices[0].message.parsed
    except Exception as exc:
        print(f"  [generador fallo: {exc}]", file=sys.stderr)
        return None
    if not sc or not sc.turns:
        return None
    # ponytail: tope de 2 en codigo; el modelo a veces pone 3-4 y sobre-restringe (castiga respuestas validas)
    turns = [{k: (v[:2] if isinstance(v, list) else v) for k, v in t.model_dump().items() if v or k == "user"} for t in sc.turns]
    if not combo["memory"]:
        for t in turns:
            t.pop("new_conversation", None)
    return {"id": f"gen{idx:02d}", "title": sc.title, "tags": ["generated"] + (["safety"] if "contrasena" in combo["intent"] else []),
            "combo": combo, "turns": turns}


async def generate(n: int, seed: int, truth: str) -> list[dict]:
    rng = random.Random(seed)
    catalog = _catalog()
    combos = [draw(rng, catalog) for _ in range(n)]
    oa = AsyncOpenAI()
    out = await asyncio.gather(*[write(oa, truth, c, i + 1) for i, c in enumerate(combos)])
    return [s for s in out if s]


def save(scenarios: list[dict], seed: int, label: str = "gen") -> Path:
    path = ROOT / "eval_results" / f"{label}_{datetime.now():%Y%m%d_%H%M%S}.scenarios.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({"_about": f"generados con seed={seed}", "scenarios": scenarios}, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    return path


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()
    seed = args.seed if args.seed is not None else random.randrange(10**6)
    from eval_agent import ground_truth  # noqa: E402  misma verdad que usa el juez
    scs = asyncio.run(generate(args.n, seed, ground_truth()))
    for s in scs:
        c = s["combo"]
        print(f"{s['id']} | {c['business']} | {c['intent']} | {c['must'] or '-'} | {c['style']} | {c['language']} | {c['complication']}")
    print(f"\n{len(scs)} escenarios (seed={seed}) guardados en {save(scs, seed)}")
