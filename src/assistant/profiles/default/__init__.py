"""Perfil por defecto: Agente 0, asistente tipo ChatGPT. Reproduce exactamente el comportamiento anterior al refactor."""
from assistant.core.config import ROOT
from assistant.core.memory import MEMORY_POLICIES, SEARCH_ECONOMY_RULE
from assistant.core.profile import AgentProfile, ToolPolicy
from assistant.core.tools import research_approval


def build_tools(model, settings, base):
    """Las herramientas base del núcleo y, con ENABLE_HITL_DEMO, el email simulado (pide aprobación)."""
    from assistant.core.tools import enviar_email_simulado

    tools = list(base)
    if settings.enable_hitl_demo:
        tools.append(enviar_email_simulado)
    return tools


def bigtool_tools(settings):
    """Extra del registro de bigtool: 31 utilidades y, con BIGTOOL_DEMO_TOOLS, las demos de math, texto y el CRM."""
    from assistant.apps.crm_demo import crm_tools
    from assistant.core.extensions.bigtool import _herramientas_math, _herramientas_texto
    from assistant.extra_tools import extra_tools

    tools = extra_tools()
    if settings.bigtool_demo_tools:
        tools += _herramientas_math() + _herramientas_texto() + crm_tools()
    return tools


TOOL_POLICIES = {
    "send_simulated_email": ToolPolicy(effect="send", approval=True),
    # pausa con la tarjeta de aprobación, salvo que el usuario haya pedido investigar en ese mensaje
    "deep_research": ToolPolicy(effect="read", approval=research_approval()),
}

PROFILE = AgentProfile(
    name="default",
    display_name="Agente 0",
    system_prompt_path=ROOT / "prompts" / "system.md",
    static_dir=ROOT / "static",
    build_tools=build_tools,
    bigtool_tools=bigtool_tools,
    tool_policies=TOOL_POLICIES,
    memory_policies=MEMORY_POLICIES,
    search_economy_rule=SEARCH_ECONOMY_RULE,
)
