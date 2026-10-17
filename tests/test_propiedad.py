"""AUTH_ENABLED=1: sesión, CSRF y dueño de cada conversación en los endpoints. El usuario B nunca lee, escribe, borra
ni consulta el contexto de un hilo de A (404 en todo) ni ve sus recuerdos. Sin tokens: modelo falso."""
import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from conftest import FakeChat, FakeSearch, tool_call

ORIGIN = {"Origin": "http://testserver"}
PW = "contraseña-larga-1"


class Eco(FakeChat):
    """Responde "ok"; si el mensaje dice "guarda: X", primero llama a save_memory con X."""

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        last = next(m for m in reversed(messages) if m.type in ("human", "tool"))
        text = str(last.content)
        if last.type == "human" and text.startswith("guarda: "):
            dato = text[len("guarda: "):]
            self.messages = iter([tool_call("save_memory", {"text": dato, "evidence": dato}, "s1")])
        else:
            self.messages = iter(["ok"])
        yield from super()._stream(messages, stop=stop, run_manager=run_manager, **kwargs)


def _app(make_settings, appdata=None, checkpointer=None, store=None, summarizer=None, **overrides):
    from assistant.agent import build_agent
    from assistant.appdata.memory import MemoryAppData
    from assistant.server import create_app
    from assistant.tools import build_tools

    s = make_settings(auth_enabled=True, **overrides)
    llm = Eco(messages=iter([]))
    store = store if store is not None else InMemoryStore()
    agent = build_agent(llm, build_tools(llm, s, search_fn=FakeSearch()), s,
                        checkpointer=checkpointer or InMemorySaver(), store=store, summarizer=summarizer)
    appdata = appdata or MemoryAppData()
    return create_app(agent=agent, settings=s, store=store, appdata=appdata), agent, appdata, store


def _login(app, email, name="Usuario"):
    c = TestClient(app, headers=ORIGIN)
    r = c.post("/auth/register", json={"email": email, "password": PW, "display_name": name})
    assert r.status_code == 200, r.text
    c.headers["X-CSRF-Token"] = r.json()["csrf"]
    return c


def _chat(c, thread_id, text):
    with c.stream("POST", "/chat", json={"message": text, "thread_id": thread_id, "user_id": "lo-que-diga-el-navegador"}) as r:
        return r.status_code, "".join(r.iter_text())


@pytest.fixture
def app_ab(make_settings):
    app, agent, appdata, store = _app(make_settings)
    a, b = _login(app, "ana@ejemplo.com", "Ana"), _login(app, "beto@ejemplo.com", "Beto")
    return app, agent, appdata, store, a, b


def test_sin_sesion_todo_responde_401(make_settings):
    app, *_ = _app(make_settings)
    c = TestClient(app, headers=ORIGIN)
    assert c.get("/auth/me").json() == {"auth_enabled": True, "user": None}
    for method, url in [("get", "/threads"), ("get", "/history/x"), ("get", "/threads/x/context"),
                        ("get", "/me/memories")]:
        assert getattr(c, method)(url).status_code == 401, url
    assert c.post("/chat", json={"message": "hola", "thread_id": "x"}).status_code == 401


def test_cookie_httponly_samesite_y_secure_configurable(make_settings):
    app, *_ = _app(make_settings)
    r = TestClient(app, headers=ORIGIN).post("/auth/register", json={"email": "a@b.co", "password": PW})
    cookie = r.headers["set-cookie"].lower()
    assert "agente0_session=" in cookie and "httponly" in cookie and "samesite=lax" in cookie
    assert "secure" not in cookie  # http y COOKIE_SECURE=auto
    app2, *_ = _app(make_settings, cookie_secure="1")
    r2 = TestClient(app2, headers=ORIGIN).post("/auth/register", json={"email": "a@b.co", "password": PW})
    assert "secure" in r2.headers["set-cookie"].lower()
    assert PW not in r.text and "password_hash" not in r.text


def test_csrf_y_origen(app_ab):
    app, _, _, _, a, _ = app_ab
    sin_csrf = TestClient(app, headers=ORIGIN, cookies=a.cookies)
    assert sin_csrf.post("/threads").status_code == 403
    otro_origen = TestClient(app, headers={"Origin": "http://malicioso.example", "X-CSRF-Token": a.headers["X-CSRF-Token"]},
                             cookies=a.cookies)
    assert otro_origen.post("/threads").status_code == 403
    assert TestClient(app, cookies=a.cookies, headers={"X-CSRF-Token": a.headers["X-CSRF-Token"]}).post(
        "/threads").status_code == 403  # sin Origin ni Referer
    assert a.post("/threads").status_code == 200


