"""Sandbox del codificador (origen aislado), sin navegador: CSP y cabeceras exactas, sin Set-Cookie, la Cookie entrante
no cambia nada, host ajeno 400, el 404 es idéntico byte a byte para todo lo que no se sirve (token caducado, ajeno,
inexistente, mal formado, ruta fuera de la versión...) y los tokens inválidos repetidos terminan en 429 sin revelar si
el token existía. Sin tokens de modelo."""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from assistant.core.coder import projects as projects_mod
from assistant.core.coder.memory import MemoryCoderRepo
from assistant.core.coder.projects import Projects
from assistant.core.coder.sandbox import create_sandbox_app
from conftest import _settings

ORIGIN = "http://127.0.0.2:8100"
A, B = "usuario-a", "usuario-b"
EXPECTED_SECURITY = {
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "cross-origin-opener-policy": "same-origin",
    "permissions-policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    "cache-control": "no-store",
}


def _expected_csp(token: str) -> str:
    b = f"{ORIGIN}/p/{token}/"
    return (f"sandbox allow-scripts; default-src 'none'; script-src {b} 'unsafe-inline'; style-src {b} 'unsafe-inline'; "
            f"img-src {b} data: blob:; media-src {b}; font-src {b}; connect-src {b}__data/; form-action 'none'; "
            "frame-src 'none'; child-src 'none'; worker-src 'none'; object-src 'none'; base-uri 'none'; "
            "frame-ancestors http://127.0.0.1:* https://127.0.0.1:* http://testserver:* https://testserver:*")


class Env:
    def __init__(self, **overrides):
        self.settings = _settings(coder_enabled=True, auth_enabled=True, trusted_hosts=("127.0.0.1", "testserver"),
                                  **overrides)
        self.projects = Projects(MemoryCoderRepo(), self.settings)
        self.app = create_sandbox_app(self.settings, self.projects)
        self.client = TestClient(self.app, base_url=ORIGIN)
        self.pid = self.projects.create(A, "x")["project_id"]
        self.projects.write_file(A, self.pid, "index.html", "<h1>hola</h1><script src='js/app.js'></script>")
        self.projects.write_file(A, self.pid, "js/app.js", "console.log(1)")
        self.token = self.projects.issue_preview(A, self.pid)["token"]


@pytest.fixture
def env():
    return Env()


def _snapshot(r) -> tuple:
    return r.status_code, r.content, sorted(r.headers.items())


def test_sirve_la_version_con_csp_y_cabeceras_exactas(env):
    r = env.client.get(f"/p/{env.token}/index.html")
    assert r.status_code == 200 and r.text.startswith("<h1>hola</h1>")
    assert r.headers["content-type"] == "text/html; charset=utf-8"
    assert r.headers["content-security-policy"] == _expected_csp(env.token)
    for k, v in EXPECTED_SECURITY.items():
        assert r.headers[k] == v
    assert r.headers["access-control-allow-origin"] == "*"
    assert "set-cookie" not in r.headers and "server" not in r.headers
    assert "access-control-allow-credentials" not in r.headers
    assert _snapshot(env.client.get(f"/p/{env.token}/")) == _snapshot(r)  # / sirve index.html
    js = env.client.get(f"/p/{env.token}/js/app.js")
    assert js.headers["content-type"] == "text/javascript; charset=utf-8" and js.text == "console.log(1)"
    assert env.client.head(f"/p/{env.token}/index.html").status_code == 200


def test_la_cookie_entrante_no_cambia_nada_y_nunca_hay_set_cookie(env):
    sin = env.client.get(f"/p/{env.token}/index.html")
    con = env.client.get(f"/p/{env.token}/index.html", headers={"Cookie": "agente0_session=secreta; otra=1"})
    assert _snapshot(con) == _snapshot(sin)
    falla = env.client.get("/p/no-existe/index.html", headers={"Cookie": "agente0_session=secreta"})
    assert "set-cookie" not in falla.headers and "secreta" not in falla.text


@pytest.mark.parametrize("base", ["http://127.0.0.1:8100", "http://localhost:8100", "http://evil.example",
                                  "http://127.0.0.2.evil.example"])
