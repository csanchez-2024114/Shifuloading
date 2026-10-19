"""Punto 47: la hora del negocio sale del país de su CRM (zonas IANA), con respaldo UTC-6 (CRM_UTC_OFFSET)."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.crm import agente, automatizaciones as auto
from app.crm import operaciones as op
from app.crm.generador import generar
from app.crm.regional import ZONAS, codigo_pais, zona_del_pais

RESPALDO = timezone(timedelta(hours=-6))


def _doc(pais=None, **extra):
    brief = {"nombre": "Negocio", "rubro": "salud", **({"ubicacion": {"pais": pais}} if pais is not None else {}), **extra}
    return generar("u1", brief, datetime(2026, 1, 15, 12, tzinfo=timezone.utc))


@pytest.mark.parametrize("pais,horas_invierno,horas_verano", [
    ("gt", -6, -6), ("mx", -6, -6), ("co", -5, -5), ("es", 1, 2), ("us", -6, -5),
])
def test_cada_pais_con_su_zona(pais, horas_invierno, horas_verano):
    z = op.zona_de(_doc(pais))
    assert z.utcoffset(datetime(2026, 1, 15, 12)) == timedelta(hours=horas_invierno)
    assert z.utcoffset(datetime(2026, 7, 15, 12)) == timedelta(hours=horas_verano)


@pytest.mark.parametrize("pais", ["otro", "Narnia", "", None])
def test_otro_o_desconocido_usa_el_respaldo(pais):
    assert op.zona_de(_doc(pais)) is op.ZONA
    assert op.ZONA.utcoffset(None) == timedelta(hours=-6)


def test_nombre_del_pais_tambien_vale_y_doc_pais_manda():
    assert codigo_pais("México") == "mx" and codigo_pais("espana") == "es" and codigo_pais("xx") is None
    d = _doc("gt")
    assert op.zona_de({**d, "pais": "es"}).key == "Europe/Madrid"
    assert op.zona_de(None) is op.ZONA


def test_todos_los_paises_del_cuestionario_tienen_zona_o_respaldo():
    from app.crm.regional import PAISES

    assert set(ZONAS) == set(PAISES)
    assert zona_del_pais("otro", RESPALDO) is RESPALDO


def test_sin_base_de_zonas_cae_al_respaldo(monkeypatch):
    import app.crm.regional as regional
    from zoneinfo import ZoneInfoNotFoundError

    def sin_tzdata(_nombre):
        raise ZoneInfoNotFoundError("sin tzdata")

    monkeypatch.setattr(regional, "ZoneInfo", sin_tzdata)
    assert zona_del_pais("es", RESPALDO) is RESPALDO


def test_hoy_cambia_de_dia_segun_el_pais():
    # 23:30 UTC del 14-ene: en Madrid ya es 15, en Guatemala todavía 14 (17:30).
    ahora = datetime(2026, 1, 14, 23, 30, tzinfo=timezone.utc)
    assert op.hora_local(ahora, _doc("es")).date().isoformat() == "2026-01-15"
    assert op.hora_local(ahora, _doc("gt")).date().isoformat() == "2026-01-14"
    assert op.hora_local(ahora).date().isoformat() == "2026-01-14"  # sin doc: respaldo


def test_cita_en_el_pasado_se_mide_en_la_hora_del_pais():
    ahora = datetime(2026, 1, 14, 23, 30, tzinfo=timezone.utc)
    # En España ya es el 15: una cita «hoy 14» ya pasó. En Guatemala sigue siendo 14 a las 17:30: «hoy 14 a las 18:00» vale.
    with pytest.raises(op.ErrorCrm, match="ya pasó"):
        op.tareas_crear(_doc("es"), "Llamar", ahora, vence="2026-01-14")
    out = op.tareas_crear(_doc("gt"), "Llamar", ahora, vence="2026-01-14", hora="18:00")
    assert out["tareas"]["porHacer"][-1]["vence"] == "2026-01-14"
    d = _doc("es")
    d = op.tareas_crear(d, "Llamar", ahora, vence="2026-01-20")
    tid = d["tareas"]["porHacer"][-1]["id"]
    with pytest.raises(op.ErrorCrm, match="ya pasó"):
        op.tareas_actualizar(d, tid, {"vence": "2026-01-14"}, ahora)


def test_el_modelo_recibe_el_hoy_del_pais():
    ahora = datetime(2026, 1, 14, 23, 30, tzinfo=timezone.utc)
    assert "fecha 2026-01-15" in json.loads(agente.contexto_crm(_doc("es"), ahora))["hoy"]
    assert "00:30" in json.loads(agente.contexto_crm(_doc("es"), ahora))["hoy"]
    assert "fecha 2026-01-14" in json.loads(agente.contexto_crm(_doc("gt"), ahora))["hoy"]


def test_recordatorio_vence_hoy_en_la_hora_del_pais():
    ahora = datetime(2026, 1, 14, 23, 30, tzinfo=timezone.utc)
    hace = ahora - timedelta(days=10)
    d = op.contactos_crear(_doc("es"), [{"n": "Ana"}], "WhatsApp", ahora=hace)
    for a in d["automatizaciones"]:
        a["on"] = a["id"] == "recordatorios"
    nombres = auto._recordatorios(d, ahora)
    assert nombres == ["Ana"]
    assert d["tareas"]["porHacer"][-1]["vence"] == "2026-01-15"
