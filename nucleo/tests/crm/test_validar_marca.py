"""validar.py y marca.py contra los fixtures dorados del laboratorio (grabar-validar-marca.mjs): mismas entradas, misma salida."""
import json
from pathlib import Path

import pytest

from assistant.packs.crm import plantillas
from assistant.packs.crm.marca import FUENTES, es_hex, revisar_logo, tokens_de_marca
from assistant.packs.crm.validar import TIPOS_CAMPO, VISTAS, campos_de, normalizar_opciones, revisar_vista, validar_plantilla

LAB = Path(__file__).parent / "fixtures" / "lab"


def casos(nombre):
    c = json.loads((LAB / f"{nombre}.json").read_text(encoding="utf-8"))
    return pytest.mark.parametrize("caso", c, ids=[x["caso"] for x in c])


def _campos(pid, sid):
    if pid is None:
        return []
    p = plantillas.plantilla_por_id(pid)
    por_id = {s["id"]: s for s in p["secciones"]}
    return campos_de(por_id[sid], por_id)


@casos("revisarVista")
def test_revisar_vista(caso):
    e = caso["entrada"]
    assert revisar_vista(e["vista"], e["opciones"], _campos(e["plantilla"], e.get("seccion")), e["donde"]) == caso["salida"]


@casos("normalizarOpciones")
def test_normalizar_opciones(caso):
    e = caso["entrada"]
    assert normalizar_opciones(e["vista"], e["opciones"]) == caso["salida"]


@casos("validarPlantilla")
def test_validar_plantilla(caso):
    assert validar_plantilla(caso["entrada"]["p"]) == caso["salida"]


@casos("tokensDeMarca")
def test_tokens_de_marca(caso):
    e = caso["entrada"]
    if "logo_id" in e["marca"]:
        # Diferencia intencional: en el CRM el logo vive en `logo_id` y, como el `logo` del laboratorio, no es «marca propia».
        assert tokens_de_marca(e["marca"], e["tema"]) == {"vars": {}, "ajustes": []}
        return
    assert tokens_de_marca(e["marca"], e["tema"]) == caso["salida"]


@casos("revisarLogo")
def test_revisar_logo(caso):
    d, largo = caso["entrada"]["dataUrl"], caso["entrada"]["largo"]
    if largo and largo > len(d or ""):
        d = d + "A" * (largo - len(d))
    assert revisar_logo(d) == caso["salida"]


def test_catalogos():
    assert TIPOS_CAMPO == ["texto", "numero", "dinero", "fecha", "hora", "estado"]
    assert "matriz" in VISTAS and VISTAS["feed"] == {"datos": False}
    nombres = {f["nombre"] for f in plantillas.fuentes()["fuentes"]}
    assert len(FUENTES) == 12 and set(FUENTES) <= nombres  # las 12 de la marca están en el catálogo grande
    assert es_hex("#ABC") and es_hex(" 16a34a ") and not es_hex("#12345") and not es_hex(None)
