"""edicion.py sobre lo que el laboratorio no tiene: secciones virtuales (contactos, tareas), registros de verdad, funciones de Carlos,
puntos de deshacer y el logo aparte. La paridad con el laboratorio está en test_herramientas_paridad.py."""
import copy

import pytest

from app.crm import operaciones as op
from app.crm import puntos, secciones_v
from app.crm.edicion import ejecutar
from app.crm.pantalla import describir_pantalla
from lab_doc import AHORA, doc_de_lab

PNG = "data:image/png;base64,iVBORw0KGgo="
E = {"bloques": [{"uid": "b0", "vista": "kpis", "seccion": "miembros", "opciones": {"por": "estado"}, "ancho": 12, "alto": 1}]}


def con_registros(doc):
    l = next(x for x in doc["listas"] if x["id"] == "l_miembros")
    l["registros"] = [{"id": "r1", "valores": {"nombre": "Ana", "plan": "Mensual", "estado": "Activa"}, "creado": AHORA},
                      {"id": "r2", "valores": {"nombre": "Rosa", "plan": "Anual", "estado": "Pausada"}, "creado": AHORA}]
    return doc


@pytest.fixture
def doc():
    return con_registros(doc_de_lab("membresias", E)[0])


@pytest.fixture
def con_contactos(doc):
    d = copy.deepcopy(doc)
    d["ocultas"] = ["cobros", "importar"]  # contactos y tareas a la vista
    d = op.contactos_crear(d, [{"n": "Ana Morales", "etapa": "Cliente"}, {"n": "Luis Pérez"}, {"n": "Eva Ruiz", "etapa": "Interesado"}], "WhatsApp", ahora=AHORA)
    return d


def sec(doc, sid):
    return next(s for s in secciones_v.secciones_de(doc) if s["id"] == sid)


def regs(doc, sid):
    return {r["id"]: r["valores"] for r in secciones_v.registros_de(doc, sid)}


def deshacer(antes, despues, texto="pedido"):
    d, p = puntos.con_punto(antes, despues, texto, AHORA)
    assert p is not None
    return puntos.deshacer(d, [p], p["n"], AHORA)["doc"]


# ───────── Estados: los registros pasan de verdad ─────────

def test_quitar_una_opcion_mueve_sus_registros(doc):
    r = ejecutar(doc, "cambiar_opciones_estado", {"seccion": "miembros", "campo": "estado", "opciones": ["Activa", "Cancelada"], "pasar_a": "Activa"})
    assert r["ok"], r["resultado"]
    assert r["resultado"].startswith("«Estado» de «Miembros» ahora tiene: Activa, Cancelada. Los registros pasan así: Pausada → Activa.")
    assert regs(r["doc"], "l_miembros")["r2"]["estado"] == "Activa"
    l = next(x for x in r["doc"]["listas"] if x["id"] == "l_miembros")
    campo = next(c for c in l["campos"] if c["id"] == "estado")
    assert campo == {"id": "estado", "nombre": "Estado", "tipo": "estado", "opciones": ["Activa", "Cancelada"]}  # sigue siendo «estado»
    assert l["opciones_estado"] == {"estado": ["Activa", "Cancelada"]} and l["mapeo_estado"] == {"estado": {"Pausada": "Activa"}}


def test_renombrar_una_opcion_renombra_sus_registros(doc):
    r = ejecutar(doc, "cambiar_opciones_estado", {"seccion": "miembros", "campo": "estado", "opciones": ["Activa", "En pausa", "Cancelada"],
                                                  "renombrar": {"Pausada": "En pausa"}})
    assert r["ok"], r["resultado"]
    assert regs(r["doc"], "l_miembros")["r2"]["estado"] == "En pausa" and regs(r["doc"], "l_miembros")["r1"]["estado"] == "Activa"


def test_etapas_de_los_contactos_con_destino(con_contactos):
    r = ejecutar(con_contactos, "cambiar_opciones_estado", {"seccion": "contactos", "campo": "etapa", "opciones": ["Prospecto", "Cliente"],
                                                            "renombrar": {"Nuevo": "Prospecto"}, "pasar_a": "Cliente"})
    assert r["ok"], r["resultado"]
    assert "Los registros pasan así: Nuevo → Prospecto, En contacto → Cliente, Interesado → Cliente." in r["resultado"]
    assert r["doc"]["etapas"] == ["Prospecto", "Cliente"]
    assert {c["n"]: c["etapa"] for c in r["doc"]["contactos"]} == {"Ana Morales": "Cliente", "Luis Pérez": "Prospecto", "Eva Ruiz": "Cliente"}


