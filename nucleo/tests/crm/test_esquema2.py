"""Esquema 2 del CRM (contrato §1 y §4): campos nuevos perezosos, inicio por defecto, tipos nuevos y lo opcional de las listas."""
import copy
from datetime import datetime, timezone

import pytest

from assistant.packs.crm import estructura as est
from assistant.packs.crm import operaciones as op
from assistant.packs.crm.generador import generar
from assistant.packs.crm.operaciones import ErrorCrm
from assistant.packs.crm.vista import vista_crm

AHORA = datetime(2026, 10, 13, 15, 0, tzinfo=timezone.utc)
BRIEF = {"nombre": "Gimnasio Fuerte", "rubro": "otro"}


@pytest.fixture
def doc():
    return generar("u1", BRIEF, AHORA)


def con_miembros(d):
    return est.lista_crear(d, "Miembros", [{"nombre": "Nombre"}, {"nombre": "Plan", "tipo": "estado", "opciones": ["Básico", "Premium"]},
                                           {"nombre": "Cuota", "tipo": "dinero"}, {"nombre": "Clase", "tipo": "hora"}], AHORA)


# ───────── normalizar ─────────

def test_normalizar_agrega_el_esquema_2_con_sus_valores_por_defecto(doc):
    n = est.normalizar(copy.deepcopy(doc))
    assert n["esquema"] == 2 and n["plantilla"] is None and n["paginas"] == {} and n["marca"] == {} and n["puntos_n"] == 0
    assert n["toma"] == {"activa": False, "fase": "juntando", "ficha": {"objetivo": "", "secciones": [], "bloques": [], "marca": {}, "restricciones": []},
                         "notas": [], "preguntadas": [], "rechazo": False}
    assert n["inicio"] == [{"uid": "b0", "vista": "kpis", "seccion": "contactos", "opciones": {"por": "etapa"}, "ancho": 12, "alto": 1}]


def test_el_inicio_por_defecto_suma_la_tabla_de_la_primera_seccion_propia(doc):
    d = con_miembros(doc)
    n = est.normalizar(d)
    lid = d["listas"][0]["id"]
    assert [(b["vista"], b["seccion"]) for b in n["inicio"]] == [("kpis", "contactos"), ("tabla", lid)]
    assert len({b["uid"] for b in n["inicio"]}) == 2


def test_sin_contactos_visibles_el_inicio_no_trae_su_resumen(doc):
    d = {**doc, "ocultas": ["contactos"]}
    assert est.normalizar(d)["inicio"] == []


def test_normalizar_es_idempotente_y_no_toca_los_registros(doc):
    d = op.contactos_crear(con_miembros(doc), [{"n": "Ana"}], "WhatsApp", ahora=AHORA)
    d = est.registro_agregar(d, d["listas"][0]["id"], {d["listas"][0]["campos"][0]["id"]: "Rosa"}, AHORA)
    registros, contactos = copy.deepcopy(d["listas"][0]["registros"]), copy.deepcopy(d["contactos"])
    n1 = est.normalizar(d)
    n2 = est.normalizar(copy.deepcopy(n1))
    assert n1 == n2
    assert n1["listas"][0]["registros"] == registros and n1["contactos"] == contactos


def test_lo_que_ya_tiene_se_respeta_aunque_este_vacio(doc):
    d = {**doc, "esquema": 2, "inicio": [], "marca": {"primario": "#123456"}, "puntos_n": 7}
    n = est.normalizar(d)
    assert n["inicio"] == [] and n["marca"] == {"primario": "#123456"} and n["puntos_n"] == 7


# ───────── tipos de campo ─────────

def test_los_tipos_nuevos_convierten_el_valor():
    assert est.valor_de_tipo("dinero", "Q 1,250.50", "Cuota") == 1250.5
    assert est.valor_de_tipo("hora", "16:30", "Clase") == "16:30"
    assert est.valor_de_tipo("hora", "4pm", "Clase") == "16:00"
    assert est.valor_de_tipo("hora", "9:05 a.m.", "Clase") == "09:05"
    assert est.valor_de_tipo("hora", "12am", "Clase") == "00:00"
    assert est.valor_de_tipo("estado", "premium", "Plan", ["Básico", "Premium"]) == "Premium"
    assert est.valor_de_tipo("lista", "básico", "Plan", ["Básico", "Premium"]) == "Básico"  # lista = estado


@pytest.mark.parametrize("tipo, valor", [("hora", "25:00"), ("hora", "mañana"), ("hora", "13pm"), ("estado", "Oro"), ("dinero", "mucho")])
def test_los_tipos_nuevos_rechazan_lo_que_no_sirve(tipo, valor):
    with pytest.raises(ErrorCrm):
        est.valor_de_tipo(tipo, valor, "Campo", ["Básico", "Premium"])


def test_un_campo_estado_necesita_opciones(doc):
    with pytest.raises(ErrorCrm):
        est.lista_crear(doc, "Miembros", [{"nombre": "Plan", "tipo": "estado"}], AHORA)
    d = con_miembros(doc)
    assert [c["tipo"] for c in d["listas"][0]["campos"]] == ["texto", "estado", "dinero", "hora"]
    assert d["listas"][0]["campos"][1]["opciones"] == ["Básico", "Premium"]


