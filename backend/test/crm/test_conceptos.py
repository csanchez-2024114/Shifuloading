"""Catálogo de conceptos y reglas de turno (lista 19-oct: 13, 14, 19, 20)."""
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


def test_masivo_registros_detecta_todos():
    assert conceptos.masivo_destruye_registros("borra a todos los miembros")


def test_humanizar_estado_quita_jerga_de_claves():
    raw = {
        "secciones_integradas": {"contactos": {"nombre": "Clientes", "oculta": False, "para_que": "x"}},
        "secciones_propias": [{"nombre": "Ventas", "total_registros": 0, "campos": []}],
        "secciones": [{"id": "l_ventas", "titulo": "Ventas", "graficos_posibles": ["dona (Dona)"]}],
        "pestanas_base": ["membresias (miembros, planes)"],
        "bloques": [{"id": "b0", "vista": "kpis", "seccion": "miembros", "donde_se_ve": "fila 1"}],
    }
    h = conceptos.humanizar_estado_modelo(raw)
    assert "secciones_integradas" not in h and "secciones_propias" not in h
    assert h["secciones_del_menu"]["Clientes"]["sirve_para"] == "x"
    assert h["tablas_del_negocio"][0]["nombre"] == "Ventas"
    assert h["secciones"][0]["graficas_disponibles"] == ["Dona"]
    assert "pestanas_base" not in h
    assert h["bloques"][0].get("tipo_de_pieza") == "resumen con cifras"


def test_humanizar_resultado_herramienta():
    from app.crm import sembrar
    from app.crm import plantillas as cat

    doc = sembrar.sembrar(generar("u", {"rubro": "comercio"}, AHORA), cat.plantilla_por_id("membresias"), porque=["test"])
    t = "Listo. Así se ve ahora: b0 (kpis) → fila 1, ancho completo."
    legible = conceptos.humanizar_resultado_herramienta(t, doc)
    assert "b0" not in legible and "kpis" not in legible
    assert "Así se ve ahora:" in legible


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
