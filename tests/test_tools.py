import os
from datetime import datetime


def test_calculadora_aritmetica():
    from assistant.tools import calculadora

    assert "14" in calculadora.invoke({"expresion": "2 + 3 * 4"})
    assert "3" in calculadora.invoke({"expresion": "(10 - 4) / 2"})


def test_calculadora_potencia():
    from assistant.tools import calculadora

    assert "1024" in calculadora.invoke({"expresion": "2 ** 10"})


def test_calculadora_sqrt():
    from assistant.tools import calculadora

    assert "4" in calculadora.invoke({"expresion": "math.sqrt(16)"})


def test_calculadora_rechaza_codigo_sin_ejecutarlo(monkeypatch):
    from assistant.tools import calculadora

    monkeypatch.delenv("PWNED", raising=False)
    for expr in (
        "__import__('os').getcwd()",
        "__import__('os').environ.__setitem__('PWNED', '1')",
    ):
        out = calculadora.invoke({"expresion": expr})
        assert isinstance(out, str)
        assert "error" in out.lower()
    assert "PWNED" not in os.environ


def test_fecha_hora_incluye_anio_actual():
    from assistant.tools import fecha_hora

    assert str(datetime.now().year) in fecha_hora.invoke({})