def test_el_enum_que_ve_el_agente_no_cambia():
    assert est.TIPOS_DE_CAMPO == ("texto", "numero", "fecha", "lista")


def test_valores_validos_con_los_tipos_nuevos(doc):
    d = con_miembros(doc)
    c = {x["nombre"]: x["id"] for x in d["listas"][0]["campos"]}
    ok = est.valores_validos(d["listas"][0]["campos"], {c["Nombre"]: "Rosa", c["Plan"]: "premium", c["Cuota"]: "350", c["Clase"]: "7 pm"})
    assert ok == {c["Nombre"]: "Rosa", c["Plan"]: "Premium", c["Cuota"]: 350, c["Clase"]: "19:00"}


# ───────── lo opcional de las listas y los ejemplos ─────────

def _sembrada(doc):
    d = con_miembros(doc)
    l = d["listas"][0]
    l.update(vista="tablero", opciones={"por": l["campos"][1]["id"]}, icono="usuarios", grupo=1, ficha={"grupos": []}, tarjeta={"campos": []},
             opciones_estado={l["campos"][1]["id"]: ["Básico", "Premium"]}, mapeo_estado={}, origen="gimnasio")
    nombre = l["campos"][0]["id"]
    l["registros"] = [{"id": "e1", "valores": {nombre: "Ejemplo Uno"}, "creado": AHORA, "ejemplo": True},
                      {"id": "r1", "valores": {nombre: "Rosa"}, "creado": AHORA}]
    return d


def test_las_claves_nuevas_de_una_lista_sobreviven_a_las_funciones_de_carlos(doc):
    d = _sembrada(doc)
    lid, nombre = d["listas"][0]["id"], d["listas"][0]["campos"][0]["id"]
    d = est.lista_renombrar(d, lid, "Socios", AHORA)
    d = est.campo_agregar(d, lid, "Teléfono", "texto", AHORA)
    d = est.registro_actualizar(d, lid, "e1", {nombre: "Ejemplo Dos"}, AHORA)
    l = d["listas"][0]
    assert l["vista"] == "tablero" and l["origen"] == "gimnasio" and l["grupo"] == 1 and "mapeo_estado" in l
    assert l["registros"][0]["ejemplo"] is True and l["registros"][0]["valores"][nombre] == "Ejemplo Dos"


def test_la_vista_de_un_crm_de_esquema_2(doc):
    d = est.normalizar(_sembrada(doc))
    v = vista_crm(d, AHORA, puntos=[{"n": 1, "antes_de": "A mano: agregó a Rosa", "hora": "2026-10-13T15:00:00+00:00", "cambio": ["datos"], "foto": {"datos": {}}}])
    assert v["esquema"] == 2 and v["inicio"] == d["inicio"] and v["marca"] == {} and v["plantilla"] is None and v["toma"]["activa"] is False
    l = v["listas"][0]
    assert l["vista"] == "tablero" and l["icono"] == "usuarios" and l["grupo"] == 1 and l["origen"] == "gimnasio" and "opcionesEstado" in l
    assert "opciones_estado" not in l and "mapeo_estado" not in l
    assert l["registros"][0] == {"id": "e1", "valores": d["listas"][0]["registros"][0]["valores"], "ejemplo": True}
    assert "ejemplo" not in l["registros"][1]
    assert v["puntos"] == [{"n": 1, "antesDe": "A mano: agregó a Rosa", "hora": "2026-10-13T15:00:00+00:00", "cambio": ["datos"]}]  # sin foto


def test_un_crm_de_antes_se_ve_exactamente_igual(doc):
    v = vista_crm(doc, AHORA)
    assert "esquema" not in v and "inicio" not in v and "puntos" not in v


def test_quitar_ejemplos_borra_solo_los_ejemplos(doc):
    d = _sembrada(doc)
    d["contactos"].append({"id": "c1", "n": "Contacto de ejemplo", "canal": "x", "etapa": "Nuevo", "dueno": "Tú", "ultimo_contacto": AHORA, "extra": {}, "ejemplo": True})
    d["total_contactos"] = 1
    out = est.ejemplos_quitar(d, ahora=AHORA)
    assert [r["id"] for r in out["listas"][0]["registros"]] == ["r1"] and out["contactos"] == [] and out["total_contactos"] == 0
    assert "2 registros de ejemplo" in out["eventos"][0]["t"]
    with pytest.raises(ErrorCrm) as e:
        est.ejemplos_quitar(out, ahora=AHORA)
    assert e.value.estado == 404


def test_quitar_ejemplos_de_una_seccion(doc):
    d = _sembrada(doc)
    d["contactos"].append({"id": "c1", "n": "Ejemplo", "canal": "x", "etapa": "Nuevo", "dueno": "Tú", "ultimo_contacto": AHORA, "extra": {}, "ejemplo": True})
    out = est.ejemplos_quitar(d, d["listas"][0]["id"], AHORA)
    assert len(out["contactos"]) == 1 and [r["id"] for r in out["listas"][0]["registros"]] == ["r1"]
