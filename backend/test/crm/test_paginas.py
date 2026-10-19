"""Pestaña como cuaderno en blanco (D49) sobre el documento del CRM: port de laboratorio/pruebas/paginas.test.mjs (12 casos). Sin IA."""
import pytest

from app.crm.edicion import ejecutar
from app.crm.lienzo import ubicar_todo
from app.crm.pantalla import plantilla_efectiva
from lab_doc import doc_de_lab

E = {"bloques": [{"uid": "b0", "vista": "kpis", "seccion": "miembros", "opciones": {"por": "estado"}, "ancho": 12, "alto": 1}]}


@pytest.fixture
def base():
    return doc_de_lab("membresias", E)[0]


def pag(doc, sid):
    return (doc.get("paginas") or {}).get(sid)


def uids(bs):
    return [b["uid"] for b in bs]


@pytest.fixture
def e1(base):
    r = ejecutar(base, "agregar_bloque", {"pestana": "miembros", "vista": "grafico", "opciones": {"tipo": "dona"}})
    assert r["ok"], r["resultado"]
    return r


def test_agregar_en_una_pestana_crea_su_lienzo_y_el_inicio_no_cambia(e1):
    d = e1["doc"]
    assert uids(d["inicio"]) == ["b0"]
    assert len(pag(d, "l_miembros")) == 2
    assert pag(d, "l_miembros")[0]["vista"] == "tabla"  # la vista de siempre de Miembros
    assert pag(d, "l_miembros")[1]["seccion"] == "l_miembros"  # sin «seccion», usa la de la pestaña
    assert "En la pestaña «Miembros»" in e1["resultado"]


def test_la_plantilla_efectiva_expone_el_lienzo_de_la_pestana(e1):
    s = next(x for x in plantilla_efectiva(e1["doc"])["secciones"] if x["id"] == "l_miembros")
    assert len(s["pagina"]) == 2


def test_quitar_por_id_encuentra_el_bloque_en_la_pestana(e1):
    r = ejecutar(e1["doc"], "quitar_bloque", {"bloque": pag(e1["doc"], "l_miembros")[1]["uid"]})
    assert r["ok"], r["resultado"]
    assert len(pag(r["doc"], "l_miembros")) == 1 and uids(r["doc"]["inicio"]) == ["b0"]


def test_la_pieza_por_defecto_de_una_pestana_sin_lienzo_se_puede_cambiar(base):
    r = ejecutar(base, "cambiar_visual", {"bloque": "p_l_miembros", "vista": "tablero", "opciones": {"por": "estado"}})
    assert r["ok"], r["resultado"]
    assert pag(r["doc"], "l_miembros")[0]["vista"] == "tablero"


def test_acomodo_automatico_tambien_en_la_pestana(e1):
    r = ejecutar(e1["doc"], "cambiar_tamano", {"bloque": pag(e1["doc"], "l_miembros")[0]["uid"], "ancho": 6})
    assert r["ok"], r["resultado"]
    anchos = [b["ancho"] for b in pag(r["doc"], "l_miembros")]
    assert sum(anchos) % 12 == 0, anchos


def test_ubicar_todo_ve_los_bloques_de_todos_los_lienzos(e1):
    u = ubicar_todo(e1["doc"])
    assert u["b0"] and u[pag(e1["doc"], "l_miembros")[1]["uid"]]


def test_pestana_inexistente_o_fija_error_claro_y_nada_cambia(base):
    r1 = ejecutar(base, "agregar_bloque", {"pestana": "nada", "vista": "tabla", "seccion": "miembros"})
    assert not r1["ok"] and "no existe" in r1["resultado"] and r1["doc"] is base
    r2 = ejecutar(base, "agregar_bloque", {"pestana": "actividad", "vista": "tabla", "seccion": "miembros"})
    assert not r2["ok"] and "no admite piezas" in r2["resultado"]


def test_una_pestana_puede_mostrar_datos_de_otra_seccion(base):
    r = ejecutar(base, "agregar_bloque", {"pestana": "miembros", "vista": "tabla", "seccion": "pagos"})
    assert r["ok"], r["resultado"]
    assert pag(r["doc"], "l_miembros")[1]["seccion"] == "l_pagos"


def test_quitar_una_seccion_se_lleva_su_lienzo_y_sus_piezas_en_otras_pestanas(base):
    a = ejecutar(base, "agregar_bloque", {"pestana": "miembros", "vista": "tabla", "seccion": "pagos"})["doc"]
    b = ejecutar(a, "agregar_bloque", {"pestana": "pagos", "vista": "grafico", "opciones": {"tipo": "columnas"}})["doc"]
    r = ejecutar(b, "quitar_seccion", {"seccion": "pagos"})
    assert r["ok"], r["resultado"]
    assert pag(r["doc"], "l_pagos") is None and all(x["seccion"] != "l_pagos" for x in pag(r["doc"], "l_miembros"))


def test_mirando_una_pestana_agregar_va_ahi_por_defecto(base):
    r = ejecutar(base, "agregar_bloque", {"vista": "kpis", "opciones": {"por": "estado"}}, {"vista": "l_miembros"})
    assert r["ok"], r["resultado"]
    assert len(pag(r["doc"], "l_miembros")) == 2 and uids(r["doc"]["inicio"]) == ["b0"] and r["vista"] == "l_miembros"


def test_mirando_una_pestana_tocar_el_inicio_sin_decirlo_se_rechaza(base):
    r1 = ejecutar(base, "cambiar_visual", {"bloque": "b0", "vista": "tabla"}, {"vista": "l_miembros"})
    assert not r1["ok"] and "INICIO" in r1["resultado"]
    r2 = ejecutar(base, "agregar_bloque", {"pestana": "inicio", "vista": "tabla", "seccion": "pagos"}, {"vista": "l_miembros"})
    assert r2["ok"], r2["resultado"]
    assert len(r2["doc"]["inicio"]) == 2


def test_pieza_igual_a_otra_del_mismo_lienzo_d55(base):
    r1 = ejecutar(base, "agregar_bloque", {"vista": "kpis", "seccion": "miembros", "opciones": {"por": "estado"}})
    assert not r1["ok"] and "pieza igual" in r1["resultado"] and "b0" in r1["resultado"]
    a = ejecutar(base, "agregar_bloque", {"vista": "grafico", "seccion": "miembros", "opciones": {"tipo": "dona"}})
    assert a["ok"], a["resultado"]
    assert not ejecutar(a["doc"], "agregar_bloque", {"vista": "grafico", "seccion": "miembros", "opciones": {"tipo": "dona"}})["ok"]
    assert ejecutar(a["doc"], "agregar_bloque", {"vista": "grafico", "seccion": "miembros", "opciones": {"tipo": "columnas"}})["ok"], "otro tipo"
    assert ejecutar(a["doc"], "agregar_bloque", {"vista": "grafico", "seccion": "miembros", "opciones": {"tipo": "dona"}}, {"confirmado": True})["ok"], "con «sí»"
    assert ejecutar(base, "agregar_bloque", {"pestana": "miembros", "vista": "kpis", "opciones": {"por": "estado"}})["ok"], "en otra pestaña"


def test_la_pieza_por_defecto_nombrada_sin_l_tambien_se_encuentra(base):
    r = ejecutar(base, "cambiar_visual", {"bloque": "p_miembros", "vista": "tablero", "opciones": {"por": "estado"}})
    assert r["ok"], r["resultado"]
    assert pag(r["doc"], "l_miembros")[0]["uid"] == "p_l_miembros" and pag(r["doc"], "l_miembros")[0]["vista"] == "tablero"
