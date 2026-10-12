"""Pruebas del núcleo del CRM: generador, operaciones y vista. No necesitan base de datos ni servidor."""
from datetime import datetime, timedelta, timezone

import pytest

from app.crm import operaciones as op
from app.crm.generador import generar
from app.crm.secciones import titulo_seccion
from app.crm.vista import hace, vista_crm

AHORA = datetime(2026, 10, 12, 15, 0, tzinfo=timezone.utc)
BRIEF = {"nombre": "Clínica Sol", "rubro": "salud", "cartera": "k2", "equipo": "chico",
         "canales": ["whatsapp", "correo"], "objetivos": ["seguimientos", "ia"], "ubicacion": {"pais": "gt"}}


@pytest.fixture
def doc():
    return generar("u1", BRIEF, AHORA)


def test_generar_respeta_el_cuestionario(doc):
    assert doc["total_contactos"] == 120 and len(doc["contactos"]) == 16
    assert doc["vendedores"] == ["Tú", "Mariana Solís"]
    activas = {a["id"] for a in doc["automatizaciones"] if a["on"]}
    assert activas == {"recordatorios", "bienvenida", "contacto", "reparto"}
    assert {c["canal"] for c in doc["contactos"]} == {"WhatsApp", "Correo"}


def test_generar_cartera_chica_no_inventa_contactos_de_mas():
    d = generar("u1", {"cartera": "k1"}, AHORA)
    assert d["total_contactos"] == 40 and len(d["contactos"]) == 16
    assert d["vendedores"] == ["Tú"]


def test_las_operaciones_no_modifican_el_original(doc):
    antes = len(doc["contactos"])
    nuevo = op.contactos_crear(doc, [{"n": "Laura Gómez"}], "Chat", ahora=AHORA)
    assert len(doc["contactos"]) == antes and len(nuevo["contactos"]) == antes + 1


def test_crear_contacto_suma_total_y_deja_rastro(doc):
    nuevo = op.contactos_crear(doc, [{"n": "Laura Gómez", "det": "5555-1234"}], "Chat", ahora=AHORA)
    assert nuevo["total_contactos"] == 121
    assert nuevo["contactos"][0]["n"] == "Laura Gómez" and nuevo["contactos"][0]["etapa"] == "Nuevo"
    assert nuevo["eventos"][0]["t"] == "Agregaste a Laura Gómez"


def test_importar_varios_contactos_en_un_solo_evento(doc):
    nuevo = op.contactos_crear(doc, [{"n": "A"}, {"n": "B"}, {"n": "C"}], "Importado", "Importaste 3 contactos", AHORA)
    assert nuevo["total_contactos"] == 123 and nuevo["eventos"][0]["t"] == "Importaste 3 contactos"


def test_tope_de_contactos(doc):
    lleno = {**doc, "total_contactos": op.MAX_CONTACTOS}
    with pytest.raises(op.ErrorCrm) as e:
        op.contactos_crear(lleno, [{"n": "X"}], "Chat")
    assert e.value.estado == 422


def test_cambiar_etapa_actualiza_el_ultimo_contacto(doc):
    c = doc["contactos"][0]
    nuevo = op.contactos_actualizar(doc, c["id"], {"etapa": "Cliente"}, ahora=AHORA)
    cn = nuevo["contactos"][0]
    assert cn["etapa"] == "Cliente" and cn["ultimo_contacto"] == AHORA
    assert vista_crm(nuevo, AHORA)["contactos"][0]["dias"] == 0
    assert "pasó a “Cliente”" in nuevo["eventos"][0]["t"]


def test_etapa_o_responsable_invalidos(doc):
    cid = doc["contactos"][0]["id"]
    with pytest.raises(op.ErrorCrm):
        op.contactos_actualizar(doc, cid, {"etapa": "Inventada"})
    with pytest.raises(op.ErrorCrm):
        op.contactos_actualizar(doc, cid, {"dueno": "Desconocido"})


