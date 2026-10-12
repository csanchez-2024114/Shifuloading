"""
platform_context — lo que la plataforma realmente ofrece, para que el agente guíe con hechos y no con consejos genéricos.

Dos fuentes (v0.8.0: el registro viejo de BigTools ya no se ofrece):
  - catalog_apps (Mongo)          apps que el usuario puede conectar, por categoría
  - registro de funciones nuevo   app/functions: 324 hoy, ~15,000 mañana. NO se inyectan en bloque: se buscan por
                                  relevancia contra lo que dice el usuario y entran pocas (decisión del proyecto).

El responder lo recibe como contexto y el evaluador lo usa para verificar que la respuesta se apoya en la plataforma.
"""
import logging
import re

from cachetools import TTLCache

from app.agent.shared.helpers.identity_loader import get_agent_identity, get_agent_personality
from app.core.mongo import mongo_manager

logger = logging.getLogger(__name__)

_DEFAULT_RULE = "Recommend ONLY what is listed here; if something is not listed, say honestly that it is not available instead of improvising."

_TOP_FUNCTIONS = 6
_DESC_CHARS = 170
_cache: TTLCache = TTLCache(maxsize=4, ttl=600)
_STOP = set(
    "that this with from have your what when then them they will would could should about into just like want need "
    "para pero como esto esta este esos esas cual cuando donde quiero necesito tengo hacer algo mis tus sus por con "
    "una uno unos unas del los las que mas muy ya".split()
)


def _alias(name_api: str) -> str:
    """google_sheets -> sheets: el usuario (y semantic_intake) suelen nombrar la app por su sufijo."""
    return name_api.split("_")[-1]


def _terms(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-záéíóúñ0-9]{4,}", (text or "").lower()) if w not in _STOP}


async def _catalog() -> list[dict]:
    if "catalog" not in _cache:
        db = mongo_manager.db
        rows = []
        if db is not None:
            rows = await db["catalog_apps"].find(
                {"active": {"$ne": False}, "visible": {"$ne": False}}, {"_id": 0, "name": 1, "nameApi": 1, "category": 1}
            ).to_list(length=200)
        _cache["catalog"] = [r for r in rows if r.get("name") and r.get("nameApi")]  # descarta documentos incompletos
    return _cache["catalog"]


def _functions() -> list[tuple[str, str, str, set[str]]]:
    """(id, verbo, descripcion, terminos) de cada funcion registrada; se carga una vez. Falla en silencio: es contexto, no requisito."""
    if "functions" not in _cache:
        out = []
        try:
            from app.functions import registry
            registry.load_all()
            for f in registry.list_functions():
                s = f.spec
                out.append((s.id, str(getattr(s.verb, "value", s.verb)), s.description,
                            _terms(s.id.replace(".", " ").replace("_", " ") + " " + s.description)))
        except Exception:
            logger.exception("[platform_context] no se pudo cargar el registro de funciones; sigo solo con catalogo y acciones")
        _cache["functions"] = out
    return _cache["functions"]


# Marcas de las lineas "- <App>: ..." de apps con las que hoy no se puede hacer nada. unavailable_apps() las lee de vuelta
# (el juez de afirmaciones las usa como verdad): si cambias el texto, cambia solo estas constantes.
_SOON = "coming soon"
_NOT_YET = "not integrated yet"
_UNAVAILABLE_LINE = re.compile(rf"^- (?P<app>[^:\n]+): (?:.*; )?(?:{_SOON} —|{_NOT_YET} —).*$", re.M)


def unavailable_apps(context: str) -> dict[str, str]:
    """{nombre en minusculas: linea completa} de las apps sin nada que hacer, sacado del bloque PLATFORM KNOWLEDGE."""
    return {m["app"].strip().lower(): m.group(0) for m in _UNAVAILABLE_LINE.finditer(context or "")}


def app_has_actions(app: str) -> bool:
    """True si la plataforma puede HACER algo con la app (acciones de workflow o funciones registradas). Una app sin
    nada es, para el usuario, una app no disponible: no se le ofrece conectarla (conectarla no le serviria de nada)."""
    key = (app or "").lower()
    return any(fid.split(".", 1)[0] in {key, _alias(key)} for fid, _, _, _ in _functions())


