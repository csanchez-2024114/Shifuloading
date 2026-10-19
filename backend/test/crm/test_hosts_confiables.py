"""Punto 41: hosts confiables (TrustedHost) ampliables por TRUSTED_HOSTS_EXTRA sin cambiar los de siempre."""
from fastapi import FastAPI
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.testclient import TestClient

from config import DEFAULT_TRUSTED_HOSTS, parse_trusted_hosts_extra, trusted_hosts


def test_sin_variable_quedan_los_de_siempre():
    assert trusted_hosts("") == DEFAULT_TRUSTED_HOSTS
    assert trusted_hosts("") == [
        "localhost",
        "127.0.0.1",
        "hypershifu.com",
        "www.hypershifu.com",
        "backend-hyper-shifu-nyzm.onrender.com",
    ]


def test_csv_se_suma_sin_repetir_y_normaliza():
    extra = " crm.midominio.com, *.ngrok.app ,https://Demo.Example.com:8443/x, 192.168.1.20:5207, localhost "
    assert parse_trusted_hosts_extra(extra) == ["crm.midominio.com", "*.ngrok.app", "demo.example.com", "192.168.1.20", "localhost"]
    final = trusted_hosts(extra)
    assert final[: len(DEFAULT_TRUSTED_HOSTS)] == DEFAULT_TRUSTED_HOSTS
    assert final[len(DEFAULT_TRUSTED_HOSTS):] == ["crm.midominio.com", "*.ngrok.app", "demo.example.com", "192.168.1.20"]


def test_json_y_asterisco_solo_se_ignora():
    assert parse_trusted_hosts_extra('["a.com", "*"]') == ["a.com"]
    assert trusted_hosts("*") == DEFAULT_TRUSTED_HOSTS


def test_middleware_acepta_extra_y_rechaza_ajeno():
    app = FastAPI()

    @app.get("/x")
    def _x():
        return {"ok": True}

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=trusted_hosts("crm.midominio.com,*.ngrok.app"))
    c = TestClient(app)
    assert c.get("/x", headers={"host": "crm.midominio.com"}).status_code == 200
    assert c.get("/x", headers={"host": "abc.ngrok.app"}).status_code == 200
    assert c.get("/x", headers={"host": "localhost:5207"}).status_code == 200
    assert c.get("/x", headers={"host": "malo.com"}).status_code == 400
