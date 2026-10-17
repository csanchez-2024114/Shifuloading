"""Cuentas en un navegador real (Playwright; se salta si no hay navegador): registro, chat, lista de conversaciones,
salir, entrar de nuevo, aislamiento entre dos usuarios y borrado de conversación. App real con AUTH_ENABLED=1, modelo
falso controlable y base de negocio en memoria. 0 tokens, sin Mongo."""
import socket
import threading
import time

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from conftest import FakeSearch

sync_api = pytest.importorskip("playwright.sync_api")

from test_ui_navegador import Controlable, _idle, _send  # noqa: E402

PW = "contraseña-larga-1"


class FakeMailer:
    def __init__(self):
        self.sent = []

    def send(self, to, subject, body):
        self.sent.append({"to": to, "subject": subject, "body": body})


MAILER = FakeMailer()  # correos de recuperación enviados por la app de este módulo


@pytest.fixture(scope="module")
def base_url():
    import uvicorn

    from assistant.agent import build_agent
    from assistant.appdata.memory import MemoryAppData
    from assistant.server import create_app
    from assistant.tools import build_tools
    from conftest import _settings

    s = _settings(model_call_limit=0, auth_enabled=True, password_reset_enabled=True)
    llm = Controlable(messages=iter([]))
    store = InMemoryStore()
    agent = build_agent(llm, build_tools(llm, s, search_fn=FakeSearch()), s, checkpointer=InMemorySaver(), store=store)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(agent=agent, settings=s, store=store, appdata=MemoryAppData(),
                                                     mailer=MAILER),
                                          host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/"
    server.should_exit = True


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


def _register(page, name, email):
    page.wait_for_selector("#authview", state="visible")
    page.click("#authtoggle")
    page.fill("#authname", name)
    page.fill("#authemail", email)
    page.fill("#authpass", PW)
    page.click("#authsubmit")
    page.wait_for_selector("#authview", state="hidden")
    page.wait_for_function("() => document.querySelector('#whoami').textContent.length > 0")


def _options(page):
    return page.eval_on_selector_all("#thread option", "els => els.map(e => e.value)")


def test_registro_chat_salir_entrar_y_aislamiento(base_url, browser):
    ctx_a = browser.new_context()
    a = ctx_a.new_page()
    a.on("dialog", lambda d: d.accept("  Viaje a   Oaxaca ") if d.type == "prompt" else d.accept())
    a.goto(base_url)
    assert a.is_visible("#authview") and not a.is_visible("#composer")  # sin sesión no se ve el chat
    _register(a, "Ana", "ana@ejemplo.com")
    assert a.inner_text("#whoami") == "Ana" and a.is_visible("#composer")
    cookies = ctx_a.cookies()
    sesion = next(c for c in cookies if c["name"] == "agente0_session")
    assert sesion["httpOnly"] and sesion["sameSite"] == "Lax"
    assert a.evaluate("document.cookie").find("agente0_session") < 0  # JavaScript no la ve

    _send(a, "hola desde Ana")
    _idle(a)
    a.wait_for_function("() => document.querySelectorAll('.row.assistant').length > 0")
    hilo_a = a.evaluate("new URL(location.href).searchParams.get('thread')")
    assert _options(a) == [hilo_a]

    # salir: vuelve el login y no queda acceso
    a.click("#logoutbtn")
    a.wait_for_selector("#authview", state="visible")
    assert a.request.get(base_url + "threads").status == 401

    # entrar de nuevo: su conversación sigue ahí
    a.fill("#authemail", "ana@ejemplo.com")
    a.fill("#authpass", "mala-contraseña")
    a.click("#authsubmit")
    a.wait_for_function("() => document.querySelector('#autherr').textContent.length > 0")
    assert a.inner_text("#autherr") == "Correo o contraseña incorrectos."
    a.fill("#authpass", PW)
    a.click("#authsubmit")
    a.wait_for_selector("#authview", state="hidden")
    a.wait_for_function("() => document.querySelectorAll('.row.user').length > 0")
    assert "hola desde Ana" in a.inner_text("#messages") and _options(a) == [hilo_a]

    # otro usuario en otro navegador: no ve nada de Ana
    ctx_b = browser.new_context()
    b = ctx_b.new_page()
    b.goto(base_url + f"?thread={hilo_a}")
    _register(b, "Beto", "beto@ejemplo.com")
    b.wait_for_function("() => document.querySelector('#thread').options.length > 0")
    assert hilo_a not in _options(b) and "hola desde Ana" not in b.inner_text("#messages")
    assert b.request.get(base_url + f"history/{hilo_a}").status == 404
    assert b.request.get(base_url + f"threads/{hilo_a}/context").status == 404

    # renombrar desde la lista de conversaciones: el nombre se guarda en el servidor y sobrevive a recargar
    a.click("#renthreadbtn")
    a.wait_for_function("() => document.querySelector('#thread').selectedOptions[0].textContent.startsWith('Viaje a Oaxaca')")
    assert a.request.get(base_url + "threads").json()["threads"][0]["title"] == "Viaje a Oaxaca"
    a.reload()
    a.wait_for_function("() => (document.querySelector('#thread').selectedOptions[0] || {}).textContent?.startsWith('Viaje a Oaxaca')")
    assert b.request.patch(base_url + f"threads/{hilo_a}", data={"title": "mío"}).status in (403, 404)

    # borrar la conversación (con confirmación)
    a.click("#delthreadbtn")
    a.wait_for_function(f"() => !Array.from(document.querySelectorAll('#thread option')).some(o => o.value === '{hilo_a}')")
    assert a.request.get(base_url + f"history/{hilo_a}").status == 404
    ctx_a.close()
    ctx_b.close()


