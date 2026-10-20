"""Herramientas del perfil por defecto: qué usa el agente normal y qué extra lleva el registro de bigtool."""
from langchain.tools import tool


# --------------------------------------------------------------------------- HITL demo


@tool("send_simulated_email")
def enviar_email_simulado(recipient: str, subject: str, body: str) -> str:
    """Sends an email (SIMULATED: nothing is actually sent). Requires human approval
    before it runs.
    """
    return f"Simulated email sent to {recipient} with subject {subject!r} ({len(body)} characters)."


# utilidades de bigtool que traen texto de internet (APIs públicas): se envuelven con UNTRUSTED_WRAP
NETWORK_TOOLS = frozenset({"convert_currency", "geocode_place", "distance_between_places", "weather_forecast",
                           "wikipedia_summary"})


def build_tools(model, settings, base):
    """Las herramientas base del núcleo y, con ENABLE_HITL_DEMO, el email simulado (pide aprobación)."""
    tools = list(base)
    if settings.enable_hitl_demo:
        tools.append(enviar_email_simulado)
    return tools


def bigtool_tools(settings):
    """Extra del registro de bigtool: 31 utilidades y, con BIGTOOL_DEMO_TOOLS, las demos de math, texto y el CRM."""
    from assistant.packs.tools.demo import _herramientas_math, _herramientas_texto
    from assistant.packs.tools.utilities import extra_tools
    from assistant.profiles.default.apps.crm_demo import crm_tools

    tools = extra_tools()
    if settings.untrusted_wrap:  # UNTRUSTED_WRAP: lo que traen de internet va envuelto como contenido no confiable
        from assistant.core.untrusted import untrusted_tool

        tools = [untrusted_tool(t) if t.name in NETWORK_TOOLS else t for t in tools]
    if settings.bigtool_demo_tools:
        tools += _herramientas_math() + _herramientas_texto() + crm_tools()
    return tools
