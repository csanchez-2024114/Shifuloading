"""Secciones virtuales (contrato §2): contactos, tareas y secciones propias con una sola forma, escribiendo con las funciones de Carlos."""
from datetime import datetime, timedelta, timezone

import pytest

from assistant.packs.crm import estructura as est
from assistant.packs.crm import operaciones as op
from assistant.packs.crm import secciones_v as sv
from assistant.packs.crm.generador import generar
from assistant.packs.crm.operaciones import ErrorCrm

AHORA = datetime(2026, 10, 13, 15, 0, tzinfo=timezone.utc)
MANANA = (AHORA + timedelta(days=1)).date().isoformat()
BRIEF = {"nombre": "Clínica Sol", "rubro": "salud"}


@pytest.fixture
def doc():
    d = generar("u1", BRIEF, AHORA)
    d = est.campo_agregar(d, "contactos", "Teléfono", "texto", AHORA)
    d = op.vendedor_agregar(d, "Marta", AHORA)
    d = op.contactos_crear(d, [{"n": "Ana Morales", "det": "Limpieza"}], "WhatsApp", ahora=AHORA)
    d = op.tareas_crear(d, "Llamar a Ana", AHORA, MANANA, "10:00")
    return est.lista_crear(d, "Proveedores", [{"nombre": "Nombre"}, {"nombre": "Deuda", "tipo": "dinero"}], AHORA)


def _ids(doc):
    l = doc["listas"][0]
    return l["id"], {c["nombre"]: c["id"] for c in l["campos"]}


def test_secciones_de_trae_todo_lo_que_tiene_registros_en_orden(doc):
    s = sv.secciones_de(doc)
    lid, _ = _ids(doc)
    assert [x["id"] for x in s] == ["contactos", "desarrollo", lid]
    assert [x["virtual"] for x in s] == ["contactos", "tareas", None]
    assert s[0]["titulo"] == "Pacientes" and s[1]["titulo"] == "Tratamientos" and s[2]["titulo"] == "Proveedores"
    tel = doc["campos_contacto"][0]["id"]
    assert [c["id"] for c in s[0]["campos"]] == ["nombre", "detalle", "canal", "etapa", "responsable", tel]
    assert s[0]["campos"][3] == {"id": "etapa", "nombre": "Etapa", "tipo": "estado", "opciones": doc["etapas"]}
    assert [c["id"] for c in s[1]["campos"]] == ["tarea", "vence", "hora", "estado"]
    assert s[1]["campos"][3]["opciones"] == ["Por hacer", "En curso", "Hecho"]
    assert all({"id", "titulo", "campos", "vista", "opciones", "icono", "grupo", "virtual"} <= set(x) for x in s)


def test_las_integradas_ocultas_no_son_secciones(doc):
    d = est.seccion_ocultar(doc, "contactos", AHORA)
    assert "contactos" not in [x["id"] for x in sv.secciones_de(d)]
    with pytest.raises(ErrorCrm) as e:
        sv.registros_de(d, "contactos")
    assert e.value.estado == 404


def test_registros_de_contactos_y_tareas_con_la_forma_uniforme(doc):
    ana = sv.registros_de(doc, "contactos")[0]
    assert ana["valores"] == {"nombre": "Ana Morales", "detalle": "Limpieza", "canal": "WhatsApp", "etapa": "Nuevo", "responsable": "Tú"}
    t = sv.registros_de(doc, "desarrollo")[0]
    assert t["valores"] == {"tarea": "Llamar a Ana", "vence": MANANA, "hora": "10:00", "estado": "Por hacer"}


def test_agregar_un_contacto_va_a_operaciones(doc):
    tel = doc["campos_contacto"][0]["id"]
    out, r = sv.registro_agregar(doc, "contactos", {"nombre": "Rosa Díaz", "etapa": "interesado", "responsable": "marta", tel: "5555-1234"}, AHORA)
    assert out["total_contactos"] == 2 and out["contactos"][0]["n"] == "Rosa Díaz"
    assert r["valores"] == {"nombre": "Rosa Díaz", "canal": "Chat", "etapa": "Interesado", "responsable": "Marta", tel: "5555-1234"}
    assert out["eventos"][0]["t"] == "Agregaste a Rosa Díaz"
    assert doc["total_contactos"] == 1  # puro: el original no cambia


