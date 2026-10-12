"""Cuentas hechas por codigo, no por el modelo: un modelo chico se equivoca al sumar una columna o sacar un porcentaje.

Dos piezas que action_runner ofrece como herramientas:
  evaluate(expression)              aritmetica segura (ast, sin eval): + - * / // % **, parentesis y sum/min/max/avg/
                                    round/abs/len sobre listas de numeros.
  aggregate(table, column, op, ..)  sum/avg/min/max/count sobre una columna de una tabla {header, rows} tal como la
                                    devolvio una funcion (p. ej. google_sheets.values.get): los numeros no pasan por el
                                    modelo, asi que no hay errores de copia ni de truncado.
"""
import ast
import operator
import re

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow,
        ast.USub: operator.neg, ast.UAdd: operator.pos}
_FUNCS = {"sum": sum, "min": min, "max": max, "abs": abs, "round": round, "len": len,
          "avg": lambda xs: sum(xs) / len(xs)}
_MAX_POWER = 100       # 9**9**9 colgaria el proceso
_MAX_NODES = 2000      # una expresion gigante tampoco


class CalcError(ValueError):
    pass


def _eval(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > _MAX_POWER:
            raise CalcError("exponent too large")
        return _OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_eval(e) for e in node.elts]
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS and not node.keywords:
        args = [_eval(a) for a in node.args]
        if node.func.id != "round" and len(args) > 1:  # sum(1, 2, 3) como sum([1, 2, 3])
            args = [args]
        return _FUNCS[node.func.id](*args)
    raise CalcError("only numbers, + - * / // % **, parentheses and sum/min/max/avg/round/abs/len are allowed")


def evaluate(expression: str) -> float | int:
    """Valor de una expresion aritmetica. CalcError si trae algo que no sea aritmetica (nombres, atributos, llamadas raras)."""
    text = str(expression or "").replace("^", "**").strip()
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise CalcError("not a valid arithmetic expression") from exc
    if sum(1 for _ in ast.walk(tree)) > _MAX_NODES:
        raise CalcError("expression too long")
    try:
        value = _eval(tree.body)
    except ZeroDivisionError as exc:
        raise CalcError("division by zero") from exc
    except (TypeError, OverflowError) as exc:
        raise CalcError(f"cannot compute: {exc}") from exc
    return _tidy(value)


def _tidy(value):
    if isinstance(value, float):
        value = round(value, 6)
        return int(value) if value.is_integer() else value
    return value


_NUM = re.compile(r"-?\d+(?:\.\d+)?")


def to_number(cell) -> float | None:
    """'$1,200.50' -> 1200.5, '(300)' -> -300, '15%' -> 15, 'N/A' -> None. Supone punto decimal y coma de miles.
    ponytail: '1.200,50' (formato europeo) se lee mal; detectar el formato de la hoja si aparece ese caso."""
    if isinstance(cell, bool) or cell is None:
        return None
    if isinstance(cell, (int, float)):
        return float(cell)
    text = str(cell).strip()
    negative = text.startswith("(") and text.endswith(")")
    found = _NUM.search(text.replace(",", "").replace(" ", ""))
    if not found:
        return None
    value = float(found.group())
    return -value if negative else value


def aggregate(table: dict, column: str, operation: str, where_column: str | None = None, where_contains: str | None = None) -> dict:
    """operation en sum|avg|min|max|count sobre `column` (titulo del encabezado o letra) de {header, rows}. Con
    where_column/where_contains solo cuentan las filas cuya celda contiene ese texto. Devuelve tambien cuantas filas
    entraron y cuantas se saltaron por no ser numero, para que la respuesta lo pueda decir."""
    header = [str(h) for h in (table or {}).get("header") or []]
    rows = [r for r in (table or {}).get("rows") or [] if isinstance(r, list)]
    if not header and not rows:
        raise CalcError("that result has no table (header and rows) to compute on")

    def index(name: str) -> int:
        wanted = str(name or "").strip().lower()
        for i, h in enumerate(header):
            if h.strip().lower() == wanted:
                return i
        for i, h in enumerate(header):
            if wanted and wanted in h.strip().lower():
                return i
        if re.fullmatch(r"[a-z]{1,2}", wanted):  # letra de columna: A, B, AA
            n = 0
            for ch in wanted:
                n = n * 26 + (ord(ch) - 96)
            if n - 1 < max(len(header), max((len(r) for r in rows), default=0)):
                return n - 1
        raise CalcError(f"no column '{name}'; the columns are: {', '.join(header) or '(no header)'}")

    col = index(column)
    if where_contains:
        wcol, needle = index(where_column or column), str(where_contains).lower()
        rows = [r for r in rows if wcol < len(r) and needle in str(r[wcol]).lower()]
    cells = [r[col] if col < len(r) else None for r in rows]
    op = str(operation or "").lower()
    if op == "count":
        return {"operation": op, "column": header[col] if col < len(header) else column, "value": len([c for c in cells if str(c or "").strip()]),
                "rows_used": len(rows), "rows_skipped": 0}
    numbers = [n for n in (to_number(c) for c in cells) if n is not None]
    if op not in ("sum", "avg", "min", "max"):
        raise CalcError("operation must be sum, avg, min, max or count")
    if not numbers:
        raise CalcError(f"column '{column}' has no numbers in those rows")
    value = {"sum": sum, "avg": lambda xs: sum(xs) / len(xs), "min": min, "max": max}[op](numbers)
    return {"operation": op, "column": header[col] if col < len(header) else column, "value": _tidy(value),
            "rows_used": len(numbers), "rows_skipped": len(cells) - len(numbers)}
