"""Perfil por defecto: Agente 0, asistente tipo ChatGPT. Reproduce exactamente el comportamiento anterior al refactor."""
from pathlib import Path

from assistant.core.i18n import TextCatalog
from assistant.core.profile import AgentProfile
from assistant.packs import ui
from assistant.packs.i18n import es
from assistant.packs.lang import es_en
from assistant.profiles.default.policies import MEMORY_POLICIES, OLD_TOOL_NAMES, SEARCH_ECONOMY_RULE, TOOL_POLICIES
from assistant.profiles.default.tools import bigtool_tools, build_tools

HERE = Path(__file__).parent

PROFILE = AgentProfile(
    name="default",
    display_name="Agente 0",
    system_prompt_path=HERE / "prompts" / "system.md",  # se relee en cada mensaje
    static_dir=ui.STATIC_DIR,  # la UI compartida del pack
    build_tools=build_tools,
    bigtool_tools=bigtool_tools,
    tool_policies=TOOL_POLICIES,
    memory_policies=MEMORY_POLICIES,
    search_economy_rule=SEARCH_ECONOMY_RULE,
    legacy_tool_names=OLD_TOOL_NAMES,
    texts=TextCatalog(es.TEXTS),  # español, sin sobreescrituras
    intents=es_en.INTENTS,  # reglas de intención en español e inglés
    lexicon=es_en.LEXICON,  # memoria por palabras en español e inglés
)
