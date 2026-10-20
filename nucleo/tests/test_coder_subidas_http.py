"""Subidas de recursos del codificador por HTTP (POST/GET/DELETE /coder/uploads): sesión + CSRF, el user_id sale
siempre de la sesión (el del formulario se ignora), S18 por HTTP (415), tope de bytes y cuota (413), y una subida
ajena da lo mismo que una inexistente. Sin tokens."""
import io
import sys

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from assistant.core.config import ConfigError
from conftest import _settings, build_test_agent

pytest.importorskip("PIL")
pytest.importorskip("multipart")
from PIL import Image  # noqa: E402

ORIGIN = {"Origin": "http://testserver"}
PW = "contraseña-larga-1"
CODER = dict(auth_enabled=True, coder_enabled=True, trusted_hosts=("127.0.0.1", "testserver"))


def _png(size=(30, 20)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, (10, 120, 200)).save(out, format="PNG")
    return out.getvalue()


def _app(**overrides):
    from assistant.core import server
    from assistant.core.appdata.memory import MemoryAppData
    from assistant.core.profile import load_profile

    s = _settings(**{**CODER, **overrides})
    appdata = MemoryAppData()
    app = server.create_app(agent=build_test_agent(["x"], s, checkpointer=InMemorySaver()), settings=s,
                            store=InMemoryStore(), appdata=appdata, profile=load_profile("coder"))
    return app, appdata


def _login(app, email):
    c = TestClient(app, headers=ORIGIN)
    r = c.post("/auth/register", json={"email": email, "password": PW, "display_name": "U"})
    c.headers["X-CSRF-Token"] = r.json()["csrf"]
    return c


def _up(c, data: bytes, name: str, **form):
    return c.post("/coder/uploads", files={"file": (name, data, "application/octet-stream")}, data=form)


def test_subir_listar_y_borrar_con_el_usuario_de_la_sesion():
    app, appdata = _app()
    a, b = _login(app, "ana@ejemplo.com"), _login(app, "beto@ejemplo.com")
    beto = appdata.users.get_by_email("beto@ejemplo.com")["user_id"]
    r = _up(a, _png(), "logo.png", user_id=beto)  # intenta subirlo a nombre de Beto
    assert r.status_code == 200, r.text
    up = r.json()
    assert up["name"] == "logo.png" and up["mime"] == "image/png" and (up["width"], up["height"]) == (30, 20)
    assert "user_id" not in up
    assert [u["upload_id"] for u in a.get("/coder/uploads").json()["uploads"]] == [up["upload_id"]]
    assert b.get("/coder/uploads").json() == {"uploads": []}  # el user_id del formulario se ignoró
    ana = appdata.users.get_by_email("ana@ejemplo.com")["user_id"]
    assert app.state.coder.list_uploads(ana)[0]["upload_id"] == up["upload_id"]
    # borrar: una ajena y una inexistente responden igual
    ajena = b.delete(f"/coder/uploads/{up['upload_id']}")
    inexistente = a.delete("/coder/uploads/up_0000000000000000")
    assert ajena.status_code == inexistente.status_code == 404 and ajena.json() == inexistente.json()
    assert a.delete(f"/coder/uploads/{up['upload_id']}").json() == {"deleted": up["upload_id"]}
    assert a.get("/coder/uploads").json() == {"uploads": []}


def test_sesion_y_csrf():
    app, _ = _app()
    a = _login(app, "ana@ejemplo.com")
    sin_csrf = TestClient(app, headers=ORIGIN, cookies=a.cookies)
    assert _up(sin_csrf, _png(), "a.png").status_code == 403
    anon = TestClient(app, headers=ORIGIN)
    assert _up(anon, _png(), "a.png").status_code == 401
    assert anon.get("/coder/uploads").status_code == 401
    otro_origen = TestClient(app, headers={"Origin": "http://evil.example", "X-CSRF-Token": a.headers["X-CSRF-Token"]},
                             cookies=a.cookies)
    assert _up(otro_origen, _png(), "a.png").status_code == 403


@pytest.mark.parametrize("data, name, status, texto", [
    (_png(), "foto.jpg", 415, "no corresponde a su extensión"),  # S18: PNG con extensión .jpg
    (b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>', "x.svg", 415, "SVG no"),  # S18
    (_png() + b"<script>fetch('https://evil.example')</script>", "a.png", 415, "código o marcas"),  # S18 políglota
    (b"<h1>x</h1>", "pagina.html", 415, "no se permite"),
    (b"", "vacio.txt", 422, "vacío"),
])
def test_rechazos_por_http(data, name, status, texto):
    app, _ = _app()
    a = _login(app, "ana@ejemplo.com")
    r = _up(a, data, name)
    assert r.status_code == status and texto in r.json()["detail"], r.text
    assert a.get("/coder/uploads").json() == {"uploads": []}


def test_tope_de_bytes_y_cuota():
    app, _ = _app(coder_max_asset_bytes=1000)
    a = _login(app, "ana@ejemplo.com")
    r = _up(a, b"x" * 1001, "grande.txt")
    assert r.status_code == 413 and "1000 bytes" in r.json()["detail"]
    app, _ = _app(coder_max_user_bytes=1500)
    a = _login(app, "ana@ejemplo.com")
    assert _up(a, b"x" * 1000, "uno.txt").status_code == 200
    r = _up(a, b"y" * 1000, "dos.txt")
    assert r.status_code == 413 and "espacio de proyectos" in r.json()["detail"]


def test_sin_pillow_el_codificador_no_arranca(monkeypatch):
    monkeypatch.setitem(sys.modules, "PIL", None)  # como si no estuviera instalado
    with pytest.raises(ConfigError, match="falta PIL"):
        _app()
