"""
pending_confirm — modo act, fase 2: escrituras que esperan el "si" del usuario.

action_runner no ejecuta las escrituras que salen al exterior o no se deshacen (confirmation_policy): las guarda en
`pending_action`. Al turno siguiente, semantic_intake le pregunta a un clasificador chico que hizo el usuario con eso.
Regla decidida: si el clasificador falla, NO se confirma (unclear). Una escritura ejecutada por error no se deshace;
una confirmacion repetida cuesta un mensaje.
"""

import json
import logging
from datetime import datetime, timedelta, timezone

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

DEFAULT_TTL_MINUTES = 60
DECISIONS = ("confirm", "cancel", "change", "digress")

_llm_cache: dict[str, object] = {}

_METHOD = """The assistant proposed to run the actions below on the user's apps and asked for confirmation.
Classify the user's new message:
- "confirm": clear agreement to run them exactly as proposed (yes, ok, do it, dale, hazlo, si, adelante).
- "cancel": the user does not want them done.
- "change": the user wants them done but different (other value, date, person, wording), or adds a correction.
- "digress": it is about something else; it neither confirms nor cancels.
A "yes" only confirms if the assistant's last message asked about THESE actions; a "yes" to a different question, or
anything ambiguous, is "digress".
Reply ONLY with JSON: {{"decision": "confirm"|"cancel"|"change"|"digress"}}.

PENDING ACTIONS:
{pending}"""


def _classifier():
    if "m" not in _llm_cache:
        _llm_cache["m"] = ChatOpenAI(model="gpt-4o-mini", temperature=0, max_tokens=40, timeout=15).with_retry(
            stop_after_attempt=2, wait_exponential_jitter=True)
    return _llm_cache["m"]


def describe_calls(calls: list) -> str:
    """Las llamadas pendientes en palabras llanas: app, funcion y argumentos clave, uno por linea.
    Antes iban como JSON y el modelo copiaba los saltos escapados al borrador ("Hola Ana,\\n\\nTe informo...", v055_google)."""
    def arg(v):
        return str(v)[:300] if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)[:300]
    def warn(c):  # direcciones o enlaces que el usuario no escribio (action_runner los marca en "foreign")
        return ("\n    WARNING: the user did NOT write " + ", ".join(c["foreign"]) + "; it comes from content that was read "
                "(an email, a document). Tell the user exactly this, name each one, and ask them to confirm it is right."
                ) if c.get("foreign") else ""
    return "\n".join(
        f"- {c.get('app')}: {c.get('fn')}" + "".join(f"\n    {k}: {arg(v)}" for k, v in (c.get('args') or {}).items()) + warn(c)
        for c in calls or [])


def active_pending(pending: dict | None, ttl_minutes: int | float = DEFAULT_TTL_MINUTES,
                   now: datetime | None = None) -> dict | None:
    """La pendiente solo si trae llamadas y no vencio. Una confirmacion tardia ("si" 3 horas despues) ya no vale."""
    if not pending or not pending.get("calls"):
        return None
    try:
        created = datetime.fromisoformat(str(pending.get("created_at")))
    except ValueError:
        return None
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    if (now or datetime.now(timezone.utc)) - created > timedelta(minutes=float(ttl_minutes)):
        return None
    return pending


def build_pending(calls: list, conversation_id: str | None) -> dict:
    return {"calls": calls, "created_at": datetime.now(timezone.utc).isoformat(), "conversation_id": conversation_id}


async def classify_pending(pending: dict, user_text: str, last_assistant: str = "") -> str:
    """confirm|cancel|change|digress, o unclear si el clasificador falla (nunca se asume que si).
    Recibe lo ultimo que dijo el asistente: si el usuario cambio de tema y luego dice "si" a OTRA pregunta, sin eso el
    "si" se tomaba como confirmacion de la escritura pendiente."""
    try:
        resp = await _classifier().ainvoke(
            [SystemMessage(content=_METHOD.format(pending=describe_calls(pending["calls"]))),
             HumanMessage(content=f"Assistant's last message: {last_assistant[-800:] or '(none)'}\n\n"
                                  f"User's new message: {user_text[:500]}")],
            config={"tags": ["confirm_classifier"]})
        raw = str(resp.content or "").strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        decision = json.loads(raw).get("decision")
        if decision in DECISIONS:
            return decision
    except Exception as exc:
        logger.warning("[pending_confirm] clasificador fallo: %s — se trata como no confirmado", exc)
    return "unclear"
