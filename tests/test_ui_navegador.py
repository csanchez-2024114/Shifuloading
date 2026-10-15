"""Interfaz en un navegador real (Playwright + Edge/Chromium ya instalados; se salta si no hay). App real con un modelo
falso controlable: 0 tokens, sin Mongo. Clics con el ratón (page.mouse), como una persona: sin las esperas de
Playwright, que no dejan hacer clic en un botón deshabilitado."""
import socket
import threading
import time

import pytest
from langchain_core.messages import AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from conftest import FakeChat, FakeSearch

sync_api = pytest.importorskip("playwright.sync_api")


class Controlable(FakeChat):
    """El mensaje del usuario decide: "lento" (palabra a palabra), "cola" (texto rápido pero el stream tarda en
    cerrarse, como cuando el servidor aún guarda el checkpoint), "tope" (pasa TURN_TOKEN_CAP), "correo" (pide una
    herramienta con aprobación). Cualquier otro: "ok"."""

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        last = next((m for m in reversed(messages) if m.type == "human"), None)
        text = str(last.content) if last else ""
        answered = messages[-1].type == "tool"
        call = None
        if "tope" in text and not answered:
            call = ({"name": "calculator", "args": '{"expression": "1+1"}'}, 90000)
        elif "correo" in text and not answered:
            call = ({"name": "send_simulated_email", "args": '{"recipient": "a@b.c", "subject": "s", "body": "b"}'}, 0)
        elif "rechazada" in text and not answered:  # 45k de 50k: la reserva de la búsqueda ya no cabe en el tope
            call = ({"name": "web_search", "args": '{"query": "vuelos"}'}, 45000)
        elif "tres" in text and not answered:  # tres búsquedas en paralelo: solo se ejecuta la primera
            calls = [{"name": "web_search", "args": f'{{"query": "q{i}"}}', "id": f"w{i}{time.time_ns()}", "index": i,
                      "type": "tool_call_chunk"} for i in range(3)]
            yield ChatGenerationChunk(message=AIMessageChunk(content="", tool_call_chunks=calls, chunk_position="last"))
            return
        if call:
            usage = {"input_tokens": call[1], "output_tokens": 0, "total_tokens": call[1]}
            yield ChatGenerationChunk(message=AIMessageChunk(content="", usage_metadata=usage, chunk_position="last",
                                                             tool_call_chunks=[{**call[0], "id": f"c{time.time_ns()}",
                                                                                "index": 0, "type": "tool_call_chunk"}]))
            return
        for w in (["respuesta", "lenta"] * 6 if "lento" in text else ["ok"]):
            if "lento" in text:
                time.sleep(0.25)
            chunk = ChatGenerationChunk(message=AIMessageChunk(content=w + " "))
            if run_manager:
                run_manager.on_llm_new_token(w + " ", chunk=chunk)
            yield chunk
        if "cola" in text:
            time.sleep(2)
        yield ChatGenerationChunk(message=AIMessageChunk(content="", chunk_position="last"))


@pytest.fixture(scope="module")
def base_url():
    import uvicorn

    from assistant.agent import build_agent
    from assistant.server import create_app
    from assistant.tools import build_tools
    from conftest import _settings

    s = _settings(turn_token_cap=50000, model_call_limit=0, enable_hitl_demo=True)
    llm = Controlable(messages=iter([]))
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
    yield f"http://127.0.0.1:{port}/"
    server.should_exit = True


@pytest.fixture(scope="module")
def page(base_url):
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
        yield pg
        browser.close()


def _tid(page):
    return page.evaluate("new URL(location.href).searchParams.get('thread')")


def _idle(page):
    page.wait_for_function("() => !document.querySelector('#input').disabled", timeout=20000)


def _click_new(page):
    box = page.locator("#newbtn").bounding_box()
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)


def _send(page, text):
    page.fill("#input", text)
    page.press("#input", "Enter")


def _fresh(page, base_url, times):
    page.goto(base_url)
    page.wait_for_timeout(300)
    page.evaluate("t => { const cb = document.querySelector('#showtimes'); if (cb.checked !== t) cb.click(); }", times)
    _click_new(page)
    page.wait_for_timeout(150)


def _ultimo_texto_contiene(page, palabra):
    page.wait_for_function("w => { const r = [...document.querySelectorAll('#messages .row.assistant')].pop();"
                           " return r && r.textContent.includes(w); }", arg=palabra, timeout=10000)


