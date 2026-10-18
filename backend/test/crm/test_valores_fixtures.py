"""Fixtures dorados del laboratorio (contrato §6): cada caso de `fixtures/lab/<funcion>.json` debe dar en Python lo MISMO que en JS.

Formato: [{caso, entrada: {<parámetros con el nombre de JS>}, salida}], con `hoy` como 'AAAA-MM-DD' (los graba
`laboratorio/servidor/grabar-fixtures.mjs` con TZ=UTC).
"""
import json
from datetime import date
from pathlib import Path

import pytest

from app.crm.valores import buscar_registro, fecha_larga, opcion_de, parse_fecha, parse_hora, parse_numero, parse_periodo

CARPETA = Path(__file__).parent / "fixtures" / "lab"


def _hoy(e):
    return date.fromisoformat(e["hoy"])


FUNCIONES = {
    "parseFecha": lambda e: parse_fecha(e.get("texto"), _hoy(e)),
    "parseNumero": lambda e: parse_numero(e.get("texto")),
    "parseHora": lambda e: parse_hora(e.get("texto")),
    "opcionDe": lambda e: opcion_de(e["campo"], e.get("valor")),
    "parsePeriodo": lambda e: parse_periodo(e.get("texto"), _hoy(e)),
    "fechaLarga": lambda e: fecha_larga(e.get("isoTexto")),
    "buscarRegistro": lambda e: buscar_registro(e["registros"], e["seccion"], e["campos"], e.get("consulta")),
}


def _casos():
    for nombre in FUNCIONES:
        archivo = CARPETA / f"{nombre}.json"
        if not archivo.exists():
            yield pytest.param(nombre, None, id=f"{nombre}-falta", marks=pytest.mark.skip(reason=f"no está {archivo.name}"))
            continue
        for i, c in enumerate(json.loads(archivo.read_text(encoding="utf-8"))):
            yield pytest.param(nombre, c, id=f"{nombre}-{i}")


@pytest.mark.parametrize("nombre,caso", list(_casos()))
def test_fixture_dorado(nombre, caso):
    assert FUNCIONES[nombre](caso["entrada"]) == caso["salida"], caso.get("caso")
