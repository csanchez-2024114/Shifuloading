"""Pruebas de la estructura del CRM: etapas, secciones visibles, secciones propias, campos y registros. Sin base de datos."""
from datetime import datetime, timezone

import pytest

from app.crm import estructura as est
from app.crm import operaciones as op
from app.crm.chat import ejecutar_pendiente, responder, sanear_pendiente
from app.crm.generador import generar
from app.crm.vista import vista_crm

AHORA = datetime(2026, 10, 13, 15, 0, tzinfo=timezone.utc)
BRIEF = {"nombre": "Clínica Sol", "rubro": "salud", "equipo": "solo", "canales": ["whatsapp"], "objetivos": ["seguimientos"]}


@pytest.fixture
def doc():
    d = generar("u1", BRIEF, AHORA)
    return op.contactos_crear(d, [{"n": "Ana Morales"}, {"n": "Luis Pérez"}], "WhatsApp", ahora=AHORA)


def con_proveedores(doc):
    return est.lista_crear(doc, "proveedores", [{"nombre": "Nombre", "tipo": "texto"}, {"nombre": "Teléfono"}, {"nombre": "Próxima compra", "tipo": "fecha"},
                                                 {"nombre": "Deuda", "tipo": "numero"}], AHORA)


def test_un_crm_nuevo_trae_la_estructura_por_defecto():
    d = generar("u1", BRIEF, AHORA)
    assert d["etapas"] == ["Nuevo", "En contacto", "Interesado", "Cliente"]
    assert d["ocultas"] == [] and d["campos_contacto"] == [] and d["listas"] == []


def test_un_crm_guardado_antes_recibe_los_campos_nuevos():
    viejo = generar("u1", BRIEF, AHORA)
    for k in ("etapas", "ocultas", "campos_contacto", "listas"):
        del viejo[k]
    viejo["contactos"] = [{"id": "a", "n": "Ana", "canal": "x", "etapa": "Nuevo", "dueno": "Tú", "ultimo_contacto": AHORA}]
    n = est.normalizar(viejo)
    assert n["etapas"] and n["listas"] == [] and n["contactos"][0]["extra"] == {}
    assert est.normalizar(n) == n  # repetirlo no cambia nada


# ───────── Etapas ─────────

def test_cambiar_las_etapas_conserva_las_que_siguen_y_reubica_las_demas(doc):
    d = op.contactos_actualizar(doc, doc["contactos"][0]["id"], {"etapa": "Cliente"}, ahora=AHORA)   # Ana -> Cliente
    n = est.etapas_definir(d, ["Prospecto", "Cotización", "Negociación", "Cliente"], AHORA)
    etapa = {c["n"]: c["etapa"] for c in n["contactos"]}
    assert n["etapas"] == ["Prospecto", "Cotización", "Negociación", "Cliente"]
    assert etapa["Ana Morales"] == "Cliente"      # se conserva
    assert etapa["Luis Pérez"] == "Prospecto"     # "Nuevo" (lugar 1) pasa al lugar 1
    assert "Cambiaste las etapas" in n["eventos"][0]["t"]


def test_si_las_etapas_nuevas_son_menos_los_contactos_van_a_la_ultima(doc):
    d = op.contactos_actualizar(doc, doc["contactos"][0]["id"], {"etapa": "Cliente"}, ahora=AHORA)
    n = est.etapas_definir(d, ["Abierto", "Cerrado"], AHORA)
    assert {c["etapa"] for c in n["contactos"]} <= {"Abierto", "Cerrado"}


def test_etapas_invalidas(doc):
    for malas in ([], ["Una sola"], ["a", "A"], ["x"] * 9, [str(i) for i in range(9)]):
        with pytest.raises(op.ErrorCrm):
            est.etapas_definir(doc, malas)


def test_los_contactos_nuevos_entran_en_la_primera_etapa_propia(doc):
    d = est.etapas_definir(doc, ["Prospecto", "Cliente"], AHORA)
    d = op.contactos_crear(d, [{"n": "Pedro"}], "Chat", ahora=AHORA)
    assert d["contactos"][0]["etapa"] == "Prospecto"
    with pytest.raises(op.ErrorCrm):
        op.contactos_actualizar(d, d["contactos"][0]["id"], {"etapa": "Nuevo"})  # la etapa vieja ya no existe