def _abre_hilo_nuevo(page, antes):
    page.wait_for_function("a => new URL(location.href).searchParams.get('thread') !== a", arg=antes, timeout=15000)
    _idle(page)
    nuevo = _tid(page)
    assert page.locator("#threadid").inner_text() == nuevo  # el id del hilo actual siempre a la vista
    assert page.locator("#messages .row").count() == 0
    assert "queued" not in (page.get_attribute("#newbtn", "class") or "")
    return nuevo


@pytest.mark.parametrize("times", [True, False], ids=["con-tiempos", "sin-tiempos"])
@pytest.mark.parametrize("caso", ["durante-stream", "texto-visible-stream-abierto", "al-terminar", "tras-tope",
                                  "tras-error-de-red", "con-aprobacion-pendiente"])
def test_nueva_conversacion_nunca_se_descarta(page, base_url, caso, times):
    _fresh(page, base_url, times)
    antes = _tid(page)
    assert page.locator("#threadid").inner_text() == antes
    if caso == "durante-stream":
        _send(page, "lento")
        page.wait_for_timeout(800)
        _click_new(page)
        # se ve que quedó en cola y no interrumpe la respuesta en curso
        assert "queued" in page.get_attribute("#newbtn", "class")
        assert page.locator("#newbtn .long").inner_text() == "Nueva al terminar…"
        assert _tid(page) == antes
    elif caso == "texto-visible-stream-abierto":
        _send(page, "cola")
        _ultimo_texto_contiene(page, "ok")
        _click_new(page)
    elif caso == "al-terminar":
        _send(page, "hola")
        _idle(page)
        _click_new(page)
    elif caso == "tras-tope":
        _send(page, "tope")
        _ultimo_texto_contiene(page, "Detuve este mensaje")
        _idle(page)
        _click_new(page)
    elif caso == "tras-error-de-red":
        page.route("**/chat", lambda r: r.abort("failed"))
        try:
            _send(page, "hola")
            page.wait_for_selector("#messages .errmsg", timeout=10000)
            _idle(page)
            _click_new(page)
        finally:
            page.unroute("**/chat")
    elif caso == "con-aprobacion-pendiente":
        _send(page, "correo")
        page.wait_for_selector("#messages .approval", timeout=10000)
        _click_new(page)
    _abre_hilo_nuevo(page, antes)


def test_segundo_clic_cancela_la_cola(page, base_url):
    _fresh(page, base_url, True)
    antes = _tid(page)
    _send(page, "lento")
    page.wait_for_timeout(600)
    _click_new(page)
    _click_new(page)
    assert "queued" not in (page.get_attribute("#newbtn", "class") or "")
    _idle(page)
    page.wait_for_timeout(500)
    assert _tid(page) == antes


def _chips(page):
    return page.evaluate("() => [...[...document.querySelectorAll('#messages .row.assistant')].pop()"
                         ".querySelectorAll('.chip')].map(c => ({cls: c.className, text: c.textContent}))")


def test_busqueda_no_realizada_no_se_marca_como_hecha_ni_al_recargar(page, base_url):
    _fresh(page, base_url, True)
    thread = _tid(page)
    _send(page, "busca vuelos rechazada")
    _idle(page)
    [chip] = [c for c in _chips(page) if "Búsqueda" in c["text"]]
    assert "skipped" in chip["cls"] and "Búsqueda no realizada" in chip["text"] and "✓" not in chip["text"]
    page.goto(f"{base_url}?thread={thread}")  # recargar: el historial muestra lo mismo
    linea = page.locator("#messages .toolline").first
    linea.wait_for(timeout=10000)
    assert linea.inner_text() == "🔎 Búsqueda no realizada" and "skipped" in linea.get_attribute("class")


def test_tres_busquedas_en_paralelo_muestran_las_no_realizadas(page, base_url):
    _fresh(page, base_url, True)
    _send(page, "busca tres cosas")
    _idle(page)
    [chip] = [c for c in _chips(page) if "Búsqueda" in c["text"]]
    assert "done" in chip["cls"] and "✓" in chip["text"] and "2 no realizadas" in chip["text"]
    assert "×3" not in chip["text"]  # solo una se ejecutó
