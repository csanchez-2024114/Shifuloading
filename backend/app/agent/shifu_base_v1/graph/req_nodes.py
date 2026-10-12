"""
req_investigator — crear un workflow por chat en DOS etapas (antes eran 6 niveles que iban y venian).

Por que: con 6 niveles el "no" del nivel 4 volvia al 3 y repetia el plan, las mejoras se preguntaban una por una y el
responder reescribia cada pregunta. Ahora el usuario ve UN solo mensaje de confirmacion con todo.

req_level (REQ_GATHER / REQ_CONFIRM en graph/state.py):
  1 → GATHER  : marca las apps conectadas; si una falta, pide conectarla (botones) y espera.
                Arma el plan; si faltan datos, pregunta SOLO eso, una pregunta por turno (cola).
                Si el horario no se entiende, lo pregunta una vez. Sin nada pendiente pasa a CONFIRM en el mismo turno.
  4 → CONFIRM : guarda el workflow (status "creating"), lo simula y manda UN mensaje: plan en palabras llanas,
                resultado de la simulacion, cuando correra y "¿Lo activo así?". Al turno siguiente clasifica la respuesta:
                  confirmar → _finalize (activa + programa/webhook) · cambiar → descarta el borrador y vuelve a GATHER
                  con la correccion · cancelar → descarta el borrador · poco claro → repite la pregunta una vez.

req_pending_questions: req_investigator_node saca una por turno sin llamar al LLM antes de correr la etapa
(_queue_or_ask). Cada turno donde este nodo habla marca req_relay=True: el responder debe entregar ese mensaje tal cual.
"""

import asyncio
import json
import logging
import re
import time
from datetime import datetime, timezone
from itertools import zip_longest

from bson import ObjectId
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import ValidationError

from config import Config
from app.agent.shifu_base_v1.graph.state import REQ_CONFIRM, REQ_GATHER, ShifuState
from app.agent.shared.helpers.catalog_cache import get_catalog_apps
from app.agent.shared.helpers.chrono_parser import parse_schedule
from app.agent.shared.helpers.platform_context import app_capability, app_has_actions, apps_by_capability
from app.agent.shared.nodes.auth_validator import auth_validator_node
from app.agent.shared.nodes.catalog_checker import catalog_checker_node
from app.agent.shared.nodes.semantic_intake import _CANCEL_PHRASES
from app.core.constants import Collections, ConnectedAccountStatus
from app.core.mongo import mongo_manager
from app.functions.select import connected_apps, function_pool, norm, search_functions, single_account_id
from app.services.scheduled_task_service import create_scheduled_task
from app.utils.events import publish_user_event
from app.workers.workflow_executor import WorkflowExecutor
from app.services.workflow_service import (
    add_step_to_workflow,
    create_workflow,
    set_webhook_trigger,
    set_workflow_frequency,
    update_workflow_metrics,
    update_workflow_status,
    WorkflowLimitExceededError,
    WorkflowAppsLimitExceededError,
    WORKFLOWS,
)

logger = logging.getLogger(__name__)

_llm = ChatOpenAI(
    model="gpt-4o-mini", temperature=0, max_tokens=800, timeout=30
).with_retry(stop_after_attempt=3, wait_exponential_jitter=True)

# El plan con funciones lista candidatas y argumentos: 800 tokens de salida se quedaban cortos.
# Modo JSON: sin el, el modelo escribia valores sin comillas (<due_date>) y el plan entero se perdia al parsear.
_plan_llm = ChatOpenAI(
    model="gpt-4o-mini", temperature=0, max_tokens=1500, timeout=45,
    model_kwargs={"response_format": {"type": "json_object"}},
).with_retry(stop_after_attempt=3, wait_exponential_jitter=True)

_USABLE = ConnectedAccountStatus.USABLE

# Mirrors the frontend's WorkflowNodeThemeKey (hyper-shifu-app/src/features/workflows/
# components/nodes/nodeDefaults.ts) — the LLM picks one of these per step in
# _build_plan's node_type field; anything else (hallucinated value) falls back to "ia".
_VALID_NODE_TYPES = {"inicio", "ia", "decision", "personalizacion", "bucle", "notificacion", "fin", "grafica"}

_YES = {"si", "sí", "yes", "dale", "sale", "ok", "okay", "claro", "perfecto", "correcto", "afirmativo", "confirmo",
        "adelante", "hazlo", "activalo", "actívalo", "activarlo", "listo"}
_NO = {"no", "nope", "negativo", "cancelar"}


# ── Small shared helpers ──────────────────────────────────────────────────────

def _last_user_text(state: ShifuState) -> str:
    for msg in reversed(state.get("messages") or []):
        if isinstance(msg, HumanMessage):
            return msg.content if isinstance(msg.content, str) else str(msg.content)
    return ""


def _history_snippet(state: ShifuState, n: int = 8) -> str:
    out = []
    for msg in (state.get("messages") or [])[-n:]:
        role = "User" if isinstance(msg, HumanMessage) else "Shifu"
        text = msg.content if isinstance(msg.content, str) else str(msg.content)
        out.append(f"{role}: {text[:300]}")
    return "\n".join(out)


def _parse_json(raw: str) -> dict:
    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, ValueError):
        return {}


def _parse_json_list(raw: str) -> list[str]:
    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(q).strip() for q in data if q and str(q).strip()]
    except (json.JSONDecodeError, ValueError):
        pass
    return []


def _queue_or_ask(questions: list[str], **extra_fields) -> dict | None:
    """Queue all but the first question; return the first as structured_prompt —
    the level does NOT advance (req_level is intentionally absent from the
    return) while questions remain. Returns None when there's nothing to ask,
    signalling the caller to proceed with its own resolution logic."""
    questions = [q for q in (questions or []) if q]
    if not questions:
        return None
    first, rest = questions[0], questions[1:]
    return {"req_pending_questions": rest or None, "structured_prompt": first, **extra_fields}


async def _app_reports(state: ShifuState, apps: list[str]) -> list[dict]:
    """Los mismos validadores del resto del grafo (catalogo + cuenta conectada), uno por app: asi este flujo
    tambien emite un boton de conectar por cada app que falte, en vez de mandar al usuario a Configuracion."""
    apps = [a for a in dict.fromkeys(apps or []) if a]
    if not apps or not state.get("user_id"):
        return []
    s = {**state, "apps_involved": apps, "catalog_query_mode": "validate"}
    try:
        cat, auth = await asyncio.gather(catalog_checker_node(s), auth_validator_node(s))
    except Exception as exc:
        logger.error("[req_investigator] app validation failed: %s", exc)
        return []
    return [*(cat.get("validation_reports") or []), *(auth.get("validation_reports") or [])]


def _connected_apps(state: ShifuState, reports: list[dict]) -> dict:
    """user_connected_apps que ven los turnos siguientes (platform_context marca con * las apps conectadas): este flujo no
    pasa por auth_validator, y semantic_intake no reinicia el campo, asi que basta escribirlo aqui."""
    found = {r["app"]: [(r.get("account") or {}).get("email") or (r.get("account") or {}).get("account_id") or ""]
             for r in reports if r.get("source") == "auth" and r.get("status") == "ok" and r.get("app")}
    return {**(state.get("user_connected_apps") or {}), **found}


async def _limit_exceeded_result(exc: Exception, user_id: str) -> dict:
    """Shared handler for WorkflowLimitExceededError / WorkflowAppsLimitExceededError —
    reuses the plan_limit_exceeded WS event / upgrade modal every other limit path
    already publishes (see usePlanLimitExceeded.ts)."""
    if isinstance(exc, WorkflowLimitExceededError):
        await publish_user_event(user_id, {
            "type": "plan_limit_exceeded",
            "payload": {
                "exceeded_limits": ["workflows"],
                "usage": {
                    "tokens_used": 0, "tokens_limit": 0, "apps_used": 0, "apps_limit": 0,
                    "workflows_used": exc.limit, "workflows_limit": exc.limit,
                },
            },
        })
        msg = (
            f"Tu plan permite hasta {exc.limit} workflows activos y ya llegaste a ese límite. "
            "Desactiva alguno o mejora tu plan para crear uno nuevo."
        )
    else:
        await publish_user_event(user_id, {
            "type": "plan_limit_exceeded",
            "payload": {
                "exceeded_limits": ["apps"],
                "usage": {
                    "tokens_used": 0, "tokens_limit": 0, "apps_used": exc.limit, "apps_limit": exc.limit,
                    "workflows_used": 0, "workflows_limit": 0,
                },
            },
        })
        msg = (
            f"Tu plan permite hasta {exc.limit} apps distintas dentro de un mismo workflow. "
            "Simplifica este workflow o mejora tu plan para combinar más apps en uno solo."
        )
    return {
        "req_level": None, "req_pending_questions": None, "req_level_entered": None,
        "req_workflow_id": None, "structured_prompt": msg,
    }