# ───────── Secciones ─────────

def test_ocultar_y_volver_a_mostrar_una_seccion_integrada(doc):
    n = est.seccion_ocultar(doc, "cobros", AHORA)
    assert n["ocultas"] == ["cobros"] and "Quitaste la sección" in n["eventos"][0]["t"]
    assert est.seccion_ocultar(n, "cobros") is n  # ya estaba oculta: no hace nada
    assert est.seccion_mostrar(n, "cobros", AHORA)["ocultas"] == []
    assert vista_crm(n, AHORA)["ocultas"] == ["cobros"]


def test_no_se_pueden_ocultar_todas_las_secciones(doc):
    d = doc
    for sid in ("contactos", "cobros", "desarrollo", "actividad", "rrhh", "importar"):
        d = est.seccion_ocultar(d, sid, AHORA)
    with pytest.raises(op.ErrorCrm):
        est.seccion_ocultar(d, "automatizaciones")        # sería la última visible
    d = con_proveedores(d)
    d = est.seccion_ocultar(d, "automatizaciones", AHORA)  # con una sección propia visible ya se puede
    with pytest.raises(op.ErrorCrm):
        est.lista_eliminar(d, d["listas"][0]["id"])        # ahora la propia es la última visible


def test_seccion_inexistente(doc):
    with pytest.raises(op.ErrorCrm):
        est.seccion_ocultar(doc, "no-existe")
    with pytest.raises(op.ErrorCrm):
        est.seccion_mostrar(doc, "no-existe")


def test_crear_una_seccion_propia_con_sus_campos(doc):
    n = con_proveedores(doc)
    l = n["listas"][0]
    assert l["nombre"] == "Proveedores" and l["id"].startswith("l_") and l["registros"] == []
    assert [(c["nombre"], c["tipo"]) for c in l["campos"]] == [("Nombre", "texto"), ("Teléfono", "texto"), ("Próxima compra", "fecha"), ("Deuda", "numero")]
    assert "Creaste la sección" in n["eventos"][0]["t"]
    assert vista_crm(n, AHORA)["listas"][0]["campos"][1]["nombre"] == "Teléfono"


def test_una_seccion_sin_campos_lleva_uno_llamado_nombre(doc):
    n = est.lista_crear(doc, "Ideas", None, AHORA)
    assert [c["nombre"] for c in n["listas"][0]["campos"]] == ["Nombre"]


def test_nombres_de_seccion_repetidos_o_vacios(doc):
    n = con_proveedores(doc)
    for malo in ("proveedores", "  ", "Pacientes", "Automatizaciones"):
        with pytest.raises(op.ErrorCrm):
            est.lista_crear(n, malo, None)
    with pytest.raises(op.ErrorCrm):
        est.lista_crear(doc, "Con campos repetidos", [{"nombre": "a"}, {"nombre": "A"}])
    with pytest.raises(op.ErrorCrm):
        est.lista_crear(doc, "Tipo raro", [{"nombre": "a", "tipo": "color"}])


def test_tope_de_secciones_y_campos(doc):
    d = doc
    for i in range(est.MAX_LISTAS):
        d = est.lista_crear(d, f"Sección {i}", None)
    with pytest.raises(op.ErrorCrm):
        est.lista_crear(d, "Una más", None)
    with pytest.raises(op.ErrorCrm):
        est.lista_crear(doc, "Muchos", [{"nombre": f"c{i}"} for i in range(est.MAX_CAMPOS + 1)])


def test_renombrar_y_eliminar_una_seccion_propia(doc):
    n = con_proveedores(doc)
    lid = n["listas"][0]["id"]
    n = op.seccion_renombrar(n, lid, "Mis proveedores", AHORA)
    assert n["listas"][0]["nombre"] == "Mis proveedores"
    n = est.lista_eliminar(n, lid, AHORA)
    assert n["listas"] == []
    with pytest.raises(op.ErrorCrm):
        est.lista_eliminar(n, lid)


# ───────── Campos ─────────

