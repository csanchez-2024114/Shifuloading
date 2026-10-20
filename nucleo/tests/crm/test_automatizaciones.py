"""Las automatizaciones que funcionan de verdad: recordatorios, reparto y resumen semanal. Sin red y sin IA."""
from datetime import datetime, timedelta, timezone

import pytest

from assistant.packs.crm import automatizaciones as au
from assistant.packs.crm import operaciones as op
from assistant.packs.crm.generador import generar

AHORA = datetime(2026, 10, 13, 15, 0, tzinfo=timezone.utc)  # martes (09:00 en Guatemala)
BRIEF = {"nombre": "Pan Dorado", "rubro": "comercio", "equipo": "chico", "objetivos": ["seguimientos", "reportes"], "problemas": ["olvido"]}


def prender(doc, *ids):
    d = op._copia(doc)
    for a in d["automatizaciones"]:
        a["on"] = a["id"] in ids
    return d


@pytest.fixture
def doc():
    return generar("u1", BRIEF, AHORA)


def con_contactos(doc, nombres, hace_dias=0, etapa=None):
    d = op.contactos_crear(doc, [{"n": n} for n in nombres], "Chat", ahora=AHORA - timedelta(days=hace_dias))
    if etapa:
        for c in d["contactos"]:
            c["etapa"] = etapa
    return d


# ───────── Catálogo y estado ─────────

def test_un_crm_nuevo_solo_enciende_las_que_funcionan_y_le_sirven():
    d = generar("u1", BRIEF, AHORA)
    assert {a["id"] for a in d["automatizaciones"] if a["on"]} == {"recordatorios", "reparto", "resumen"}
    solo = generar("u1", {"rubro": "comercio", "equipo": "solo", "canales": ["whatsapp"], "objetivos": ["ia"]}, AHORA)
    assert not any(a["on"] for a in solo["automatizaciones"])  # WhatsApp e IA no encienden nada que no existe
    assert [a["id"] for a in solo["automatizaciones"]] == list(au.CATALOGO)


def test_las_que_todavia_no_existen_no_se_pueden_encender(doc):
    for pronto in ("bienvenida", "contacto", "vencidos"):
        with pytest.raises(op.ErrorCrm) as e:
            op.automatizacion_fijar(doc, pronto, True, AHORA)
        assert e.value.estado == 422 and "Próximamente" in e.value.mensaje
    assert op.automatizacion_fijar(doc, "bienvenida", False, AHORA)["eventos"] == doc["eventos"]  # apagar una apagada no hace nada
    assert op.automatizacion_fijar(doc, "recordatorios", False, AHORA)["automatizaciones"][0]["on"] is False


def test_un_crm_guardado_antes_se_pone_al_dia():
    viejo = {"automatizaciones": [{"id": "bienvenida", "pilar": "x", "t": "viejo", "d": "viejo", "on": True},
                                  {"id": "recordatorios", "pilar": "x", "t": "Recordatorios de seguimiento", "d": "Te avisa...", "on": True}]}
    d = au.normalizar(viejo)
    por_id = {a["id"]: a for a in d["automatizaciones"]}
    assert list(por_id) == list(au.CATALOGO) and por_id["bienvenida"]["on"] is False and por_id["recordatorios"]["on"] is True
    assert "3 días sin cambiar de etapa" in por_id["recordatorios"]["d"] and por_id["resumen"]["on"] is False


def test_el_detalle_dice_cuales_funcionan():
    assert au.detalle("recordatorios") == {"disponible": True, "nota": None}
    assert au.detalle("bienvenida")["disponible"] is False and "WhatsApp" in au.detalle("bienvenida")["nota"]


# ───────── Reparto ─────────

def test_el_reparto_asigna_por_turnos_y_sigue_donde_se_quedo(doc):
    d = op.vendedor_agregar(op.vendedor_agregar(doc, "Marta", AHORA), "Carlos", AHORA)
    d = op.contactos_crear(d, [{"n": n} for n in ["A1", "A2", "A3", "A4"]], "Chat", ahora=AHORA)
    duenos = [c["dueno"] for c in d["contactos"]]  # el lote queda en el orden en que se creó
    assert duenos == ["Tú", "Marta", "Carlos", "Tú"] and d["reparto_n"] == 4
    d = op.contactos_crear(d, [{"n": "B1"}], "Chat", ahora=AHORA)
    assert d["contactos"][0]["dueno"] == "Marta"  # el turno 5 sigue donde se quedó


def test_sin_equipo_o_apagado_todo_queda_con_la_persona(doc):
    solo = op.contactos_crear(doc, [{"n": "A1"}, {"n": "A2"}], "Chat", ahora=AHORA)
    assert {c["dueno"] for c in solo["contactos"]} == {"Tú"} and "reparto_n" not in solo
    con_equipo = op.vendedor_agregar(doc, "Marta", AHORA)
    apagado = op.contactos_crear(prender(con_equipo, "recordatorios"), [{"n": "A1"}, {"n": "A2"}], "Chat", ahora=AHORA)
    assert {c["dueno"] for c in apagado["contactos"]} == {"Tú"}


# ───────── Recordatorios ─────────

def test_un_contacto_sin_avance_recibe_una_tarea_automatica(doc):
    d = con_contactos(prender(doc, "recordatorios"), ["Oscar Siacajau"], hace_dias=4)
    nuevo, cambio = au.ejecutar_pendientes(d, AHORA)
    assert cambio is True
    t = nuevo["tareas"]["porHacer"][0]
    assert t["t"] == "Dar seguimiento a Oscar Siacajau" and t["auto"] == "recordatorios" and t["vence"] == "2026-10-13"
    assert t["contacto_id"] == nuevo["contactos"][0]["id"]
    assert "Recordatorio automático" in nuevo["eventos"][0]["t"]
    assert d["tareas"]["porHacer"] == []  # no toca el original


