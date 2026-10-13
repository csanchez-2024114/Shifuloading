"""Pruebas del chat del CRM (sin base de datos): cada frase hace lo que dice y borrar siempre pide confirmación."""
from datetime import datetime, timezone

import pytest

from app.crm import operaciones as op
from app.crm.chat import responder, sanear_pendiente
from app.crm.generador import generar

AHORA = datetime(2026, 10, 12, 15, 0, tzinfo=timezone.utc)
BRIEF = {"nombre": "Clínica Sol", "rubro": "salud", "cartera": "k2", "equipo": "chico", "canales": ["whatsapp"], "objetivos": ["seguimientos"]}


@pytest.fixture
def doc():
    """Un CRM con contactos y tareas ya creados por la persona (el CRM nuevo nace vacío)."""
    d = generar("u1", BRIEF, AHORA)
    d = op.contactos_crear(d, [{"n": n} for n in ["Ana Morales", "Luis Pérez", "Sofía Ríos"]], "WhatsApp", ahora=AHORA)
    return op.tareas_crear(d, "Importar contactos", AHORA)


def dice(doc, texto, pendiente=None):
    return responder(doc, texto, pendiente, AHORA)


def test_agregar_contacto(doc):
    r = dice(doc, "Agrega a laura gómez")
    assert r["doc"]["contactos"][0]["n"] == "Laura Gómez" and r["doc"]["total_contactos"] == doc["total_contactos"] + 1
    assert "Pacientes" in r["respuesta"] and r["vista"] == "contactos"


def test_agregar_contacto_con_palabra_de_tipo(doc):
    assert dice(doc, "crea cliente Pedro Castillo")["doc"]["contactos"][0]["n"] == "Pedro Castillo"


def test_no_duplica_un_contacto_que_ya_existe(doc):
    r = dice(doc, "agrega a Ana Morales")
    assert r["doc"] is doc and "ya está" in r["respuesta"]


def test_agregar_sin_nombre_pregunta(doc):
    r = dice(doc, "agrega a")
    assert r["doc"] is doc and "¿Cómo se llama?" in r["respuesta"]


def test_agregar_tarea(doc):
    r = dice(doc, "Agrega la tarea llamar a proveedores")
    assert r["doc"]["tareas"]["porHacer"][-1]["t"] == "Llamar a proveedores" and r["vista"] == "desarrollo"


def test_mover_contacto_de_etapa(doc):
    r = dice(doc, "Mueve a Ana Morales a Cliente")
    assert next(c for c in r["doc"]["contactos"] if c["n"] == "Ana Morales")["etapa"] == "Cliente"


def test_renombrar_seccion_tiene_prioridad_sobre_contactos(doc):
    r = dice(doc, "Renombra Historial a Bitácora clínica")
    assert r["doc"]["secciones"]["actividad"] == "Bitácora Clínica"


def test_renombrar_contacto(doc):
    r = dice(doc, "cambia Luis Pérez por Luis Pérez Soto")
    assert r["doc"]["contactos"][1]["n"] == "Luis Pérez Soto"


def test_activar_y_apagar_automatizaciones(doc):
    r = dice(doc, "activa los avisos de cobros vencidos")
    assert next(a for a in r["doc"]["automatizaciones"] if a["id"] == "vencidos")["on"] is True
    r2 = dice(r["doc"], "apaga los recordatorios")
    assert next(a for a in r2["doc"]["automatizaciones"] if a["id"] == "recordatorios")["on"] is False
    assert dice(doc, "activa la teletransportación")["doc"] is doc


def test_eliminar_pide_confirmacion_y_no_borra_hasta_el_si(doc):
    r = dice(doc, "Elimina a Luis Pérez")
    assert r["doc"] is doc and "¿Seguro" in r["respuesta"] and r["pendiente"]["tipo"] == "contacto"
    ok = dice(doc, "sí", r["pendiente"])
    assert all(c["n"] != "Luis Pérez" for c in ok["doc"]["contactos"]) and ok["doc"]["total_contactos"] == doc["total_contactos"] - 1


def test_cualquier_otra_cosa_cancela_el_borrado(doc):
    r = dice(doc, "Elimina a Luis Pérez")
    no = dice(doc, "mejor no", r["pendiente"])
    assert no["doc"] is doc and "no borré nada" in no["respuesta"] and "pendiente" not in no


def test_eliminar_tarea_con_confirmacion(doc):
    r = dice(doc, "elimina tarea importar contactos")
    assert r["pendiente"]["tipo"] == "tarea"
    ok = dice(doc, "dale", r["pendiente"])
    assert all(t["t"] != "Importar contactos" for t in ok["doc"]["tareas"]["porHacer"])


def test_confirmar_algo_que_ya_no_existe_no_falla(doc):
    r = dice(doc, "sí", {"tipo": "contacto", "id": "ya-no-esta"})
    assert r["doc"] is doc and "ya no existe" in r["respuesta"]


def test_importar_manda_a_la_seccion(doc):
    assert dice(doc, "tengo mis clientes en un excel")["vista"] == "importar"


def test_no_entiende_y_saluda(doc):
    assert "Aún no entendí" in dice(doc, "blablabla")["respuesta"]
    assert "Puedo agregar" in dice(doc, "hola")["respuesta"]


def test_el_pendiente_del_cliente_se_sanea():
    assert sanear_pendiente({"tipo": "contacto", "id": "abc", "extra": "x"}) == {"tipo": "contacto", "id": "abc"}
    for malo in (None, "x", {"tipo": "otro", "id": "a"}, {"tipo": "tarea", "id": 5}, {"tipo": "tarea", "id": "a" * 100}):
        assert sanear_pendiente(malo) is None
