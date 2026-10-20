"""Punto 48: los topes de tamaño en un solo lugar (`topes`) y UN tope de campos por sección (20) en los dos caminos."""
from datetime import datetime, timezone

import pytest

from assistant.packs.crm import edicion, topes
from assistant.packs.crm import estructura as est
from assistant.packs.crm import operaciones as op
from assistant.packs.crm.generador import generar
from lab_doc import doc_de_lab

AHORA = datetime(2026, 10, 13, 15, 0, tzinfo=timezone.utc)
E = {"vista": "inicio", "bloques": []}


def test_un_solo_lugar_y_los_demas_valores_sin_cambio():
    assert (topes.SECCIONES_PROPIAS, topes.CAMPOS_POR_SECCION, topes.REGISTROS_POR_SECCION, topes.CONTACTOS) == (12, 20, 2000, 5000)
    assert est.MAX_LISTAS == topes.SECCIONES_PROPIAS and est.MAX_REGISTROS == topes.REGISTROS_POR_SECCION
    assert est.MAX_CAMPOS == edicion.MAX_CAMPOS_SECCION == topes.CAMPOS_POR_SECCION
    assert op.MAX_CONTACTOS == topes.CONTACTOS


def test_modo_diseno_agrega_hasta_20_campos_y_el_21_se_frena_con_el_numero_real():
    doc, ctx = doc_de_lab("membresias", E)
    sec = next(l for l in doc["listas"] if l["id"] == "l_miembros")
    hechos = 0
    for i in range(len(sec["campos"]), topes.CAMPOS_POR_SECCION):
        r = edicion.ejecutar(doc, "agregar_campo", {"seccion": "miembros", "nombre": f"Dato {i}", "tipo": "texto"}, ctx)
        assert r["ok"], r["resultado"]
        doc, hechos = r["doc"], hechos + 1
    assert hechos > 8 - len(sec["campos"])  # pasa el tope viejo de 8
    assert len(next(l for l in doc["listas"] if l["id"] == "l_miembros")["campos"]) == 20
    r = edicion.ejecutar(doc, "agregar_campo", {"seccion": "miembros", "nombre": "Uno más", "tipo": "texto"}, ctx)
    assert not r["ok"] and "ya tiene 20 campos (el máximo)" in r["resultado"]


def test_modo_diseno_crea_una_seccion_con_hasta_20_campos():
    doc, ctx = doc_de_lab("membresias", E)
    campos = [{"nombre": f"Campo {i}", "tipo": "texto"} for i in range(22)]
    r = edicion.ejecutar(doc, "crear_seccion", {"titulo": "Taller", "campos": campos}, ctx)
    assert r["ok"], r["resultado"]
    taller = next(l for l in r["doc"]["listas"] if l["nombre"] == "Taller")
    assert [c["nombre"] for c in taller["campos"]] == [f"Campo {i}" for i in range(20)]
    assert "con 20 campos" in r["resultado"]  # el modelo lee cuántos quedaron de verdad


@pytest.mark.parametrize("ambito", ["lista", "contactos"])
def test_camino_de_carlos_mismo_tope(ambito):
    doc = generar("u1", {"nombre": "Taller", "rubro": "servicios"}, AHORA)
    if ambito == "lista":
        doc = est.lista_crear(doc, "Reparaciones", [{"nombre": "Equipo", "tipo": "texto"}], AHORA)
        ambito = doc["listas"][-1]["id"]
    campos = est._ambito(doc, ambito)[0]
    for i in range(len(campos), topes.CAMPOS_POR_SECCION):
        doc = est.campo_agregar(doc, ambito, f"Dato {i}", "texto", AHORA)
    assert len(est._ambito(doc, ambito)[0]) == 20
    with pytest.raises(op.ErrorCrm, match="hasta 20 campos"):
        est.campo_agregar(doc, ambito, "Uno más", "texto", AHORA)


def test_crear_lista_con_mas_de_20_campos_se_frena():
    doc = generar("u1", {"nombre": "Taller", "rubro": "servicios"}, AHORA)
    est.lista_crear(doc, "Justo", [{"nombre": f"c{i}"} for i in range(20)], AHORA)
    with pytest.raises(op.ErrorCrm):
        est.lista_crear(doc, "Demasiados", [{"nombre": f"c{i}"} for i in range(21)], AHORA)