def test_recuperar_contraseña_por_correo(base_url, browser):
    import re

    ctx = browser.new_context()
    p = ctx.new_page()
    p.goto(base_url)
    _register(p, "Caro", "caro@ejemplo.com")
    p.click("#logoutbtn")
    p.wait_for_selector("#authview", state="visible")

    # pedir el enlace: respuesta genérica
    p.fill("#authemail", "caro@ejemplo.com")
    p.click("#forgotbtn")
    assert p.is_visible("#recoverform") and not p.is_visible("#authform")
    assert p.input_value("#recoveremail") == "caro@ejemplo.com"
    p.click("#recoversubmit")
    p.wait_for_function("() => document.querySelector('#recovermsg').textContent.length > 0")
    assert p.inner_text("#recovermsg").startswith("Si el correo está registrado")
    [mail] = [m for m in MAILER.sent if m["to"] == "caro@ejemplo.com"]
    token = re.search(r"#reset=([A-Za-z0-9_-]+)", mail["body"]).group(1)

    # abrir el enlace: pide la contraseña nueva y quita el token de la barra
    q = ctx.new_page()
    q.goto(f"{base_url}#reset={token}")
    q.wait_for_selector("#recoverpass", state="visible")
    assert "reset" not in q.url and q.inner_text("#authtitle") == "Elige una contraseña nueva"
    q.fill("#recoverpass", "corta")
    q.click("#recoversubmit")
    q.wait_for_function("() => document.querySelector('#recovererr').textContent.length > 0")
    q.fill("#recoverpass", "contraseña-nueva-123")
    q.click("#recoversubmit")
    q.wait_for_function("() => document.querySelector('#authinfo').textContent.includes('Contraseña cambiada')")
    assert q.is_visible("#authform")

    # entra con la nueva; la vieja ya no sirve
    q.fill("#authemail", "caro@ejemplo.com")
    q.fill("#authpass", PW)
    q.click("#authsubmit")
    q.wait_for_function("() => document.querySelector('#autherr').textContent.length > 0")
    q.fill("#authpass", "contraseña-nueva-123")
    q.click("#authsubmit")
    q.wait_for_selector("#authview", state="hidden")
    assert q.inner_text("#whoami") == "Caro"
    ctx.close()
