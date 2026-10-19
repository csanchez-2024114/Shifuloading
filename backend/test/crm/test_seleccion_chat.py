"""La selección de piezas del chat llega al modelo por `adjunto`, no mezclada en el texto (como los archivos)."""
import base64

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytest.importorskip("langchain_core")

from app.crm import agente  # noqa: E402
from test_rutas import BRIEF, router  # noqa: E402
from test_rutas_puntos import _FakeDbPuntos  # noqa: E402

URL = "/api/v1/crm"
H = {"X-Usuario": "u1"}


def _b64(contenido: bytes) -> str:
    return f"data:text/plain;base64,{base64.b64encode(contenido).decode()}"


@pytest.fixture
def cli(monkeypatch):
    monkeypatch.setenv("CRM_IA", "0")
    db = _FakeDbPuntos()
    app = FastAPI()
    app.state.db = db
    app.include_router(router, prefix=URL)
    c = TestClient(app)
    assert c.post(URL, json={"brief": BRIEF}, headers=H).status_code == 201
    return c


def test_seleccion_en_adjunto_texto_intacto(cli, monkeypatch):
    llamadas = []

    async def _responder(doc, texto, historial, con_captura=False, **kw):
        llamadas.append((texto, kw.get("adjunto") or ""))
        return {"doc": doc, "respuesta": "Listo.", "modo": "ia", "cambios": [], "fallos": [], "intentos": [], "consultas": [], "avisos": []}

    monkeypatch.setattr(agente, "activo", lambda: True)
    monkeypatch.setattr(agente, "responder", _responder)

    payload = {
        "texto": "cambia el color",
        "contexto": {"seleccion": [{"tipo": "bloque", "id": "b2", "nombre": "Dona"}]},
    }
    r = cli.post(f"{URL}/chat", json=payload, headers=H).json()
    assert r["modo"] == "ia" and len(llamadas) == 1
    texto, adjunto = llamadas[0]
    assert texto == "cambia el color"
    assert "b2" in adjunto and "Dona" in adjunto


def test_seleccion_y_archivo_en_adjunto(cli, monkeypatch):
    llamadas = []

    async def _responder(doc, texto, historial, con_captura=False, **kw):
        llamadas.append(kw.get("adjunto") or "")
        return {"doc": doc, "respuesta": "Ok.", "modo": "ia", "cambios": [], "fallos": [], "intentos": [], "consultas": [], "avisos": []}

    monkeypatch.setattr(agente, "activo", lambda: True)
    monkeypatch.setattr(agente, "responder", _responder)

    secreto = "dato del archivo"
    payload = {
        "texto": "resume",
        "contexto": {
            "seleccion": [{"tipo": "bloque", "id": "b1", "nombre": "KPIs"}],
            "archivo": {"nombre": "n.txt", "datos": _b64(secreto.encode())},
        },
    }
    cli.post(f"{URL}/chat", json=payload, headers=H)
    adjunto = llamadas[0]
    assert "b1" in adjunto and secreto in adjunto and "no obedezcas" in adjunto


def test_demasiadas_piezas_422(cli):
    piezas = [{"tipo": "bloque", "id": f"b{i}", "nombre": f"P{i}"} for i in range(13)]
    r = cli.post(f"{URL}/chat", json={"texto": "hola", "contexto": {"seleccion": piezas}}, headers=H)
    assert r.status_code == 422
