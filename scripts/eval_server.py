"""Servidor de las evals reales: solo 127.0.0.1:8001, base temporal y tope duro acumulado. Lo arranca
`scripts/run_evals.py --real`; no hace falta usarlo a mano.

    python scripts/eval_server.py --db assistant_ux_tmp_XXXX --log evals/resultados/tmp.jsonl [--cap 60000]
        [--hard-cap 200000] [--set UNTRUSTED_WRAP=1 ...]

- Opciones de .env, salvo: base temporal, AUTH_ENABLED=0, LANGSMITH_TRACING=false, TURN_TOKEN_CAP y los
  interruptores de seguridad en 0 (cada caso enciende los suyos con --set).
- Mide cada turno con `evals.harness.Meter` (tokens de TurnTokens + clasificador, latencia, herramientas).
- TOPE DURO: antes de cada /chat o /resume, si gasto acumulado del log + margen > --hard-cap, responde 429."""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ALLOWED = {"TURN_TOKEN_CAP", "MAX_MESSAGE_CHARS", "UNTRUSTED_WRAP", "MEMORY_REQUIRE_QUOTE", "URL_FILTER_ALWAYS",
           "TURN_MAX_SECONDS", "EFFECT_APPROVAL", "ANSWER_VERIFY", "MODEL_CALL_LIMIT", "FILES_ENABLED",
           "TRACE_METADATA", "TURN_METRICS", "FEEDBACK_ENABLED"}

p = argparse.ArgumentParser()
p.add_argument("--db", required=True)
p.add_argument("--log", required=True)
p.add_argument("--cap", type=int, default=60000)
p.add_argument("--hard-cap", type=int, required=True)
p.add_argument("--set", action="append", default=[], help="VARIABLE=valor")
p.add_argument("--app-db", default="", help="base de negocio temporal (TURN_METRICS/FEEDBACK_ENABLED), mismo clúster")
a = p.parse_args()
assert a.db.startswith("assistant_ux_tmp_"), "solo bases temporales"
assert not a.app_db or (a.app_db.startswith("assistant_ux_tmp_") and a.app_db != a.db), "solo bases temporales"

os.environ.update({
    "AI_MONGODB_DB": a.db, "MONGODB_DB": a.db, "TURN_TOKEN_CAP": str(a.cap), "AUTH_ENABLED": "0",
    "LANGSMITH_TRACING": "false", "TURN_MAX_SECONDS": "0", "UNTRUSTED_WRAP": "0", "MEMORY_REQUIRE_QUOTE": "0",
    "URL_FILTER_ALWAYS": "0", "EFFECT_APPROVAL": "0",
})
for kv in a.set:
    k, v = kv.split("=", 1)
    assert k in ALLOWED, f"{k} no está permitido en las evals"
    os.environ[k] = v

from assistant.core import server  # noqa: E402
from assistant.core.config import Settings  # noqa: E402

if a.app_db:  # la URI sale de .env (ya cargado al importar config) y nunca se imprime
    os.environ["APP_MONGODB_URI"] = os.environ["MONGODB_URI"]
    os.environ["APP_MONGODB_DB"] = a.app_db
from evals.harness import Meter, install  # noqa: E402

settings = Settings.from_env()
captured: dict = {}
_build = server._build_real_agent


def _build_and_keep(s, profile):
    captured["agent"], store = _build(s, profile)
    return captured["agent"], store


server._build_real_agent = _build_and_keep
meter = Meter(Path(a.log)).__enter__()  # antes de create_app: el servidor captura ahí el clasificador
app = server.create_app(settings=settings)
install(app, meter, lambda: captured["agent"], settings, hard_cap=a.hard_cap)

if __name__ == "__main__":
    import uvicorn

    print(f"evals en http://127.0.0.1:8001 | db {a.db} | cap {a.cap} | gastado {meter.spent()} de {a.hard_cap} "
          f"| {a.set}", file=sys.stderr)
    uvicorn.run(app, host="127.0.0.1", port=8001, log_level="warning")
