"""Perfil `crm`: el CRM generativo (Shifuloading) sobre el núcleo de Alan. El dominio vive en `assistant.packs.crm`; aquí
van el bucle del turno como middleware (`bucle.ContextoCrm`, `VueltaCrm`, `VerdadFinal`) y el registro del motor.

Fase 2 (plan: docs/crm/PLAN_NUCLEO_ALAN_2026-10-19.md): el prompt, las herramientas y la verdad de la respuesta son los del
CRM tal cual; el núcleo aporta create_agent y su pila. `CRM_NUCLEO=agente0` hace que la ruta del chat use este motor.
"""
from pathlib import Path

from assistant.core.i18n import TextCatalog
from assistant.core.profile import AgentProfile
from assistant.packs import ui
from assistant.packs.i18n import es
from assistant.packs.lang import es_en

HERE = Path(__file__).parent


def build_tools(model, settings, base):
    # Las herramientas del CRM cambian en cada vuelta (toma, pestaña abierta, tras deshacer): las pone ContextoCrm.
    return []


def extra_middleware(settings):
    from assistant.profiles.crm.bucle import middlewares

    return middlewares()


MEMORY_POLICIES = {"strict": "## Saving to long-term memory\n- Not used by this profile."}

PROFILE = AgentProfile(
    name="crm",
    display_name="CRM generativo",
    system_prompt_path=HERE / "prompts" / "system.md",
    static_dir=ui.STATIC_DIR,
    build_tools=build_tools,
    memory_policies=MEMORY_POLICIES,
    texts=TextCatalog(es.TEXTS),
    intents=es_en.INTENTS,
    lexicon=es_en.LEXICON,
    extra_middleware=extra_middleware,
)
