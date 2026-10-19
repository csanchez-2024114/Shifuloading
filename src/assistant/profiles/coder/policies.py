"""Políticas del perfil coder: qué hace cada herramienta (effect), cuáles piden aprobación y qué se guarda en la
memoria global. Restaurar una versión y borrar un proyecto piden siempre la tarjeta, con los datos reales."""
from assistant.core.profile import ToolPolicy
from assistant.packs.tools.coder import delete_project_card, restore_card


def _card(description) -> dict:
    return {"allowed_decisions": ["approve", "reject"], "description": description}


TOOL_POLICIES = {
    "web_search": ToolPolicy(effect="read", evidence=True),
    "create_project": ToolPolicy(effect="write"),
    "list_projects": ToolPolicy(effect="read"),
    "list_project_files": ToolPolicy(effect="read"),
    "read_project_file": ToolPolicy(effect="read"),
    "write_project_file": ToolPolicy(effect="write"),
    "edit_project_file": ToolPolicy(effect="write"),
    "delete_project_file": ToolPolicy(effect="write"),  # crea una versión nueva: se puede recuperar
    "add_project_asset": ToolPolicy(effect="write"),  # una subida del propio usuario
    "preview_project": ToolPolicy(effect="read"),  # enlace privado de 30 minutos, solo lectura
    "list_project_versions": ToolPolicy(effect="read"),
    "diff_project_versions": ToolPolicy(effect="read"),
    "restore_project_version": ToolPolicy(effect="write", approval=_card(restore_card)),
    "delete_project": ToolPolicy(effect="delete", approval=_card(delete_project_card)),
}

# lo que lee el modelo va en inglés
MEMORY_POLICIES = {
    "strict": """## Saving to long-term memory
- Long-term memory is shared by all of this user's conversations, so it holds only a few precise facts. Call save_memory ONLY when the user explicitly asks you to remember something, or states a durable fact about themselves that will clearly be useful in other conversations.
- Never save project content: code, file contents, project names or ids, what you built or changed, or any text that came from a project file, an attachment or a web page. The projects keep all of that.
- Only save what the user explicitly said about themselves, in the user's language, and pass in evidence the user's exact words copied verbatim.
- Save at most {max_per_turn} memories per message.""",
}