def test_los_estados_de_las_tareas_son_fijos(con_contactos):
    r = ejecutar(con_contactos, "cambiar_opciones_estado", {"seccion": "desarrollo", "campo": "estado", "opciones": ["A", "B"], "pasar_a": "A"})
    assert not r["ok"] and "son fijos" in r["resultado"] and r["doc"] is con_contactos


# ───────── Quitar: con las funciones de Carlos, y se puede deshacer de verdad ─────────

def test_quitar_una_lista_borra_sus_registros_y_deshacer_los_devuelve(doc):
    r = ejecutar(doc, "quitar_seccion", {"seccion": "miembros"})
    assert r["ok"], r["resultado"]
    assert "con sus registros (se puede deshacer)" in r["resultado"]
    assert all(l["id"] != "l_miembros" for l in r["doc"]["listas"]) and r["doc"]["inicio"] == []
    vuelta = deshacer(doc, r["doc"])
    assert regs(vuelta, "l_miembros") == regs(doc, "l_miembros") and vuelta["inicio"] == doc["inicio"]


def test_quitar_un_campo_borra_sus_valores_y_deshacer_los_devuelve(doc):
    d = ejecutar(doc, "cambiar_ficha", {"seccion": "miembros", "grupos": [{"titulo": "Datos", "campos": ["nombre", "plan"]}]})["doc"]
    d = ejecutar(d, "cambiar_tarjeta", {"seccion": "miembros", "campos": ["nombre", "plan"]})["doc"]
    r = ejecutar(d, "quitar_campo", {"seccion": "miembros", "campo": "plan"})
    assert r["ok"], r["resultado"]
    s = sec(r["doc"], "l_miembros")
    assert "plan" not in [c["id"] for c in s["campos"]] and "plan" not in regs(r["doc"], "l_miembros")["r1"]
    assert s["ficha"]["grupos"][0]["campos"] == ["nombre"] and s["tarjeta"] == {"campos": ["nombre"]}  # nada queda huérfano
    vuelta = deshacer(d, r["doc"])
    assert regs(vuelta, "l_miembros")["r1"]["plan"] == "Mensual" and "plan" in [c["id"] for c in sec(vuelta, "l_miembros")["campos"]]


def test_un_campo_que_usa_un_bloque_no_se_quita(doc):
    r = ejecutar(doc, "quitar_campo", {"seccion": "miembros", "campo": "estado"})
    assert not r["ok"] and "lo usan estos bloques del inicio: b0 (kpis)" in r["resultado"]


def test_quitar_una_seccion_del_sistema_solo_la_oculta(con_contactos):
    r = ejecutar(con_contactos, "quitar_seccion", {"seccion": "desarrollo"})
    assert r["ok"] and "sus datos se conservan" in r["resultado"]
    assert "desarrollo" in r["doc"]["ocultas"] and r["doc"]["tareas"] == con_contactos["tareas"]


# ───────── Secciones virtuales ─────────

def test_campo_nuevo_en_los_contactos_lleva_el_id_de_carlos_y_lo_dice(con_contactos):
    r = ejecutar(con_contactos, "agregar_campo", {"seccion": "contactos", "nombre": "cumpleanos", "tipo": "fecha"}, {"texto": "pon el cumpleaños"})
    assert r["ok"], r["resultado"]
    c = r["doc"]["campos_contacto"][-1]
    assert c["id"].startswith("f_") and c["nombre"] == "Cumpleaños" and c["tipo"] == "fecha"
    assert r["resultado"].startswith(f"Campo «Cumpleaños» (fecha) agregado a «Pacientes». Su id es {c['id']}.")


def test_campo_nuevo_en_una_lista_lleva_su_slug(doc):
    r = ejecutar(doc, "agregar_campo", {"seccion": "miembros", "nombre": "Teléfono", "tipo": "texto", "ejemplos": ["5555-1234"]})
    assert r["ok"], r["resultado"]
    c = next(x for x in r["doc"]["listas"] if x["id"] == "l_miembros")["campos"][-1]
    assert c == {"id": "telefono", "nombre": "Teléfono", "tipo": "texto", "ejemplos": ["5555-1234"]}
    assert " Su id es" not in r["resultado"]


