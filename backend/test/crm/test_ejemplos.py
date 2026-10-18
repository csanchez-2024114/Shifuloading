"""Datos de ejemplo: el port a Python da EXACTAMENTE lo mismo que `datosEjemplo.js` (fixtures de `laboratorio/servidor/grabar-ejemplos.mjs`,
con hoy = 2026-10-16). Sin base de datos."""
import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

from app.crm import ejemplos as ej

LAB = Path(__file__).parent / "fixtures" / "lab"
PLANTILLAS = {p["id"]: p for p in json.loads((LAB / "ejemplos_plantillas.json").read_text(encoding="utf-8"))}
DATOS = json.loads((LAB / "ejemplos_datos.json").read_text(encoding="utf-8"))
EXTENDER = json.loads((LAB / "ejemplos_extender.json").read_text(encoding="utf-8"))
HOY = date.fromisoformat(DATOS["hoy"])


def huella(x) -> str:
    return hashlib.sha256(json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def test_hay_casos_suficientes():
    assert len(PLANTILLAS) >= 6
    niveles = {c["entrada"]["nivel"] for c in DATOS["casos"]}
    assert niveles == {"vacio", "pocos", "muchos"} and len(DATOS["casos"]) >= 18


@pytest.mark.parametrize("caso", DATOS["casos"], ids=[c["caso"] for c in DATOS["casos"]])
def test_igual_que_el_laboratorio(caso):
    d = ej.datos_ejemplo(PLANTILLAS[caso["entrada"]["plantilla"]], caso["entrada"]["nivel"], hoy=HOY, pais="gt")
    if "salida" in caso:
        assert d == caso["salida"]
    if "huella" in caso:
        assert huella(d) == caso["huella"]


@pytest.mark.parametrize("caso", EXTENDER["casos"], ids=[c["caso"] for c in EXTENDER["casos"]])
def test_extender_y_sin_ejemplos(caso):
    e = caso["entrada"]
    base = PLANTILLAS[e["plantilla"]]
    datos = ej.datos_ejemplo(base, e["nivel"], hoy=HOY)
    out = ej.extender_datos(datos, base, e["est"], e["nivel"], hoy=HOY) if "est" in e else ej.sin_ejemplos(datos)
    assert out == caso["salida"]


def test_todo_registro_va_marcado_como_ejemplo_y_el_nombre_es_unico():
    regs = ej.registros_ejemplo(PLANTILLAS["membresias"], "muchos", hoy=HOY)
    assert all(r["ejemplo"] is True for rs in regs.values() for r in rs)
    nombres = [r["valores"]["nombre"] for r in regs["miembros"]]
    assert len(nombres) == 220 and len(set(nombres)) == 220


def test_fechas_relativas_a_hoy():
    a = ej.registros_ejemplo(PLANTILLAS["membresias"], "pocos", hoy=date(2026, 10, 16))
    b = ej.registros_ejemplo(PLANTILLAS["membresias"], "pocos", hoy=date(2026, 10, 17))
    fa, fb = a["miembros"][0]["valores"]["vence"], b["miembros"][0]["valores"]["vence"]
    assert (date.fromisoformat(fb) - date.fromisoformat(fa)).days == 1
    assert a["miembros"][0]["valores"]["nombre"] == b["miembros"][0]["valores"]["nombre"]


