"""
message_index — guarda los mensajes ORIGINALES del usuario con su embedding (coleccion user_message_index).

Por que: el diario resume y pierde nombres propios ("hoja Pedidos Navidad" quedaba como "recordatorios de entrega").
El texto literal sí se encuentra por significado despues (search_older_messages) aunque la conversacion sea vieja.
Nunca rompe el turno: cualquier falla se registra y se ignora.
"""
import logging
import re
from datetime import datetime, timezone

from app.agent.shared.memory.memory_embedder import embed_text
from app.agent.shared.memory.memory_learner import _SECRET

logger = logging.getLogger(__name__)

INDEX = "user_message_index"
MAX_CHARS = 1000
_TRIVIAL = re.compile(
    r"(?:(?:hola|buenas|buenos|dias|días|tardes|noches|hi|hello|hey|gracias|thanks|thank|you|ok|okay|vale|listo|"
    r"perfecto|genial|adios|adiós|bye|muchas|si|sí|no)\b[\s,.!¡¿?]*)+",
    re.I,
)


def is_trivial(text: str) -> bool:
    text = (text or "").strip()
    return len(text.split()) < 3 or bool(_TRIVIAL.fullmatch(text))


def indexable(text: str) -> bool:
    """Frontera de confianza: un texto que parezca credencial no se indexa NI en parte (se descarta entero)."""
    return not is_trivial(text) and not _SECRET.search(text)


async def index_message(db, *, user_id: str, conversation_id: str, text: str) -> bool:
    """Un embedding por mensaje del usuario. True si quedo guardado."""
    try:
        text = (text or "").strip()
        if db is None or not user_id or not indexable(text):
            return False
        text = text[:MAX_CHARS]
        embedding = await embed_text(text)
        if not embedding:
            return False
        now = datetime.now(timezone.utc)
        await db[INDEX].insert_one({
            "user_id": user_id, "conversation_id": conversation_id, "date": now.strftime("%Y-%m-%d"),
            "text": text, "embedding": embedding, "created_at": now,
        })
        return True
    except Exception as exc:
        logger.warning("[message_index] no se pudo indexar el mensaje: %s", exc)
        return False