@pytest.mark.parametrize("nombre,args,texto", [
    ("agregar_campo", {"seccion": "desarrollo", "nombre": "Prioridad", "tipo": "texto"}, "no admite campos nuevos"),
    ("quitar_campo", {"seccion": "contactos", "campo": "canal"}, "es fijo"),
    ("renombrar_campo", {"seccion": "contactos", "campo": "nombre", "nombre": "Cliente"}, "es fijo"),
    ("renombrar_campo", {"seccion": "desarrollo", "campo": "vence", "nombre": "Fecha"}, "es fijo"),
    ("cambiar_ficha", {"seccion": "contactos", "grupos": [{"titulo": "A", "campos": ["nombre"]}]}, "todavía no se puede cambiar"),
    ("cambiar_tarjeta", {"seccion": "desarrollo", "campos": ["tarea"]}, "todavía no se puede cambiar"),
])
def test_lo_fijo_de_las_secciones_del_sistema(con_contactos, nombre, args, texto):
    r = ejecutar(con_contactos, nombre, args)
    assert not r["ok"] and texto in r["resultado"] and r["doc"] is con_contactos and r["etiqueta"] is None


def test_renombrar_campo_de_los_contactos_y_la_seccion(con_contactos):
    d = ejecutar(con_contactos, "agregar_campo", {"seccion": "contactos", "nombre": "Ciudad", "tipo": "texto"})["doc"]
    fid = d["campos_contacto"][-1]["id"]
    r = ejecutar(d, "renombrar_campo", {"seccion": "contactos", "campo": fid, "nombre": "Municipio"})
    assert r["ok"] and d["campos_contacto"][-1]["nombre"] == "Ciudad" and r["doc"]["campos_contacto"][-1]["nombre"] == "Municipio"
    r2 = ejecutar(r["doc"], "renombrar_seccion", {"seccion": "Pacientes", "titulo": "Socios"})
    assert r2["ok"] and r2["resultado"].startswith("«Pacientes» ahora se llama «Socios».") and r2["doc"]["secciones"]["contactos"] == "Socios"


def test_abrir_una_pestana_fija_de_carlos(doc):
    r = ejecutar(doc, "abrir_seccion", {"seccion": "Historial"})
    assert r["ok"] and r["vista"] == "actividad" and r["etiqueta"] is None


# ───────── Secciones nuevas ─────────

def test_crear_seccion_va_antes_de_las_de_abajo_y_guarda_lo_del_esquema_2(doc):
    r = ejecutar(doc, "crear_seccion", {"desde": "inventario", "con_piezas": True})
    assert r["ok"], r["resultado"]
    ids = [l["id"] for l in r["doc"]["listas"]]
    assert ids == ["l_miembros", "l_inventario", "l_pagos"]  # Pagos es del grupo de abajo
    l = r["doc"]["listas"][1]
    assert (l["origen"], l["vista"], l["icono"], l["registros"]) == ("inventario", "tablero", "tabla", [])
    assert [c["id"] for c in l["campos"]] == ["producto", "categoria", "existencia", "costo", "minimo", "estado"]  # los de la pestaña base
    nuevas = [b for b in r["doc"]["inicio"] if b["seccion"] == "l_inventario"]
    assert nuevas and "En el inicio se agregaron" in r["resultado"]
    assert r["etiqueta"] == "creó la pestaña «inventario»"


def test_crear_seccion_tablero_sin_estado_no_se_crea(doc):
    r = ejecutar(doc, "crear_seccion", {"titulo": "Clases", "vista": "tablero", "campos": [{"nombre": "Clase", "tipo": "texto"}]})
    assert not r["ok"] and "la vista «tablero» necesita la opción «por»" in r["resultado"] and r["doc"] is doc


# ───────── Logo y marca ─────────

