"""Evals del agente.

    python scripts/run_evals.py                      # modo falso: modelos falsos, 0 tokens (también corre en la suite)
    python scripts/run_evals.py --only mem-guardar   # un caso (o varios, separados por comas)
    python scripts/run_evals.py --real               # muestra el plan y el costo, y NO corre
    python scripts/run_evals.py --real --hard-cap 450000 --confirm-cap 450000   # corre de verdad

Modo real: arranca scripts/eval_server.py en 127.0.0.1:8001 con una base temporal `assistant_ux_tmp_<fecha>` (que
borra al terminar), mide cada turno y respeta un tope duro acumulado (429 en el servidor y corte por margen antes
de cada caso). Sin `--confirm-cap` igual a `--hard-cap`, solo imprime el plan. Resultados en evals/resultados/.
Con `--langsmith`, y solo si LANGSMITH_TRACING está activo, sube el dataset y los resultados."""
import argparse
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evals import runner  # noqa: E402


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--real", action="store_true")
    p.add_argument("--only", default="", help="ids separados por comas")
    p.add_argument("--category", default="")
    p.add_argument("--cap", type=int, default=60000, help="TURN_TOKEN_CAP del modo real")
    p.add_argument("--hard-cap", type=int, default=0, help="tope duro acumulado del modo real")
    p.add_argument("--confirm-cap", type=int, default=0, help="debe ser igual a --hard-cap para correr")
    p.add_argument("--out", default=str(runner.RESULTS_DIR))
    p.add_argument("--langsmith", action="store_true")
    a = p.parse_args(argv)

    mode = "real" if a.real else "fake"
    cases = runner.load_dataset(mode=mode)
    if a.only:
        wanted = set(a.only.split(","))
        cases = [c for c in cases if c["id"] in wanted]
    if a.category:
        cases = [c for c in cases if c.get("category") == a.category]
    if not cases:
        print("Ningún caso coincide.")
        return 1

    extra = {}
    if a.real:
        plan = runner.real_plan(cases, a.cap)
        print(f"Plan real: {plan['cases']} casos, {plan['messages']} mensajes (/chat + /resume), "
              f"TURN_TOKEN_CAP {plan['turn_token_cap']}.")
        print(f"Estimación: ~{plan['estimate']:,} tokens. Peor caso (suma de márgenes): {plan['worst']:,}.")
        if not a.hard_cap or a.confirm_cap != a.hard_cap:
            print("No se corrió: pasa --hard-cap N y --confirm-cap N (el mismo número) para confirmar el gasto.")
            return 2
        db = f"assistant_ux_tmp_{time.strftime('%Y%m%d%H%M%S')}"
        log = Path(a.out) / f"{db}.jsonl"
        log.parent.mkdir(parents=True, exist_ok=True)
        print(f"Base temporal {db}; tope duro {a.hard_cap:,}.", flush=True)
        try:
            out = runner.run_real(cases, a.cap, a.hard_cap, log, db)
        finally:
            left = runner.drop_temp_db(db)
            tmp = [d for d in left if d.startswith("assistant_ux_tmp_")]
            print(f"Base temporal borrada. Bases temporales que quedan: {tmp or 'ninguna'}.")
        extra = {"turn_token_cap": a.cap, "hard_cap": a.hard_cap, "db": db, "log": log.name}
    else:
        out = runner.run_fake(cases)

    results = runner.build_results(mode, out, extra)
    path = runner.save_results(results, Path(a.out))
    s = results["summary"]
    for c in out:
        if c.get("passed") is False:
            print(f"FALLA {c['id']}: " + "; ".join(f"{k['name']}: {k['detail']}" for k in c["checks"] if not k["ok"]))
    print(f"{s['passed']}/{s['cases']} casos en verde, {s['failed']} fallas, {s['skipped']} sin correr, "
          f"{s['tokens']:,} tokens. Resultados: {path}")
    if a.langsmith:
        from evals.langsmith_upload import upload

        print(upload(results))
    return 0 if s["failed"] == 0 else 1


if __name__ == "__main__":
    logging.disable(logging.INFO)  # sin el registro de cada petición HTTP del cliente
    sys.exit(main())