def apps_by_capability() -> dict[str, list[str]]:
    """Apps con las que HOY se puede hacer algo, segun el registro: {"write": [...], "read": [...]}."""
    verbs: dict[str, set] = {}
    for fid, verb, _, _ in _functions():
        verbs.setdefault(fid.split(".", 1)[0], set()).add(verb)
    return {"write": sorted(a for a, v in verbs.items() if v != {"read"}),
            "read": sorted(a for a, v in verbs.items() if v == {"read"})}


def app_capability(app: str) -> str:
    """Lo que la plataforma puede hacer HOY con la app, segun el registro (no segun el modelo):
    "none" (no existe o aun no tiene nada), "read" (solo lee) o "write" (tambien envia, crea, publica...).
    Acepta el nombre visible ("Google Sheets") o el nameApi. Lo usa el juez de afirmaciones para decidir en codigo."""
    key = "_".join((app or "").lower().split())
    keys = {key, _alias(key)}
    verbs = {verb for fid, verb, _, _ in _functions() if fid.split(".", 1)[0] in keys}
    return "none" if not verbs else "read" if verbs == {"read"} else "write"


async def unavailable_catalog_names() -> set[str]:
    """Nombres (tal como estan en el catalogo) de las apps con las que hoy no se puede hacer nada. El juez los usa para que
    la respuesta no OFREZCA una app no disponible como alternativa ("te aviso por Slack") aunque el usuario no la nombro.
    Conservan las mayusculas: "Teams" u "Outlook" en minusculas son palabras comunes en ingles."""
    return {c["name"] for c in await _catalog() if app_capability(c["nameApi"]) == "none"
            and app_capability(c["name"]) == "none"}


def _relevant_functions(query: str, apps_named: set[str]) -> list[tuple[str, str, str]]:
    q = _terms(query)
    scored = []
    for fid, verb, desc, terms in _functions():
        score = len(q & terms) + (3 if fid.split(".", 1)[0] in apps_named else 0) * bool(q & terms)
        if score:
            scored.append((score, fid, verb, desc))
    scored.sort(key=lambda x: -x[0])
    return [(fid, verb, desc) for _, fid, verb, desc in scored[:_TOP_FUNCTIONS]]


async def build_platform_context(state) -> str:
    """Bloque 'PLATFORM KNOWLEDGE' para este turno. Cadena vacía si no hay nada que decir.
    Es contexto auxiliar: cualquier fallo aqui se registra y el turno sigue sin el bloque."""
    try:
        return await _build(state)
    except Exception:
        logger.exception("[platform_context] no se pudo construir el contexto de plataforma")
        return ""


