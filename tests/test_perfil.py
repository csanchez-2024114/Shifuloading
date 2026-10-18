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


def test_catalogo_base_mas_sobreescrituras_y_claves_que_faltan(monkeypatch):
    from assistant.core.config import ConfigError
    from assistant.core.i18n import REQUIRED_TEXTS, TextCatalog
    from assistant.core.profile import AgentProfile, load_profile
    from assistant.packs.i18n import es

    fusionado = TextCatalog(es.TEXTS, {"agent.cut_note": "corte"})
    assert fusionado["agent.cut_note"] == "corte" and fusionado["agent.limit_reached"] == es.LIMIT_MSG
    assert not fusionado.missing() and set(REQUIRED_TEXTS) <= set(fusionado)

    incompleto = {k: v for k, v in es.TEXTS.items() if k not in ("agent.cut_note", "format.thousands_sep")}
    modulo = types.ModuleType("perfil.textos_incompletos")
    modulo.PROFILE = AgentProfile(name="x", display_name="x", system_prompt_path=None, static_dir=None,
                                  build_tools=lambda m, s, base: base, memory_policies={"strict": "..."},
                                  texts=TextCatalog(incompleto))
    monkeypatch.setitem(sys.modules, "perfil.textos_incompletos", modulo)
    with pytest.raises(ConfigError) as exc:
        load_profile("perfil.textos_incompletos")
    assert "le faltan estas claves: agent.cut_note, format.thousands_sep." in str(exc.value)


def test_importar_el_nucleo_no_carga_ningun_perfil():
    import subprocess

    codigo = ("import sys, assistant.core.server, assistant.core.agent, assistant.core.tools, assistant.core.memory, "
              "assistant.core.citations, assistant.core.extensions.bigtool, assistant.server\n"
              "cargados = [m for m in sys.modules if m.startswith(('assistant.profiles', 'assistant.packs'))]\n"
              "assert not cargados, cargados\n"
              "assert 'app' not in vars(sys.modules['assistant.core.server'])\n")
    r = subprocess.run([sys.executable, "-W", "ignore", "-c", codigo], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
