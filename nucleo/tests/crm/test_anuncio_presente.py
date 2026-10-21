"""«La creo con campos…» sin llamar a nada es un anuncio sin hacer (como «la crearé»): el código lo corrige. Modelo simulado: sin OpenAI."""
import pytest

pytest.importorskip("langchain_core")
from test_agente_diseno import AHORA, correr, dice, doc, llamar  # noqa: E402,F401

from assistant.packs.crm import agente, agente_diseno  # noqa: E402


@pytest.fixture(autouse=True)
def con_diseno(monkeypatch):
    monkeypatch.setenv("CRM_DISENO", "1")
    monkeypatch.setattr(agente, "_pausa_hasta", 0.0)


@pytest.mark.parametrize("respuesta", [
    "No tienes aún la sección de inventario. La creo con campos básicos: producto, cantidad y mínimo.",
    "Creo la sección Inventario con producto y stock.",
    "Te la agrego con producto, categoría y precio.",
])
def test_anuncio_en_presente_sin_hacer_es_promesa(doc, respuesta):
    s = agente_diseno.SesionDiseno(doc, AHORA, "quiero llevar el inventario")
    assert s.promesas_sin_respaldo(respuesta)


@pytest.mark.parametrize("respuesta", [
    "Creo que te conviene un tablero.",          # opinión
    "¿La creo con producto y cantidad?",         # pregunta
    "No la creo todavía: dime los campos.",      # negado
    "Ya creé la sección Inventario.",            # pasado (lo revisa otro cerco)
])
def test_lo_que_no_es_anuncio_no_dispara(doc, respuesta):
    assert agente_diseno.SesionDiseno(doc, AHORA, "quiero llevar el inventario").promesas_sin_respaldo(respuesta) == []


@pytest.mark.asyncio
async def test_si_anuncia_y_no_hace_el_codigo_le_pide_hacerlo(doc):
    r, _ = await correr(doc, "quiero llevar el inventario",
                        dice("No tienes inventario. La creo con producto, cantidad y mínimo."),
                        dice("", llamar("crear_seccion", titulo="Inventario", campos=[{"nombre": "Producto", "tipo": "texto"}, {"nombre": "Cantidad", "tipo": "numero"}])),
                        dice("Listo, creé Inventario."))
    assert r["avisos"] and "crear_seccion" in [c["herramienta"] for c in r["cambios"]]


@pytest.mark.asyncio
async def test_si_lo_hizo_no_molesta(doc):
    r, _ = await correr(doc, "quiero llevar el inventario",
                        dice("", llamar("crear_seccion", titulo="Inventario", campos=[{"nombre": "Producto", "tipo": "texto"}, {"nombre": "Cantidad", "tipo": "numero"}])),
                        dice("Creé la sección Inventario; la agrego también al menú."))
    assert r["avisos"] == []


@pytest.mark.asyncio
async def test_lo_que_eligio_el_codigo_no_es_promesa(doc):
    # «pon mis colores: rojo» → el código aclara el rojo para el tema oscuro y lo dice en su resultado; el modelo lo cuenta en pasado.
    r, modelo = await correr(doc, "pon mis colores: rojo #DC2626", dice("", llamar("cambiar_marca", primario="#DC2626")),
                             dice("Puse tu rojo como principal; para que se lea bien en oscuro lo aclaré un poco."))
    assert not any("no lo hiciste en este mensaje" in a["aviso"] for a in r["avisos"])