async def _build(state) -> str:
    catalog = await _catalog()
    connected = set((state.get("user_connected_apps") or {}).keys())
    # El flujo de requisitos va de semantic_intake a req_investigator sin pasar por auth_validator, asi que
    # user_connected_apps llega vacio: sin esto el agente decia "conecta Google Sheets" con la cuenta ya conectada.
    connected |= {r.get("app") for r in (state.get("validation_reports") or [])
                  if r.get("source") == "auth" and r.get("status") == "ok" and r.get("app")}
    last_human = next((m for m in reversed(state.get("messages") or []) if getattr(m, "type", "") == "human"), None)
    query = f"{state.get('structured_prompt') or ''} {getattr(last_human, 'content', '') or ''}"
    low = query.lower()
    named = {a.lower() for a in (state.get("apps_involved") or [])}
    if state.get("req_level") is not None:  # mientras dura el flujo de requisitos, las apps de la automatizacion siguen en juego
        named |= {a.lower() for a in (state.get("req_apps_scope") or [])}
    named |= {c["nameApi"] for c in catalog if c.get("nameApi") and (c["nameApi"].replace("_", " ") in low or c["name"].lower() in low)}

    # El proposito sale de la identidad y la regla de la personalidad (ambos editables en Mongo): al pivotar a otro
    # dominio cambian los datos, no este archivo.
    identity = await get_agent_identity()
    knowledge = (await get_agent_personality()).get("platform_knowledge") or {}
    rule = knowledge.get("rule") or _DEFAULT_RULE
    lines = ["## PLATFORM KNOWLEDGE (ground truth for this turn)", " ".join(filter(None, [identity.get("purpose"), rule]))]
    if knowledge.get("triggers"):  # como arranca un workflow (dato de la personalidad)
        lines.append("How a workflow can start: " + knowledge["triggers"])
    if knowledge.get("notices"):  # como se entera el usuario de lo que pasa con sus workflows (dato de la personalidad)
        lines.append("How the user is told about their workflows: " + knowledge["notices"])
    if knowledge.get("files"):  # que archivos puede adjuntar el usuario al chat (dato de la personalidad)
        lines.append("Files in the chat: " + knowledge["files"])
    if knowledge.get("support"):  # a donde remitir precios, planes, cobros (dato de la personalidad)
        lines.append("Support (prices, plans, charges, account problems): " + knowledge["support"])

    if catalog:
        by_cat: dict[str, list[str]] = {}
        for c in catalog:
            mark = "*" if c["nameApi"] in connected else ""
            # "(coming soon)": la plataforma aun no hace nada con ella; sin esta marca el agente la sugeria como alternativa
            soon = "" if app_has_actions(c["nameApi"]) else " (coming soon)"
            by_cat.setdefault(c.get("category") or "Other", []).append(c["name"] + mark + soon)
        lines.append("Apps on the platform (* = already connected by this user; (coming soon) = being built, nothing can be done with it yet): "
                     + " | ".join(f"{cat}: {', '.join(names)}" for cat, names in by_cat.items()))

    # Lo que NO existe tambien hay que decirlo: sin esto el modelo (y el evaluador) deducen que "Instagram" puede publicar
    # solo porque la app esta en el catalogo, cuando su unica funcion es leer el perfil.
    caps = []
    for c in catalog:
        if c["nameApi"] not in named and _alias(c["nameApi"]) not in named:
            continue
        fns =[(fid, verb) for fid, verb, _, _ in _functions() if fid.split(".", 1)[0] == c["nameApi"]]
        reads = [fid for fid, verb in fns if verb == "read"]
        writes = [fid for fid, verb in fns if verb != "read"]
        parts = []
        if fns:
            parts.append(f"{len(reads)} read function(s)" + (f" and {len(writes)} write function(s)" if writes else
                         " and NO write functions: it cannot post, send, create or modify anything"))
            if not writes:
                parts.append("read: " + ", ".join(reads[:6]))
        if not fns:
            # En terminos del usuario: "se puede conectar pero no tiene acciones" es un dato interno y el modelo lo repetia
            parts.append(_SOON + " — the team is building it; nothing can be done with it for the user yet (it "
                         "cannot read, send, create or start anything), so do not ask the user to connect it")
        if c["nameApi"] in connected:  # un modelo chico seguia pidiendo "conecta tu cuenta" aunque la app llevara el asterisco
            parts.insert(0, "the user has ALREADY connected their account: never ask them to connect it")
        caps.append(f"- {c['name']}: " + "; ".join(parts))
    known = {c["nameApi"] for c in catalog} | {_alias(c["nameApi"]) for c in catalog}
    for app in sorted(named - known):
        # En terminos del usuario: "todavia no esta, seguimos sumando integraciones" (no un portazo de "no existe")
        caps.append(f"- {app}: {_NOT_YET} — the team keeps adding new integrations, so it may be possible later (no "
                    "dates, no guarantees); today it cannot be connected, used as a trigger or used for any action")
    if caps:
        lines.append("What the apps mentioned in this request can and cannot do:\n" + "\n".join(caps))

    funcs = _relevant_functions(query, named)
    if funcs:
        lines.append("Platform functions most relevant to this request (id [type] — what it does):\n" + "\n".join(
            f"- {fid} [{verb}] — {desc[:_DESC_CHARS].rstrip()}{'…' if len(desc) > _DESC_CHARS else ''}" for fid, verb, desc in funcs))
    return "\n\n".join(lines) if len(lines) > 2 else ""
