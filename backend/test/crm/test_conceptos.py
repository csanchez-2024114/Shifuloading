"""Catálogo de conceptos y reglas de turno (lista 19-oct: 7, 8, 13, 14, 19, 20)."""
import json

from app.crm import conceptos
from app.crm.generador import generar
from datetime import datetime, timezone

AHORA = datetime(2026, 10, 13, 15, 0, tzinfo=timezone.utc)


def test_catalogo_tiene_81_conceptos():
    assert len(conceptos._catalogo()) == 81


def test_importar_sin_falta():
    imp = next(c for c in conceptos._catalogo() if c["id"] == "importar")
    assert imp.get("falta") is None


def test_detecta_cita_e_inventario():
    d = conceptos._detectar("agenda una cita con Pedro mañana")
    assert "cita" in d
    assert "inventario" in conceptos._detectar("quiero llevar inventario de productos")


def test_si_suelto_con_recomendacion():
    hist = [{"de": "yo", "t": "¿qué gráficas?"}, {"de": "shifu", "t": "Te recomiendo una dona por estado. ¿La pongo?"}]
    assert conceptos.texto_tras_afirmacion("sí", hist)


def test_masivo_bloques_no_confunde_todos_los_miembros():
    assert not conceptos.masivo_destruye_bloques("quita la dona de todos los miembros")
    assert conceptos.masivo_destruye_registros("borra a todos los miembros")


def test_sin_jerga_quita_ids():
    t = conceptos.sin_jerga("Es una sección propia, no integrada (l_miembros).")
    assert "integrad" not in t.lower()
    assert "l_miembros" not in t


def test_sugerir_graficas_max_tres():
    doc = generar("u", {"rubro": "comercio", "que_vendes": "reparo computadoras"}, AHORA)
    from app.crm import sembrar
    from app.crm import plantillas as cat

    doc = sembrar.sembrar(doc, cat.plantilla_por_id("membresias"), porque=["test"])
    sec = next(s for s in doc["listas"] if s["id"].startswith("l_"))
    sec_wrap = {"id": sec["id"], "titulo": sec["nombre"], "campos": sec["campos"]}
    sug = conceptos.sugerir_graficas(doc, sec_wrap, 3)
    assert 1 <= len(sug) <= 3


def test_bloque_prompt_incluye_linea_por_concepto():
    bloque = conceptos.bloque_para_prompt("hola", None)
    assert bloque.count("\n") >= 80
    assert "cita:" in bloque.lower() or "Cita" in bloque
