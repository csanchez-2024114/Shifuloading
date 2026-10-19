"""Ruta POST /api/v1/crm/lab/chat con el agente real (modelo falso) y montaje condicional."""
from __future__ import annotations

import pytest

pytest.importorskip("langchain_core")
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402

from app.crm import agente  # noqa: E402
from app.routes.crm import labRoutes  # noqa: E402
from test_adaptador_lab import BANCO2_E  # noqa: E402


class ModeloFalso:
    def __init__(self, *guion):
        self.guion = list(guion)
        self.ataduras = []

    def bind_tools(self, herramientas, **kw):
        self.ataduras.append({"nombres": [h["function"]["name"] for h in herramientas], **kw})
        return self

    async def ainvoke(self, mensajes):
        return self.guion.pop(0)


_n = 0


def _llamar(herramienta, /, **args):
    global _n
    _n += 1
    return {"name": herramienta, "args": args, "id": f"lr{_n}"}


@pytest.fixture(autouse=True)
def con_diseno(monkeypatch):
    monkeypatch.setenv("CRM_DISENO", "1")
    monkeypatch.setattr(agente, "activo", lambda: True)
    monkeypatch.setattr(agente, "_pausa_hasta", 0.0)


@pytest.fixture
def cliente_lab(monkeypatch):
    monkeypatch.setenv("CRM_LAB_ADAPTER", "1")
    labRoutes.configurar_responder(None)
    app = FastAPI()
    app.include_router(labRoutes.router, prefix="/api/v1/crm")
    return TestClient(app)


def _modelo(monkeypatch, *guion):
    modelo = ModeloFalso(*guion)
    monkeypatch.setattr(agente, "_modelo", lambda: modelo)
    return modelo


def test_turno_agrega_dona(cliente_lab, monkeypatch):
    _modelo(
        monkeypatch,
        AIMessage(
            content="",
            tool_calls=[
                _llamar(
                    "agregar_bloque",
                    vista="grafico",
                    seccion="miembros",
                    opciones={"tipo": "dona"},
                    ancho=4,
                    alto=2,
                )
            ],
        ),
        AIMessage(content="Listo, agregué la dona."),
    )
    r = cliente_lab.post(
        "/api/v1/crm/lab/chat",
        json={
            "plantilla": "membresias",
            "estado": BANCO2_E,
            "texto": "agrega una dona de los estados de los miembros chiquita",
        },
    )
    assert r.status_code == 200
    d = r.json()
    assert any(c["herramienta"] == "agregar_bloque" for c in d["cambios"])
    vistas = [b["vista"] for b in d["estado"]["bloques"]]
    assert "grafica" in vistas or "grafico" in vistas
    assert len(d["estado"].get("puntos") or []) == 1


def test_dos_turnos_deshacer_restaura_bloques(cliente_lab, monkeypatch):
    guion_turno1 = [
        AIMessage(
            content="",
            tool_calls=[
                _llamar(
                    "agregar_bloque",
                    vista="grafico",
                    seccion="miembros",
                    opciones={"tipo": "dona"},
                    ancho=4,
                    alto=2,
                )
            ],
        ),
        AIMessage(content="Listo, agregué la dona."),
    ]
    guion_turno2 = [
        AIMessage(content="", tool_calls=[_llamar("deshacer", pedido=1)]),
        AIMessage(content="Listo, deshice eso."),
    ]
    modelo = ModeloFalso(*guion_turno1)

    def _modelo_turno1():
        return modelo

    monkeypatch.setattr(agente, "_modelo", _modelo_turno1)

    r1 = cliente_lab.post(
        "/api/v1/crm/lab/chat",
        json={"plantilla": "membresias", "estado": BANCO2_E, "texto": "agrega una dona chiquita"},
    )
    assert r1.status_code == 200
    d1 = r1.json()
    n_bloques_despues = len(d1["estado"]["bloques"])
    assert n_bloques_despues == len(BANCO2_E["bloques"]) + 1
    assert len(d1["estado"].get("puntos") or []) == 1

    modelo.guion = list(guion_turno2)
    monkeypatch.setattr(agente, "_modelo", lambda: modelo)

    r2 = cliente_lab.post(
        "/api/v1/crm/lab/chat",
        json={
            "plantilla": "membresias",
            "estado": d1["estado"],
            "texto": "deshaz eso",
            "historial": [{"de": "yo", "t": "agrega una dona chiquita"}, {"de": "shifu", "t": d1["respuesta"]}],
        },
    )
    assert r2.status_code == 200
    d2 = r2.json()
    assert len(d2["estado"]["bloques"]) == len(BANCO2_E["bloques"])
    assert any(c["herramienta"] == "deshacer" for c in d2["cambios"])
    assert not d2["estado"].get("puntos")


def test_sin_crm_lab_adapter_la_ruta_no_existe():
    """Como en main.py: sin CRM_LAB_ADAPTER=1 el router no se monta."""
    app = FastAPI()
    c = TestClient(app)
    assert c.post("/api/v1/crm/lab/chat", json={"texto": "hola"}).status_code == 404


def test_con_adapter_apagado_en_router_404(monkeypatch):
    monkeypatch.delenv("CRM_LAB_ADAPTER", raising=False)
    labRoutes.configurar_responder(None)
    app = FastAPI()
    app.include_router(labRoutes.router, prefix="/api/v1/crm")
    c = TestClient(app)
    assert c.post("/api/v1/crm/lab/chat", json={"texto": "hola"}).status_code == 404


def test_sin_crm_diseno_503(cliente_lab, monkeypatch):
    monkeypatch.setenv("CRM_LAB_ADAPTER", "1")
    monkeypatch.delenv("CRM_DISENO", raising=False)
    r = cliente_lab.post("/api/v1/crm/lab/chat", json={"plantilla": "membresias", "estado": BANCO2_E, "texto": "hola"})
    assert r.status_code == 503
    assert "CRM_DISENO" in r.json()["detail"]
