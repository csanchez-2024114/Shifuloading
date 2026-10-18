import os
from datetime import datetime


def test_calculadora_aritmetica():
    from assistant.tools import calculadora

    assert "14" in calculadora.invoke({"expression": "2 + 3 * 4"})
    assert "3" in calculadora.invoke({"expression": "(10 - 4) / 2"})


def test_calculadora_potencia():
    from assistant.tools import calculadora

    assert "1024" in calculadora.invoke({"expression": "2 ** 10"})


def test_calculadora_sqrt():
    from assistant.tools import calculadora

    assert "4" in calculadora.invoke({"expression": "math.sqrt(16)"})


def test_calculadora_rechaza_codigo_sin_ejecutarlo(monkeypatch):
    from assistant.tools import calculadora

    monkeypatch.delenv("PWNED", raising=False)
    for expr in (
        "__import__('os').getcwd()",
        "__import__('os').environ.__setitem__('PWNED', '1')",
    ):
        out = calculadora.invoke({"expression": expr})
        assert isinstance(out, str)
        assert "error" in out.lower()
    assert "PWNED" not in os.environ


def test_fecha_hora_incluye_anio_actual():
    from assistant.tools import fecha_hora

    assert str(datetime.now().year) in fecha_hora.invoke({})


def test_calculadora_topes_de_tamano_solo_para_entradas_patologicas():
    """S4: antes, ((10**10000)**10000)**10000 y factorial(10**6) colgaban el hilo del servidor. Ahora fallan rápido;
    lo normal (incluido lo grande pero mostrable) sigue igual."""
    import time

    from assistant.core.tools import calculadora

    inicio = time.monotonic()
    assert calculadora.invoke({"expression": "((10**10000)**10000)**10000"}) == "Error: result too large"
    assert calculadora.invoke({"expression": "factorial(10**6)"}) == "Error: factorial argument too large"
    assert calculadora.invoke({"expression": "(2**9000)*(2**9000)"}) == "Error: result too large"
    assert calculadora.invoke({"expression": "factorial(2000)"}) == "Error: factorial argument too large"
    assert time.monotonic() - inicio < 2
    assert calculadora.invoke({"expression": "2**10000"}) == str(2**10000)  # 3011 dígitos: se muestra
    assert calculadora.invoke({"expression": "factorial(1000)"}).startswith("40238726007709377354")
    assert calculadora.invoke({"expression": "2**-3"}) == "0.125"
    assert calculadora.invoke({"expression": "1.5**1000"}).startswith("1.2338")
