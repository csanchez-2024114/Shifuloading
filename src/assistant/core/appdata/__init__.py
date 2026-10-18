"""Base de negocio: usuarios, sesiones, propiedad de conversaciones e intentos de login (AUTH_ENABLED)."""
from assistant.core.appdata.repos import AppData, DuplicateEmail

__all__ = ["AppData", "DuplicateEmail", "thread_title"]

TITLE_WORDS = 6
TITLE_CHARS = 48


MAX_TITLE_CHARS = 80


def clean_title(title: str) -> str | None:
    """Título puesto por el usuario: espacios colapsados, 1 a MAX_TITLE_CHARS caracteres. None si no vale."""
    title = " ".join((title or "").split())
    return title if 0 < len(title) <= MAX_TITLE_CHARS else None


def thread_title(text: str) -> str:
    """Título de una conversación: las primeras palabras de su primer mensaje (sin llamar al modelo)."""
    words = (text or "").split()
    title = " ".join(words[:TITLE_WORDS])
    if len(title) > TITLE_CHARS:
        title = title[:TITLE_CHARS].rsplit(" ", 1)[0] or title[:TITLE_CHARS]
    return title + ("…" if len(words) > TITLE_WORDS or len(" ".join(words)) > len(title) else "")
