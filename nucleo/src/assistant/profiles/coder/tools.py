"""Herramientas del perfil coder: las base de conversación (sin deep_research ni check_python_syntax) y las de
archivos de proyecto. Sin CODER_ENABLED=1 el perfil no arranca."""
from assistant.core.config import ConfigError
from assistant.packs.i18n import es_coder
from assistant.packs.tools.coder import make_coder_tools

# herramientas base del núcleo que usa este perfil, en el orden del núcleo (read_file/search_in_file solo existen con
# FILES_ENABLED=1: sirven para leer un adjunto con especificaciones)
BASE = ("web_search", "calculator", "current_datetime", "save_memory", "search_memories", "update_memory",
        "read_file", "search_in_file")


def build_tools(model, settings, base):
    if not settings.coder_enabled:
        raise ConfigError(es_coder.TEXTS["startup.coder_profile_needs_coder"])
    return [t for t in base if t.name in BASE] + make_coder_tools(settings)
