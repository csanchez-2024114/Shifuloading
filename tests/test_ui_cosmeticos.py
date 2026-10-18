"""Cosméticos de la UI en un navegador real con modelo falso (0 tokens, sin Mongo):
(a) un 4xx muestra el `detail` en español, sin el JSON crudo;
(b) la tarjeta de deep_research aprobada pasa de "✓ Investigando…" a "✓ Aprobada" al terminar el turno;
(d) un /history lento que responde después de enviar ya no borra el mensaje recién enviado."""
import socket
import threading
import time

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from conftest import FakeChat, FakeSearch, _settings, tool_call

sync_api = pytest.importorskip("playwright.sync_api")


class Guion(FakeChat):
    """"estudio" pide deep_research (sin pedirlo explícitamente: tarjeta); el investigador responde un resumen; tras
    una herramienta, la respuesta final. Cualquier otro mensaje: "Respuesta rápida."."""

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        last = messages[-1]
        text = str(last.content)
        if last.type == "tool":
            self.messages = iter(["Informe final."])
        elif "estudio" in text:
            self.messages = iter([tool_call("deep_research", {"task": "leyes de IA"}, f"d{time.time_ns()}")])
        elif "leyes de IA" in text:
            self.messages = iter(["RESUMEN del investigador."])
        else:
            self.messages = iter(["Respuesta rápida."])
        yield from super()._stream(messages, stop=stop, run_manager=run_manager, **kwargs)


def _serve(**overrides):
    import uvicorn

    from assistant.core.agent import build_agent
    from assistant.core.server import create_app
    from assistant.core.tools import build_tools

    s = _settings(**overrides)
    llm = Guion(messages=iter([]))
    agent = build_agent(llm, build_tools(llm, s, search_fn=FakeSearch()), s, checkpointer=InMemorySaver(),
                        store=InMemoryStore())
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
    return server, f"http://127.0.0.1:{port}/"


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


def _page(browser, url, thread):
    page, errors = browser.new_page(), []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"{url}?thread={thread}")
    page.wait_for_timeout(500)
    return page, errors


def _idle(page):
    page.wait_for_function("() => !document.querySelector('#input').disabled", timeout=20000)


def test_a_un_413_muestra_el_aviso_sin_json(browser):
    server, url = _serve(max_message_chars=20)
    page, errors = _page(browser, url, "cos-a")
    page.fill("#input", "x" * 30)
    page.click("#send")
    page.wait_for_function("() => document.body.innerText.includes('demasiado largo')")
    msgs = page.inner_text("#messages")
    assert "⚠️ El mensaje es demasiado largo: el máximo es 20 caracteres (MAX_MESSAGE_CHARS)." in msgs
    assert '{"detail"' not in msgs and "Error del servidor (413)" not in msgs and errors == []
    page.close()
    server.should_exit = True


def test_b_tarjeta_aprobada_dice_aprobada_al_terminar(browser):
    server, url = _serve(model_call_limit=0)
    page, errors = _page(browser, url, "cos-b")
    page.fill("#input", "hazme un estudio de las leyes")
    page.click("#send")
    page.wait_for_selector("text=Sí, investiga")
    page.click("text=Sí, investiga")
    page.wait_for_function("() => document.body.innerText.includes('Informe final.')", timeout=20000)
    _idle(page)
    result = page.inner_text(".approval .result")
    assert result == "✓ Aprobada" and errors == []
    page.close()
    server.should_exit = True


def test_d_un_historial_lento_no_borra_el_mensaje_enviado(browser, monkeypatch):
    from assistant.core import agent as agent_mod

    original = agent_mod.get_history

    def lenta(*args, **kwargs):  # lee el hilo (aún vacío) y responde tarde, como Atlas en la prueba real
        out = original(*args, **kwargs)
        time.sleep(1.5)
        return out

    monkeypatch.setattr(agent_mod, "get_history", lenta)
    server, url = _serve()
    page, errors = browser.new_page(), []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"{url}?thread=cos-d")  # sin esperar: se envía mientras /history sigue en curso
    page.fill("#input", "hola")
    page.press("#input", "Enter")
    page.wait_for_timeout(3000)  # el /history lento ya respondió
    msgs = page.inner_text("#messages")
    assert "hola" in msgs and "Respuesta rápida." in msgs and "Cargando conversación" not in msgs
    assert "¿En qué te ayudo?" not in msgs and errors == []
    page.close()
    server.should_exit = True