def test_campos_extra_de_los_contactos_con_valores_validados(doc):
    d = est.campo_agregar(doc, "contactos", "cumpleaños", "fecha", AHORA)
    d = est.campo_agregar(d, "contactos", "Presupuesto", "numero", AHORA)
    cumple, pres = d["campos_contacto"][0]["id"], d["campos_contacto"][1]["id"]
    d = op.contactos_actualizar(d, d["contactos"][0]["id"], {"extra": {cumple: "25/12/1990", pres: "1,500.50"}}, ahora=AHORA)
    assert d["contactos"][0]["extra"] == {cumple: "1990-12-25", pres: 1500.5}
    assert vista_crm(d, AHORA)["contactos"][0]["extra"][cumple] == "1990-12-25"
    with pytest.raises(op.ErrorCrm):
        op.contactos_actualizar(d, d["contactos"][0]["id"], {"extra": {pres: "mucho"}})
    with pytest.raises(op.ErrorCrm):
        op.contactos_actualizar(d, d["contactos"][0]["id"], {"extra": {"f_inventado": "x"}})


def test_los_contactos_nuevos_pueden_traer_campos_extra(doc):
    d = est.campo_agregar(doc, "contactos", "Teléfono", "texto", AHORA)
    cid = d["campos_contacto"][0]["id"]
    d = op.contactos_crear(d, [{"n": "Pedro", "extra": {cid: "5555-1234"}}], "Chat", ahora=AHORA)
    assert d["contactos"][0]["extra"] == {cid: "5555-1234"}


def test_quitar_un_campo_borra_sus_valores(doc):
    d = est.campo_agregar(doc, "contactos", "Teléfono", "texto", AHORA)
    cid = d["campos_contacto"][0]["id"]
    d = op.contactos_actualizar(d, d["contactos"][0]["id"], {"extra": {cid: "5555"}}, ahora=AHORA)
    d = est.campo_eliminar(d, "contactos", cid, AHORA)
    assert d["campos_contacto"] == [] and d["contactos"][0]["extra"] == {}


def test_una_seccion_propia_no_puede_quedarse_sin_campos(doc):
    n = est.lista_crear(doc, "Ideas", None, AHORA)
    with pytest.raises(op.ErrorCrm):
        est.campo_eliminar(n, n["listas"][0]["id"], n["listas"][0]["campos"][0]["id"])


def test_campos_repetidos_o_de_tipo_raro(doc):
    d = est.campo_agregar(doc, "contactos", "Edad", "numero", AHORA)
    with pytest.raises(op.ErrorCrm):
        est.campo_agregar(d, "contactos", "edad", "numero")
    with pytest.raises(op.ErrorCrm):
        est.campo_agregar(d, "contactos", "Otro", "booleano")
    with pytest.raises(op.ErrorCrm):
        est.campo_agregar(d, "l_inexistente", "X", "texto")


# ───────── Registros ─────────

def test_agregar_cambiar_y_quitar_registros(doc):
    n = con_proveedores(doc)
    l = n["listas"][0]
    nombre, tel, fecha, deuda = (c["id"] for c in l["campos"])
    n = est.registro_agregar(n, l["id"], {nombre: "Ferretería Díaz", tel: "5555-1234", fecha: "2026-11-02", deuda: "1200"}, AHORA)
    r = n["listas"][0]["registros"][0]
    assert r["valores"] == {nombre: "Ferretería Díaz", tel: "5555-1234", fecha: "2026-11-02", deuda: 1200}
    n = est.registro_actualizar(n, l["id"], r["id"], {deuda: 900, tel: ""}, AHORA)
    assert n["listas"][0]["registros"][0]["valores"][deuda] == 900 and tel not in n["listas"][0]["registros"][0]["valores"]
    assert est.resumen_de_registro(n["listas"][0], n["listas"][0]["registros"][0]) == "Ferretería Díaz · 2026-11-02"
    n = est.registro_eliminar(n, l["id"], r["id"], AHORA)
    assert n["listas"][0]["registros"] == []


def test_registros_invalidos(doc):
    n = con_proveedores(doc)
    l = n["listas"][0]
    nombre, _, fecha, deuda = (c["id"] for c in l["campos"])
    for malo in ({}, {nombre: ""}, {deuda: "mucho"}, {fecha: "mañana"}, {"f_inventado": "x"}):
        with pytest.raises(op.ErrorCrm):
            est.registro_agregar(n, l["id"], malo)
    with pytest.raises(op.ErrorCrm):
        est.registro_actualizar(n, l["id"], "no-existe", {nombre: "x"})
    with pytest.raises(op.ErrorCrm):
        est.registro_eliminar(n, "l_no", "x")


