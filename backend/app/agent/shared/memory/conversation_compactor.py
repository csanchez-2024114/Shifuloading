"""
conversation_compactor — resumen rodante de la conversacion (compactacion).

Sin esto el responder manda TODO el historial y la entrada crece de 2.7k a 18k tokens hacia el turno 49. Aqui se pliegan
los mensajes que salen de la ventana en un resumen corto; el responder manda resumen + ventana. Los mensajes siguen
completos en el checkpoint (el historial de la UI no se toca).

Los numeros (cuando compactar, cuantos mensajes quedan en la ventana, modelo) son dato:
agent_personality.memory_policy.compaction; aqui solo estan los respaldos.
"""

import logging
from typing import Optional

from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

DEFAULTS = {"enabled": True, "max_messages": 20, "keep_messages": 12, "model": "gpt-4o-mini"}

_MAX_CHARS = 2000  # por mensaje: un pegado largo no debe inflar el prompt del compactor

_PROMPT = (
    "You maintain the rolling summary of a long conversation between a USER and an AI assistant. You receive the "
    "PREVIOUS SUMMARY (may be empty) and the OLDER MESSAGES that are leaving the assistant's context window. Write the "
    "new summary: it replaces both.\n"
    "- Keep EVERY concrete fact the USER gave: names, numbers, amounts, dates, sheet/file names, people, companies, "
    "tools, preferences.\n"
    "- Keep decisions made and tasks still open (what the user asked for and has not received yet).\n"
    "- If the user changed something, keep the LATEST value and note the change (e.g. 'now uses Excel, before Sheets').\n"
    "- Drop small talk, greetings and the assistant's filler. Keep what the assistant committed to do or told the user "
    "only when it matters later.\n"
    "- Never invent anything that is not in the input. Never include passwords, codes, tokens or API keys: write "
    "[redacted] instead.\n"
    "- Plain bullet points, at most ~250 words. Write in the language the user uses. Output only the summary."
)


def chat_messages(messages: list) -> list:
    """Solo lo que cuenta para el resumen: mensajes del usuario y del asistente, en orden."""
    return [m for m in messages if isinstance(m, (HumanMessage, AIMessage))]


def window_messages(messages: list, summary_upto: Optional[int]) -> list:
    """Mensajes que ve el responder cuando hay resumen: desde summary_upto (contado sobre Human/AI).
    Nunca corta el mensaje actual del usuario: el inicio se limita al ultimo HumanMessage."""
    chat = chat_messages(messages)
    last_human = max((i for i, m in enumerate(chat) if isinstance(m, HumanMessage)), default=0)
    return chat[min(max(int(summary_upto or 0), 0), last_human):]


def _render(messages: list) -> str:
    return "\n".join(
        f"{'USER' if isinstance(m, HumanMessage) else 'ASSISTANT'}: {str(m.content)[:_MAX_CHARS]}" for m in messages
    )


async def compact(previous_summary: Optional[str], messages_to_fold: list, model: str = DEFAULTS["model"]) -> str:
    """Mezcla el resumen previo con los mensajes que salen de la ventana. Nunca lanza: si falla devuelve el resumen
    previo (el llamador no avanza summary_upto y reintenta el turno siguiente)."""
    previous = previous_summary or ""
    try:
        llm = ChatOpenAI(model=model, temperature=0)
        out = await llm.ainvoke(
            [("system", _PROMPT),
             ("human", f"PREVIOUS SUMMARY:\n{previous or '(none)'}\n\nOLDER MESSAGES:\n{_render(messages_to_fold)}")],
            config={"tags": ["conversation_compactor"]},
        )
        text = str(getattr(out, "content", "") or "").strip()
        return text or previous
    except Exception as exc:
        logger.warning("[conversation_compactor] no se pudo resumir: %s", exc)
        return previous