def test_host_ajeno_400(env, base):
    r = TestClient(env.app, base_url=base).get(f"/p/{env.token}/index.html")
    assert r.status_code == 400 and "hola" not in r.text


def test_el_404_es_identico_byte_a_byte(env, monkeypatch):
    p = env.projects
    # token de un proyecto de otro usuario: válido, pero la ruta pedida solo existe en el proyecto de A
    pid_b = p.create(B, "de b")["project_id"]
    p.write_file(B, pid_b, "otro.html", "b")
    token_b = p.issue_preview(B, pid_b)["token"]
    # token de un proyecto que ya se borró
    pid_borrado = p.create(A, "borrado")["project_id"]
    p.write_file(A, pid_borrado, "index.html", "x")
    token_borrado = p.issue_preview(A, pid_borrado)["token"]
    p.delete_project(A, pid_borrado)
    # token caducado
    token_viejo = p.issue_preview(A, env.pid)["token"]
    real_now = projects_mod._now
    monkeypatch.setattr(projects_mod, "_now", lambda: real_now() + timedelta(minutes=31))
    caducado = env.client.get(f"/p/{token_viejo}/index.html")
    monkeypatch.setattr(projects_mod, "_now", real_now)

    respuestas = {
        "caducado": caducado,
        "ajeno": env.client.get(f"/p/{token_b}/js/app.js"),
        "proyecto_borrado": env.client.get(f"/p/{token_borrado}/index.html"),
        "inexistente": env.client.get("/p/" + "A" * 43 + "/index.html"),
        "mal_formado": env.client.get("/p/x/index.html"),
        "ruta_fuera_de_la_version": env.client.get(f"/p/{env.token}/no.html"),
        "traversal": env.client.get(f"/p/{env.token}/..%2f..%2fsecret.txt"),
        "traversal_codificado": env.client.get(f"/p/{env.token}/%2e%2e/index.html"),
        "tipo_no_permitido": env.client.get(f"/p/{env.token}/app.py"),
        "raiz": env.client.get("/"),
        "sin_token": env.client.get("/p/"),
        "otra_ruta": env.client.get("/s/algo/index.html"),
        "u": env.client.get("/u/alguien/"),
        "post": env.client.post(f"/p/{env.token}/index.html"),
        "favicon": env.client.get("/favicon.ico"),
    }
    base = _snapshot(respuestas["inexistente"])
    assert base[0] == 404 and base[1] == b"Not found"
    for nombre, r in respuestas.items():
        assert _snapshot(r) == base, nombre
    assert dict(base[2])["content-security-policy"] == "sandbox; default-src 'none'; frame-ancestors 'none'"


def test_tokens_invalidos_repetidos_dan_429_sin_revelar_si_el_token_existe():
    env = Env(coder_token_fail_max=3, coder_token_fail_window_minutes=15)
    for i in range(3):
        assert env.client.get(f"/p/{'B' * 40}{i:03d}/index.html").status_code == 404
    bloqueado_malo = env.client.get("/p/" + "C" * 43 + "/index.html")
    bloqueado_bueno = env.client.get(f"/p/{env.token}/index.html")  # el token válido también recibe 429
    assert bloqueado_malo.status_code == 429
    assert _snapshot(bloqueado_bueno) == _snapshot(bloqueado_malo)
    assert bloqueado_malo.content == b"Too many requests" and "set-cookie" not in bloqueado_malo.headers


def test_los_aciertos_y_las_rutas_que_faltan_no_cuentan_como_intentos():
    env = Env(coder_token_fail_max=2)
    for _ in range(5):
        assert env.client.get(f"/p/{env.token}/index.html").status_code == 200
        assert env.client.get(f"/p/{env.token}/falta.png").status_code == 404  # p. ej. un recurso que falta
    assert env.client.get(f"/p/{env.token}/index.html").status_code == 200


def test_el_sandbox_real_no_arranca_sin_coder_enabled(monkeypatch):
    from assistant.core.coder import sandbox
    from assistant.core.config import ConfigError

    monkeypatch.delenv("CODER_ENABLED", raising=False)
    with pytest.raises(ConfigError, match="CODER_ENABLED=1"):
        sandbox._real_app()
