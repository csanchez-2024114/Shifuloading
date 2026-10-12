"""Cuentas por codigo (helpers/calc.py): aritmetica segura y agregados sobre una tabla."""
import pytest

from app.agent.shared.helpers import calc

TABLE = {"header": ["Concepto", "Monto", "Mes"],
         "rows": [["Ventas", "$1,200.50", "enero"], ["Renta", "(300)", "enero"], ["Ventas", "800", "febrero"], ["Nota", "N/A", "febrero"]]}


def test_arithmetic():
    assert calc.evaluate("2340 * 15 / 100") == 351
    assert calc.evaluate("(1200.5 - 300 + 800) / 3") == pytest.approx(566.833333)
    assert calc.evaluate("sum([1, 2, 3.5]) + max(4, 9) - avg([2, 4])") == 12.5
    assert calc.evaluate("2^10") == 1024 and calc.evaluate("round(10 / 3, 2)") == 3.33


@pytest.mark.parametrize("bad", ["__import__('os').system('x')", "open('a')", "a + 1", "(1).real", "9**9**9", "1/0", "", "lambda: 1",
                                 "[x for x in [1]]", "'a' * 3"])
def test_anything_that_is_not_arithmetic_is_refused(bad):
    with pytest.raises(calc.CalcError):
        calc.evaluate(bad)


def test_numbers_as_people_write_them():
    assert [calc.to_number(c) for c in ("$1,200.50", "(300)", "15%", "N/A", "", None, 7, True)] == [1200.5, -300, 15, None, None, None, 7, None]


def test_aggregate_a_column_by_title_and_says_what_it_skipped():
    out = calc.aggregate(TABLE, "monto", "sum")
    assert out == {"operation": "sum", "column": "Monto", "value": 1700.5, "rows_used": 3, "rows_skipped": 1}
    assert calc.aggregate(TABLE, "B", "max")["value"] == 1200.5          # por letra de columna
    assert calc.aggregate(TABLE, "Monto", "avg")["value"] == pytest.approx(566.833333)
    assert calc.aggregate(TABLE, "Concepto", "count")["value"] == 4


def test_aggregate_only_the_rows_that_match():
    assert calc.aggregate(TABLE, "Monto", "sum", "Mes", "enero")["value"] == 900.5
    assert calc.aggregate(TABLE, "Monto", "sum", "Concepto", "ventas")["value"] == 2000.5


@pytest.mark.parametrize("args", [("Total", "sum"), ("Concepto", "sum"), ("Monto", "median"), ("Z", "sum")])
def test_aggregate_errors_are_explicit(args):
    with pytest.raises(calc.CalcError):
        calc.aggregate(TABLE, *args)
    with pytest.raises(calc.CalcError):
        calc.aggregate({"files": []}, "Monto", "sum")
