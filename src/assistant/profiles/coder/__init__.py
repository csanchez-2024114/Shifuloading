"""Perfil coder: Agente 0 como agente codificador de mini apps estáticas (CODER_ENABLED=1, AGENT_PROFILE=coder). Usa
la UI compartida; el perfil por defecto no cambia. Plan: docs/CODER_PLAN.md."""
from pathlib import Path

from assistant.core.i18n import TextCatalog
from assistant.core.profile import AgentProfile
from assistant.packs import ui
from assistant.packs.i18n import es, es_coder
from assistant.packs.lang import es_en
from assistant.profiles.coder.policies import MEMORY_POLICIES, TOOL_POLICIES
from assistant.profiles.coder.tools import build_tools

HERE = Path(__file__).parent

PROFILE = AgentProfile(
    name="coder",
    display_name="Agente 0 · Código",
    system_prompt_path=HERE / "prompts" / "system.md",  # se relee en cada mensaje
    static_dir=ui.STATIC_DIR,
    build_tools=build_tools,
    tool_policies=TOOL_POLICIES,
    memory_policies=MEMORY_POLICIES,
    texts=TextCatalog(es.TEXTS, es_coder.TEXTS),
    intents=es_en.INTENTS,
    lexicon=es_en.LEXICON,
)
