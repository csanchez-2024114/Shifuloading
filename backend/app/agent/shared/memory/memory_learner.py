"""
memory_learner — mini agente que aprende del usuario al final de cada turno.

Lee el ultimo intercambio y escribe:
  - hechos estables del usuario en user_semantic_memory (un documento por hecho, el mismo esquema que /me/memories,
    asi el usuario los ve y los borra desde ahi),
  - lo que se esta haciendo en esta conversacion en user_daily_diary (un documento por conversacion), para que en otra
    conversacion el agente sepa en que quedaron.

Que recordar y que nunca recordar son DATOS (agent_personality.memory_policy); el codigo solo aplica el resultado.
Unica regla en codigo: nada que parezca credencial se guarda, aunque el modelo lo devuelva (frontera de confianza).
"""
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.agent.shared.memory.episodic_memory_helper import COMMITMENTS_DEFAULTS, load_commitments
from app.agent.shared.memory.memory_embedder import embed_text

logger = logging.getLogger(__name__)

FACTS = "user_semantic_memory"
DIARY = "user_daily_diary"
_DEFAULT_MODEL = "gpt-4o-mini"
_SECRET = re.compile(r"password|contrase|passwd|token|api[\s_-]?key|secret|clave|pin\b|cvv|tarjeta", re.I)

_METHOD = """\
You maintain the long-term memory an assistant keeps about ONE user. Read the last exchange and decide what to store.

WHAT TO REMEMBER:
{remember}

NEVER STORE:
{never}

Suggested keys (reuse them; reuse an EXISTING key to update it instead of creating a near-duplicate): {keys}

KNOWN FACTS (key: value):
{facts}

CURRENT SUMMARY OF THIS CONVERSATION: {activity}

TODAY: {today} ({weekday}). Resolve every relative date against it. Next days: {calendar}.

OPEN COMMITMENTS FROM OTHER CONVERSATIONS (conversation_id: task — due date):
{commitments}

Return:
- facts: only NEW or CHANGED facts the USER stated or clearly confirmed about themselves in THIS exchange — never repeat
  a known fact that did not change. action "add" for a new key, "update" to change an existing key, "forget" if the user
  asked to forget it or said it is no longer true. When the user changes something, also update or forget EVERY known
  fact that the change makes wrong. Values short, in the user's language. Most turns: empty list.
- activity: the GOAL(S) the user wants in this conversation — not the last step — with the concrete names they gave
  (sheet and file names, people, companies, suppliers, clients, products, days, apps), e.g. "Registrar en la hoja
  'Citas Vet' cada cita que llega por Gmail", "Preparar el catálogo de invierno y mandárselo a Harinas del Norte".
  Never drop a proper name the user gave: it is how they will ask about it weeks later.
  Keep every goal already in the current summary and add new ones; the current step goes in pending.
  ANY concrete thing the user wants done is a task — also a one-off action ("delete a file in Drive", "send an email")
  and also when it is blocked (then pending says what blocks it, e.g. "connect Google Drive"). Return null ONLY when the
  user just greets, chats, says goodbye or asks what you remember (the current summary is kept). The task must come
  from the USER's own words in this exchange: the assistant recalling earlier conversations is not a new task.
  due_date (YYYY-MM-DD): the DEADLINE the user gave for something they must do or deliver in this conversation ("tengo
  que entregar la nómina el viernes", "mañana", "el 15", "la próxima semana"), even when the current pending step is
  something else (e.g. connecting an app): the deadline belongs to their commitment, not to the step. Resolve it
  against TODAY (a weekday means its next occurrence, counting today only if the user said "hoy"). Also keep the
  commitment and its day in the summary ("Entregar la nómina de los 5 empleados el viernes"). No deadline given: null.
  Never invent a date. If the current summary already shows "due <date>", return that same due_date.
  A commitment with a deadline stays in the summary (with its day) and keeps its due_date until the user says it is
  done: declining help or automation with it ("no necesito automatizarlo") or changing topic does NOT cancel it; add
  the new topic next to it.
- closed: conversation_ids from the OPEN COMMITMENTS list that the USER says in THIS exchange are already done, delivered
  or no longer needed. Only on the user's own words; when in doubt, empty list."""


class _Fact(BaseModel):
    key: str = Field(description="short snake_case key, e.g. role, company, tools")
    value: str
    action: Literal["add", "update", "forget"] = "add"


class _Activity(BaseModel):
    summary: str = Field(description="The goal(s) of this conversation with concrete names; keeps earlier goals")
    pending: Optional[str] = None
    due_date: Optional[str] = Field(None, description="YYYY-MM-DD, only if the user gave a date for the pending task")


class _Learned(BaseModel):
    facts: list[_Fact] = []
    activity: Optional[_Activity] = None
    closed: list[str] = Field([], description="conversation_ids of open commitments the user says are done")


_cache: dict = {}


async def _extract(model: str, prompt: str, exchange: str) -> _Learned:
    if model not in _cache:
        _cache[model] = ChatOpenAI(model=model, temperature=0).with_structured_output(_Learned)
    return await _cache[model].ainvoke(
        [("system", prompt), ("human", exchange)], config={"tags": ["memory_learner"]}
    )


def _is_secret(f: _Fact) -> bool:
    return bool(_SECRET.search(f.key) or _SECRET.search(f.value))