def test_b_no_accede_a_nada_de_a(app_ab):
    app, agent, appdata, store, a, b = app_ab
    tid = a.post("/threads").json()["thread_id"]
    code, body = _chat(a, tid, "guarda: Vive en Mérida")
    assert code == 200 and '"done"' in body
    assert a.get(f"/history/{tid}").status_code == 200
    assert [t["thread_id"] for t in a.get("/threads").json()["threads"]] == [tid]
    assert appdata.threads.get(tid)["title"] == "guarda: Vive en Mérida"  # primeras palabras del primer mensaje

    assert b.get(f"/history/{tid}").status_code == 404
    assert b.get(f"/threads/{tid}/context").status_code == 404
    assert b.post(f"/threads/{tid}/compact").status_code == 404
    assert b.delete(f"/threads/{tid}").status_code == 404
    assert _chat(b, tid, "hola")[0] == 404
    assert b.post("/resume", json={"thread_id": tid, "decisions": [{"type": "approve"}]}).status_code == 404
    assert b.get("/threads").json()["threads"] == []
    assert b.get("/me/memories").json()["memories"] == []
    # un hilo inexistente responde igual que uno ajeno
    assert b.get("/history/no-existe").status_code == 404
    # las rutas con user_id del navegador no existen con cuentas
    a_uid = appdata.users.get_by_email("ana@ejemplo.com")["user_id"]
    assert b.get(f"/memories/{a_uid}").status_code == 404
    # el recuerdo quedó con el UUID de la sesión, no con el user_id que mandó el navegador
    mems = a.get("/me/memories").json()["memories"]
    assert [m["text"] for m in mems] == ["Vive en Mérida"]
    from assistant import memory
    assert memory.list_memories(store, "lo-que-diga-el-navegador") == []
    assert a.get(f"/threads/{tid}").status_code in (404, 405)  # no hay lectura directa de la fila


def test_logout_corta_el_acceso(app_ab):
    _, _, _, _, a, _ = app_ab
    assert a.post("/auth/logout").status_code == 200
    assert a.get("/threads").status_code == 401
    assert a.get("/auth/me").json()["user"] is None


def test_login_endpoint_generico_y_bloqueo(make_settings):
    from assistant.auth import LOCKED_ERROR, LOGIN_ERROR

    app, *_ = _app(make_settings)
    _login(app, "ana@ejemplo.com")
    c = TestClient(app, headers=ORIGIN)
    r1 = c.post("/auth/login", json={"email": "ana@ejemplo.com", "password": "mala-contraseña"})
    r2 = c.post("/auth/login", json={"email": "nadie@ejemplo.com", "password": "mala-contraseña"})
    assert r1.status_code == r2.status_code == 401 and r1.json() == r2.json() == {"detail": LOGIN_ERROR}
    for _ in range(4):  # 5 fallos del mismo correo (la IP aguanta 20)
        c.post("/auth/login", json={"email": "ana@ejemplo.com", "password": "mala-contraseña"})
    r = c.post("/auth/login", json={"email": "ana@ejemplo.com", "password": PW})
    assert r.status_code == 429 and r.json() == {"detail": LOCKED_ERROR}


def test_borrar_conversacion_borra_checkpoints_y_fila(app_ab):
    _, agent, appdata, _, a, _ = app_ab
    tid = a.post("/threads").json()["thread_id"]
    _chat(a, tid, "hola")
    assert agent.checkpointer.get_tuple({"configurable": {"thread_id": tid}}) is not None
    assert a.delete(f"/threads/{tid}").json() == {"deleted": tid}
    assert agent.checkpointer.get_tuple({"configurable": {"thread_id": tid}}) is None
    assert appdata.threads.get(tid) is None and a.get(f"/history/{tid}").status_code == 404


def test_borrar_cuenta_borra_todo_en_las_dos_bases(app_ab):
    from assistant import memory

    _, agent, appdata, store, a, b = app_ab
    ana = appdata.users.get_by_email("ana@ejemplo.com")
    hilos = []
    for texto in ["guarda: Vive en Mérida", "guarda: Tiene una perrita llamada Canela"]:
        tid = a.post("/threads").json()["thread_id"]
        _chat(a, tid, texto)
        hilos.append(tid)
    tid_b = b.post("/threads").json()["thread_id"]
    _chat(b, tid_b, "guarda: Vive en Monterrey")
    assert len(memory.list_memories(store, ana["user_id"])) == 2

    assert a.post("/auth/delete-account", json={"password": "incorrecta-123"}).status_code == 401
    r = a.post("/auth/delete-account", json={"password": PW})
    assert r.status_code == 200 and r.json()["threads"] == 2
    assert appdata.users.get(ana["user_id"]) is None and appdata.threads.list_for_user(ana["user_id"]) == []
    assert not [s for s in getattr(appdata.sessions, "rows", {}).values() if s["user_id"] == ana["user_id"]]
    assert all(agent.checkpointer.get_tuple({"configurable": {"thread_id": t}}) is None for t in hilos)
    assert memory.list_memories(store, ana["user_id"]) == []
    assert a.get("/threads").status_code == 401
    # B sigue intacto
    assert agent.checkpointer.get_tuple({"configurable": {"thread_id": tid_b}}) is not None
    assert [m["text"] for m in b.get("/me/memories").json()["memories"]] == ["Vive en Monterrey"]


def test_sin_cuentas_todo_sigue_como_antes(make_settings):
    from assistant.server import create_app

    app = create_app(agent=_app(make_settings)[1], settings=make_settings(), store=InMemoryStore())
    c = TestClient(app)
    assert c.get("/auth/me").json() == {"auth_enabled": False}
    assert c.get("/memories/usuario").status_code == 200
    assert c.post("/auth/login", json={"email": "a@b.co", "password": PW}).status_code == 404
