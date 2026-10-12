"""
snapshot_prompts.py — foto de TODOS los prompts del agente en una version, para saber que se usaba y comparar versiones.

    python scripts/snapshot_prompts.py            # escribe doc/agente/prompts/<AGENT_VERSION>.json y muestra que cambio
    python scripts/snapshot_prompts.py --check    # solo compara Mongo con la foto de la version actual (no escribe)

Incluye:
  - datos de comportamiento en Mongo (agent_identity y agent_personality del SHIFU_AGENT_ID): voz, jueces, memoria, saludo...
  - prompts fijos en codigo (constantes *PROMPT*/*METHOD*/*SYSTEM* de los mini agentes).
El prompt del responder se arma en codigo (identity_loader/responder) a partir de esos datos; el codigo queda en git.
Se versiona en git: el diff entre dos fotos es exactamente lo que cambio en los prompts.
"""
import importlib
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")
sys.stdout.reconfigure(encoding="utf-8")
from pymongo import MongoClient  # noqa: E402

from app.agent.version import AGENT_VERSION, fingerprint  # noqa: E402

OUT = ROOT / "doc" / "agente" / "prompts"
# ponytail: lista a mano; un mini agente nuevo con prompt fijo se agrega aqui.
CODE_MODULES = [
    "app.agent.shared.prompts.semantic_intake",
    "app.agent.shared.nodes.response_evaluator",
    "app.agent.shared.memory.memory_learner",
    "app.agent.shared.nodes.research_curator",
    "app.agent.shared.documents.structured_extraction",
    "app.agent.shifu_base_v1.graph.req_nodes",
]
_NAME = re.compile(r"PROMPT|METHOD|SYSTEM")


def mongo_docs() -> tuple[dict, dict]:
    db = MongoClient(os.environ["MONGO_URI"])[os.environ.get("MONGO_DB_NAME", "shifu")]
    agent_id = os.getenv("SHIFU_AGENT_ID", "shifu_v1")
    strip = lambda d: {k: v for k, v in (d or {}).items() if k not in ("_id", "created_at", "updated_at")}
    return strip(db.agent_identity.find_one({"agent_id": agent_id})), strip(db.agent_personality.find_one({"agent_id": agent_id}))


def code_prompts() -> dict:
    out = {}
    for name in CODE_MODULES:
        mod = importlib.import_module(name)
        for attr, val in vars(mod).items():
            if _NAME.search(attr) and isinstance(val, str) and len(val) > 80:
                out[f"{name}.{attr}"] = val
    return out


def changed(old: dict, new: dict, prefix="") -> list[str]:
    keys = sorted(set(old) | set(new))
    diffs = []
    for k in keys:
        a, b = old.get(k), new.get(k)
        if isinstance(a, dict) and isinstance(b, dict):
            diffs += changed(a, b, f"{prefix}{k}.")
        elif a != b:
            diffs.append(f"{prefix}{k}: " + ("nuevo" if a is None else "quitado" if b is None else "cambio"))
    return diffs


def main():
    identity, personality = mongo_docs()
    snap = {
        "version": f"{AGENT_VERSION}+{fingerprint(identity, personality)}",
        "agent_id": os.getenv("SHIFU_AGENT_ID", "shifu_v1"),
        "mongo": {"agent_identity": identity, "agent_personality": personality},
        "code": code_prompts(),
    }
    snap = json.loads(json.dumps(snap, ensure_ascii=False, default=str))
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{AGENT_VERSION}.json"
    prev_files = sorted((p for p in OUT.glob("*.json") if p != path), key=lambda p: [int(x) for x in p.stem.split(".")])
    base = path if path.exists() else (prev_files[-1] if prev_files else None)
    if base:
        old = json.loads(base.read_text(encoding="utf-8"))
        diffs = changed(old.get("mongo", {}), snap["mongo"], "mongo.") + changed(old.get("code", {}), snap["code"], "code.")
        print(f"Contra {base.name} ({old.get('version')}): " + (f"{len(diffs)} cambios" if diffs else "sin cambios"))
        for d in diffs:
            print("  -", d)
        if path.exists() and diffs and "--check" in sys.argv:
            print(f"\nMongo/codigo ya no coinciden con la foto de {AGENT_VERSION}: sube la version o actualiza la foto.")
            sys.exit(1)
    if "--check" not in sys.argv:
        path.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"Foto {snap['version']} guardada en {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
