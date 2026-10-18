"""UI de 👍/👎 (FEEDBACK_ENABLED) en un navegador real con modelo falso: 0 tokens, sin Mongo. Con el interruptor en 0
no hay botones ni ningún POST a /feedback; con 1, 👍 guarda 1 y 👎 lo cambia a -1, sin errores de JavaScript."""
import socket
import threading
import time

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from conftest import FakeChat, FakeSearch, _settings

sync_api = pytest.importorskip("playwright.sync_api")
ON = {"feedback_enabled": True, "trace_metadata": True, "turn_metrics": True}


def _serve(flags: dict):
    import uvicorn

    from assistant.core.agent import build_agent
    from assistant.core.appdata.memory import MemoryAppData
    from assistant.core.server import create_app
    from assistant.core.tools import build_tools

    s = _settings(**flags)
    llm = FakeChat(messages=iter(["Respuesta de prueba."] * 5))
    store, appdata = InMemoryStore(), MemoryAppData()
    agent = build_agent(llm, build_tools(llm, s, search_fn=FakeSearch()), s, checkpointer=InMemorySaver(),
                        store=store)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(agent=agent, settings=s, store=store, appdata=appdata),
                                          host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    return server, f"http://127.0.0.1:{port}/", appdata


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


def _turn(page, url):
    page.goto(url + "?thread=fb1")
    page.wait_for_timeout(500)
    page.fill("#input", "hola")
    page.click("#send")
    page.wait_for_function("() => document.body.innerText.includes('Respuesta de prueba.')", timeout=20000)
    page.wait_for_function("() => !document.querySelector('#input').disabled", timeout=20000)
    page.wait_for_timeout(300)


def test_sin_el_interruptor_no_hay_botones_ni_post_a_feedback(browser):
    server, url, appdata = _serve({})
    page, errors, posts = browser.new_page(), [], []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("request", lambda r: posts.append(r.url) if r.method == "POST" and "/feedback" in r.url else None)
    _turn(page, url)
    assert page.locator(".feedback button").count() == 0
    assert posts == [] and errors == [] and appdata.feedback.rows == {}
    page.close()
    server.should_exit = True


def test_pulgar_arriba_y_luego_abajo(browser):
    server, url, appdata = _serve(ON)
    page, errors = browser.new_page(), []
    page.on("pageerror", lambda e: errors.append(str(e)))
    _turn(page, url)
    up, down = ".feedback button[aria-label='Me sirvió']", ".feedback button[aria-label='No me sirvió']"
    page.click(up)
    page.wait_for_function(f"() => document.querySelector(\"{up}\").getAttribute('aria-pressed') === 'true'")
    [row] = appdata.feedback.rows.values()
    assert row["score"] == 1 and row["thread_id"] == "fb1"
    [metric] = appdata.turn_metrics.rows.values()
    assert row["run_id"] == metric["run_id"]
    page.click(down)
    page.wait_for_function(f"() => document.querySelector(\"{down}\").getAttribute('aria-pressed') === 'true'")
    assert [r["score"] for r in appdata.feedback.rows.values()] == [-1]
    assert page.get_attribute(up, "aria-pressed") == "false" and errors == []
    page.close()
    server.should_exit = True
