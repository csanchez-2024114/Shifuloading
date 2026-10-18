"""Subida opcional de una corrida a LangSmith: nunca obligatoria. Solo actúa si LANGSMITH_TRACING está activo y el
paquete `langsmith` está instalado; si no, devuelve el motivo y no importa nada."""
import os

DATASET_NAME = "agente-0-evals"


def enabled() -> bool:
    return (os.getenv("LANGSMITH_TRACING") or "").strip().lower() in ("1", "true", "yes")


def upload(results: dict) -> str:
    if not enabled():
        return "LangSmith: no se subió (LANGSMITH_TRACING no está activo)."
    try:
        from langsmith import Client
    except ImportError:
        return "LangSmith: no se subió (falta el paquete langsmith)."
    client = Client()
    if client.has_dataset(dataset_name=DATASET_NAME):
        dataset = client.read_dataset(dataset_name=DATASET_NAME)
    else:
        dataset = client.create_dataset(DATASET_NAME, description="Casos de scripts/run_evals.py")
    meta = results["meta"]
    # un ejemplo por caso y corrida: entradas = id, salidas = resultado de los checks (sin contenido de usuarios)
    client.create_examples(
        dataset_id=dataset.id,
        inputs=[{"case": c["id"], "category": c.get("category")} for c in results["cases"]],
        outputs=[{"passed": c.get("passed"), "tokens": c.get("tokens"),
                  "checks": {k["name"]: k["ok"] for k in c.get("checks", [])}} for c in results["cases"]],
        metadata=[{"mode": meta["mode"], "commit": meta["commit"], "date": meta["date"]} for _ in results["cases"]],
    )
    return f"LangSmith: {len(results['cases'])} casos subidos al dataset {DATASET_NAME}."
