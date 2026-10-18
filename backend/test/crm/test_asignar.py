"""Regla de asignación de plantilla: el port a Python da lo mismo que `asignar.js` en 204 combinaciones de respuestas
(fixtures de `laboratorio/servidor/grabar-asignar.mjs`). Sin base de datos."""
import json
from pathlib import Path

import pytest

from app.crm.asignar import asignar

LAB = Path(__file__).parent / "fixtures" / "lab"
PLANTILLAS = json.loads((LAB / "asignar_plantillas.json").read_text(encoding="utf-8"))
CASOS = json.loads((LAB / "asignar_casos.json").read_text(encoding="utf-8"))


def test_hay_al_menos_100_combinaciones():
    assert len(CASOS) >= 100
    assert any(c["salida"]["ambiguo"] for c in CASOS) and any(not c["salida"]["ambiguo"] for c in CASOS)


@pytest.mark.parametrize("caso", CASOS, ids=[c["caso"][:60] for c in CASOS])
def test_igual_que_el_laboratorio(caso):
    out = asignar(caso["entrada"], PLANTILLAS)
    assert out["opciones"] == caso["salida"]["opciones"]
    assert out["ambiguo"] == caso["salida"]["ambiguo"]
    assert out["recomendada"] == caso["salida"].get("recomendada")


def test_acepta_que_vendes_con_guion_bajo():
    a = asignar({"rubro": "servicios", "queVendes": "Membresías de gimnasio"}, PLANTILLAS)
    b = asignar({"rubro": "servicios", "que_vendes": "Membresías de gimnasio"}, PLANTILLAS)
    assert a == b and a["recomendada"]["puntos"] >= 5


def test_sin_catalogo_no_hay_recomendada():
    assert asignar({"rubro": "servicios"}, []) == {"recomendada": None, "opciones": [], "ambiguo": True}
