"""Agente codificador: arranque. Con los CODER_* en 0 nada cambia (ni rutas ni estado); las combinaciones inválidas
no arrancan (ConfigError en español); con una válida, app.state.coder usa la base de negocio. Sin tokens."""
import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from assistant.core.config import ConfigError
from conftest import _settings, build_test_agent

VALIDO = dict(auth_enabled=True, coder_enabled=True, trusted_hosts=("127.0.0.1", "testserver"))


def _app(appdata="memoria", **overrides):
    from assistant.core import server
    from assistant.core.appdata.memory import MemoryAppData

    s = _settings(**overrides)
    extra = {"appdata": MemoryAppData()} if appdata == "memoria" else {"appdata": appdata}
    return server.create_app(agent=build_test_agent(["hola"], s, checkpointer=InMemorySaver()), settings=s,
                             store=InMemoryStore(), **extra)


def _rutas(app) -> set[str]:
    return {r.path for r in app.routes}


def test_con_los_interruptores_en_0_no_hay_nada_del_codificador():
    app = _app(appdata=None)
    assert not hasattr(app.state, "coder")
    assert not any(r.startswith("/coder") for r in _rutas(app))
    app = _app(auth_enabled=True)  # con cuentas, igual
    assert not hasattr(app.state, "coder")


@pytest.mark.parametrize("overrides, texto", [
    (dict(coder_data_enabled=True), "necesitan CODER_ENABLED=1"),
    (dict(coder_sharing_enabled=True), "necesitan CODER_ENABLED=1"),
    (dict(coder_public_write_enabled=True), "necesitan CODER_ENABLED=1"),
    (dict(VALIDO, auth_enabled=False, trusted_hosts=("127.0.0.1", "testserver")), "AUTH_ENABLED=1"),
    (dict(VALIDO, coder_public_write_enabled=True), "CODER_DATA_ENABLED=1 y CODER_SHARING_ENABLED=1"),
    (dict(VALIDO, coder_public_write_enabled=True, coder_data_enabled=True), "CODER_SHARING_ENABLED=1"),
    (dict(VALIDO, use_bigtool=True), "USE_BIGTOOL"),
    (dict(VALIDO, coder_sandbox_origin="localhost:8100"), "CODER_SANDBOX_ORIGIN debe ser"),
    (dict(VALIDO, coder_sandbox_origin="javascript:alert(1)"), "CODER_SANDBOX_ORIGIN debe ser"),
    (dict(VALIDO, coder_sandbox_origin="http://localhost:8100/ruta"), "CODER_SANDBOX_ORIGIN debe ser"),
    (dict(VALIDO, coder_sandbox_origin="http://u:p@localhost:8100"), "CODER_SANDBOX_ORIGIN debe ser"),
    (dict(VALIDO, coder_sandbox_origin="http://localhost:8100", trusted_hosts=("localhost", "127.0.0.1", "testserver")),
     "también está en TRUSTED_HOSTS"),
    (dict(VALIDO, coder_sandbox_origin="http://127.0.0.1:8100"), "también está en TRUSTED_HOSTS"),  # solo otro puerto
    (dict(VALIDO, trusted_hosts=("127.0.0.1", "*")), "también está en TRUSTED_HOSTS"),
    (dict(VALIDO, coder_sandbox_origin="http://LOCALHOST:8100", trusted_hosts=("localhost", "testserver")),
     "también está en TRUSTED_HOSTS"),
])
def test_combinaciones_invalidas_no_arrancan(overrides, texto):
    with pytest.raises(ConfigError) as e:
        _app(**overrides)
    assert texto in str(e.value)


def test_con_los_defaults_y_coder_enabled_la_validacion_de_hosts_pasa(monkeypatch):
    """El default de CODER_SANDBOX_ORIGIN (127.0.0.2, otro host de loopback) no choca con el TRUSTED_HOSTS por defecto
    (localhost, 127.0.0.1): basta con encender CODER_ENABLED y AUTH_ENABLED."""
    from assistant.core.coder.routes import check_settings
    from assistant.core.config import Settings

    for name in ("TRUSTED_HOSTS", "CODER_SANDBOX_ORIGIN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AUTH_ENABLED", "1")
    monkeypatch.setenv("CODER_ENABLED", "1")
    s = Settings.from_env()
    assert s.trusted_hosts == ("localhost", "127.0.0.1")
    assert s.coder_sandbox_origin == "http://127.0.0.2:8100"
    check_settings(s, None, appdata=object())  # no lanza
    app = _app(**dict(VALIDO, trusted_hosts=("localhost", "127.0.0.1", "testserver")))  # arranca con esos hosts
    assert hasattr(app.state, "coder")


def test_sin_base_de_negocio_no_arranca():
    from assistant.core.coder.routes import check_settings

    with pytest.raises(ConfigError, match="base de negocio"):
        check_settings(_settings(**VALIDO), None, appdata=None)


def test_combinacion_valida_en_memoria():
    from assistant.core.coder.memory import MemoryCoderRepo
    from assistant.core.coder.projects import Projects

    app = _app(**VALIDO)
    assert isinstance(app.state.coder, Projects)
    assert isinstance(app.state.coder.repo, MemoryCoderRepo)
    todo = dict(VALIDO, coder_data_enabled=True, coder_sharing_enabled=True, coder_public_write_enabled=True)
    assert isinstance(_app(**todo).state.coder, Projects)


def test_combinacion_valida_usa_la_base_de_negocio_y_no_crea_nada_al_arrancar(mongo_client):
    import uuid

    from assistant.core.appdata.mongo import MongoAppData
    from assistant.core.coder.mongo import MongoCoderRepo
    from coder_repos import TMP_PREFIX

    name = TMP_PREFIX + uuid.uuid4().hex[:12]
    try:
        app = _app(appdata=MongoAppData(mongo_client, name), **VALIDO)
        repo = app.state.coder.repo
        assert isinstance(repo, MongoCoderRepo) and repo.db.name == name
        assert [c for c in mongo_client[name].list_collection_names() if c.startswith("coder_")] == []
        pid = app.state.coder.create("u1", "x")["project_id"]
        assert app.state.coder.get("u1", pid)["nombre"] == "x"
        assert "coder_projects" in mongo_client[name].list_collection_names()
    finally:
        mongo_client.drop_database(name)
