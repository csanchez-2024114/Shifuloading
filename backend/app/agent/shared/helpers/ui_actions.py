"""Catalogo de acciones de interfaz (UI actions): lo que la interfaz puede abrir o mostrar cuando el usuario lo pide.

Es DATO: coleccion `ui_actions_catalog` en Mongo, un documento por accion. Agregar una accion es agregar un documento
(`python scripts/seed_ui_actions.py` carga la lista de prueba); el codigo no cambia. Contrato con el frontend:
doc/agente/UI_ACTIONS.md.

    {"id": "open_workflows", "status": "active", "source": "user",
     "label": {"es": "Ver mis workflows", "en": "See my workflows"},     # o un texto solo
     "description": "<en ingles: que abre y cuando sirve; el modelo elige con este texto>",
     "params": {"app": "<en ingles: que va en este parametro>"},
     "plans": ["pro", "business"],   # opcional: solo esos planes; sin el campo, todos
     "confirm": true}                # opcional: cambia algo; el frontend DEBE pedir confirmacion antes de ejecutarla

- source "user": la puede pedir el usuario; `semantic_intake` la elige leyendo el catalogo y viaja en `ui_actions` como
  {"type": "ui_action", "id", "label", "params", "confirm"}. El frontend decide que hace con cada `id`.
- source "system": la arma el codigo desde el estado (`chat._build_ui_actions`: connect_app, render_workflow,
  open_trigger). Estan en el catalogo para que la lista sea una sola; el modelo no las ve.

El agente solo ofrece lo que el cliente declara soportar (`ui_supported` en el cuerpo del chat): asi nunca promete un
boton que ese frontend no sabe pintar. Un cliente que no declara nada no recibe acciones pedidas por el usuario.
"""
import logging

from cachetools import TTLCache

from app.core.mongo import mongo_manager

logger = logging.getLogger(__name__)

COLLECTION = "ui_actions_catalog"
MAX_PER_TURN = 2
_cache: TTLCache = TTLCache(maxsize=1, ttl=600)  # 10 min, como la personalidad: se edita en Mongo sin reiniciar
_LANG = {"spanish": "es", "english": "en", "portuguese": "pt", "french": "fr", "german": "de", "italian": "it"}


async def get_catalog() -> list[dict]:
    if "all" not in _cache:
        db = mongo_manager.db
        try:
            _cache["all"] = [] if db is None else await db[COLLECTION].find({"status": "active"}, {"_id": 0}).to_list(length=200)
        except Exception as exc:  # sin catalogo el turno sigue: solo no hay acciones pedidas por el usuario
            logger.warning("[ui_actions] catalog not loaded: %s", exc)
            return []
    return _cache["all"]


async def offer(supported, plan: str | None) -> list[str]:
    """Ids que ESTE turno puede ofrecer: en el catalogo, que el usuario puede pedir, que su plan permite y que el cliente
    declaro saber pintar. `supported` viene del cliente: se valida (lista de textos cortos, tope 200)."""
    wanted = {s for s in (supported if isinstance(supported, list) else [])[:200] if isinstance(s, str) and len(s) <= 64}
    return [a["id"] for a in await get_catalog()
            if a.get("source") == "user" and a.get("id") in wanted and (not a.get("plans") or plan in a["plans"])]


def offered(catalog: list[dict], ids) -> list[dict]:
    allowed = set(ids or [])
    return [a for a in catalog if a.get("source") == "user" and a.get("id") in allowed]


def prompt_block(actions: list[dict]) -> str:
    """Lo que ve semantic_intake. Sin acciones que ofrecer no se pinta nada."""
    rows = [a for a in actions if a.get("id") and a.get("description")]
    if not rows:
        return ""
    lines = "\n".join(
        f"- {a['id']} — {a['description']}"
        + (f" Params: {', '.join(f'{k} ({v})' for k, v in a['params'].items())}." if a.get("params") else "")
        for a in rows)
    return (
        "## UI actions (screens the interface can open for the user)\n"
        f"{lines}\n"
        "If the user explicitly asks to SEE, OPEN, SHOW, GO TO or START one of these, add to your JSON: "
        '"ui_actions": [{"id": "<id from this list>", "params": {}}]. Each description says when it applies. Only for an '
        "explicit request; a question about the topic, or asking you to DO something to their data (create, pause, "
        "connect, send), is not one. Otherwise omit the field.\n\n"
    )


def _label(spec: dict, language: str | None) -> str:
    """El texto del boton en el idioma del usuario si el catalogo lo trae; si no, espanol, y si no, el primero."""
    label = spec.get("label")
    if not isinstance(label, dict):
        return str(label or spec["id"])
    code = _LANG.get((language or "").strip().lower(), "es")
    return str(label.get(code) or label.get("es") or next(iter(label.values()), spec["id"]))


def resolve(requested, actions: list[dict], language: str | None = None) -> list[dict]:
    """Lo que pidio el modelo, validado contra lo ofrecido: id inventado o no ofrecido se descarta, parametros no
    declarados se quitan, tope por turno."""
    known = {a["id"]: a for a in actions if a.get("id")}
    out: list[dict] = []
    for item in requested if isinstance(requested, list) else []:
        spec = known.get((item or {}).get("id")) if isinstance(item, dict) else None
        if not spec or any(o["id"] == spec["id"] for o in out):
            continue
        params = item.get("params") if isinstance(item.get("params"), dict) else {}
        out.append({"type": "ui_action", "id": spec["id"], "label": _label(spec, language),
                    "params": {k: str(v)[:200] for k, v in params.items() if k in (spec.get("params") or {}) and v not in (None, "")},
                    "confirm": bool(spec.get("confirm"))})
    return out[:MAX_PER_TURN]
