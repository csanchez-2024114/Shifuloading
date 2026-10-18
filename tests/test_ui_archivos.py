"""UI de archivos (FILES_ENABLED) en un navegador real con modelo falso: 0 tokens, sin Mongo. El botón 📎 solo aparece
si /files/config responde; el adjunto sube, se ve como chip, viaja con el mensaje y queda en el historial; un archivo
rechazado muestra el aviso en español."""
import socket
import threading
import time

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from conftest import FakeChat, FakeSearch, _settings, tool_call

sync_api = pytest.importorskip("playwright.sync_api")
pytest.importorskip("multipart")


def _serve(files_enabled: bool):
    import uvicorn

    from assistant.core.agent import build_agent
    from assistant.core.server import create_app
    from assistant.core.tools import build_tools

    s = _settings(files_enabled=files_enabled)
    llm = FakeChat(messages=iter([tool_call("search_in_file", {"query": "hola"}, "f1"), "El archivo saluda."] * 5))
    store = InMemoryStore()
    agent = build_agent(llm, build_tools(llm, s, search_fn=FakeSearch()), s, checkpointer=InMemorySaver(),
                        store=store)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(agent=agent, settings=s, store=store), host="127.0.0.1",
                                          port=port, log_level="warning"))
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


def test_sin_el_interruptor_no_hay_boton_de_adjuntar(browser):
    server, url = _serve(False)
    page, errors = browser.new_page(), []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(url)
    page.wait_for_timeout(600)
    assert not page.is_visible("#attach") and errors == []
    page.close()
    server.should_exit = True


def test_adjuntar_enviar_y_ver_el_archivo_en_el_historial(browser, tmp_path):
    server, url = _serve(True)
    page, errors = browser.new_page(), []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(url)
    page.wait_for_selector("#attach", state="visible")
    (tmp_path / "notas.txt").write_text("hola desde el archivo", encoding="utf-8")
    page.set_input_files("#fileinput", str(tmp_path / "notas.txt"))
    page.wait_for_function("() => document.querySelector('#filesbar').innerText.includes('📎 notas.txt')")
    page.fill("#input", "¿Qué dice el archivo?")
    page.click("#send")
    page.wait_for_function("() => document.body.innerText.includes('El archivo saluda.')", timeout=20000)
    assert "📎 notas.txt" in page.inner_text(".row.user .bubble")
    assert page.inner_text("#filesbar") == ""  # el adjunto se fue con el mensaje
    assert "Archivo leído" in page.inner_text("#messages") or "Búsqueda en el archivo" in page.inner_text("#messages")
    page.reload()
    page.wait_for_selector(".row.user .bubble")
    assert "📎 notas.txt" in page.inner_text(".row.user .bubble")
    (tmp_path / "falso.png").write_text("no soy png", encoding="utf-8")
    page.set_input_files("#fileinput", str(tmp_path / "falso.png"))
    page.wait_for_function("() => document.querySelector('#filesbar').innerText.includes('no corresponde')")
    assert errors == []
    page.close()
    server.should_exit = True
