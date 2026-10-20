"""Fase 2 (plan del núcleo de Alan): con el mismo guion del modelo, el bucle propio (`agente_diseno._responder`) y el del núcleo
(`profiles/crm/bucle.responder`) mandan al modelo exactamente los mismos mensajes, con las mismas herramientas, y devuelven
la misma salida. Si esto se rompe, los bancos con IA real dejan de ser comparables."""
import copy

import pytest
from langchain_core.messages import AIMessage

from assistant.packs.crm import agente_diseno as ad
from assistant.profiles.crm import bucle
from test_agente_diseno import AHORA, BRIEF, ModeloFalso, dice, llamar  # noqa: F401
from assistant.packs.crm import operaciones as op
from assistant.packs.crm.generador import generar


@pytest.fixture(autouse=True)
def con_diseno(monkeypatch):
    monkeypatch.setenv("CRM_DISENO", "1")
    from assistant.packs.crm import agente

    monkeypatch.setattr(agente, "_pausa_hasta", 0.0)


def _doc():
    d = generar("u1", BRIEF, AHORA)
    return op.contactos_crear(d, [{"n": n} for n in ["Ana Morales", "Luis Pérez", "Ana Ruiz"]], "WhatsApp", ahora=AHORA)


class GuionLargo(ModeloFalso):
    """Como ModeloFalso, pero si se acaba el guion responde «Listo.» (los dos bucles lo agotan igual)."""

    async def ainvoke(self, mensajes):
        self.recibidos.append(list(mensajes))
        return self.guion.pop(0) if self.guion else AIMessage(content="Listo.")


def _forma(mensajes):
    """Lo que el modelo ve de cada mensaje (sin ids internos de LangGraph)."""
    salida = []
    for m in mensajes:
        llamadas = [(c["name"], c["args"]) for c in (getattr(m, "tool_calls", None) or [])]
        salida.append((m.type, m.content, llamadas, getattr(m, "tool_call_id", None)))
    return salida


GUIONES = {
    "solo responde": ("hola", [dice("Hola, ¿qué hacemos hoy?")]),
    "agrega y responde": ("agrega a Pedro Gómez", [dice("", llamar("agregar_registro", seccion="contactos", valores={"n": "Pedro Gómez"})),
                                                  dice("Listo, agregué a Pedro Gómez.")]),
    "dice que hizo sin hacer: corrección": ("agrega a Marta", [dice("Listo, agregué a Marta."),
                                                              dice("", llamar("agregar_registro", seccion="contactos", valores={"n": "Marta"})),
                                                              dice("Agregué a Marta.")]),
    "deshacer sin pedidos": ("deshaz eso", [dice("", llamar("deshacer", pedido=1)), dice("No hay nada que deshacer todavía.")]),
    "herramienta inexistente": ("haz magia", [dice("", llamar("no_existe", x=1)), dice("No pude hacerlo.")]),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("caso", sorted(GUIONES))
async def test_los_dos_bucles_mandan_y_devuelven_lo_mismo(caso, monkeypatch):
    texto, guion = GUIONES[caso]
    resultados, doc = [], _doc()
    for motor in (ad._responder, bucle.responder):
        monkeypatch.setattr(ad, "_responder", motor)
        modelo = GuionLargo(*[copy.deepcopy(m) for m in guion])
        r = await ad.responder(copy.deepcopy(doc), texto, [], AHORA, False, modelo=modelo)
        resultados.append((r, modelo))
    (r1, m1), (r2, m2) = resultados
    assert [_forma(v) for v in m1.recibidos] == [_forma(v) for v in m2.recibidos]
    # una vuelta sin herramientas: el bucle propio ata una lista vacía y el del núcleo no ata nada
    assert [a["nombres"] for a in m1.ataduras if a["nombres"]] == [a["nombres"] for a in m2.ataduras if a["nombres"]]
    for clave in ("respuesta", "cambios", "fallos", "intentos", "consultas", "avisos", "por_hacer", "pendiente", "vista"):
        assert r1.get(clave) == r2.get(clave), clave
    assert r1["doc"].get("contactos") == r2["doc"].get("contactos")
    assert isinstance(m2.recibidos[0][0].content, str) and m2.recibidos[0][0].type == "system"
    assert all(not isinstance(x, AIMessage) or x.content is not None for v in m2.recibidos for x in v)