def test_repetirlo_no_duplica_la_tarea(doc):
    d = con_contactos(prender(doc, "recordatorios"), ["Oscar"], hace_dias=5)
    uno, _ = au.ejecutar_pendientes(d, AHORA)
    dos, cambio = au.ejecutar_pendientes(uno, AHORA + timedelta(days=2))
    assert cambio is False and dos is uno and len(dos["tareas"]["porHacer"]) == 1
    # aunque la persona borre la tarea, no se vuelve a crear por el mismo tramo sin avance
    uno["tareas"]["porHacer"] = []
    tres, cambio = au.ejecutar_pendientes(uno, AHORA + timedelta(days=9))
    assert cambio is False and tres["tareas"]["porHacer"] == []


def test_si_el_contacto_avanza_y_se_vuelve_a_enfriar_se_le_recuerda_de_nuevo(doc):
    d = con_contactos(prender(doc, "recordatorios"), ["Oscar"], hace_dias=5)
    uno, _ = au.ejecutar_pendientes(d, AHORA)
    uno = op.contactos_actualizar(uno, uno["contactos"][0]["id"], {"etapa": "En contacto"}, ahora=AHORA)  # avanzó: ultimo_contacto = ahora
    sin_cambio, cambio = au.ejecutar_pendientes(uno, AHORA + timedelta(days=1))
    assert cambio is False
    otra, cambio = au.ejecutar_pendientes(uno, AHORA + timedelta(days=4))
    assert cambio is True and len(otra["tareas"]["porHacer"]) == 2


def test_no_recuerda_a_los_recientes_ni_a_los_que_ya_llegaron_a_la_ultima_etapa(doc):
    reciente = con_contactos(prender(doc, "recordatorios"), ["Nuevo"], hace_dias=2)
    assert au.ejecutar_pendientes(reciente, AHORA)[1] is False
    cliente = con_contactos(prender(doc, "recordatorios"), ["Ya es cliente"], hace_dias=30, etapa=doc["etapas"][-1])
    assert au.ejecutar_pendientes(cliente, AHORA)[1] is False


def test_apagado_no_hace_nada_y_hay_tope_por_vez(doc):
    viejo = con_contactos(prender(doc, "resumen"), ["A"], hace_dias=10)
    assert au.ejecutar_pendientes(viejo, AHORA)[0]["tareas"]["porHacer"] == []
    muchos = con_contactos(prender(doc, "recordatorios"), [f"Persona {i}" for i in range(25)], hace_dias=10)
    nuevo, _ = au.ejecutar_pendientes(muchos, AHORA)
    assert len(nuevo["tareas"]["porHacer"]) == au.MAX_RECORDATORIOS_POR_VEZ
    otra, _ = au.ejecutar_pendientes(nuevo, AHORA)  # la siguiente apertura sigue con los que faltaron
    assert len(otra["tareas"]["porHacer"]) == 20


def test_sin_ninguna_encendida_ni_se_copia_el_documento(doc):
    d = prender(doc)
    nuevo, cambio = au.ejecutar_pendientes(d, AHORA)
    assert nuevo is d and cambio is False


# ───────── Resumen semanal ─────────

def test_el_resumen_se_marca_la_primera_vez_y_llega_la_semana_siguiente(doc):
    d = con_contactos(prender(doc, "resumen"), ["Ana", "Luis"])
    d = op.tareas_crear(d, "Llamar a proveedores", AHORA, vence="2026-10-13")
    primera, cambio = au.ejecutar_pendientes(d, AHORA)
    assert cambio is True and primera["ultimo_resumen"] == "2026-W42" and not any("Resumen" in e["t"] for e in primera["eventos"])
    misma, cambio = au.ejecutar_pendientes(primera, AHORA + timedelta(days=3))
    assert cambio is False and misma is primera
    semana_siguiente = AHORA + timedelta(days=7)
    con_resumen, cambio = au.ejecutar_pendientes(primera, semana_siguiente)
    assert cambio is True and con_resumen["ultimo_resumen"] == "2026-W43"
    texto = con_resumen["eventos"][0]["t"]
    assert texto.startswith("Resumen de la semana: 2 contactos") and "2 en Nuevo" in texto and "1 por hacer" in texto and "1 vencida" in texto


def test_un_crm_vacio_no_genera_un_resumen_vacio(doc):
    d = prender(doc, "resumen")
    d["ultimo_resumen"] = "2026-W41"
    nuevo, cambio = au.ejecutar_pendientes(d, AHORA)
    assert cambio is True and nuevo["ultimo_resumen"] == "2026-W42" and not any("Resumen" in e["t"] for e in nuevo["eventos"])


# ───────── Vista ─────────

def test_la_vista_dice_cuales_no_existen_y_cuales_tareas_son_automaticas(doc):
    from assistant.packs.crm.vista import vista_crm

    d = con_contactos(prender(doc, "recordatorios"), ["Oscar"], hace_dias=4)
    d, _ = au.ejecutar_pendientes(d, AHORA)
    v = vista_crm(d, AHORA)
    pronto = [a for a in v["automatizaciones"] if a["disponible"] is False]
    assert {a["id"] for a in pronto} == {"bienvenida", "contacto", "vencidos"} and all(a["nota"].startswith("Próximamente") for a in pronto)
    assert v["tareas"]["porHacer"][0]["auto"] is True and "recordado" not in str(v["contactos"])