async def _extract_apps_scope(state: ShifuState) -> list[str]:
    """Extract distinct app/service names mentioned so far in the conversation."""
    seed = state.get("req_apps_scope") or state.get("apps_involved") or []
    history = _history_snippet(state)
    system = (
        "Given this conversation about setting up an automation, list ONLY the "
        "distinct app/service names needed (e.g. gmail, slack, google_sheets). "
        "Use lowercase, underscore-separated canonical-style keys. "
        # "dime cuanto vale el bitcoin" en el mismo mensaje hacia que el flujo dijera "Bitcoin todavia no esta disponible".
        "An app is software the user would connect or act in. NEVER list a topic, currency, product or piece of "
        "information the user merely asks about (bitcoin, the dollar, the weather, an iPhone, a football match). "
        "Return ONLY a JSON array of strings — empty array if none are clear yet."
    )
    try:
        resp = await _llm.ainvoke([
            SystemMessage(content=system),
            HumanMessage(content=f"Conversation:\n{history}"),
        ])
        extracted = _parse_json_list(resp.content or "")
    except Exception as exc:
        logger.error("[req_investigator] L2 app-extraction LLM failed: %s", exc)
        extracted = []
    merged = list(dict.fromkeys([*(a.lower().replace(" ", "_") for a in seed), *extracted]))
    return merged


async def _catalog_auth_failures(apps_scope: list[str], user_id: str) -> list[str]:
    failures: list[str] = []
    catalog = set(await get_catalog_apps() or [])
    if not catalog:
        return failures
    db = mongo_manager.db
    for app in apps_scope:
        if not app:
            continue
        if app not in catalog:
            failures.append(f"'{app}' no está disponible en el catálogo de Shifu")
            continue
        docs = await db[Collections.USER_CONNECTED_ACCOUNTS].find(
            {"user_id": user_id, "provider": app.lower()}
        ).to_list(length=5)
        usable = [d for d in docs if d.get("status") in _USABLE]
        if not usable:
            failures.append(
                f"No tienes conectada una cuenta de '{app}' (el botón para conectarla está en pantalla)."
            )
    return failures


# ── Plan con funciones reales ─────────────────────────────────────────────────

_MAX_PLAN_ROUNDS = 2      # rondas de preguntas por datos faltantes antes de dejar fuera el paso incompleto
# Funciones que no tienen sentido en un workflow que corre solo. gmail.drafts.send envia un borrador que YA existe: un
# workflow solo podria conocer su id creandolo en el paso anterior, y eso es gmail.messages.send con un paso de mas (el
# modelo lo armaba asi aun con la descripcion advirtiendolo; hoja_nueva_aviso). En el modo act si se ofrece.
# ponytail: lista en codigo; si crece, pasarla a un campo de la ficha.
_NOT_FOR_PLANS = {"gmail.drafts.send"}
_MAX_CANDIDATES = 30      # funciones que se le muestran al modelo (cabe en el prompt y se mantiene la precision de eleccion)
_MAX_MISSING_QUESTIONS = 5

# Con funciones reales: el modelo ELIGE entre candidatas y llena argumentos; el codigo valida todo (_check_plan).
_PLAN_RULES_FN = (
    "You are a workflow architect. Today is {today}. Based on the conversation, extract a structured plan that a machine "
    "will RUN, so each step must be one real function from CANDIDATE FUNCTIONS. Return ONLY valid JSON (no markdown):\n"
    '{"goal":"<one-line goal>","apps_needed":["<app>"],'
    '"trigger_type":"webhook|email|schedule|manual","trigger_event":"<event>",'
    '"trigger_filter":"<only for email: Gmail search query>",'
    '"steps":[{"order":1,"function_id":"<id copied from CANDIDATE FUNCTIONS>","args":{"<input name>":"<value>"},'
    '"description":"<what this step does, plain words>",'
    '"node_type":"<inicio|ia|decision|personalizacion|bucle|notificacion|fin|grafica>"}],'
    '"metrics":[{"key":"<metric_name>","source":"step_N","field":"<json_path>","label":"<Human label>"}]}\n'
    "Rules:\n"
    "- function_id MUST be copied exactly from CANDIDATE FUNCTIONS. Never invent one. If no candidate does what a step "
    "needs, leave that step out.\n"
    "- args: use ONLY the input names listed for that function (after 'in:'; a trailing * means required). Fill them with "
    "what the user said (names, emails, sheet ranges, dates, subjects, text). NEVER invent ids, emails, file names or any "
    "value the user did not give: omit that input instead (the system will ask the user for it).\n"
    "- An OPTIONAL input (no trailing *) the user did not mention is left out: the function uses its own default (a sheet "
    "range left out reads the whole first tab). If the user gave no cell range, there must be NO range arg at all.\n"
    "- One step per action the user asked for, with the function that COMPLETES it. Do not add a preparatory step: to "
    "send, notify or tell someone, use the function that sends; one that only saves a draft is for when the user asks "
    "for a draft.\n"
    "- Write goal and every description in the language the user writes in.\n"
    "- An arg may use the result of an EARLIER step: write \"{{step_N.field}}\" where N is that step's order and field is "
    "one of its 'out:' fields. To reach inside a list or object use dots and [n]: \"{{step_1.rows[0][0]}}\" is the first "
    "cell of the first row. When the template is the whole value it keeps the field's type (e.g. a list). It can also "
    "sit inside text (\"Total: {{step_1.total}}\"). Never reference a later step.\n"
    "- If trigger_type is webhook, an arg may use data sent to the webhook: \"{{trigger.<field>}}\" (e.g. \"{{trigger.amount}}\").\n"
    "- trigger_type is email when the workflow must start each time an email ARRIVES in the user's Gmail (\"when I get an "
    "email from...\"). Put which emails start it in trigger_filter, in Gmail search syntax built only from what the user "
    "said (\"from:ana@x.com\", \"subject:invoice\", \"has:attachment\"); empty means any new email. The system finds that email by itself, so the "
    "plan must NOT contain gmail.messages.search (nor any step that looks for the email): the FIRST step already has it "
    "as \"{{trigger.sender}}\", \"{{trigger.subject}}\", \"{{trigger.snippet}}\" (preview of the text), "
    "\"{{trigger.date}}\" and \"{{trigger.id}}\". Example: \"when an email from ana@x.com arrives, add its subject to my "
    "sheet\" is trigger_type email, trigger_filter \"from:ana@x.com\" and ONE step that appends [[\"{{trigger.subject}}\"]].\n"
    "- Do NOT add a step for the trigger itself (a schedule or an incoming event): it goes in trigger_type/trigger_event.\n"
    "- For an app listed under APPS WITHOUT FUNCTIONS, write an old-style step with no function_id: "
    '{"order":N,"app":"<app>","action":"<action>","description":"<what it does>","node_type":"<type>"}.\n'
    "node_type is the step's role in the flow, not its app: ia=uses an LLM to analyze or generate, "
    "decision=conditional logic, personalizacion=tailored content, bucle=repeats or waits, "
    "notificacion=sends an outbound message/alert, fin=final outcome, grafica=dashboard of results.\n"
    "metrics: ONLY include this array if the workflow has a REAL quantifiable result worth tracking (count, amount, score). "
    "source is 'step_N' (that step's order) and field is a key of that step's out: fields."
)


def _ptype(prop: dict) -> str:
    """Tipo corto de un campo del esquema JSON (suficiente para que el modelo sepa que valor poner)."""
    if prop.get("enum"):
        return "|".join(str(v) for v in prop["enum"][:6])
    if prop.get("type"):
        t = prop["type"]
        t = "/".join(t) if isinstance(t, list) else str(t)
        if t == "array":
            item = (prop.get("items") or {}).get("type")
            return f"array<{item}>" if item else "array"
        return t
    alts = [a.get("type") for a in prop.get("anyOf") or [] if isinstance(a, dict) and a.get("type") not in (None, "null")]
    return "/".join(dict.fromkeys(str(a) for a in alts)) or "object"


def _fields_line(schema: dict, mark_required: bool, limit: int = 10) -> str:
    props = (schema or {}).get("properties") or {}
    required = set((schema or {}).get("required") or [])
    names = sorted(props, key=lambda n: (n not in required, n))[:limit]
    return ", ".join(f"{n}{'*' if mark_required and n in required else ''}:{_ptype(props[n])}" for n in names) or "(none)"


