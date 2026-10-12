"""
Version del agente. Se sube a mano al cambiar el comportamiento (codigo o datos) y se anota en doc/agente/CHANGELOG.md.

El comportamiento vive en dos lugares: codigo (git) y datos en Mongo (agent_identity / agent_personality), que un admin
puede editar sin commit. Por eso la version que se estampa en cada respuesta, traza y corrida de evaluacion es
"<AGENT_VERSION>+<huella>": la huella cambia sola si alguien edita los prompts en Mongo, aunque nadie suba la version.
"""
import hashlib
import json

from app.agent.shared.helpers.identity_loader import get_agent_identity, get_agent_personality

AGENT_VERSION = "0.11.0"


def fingerprint(identity: dict, personality: dict) -> str:
    """Huella corta de los datos de comportamiento (sin _id ni fechas, que cambian sin cambiar el comportamiento)."""
    clean = lambda d: {k: v for k, v in (d or {}).items() if k not in ("_id", "created_at", "updated_at")}
    raw = json.dumps([clean(identity), clean(personality)], sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:8]


async def agent_version() -> str:
    return f"{AGENT_VERSION}+{fingerprint(await get_agent_identity(), await get_agent_personality())}"
