"""Medidor de contexto en un navegador real (Playwright; se salta si no hay navegador). App real con el modelo falso
controlable y una ventana pequeña para pasar por ámbar y rojo en pocos turnos. 0 tokens, sin Mongo."""
import socket
import threading
import time

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from conftest import FakeChat, FakeSearch

sync_api = pytest.importorskip("playwright.sync_api")

from test_ui_navegador import Controlable, _click_new, _idle, _send, _tid  # noqa: E402

LARGO = "palabra " * 200  # ~400 tokens por mensaje


@pytest.fixture(scope="module")
def app_info():
    import uvicorn

    from assistant.agent import build_agent, fixed_prompt_tokens
    from assistant.server import create_app
    from assistant.tools import build_tools
    from conftest import _settings

    s0 = _settings(model_call_limit=0)
    llm = Controlable(messages=iter([]))
    base = fixed_prompt_tokens(build_tools(llm, s0, search_fn=FakeSearch()), settings=s0)
    window = base * 2  # una conversación nueva empieza en ~50%: ámbar (70%) y rojo (85%) en pocos turnos
    s = _settings(model_call_limit=0, context_window_tokens=window, compact_keep_pct=10)
    summ = FakeChat(messages=iter(["- El usuario envió varios mensajes largos de prueba."] * 20))
    agent = build_agent(llm, build_tools(llm, s, search_fn=FakeSearch()), s, checkpointer=InMemorySaver(),
                        store=InMemoryStore(), summarizer=summ)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(agent=agent, settings=s, store=InMemoryStore()),
                                          host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield {"url": f"http://127.0.0.1:{port}/", "base": agent.base_context_tokens, "window": window}
    server.should_exit = True


@pytest.fixture(scope="module")
def page(app_info):
    with sync_api.sync_playwright() as p:
        browser = None
        for kw in ({"channel": "msedge"}, {"channel": "chrome"}, {}):
            try:
                browser = p.chromium.launch(headless=True, **kw)
                break
            except Exception:  # noqa: BLE001 - probar el siguiente navegador
                continue
        if browser is None:
            pytest.skip("no hay navegador para Playwright")
        pg = browser.new_page()
        pg.on("dialog", lambda d: d.accept())  # confirmación de "Compactar ahora"
        yield pg
        browser.close()


def _tokens(page) -> int:
    return int(page.get_attribute("#ctxmeter", "data-tokens") or 0)


def _level(page) -> str:
    return page.get_attribute("#ctxmeter", "data-level")


def _wait_tokens(page, cond, timeout=10000):
    page.wait_for_function(f"() => {{ const t = +document.querySelector('#ctxmeter').dataset.tokens; return {cond}; }}",
                           timeout=timeout)


def test_medidor_sube_cambia_de_color_se_conserva_compacta_y_no_se_hereda(page, app_info):
    page.goto(app_info["url"])
    _click_new(page)
    _wait_tokens(page, f"t === {app_info['base']}")  # conversación nueva: contexto base (prompt + herramientas)
    assert "estimado" in page.inner_text("#ctxtext") and _level(page) == "ok"
    assert page.inner_text("#ctxtext").startswith("Contexto: ~")
    assert not page.locator("#compactbtn").is_hidden()

    valores, niveles = [_tokens(page)], [_level(page)]
    for i in range(8):
        _send(page, f"mensaje {i} {LARGO}")
        _idle(page)
        _wait_tokens(page, f"t > {valores[-1]}")  # el medidor sube tras cada turno
        valores.append(_tokens(page))
        niveles.append(_level(page))
        if niveles[-1] == "crit":
            break
    assert valores == sorted(valores) and len(set(valores)) == len(valores)
    assert "warn" in niveles and niveles[-1] == "crit", niveles  # ámbar y luego rojo
    assert niveles.index("warn") < niveles.index("crit")
    pct = 100 * valores[-1] / app_info["window"]
    assert f"({round(pct)}%)" in page.inner_text("#ctxtext")
    assert "Total consumido" in page.get_attribute("#ctxmeter", "title")

    # se conserva al recargar (sale del checkpoint)
    thread = _tid(page)
    page.reload()
    _wait_tokens(page, f"t === {valores[-1]}")
    assert _level(page) == "crit" and _tid(page) == thread

    # "Compactar ahora": marca en el hilo y el valor baja
    box = page.locator("#compactbtn").bounding_box()
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.wait_for_selector(".sys.compacted", timeout=10000)
    marca = page.inner_text(".sys.compacted")
    assert marca.startswith("🗜️ Conversación compactada:") and "→" in marca
    _wait_tokens(page, f"t < {valores[-1]}")
    assert _level(page) != "crit"

    # una conversación nueva no hereda el valor
    compactado = _tokens(page)
    _click_new(page)
    _wait_tokens(page, f"t === {app_info['base']}")
    assert _tokens(page) != compactado and _level(page) == "ok"
