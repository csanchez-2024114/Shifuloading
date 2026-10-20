"""TRACE_METADATA (apagado por defecto): cada turno (/chat o /resume) lleva un run_id propio y metadatos en la traza
de LangChain/LangSmith, y la UI recibe el run_id en el evento SSE "run" para poder dar feedback de ese turno.

Los metadatos no llevan contenido de mensajes: hilo, usuario (el id de la sesión con cuentas), esfuerzo, sha256 del
prompt del sistema (sin la línea de la fecha, para que sea estable), modelo y perfil. Vive en su propio módulo para no
sumar constantes a los que fija la huella."""
import hashlib
import uuid

DATE_LINE_PREFIX = "User's current local date and time:"  # la última línea de system_prompt_text
RUN_NAME = "agent_turn"


def prompt_sha256(prompt: str) -> str:
    """sha256 (16 hex) del prompt sin la línea de la fecha: cambia solo si cambia el prompt o una regla."""
    stable = "\n".join(line for line in prompt.splitlines() if not line.startswith(DATE_LINE_PREFIX))
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()[:16]


def new_run_id() -> uuid.UUID:
    return uuid.uuid4()


def apply(config: dict, run_id: uuid.UUID, *, thread_id: str, user_id: str, kind: str, effort: str | None,
          effort_source: str, model: str, profile_name: str, prompt_sha: str) -> dict:
    """Pone run_id, run_name, metadata y tags en la config del turno (la raíz de la traza). Devuelve los metadatos."""
    metadata = {"thread_id": thread_id, "user_id": user_id, "turn_kind": kind, "effort": effort,
                "effort_source": effort_source, "model": model, "profile": profile_name, "prompt_sha256": prompt_sha}
    config["run_id"] = run_id
    config["run_name"] = RUN_NAME
    config["metadata"] = {**(config.get("metadata") or {}), **metadata}
    config["tags"] = list(dict.fromkeys([*(config.get("tags") or []), RUN_NAME, profile_name, kind]))
    return metadata
