"""effect="publish" (agente codificador): con EFFECT_APPROVAL=1 pide la tarjeta como cualquier efecto que no es de
lectura; con 0 no cambia nada. Sin tokens."""
from dataclasses import replace

from assistant.core.agent import approvals
from assistant.core.profile import ToolPolicy, load_profile
from conftest import _settings


def _perfil():
    base = load_profile("default")
    return replace(base, tool_policies={**base.tool_policies, "share_x": ToolPolicy(effect="publish")})


def test_publish_pide_aprobacion_solo_con_effect_approval():
    perfil = _perfil()
    assert "share_x" not in approvals(perfil, _settings())
    card = approvals(perfil, _settings(effect_approval=True))["share_x"]
    assert card["allowed_decisions"] == ["approve", "reject"] and "share_x" in card["description"]


def test_publish_con_aprobacion_explicita_usa_la_del_perfil():
    base = load_profile("default")
    explicita = {"allowed_decisions": ["approve", "reject"], "description": "tarjeta propia"}
    perfil = replace(base, tool_policies={**base.tool_policies,
                                          "share_x": ToolPolicy(effect="publish", approval=explicita)})
    for s in (_settings(), _settings(effect_approval=True)):
        assert approvals(perfil, s)["share_x"] == explicita
