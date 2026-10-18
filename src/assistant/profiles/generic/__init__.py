"""Perfil genérico: asistente de propósito general, prueba de que el núcleo pivota sin tocar core/. Solo usa piezas
del núcleo y de los packs (textos en español, reglas de intención y léxico es_en, la UI compartida); no importa ningún
otro perfil."""
from pathlib import Path

from assistant.core.i18n import TextCatalog
from assistant.core.profile import AgentProfile, ToolPolicy
from assistant.core.tools import research_approval
from assistant.packs import ui
from assistant.packs.i18n import es
from assistant.packs.lang import es_en

HERE = Path(__file__).parent

# herramientas base del núcleo que usa este perfil (sin check_python_syntax), en el orden del núcleo
TOOLS = ("web_search", "calculator", "current_datetime", "save_memory", "search_memories", "update_memory",
         "deep_research")


def build_tools(model, settings, base):
    return [t for t in base if t.name in TOOLS]


TOOL_POLICIES = {
    "web_search": ToolPolicy(effect="read", evidence=True),
    # tarjeta de confirmación, salvo que el usuario pida investigar en ese mensaje
    "deep_research": ToolPolicy(effect="read", approval=research_approval(),
                                description_key="tools.deep_research_confirm", evidence=True),
}

# lo que lee el modelo va en inglés
MEMORY_POLICIES = {
    "strict": """## Saving to long-term memory
- Long-term memory is shared by all of this user's conversations. Call save_memory ONLY when the user explicitly asks you to remember something, or states a durable fact about themselves that will clearly be useful in other conversations.
- Never save conversation content, tool results or details of the current task. Only save what the user explicitly said about themselves, in the user's language, and pass in evidence the user's exact words.
- Save at most {max_per_turn} memories per message.""",
}

SEARCH_ECONOMY_RULE = """## Looking up memories
- If the answer is already in the visible conversation or in its summary, answer directly; call search_memories only when the information is not available in this conversation."""

PROFILE = AgentProfile(
    name="generic",
    display_name="Asistente genérico",
    system_prompt_path=HERE / "prompts" / "system.md",
    static_dir=ui.STATIC_DIR,
    build_tools=build_tools,
    tool_policies=TOOL_POLICIES,
    memory_policies=MEMORY_POLICIES,
    search_economy_rule=SEARCH_ECONOMY_RULE,
    texts=TextCatalog(es.TEXTS),
    intents=es_en.INTENTS,
    lexicon=es_en.LEXICON,
)
