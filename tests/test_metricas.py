"""TURN_METRICS: una fila por turno en la base de negocio, sin contenido de mensajes, con latencia, tokens,
herramientas, aprobaciones y estado; resumen en /metrics/summary y borrado con el hilo y la cuenta. Sin tokens."""
import json

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from conftest import FakeChat, FakeSearch, _settings, tool_call

SECRET = "mi-dato-privado-4242"
ORIGIN = {"Origin": "http://testserver"}


class ConUso(FakeChat):
    """FakeChat que además informa `tokens` por llamada (para medir el turno)."""

    tokens: int = 1000

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        chunks = list(super()._stream(messages, stop=stop, run_manager=run_manager, **kwargs))
        last = chunks[-1].message
        usage = {"input_tokens": self.tokens * 9 // 10, "output_tokens": self.tokens // 10, "total_tokens": self.tokens}
        chunks[-1] = ChatGenerationChunk(message=AIMessageChunk(content=last.content, usage_metadata=usage,
                                                                tool_call_chunks=last.tool_call_chunks,
                                                                chunk_position="last"))
        yield from chunks


class Falla(FakeChat):
    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        raise RuntimeError("se cayó el proveedor")
        yield  # noqa: unreachable - es un generador


def _app(*responses, llm_cls=ConUso, auth=False, tokens=1000, **overrides):
    from assistant.core.agent import build_agent
    from assistant.core.appdata.memory import MemoryAppData
    from assistant.core.server import create_app
    from assistant.core.tools import build_tools

    s = _settings(**{"turn_metrics": True, "auth_enabled": auth, **overrides})
    llm = llm_cls(messages=iter(list(responses)), **({"tokens": tokens} if llm_cls is ConUso else {}))
    store, appdata = InMemoryStore(), MemoryAppData()
    agent = build_agent(llm, build_tools(llm, s, search_fn=FakeSearch()), s, checkpointer=InMemorySaver(),
                        store=store)
    return create_app(agent=agent, settings=s, store=store, appdata=appdata), appdata


def _chat(client, text, thread="h1", user="ana"):
    return client.post("/chat", json={"message": text, "thread_id": thread, "user_id": user})


def _rows(appdata):
    return sorted(appdata.turn_metrics.rows.values(), key=lambda r: r["ts"])


def test_apagado_no_hay_ruta_ni_filas():
    from assistant.core.appdata.memory import MemoryAppData
    from assistant.core.server import create_app

    from conftest import build_test_agent

    s, appdata = _settings(), MemoryAppData()
    app = create_app(agent=build_test_agent(["ok"], s, checkpointer=InMemorySaver()), settings=s,
                     store=InMemoryStore(), appdata=appdata)
    c = TestClient(app)
    assert _chat(c, "hola").status_code == 200
    assert c.get("/metrics/summary").status_code == 404 and appdata.turn_metrics.rows == {}


def test_una_fila_por_turno_sin_contenido_de_mensajes():
    app, appdata = _app(tool_call("calculator", {"expression": "2+2"}, "c1"), f"Son 4. {SECRET}")
    _chat(TestClient(app), f"Calcula 2+2; {SECRET}")
    [row] = _rows(appdata)
    assert row["status"] == "done" and row["kind"] == "chat" and row["thread_id"] == "h1" and row["user_id"] == "ana"
    assert row["tools"] == [{"name": "calculator", "status": "success"}]
    assert row["tokens_total"] == 2000 and row["tokens_input"] == 1800 and row["tokens_output"] == 200
    assert row["latency_ms"] >= 0 and row["approved"] == row["rejected"] == 0 and row["model"] == "gpt-6-luna"
    assert SECRET not in json.dumps(row, default=str)  # ni el mensaje, ni la respuesta, ni los argumentos


def test_tarjeta_rechazada_cuenta_la_aprobacion_y_el_estado():
    app, appdata = _app(tool_call("deep_research", {"task": "algo"}, "d1"), "Sin investigar.")
    c = TestClient(app)
    _chat(c, "dame un plan para mi viaje")
    c.post("/resume", json={"thread_id": "h1", "user_id": "ana",
                            "decisions": [{"type": "reject", "message": "The user declined this action."}]})
    chat, resume = _rows(appdata)
    assert chat["status"] == "interrupted" and chat["kind"] == "chat"
    assert resume["kind"] == "resume" and resume["rejected"] == 1 and resume["approved"] == 0
    assert resume["tools"] == [{"name": "deep_research", "status": "skipped"}] and resume["status"] == "done"


def test_estados_de_corte_y_error():
    # la 1.ª llamada (90k, con herramienta) pasa el tope de 50k: el turno se aborta antes de la herramienta
    app, appdata = _app(tool_call("calculator", {"expression": "1+1"}, "c1"), "ok", tokens=90000,
                        turn_token_cap=50000)
    _chat(TestClient(app), "suma")
    assert _rows(appdata)[0]["status"] == "cap"
    app, appdata = _app(llm_cls=Falla)
    _chat(TestClient(app), "hola")
    assert _rows(appdata)[0]["status"] == "error"


def test_con_trace_metadata_la_fila_usa_el_run_id():
    app, appdata = _app("ok", trace_metadata=True)
    r = _chat(TestClient(app), "hola")
    run = json.loads(r.text.splitlines()[0][6:])
    [row] = _rows(appdata)
    assert run["type"] == "run" and row["run_id"] == run["run_id"] == row["turn_id"]


def test_resumen():
    app, appdata = _app(tool_call("calculator", {"expression": "1+1"}, "c1"), "dos", "hola de nuevo")
    c = TestClient(app)
    _chat(c, "suma")
    _chat(c, "otra")
    out = c.get("/metrics/summary", params={"days": 7}).json()
    assert out["turns"] == 2 and out["status"] == {"done": 2}
    assert out["tools"] == {"calculator": {"success": 1}} and out["tokens"]["total"] == 3000
    assert out["latency_ms"]["p50"] is not None and out["approvals"]["rejection_rate"] is None


def test_sin_base_de_negocio_no_arranca():
    from assistant.core.config import ConfigError
    from assistant.core.server import create_app

    with pytest.raises(ConfigError, match="base de negocio"):
        create_app(agent=object(), settings=_settings(turn_metrics=True), store=InMemoryStore())


def test_con_cuentas_el_resumen_es_del_usuario_y_se_borra_con_el_hilo():
    app, appdata = _app("uno", "dos", "tres", auth=True)

    def login(email):
        c = TestClient(app, headers=ORIGIN)
        r = c.post("/auth/register", json={"email": email, "password": "contraseña-larga-1", "display_name": "x"})
        c.headers["X-CSRF-Token"] = r.json()["csrf"]
        return c

    ana, beto = login("ana@ejemplo.com"), login("beto@ejemplo.com")
    ta = ana.post("/threads").json()["thread_id"]
    tb = beto.post("/threads").json()["thread_id"]
    _chat(ana, "hola", ta)
    _chat(ana, "otra", ta)
    _chat(beto, "hola", tb)
    assert ana.get("/metrics/summary").json()["turns"] == 2 and beto.get("/metrics/summary").json()["turns"] == 1
    assert ana.delete(f"/threads/{ta}").status_code == 200
    assert ana.get("/metrics/summary").json()["turns"] == 0 and beto.get("/metrics/summary").json()["turns"] == 1


def test_mongo_no_crea_colecciones_nuevas_con_los_interruptores_apagados(mongo_client):
    from assistant.core.appdata.mongo import MongoAppData

    db = "app_test"
    mongo_client.drop_database(db)
    appdata = MongoAppData(mongo_client, db)
    appdata.turn_metrics.delete_for_thread("h1")
    appdata.feedback.delete_for_user("ana")
    assert {"turn_metrics", "feedback"}.isdisjoint(mongo_client[db].list_collection_names())
    from datetime import datetime, timezone

    appdata.turn_metrics.add({"turn_id": "t1", "thread_id": "h1", "user_id": "ana", "ts": datetime.now(timezone.utc)})
    assert appdata.turn_metrics.get("t1")["user_id"] == "ana"
    ttl = [i for i in mongo_client[db]["turn_metrics"].list_indexes() if "expireAfterSeconds" in i]
    assert ttl and ttl[0]["expireAfterSeconds"] == 90 * 86400
    mongo_client.drop_database(db)