@pytest.mark.parametrize("tipo,entrada,esperado", [
    ("numero", "1,250", 1250), ("numero", "Q 1.500,50".replace(".", "").replace(",", "."), 1500.5), ("numero", 7.0, 7), ("numero", "3,5", 3.5),
    ("fecha", "2026-01-31", "2026-01-31"), ("fecha", "31/01/2026", "2026-01-31"), ("fecha", "31-01-2026", "2026-01-31"),
    ("texto", "  hola ", "hola"), ("texto", None, None), ("numero", "", None),
])
def test_valores_por_tipo(tipo, entrada, esperado):
    assert est.valor_de_tipo(tipo, entrada, "campo") == esperado


@pytest.mark.parametrize("tipo,entrada", [("numero", "abc"), ("numero", True), ("fecha", "31/31/2026"), ("fecha", "ayer"), ("color", "rojo")])
def test_valores_que_no_sirven(tipo, entrada):
    with pytest.raises(op.ErrorCrm):
        est.valor_de_tipo(tipo, entrada, "campo")


# ───────── Confirmaciones de lo nuevo (las resuelven las reglas, sin IA) ─────────

def test_el_pendiente_acepta_solo_la_forma_de_cada_tipo():
    assert sanear_pendiente({"tipo": "lista", "id": "l_1", "extra": "x"}) == {"tipo": "lista", "id": "l_1"}
    assert sanear_pendiente({"tipo": "registro", "lista": "l_1", "id": "r1"}) == {"tipo": "registro", "lista": "l_1", "id": "r1"}
    assert sanear_pendiente({"tipo": "campo", "ambito": "contactos", "id": "f_1"}) == {"tipo": "campo", "ambito": "contactos", "id": "f_1"}
    for malo in ({"tipo": "registro", "id": "r1"}, {"tipo": "campo", "id": "f_1"}, {"tipo": "lista"}, {"tipo": "borrar_todo", "id": "x"}, {"tipo": "lista", "id": ""}):
        assert sanear_pendiente(malo) is None


def test_confirmar_el_borrado_de_cada_cosa_nueva(doc):
    d = con_proveedores(doc)
    l = d["listas"][0]
    d = est.registro_agregar(d, l["id"], {l["campos"][0]["id"]: "Ferretería Díaz"}, AHORA)
    d = est.campo_agregar(d, "contactos", "Teléfono", "texto", AHORA)
    cid = d["campos_contacto"][0]["id"]
    rid = d["listas"][0]["registros"][0]["id"]

    n, msg = ejecutar_pendiente(d, {"tipo": "registro", "lista": l["id"], "id": rid}, AHORA)
    assert n["listas"][0]["registros"] == [] and "Ferretería Díaz" in msg
    n, msg = ejecutar_pendiente(d, {"tipo": "campo", "ambito": "contactos", "id": cid}, AHORA)
    assert n["campos_contacto"] == [] and "Teléfono" in msg
    n, msg = ejecutar_pendiente(d, {"tipo": "lista", "id": l["id"]}, AHORA)
    assert n["listas"] == [] and "Proveedores" in msg
    r = responder(d, "sí", {"tipo": "lista", "id": l["id"]}, AHORA)          # por el chat de reglas
    assert r["doc"]["listas"] == [] and "Proveedores" in r["respuesta"]
    r = responder(d, "no", {"tipo": "lista", "id": l["id"]}, AHORA)
    assert r["doc"] is d and "no borré nada" in r["respuesta"]


def test_confirmar_algo_que_ya_no_existe_no_rompe(doc):
    r = responder(doc, "sí", {"tipo": "lista", "id": "l_ya_no"}, AHORA)
    assert r["doc"] is doc and "ya no existe" in r["respuesta"]


def test_las_reglas_renombran_una_seccion_propia_y_usan_las_etapas_del_crm(doc):
    d = con_proveedores(doc)
    r = responder(d, "Renombra Proveedores a Mis proveedores", None, AHORA)
    assert r["doc"]["listas"][0]["nombre"] == "Mis Proveedores"
    d = est.etapas_definir(d, ["Prospecto", "Cliente"], AHORA)
    r = responder(d, "Mueve a Ana Morales a Cliente", None, AHORA)
    assert next(c for c in r["doc"]["contactos"] if c["n"] == "Ana Morales")["etapa"] == "Cliente"
