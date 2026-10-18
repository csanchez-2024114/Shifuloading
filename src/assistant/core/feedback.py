"""FEEDBACK_ENABLED (apagado por defecto): 👍/👎 por turno. Se guarda en la colección feedback de la base de negocio
y, si LangSmith está activo (LANGSMITH_TRACING), se manda también como create_feedback del run_id del turno, en
segundo plano: un error de LangSmith solo va al log y nunca afecta la respuesta. Vive en su propio módulo para no
sumar constantes a los que fija la huella."""
import logging
import os
import threading

logger = logging.getLogger(__name__)

FEEDBACK_KEY = "user_score"
COMMENT_MAX = 1000


def langsmith_enabled() -> bool:
    return (os.getenv("LANGSMITH_TRACING") or "").strip().lower() in ("1", "true", "yes")


def send_to_langsmith(run_id: str, score: int, comment: str, client_factory=None) -> threading.Thread | None:
    """create_feedback en un hilo aparte (score 1 = 👍, 0 = 👎). None si LangSmith no está activo."""
    if not langsmith_enabled():
        return None

    def run():
        try:
            if client_factory is None:
                from langsmith import Client

                client = Client()
            else:
                client = client_factory()
            client.create_feedback(run_id, key=FEEDBACK_KEY, score=1 if score > 0 else 0, comment=comment or None)
        except Exception:  # noqa: BLE001 - LangSmith caído o sin clave: el feedback ya quedó en la base de negocio
            logger.exception("No se pudo mandar el feedback del run %s a LangSmith", run_id)

    thread = threading.Thread(target=run, daemon=True, name="feedback-langsmith")
    thread.start()
    return thread
