"""Candado por hilo: mientras un turno corre, un segundo /chat o /resume en el MISMO hilo responde 409; otro hilo no
espera; al terminar el turno el candado se suelta (también si el turno falla). Sin tokens: modelo falso lento."""
import threading
import time

from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from conftest import FakeChat, FakeSearch, _settings


class Lento(FakeChat):
    """Tarda `delay` segundos en responder "ok"."""

    delay: float = 1.0

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        time.sleep(self.delay)
        self.messages = iter(["ok"])
        yield from super()._stream(messages, stop=stop, run_manager=run_manager, **kwargs)


class Roto(FakeChat):
    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        raise RuntimeError("falla del proveedor")
        yield  # noqa: unreachable - es un generador


def _app(llm, **overrides):
    from assistant.core.agent import build_agent
    from assistant.core.server import create_app
    from assistant.core.tools import build_tools

    s = _settings(**overrides)
    agent = build_agent(llm, build_tools(llm, s, search_fn=FakeSearch()), s, checkpointer=InMemorySaver(),
                        store=InMemoryStore())
    return create_app(agent=agent, settings=s, store=InMemoryStore())


def _post(app, path, thread, out, key):
    body = {"message": "hola", "thread_id": thread, "user_id": "ana"} if path == "/chat" else \
        {"thread_id": thread, "user_id": "ana", "decisions": [{"type": "approve"}]}
    r = TestClient(app).post(path, json=body)
    out[key] = (r.status_code, r.json().get("detail") if r.status_code != 200 else r.text)


def test_segundo_chat_o_resume_en_el_mismo_hilo_da_409():
    app = _app(Lento(messages=iter([]), delay=1.2))
    out = {}
    first = threading.Thread(target=_post, args=(app, "/chat", "h1", out, "primero"))
    first.start()
    time.sleep(0.4)  # el primer turno está en curso
    _post(app, "/chat", "h1", out, "segundo")
    _post(app, "/resume", "h1", out, "resume")
    _post(app, "/chat", "h2", out, "otro_hilo")
    first.join()
    assert out["primero"][0] == 200 and '"type": "done"' in out["primero"][1]
    assert out["segundo"][0] == 409 and "respuesta en curso" in out["segundo"][1]
    assert out["resume"][0] == 409
    assert out["otro_hilo"][0] == 200  # otro hilo no espera ni se bloquea
    _post(app, "/chat", "h1", out, "despues")  # terminado el turno, el hilo queda libre
    assert out["despues"][0] == 200


def test_sin_keepalive_tambien_se_suelta():
    app = _app(Lento(messages=iter([]), delay=0.1), sse_ping_seconds=0)
    out = {}
    _post(app, "/chat", "h1", out, "a")
    _post(app, "/chat", "h1", out, "b")
    assert out["a"][0] == out["b"][0] == 200


def test_un_turno_que_falla_suelta_el_candado():
    app = _app(Roto(messages=iter([])))
    out = {}
    _post(app, "/chat", "h1", out, "a")
    assert out["a"][0] == 200 and '"type": "error"' in out["a"][1]
    _post(app, "/chat", "h1", out, "b")
    assert out["b"][0] == 200  # no quedó bloqueado


def test_un_413_no_toma_el_candado():
    app = _app(Lento(messages=iter([]), delay=0.1), max_message_chars=10)
    c = TestClient(app)
    assert c.post("/chat", json={"message": "x" * 11, "thread_id": "h1", "user_id": "ana"}).status_code == 413
    assert c.post("/chat", json={"message": "hola", "thread_id": "h1", "user_id": "ana"}).status_code == 200