async def learn(db, *, user_id: str, conversation_id: str, user_text: str, reply: str, policy: dict,
                allow_activity: bool = True, now: Optional[datetime] = None) -> dict:
    """Aprende del ultimo intercambio. Devuelve lo que escribio (para la traza y las pruebas). Nunca lanza.

    now: el reloj del turno (state["current_time_utc"]). Las fechas relativas ("el viernes") se resuelven contra el,
    nunca contra datetime.now directo: en desarrollo el reloj puede venir simulado."""
    now = now or datetime.now(timezone.utc)
    cfg = {**COMMITMENTS_DEFAULTS, **(policy.get("commitments") or {})}
    try:
        known = await db[FACTS].find({"user_id": user_id, "status": "active"}, {"key": 1, "value": 1}).to_list(length=50)
        current = await db[DIARY].find_one({"user_id": user_id, "conversation_id": conversation_id}) or {}
        # Pendientes con fecha de otras conversaciones, sin tope de horizonte: el usuario puede cerrar uno adelantado.
        open_c = (await load_commitments(db, user_id, now, 36500, conversation_id)) if cfg["enabled"] else []
        prompt = _METHOD.format(
            today=now.strftime("%Y-%m-%d"), weekday=now.strftime("%A"),
            # El modelo chico no cuenta dias: "el viernes" (lunes 12) salia 14, que es miercoles (fecha_v054d).
            calendar=", ".join(f"{d:%A} {d:%Y-%m-%d}" for d in (now + timedelta(days=i) for i in range(1, 8))),
            commitments="\n".join(f"{c['conversation_id']}: {c['pending']} — {c['due_date']}" for c in open_c) or "(none)",
            remember=policy.get("remember") or "Stable facts about the user: role, company, what they work on, the tools they use, preferences about how to be helped.",
            never=policy.get("never") or "Passwords, tokens, API keys, payment data, health data, anything about third parties.",
            keys=", ".join(policy.get("suggested_keys") or ["role", "company", "work", "tools", "preferences"]),
            facts="\n".join(f"{k['key']}: {k['value']}" for k in known) or "(none)",
            activity=" — ".join(x for x in [(current.get("activities") or [""])[0], current.get("pending") or "",
                                            f"due {current['due_date']}" if current.get("pending") and current.get("due_date") else ""] if x) or "(none)",
        )
        learned = await _extract(policy.get("model") or _DEFAULT_MODEL, prompt, f"USER: {user_text}\nASSISTANT: {reply}")
    except Exception as exc:
        logger.warning("[memory_learner] no se pudo aprender del turno: %s", exc)
        return {"facts": [], "activity": None, "closed": []}

    same = {(k["key"], str(k["value"]).strip().lower()) for k in known}
    written = []
    for f in learned.facts:
        key = f.key.strip().lower()
        if not key or _is_secret(f) or (f.action != "forget" and (key, f.value.strip().lower()) in same):
            continue  # credencial, o el modelo repitio un hecho que ya estaba igual
        sel = {"user_id": user_id, "key": key}
        if f.action == "forget":
            await db[FACTS].update_one(sel, {"$set": {"status": "archived", "last_seen_at": now}})
        else:
            await db[FACTS].update_one(sel, {
                "$set": {"value": f.value.strip(), "status": "active", "last_seen_at": now, "source_conversation": conversation_id},
                "$inc": {"mention_count": 1},
                "$setOnInsert": {"created_at": now},
            }, upsert=True)
        written.append({"key": key, "value": f.value, "action": f.action})

    activity = None
    # allow_activity=False en saludos/charla (semantic_intake): el modelo copiaba como tarea nueva lo que el agente
    # recordaba al saludar (3/3 aun con la regla en el prompt), y tapaba el pendiente real de la otra conversacion.
    if allow_activity and learned.activity and learned.activity.summary.strip():
        activity = {"summary": learned.activity.summary.strip(), "pending": (learned.activity.pending or "").strip() or None,
                    "due_date": None}
        # La fecha solo vale si hay pendiente, la politica lo permite y el formato es valido (el modelo puede inventar).
        if activity["pending"] and cfg["enabled"]:
            activity["due_date"] = _valid_date(learned.activity.due_date)
        # Un embedding por escritura del diario: permite recordar conversaciones viejas por significado (search_older).
        embedding = await embed_text(f"{activity['summary']} {activity['pending'] or ''}".strip())
        update = {"$set": {"date": now.strftime("%Y-%m-%d"), "activities": [activity["summary"]], "pending": activity["pending"],
                           "due_date": activity["due_date"], "updated_at": now}}
        if embedding:
            update["$set"]["embedding"] = embedding
        else:
            update["$unset"] = {"embedding": ""}  # el del resumen anterior ya no corresponde; el backfill lo rehace
        if activity["due_date"]:
            update.setdefault("$unset", {})["done_at"] = ""  # un compromiso nuevo en esta conversacion reabre el cierre anterior
        await db[DIARY].update_one({"user_id": user_id, "conversation_id": conversation_id}, update, upsert=True)

    # Cierres: solo ids que se le ofrecieron al modelo, y el filtro lleva user_id (nunca se confia en un id ajeno).
    offered = {c["conversation_id"] for c in open_c}
    closed = []
    for cid in dict.fromkeys(learned.closed):
        if cid in offered:
            res = await db[DIARY].update_one({"user_id": user_id, "conversation_id": cid},
                                             {"$set": {"done_at": now, "pending": None}})
            if res.matched_count:
                closed.append(cid)
    return {"facts": written, "activity": activity, "closed": closed}


def _valid_date(value: Optional[str]) -> Optional[str]:
    try:
        return datetime.strptime((value or "").strip(), "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        return None
