"""Perfil mínimo de prueba: una herramienta y un prompt propios, sin tocar core/. Solo importa de assistant.core y
assistant.packs; ningún otro perfil."""
from pathlib import Path

from langchain.tools import tool

from assistant.core.i18n import TextCatalog
from assistant.core.profile import AgentProfile
from assistant.packs import ui
from assistant.packs.i18n import es

HERE = Path(__file__).parent


@tool("word_count")
def word_count(text: str) -> str:
    """Counts the words in a text."""
    return f"{len(text.split())} words."


def build_tools(model, settings, base):
    return [word_count]  # ninguna herramienta del núcleo


PROFILE = AgentProfile(
    name="minimal",
    display_name="Mínimo",
    system_prompt_path=HERE / "prompts" / "system.md",
    static_dir=ui.STATIC_DIR,
    build_tools=build_tools,
    memory_policies={"strict": "## Saving to long-term memory\n- Never call save_memory."},
    texts=TextCatalog(es.TEXTS, {"http.thread_not_found": "No encontré esa conversación."}),  # base + 1 propia
)
