"""Lo calculable de meter datos por chat (valores.py): fechas, montos, horas, opciones y a qué registro se refiere.

Los mismos 78 casos de `laboratorio/pruebas/valores.test.mjs`, con hoy fijo (viernes 16 de octubre de 2026). Sin IA.
"""
from datetime import date

import pytest

from app.crm.valores import buscar_registro, fecha_larga, opcion_de, parse_fecha, parse_hora, parse_numero, parse_periodo

HOY = date(2026, 10, 16)  # viernes

FECHAS = [
    ("2026-10-30", "2026-10-30"), ("30/10/2026", "2026-10-30"), ("30-10-26", "2026-10-30"), ("30/10", "2026-10-30"),
    ("el 30 de octubre", "2026-10-30"), ("30 de octubre de 2027", "2027-10-30"), ("30 oct", "2026-10-30"), ("oct 30", "2026-10-30"),
    ("hoy", "2026-10-16"), ("mañana", "2026-10-17"), ("pasado mañana", "2026-10-18"), ("ayer", "2026-10-15"), ("en 5 días", "2026-10-21"),
    ("dentro de dos semanas", "2026-10-30"), ("en un mes", "2026-11-16"), ("hace 3 días", "2026-10-13"), ("el viernes", "2026-10-23"),
    ("el próximo jueves", "2026-10-22"), ("el lunes", "2026-10-19"), ("31/02/2026", None), ("cuando pueda", None), ("", None),
    # años dichos en palabras (prueba de cliente: «vence el 15 de octubre del próximo año» no se entendía)
    ("15 de octubre del próximo año", "2027-10-15"), ("15 de octubre del año que viene", "2027-10-15"), ("1 de marzo de este año", "2026-03-01"),
    ("3 de enero del año pasado", "2025-01-03"), ("en un año", "2027-10-16"),
    # relativas como las reescribe el modelo (prueba de cliente)
    ("un mes desde hoy", "2026-11-16"), ("hoy + 1 mes", "2026-11-16"), ("hoy+30 días", "2026-11-15"), ("30 días a partir de hoy", "2026-11-15"),
    ("dentro de 2 semanas desde hoy", "2026-10-30"),
]


@pytest.mark.parametrize("texto,esperado", FECHAS)
def test_fecha(texto, esperado):
    assert parse_fecha(texto, HOY) == esperado


NUMEROS = [("Q1,200.50", 1200.5), ("1.200,50", 1200.5), ("$ 300", 300), ("500 quetzales", 500), ("12,5", 12.5), ("1,200", 1200),
           ("1,200,000", 1200000), ("1.200.000", 1200000), ("3.5", 3.5), (45, 45), ("nada", None)]


@pytest.mark.parametrize("texto,esperado", NUMEROS)
def test_numero(texto, esperado):
    assert parse_numero(texto) == esperado


HORAS = [("9am", "09:00"), ("9:30", "09:30"), ("15:00", "15:00"), ("3 pm", "15:00"), ("3 de la tarde", "15:00"), ("8 de la noche", "20:00"),
         ("12 am", "00:00"), ("mediodía", "12:00"), ("25:00", None), ("tarde", None)]


@pytest.mark.parametrize("texto,esperado", HORAS)
def test_hora(texto, esperado):
    assert parse_hora(texto) == esperado


def test_opcion_sin_mayusculas_ni_acentos():
    est = {"opciones": ["Activa", "Pausada", "Cancelada"]}
    assert opcion_de(est, "pausada") == "Pausada"
    assert opcion_de(est, "Congelada") is None


SEC = {"id": "miembros"}
CAMPOS = [{"id": "nombre", "tipo": "texto"}, {"id": "plan", "tipo": "texto"}, {"id": "estado", "tipo": "estado"}]
R = [{"id": "a", "valores": {"nombre": "Ana López", "plan": "Mensual"}}, {"id": "b", "valores": {"nombre": "Ana Martínez", "plan": "Anual"}},
     {"id": "c", "valores": {"nombre": "Carlos Pérez", "plan": "Mensual"}}]


def test_nombre_exacto_sin_acentos():
    assert buscar_registro(R, SEC, CAMPOS, "ana lopez")["registro"]["id"] == "a"


def test_palabra_suelta_que_coincide_con_2_da_candidatos():
    assert [r["id"] for r in buscar_registro(R, SEC, CAMPOS, "Ana")["candidatos"]] == ["a", "b"]


def test_apellido_unico():
    assert buscar_registro(R, SEC, CAMPOS, "Pérez")["registro"]["id"] == "c"


def test_por_id():
    assert buscar_registro(R, SEC, CAMPOS, "b")["registro"]["id"] == "b"


def test_no_existe():
    assert buscar_registro(R, SEC, CAMPOS, "Rosa Gómez").get("ninguno")


PERIODOS = [
    ("hoy", "2026-10-16", "2026-10-16"), ("esta semana", "2026-10-12", "2026-10-18"), ("la semana pasada", "2026-10-05", "2026-10-11"),
    ("la próxima semana", "2026-10-19", "2026-10-25"), ("este mes", "2026-10-01", "2026-10-31"), ("el mes pasado", "2026-09-01", "2026-09-30"),
    ("el próximo mes", "2026-11-01", "2026-11-30"), ("este año", "2026-01-01", "2026-12-31"), ("los últimos 30 días", "2026-09-16", "2026-10-16"),
    ("los próximos 7 días", "2026-10-16", "2026-10-23"), ("vencidos", None, "2026-10-15"), ("octubre", "2026-10-01", "2026-10-31"),
    ("en febrero", "2026-02-01", "2026-02-28"), ("diciembre de 2025", "2025-12-01", "2025-12-31"), ("del 1 al 15 de octubre", "2026-10-01", "2026-10-15"),
    ("del 3 de octubre al 2 de noviembre", "2026-10-03", "2026-11-02"), ("el 30 de octubre", "2026-10-30", "2026-10-30"),
]


@pytest.mark.parametrize("texto,desde,hasta", PERIODOS)
def test_periodo(texto, desde, hasta):
    assert parse_periodo(texto, HOY) == {"desde": desde, "hasta": hasta}


def test_periodo_que_no_se_entiende():
    assert parse_periodo("cuando llueva", HOY) is None
    assert parse_periodo("del 15 al 1 de octubre", HOY) is None


def test_fecha_larga():
    assert fecha_larga("2026-10-30") == "30 de octubre de 2026"
    assert fecha_larga("2026-01-05") == "5 de enero de 2026"