def test_contacto_inexistente_es_404(doc):
    for f in (lambda: op.contactos_actualizar(doc, "no", {"n": "X"}), lambda: op.contactos_eliminar(doc, "no")):
        with pytest.raises(op.ErrorCrm) as e:
            f()
        assert e.value.estado == 404


def test_eliminar_contacto_resta_total(doc):
    cid = doc["contactos"][3]["id"]
    nuevo = op.contactos_eliminar(doc, cid, AHORA)
    assert nuevo["total_contactos"] == 119 and all(c["id"] != cid for c in nuevo["contactos"])


def test_tareas_crear_mover_eliminar(doc):
    n = op.tareas_crear(doc, "Llamar a proveedores", AHORA)
    tid = n["tareas"]["porHacer"][-1]["id"]
    n = op.tareas_mover(n, tid, "hecho")
    assert any(t["id"] == tid for t in n["tareas"]["hecho"]) and all(t["id"] != tid for t in n["tareas"]["porHacer"])
    n = op.tareas_eliminar(n, tid, AHORA)
    assert all(t["id"] != tid for t in n["tareas"]["hecho"])
    with pytest.raises(op.ErrorCrm):
        op.tareas_mover(n, tid, "hecho")
    with pytest.raises(op.ErrorCrm):
        op.tareas_mover(doc, doc["tareas"]["porHacer"][0]["id"], "nunca")


def test_automatizacion_fijar_solo_deja_rastro_si_cambia(doc):
    a = next(x for x in doc["automatizaciones"] if not x["on"])
    mismo = op.automatizacion_fijar(doc, a["id"], False, AHORA)
    assert mismo["eventos"] == doc["eventos"]
    nuevo = op.automatizacion_fijar(doc, a["id"], True, AHORA)
    assert next(x for x in nuevo["automatizaciones"] if x["id"] == a["id"])["on"] is True
    assert nuevo["eventos"][0]["t"].startswith("Activaste")
    with pytest.raises(op.ErrorCrm):
        op.automatizacion_fijar(doc, "nada", True)


def test_renombrar_seccion_usa_el_nombre_del_rubro(doc):
    nuevo = op.seccion_renombrar(doc, "actividad", "Bitácora clínica", AHORA)
    assert nuevo["secciones"]["actividad"] == "Bitácora clínica"
    assert nuevo["eventos"][0]["t"] == "Renombraste “Historial” a “Bitácora clínica”"
    with pytest.raises(op.ErrorCrm):
        op.seccion_renombrar(doc, "inventada", "X")


def test_nombres_de_seccion_por_rubro():
    assert titulo_seccion("salud", "contactos") == "Pacientes"
    assert titulo_seccion("inmobiliaria", "rrhh") == "Asesores"
    assert titulo_seccion("rubro-raro", "cobros") == "Cobros"
    assert titulo_seccion("salud", "contactos", {"contactos": "Mis pacientes"}) == "Mis pacientes"


def test_tiempos_relativos():
    assert hace(AHORA, AHORA) == "ahora"
    assert hace(AHORA - timedelta(minutes=5), AHORA) == "hace 5 min"
    assert hace(AHORA - timedelta(hours=3), AHORA) == "hace 3 h"
    assert hace(AHORA - timedelta(days=1), AHORA) == "hace 1 día"
    assert hace(AHORA - timedelta(days=4), AHORA) == "hace 4 días"
    # Mongo devuelve fechas sin zona horaria: se tratan como UTC
    assert hace((AHORA - timedelta(minutes=2)).replace(tzinfo=None), AHORA) == "hace 2 min"


def test_la_vista_tiene_la_forma_del_contrato(doc):
    v = vista_crm(doc, AHORA)
    assert set(v) == {"brief", "totalContactos", "contactos", "vendedores", "tareas", "eventos", "automatizaciones", "secciones"}
    assert set(v["contactos"][0]) == {"id", "n", "det", "canal", "etapa", "dueno", "dias"}
    assert set(v["eventos"][0]) == {"id", "e", "t", "h"}
    assert "user_id" not in v and "version" not in v
