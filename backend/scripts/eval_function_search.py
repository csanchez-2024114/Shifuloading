"""Mide la busqueda de funciones del modo act SIN el agente (fase 0): palabras ($0) contra embeddings (~$0.001).

Por cada caso de eval_actions_cases.json busca dentro del cerco (las apps del caso), K candidatas por app, y mira si
cada llamada necesaria tiene al menos un id aceptable entre las candidatas. Los casos sin funcion no cuentan para el
acierto; se reporta el puntaje mas alto que obtuvieron (sirve para decidir un umbral de "no hay funcion").

    python scripts/eval_function_search.py [--k 3]
Los embeddings de las fichas se guardan en eval_results/fn_embeddings.json (se recalculan solo si cambia el texto).
"""
import argparse
import asyncio
import json
import math
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from app.agent.shared.helpers.platform_context import _functions, _terms  # noqa: E402
from app.agent.shared.memory.memory_embedder import _embeddings  # noqa: E402

CACHE = ROOT / "eval_results" / "fn_embeddings.json"


def _doc(fid: str, desc: str) -> str:
    return f"{fid.replace('.', ' ').replace('_', ' ')}: {desc}"


def _cos(a, b) -> float:
    return sum(x * y for x, y in zip(a, b)) / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)) or 1)


async def _fn_vectors(fns) -> dict:
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    todo = [(fid, _doc(fid, d)) for fid, _, d, _ in fns if cache.get(fid, {}).get("text") != _doc(fid, d)]
    if todo:
        vecs = await _embeddings.aembed_documents([t for _, t in todo])
        cache.update({fid: {"text": t, "v": v} for (fid, t), v in zip(todo, vecs)})
        CACHE.parent.mkdir(exist_ok=True)
        CACHE.write_text(json.dumps(cache), encoding="utf-8")
    return {fid: c["v"] for fid, c in cache.items()}


def _hit(case, picked: set) -> bool:
    return all(any(i in picked for i in group) for group in case["need"])


async def main(k: int) -> None:
    cases = json.loads((ROOT / "scripts" / "eval_actions_cases.json").read_text(encoding="utf-8"))["cases"]
    fns = _functions()
    by_app = {}
    for fid, verb, desc, terms in fns:
        by_app.setdefault(fid.split(".", 1)[0], []).append((fid, verb, desc, terms))
    fvec = await _fn_vectors(fns)
    qvec = dict(zip([c["id"] for c in cases], await _embeddings.aembed_documents([c["q"] for c in cases])))

    score = {"palabras": [0, 0], "embeddings": [0, 0]}
    for c in cases:
        kw, em, top_none = set(), set(), 0.0
        for app in c["apps"]:
            pool = by_app.get(app, [])
            q = _terms(c["q"])
            kw |= {f[0] for f in sorted(pool, key=lambda f: -len(q & f[3]))[:k] if q & f[3]}
            ranked = sorted(((_cos(qvec[c["id"]], fvec[f[0]]), f[0]) for f in pool), reverse=True)[:k]
            em |= {fid for _, fid in ranked}
            top_none = max([top_none] + [s for s, _ in ranked])
        if not c["need"]:
            print(f"  {c['id']:28} sin funcion: puntaje mas alto {top_none:.3f}")
            continue
        for name, picked in (("palabras", kw), ("embeddings", em)):
            ok = _hit(c, picked)
            score[name][0] += ok
            score[name][1] += 1
            if not ok:
                print(f"  {c['id']:28} {name:10} FALLA  candidatas: {sorted(picked)}")
    print(json.dumps({n: f"{h}/{t} ({h / t:.0%})" for n, (h, t) in score.items()}, ensure_ascii=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=3)
    asyncio.run(main(ap.parse_args().k))
