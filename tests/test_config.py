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