def _candidate_line(fn) -> str:
    """Una linea por funcion: id, verbo, primera frase de la descripcion, entradas (* = obligatoria) y salidas."""
    s = fn.spec
    first = re.split(r"(?<=[.!?])\s", s.description.strip(), maxsplit=1)[0][:160]
    return (f"- {s.id} [{s.verb.value}] {first} | in: {_fields_line(s.input_schema, True)} "
            f"| out: {_fields_line(s.output_schema, False, 8)}")


async def _plan_candidates(state: ShifuState, query: str) -> tuple[dict, list[str]]:
    """Funciones que el plan puede usar (cerco: apps conectadas y nombradas, lectura/crear/actualizar, sin las que exigen
    una persona) y las apps nombradas que se quedan sin funciones (esas conservan el paso estilo viejo)."""
    db, user_id = mongo_manager.db, state.get("user_id")
    if db is None or not user_id:
        return {}, []
    scope = [a for a in [*(state.get("req_apps_scope") or []), *(state.get("apps_involved") or [])] if a]
    try:
        connected = await connected_apps(db, user_id)
        named = {norm(a) for a in scope}
        apps = {a for a in connected if norm(a) in named} if named else connected
        pool = {fid: fn for fid, fn in function_pool(apps).items() if fid not in _NOT_FOR_PLANS}  # delete ya queda fuera (VERBS_DEFAULT); lo irreversible lo confirma el usuario en el plan
        # 30 entre las apps: con 18, al crecer Gmail a 10 funciones gmail.messages.send (que la busqueda rankea ultima
        # para "mandame... por Gmail") quedaba fuera y el plan armaba borrador -> enviar borrador (v0.8.1).
        per_app = max(3, 30 // max(len(apps), 1))
        ranked: list[list[str]] = []
        for app in sorted({fn.spec.app for fn in pool.values()}):
            sub = {fid: fn for fid, fn in pool.items() if fn.spec.app == app}
            try:
                ranked.append(await search_functions(sub, query, {app}, per_app))
            except Exception as exc:  # sin embeddings el plan sigue, con las primeras de la app
                logger.warning("[req_investigator] busqueda de funciones fallo (%s): %s", app, exc)
                ranked.append(sorted(sub)[:per_app])
    except Exception as exc:
        logger.error("[req_investigator] no se pudieron calcular las candidatas: %s", exc)
        return {}, []
    ids = [fid for group in zip_longest(*ranked) for fid in group if fid]  # una por app a la vez, para repartir el cupo
    offered: dict = {}
    for fid in dict.fromkeys(ids):
        if len(offered) >= _MAX_CANDIDATES:
            break
        offered[fid] = pool[fid]
    served = {norm(fn.spec.app) for fn in offered.values()}
    return offered, [a for a in dict.fromkeys(scope) if norm(a) not in served]


def _user_query(state: ShifuState, adjustment: str | None) -> str:
    """Texto para buscar funciones: lo que dijo el usuario (sin las respuestas de Shifu, que meterian ruido)."""
    said = [m.content if isinstance(m.content, str) else str(m.content)
            for m in (state.get("messages") or [])[-14:] if isinstance(m, HumanMessage)]
    return "\n".join([state.get("req_goal") or "", *(s[:300] for s in said), adjustment or ""]).strip()[:1500]


def _clean_args(fn, raw) -> dict:
    """Solo entradas que la funcion declara y con valor: un "" o None inventado por el modelo debe verse como FALTANTE."""
    props = (fn.spec.input_schema or {}).get("properties") or {}
    if not isinstance(raw, dict):
        return {}
    # Un marcador inventado ("<list_id>", "<due_date>") tambien es FALTANTE: el modelo lo escribe en vez de admitir que no
    # tiene el dato (eval_workflow_plan, dos_apps_tareas).
    def placeholder(v):
        return isinstance(v, str) and v.strip().startswith("<") and v.strip().endswith(">")
    return {k: v for k, v in raw.items()
            if k in props and v is not None and v != "" and v != [] and not placeholder(v)}


def _arg_errors(fn, args: dict) -> list[dict]:
    """Errores de validar los argumentos con el modelo de la funcion. Un valor con plantilla {{...}} no se rechaza: no se
    conoce hasta correr. Lo demas (p. ej. un campo obligatorio que el usuario nunca dio) se devuelve para preguntarlo."""
    props = (fn.spec.input_schema or {}).get("properties") or {}
    try:
        fn.input_model.model_validate(args)
        return []
    except ValidationError as exc:
        errors = exc.errors()
    except Exception as exc:  # un validador propio que lance otra cosa: igual se pregunta, no se guarda a ciegas
        errors = [{"loc": (), "type": "value_error", "msg": str(exc)}]
    out, seen = [], set()
    for e in errors:
        loc = e.get("loc") or ()
        field = str(loc[0]) if loc else ""
        if field and "{{" in json.dumps(args.get(field), default=str):
            continue
        kind = "missing" if e.get("type") == "missing" else "invalid"
        if (field, kind) in seen:
            continue
        seen.add((field, kind))
        out.append({"field": field, "kind": kind, "msg": str(e.get("msg", ""))[:160],
                    "field_desc": str((props.get(field) or {}).get("description", ""))[:200]})
    return out


# Lo que un paso puede leer del correo que disparo el workflow (campos de MessageRow de gmail.messages.search).
_EMAIL_TRIGGER_FIELDS = {"id", "thread_id", "sender", "to", "subject", "date", "snippet"}
_ANY_TEMPLATE = re.compile(r"\{\{\s*([^}]*?)\s*\}\}")
_KNOWN_ROOT = re.compile(r"(step_\d+|trigger|state|item)\b")  # las raices que WorkflowExecutor sabe resolver
_TRIGGER_REF = re.compile(r"\{\{\s*trigger\.?([A-Za-z_]*)")


_A1_RANGE = re.compile(r"^(?:'?[^!']+'?!)?(\$?[A-Za-z]{1,3}\$?\d*(?::\$?[A-Za-z]{1,3}\$?\d*)?)$")


def _unsaid_range(field: str, value, said: str) -> bool:
    """Un rango de hoja (A1:B1) que el usuario nunca escribio es un invento del modelo: dos reglas de prompt no lo
    quitaron (v0.6.6, v0.7.3) y un filtro general se llevaba valores legitimos como q="is:unread". Este es angosto: solo
    campos llamados `range`, solo celdas con numero de fila (A1:B1, A1:B) y solo si no aparecen en lo que dijo el usuario.
    Columnas enteras (Ventas!A:B) se dejan: es una lectura razonable de "lee mi hoja Ventas", no un invento."""
    if "range" not in field.lower() or not isinstance(value, str) or not said:
        return False
    m = _A1_RANGE.match(value.strip())
    cells = m.group(1).replace("$", "").upper() if m else ""
    return any(c.isdigit() for c in cells) and cells not in said.upper()


def _check_plan(plan: dict, offered: dict, give_up: bool = False, said: str = "") -> dict:
    """Nunca se confia en el modelo: cada paso se revisa en codigo.
    - function_id fuera de las candidatas -> el paso se descarta y se avisa.
    - argumentos validados con el modelo de la funcion -> lo que falte va a plan["missing"] (se pregunta al usuario).
    - {{step_N...}} solo puede apuntar a un paso anterior que SI se conservo (si no, se descarta en cascada).
    - paso estilo viejo (sin function_id) solo para apps que no tienen candidatas.
    give_up=True (ya se pregunto dos veces): el paso incompleto se deja fuera en vez de volver a preguntar."""
    served = {norm(fn.spec.app) for fn in offered.values()}
    kept, notes, missing, kept_orders = [], [], [], set()
    for raw in plan.get("steps") or []:
        if not isinstance(raw, dict):
            continue
        try:
            order = int(raw.get("order"))
        except (TypeError, ValueError):
            order = 0
        if order < 1 or order in kept_orders:
            order = max(kept_orders, default=0) + 1
        desc = str(raw.get("description") or raw.get("action") or "").strip()
        fid = raw.get("function_id")
        if not fid:
            if norm(raw.get("app")) in served:  # app con funciones reales: un paso inventado no se acepta
                notes.append(f"No pude armar el paso «{desc}»: no encontré una acción real para hacerlo.")
                continue
            # v0.8.0: una app sin funciones aun no se puede usar; antes se guardaba un paso del sistema viejo.
            notes.append(f"Dejé fuera el paso «{desc}»: {raw.get('app') or 'esa app'} todavía no está disponible en la plataforma.")
            continue
        fn = offered.get(fid)
        if fn is None:
            notes.append(f"No pude armar el paso «{desc}»: esa acción no existe todavía.")
            continue
        args = _clean_args(fn, raw.get("args"))
        if not give_up:  # si ya se pregunto dos veces se acepta el rango supuesto: el usuario lo ve en la confirmacion
            args = {k: v for k, v in args.items() if not _unsaid_range(k, v, said)}
        # Una plantilla que el ejecutor no conoce ("{{spreadsheet_id}}", "{{user_email}}") es el modelo esquivando un dato
        # que no tiene: se quita para que se pregunte (eval_workflow_plan, faltan_datos, v0.8.1).
        args = {k: v for k, v in args.items()
                if all(_KNOWN_ROOT.match(t) for t in _ANY_TEMPLATE.findall(json.dumps(v, default=str)))}
        if plan.get("trigger_type") == "email":
            # El correo que disparo trae campos fijos: uno inventado ("{{trigger.total}}") se quita para que se pregunte.
            args = {k: v for k, v in args.items()
                    if set(_TRIGGER_REF.findall(json.dumps(v, default=str))) <= _EMAIL_TRIGGER_FIELDS}
        elif plan.get("trigger_type") != "webhook":
            # Sin webhook no hay datos del disparador: "{{trigger.spreadsheet_id}}" es el modelo esquivando un dato que
            # no tiene. Se quita para que se pregunte (eval_workflow_plan, faltan_datos).
            args = {k: v for k, v in args.items() if "{{trigger" not in json.dumps(v, default=str).replace(" ", "")}
        refs = {int(n) for n in re.findall(r"\{\{\s*step_(\d+)", json.dumps(args, default=str))}
        if any(n not in kept_orders or n >= order for n in refs):
            notes.append(f"Dejé fuera el paso «{desc}»: dependía del resultado de un paso que no se pudo armar.")
            continue
        errors = _arg_errors(fn, args)
        # Un valor invalido en un campo OPCIONAL es un invento del modelo (file_type="*"): se quita y la funcion usa su
        # valor por defecto, en vez de preguntarle al usuario por algo que nunca pidio (eval_workflow_plan, drive_a_correo).
        required = set((fn.spec.input_schema or {}).get("required") or [])
        guessed = [e["field"] for e in errors if e["kind"] == "invalid" and e["field"] in args and e["field"] not in required]
        if guessed:
            for field in guessed:
                args.pop(field)
            errors = _arg_errors(fn, args)
        if errors and give_up:
            notes.append(f"Dejé fuera el paso «{desc}»: faltaban datos para hacerlo.")
            continue
        missing += [{**e, "order": order, "step": desc} for e in errors]
        kept.append({"order": order, "function_id": fid, "function_version": fn.spec.version, "app": fn.spec.app,
                     "action": fid, "args": args, "description": desc, "node_type": raw.get("node_type")})
        kept_orders.add(order)
    return {**plan, "steps": kept, "notes": notes, "missing": missing}


def _previous_view(plan: dict) -> dict:
    """El plan anterior en compacto: el modelo conserva lo ya sabido (valores, horario) en vez de re-derivarlo de la charla."""
    return {"goal": plan.get("goal"), "trigger_type": plan.get("trigger_type"), "trigger_event": plan.get("trigger_event"),
            **({"trigger_filter": plan["trigger_filter"]} if plan.get("trigger_filter") else {}),
            "steps": [{k: s.get(k) for k in ("order", "function_id", "app", "args", "description", "node_type") if s.get(k)}
                      for s in plan.get("steps") or []]}


async def _build_plan(state: ShifuState, adjustment: str | None = None, give_up: bool = False,
                      previous: dict | None = None) -> dict:
    history = _history_snippet(state, n=14)
    human = f"Conversation:\n{history}"
    if previous and previous.get("steps"):
        human += ("\n\nPREVIOUS PLAN (keep every step, value and the schedule the user did not change; copy its args "
                  "as they are):\n" + json.dumps(_previous_view(previous), ensure_ascii=False, default=str)[:2500])
    if adjustment:
        human += f"\n\nThe user wants this adjustment to the previous plan: {adjustment}"
    if language := (state.get("user_language") or "").strip():
        # Un usuario en ingles recibia un workflow que mandaba "Total de la hoja" / "El total es: ..." (idiomas, v0.9.11).
        human += (f"\n\nThe user writes in {language}: write in {language} every text the automation will send or "
                  "create (email subject and body, messages, titles, names).")
    offered, no_functions = await _plan_candidates(state, _user_query(state, adjustment))
    if offered:
        system = _PLAN_RULES_FN.replace("{today}", time.strftime("%Y-%m-%d"))
        human += "\n\nCANDIDATE FUNCTIONS (the only ones you may use):\n" + "\n".join(_candidate_line(f) for f in offered.values())
        if no_functions:
            human += "\n\nAPPS WITHOUT FUNCTIONS: " + ", ".join(no_functions)
    else:
        # Ninguna app con funciones: no hay nada real que planear (antes se armaba un plan del sistema viejo).
        if not no_functions:
            # No nombro ninguna app ni tiene una conectada: decir "las apps que mencionas" era falso (prefs_dificiles).
            return {"steps": [], "notes": ["El usuario no nombró ninguna app y todavía no tiene ninguna conectada, así que "
                                           "aún no hay con qué armarlo."]}
        return {"steps": [], "notes": [f"Todavía no hay acciones disponibles para {', '.join(no_functions)}."]}
    try:
        resp = await _plan_llm.ainvoke([SystemMessage(content=system), HumanMessage(content=human)])
        plan = _parse_json(resp.content or "")
    except Exception as exc:
        logger.error("[req_investigator] L3 plan-build LLM failed: %s", exc)
        plan = {}
    if plan:
        plan = _check_plan(plan, offered, give_up, said=_user_query(state, adjustment))
        for app in no_functions:  # que el plan diga lo que quedo fuera aunque el modelo no haya escrito ese paso
            if not any(app.lower() in n.lower() for n in plan["notes"]):
                plan["notes"].append(_not_yet(app))
    return plan


async def _missing_questions(missing: list[dict]) -> list[str]:
    """Una pregunta por dato faltante, en palabras simples. El modelo solo redacta; que preguntar lo decidio el codigo."""
    items = missing[:_MAX_MISSING_QUESTIONS]
    fallback = [f"Para el paso «{m['step']}» me falta un dato: {m['field_desc'] or m['field'] or m['msg']}. ¿Me lo compartes?"
                for m in items]
    system = (
        "The user is building an automation and some values are missing or wrong. For each item write ONE short question "
        "asking the user for that value, in the language of the conversation (Spanish if unsure), in plain words. Never "
        "mention technical field names, ids, JSON or functions. Return ONLY a JSON array of strings, same order and "
        "length as the items."
    )
    lines = "\n".join(f"- step: {m['step']}; needed: {m['field_desc'] or m['field']}; problem: {m['kind']} {m['msg']}"
                      for m in items)
    try:
        resp = await _llm.ainvoke([SystemMessage(content=system), HumanMessage(content=lines)])
        asked = _parse_json_list(resp.content or "")
    except Exception as exc:
        logger.error("[req_investigator] L3 missing-question LLM failed: %s", exc)
        asked = []
    return asked if len(asked) == len(items) else fallback


_TEMPLATE_RE = re.compile(r"\{\{\s*step_(\d+)[^}]*\}\}")
_TRIGGER_RE = re.compile(r"\{\{\s*trigger[^}]*\}\}")


def _plan_view(req_plan: dict) -> dict:
    """Lo que ve el redactor del resumen: app, que hace y valores clave. Sin ids de funcion ni nombres de campo."""
    steps = []
    for s in req_plan.get("steps") or []:
        values = {k: _TRIGGER_RE.sub("(dato que llegue al webhook)",
                                     _TEMPLATE_RE.sub(lambda m: f"(lo que devuelva el paso {m.group(1)})", str(v)))[:80]
                  for k, v in (s.get("args") or {}).items()}
        steps.append({"order": s.get("order"), "app": str(s.get("app") or "").replace("_", " "),
                      "what": s.get("description") or s.get("action") or "", **({"values": values} if values else {})})
    return {"goal": req_plan.get("goal"), "trigger": req_plan.get("trigger_type"), "when": req_plan.get("trigger_event"),
            "steps": steps, **({"left_out": req_plan["notes"]} if req_plan.get("notes") else {})}


# ── Guardar el borrador y simular ─────────────────────────────────────────────

def _format_dry_run_summary(trace: dict) -> str:
    # El ejecutor devuelve los pasos en "trace"; "step_trace" queda de respaldo.
    steps = trace.get("trace") or trace.get("step_trace") or []
    lines = ["Simulé tu workflow paso a paso:"]
    if trace.get("error"):
        lines.append("(la simulación no pudo correr)")
    for t in steps:
        name = t.get("name") or t.get("action") or f"Paso {t.get('order')}"
        if t.get("type") == "condition":
            state_txt = "condición cumplida" if t.get("passed") else "condición no cumplida"
            lines.append(f"- {name}: {state_txt}")
        elif t.get("error"):
            lines.append(f"- {name}: no se pudo simular ({t['error']})")
        elif t.get("function_id"):
            lines.append(f"- {name}: simulado OK con datos de ejemplo")
        else:
            lines.append(f"- {name}: {t.get('mock_result', 'simulado OK')}")
    if not steps:
        lines.append("(sin pasos para simular)")
    return "\n".join(lines)


def _step_doc(s: dict, accounts: dict) -> dict:
    """Paso del plan -> paso guardado en el workflow. Con function_id el ejecutor lo corre por app.functions: `config` son
    los argumentos de la funcion (nodeType se queda ahi porque el front lo lee; el ejecutor lo ignora como argumento).
    account_id solo si la app tiene una unica cuenta; si no, queda None y el ejecutor pide elegir en vez de adivinar."""
    node_type = s.get("node_type")
    if node_type not in _VALID_NODE_TYPES:
        node_type = "ia"
    order = s.get("order", 1)
    fid = s.get("function_id")
    if not fid:
        return {
            "order": order, "name": s.get("action", f"Paso {order}"),
            "description": s.get("description", ""), "app": s.get("app", ""),
            "action": s.get("action", ""), "account_id": s.get("account_id", ""),
            "config": {"nodeType": node_type}, "metadata": {},
        }
    doc = {
        "order": order, "name": (s.get("description") or fid)[:80], "description": s.get("description", ""),
        "app": s.get("app", ""), "action": fid, "function_id": fid,
        "account_id": accounts.get(s.get("app")),
        "config": {**(s.get("args") or {}), "nodeType": node_type}, "metadata": {"nodeType": node_type},
    }
    if s.get("function_version"):
        doc["function_version"] = s["function_version"]  # fija la version con que se planeo
    return doc


async def _single_accounts(db, user_id: str, steps: list[dict]) -> dict:
    """app -> account_id cuando el usuario tiene una sola cuenta de esa app (solo para pasos con function_id)."""
    out: dict = {}
    for app in {s.get("app") for s in steps if s.get("function_id") and s.get("app")}:
        try:
            out[app] = await single_account_id(db, user_id, app)
        except Exception as exc:
            logger.warning("[req_investigator] no se pudo resolver la cuenta de %s: %s", app, exc)
    return out


async def _persist_and_simulate(state: ShifuState) -> dict:
    """Guarda el borrador (status="creating": inactivo, no cuenta contra la cuota, ver _ACTIVE_STATUSES) con sus pasos y lo
    simula con WorkflowExecutor.execute_dry_run(). Devuelve solo lo que hay que recordar; el mensaje lo arma _confirm_message."""
    req_plan = state.get("req_plan") or {}
    workflow_id = state.get("req_workflow_id")
    user_id = state.get("user_id") or ""

    raw_steps = req_plan.get("steps") or []
    step_docs: list[dict] = []
    deployed_steps: list[dict] = state.get("req_deployed_steps") or []
    try:
        db = mongo_manager.db
        accounts = await _single_accounts(db, user_id, raw_steps)
        step_docs = [_step_doc(s, accounts) for s in raw_steps]
        if not workflow_id:
            goal = state.get("req_goal") or req_plan.get("goal") or "Workflow automatizado"
            workflow_id = await create_workflow(
                user_id=user_id, user_email=state.get("user_email") or "",
                name=goal[:100], description="Creado via chat.",
                conversation_id=state.get("conversation_id") or "", db=db,
            )
            deployed_steps = []
            for step_dict in step_docs:
                await add_step_to_workflow(workflow_id, step_dict, db)
                deployed_steps.append(step_dict)

            raw_metrics = req_plan.get("metrics") or []
            if raw_metrics:
                max_order = max((s.get("order", 1) for s in raw_steps), default=1)
                valid_metrics = []
                for m in raw_metrics:
                    key, source, field, label = m.get("key", ""), m.get("source", ""), m.get("field", ""), m.get("label", "")
                    step_match = re.match(r"step_(\d+)", source)
                    if key and source and field and step_match and 1 <= int(step_match.group(1)) <= max_order:
                        valid_metrics.append({"key": key, "source": source, "field": field, "label": label or key})
                if valid_metrics:
                    await update_workflow_metrics(workflow_id, valid_metrics, db)
    except (WorkflowLimitExceededError, WorkflowAppsLimitExceededError) as exc:
        return await _limit_exceeded_result(exc, user_id)

    fake_run = {
        "_id": "dry-run", "user_id": user_id, "workflow_id": workflow_id,
        "workflow_name": (state.get("req_goal") or req_plan.get("goal") or "")[:100],
        "steps": step_docs,  # con function_id y argumentos: el ejecutor simula con el ejemplo de la ficha
    }
    try:
        trace = await WorkflowExecutor(fake_run, mongo_manager.db, dry_run=True).execute_dry_run()
    except Exception as exc:
        logger.error("[req_investigator] dry run failed: %s", exc)
        trace = {"dry_run": True, "trace": [], "steps_simulated": 0, "error": str(exc)[:200]}
    return {"req_workflow_id": workflow_id, "req_deployed_steps": deployed_steps, "req_dry_run_result": trace}


async def _discard_draft(user_id: str, workflow_id: str | None) -> None:
    """Borra el borrador. El filtro status="creating" garantiza que nunca se toca un workflow ya activo."""
    if not workflow_id:
        return
    try:
        await mongo_manager.db[WORKFLOWS].delete_one({"_id": ObjectId(workflow_id), "user_id": user_id, "status": "creating"})
    except Exception as exc:
        logger.warning("[req_investigator] no se pudo descartar el borrador %s: %s", workflow_id, exc)


# ── Horario ───────────────────────────────────────────────────────────────────

_DIAS_ES = {"1": "lunes", "2": "martes", "3": "miércoles", "4": "jueves", "5": "viernes", "6": "sábado", "0": "domingo"}
_TIME_HINT_RE = re.compile(r"\d|medianoche|midnight|mediod[ií]a|noon")
_ASK_SCHEDULE = ("Casi listo. ¿Qué día y a qué hora quieres que corra? "
                 "Por ejemplo: \"cada lunes a las 9:00\" o \"todos los días a las 18:00\".")


def _cron_es(cron: str, fallback: str | None = None) -> str:
    """El cron en español llano. chrono_parser describe en inglés ("Every Monday at 9:00") y el usuario habla español."""
    try:
        minute, hour, dom, mon, dow = cron.split()
    except ValueError:
        return fallback or cron
    if cron == "0 * * * *":
        return "cada hora"
    if minute.isdigit() and hour.isdigit() and mon == "*":
        at = f"{int(hour)}:{int(minute):02d}"
        if dom == "*" and dow in _DIAS_ES:
            return f"cada {_DIAS_ES[dow]} a las {at}"
        if dom == "*" and dow == "*":
            return f"todos los días a las {at}"
        if dom.isdigit() and dow == "*":
            return f"el día {dom} de cada mes a las {at}"
    return fallback or cron


def _resolve_schedule(state: ShifuState, adjustment: str | None = None) -> dict | None:
    """{"cron","human"} del horario del workflow, o None si no hay uno entendible.
    El turno de confirmacion ("si") casi nunca trae horario, asi que se lee el del plan y, si le falta la hora, el de lo que
    el usuario dijo antes (de lo contrario "cada lunes" se programaba a medianoche). Un horario de ritmo ("cada hora") no
    necesita hora."""
    ctx = state.get("schedule_context") or {}
    if ctx.get("cron"):
        return {"cron": ctx["cron"], "human": ctx.get("human")}
    said = [m.content if isinstance(m.content, str) else str(m.content)
            for m in reversed(state.get("messages") or []) if isinstance(m, HumanMessage)]
    event = state.get("req_trigger_event") or ""
    # "cada lunes" + la respuesta a "¿a que hora?" ("a las 18"): ninguna parsea sola, juntas si.
    joined = f"{event} {said[0]}" if event and said and not _TIME_HINT_RE.search(event.lower()) else ""
    first = None
    for text in [joined, event, adjustment or "", *said]:
        parsed = parse_schedule(text) if text else None
        if not parsed:
            continue
        found = {"cron": parsed["cron"], "human": parsed.get("human")}
        if _TIME_HINT_RE.search(text.lower()) or parsed.get("type") == "hourly":
            return found
        first = first or {**found, "no_time": True}  # "cada lunes" sin hora: parse_schedule cae a medianoche
    return first


def _when_fact(plan: dict, schedule: dict | None, tz: str | None) -> dict:
    """Cuando correra, como hecho para el redactor. Solo programado y webhook corren solos; lo demas es a mano."""
    ttype = plan.get("trigger_type")
    if ttype == "schedule" and schedule and schedule.get("cron"):
        return {"kind": "schedule", "description": _cron_es(schedule["cron"], schedule.get("human")),
                "english": schedule.get("human"), "cron": schedule["cron"], "timezone": tz or "UTC"}
    if ttype == "webhook":
        return {"kind": "webhook", "note": "it runs each time something sends data to the workflow's private webhook "
                                           "address; the address is given once it is active"}
    if ttype == "email":
        return {"kind": "email", "emails_that_start_it": plan.get("trigger_filter") or "any new email in the inbox",
                "filter": plan.get("trigger_filter") or "",
                "note": "it runs once for each NEW email that arrives in the user's Gmail and matches; the inbox is "
                        "checked every few minutes, so it is not instant; emails that arrived before activating do not count"}
    note = "it runs only when the user starts it by hand from their workflows panel"
    if ttype == "schedule":
        note = "the schedule could not be understood, so it will NOT run by itself; " + note
    return {"kind": "manual", "note": note}


# ── CONFIRM: un solo mensaje con todo ─────────────────────────────────────────

_CONFIRM_SYSTEM = (
    "You write the confirmation message of an automation the user asked to create. You receive FACTS as JSON. Write ONE "
    "short message in the language of the conversation (Spanish if unsure), friendly, plain words: no JSON, no ids, no "
    "technical field names, no {{templates}} (say «el resultado del paso 1» in words). Order:\n"
    "1) The plan, step by step: for each step the app, what it does and its key values (sheet, range, recipient, subject, text).\n"
    "2) What the simulation showed, in ONE short sentence; if a step could not be simulated, say so plainly.\n"
    "3) When it will run, from 'when' (say it in the user's language and mention the time zone; for a webhook, an "
    "incoming email or a manual run say so plainly).\n"
    "4) End with ONE question asking whether to activate it like this.\n"
    "Use ONLY the facts given: never add steps, values, promises or claims about what the platform can or cannot do. If "
    "'left_out' is present, say plainly what could not be included. Ask nothing else."
)


_FILTER_PART = re.compile(r'(\w+):("[^"]*"|\S+)|("[^"]*"|\S+)')
_FILTER_ES = {"from": "de {}", "to": "para {}", "subject": "con asunto «{}»", "label": "con la etiqueta {}"}


def _filter_es(q: str) -> str:
    """El filtro de Gmail en palabras: 'from:ana@x.com subject:factura' -> 'de ana@x.com, con asunto «factura»'.
    Un operador que no se conoce se deja tal cual (mejor verlo crudo que decir algo falso)."""
    out = []
    for key, value, word in _FILTER_PART.findall(q or ""):
        value = value.strip('"')
        if key == "has" and value == "attachment":
            out.append("con archivo adjunto")
        elif key in _FILTER_ES:
            out.append(_FILTER_ES[key].format(value))
        elif key:
            out.append(f"{key}:{value}")
        else:
            out.append("que mencione «" + word.strip('"') + "»")
    return ", ".join(out)


def _when_es(when: dict) -> str:
    if when["kind"] == "schedule":
        return f"Va a correr {when['description']} (zona horaria: {when['timezone']})."
    if when["kind"] == "webhook":
        return "Va a correr cada vez que algo envíe datos a su dirección de webhook (te la doy al activarlo)."
    if when["kind"] == "email":
        which = _filter_es(when.get("filter") or "")
        return (f"Va a correr con cada correo nuevo que llegue a tu Gmail{' ' + which if which else ''}; reviso la "
                "bandeja cada pocos minutos.")
    extra = " No entendí el horario que querías, así que no correrá solo." if "NOT run by itself" in when["note"] else ""
    return "Lo ejecutas tú a mano desde tu panel de workflows." + extra


async def _confirm_message(state: ShifuState, plan: dict, schedule: dict | None) -> str:
    when = _when_fact(plan, schedule, state.get("user_timezone"))
    sim = _format_dry_run_summary(state.get("req_dry_run_result") or {})
    view = _plan_view(plan)
    facts = json.dumps({"plan": view, "simulation": sim, "when": when}, ensure_ascii=False)[:3500]
    try:
        resp = await _llm.ainvoke([SystemMessage(content=_CONFIRM_SYSTEM), HumanMessage(content=facts)],
                                  config={"tags": ["req_confirm_message"]})
        text = str(resp.content or "").strip()
        if text:
            return text if "?" in text[-160:] else f"{text}\n\n¿Lo activo así?"
    except Exception as exc:
        logger.error("[req_investigator] confirm-message LLM failed: %s", exc)
    steps = "\n".join(
        f"{i}. {s['app']}: {s['what']}" + (f" ({'; '.join(s['values'].values())})" if s.get("values") else "")
        for i, s in enumerate(view["steps"], 1))
    notes = "".join(f"\n{n}" for n in plan.get("notes") or [])
    return f"Esto es lo que armé:\n{steps}{notes}\n\n{sim}\n\n{_when_es(when)}\n\n¿Lo activo así?"


async def _present(state: ShifuState, plan: dict, schedule: dict | None) -> dict:
    """Pasa a CONFIRM: guarda y simula el borrador y devuelve el mensaje unico. Lo que se muestra (plan y horario) queda en
    el estado: es exactamente lo que se activa despues."""
    known = {
        "req_plan": plan, "req_goal": plan.get("goal", ""),
        "req_apps_scope": plan.get("apps_needed") or state.get("req_apps_scope") or [],
        "req_trigger_type": plan.get("trigger_type"), "req_trigger_event": plan.get("trigger_event"),
        "req_schedule": schedule, "req_plan_rounds": None, "req_level_entered": None, "req_schedule_asked": None,
        "req_adjustment": None, "req_confirm_unclear": None, "req_pending_questions": None,
    }
    saved = await _persist_and_simulate({**state, **known})
    if "structured_prompt" in saved:  # limite del plan: ya trae su mensaje y cierra el flujo
        return saved
    message = await _confirm_message({**state, **known, **saved}, plan, schedule)
    return {**known, **saved, "req_level": REQ_CONFIRM, "structured_prompt": message}


# ── GATHER ────────────────────────────────────────────────────────────────────

def _not_yet(app: str) -> str:
    return (f"{app.replace('_', ' ').title()} todavía no está disponible en Shifu (el equipo sigue sumando integraciones), "
            "así que esa parte queda fuera por ahora.")


def _read_only(app: str) -> str:
    """El hecho sale del registro de funciones, no del modelo: sin el, el flujo pedia conectar Instagram para "publicar
    cada lunes" y no decia que ahi solo se puede leer (escenario app_solo_lectura)."""
    return (f"Ojo: con {app.replace('_', ' ').title()} por ahora solo puedo leer datos; todavía no puedo enviar, publicar "
            "ni modificar nada ahí.")


def _connect_message(failures: list[str]) -> str:
    return ("Antes de armarlo necesito esto:\n" + "\n".join(f"- {f}" for f in failures)
            + "\nCuando lo hayas conectado, avísame y sigo con tu workflow.")


async def _gather(state: ShifuState) -> dict:
    """Apps conectadas → plan → datos faltantes → (mismo turno) CONFIRM. Pregunta solo lo que falta."""
    user_id = state.get("user_id") or ""
    adjustment = state.get("req_adjustment")  # correccion que dejo CONFIRM; se aplica al plan anterior
    plan = state.get("req_plan") or {}
    verified: dict = {}

    # 1. Apps. Se revisa en la primera visita y en cada cambio (la correccion puede traer una app nueva).
    if adjustment or state.get("req_preflight_passed") is not True:
        apps = await _extract_apps_scope(state)
        # Una app con la que aun no se puede hacer nada (Slack) no se pide conectar: conectarla no serviria. Se dice que
        # todavia no esta y el workflow se arma con el resto (escenario varias_apps_slack, v0.8.0).
        usable = [a for a in apps if app_has_actions(a)]
        failures = await _catalog_auth_failures(usable, user_id)
        reports = await _app_reports(state, usable)
        connected = _connected_apps(state, reports) or None
        if failures:
            # Un solo mensaje (los botones de conectar salen de validation_reports) y no se avanza hasta que se conecte.
            return {"req_apps_scope": apps, "req_preflight_passed": False, "req_preflight_failures": failures,
                    "validation_reports": reports, "user_connected_apps": connected, "req_level_entered": None,
                    "req_adjustment": adjustment, "req_compose": True,
                    "structured_prompt": "\n".join([_connect_message(failures),
                                                    *(_read_only(a) for a in usable if app_capability(a) == "read"),
                                                    *(_not_yet(a) for a in apps if a not in usable)])}
        verified = {"req_apps_scope": apps, "req_preflight_passed": True, "req_preflight_failures": [],
                    "user_connected_apps": connected}
        state = {**state, "req_apps_scope": apps}

    # 2. Plan. Se rearma si hay una correccion, si no hay plan o si se acaba de preguntar lo que faltaba.
    rounds = state.get("req_plan_rounds") or 0
    if adjustment or not plan or state.get("req_level_entered") == REQ_GATHER:
        new = await _build_plan(state, adjustment, give_up=rounds >= _MAX_PLAN_ROUNDS, previous=plan or None)
        missing = new.pop("missing", None) or []
        if missing:
            # El plan a medias se guarda: al vaciarse la cola se rearma con las respuestas sin perder lo que ya estaba.
            queued = _queue_or_ask(await _missing_questions(missing), req_level_entered=REQ_GATHER, req_plan=new or None,
                                   req_plan_rounds=rounds + 1, req_adjustment=adjustment, **verified)
            if queued:
                return queued
        plan = new
    if not plan.get("steps"):
        notes = " ".join(plan.get("notes") or [])
        msg = ("No pude armar un plan con lo que me contaste. " + notes).strip()
        # Hechos, no mensaje final (req_compose): el responder propone con apps reales de la plataforma y respeta lo que
        # sabe del usuario; el texto fijo era un callejon sin salida ("cuentame mas") para quien pidio "decide tu".
        # La lista de apps va en los hechos: sin ella proponia Google Calendar y Telegram y el juez lo hacia rehacer
        # 3 veces (4 intentos por turno).
        usable = apps_by_capability()
        return {**verified, "req_plan": None, "req_plan_rounds": None, "req_level_entered": None, "req_adjustment": None,
                "req_compose": True,
                "structured_prompt": msg + " Falta saber qué apps usar y qué debe pasar: propón UNA opción concreta o "
                                           "pregunta lo mínimo. Solo se puede proponer con estas apps (ninguna otra "
                                           f"funciona hoy). Pueden leer y escribir: {', '.join(usable['write'])}. Solo "
                                           f"leer: {', '.join(usable['read'])}."}

    if plan.get("trigger_type") == "email" and "gmail" not in await connected_apps(mongo_manager.db, user_id):
        # El disparador lee la bandeja: sin Gmail conectado no hay nada que vigilar (aunque ningun paso use Gmail).
        return {**verified, "req_plan": plan, "req_preflight_passed": False, "req_level_entered": None,
                "req_adjustment": None, "validation_reports": await _app_reports(state, ["gmail"]),
                "structured_prompt": _connect_message(["Conecta tu cuenta de Gmail: la necesito para ver los correos que llegan."])}

    # 3. Horario. Sin uno entendible se pregunta una vez; si sigue sin entenderse se confirma como "a mano", sin atrapar al usuario.
    schedule = None
    if plan.get("trigger_type") == "schedule":
        schedule = _resolve_schedule({**state, "req_trigger_event": plan.get("trigger_event")}, adjustment)
        if (not schedule or schedule.get("no_time")) and (adjustment or not state.get("req_schedule_asked")):
            return {**verified, "req_plan": plan, "req_goal": plan.get("goal", ""), "req_trigger_type": "schedule",
                    "req_trigger_event": plan.get("trigger_event"), "req_schedule_asked": True, "req_plan_rounds": None,
                    "req_level_entered": None, "req_adjustment": None, "structured_prompt": _ASK_SCHEDULE}

    # 4. Nada falta: CONFIRM en este mismo turno.
    return {**verified, **await _present({**state, **verified}, plan, schedule)}


# ── CONFIRM: la respuesta del usuario ─────────────────────────────────────────

_CONFIRM_CLASSIFIER = (
    "The assistant showed the user an automation (plan, simulation, when it runs) and asked whether to activate it. "
    "Classify the user's reply:\n"
    "- \"confirm\": clear agreement to activate it exactly as shown (sí, dale, actívalo, ok, adelante).\n"
    "- \"change\": they want it different (another value, hour, day, app, step, recipient) or add a correction, even if the "
    "reply also contains a yes or a no.\n"
    "- \"cancel\": they do not want it activated or created (no, mejor no, déjalo).\n"
    "- \"unclear\": anything else (a question, something ambiguous). A yes only confirms if it answers THIS question.\n"
    "Reply ONLY with JSON: {\"decision\": \"confirm\"|\"change\"|\"cancel\"|\"unclear\"}."
)


def _last_ai_text(state: ShifuState) -> str:
    for msg in reversed(state.get("messages") or []):
        if isinstance(msg, AIMessage):
            return msg.content if isinstance(msg.content, str) else str(msg.content)
    return ""


async def _classify_confirm(text: str, last_assistant: str) -> str:
    """confirm|change|cancel|unclear. Si el clasificador falla es "unclear": activar por error programa correos de verdad,
    repetir una pregunta cuesta un mensaje."""
    plain = (text or "").strip().lower().strip(" .,!¡¿?")
    if not plain:
        return "unclear"
    if plain in _YES:
        return "confirm"
    if plain in _NO or (len(plain.split()) <= 6 and any(p in plain for p in _CANCEL_PHRASES)):
        return "cancel"  # un "no" a secas a "¿lo activo así?" es no activarlo
    try:
        resp = await _llm.ainvoke(
            [SystemMessage(content=_CONFIRM_CLASSIFIER),
             HumanMessage(content=f"Assistant's last message: {last_assistant[-1200:] or '(none)'}\n\nUser's reply: {text[:500]}")],
            config={"tags": ["confirm_classifier"]})
        decision = _parse_json(str(resp.content or "")).get("decision")
        if decision in ("confirm", "change", "cancel"):
            return decision
    except Exception as exc:
        logger.warning("[req_investigator] confirm classification failed: %s — not confirmed", exc)
    return "unclear"


_ENDED = {
    "req_level": None, "req_pending_questions": None, "req_level_entered": None, "req_plan": None, "req_workflow_id": None,
    "req_deployed_steps": None, "req_dry_run_result": None, "req_schedule": None, "req_adjustment": None,
    "req_confirm_unclear": None, "req_schedule_asked": None, "req_plan_rounds": None, "req_preflight_passed": None,
}


async def _confirm_stage(state: ShifuState) -> dict:
    workflow_id = state.get("req_workflow_id")
    if not workflow_id or state.get("req_dry_run_result") is None:
        return {"req_level": REQ_GATHER}  # no hay nada mostrado que confirmar (estado viejo): se reune de nuevo
    user_id = state.get("user_id") or ""
    text = _last_user_text(state)
    decision = await _classify_confirm(text, _last_ai_text(state))
    logger.info("[req_investigator] confirm decision=%s wf=%s", decision, workflow_id)

    if decision == "confirm":
        return await _finalize(state)
    if decision == "change":
        # El borrador viejo se descarta (no se parchea): _present guarda uno nuevo con el plan corregido.
        await _discard_draft(user_id, workflow_id)
        return {"req_level": REQ_GATHER, "req_adjustment": text, "req_level_entered": None, "req_confirm_unclear": None,
                "req_workflow_id": None, "req_deployed_steps": None, "req_dry_run_result": None, "req_schedule": None}
    if decision == "cancel":
        await _discard_draft(user_id, workflow_id)
        return {**_ENDED, "structured_prompt": "Listo, no activé nada y descarté el borrador. "
                                               "Si quieres armarlo de otra forma, cuéntame y lo preparo de nuevo."}
    if (state.get("req_confirm_unclear") or 0) < 1:
        return {"req_confirm_unclear": 1, "structured_prompt": "No estoy seguro de haberte entendido. ¿Lo activo así como te lo "
                                                               "mostré? Dime «sí» para activarlo o qué quieres cambiar."}
    await _discard_draft(user_id, workflow_id)  # segunda vez sin entender: no se deja al usuario atrapado ni se activa a ciegas
    return {**_ENDED, "structured_prompt": "No logré entender tu respuesta, así que no activé nada y descarté el borrador. "
                                           "Si quieres que lo arme de nuevo, cuéntamelo otra vez."}


# ── Activar ───────────────────────────────────────────────────────────────────

async def _finalize(state: ShifuState) -> dict:
    """El usuario confirmo: activa el workflow y deja listo su disparador (horario o webhook)."""
    workflow_id = state.get("req_workflow_id")
    req_plan = state.get("req_plan") or {}
    deployed_steps = state.get("req_deployed_steps") or []
    user_id = state.get("user_id") or ""
    user_email = state.get("user_email") or ""
    goal = state.get("req_goal") or req_plan.get("goal") or "Workflow automatizado"
    trigger_type = state.get("req_trigger_type") or "manual"

    webhook_url: str | None = None
    trigger_summary: str | None = None
    when_text = "Se ejecuta a mano desde tu panel de workflows."
    try:
        db = mongo_manager.db

        if trigger_type == "webhook" and workflow_id:
            token = await set_webhook_trigger(workflow_id, db)
            if token:
                webhook_url = f"{Config.BACKEND_BASE_URL}/api/v1/webhooks/{token}"
                trigger_summary = f"Webhook listo — envía un POST a {webhook_url}"
                when_text = trigger_summary
        elif trigger_type == "email" and workflow_id:
            # El vigilante (app/workers/email_trigger_loop.py) busca desde AHORA: los correos viejos no disparan nada.
            now = datetime.now(timezone.utc)
            q = str(req_plan.get("trigger_filter") or "").strip()
            await db[WORKFLOWS].update_one({"_id": ObjectId(workflow_id), "user_id": user_id}, {"$set": {
                "trigger_type": "email",
                "email_trigger": {"q": q, "account_id": await single_account_id(db, user_id, "gmail"),
                                  "since": now, "seen_ids": [], "next_poll_at": now}}})
            trigger_summary = ("Correrá con cada correo nuevo que llegue a tu Gmail"
                               + (f" {_filter_es(q)}" if q else "") + ". Reviso la bandeja cada pocos minutos.")
            when_text = trigger_summary
        elif trigger_type == "schedule" and workflow_id:
            # Lo que se le mostro al usuario manda; el resto es respaldo para estados sin req_schedule.
            sched = state.get("req_schedule") or _resolve_schedule(state) or {}
            cron, tz = sched.get("cron"), state.get("user_timezone") or None
            if cron:
                await create_scheduled_task(
                    user_id=user_id, user_email=user_email, workflow_id=workflow_id,
                    name="scheduled_workflow", schedule_type="cron",
                    # timezone: el cron se lee en la zona del usuario ("lunes 9:00" = 9:00 de ahi); sin zona, UTC.
                    schedule_config={"cron_expression": cron, **({"timezone": tz} if tz else {})}, db=db,
                )
                trigger_summary = f"Programado: {_cron_es(cron, sched.get('human'))} (zona horaria: {tz or 'UTC'})"
                when_text = trigger_summary
            else:
                # Sin horario entendible no se atrapa al usuario ni se afirma que correra solo.
                await set_workflow_frequency(
                    workflow_id=workflow_id, frequency_type="custom", every_seconds=None,
                    frequency_label=state.get("req_trigger_event") or "", db=db,
                )
                trigger_summary = ("No pude entender el horario, así que por ahora NO correrá solo: puedes ejecutarlo "
                                   "a mano desde tu panel y decirme un horario claro cuando quieras programarlo.")
                when_text = trigger_summary

        if workflow_id:
            await update_workflow_status(workflow_id, "active", db)

        logger.info("[req_investigator] workflow activated id=%s user=%s", workflow_id, user_id)
        confirm_msg = (
            f"¡Listo! Tu workflow **{goal}** quedó activo ({len(deployed_steps)} pasos).\n\n"
            f"{when_text}\n\nPuedes verlo y gestionarlo en tu panel de workflows."
        )
    except Exception as exc:
        logger.error("[req_investigator] finalize failed: %s", exc)
        # El borrador sigue guardado: se queda en CONFIRM para que un "sí" lo reintente.
        return {"req_level": REQ_CONFIRM, "structured_prompt": "Tuve un problema al activar el workflow y no quedó activo. "
                                                               "Dime «sí» para intentarlo de nuevo."}

    return {
        **_ENDED,
        "req_workflow_id": workflow_id,
        "req_deployed_steps": deployed_steps,  # la UI pinta la tarjeta del workflow con estos pasos
        "req_webhook_url": webhook_url,
        "req_trigger_summary": trigger_summary,
        "req_deployed": True,
        "structured_prompt": confirm_msg,
    }


# ── Dispatcher ───────────────────────────────────────────────────────────────

_LEVEL_FUNCS = {
    REQ_GATHER: _gather,
    REQ_CONFIRM: _confirm_stage,
}


async def req_investigator_node(state: ShifuState) -> dict:
    """Saca una pregunta encolada por turno (sin LLM, maxima prioridad). Si no hay, corre la etapa actual y la encadena
    mientras avance en silencio (p. ej. CONFIRM que pide cambiar vuelve a GATHER en el mismo turno), para que el usuario
    siempre vea contenido real. Acotado a 4 saltos: no puede ciclar. Todo mensaje del nodo sale con req_relay=True."""
    pending = state.get("req_pending_questions") or []
    if pending:
        next_q, rest = pending[0], pending[1:]
        return {"req_pending_questions": rest or None, "structured_prompt": next_q, "req_relay": True}

    accumulated: dict = {}
    working_state: ShifuState = state
    level = working_state.get("req_level") or REQ_GATHER
    for _ in range(4):
        logger.info("[req_investigator] level=%s user=%s", level, working_state.get("user_id", "?"))
        level_fn = _LEVEL_FUNCS.get(level)
        if level_fn is None:
            logger.warning("[req_investigator] unexpected level=%s — clearing", level)
            result = {"req_level": None, "req_pending_questions": None, "req_level_entered": None}
        else:
            result = await level_fn(working_state)

        accumulated.update(result)
        if "structured_prompt" in result or result.get("req_level") is None:
            break
        working_state = {**working_state, **accumulated}  # type: ignore[typeddict-item]
        level = working_state.get("req_level") or REQ_GATHER

    if accumulated.get("structured_prompt"):
        # req_compose: la etapa dejo hechos, no un mensaje final; el responder arma la respuesta con ellos.
        accumulated["req_relay"] = not accumulated.get("req_compose")
        if accumulated["req_relay"]:
            accumulated["structured_prompt"] = await _in_user_language(state, str(accumulated["structured_prompt"]))
    return accumulated


# Lo que una traduccion no puede perder ni cambiar: correos, enlaces, horas, rangos de hoja y numeros.
_PROTECTED = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+|https?://\S+|\b\d{1,2}:\d{2}\b|\b[A-Z]+\d*:[A-Z]+\d*\b|\b\d+\b")

_TRANSLATE = (
    "Translate MESSAGE into {language}. It is a message from an assistant to its user about an automation. Keep every "
    "fact, step, value, name, time, time zone and number exactly; keep text inside «» or quotes, emails, links and "
    "**bold** names untouched; write times and numbers with the same digits and punctuation as the message (9:00 stays "
    "9:00, never 9h00 or 9 a.m.); translate every other word, greetings and exclamations included; keep the same line "
    "breaks and the final question if there is one. Add nothing, drop "
    "nothing, explain nothing. Return only the translated message."
)


async def _in_user_language(state: ShifuState, message: str) -> str:
    """Los mensajes del flujo estan escritos en espanol en el codigo: a quien escribe en ingles, portugues o frances se
    le entregaban en espanol (0 de 6, idiomas del 2026-10-11). Se traducen con un modelo y el codigo comprueba que no se
    perdio ningun dato; si falta uno, o falla, se entrega el original."""
    language = (state.get("user_language") or "").strip()
    if not language or language.lower().startswith(("spanish", "español", "espanol")):
        return message
    try:
        resp = await _llm.ainvoke([SystemMessage(content=_TRANSLATE.format(language=language)), HumanMessage(content=message)],
                                  config={"tags": ["req_translate"]})
        text = str(resp.content or "").strip()
    except Exception as exc:
        logger.warning("[req_investigator] translation failed: %s", exc)
        return message
    lost = [t for t in set(_PROTECTED.findall(message)) if t not in text]
    if not text or lost or (message.rstrip().endswith("?") and "?" not in text[-200:]):
        logger.warning("[req_investigator] translation dropped %s; delivering the original", lost)
        return message
    return text
