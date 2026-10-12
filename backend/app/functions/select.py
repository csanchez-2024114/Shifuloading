"""Seleccion de funciones para el agente: que apps tiene conectadas el usuario, que funciones caen dentro del cerco y cuales
son las mas parecidas a un texto (patron langgraph-bigtool). Lo comparten el modo act (action_runner) y el flujo de
requisitos (req_nodes) para que ambos usen el mismo cerco.

Fase 0 (scripts/eval_function_search.py): palabras 26% contra embeddings 92% con 5 candidatas por app; por eso embeddings.
"""
import math
import os

from app.core.constants import Collections, ConnectedAccountStatus

PER_APP = 5
VERBS_DEFAULT = frozenset({"read", "create", "update"})  # delete sigue fuera del cerco

# ponytail: vectores de las fichas en memoria del proceso (~$0.001 por arranque con 324); con miles, al Store/Atlas.
_fn_vectors: dict[str, list[float]] = {}


def norm(name: str) -> str:
    return "".join(ch for ch in (name or "").lower() if ch.isalnum())


def tool_name(fid: str) -> str:
    return fid.replace(".", "__")  # OpenAI solo acepta [a-zA-Z0-9_-]


def statuses() -> set[str]:
    """Estados de funcion que el agente puede usar. Hoy todas estan en draft: en local se abre con la variable."""
    return {s.strip() for s in os.getenv("SHIFU_FUNCTIONS_STATUSES", "active").split(",") if s.strip()}


def _cos(a, b) -> float:
    return sum(x * y for x, y in zip(a, b)) / ((math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))) or 1)


def function_pool(apps: set[str], verbs=VERBS_DEFAULT, exclude_ask: bool = False) -> dict:
    """Funciones dentro del cerco: de esas apps, con esos verbos y con estado permitido.
    exclude_ask: un workflow corre sin nadie delante, asi que lo irreversible o de borrado no puede planearse."""
    from app.functions import registry
    registry.load_all()
    ok = statuses()
    return {f.spec.id: f for f in registry.list_functions()
            if f.spec.app in apps and f.spec.verb.value in verbs and f.spec.status.value in ok
            and not (exclude_ask and f.spec.confirmation_policy.value == "ask")}


async def _usable_accounts(db, user_id: str) -> list[dict]:
    return await db[Collections.USER_CONNECTED_ACCOUNTS].find(
        {"user_id": user_id, "status": {"$in": list(ConnectedAccountStatus.USABLE)}},
        {"provider": 1, "account_id": 1}).to_list(length=200)


async def connected_apps(db, user_id: str) -> set[str]:
    """Apps del registro de funciones que el usuario tiene conectadas (por provider_keys)."""
    from app.functions import registry
    registry.load_all()
    providers = {norm(r.get("provider")) for r in await _usable_accounts(db, user_id)}
    return {a.app for a in registry.list_apps() if providers & {norm(k) for k in a.provider_keys}}


async def single_account_id(db, user_id: str, app: str) -> str | None:
    """El account_id de la app si el usuario tiene EXACTAMENTE una cuenta usable; con varias (o ninguna) None, y el
    ejecutor devuelve account_selection_required en vez de adivinar cual usar."""
    from app.functions import registry
    keys = {norm(k) for k in registry.get_app(app).provider_keys}
    rows = [r for r in await _usable_accounts(db, user_id) if norm(r.get("provider")) in keys]
    return str(rows[0]["account_id"]) if len(rows) == 1 and rows[0].get("account_id") else None


async def search_functions(pool: dict, query: str, apps: set[str], k: int = PER_APP) -> list[str]:
    from app.agent.shared.memory.memory_embedder import _embeddings  # perezoso: este paquete no depende del agente al importarse
    todo = [fid for fid in pool if fid not in _fn_vectors]
    if todo:
        docs = [f"{fid.replace('.', ' ').replace('_', ' ')}: {pool[fid].spec.description}" for fid in todo]
        _fn_vectors.update(zip(todo, await _embeddings.aembed_documents(docs)))
    q = await _embeddings.aembed_query(query)
    out = []
    for app in sorted(apps):  # una busqueda por app: "Asana y ClickUp" trae candidatas de las dos
        ranked = sorted((fid for fid in pool if pool[fid].spec.app == app), key=lambda fid: -_cos(q, _fn_vectors[fid]))
        # Las de buscar por nombre van siempre: sin ellas el modelo pasaba el nombre como id
        # ("task_gid": "Lanzamiento web", eval_action_runner 2026-10-10).
        finders = [fid for fid in ranked if fid.endswith(".search")][:2]
        out += list(dict.fromkeys(ranked[:k] + finders))
    return out


def tool_schema(fn) -> dict:
    s = fn.spec
    return {"type": "function", "function": {"name": tool_name(s.id), "description": s.description[:1000],
                                             "parameters": s.input_schema}}
