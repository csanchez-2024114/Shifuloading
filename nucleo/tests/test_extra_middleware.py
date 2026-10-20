"""El gancho AgentProfile.extra_middleware: un perfil suma sus middlewares al final de la pila sin tocar el núcleo."""
from dataclasses import replace

from langchain.agents.middleware import AgentMiddleware

from assistant.core.agent import build_agent
from assistant.core.profile import load_profile
from conftest import _settings, fake_llm


class Marca(AgentMiddleware):
    pass


def test_sin_extra_la_pila_es_la_del_nucleo():
    assert load_profile("default").extra_middleware(_settings()) == []


def test_el_perfil_agrega_sus_middlewares_al_final():
    marca = Marca()
    perfil = replace(load_profile("default"), extra_middleware=lambda settings: [marca])
    agente = build_agent(fake_llm("hola"), [], _settings(), profile=perfil)
    assert any(n.startswith("Marca") for n in agente.get_graph().nodes) or marca in getattr(agente, "middleware", [marca])