def test_usar_logo_guarda_el_id_y_devuelve_la_imagen_para_guardarla(doc):
    r = ejecutar(doc, "usar_logo", {}, {"imagen": PNG})
    assert r["ok"] and r["doc"]["marca"]["logo_id"] == r["logo"]["id"] and r["logo"]["imagen"] == PNG
    r2 = ejecutar(doc, "usar_logo", {}, {"imagen": PNG, "logo_id": "img_123"})
    assert r2["doc"]["marca"] == {"logo_id": "img_123"} and "logo" not in r2
    pantalla = describir_pantalla(r2["doc"])
    assert pantalla["marca"]["logo"] == "(tiene logo)" and "logo_id" not in pantalla["marca"]
    r3 = ejecutar(r2["doc"], "cambiar_marca", {"primario": "#16A34A"})
    assert r3["resultado"].startswith("Marca aplicada: primario #16A34A.") and r3["doc"]["marca"]["logo_id"] == "img_123"
    assert ejecutar(r3["doc"], "restablecer_marca", {})["doc"]["marca"] == {}


def test_agregar_grafico_acepta_nombre_visible(doc):
    r = ejecutar(doc, "agregar_bloque", {"seccion": "miembros", "vista": "grafico", "opciones": {"tipo": "Dona"}})
    assert r["ok"], r["resultado"]
    graficos = [b for b in r["doc"]["inicio"] if b.get("vista") == "grafico"]
    assert graficos and (graficos[-1].get("opciones") or {}).get("tipo") == "dona"


def test_no_cambia_el_documento_que_recibe(doc):
    antes = copy.deepcopy(doc)
    for nombre, args in [("agregar_bloque", {"seccion": "miembros", "vista": "tabla"}), ("cambiar_marca", {"primario": "#000000"}),
                         ("crear_seccion", {"titulo": "Gastos", "campos": [{"nombre": "Monto", "tipo": "dinero"}]}),
                         ("cambiar_opciones_estado", {"seccion": "miembros", "campo": "estado", "opciones": ["Activa", "Cancelada"], "pasar_a": "Activa"}),
                         ("quitar_campo", {"seccion": "miembros", "campo": "plan"}), ("quitar_seccion", {"seccion": "pagos"})]:
        assert ejecutar(doc, nombre, args)["ok"], nombre
        assert doc == antes, nombre


def test_describir_incluye_las_secciones_virtuales(con_contactos):
    p = describir_pantalla(con_contactos, "inicio", [{"n": 3, "antes_de": "pon verde", "cambio": ["marca"], "hora": "10:00"}])
    assert [s["id"] for s in p["secciones"]][:2] == ["contactos", "desarrollo"]
    assert p["pedidos_anteriores"] == [{"pedido": 3, "dijo": "pon verde", "cambio": ["marca"], "hora": "10:00"}]
    assert "pestanas_base" in p and "conteo" not in str(p["secciones"][0])  # sin números de registros (decisión medida)


# ───────── Toma de diseño y despacho ─────────

def test_construir_desde_la_ficha_con_el_lienzo_y_la_validacion_reales(doc):
    d = ejecutar(doc, "abrir_toma", {"objetivo": "ver mis miembros"})["doc"]
    d = ejecutar(d, "anotar_bloque", {"que": "resumen", "seccion": "miembros"})["doc"]
    d = ejecutar(d, "anotar_bloque", {"que": "grafica", "seccion": "miembros", "grafico": "dona"})["doc"]
    from app.crm.edicion import construir_desde_ficha
    r = construir_desde_ficha(d, ahora_ms=1_700_000_000_000)
    assert r["errores"] == []
    assert [(b["vista"], b["seccion"], b["ancho"]) for b in r["doc"]["inicio"]] == [("kpis", "l_miembros", 12), ("grafico", "l_miembros", 12)]
    assert r["doc"]["toma"]["activa"] is False
    malo = copy.deepcopy(d)
    malo["toma"]["ficha"]["bloques"].append({"vista": "tablero", "seccion": "l_pagos", "opciones": {"por": "monto"}})
    r2 = construir_desde_ficha(malo, ahora_ms=1_700_000_000_000)
    assert r2["errores"] and "«por» debe ser un campo de tipo estado" in r2["errores"][0] and r2["doc"]["inicio"] == doc["inicio"]


@pytest.mark.parametrize("nombre", ["agregar_registro", "consultar_datos", "deshacer", "leer_enlace"])
def test_lo_que_despacha_el_chat_no_pasa_por_aqui(doc, nombre):
    with pytest.raises(ValueError):
        ejecutar(doc, nombre, {})