@pytest.mark.parametrize("valores", [{"detalle": "sin nombre"}, {"nombre": "X", "etapa": "Perdido"}, {"nombre": "X", "responsable": "Nadie"},
                                     {"nombre": "X", "raro": 1}, {"nombre": "x" * 41}])
def test_agregar_un_contacto_que_no_sirve(doc, valores):
    with pytest.raises(ErrorCrm):
        sv.registro_agregar(doc, "contactos", valores, AHORA)


def test_editar_y_eliminar_un_contacto(doc):
    cid = doc["contactos"][0]["id"]
    tel = doc["campos_contacto"][0]["id"]
    out, r = sv.registro_actualizar(doc, "contactos", cid, {"etapa": "Cliente", tel: "4444"}, AHORA)
    assert r["valores"]["etapa"] == "Cliente" and r["valores"][tel] == "4444" and out["eventos"][0]["t"] == "Ana Morales pasó a “Cliente”"
    out = sv.registro_eliminar(out, "contactos", cid, AHORA)
    assert out["contactos"] == [] and out["total_contactos"] == 0
    with pytest.raises(ErrorCrm):
        sv.registro_actualizar(out, "contactos", cid, {"etapa": "Cliente"}, AHORA)


def test_tareas_con_estado(doc):
    out, r = sv.registro_agregar(doc, "desarrollo", {"tarea": "Pedir insumos", "estado": "en curso"}, AHORA)
    assert r["valores"] == {"tarea": "Pedir insumos", "estado": "En curso"}
    assert [t["t"] for t in out["tareas"]["enCurso"]] == ["Pedir insumos"]
    out, r = sv.registro_actualizar(out, "desarrollo", r["id"], {"estado": "Hecho", "vence": MANANA}, AHORA)
    assert out["tareas"]["enCurso"] == [] and out["tareas"]["hecho"][0]["vence"] == MANANA and r["valores"]["estado"] == "Hecho"
    out = sv.registro_eliminar(out, "desarrollo", r["id"], AHORA)
    assert out["tareas"]["hecho"] == []


def test_una_tarea_con_estado_que_no_existe(doc):
    with pytest.raises(ErrorCrm):
        sv.registro_agregar(doc, "desarrollo", {"tarea": "X", "estado": "Archivada"}, AHORA)
    with pytest.raises(ErrorCrm):
        sv.registro_agregar(doc, "desarrollo", {"vence": MANANA}, AHORA)


def test_las_listas_van_a_estructura(doc):
    lid, c = _ids(doc)
    out, r = sv.registro_agregar(doc, lid, {c["Nombre"]: "Ferretería Díaz", c["Deuda"]: "Q 1,200"}, AHORA)
    assert r == {"id": out["listas"][0]["registros"][0]["id"], "valores": {c["Nombre"]: "Ferretería Díaz", c["Deuda"]: 1200}}
    out, r = sv.registro_actualizar(out, lid, r["id"], {c["Deuda"]: 0}, AHORA)
    assert r["valores"][c["Deuda"]] == 0
    out = sv.registro_eliminar(out, lid, r["id"], AHORA)
    assert out["listas"][0]["registros"] == []


def test_una_seccion_que_no_existe(doc):
    with pytest.raises(ErrorCrm) as e:
        sv.registro_agregar(doc, "l_nada", {"x": 1}, AHORA)
    assert e.value.estado == 404


def test_el_ejemplo_se_ve_en_la_forma_uniforme(doc):
    lid, c = _ids(doc)
    doc["listas"][0]["registros"] = [{"id": "e1", "valores": {c["Nombre"]: "Ejemplo"}, "creado": AHORA, "ejemplo": True}]
    assert sv.registros_de(doc, lid) == [{"id": "e1", "valores": {c["Nombre"]: "Ejemplo"}, "ejemplo": True}]


