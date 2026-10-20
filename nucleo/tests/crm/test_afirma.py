"""Detector de «afirma un cambio» (D51): los 18 casos reales de `laboratorio/pruebas/afirma.test.mjs`."""
import json
from pathlib import Path

import pytest

from assistant.packs.crm.afirma import afirma_cambio

# Afirman un cambio (si ninguna herramienta cambió nada, es mentira y el código lo corrige)
AFIRMAN = ["Agregué a Juan Pérez con plan mensual.", "Listo, puse el tema oscuro.", "Creé la sección Cobros y la puse en el inicio. ¿Quieres algo más?",
           "Hice la gráfica más grande y la moví arriba.", "Borré a Ana Gómez de las membresías.", "Cambié el estado de Ana a Pausada; no pude poner la fecha.",
           "Lista la tabla de clases.", "Ya renombré la pestaña a Cobranza"]
# No afirman nada (todos vistos en respuestas reales que el cerco descartaba)
NO_AFIRMAN = ["Tienes 2 miembros activos y no hay monto registrado para ellos. ¿Quieres que agregue el monto para Juan?",
              "Para registrar ese pago necesito que exista una sección de cobros. ¿Quieres que cree la sección \"cobros\"?",
              "No hice ningún cambio, solo consulté datos para responderte.", "Todavía no lo agregué: dime la fecha exacta.",
              "No hay opción para exportar a Excel. ¿Quieres que te muestre la tabla de miembros?", "Nadie vence este mes en membresías.",
              "¿Lo pongo arriba de todo?", "Puedo agregar un bloque con la tabla, ¿lo agrego al inicio?", "Este mes te pagaron un total de Q31,120.",
              "Si quieres, la creo para que puedas registrar pagos"]


def test_son_los_18_casos_del_laboratorio():
    assert len(AFIRMAN) + len(NO_AFIRMAN) == 18


@pytest.mark.parametrize("texto", AFIRMAN)
def test_afirma(texto):
    assert afirma_cambio(texto) is True


@pytest.mark.parametrize("texto", NO_AFIRMAN)
def test_no_afirma(texto):
    assert afirma_cambio(texto) is False


def test_vacio_y_none():
    assert afirma_cambio("") is False and afirma_cambio(None) is False


# Los 412 casos dorados de afirmaCambio (grabar-fixtures.mjs, contrato §6).
_DORADOS = json.loads((Path(__file__).parent / "fixtures" / "lab" / "afirmaCambio.json").read_text(encoding="utf-8"))


def test_hay_412_casos_dorados():
    assert len(_DORADOS) == 412


@pytest.mark.parametrize("caso", _DORADOS, ids=[str(i) for i in range(len(_DORADOS))])
def test_igual_que_el_laboratorio(caso):
    assert afirma_cambio(caso["entrada"]["texto"]) is caso["salida"], caso["caso"]
