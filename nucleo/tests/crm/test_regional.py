"""Formatos por país (regional.py): los mismos textos que da `Intl` en el laboratorio (Node 22, ICU 78), copiados de su salida."""
from datetime import date

import pytest

from assistant.packs.crm.regional import region_de

D = " "  # el espacio duro que pone ICU junto al símbolo

DINERO = [
    ("gt", 1250, f"Q{D}1,250"), ("gt", 11600.5, f"Q{D}11,600.50"), ("gt", -1250, f"-Q{D}1,250"), ("gt", 1.005, f"Q{D}1"), ("gt", 0.005, f"Q{D}0.01"),
    ("gt", 999999.995, f"Q{D}1,000,000"), ("mx", 11600.5, "$11,600.50"), ("co", 11600.5, f"${D}11.601"), ("co", 2.675, f"${D}3"),
    ("es", 1250, f"1250{D}€"), ("es", 11600.5, f"11.600,50{D}€"), ("us", -11600.567, "-$11,600.57"), ("otro", 1250.5, f"USD{D}1,250.50"),
    ("zz", 1250, f"Q{D}1,250"), (None, 1250, f"Q{D}1,250"), ("gt", float("nan"), "QNaN"), ("gt", -0.001, f"-Q{D}0"),
]


@pytest.mark.parametrize("pais,n,esperado", DINERO)
def test_dinero(pais, n, esperado):
    assert region_de(pais).dinero(n) == esperado


def test_numero_y_cortos():
    gt, es, co = region_de("gt"), region_de("es"), region_de("co")
    assert gt.numero(1234567.891) == "1,234,567.89"
    assert gt.numero(12.345) == "12.35"  # mitad hacia afuera sobre el decimal más corto, como Intl
    assert es.numero(1250.5) == "1250,5" and es.numero(12345) == "12.345"
    assert co.numero(1250) == "1.250"
    assert gt.dinero_corto(1250) == f"Q{D}1.3 mil" and gt.dinero_corto(-1250) == f"−Q{D}1.3 mil"
    assert es.dinero_corto(999999.995) == f"1000 mil{D}€"
    assert gt.numero_corto(1234567.891) == "1.2 M" and gt.numero_corto(-1250) == "-1.3 mil"


def test_pct():
    assert region_de("gt").pct(0.125) == "12.5%"
    assert region_de("gt").pct(0.035) == "3.5%"
    assert region_de("es").pct(-0.0333) == f"-3,3{D}%"


def test_fecha():
    hoy = date(2026, 10, 16)
    assert region_de("gt").fecha("2026-10-30", hoy) == "30 oct"
    assert region_de("gt").fecha("2025-09-05", hoy) == "5 sept 2025"
    assert region_de("mx").fecha("2026-09-05", hoy) == "5 sep"
    assert region_de("co").fecha("2025-05-01", hoy) == "1 de may de 2025"


def test_hora():
    assert region_de("gt").hora("15:05") == "3:05 p. m."
    assert region_de("gt").hora("0:00") == "12:00 a. m."
    assert region_de("mx").hora("9:00") == "9:00 a.m."
    assert region_de("es").hora("15:05") == "15:05"
    assert region_de("gt").hora("9:75") == "10:15 a. m."
    assert region_de("gt").hora("25:00") == "25:00" and region_de("gt").hora("x") == "x" and region_de("gt").hora(None) == ""
