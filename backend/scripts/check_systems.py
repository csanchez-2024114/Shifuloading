"""
check_systems.py — ¿siguen funcionando todos los sistemas del agente? Se corre despues de cada cambio.

    python scripts/check_systems.py                 # pruebas sin costo + un escenario o dos por sistema (~$0.10, ~6 min)
    python scripts/check_systems.py --free          # solo las pruebas sin costo (pytest, ~1 min, $0)
    python scripts/check_systems.py --base http://localhost:5002

No mide nada nuevo: junta pytest y `eval_agent.py --only` y lo resume por sistema. La parte en vivo necesita el backend
arriba con funciones simuladas (SHIFU_FUNCTIONS_SIMULATE=1 SHIFU_FUNCTIONS_STATUSES=active,testing,draft) y
RATE_LIMIT_ENABLED=false. Sale con codigo 1 si algo falla.

Un "FALLA" en vivo se LEE antes de creerlo: el juez del arnes marca falsas (~4 de cada 10 en el replay de v0.9.6) y es
una sola corrida por escenario. Por eso se imprime el criterio que fallo y el inicio de la respuesta.
"""
import argparse
import glob
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

# Un sistema = los escenarios de eval_scenarios.json que lo ejercitan de punta a punta. Para cubrir algo nuevo se agrega
# el id aqui. ponytail: los avisos y el programador no tienen escenario de chat; los cubre solo pytest.
SYSTEMS = {
    "Conversación (grafo, tono, idioma)": ["saludo", "ingles"],
    "Catálogo y honestidad": ["app_inexistente"],
    "Memoria (misma y otra conversación)": ["memoria_entre_conversaciones"],
    "Búsqueda web": ["web_estable", "web_juicio"],
    "Modo act: leer en apps": ["act_dos_apps"],
    "Modo act: escribir con confirmación": ["act_enviar_correo"],
    "Crear workflows por chat": ["wf_programado"],
    "Administrar y ejecutar workflows": ["wf_administrar"],
    "Seguridad (credenciales en el chat)": ["credencial_gmail"],
}
PYTEST = {"Pruebas del agente (grafo, nodos, flujos)": "test/agente_v3", "Pruebas de funciones de apps": "test/functions"}


def run_pytest() -> list[tuple[str, bool, str]]:
    out = []
    for name, path in PYTEST.items():
        r = subprocess.run([sys.executable, "-m", "pytest", path, "-q", "-p", "no:cacheprovider"], cwd=ROOT,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        last = (r.stdout.strip().splitlines() or ["(sin salida)"])[-1]
        out.append((name, r.returncode == 0, last))
    return out


def run_live(base: str, max_usd: float) -> tuple[list[tuple[str, bool, str]], str]:
    from app.agent.version import AGENT_VERSION
    try:
        urllib.request.urlopen(f"{base}/docs", timeout=5)
    except Exception as exc:
        return [("Backend", False, f"no responde en {base} ({exc})")], ""
    label = f"check_{AGENT_VERSION.replace('.', '')}"
    ids = [i for group in SYSTEMS.values() for i in group]
    r = subprocess.run([sys.executable, "-X", "utf8", "scripts/eval_agent.py", "--base", base, "--label", label, "--repeats", "1",
                        "--max-usd", str(max_usd), "--only", ",".join(ids)], cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    files = sorted(glob.glob(str(ROOT / "eval_results" / f"{label}_*.json")))
    if r.returncode != 0 or not files:
        return [("Evaluación en vivo", False, (r.stderr or r.stdout).strip()[-300:])], ""
    data = json.loads(Path(files[-1]).read_text(encoding="utf-8"))
    rows, out, details = data["rows"], [], []
    for name, group in SYSTEMS.items():
        mine = [x for x in rows if x["scenario"] in group]
        # Un turno que el juez no pudo calificar (su llamada fallo) no es una falla del agente: se cuenta aparte.
        unjudged = [x for x in mine if x.get("has_criteria") and x.get("criteria_ok") is None and not x.get("error")]
        bad = [x for x in mine if x.get("error") or x.get("exhausted") or (x.get("has_criteria") and x.get("criteria_ok") is False)]
        missing = [g for g in group if not any(x["scenario"] == g for x in mine)]
        note = (f"{len(mine) - len(bad)}/{len(mine)} turnos" + (f", sin correr: {missing}" if missing else "")
                + (f", {len(unjudged)} sin calificar (falló el juez)" if unjudged else ""))
        out.append((name, bool(mine) and not bad and not missing, note))
        for x in bad:
            v = x.get("verdict") or {}
            why = ([x["error"]] if x.get("error") else []) + (["agotó los reintentos"] if x.get("exhausted") else []) \
                + [f"no cumplió: {e['text']}" for e in v.get("expectations", []) if not e["met"]] \
                + [f"hizo lo prohibido: {f['text']}" for f in v.get("forbidden", []) if f["violated"]]
            details.append(f"  {x['scenario']} turno {x['turn']}: {'; '.join(why) or 'sin detalle'}\n"
                           f"    respuesta: {(x.get('reply') or '')[:240]!r}")
    s = data["summary"]
    foot = (f"versión {s['agent_version']} · {s['turns']} turnos · {s['attempts_per_turn']} intentos por turno · "
            f"~${s['spent_usd_est']} estimado · {Path(files[-1]).name}")
    return out, "\n".join(details + [foot])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:5001")
    ap.add_argument("--free", action="store_true", help="solo pytest, sin gastar en OpenAI")
    ap.add_argument("--max-usd", type=float, default=0.30)
    args = ap.parse_args()

    results, extra = run_pytest(), ""
    if not args.free:
        live, extra = run_live(args.base, args.max_usd)
        results += live
    width = max(len(n) for n, _, _ in results)
    for name, ok, note in results:
        print(f"{'OK   ' if ok else 'FALLA'}  {name:<{width}}  {note}")
    if extra:
        print("\n" + extra)
    failed = [n for n, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} sistemas en verde" + (f" · revisar: {', '.join(failed)}" if failed else ""))
    sys.exit(1 if failed else 0)