# ───────── Lo que pide registros.py (C1) ─────────

def test_agregar_con_un_id_ya_generado(doc):
    lid, c = _ids(doc)
    out, r = sv.registro_agregar(doc, lid, {c["Nombre"]: "Ferretería Díaz"}, AHORA, id=f"{lid}-p1")
    assert r["id"] == f"{lid}-p1" and out["listas"][0]["registros"][0]["id"] == f"{lid}-p1"
    out, r = sv.registro_agregar(out, "contactos", {"nombre": "Rosa"}, AHORA, id="contactos-p1")
    assert r["id"] == "contactos-p1" and out["contactos"][0]["id"] == "contactos-p1"
    out, r = sv.registro_agregar(out, "desarrollo", {"tarea": "Llamar", "estado": "Hecho"}, AHORA, id="desarrollo-p1")
    assert r["id"] == "desarrollo-p1" and out["tareas"]["hecho"][0]["id"] == "desarrollo-p1"
    with pytest.raises(ErrorCrm) as e:
        sv.registro_agregar(out, lid, {c["Nombre"]: "Otra"}, AHORA, id=f"{lid}-p1")
    assert e.value.estado == 409
    _, r = sv.registro_agregar(out, lid, {c["Nombre"]: "Sin id"}, AHORA)
    assert len(r["id"]) == 32  # sin id, como siempre


def test_vacio_en_una_edicion_guarda_el_vacio_de_carlos(doc):
    lid, c = _ids(doc)
    out, r = sv.registro_agregar(doc, lid, {c["Nombre"]: "Ferretería", c["Deuda"]: 100}, AHORA)
    out, r = sv.registro_actualizar(out, lid, r["id"], {c["Deuda"]: ""}, AHORA)
    assert r["valores"] == {c["Nombre"]: "Ferretería"} and c["Deuda"] not in out["listas"][0]["registros"][0]["valores"]
    cid, tel = doc["contactos"][0]["id"], doc["campos_contacto"][0]["id"]
    out, _ = sv.registro_actualizar(out, "contactos", cid, {tel: "5555"}, AHORA)
    out, r = sv.registro_actualizar(out, "contactos", cid, {"detalle": "", tel: ""}, AHORA)
    contacto = next(x for x in out["contactos"] if x["id"] == cid)
    assert contacto["det"] is None and contacto["extra"] == {} and "detalle" not in r["valores"]
    tid = out["tareas"]["porHacer"][0]["id"]
    out, r = sv.registro_actualizar(out, "desarrollo", tid, {"vence": "", "hora": ""}, AHORA)
    assert r["valores"] == {"tarea": "Llamar a Ana", "estado": "Por hacer"}
    for sec, rid, campo in (("contactos", cid, "nombre"), ("contactos", cid, "etapa"), ("desarrollo", tid, "tarea"), ("desarrollo", tid, "estado")):
        with pytest.raises(ErrorCrm):
            sv.registro_actualizar(out, sec, rid, {campo: ""}, AHORA)


def test_lista_es_estado_en_las_secciones(doc):
    d = est.lista_crear(doc, "Pedidos", [{"nombre": "Estado", "tipo": "lista", "opciones": ["Nuevo", "Listo"]}], AHORA)
    sec = next(x for x in sv.secciones_de(d) if x["titulo"] == "Pedidos")
    assert sec["campos"][0]["tipo"] == "estado" and sec["campos"][0]["opciones"] == ["Nuevo", "Listo"]
    assert next(l for l in d["listas"] if l["nombre"] == "Pedidos")["campos"][0]["tipo"] == "lista"  # lo guardado no cambia
    out, r = sv.registro_agregar(d, sec["id"], {sec["campos"][0]["id"]: "listo"}, AHORA)
    assert r["valores"][sec["campos"][0]["id"]] == "Listo"
