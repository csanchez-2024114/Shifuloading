import pytest


def test_ping_mongo_inalcanzable():
    from assistant.config import ConfigError
    from assistant.memory import ping_mongo

    with pytest.raises(ConfigError, match="No pude conectar a MongoDB en"):
        ping_mongo("mongodb://127.0.0.1:27999", timeout_ms=300)


class _FakeModels:
    def __init__(self, ids):
        self.data = [type("M", (), {"id": i})() for i in ids]

    def __iter__(self):
        return iter(self.data)


def _patch_openai(monkeypatch, ids):
    import openai

    class FakeOpenAI:
        def __init__(self, *args, **kwargs):
            self.models = type("Models", (), {"list": lambda s: _FakeModels(ids)})()

    monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)


def test_verify_model_existe(monkeypatch):
    from assistant.memory import verify_model

    _patch_openai(monkeypatch, ["gpt-4o", "gpt-6-luna", "gpt-6-luna-mini"])
    assert verify_model("sk-test-fake", "gpt-6-luna") == "gpt-6-luna"


def test_verify_model_no_existe_lista_luna(monkeypatch):
    from assistant.config import ConfigError
    from assistant.memory import verify_model

    _patch_openai(monkeypatch, ["gpt-4o", "gpt-6-luna", "gpt-6-luna-mini"])
    with pytest.raises(ConfigError) as exc:
        verify_model("sk-test-fake", "gpt-inexistente")
    msg = str(exc.value)
    assert "gpt-6-luna" in msg and "gpt-6-luna-mini" in msg
    assert "gpt-4o" not in msg  # solo se listan los ids 'luna'


def test_require_api_key_sin_clave(make_settings):
    from assistant.config import ConfigError

    with pytest.raises(ConfigError):
        make_settings(openai_api_key="").require_api_key()
    make_settings().require_api_key()  # con clave no falla


def test_todos_los_chatopenai_llevan_timeout_y_reintentos(monkeypatch):
    """P4: LLM_TIMEOUT_SECONDS (300) y LLM_MAX_RETRIES (2) en todo ChatOpenAI que hace llamadas. El único sin ellos es
    el de config._profile_window, que solo lee el perfil del modelo y nunca llama a la API."""
    import re
    from pathlib import Path

    from conftest import _settings

    from assistant.core import agent, tools

    s = _settings()
    assert (s.llm_timeout_seconds, s.llm_max_retries) == (300.0, 2)
    for m in (agent.make_model(s), agent.make_checker_model(s), agent.make_summary_model(s)):
        assert (m.request_timeout, m.max_retries) == (300.0, 2)
    assert agent.make_model(_settings(llm_timeout_seconds=0, llm_max_retries=0)).request_timeout is None

    creados = []

    class Registro:
        def __init__(self, **kwargs):
            creados.append(kwargs)
            raise RuntimeError("sin red")

    monkeypatch.setattr(tools, "ChatOpenAI", Registro)
    monkeypatch.setattr(tools, "_ddg_search", lambda q: "ddg")
    tools.web_search("q", s)
    monkeypatch.setattr(agent, "ChatOpenAI", Registro)
    agent.clasificar_esfuerzo(s, "hola")
    assert [(k["timeout"], k["max_retries"]) for k in creados] == [(300.0, 2), (300.0, 2)]

    src = Path(__file__).resolve().parents[1] / "src" / "assistant"
    sitios = [(p.name, m.start()) for p in src.rglob("*.py") for m in re.finditer(r"ChatOpenAI\(", p.read_text("utf-8"))]
    sin_kwargs = [(p.name, line) for p in src.rglob("*.py") for line in re.findall(r"ChatOpenAI\([^\n]*(?:\n[^\n]*){0,8}",
                  p.read_text("utf-8")) if "llm_kwargs(settings)" not in line]
    assert len(sitios) == 6 and [n for n, _ in sin_kwargs] == ["config.py"], sin_kwargs
