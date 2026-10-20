"""Catálogo de conceptos y reglas de turno (lista 19-oct: 13, 14, 19, 20)."""
import json

from app.crm import conceptos
from app.crm import plantillas
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
    assert h["secciones_del_menu"]["contactos"]["nombre"] == "Clientes"
    assert h["secciones_del_menu"]["contactos"]["sirve_para"] == "x"
    assert h["tablas_del_negocio"][0]["nombre"] == "Ventas"
    assert h["secciones"][0]["id"] == "l_ventas"
    assert h["secciones"][0]["graficas_disponibles"] == ["dona (Dona)"]
    assert h["plantillas_de_pestana"] == ["membresias (miembros, planes)"]
    assert "pestanas_base" not in h
    assert h["bloques"][0].get("vista") == "kpis"
    assert h["bloques"][0].get("tipo_de_pieza") == "resumen con cifras"
    assert h["bloques"][0].get("seccion") == "miembros"
    assert h["bloques"][0].get("id") == "b0"


def test_humanizar_bloque_grafico_conserva_tipo_y_graficas():
    raw = {
        "secciones": [{"id": "miembros", "titulo": "Miembros", "graficos_posibles": ["dona (Dona)", "linea (Línea)"]}],
        "bloques": [
            {
                "id": "b1",
                "vista": "grafico",
                "seccion": "miembros",
                "opciones": {"tipo": "dona", "por": "estado"},
            }
        ],
    }
    h = conceptos.humanizar_estado_modelo(raw)
    assert h["bloques"][0]["vista"] == "grafico"
    assert h["bloques"][0]["opciones"]["tipo"] == "dona"
    assert h["secciones"][0]["graficas_disponibles"] == ["dona (Dona)", "linea (Línea)"]


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


def test_resolver_tipo_grafico_por_nombre_visible():
    assert plantillas.resolver_tipo_grafico("dona") == "dona"
    assert plantillas.resolver_tipo_grafico("Dona") == "dona"
    assert plantillas.resolver_tipo_grafico("DÓNA") == "dona"
    assert plantillas.resolver_tipo_grafico("no-existe") is None


def test_bloque_prompt_incluye_linea_por_concepto():
    bloque = conceptos.bloque_para_prompt("hola", None)
    assert bloque.count("\n") >= 80
    assert "cita:" in bloque.lower() or "Cita" in bloque


def test_el_detalle_dice_que_el_equipo_ya_existe_y_esta_oculto_en_vez_de_la_receta():
    doc = {"ocultas": ["rrhh"], "inicio": [], "paginas": {}}
    bloque = conceptos.bloque_para_prompt("agrega 40 empleados", None, doc, lambda sid: {"rrhh": "Equipo"}.get(sid, sid))
    detalle = bloque.split("Detalle (solo lo detectado en este mensaje):")[1]
    assert "es «Equipo», oculta en el menú" in detalle and "Se arma con" not in detalle.split("**Empleado**")[1].split("\n")[0]


def test_el_detalle_de_una_vista_dice_si_hay_piezas_asi_en_lo_que_mira():
    c = {"id": "vista_agenda", "se_arma_con": {"vista": "agenda"}}
    doc = {"inicio": [{"uid": "b1", "vista": "kpis"}], "paginas": {"l_citas": [{"uid": "p_l_citas_0", "vista": "agenda"}],
                                                                     "l_miembros": [{"uid": "p_l_miembros_1", "vista": "vencimientos"}]}}
    tit = {"l_citas": "Citas", "l_miembros": "Miembros"}.get
    assert "no hay ninguna pieza agenda; sí hay en: «Citas»" in conceptos.en_tu_crm(c, doc, tit, "l_miembros")
    assert "p_l_citas_0" in conceptos.en_tu_crm(c, doc, tit, "l_citas")
    assert conceptos.en_tu_crm({"id": "vista_tabla", "se_arma_con": {"vista": "tabla"}}, doc, tit, None) is None
