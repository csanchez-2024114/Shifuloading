"""Políticas del perfil por defecto: aprobaciones por herramienta, nombres antiguos de las herramientas y qué se
guarda en la memoria global."""
from assistant.core.profile import ToolPolicy
from assistant.core.tools import research_approval

TOOL_POLICIES = {
    "web_search": ToolPolicy(effect="read", evidence=True),
    "send_simulated_email": ToolPolicy(effect="send", approval=True),
    # pausa con la tarjeta de aprobación, salvo que el usuario haya pedido investigar en ese mensaje
    "deep_research": ToolPolicy(effect="read", approval=research_approval(),
                                description_key="tools.deep_research_confirm", evidence=True),
}

# Nombres anteriores (en español) de las herramientas. Los hilos guardados antes del cambio los tienen en su
# historial (llamadas y resultados) y bigtool en selected_tool_ids.
OLD_TOOL_NAMES = {"buscar_web": "web_search", "calculadora": "calculator", "fecha_hora": "current_datetime",
                  "guardar_recuerdo": "save_memory", "buscar_recuerdos": "search_memories",
                  "actualizar_recuerdo": "update_memory", "investigador_profundo": "deep_research",
                  "enviar_email_simulado": "send_simulated_email"}


# Política de guardado en la memoria global (MEMORY_SAVE_POLICY). Va al final del prompt del sistema. Ningún recuerdo
# se inyecta en el prompt: el modelo solo los consulta con search_memories, así cada conversación sigue independiente.
MEMORY_POLICIES = {
    "strict": """## Saving to long-term memory
- Long-term memory is shared by all of this user's conversations, so it holds only a few precise facts. Call save_memory ONLY when:
  (a) the user explicitly asks you to remember something ("remember that…");
  (b) the user states a durable personal fact that will clearly be useful in other conversations: where they live, their job, their pets or family, a stable preference or a lasting technical constraint (e.g. "only Python 3.12");
  (c) the user wants a specific dated event remembered (a birthday, an appointment).
- Never save conversation content: what you explained, tasks, calculations and their results, tool or search results, the topics discussed, or details of the current request (file names, amounts, the dates or budget of a one-off plan, what they are working on today). The conversation itself keeps that.
- Only save what the user explicitly said about themselves, written in the user's language, and pass in evidence the user's exact words copied verbatim. Never save your own assumptions or inferences.
- Save at most {max_per_turn} memories per message.""",
    "broad": """## Saving to long-term memory
- When the user shares stable personal facts (name, likes, preferences, lasting decisions, job and role), save them with save_memory, written in the user's language, and pass in evidence the user's exact words copied verbatim.
- Also save the user's durable technical constraints when they state them explicitly: language or library versions (e.g. "only Python 3.12"), libraries they cannot use or install, their operating system or runtime environment. Pass their exact words as evidence.
- Stable facts the user mentions while asking for something else (where they live, their diet, what they like, their job) are still facts about them: save them.
- Do not save passing details of a single task: file names, row counts, data values, error messages, amounts, the dates or budget of a one-off plan, or what the user is working on today ("today I'm working on file X" is not a fact about the user).
- Only save what the user explicitly said about themselves. Never save your own assumptions, inferences or things you said.""",
}


# MEMORY_SEARCH_ECONOMY: prueba A/B anterior, la configuración B llamó a search_memories en 6 preguntas seguidas
# cuyas respuestas ya estaban en la conversación (~55k tokens extra).
SEARCH_ECONOMY_RULE = """## Looking up memories
- If the answer is already in the visible conversation or in its summary, answer directly; call search_memories only when the information is not available in this conversation. This takes precedence over checking memories at the start of a conversation."""
