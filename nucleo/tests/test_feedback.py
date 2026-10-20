"""FEEDBACK_ENABLED: 👍/👎 por turno (run_id del evento "run"), guardado en la base de negocio, solo del dueño del
turno, y mandado a LangSmith en segundo plano si está activo. Sin tokens."""
import json
import sys
import time
import types as pytypes

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from conftest import FakeChat, FakeSearch, _settings

ORIGIN = {"Origin": "http://testserver"}
ON = {"feedback_enabled": True, "trace_metadata": True, "turn_metrics": True}


def _app(n=5, auth=False, **overrides):
    from assistant.core.agent import build_agent
    from assistant.core.appdata.memory import MemoryAppData
    from assistant.core.server import create_app
    from assistant.core.tools import build_tools

    s = _settings(**{**ON, "auth_enabled": auth, **overrides})
    llm = FakeChat(messages=iter(["ok"] * n))
    store, appdata = InMemoryStore(), MemoryAppData()
    agent = build_agent(llm, build_tools(llm, s, search_fn=FakeSearch()), s, checkpointer=InMemorySaver(),
                        store=store)
    return create_app(agent=agent, settings=s, store=store, appdata=appdata), appdata


def _turn(client, thread="h1", user="ana"):
    r = client.post("/chat", json={"message": "hola", "thread_id": thread, "user_id": user})
    first = json.loads(r.text.splitlines()[0][6:])
    assert first["type"] == "run"
    return first["run_id"]


def test_apagado_no_hay_rutas():
    from assistant.core.appdata.memory import MemoryAppData
    from assistant.core.server import create_app

    from conftest import build_test_agent

    s = _settings()
    c = TestClient(create_app(agent=build_test_agent(["ok"], s), settings=s, store=InMemoryStore(),
                              appdata=MemoryAppData()))
    assert c.get("/feedback/config").status_code == 404
    assert c.post("/feedback", json={"run_id": "x", "score": 1}).status_code in (404, 405)


@pytest.mark.parametrize("missing", ["trace_metadata", "turn_metrics"])
def test_necesita_trazas_y_metricas(missing):
    from assistant.core.appdata.memory import MemoryAppData
    from assistant.core.config import ConfigError
    from assistant.core.server import create_app

    with pytest.raises(ConfigError, match="FEEDBACK_ENABLED"):
        create_app(agent=object(), settings=_settings(**{**ON, missing: False}), store=InMemoryStore(),
                   appdata=MemoryAppData())


def test_feedback_de_un_turno_propio():
    app, appdata = _app()
    c = TestClient(app)
    assert c.get("/feedback/config").json()["enabled"] is True
    run = _turn(c)
    r = c.post("/feedback", json={"run_id": run, "score": 1, "comment": "  muy bien  ", "user_id": "ana"})
    assert r.status_code == 200 and r.json() == {"ok": True, "run_id": run, "score": 1}
    c.post("/feedback", json={"run_id": run, "score": -1, "user_id": "ana"})  # cambia de opinión: el último gana
    [row] = appdata.feedback.rows.values()
    assert row["score"] == -1 and row["thread_id"] == "h1" and row["user_id"] == "ana"
    assert c.get("/metrics/summary").json()["feedback"] == {"up": 0, "down": 1}


def test_rechazos():
    app, _ = _app()
    c = TestClient(app)
    run = _turn(c)
    assert c.post("/feedback", json={"run_id": run, "score": 5, "user_id": "ana"}).status_code == 400
    r = c.post("/feedback", json={"run_id": run, "score": 1, "comment": "x" * 1001, "user_id": "ana"})
    assert r.status_code == 400 and "1000" in r.json()["detail"]
    assert c.post("/feedback", json={"run_id": "no-existe", "score": 1, "user_id": "ana"}).status_code == 404
    assert c.post("/feedback", json={"run_id": run, "score": 1, "user_id": "beto"}).status_code == 404


def test_con_cuentas_solo_el_dueno_y_con_csrf():
    app, appdata = _app(auth=True)

    def login(email):
        c = TestClient(app, headers=ORIGIN)
        r = c.post("/auth/register", json={"email": email, "password": "contraseña-larga-1", "display_name": "x"})
        c.headers["X-CSRF-Token"] = r.json()["csrf"]
        return c

    ana, beto = login("ana@ejemplo.com"), login("beto@ejemplo.com")
    run = _turn(ana, ana.post("/threads").json()["thread_id"])
    assert beto.post("/feedback", json={"run_id": run, "score": -1}).status_code == 404
    sin_csrf = TestClient(app, headers=ORIGIN, cookies=ana.cookies)
    assert sin_csrf.post("/feedback", json={"run_id": run, "score": 1}).status_code == 403
    assert ana.post("/feedback", json={"run_id": run, "score": 1, "user_id": "beto"}).status_code == 200
    [row] = appdata.feedback.rows.values()
    assert row["user_id"] != "beto"  # sale de la sesión


def test_langsmith_en_segundo_plano(monkeypatch):
    calls = []

    class Client:
        def create_feedback(self, run_id, **kwargs):
            calls.append((run_id, kwargs))

    monkeypatch.setitem(sys.modules, "langsmith", pytypes.SimpleNamespace(Client=Client))
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    app, _ = _app()
    c = TestClient(app)
    run = _turn(c)
    c.post("/feedback", json={"run_id": run, "score": -1, "comment": "le faltó la fuente", "user_id": "ana"})
    for _ in range(50):
        if calls:
            break
        time.sleep(0.02)
    assert calls == [(run, {"key": "user_score", "score": 0, "comment": "le faltó la fuente"})]


def test_un_error_de_langsmith_no_rompe_nada(monkeypatch, caplog):
    from assistant.core.feedback import send_to_langsmith

    def roto():
        raise RuntimeError("sin red")

    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    assert send_to_langsmith("r1", 1, "", client_factory=roto) is None  # apagado: ni lo intenta
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    t = send_to_langsmith("r1", 1, "", client_factory=roto)
    t.join(2)
    assert "No se pudo mandar el feedback" in caplog.text
