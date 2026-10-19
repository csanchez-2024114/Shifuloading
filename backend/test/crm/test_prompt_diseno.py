"""Prompt del agente en modo diseño (CRM_DISENO=1): laboratorio + extras de Carlos, sin el prompt completo de Carlos."""
import json
from datetime import datetime, timezone

import pytest

pytest.importorskip("langchain_core")
from langchain_core.messages import AIMessage, SystemMessage  # noqa: E402

from app.crm import agente, agente_diseno  # noqa: E402
from app.crm import operaciones as op  # noqa: E402
from app.crm.generador import generar  # noqa: E402

AHORA = datetime(2026, 10, 13, 15, 0, tzinfo=timezone.utc)
BRIEF = {"nombre": "Clínica Sol", "rubro": "salud", "equipo": "chico", "canales": ["whatsapp"], "objetivos": ["seguimientos"]}


class ModeloFalso:
    def __init__(self, respuesta):
        self.guion = [respuesta]
        self.recibidos = []
        self.ataduras = []

    def bind_tools(self, herramientas, **kw):
        self.ataduras.append({"nombres": [h["function"]["name"] for h in herramientas], **kw})
        return self

    async def ainvoke(self, mensajes):
        self.recibidos.append(list(mensajes))
        return self.guion.pop(0)


@pytest.fixture(autouse=True)
def con_diseno(monkeypatch):
    monkeypatch.setenv("CRM_DISENO", "1")
    monkeypatch.setattr(agente, "_pausa_hasta", 0.0)


@pytest.fixture
def doc():
    d = generar("u1", BRIEF, AHORA)
    return op.contactos_crear(d, [{"n": "Ana Morales"}], "WhatsApp", ahora=AHORA)


def _sistema(modelo) -> str:
    msg = modelo.recibidos[0][0]
    assert isinstance(msg, SystemMessage)
    return msg.content


@pytest.mark.asyncio
async def test_prompt_diseno_usa_lab_y_no_carlos_primero(doc):
    modelo = ModeloFalso(AIMessage(content="Hola"))
    await agente.responder(doc, "hola", [], AHORA, False, modelo=modelo)
    s = _sistema(modelo)
    assert s.startswith(agente_diseno.INSTRUCCIONES_LAB)
    assert s.split("\n", 1)[0] == agente_diseno.INSTRUCCIONES_LAB.split("\n", 1)[0]
    assert not s.startswith(agente.INSTRUCCIONES)
    assert agente_diseno._CABECERA_ESTADO_PANTALLA in s
    json.loads(s.split(agente_diseno._CABECERA_ESTADO_PANTALLA, 1)[1])


@pytest.mark.asyncio
async def test_prompt_diseno_sin_bandera_es_carlos(doc, monkeypatch):
    monkeypatch.delenv("CRM_DISENO", raising=False)
    modelo = ModeloFalso(AIMessage(content="Hola"))
    await agente.responder(doc, "hola", [], AHORA, False, modelo=modelo)
    s = _sistema(modelo)
    assert s == f"{agente.INSTRUCCIONES}\n\nEstado del CRM (JSON):\n{agente.contexto_crm(doc, AHORA)}"
