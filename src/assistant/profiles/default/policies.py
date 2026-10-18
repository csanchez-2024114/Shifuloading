"""Políticas del perfil por defecto: aprobaciones por herramienta y nombres antiguos de las herramientas."""
from assistant.core.profile import ToolPolicy
from assistant.core.tools import research_approval

TOOL_POLICIES = {
    "send_simulated_email": ToolPolicy(effect="send", approval=True),
    # pausa con la tarjeta de aprobación, salvo que el usuario haya pedido investigar en ese mensaje
    "deep_research": ToolPolicy(effect="read", approval=research_approval()),
}

# Nombres anteriores (en español) de las herramientas. Los hilos guardados antes del cambio los tienen en su
# historial (llamadas y resultados) y bigtool en selected_tool_ids.
OLD_TOOL_NAMES = {"buscar_web": "web_search", "calculadora": "calculator", "fecha_hora": "current_datetime",
                  "guardar_recuerdo": "save_memory", "buscar_recuerdos": "search_memories",
                  "actualizar_recuerdo": "update_memory", "investigador_profundo": "deep_research",
                  "enviar_email_simulado": "send_simulated_email"}
