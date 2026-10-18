"""Carga de perfiles (AGENT_PROFILE): el perfil por defecto trae lo del caso de uso actual y los errores son claros.
Sin red ni Mongo."""
import sys
import types

import pytest


def test_perfil_por_defecto_trae_el_caso_de_uso_actual(monkeypatch):
    from assistant.core.profile import AgentProfile, load_profile

    monkeypatch.delenv("AGENT_PROFILE", raising=False)
    p = load_profile()
    assert isinstance(p, AgentProfile) and p.name == "default" and p.display_name == "Agente 0"
    assert p.system_prompt_path.is_file() and (p.static_dir / "index.html").is_file()
    assert set(p.memory_policies) == {"strict", "broad"} and p.search_economy_rule
    assert p.tool_policies["send_simulated_email"].approval is True
    assert p.tool_policies["deep_research"].approval["allowed_decisions"] == ["approve", "reject"]
    assert load_profile("default") is p  # caché


def test_perfil_inexistente_da_error_claro_en_espanol(monkeypatch):
    from assistant.core.config import ConfigError
    from assistant.core.profile import load_profile

    monkeypatch.setenv("AGENT_PROFILE", "no_existe")
    with pytest.raises(ConfigError) as exc:
        load_profile()
    msg = str(exc.value)
    assert "No existe el perfil 'no_existe' (AGENT_PROFILE)" in msg and "Perfiles disponibles: " in msg
    assert "default" in msg


def test_modulo_sin_profile_valido_da_error_claro(monkeypatch):
    from assistant.core.config import ConfigError
    from assistant.core.profile import AgentProfile, load_profile

    monkeypatch.setitem(sys.modules, "perfil.sin_profile", types.ModuleType("perfil.sin_profile"))
    with pytest.raises(ConfigError, match="no define PROFILE"):
        load_profile("perfil.sin_profile")
    sin_strict = types.ModuleType("perfil.sin_strict")
    sin_strict.PROFILE = AgentProfile(name="x", display_name="x", system_prompt_path=None, static_dir=None,
                                      build_tools=lambda m, s, base: base, memory_policies={"broad": "..."})
    monkeypatch.setitem(sys.modules, "perfil.sin_strict", sin_strict)
    with pytest.raises(ConfigError, match="'strict'"):
        load_profile("perfil.sin_strict")
