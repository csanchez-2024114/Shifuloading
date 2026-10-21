"""Lo calculable de meter datos por chat (port de `laboratorio/src/plantillas/valores.js`, D50).

El modelo copia lo que dijo la persona y el CÓDIGO lo entiende y lo valida: fechas en palabras («el 30 de octubre», «mañana», «en 5 días»,
«el viernes»), montos («Q1,200.50», «1.200,50», «500»), horas («9am», «3 de la tarde», «15:30»), opciones de un estado (sin importar
mayúsculas ni acentos) y a qué registro se refiere («Ana López»): si hay más de uno que coincide, NO adivina: devuelve los candidatos para
preguntar.

Funciones puras, con el mismo resultado que las del laboratorio (las pruebas y los fixtures dorados lo comparan). `hoy` siempre se pasa:
el código del servidor no usa el reloj por su cuenta. Las fechas se devuelven como 'AAAA-MM-DD'.

También viven aquí las pocas conversiones de JS que hacen falta para dar los MISMOS textos (`texto_js`, `numero_js`, `sin_acentos`).
"""
from __future__ import annotations

import math
import re
import unicodedata
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
DIAS = ["domingo", "lunes", "martes", "miercoles", "jueves", "viernes", "sabado"]
TIPOS_NO_TEXTO = ("estado", "lista", "fecha", "hora", "numero", "dinero")  # "lista" (Carlos) = alias de "estado"

# Lo que JS cuenta como espacio en `trim()` y en `\s`.
_ESPACIOS = "\t\n\v\f\r                  　﻿"
_S = "[" + _ESPACIOS + "]"


def _re(patron: str) -> re.Pattern:
    """Una expresión con la semántica de JS: `\\d` solo 0-9 y `\\s` los espacios de JS."""
    return re.compile(patron.replace(r"\s", _S), re.ASCII)


# ───────── Conversiones de JS (para dar los mismos textos) ─────────

def recortar(t: str) -> str:
    """`String.prototype.trim` de JS."""
    return t.strip(_ESPACIOS)


def _numero_a_texto(x: float) -> str:
    """`Number.prototype.toString()` de JS (1200.0 → «1200», 1e-7 → «1e-7»)."""
    if math.isnan(x):
        return "NaN"
    if math.isinf(x):
        return "Infinity" if x > 0 else "-Infinity"
    if x == 0:
        return "0"
    signo = "-" if x < 0 else ""
    _, cifras_t, exp = Decimal(repr(abs(x))).normalize().as_tuple()
    cifras = "".join(map(str, cifras_t))
    k = len(cifras)
    n = exp + k
    if k <= n <= 21:
        cuerpo = cifras + "0" * (n - k)
    elif 0 < n <= 21:
        cuerpo = cifras[:n] + "." + cifras[n:]
    elif -6 < n <= 0:
        cuerpo = "0." + "0" * (-n) + cifras
    else:
        e = n - 1
        cuerpo = cifras[0] + ("." + cifras[1:] if k > 1 else "") + "e" + ("+" if e >= 0 else "-") + str(abs(e))
    return signo + cuerpo


def texto_js(v: Any) -> str:
    """`String(v ?? '')` de JS: None → «», True → «true», 1200.0 → «1200», un dict → «[object Object]»."""
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return _numero_a_texto(v)
    if isinstance(v, (list, tuple)):
        return ",".join(texto_js(x) for x in v)
    if isinstance(v, dict):
        return "[object Object]"
    return str(v)


def plantilla_js(v: Any) -> str:
    """Un valor dentro de un texto de JS (`${v}`): lo que falta sale «undefined», como en el laboratorio."""
    return "undefined" if v is None else texto_js(v)


_NUMERO_JS = re.compile(r"[+-]?(?:Infinity|(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?)", re.ASCII)


def numero_js(v: Any) -> float:
    """`Number(v)` de JS. None se toma como `undefined` (lo que no está) → NaN."""
    if v is None:
        return math.nan
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, dict):
        return math.nan
    t = recortar(texto_js(v))
    if t == "":
        return 0.0
    if _NUMERO_JS.fullmatch(t):
        return float(t.replace("Infinity", "inf"))
    if re.fullmatch(r"0[xX][0-9a-fA-F]+|0[oO][0-7]+|0[bB][01]+", t):
        return float(int(t, 0))
    return math.nan


def es_numero(v: Any) -> bool:
    """`typeof v === 'number'`."""
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def a_js(n: float) -> int | float:
    """Un número como lo guarda JS: sin «.0» si es entero (1200.0 → 1200)."""
    if isinstance(n, float) and n.is_integer() and abs(n) < 2**53:
        return int(n)
    return n


def sin_acentos(t: Any) -> str:
    """Minúsculas, sin acentos (ni la tilde de la ñ) y sin espacios a los lados."""
    n = unicodedata.normalize("NFD", texto_js(t).lower())
    return recortar("".join(c for c in n if not "̀" <= c <= "ͯ"))


# ───────── Fechas ─────────

def _dia(hoy: date | datetime) -> date:
    return date(hoy.year, hoy.month, hoy.day)


def iso(d: date) -> str:
    """'AAAA-MM-DD' (el año sin rellenar, como el laboratorio)."""
    return f"{d.year}-{d.month:02d}-{d.day:02d}"


def _fecha_js(y: int, mes0: int, d: int) -> date:
    """`new Date(y, mes0, d)`: el mes y el día se desbordan (31 de febrero → 3 de marzo); los años 0-99 son 1900-1999."""
    if 0 <= y <= 99:
        y += 1900
    y += mes0 // 12
    return date(y, mes0 % 12 + 1, 1) + timedelta(days=d - 1)


def _mas_meses(base: date, n: int) -> date:
    """`d.setMonth(d.getMonth() + n)`: conserva el día y se desborda (31 de enero + 1 mes → 3 de marzo)."""
    total = base.month - 1 + n
    return date(base.year + total // 12, total % 12 + 1, 1) + timedelta(days=base.day - 1)


def _valida(y: int, m: int, d: int) -> date | None:
    if y < 100:
        return None  # en JS `new Date(26, …)` es 1926: nunca coincide
    try:
        return date(y, m, d)
    except ValueError:
        return None


def _mes(t: str) -> int:
    k = sin_acentos(t)[:3]
    i = next((j for j, m in enumerate(MESES) if m.startswith(k)), -1)
    return i + 1 if i >= 0 and len(k) >= 3 else 0


def _dia_semana(d: date) -> int:
    """`getDay()`: domingo = 0."""
    return (d.weekday() + 1) % 7


_N = {"un": 1, "una": 1, "dos": 2, "tres": 3}

_ANIO_DICHO = _re(r"\s*(?:de|del)\s+(?:(este|proximo|siguiente|pasado)\s+ano|ano\s+(que viene|entrante|proximo|siguiente|pasado))\Z")
_F_ISO = _re(r"(\d{4})-(\d{1,2})-(\d{1,2})")
_F_NUM = _re(r"(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?")
_F_HOY_MAS = _re(r"hoy\s*\+\s*(\d+)\s*(dia|dias|semana|semanas|mes|meses|ano|anos)")
_F_DESDE_HOY = _re(r"(?:(?:dentro de|en)\s+)?(\d+|un|una|dos|tres)\s+(dia|dias|semana|semanas|mes|meses|ano|anos)\s+(?:desde|a partir de|contando desde|despues de)\s+hoy")
_F_EN = _re(r"(?:dentro de |en )(\d+|un|una|dos|tres)\s+(dia|dias|semana|semanas|mes|meses|ano|anos)")
_F_HACE = _re(r"hace (\d+|un|una|dos|tres)\s+(dia|dias|semana|semanas)")
_F_DIA_MES = _re(r"(\d{1,2})\s*(?:de\s+)?([a-z]+)(?:\s*(?:de|del)?\s*(\d{4}))?")
_F_MES_DIA = _re(r"([a-z]+)\s+(\d{1,2})(?:\s*(?:de|,)?\s*(\d{4}))?")
_F_SEMANA = _re(r"(?:este |el |proximo |el proximo )?(domingo|lunes|martes|miercoles|jueves|viernes|sabado)")


def parse_fecha(texto: Any, hoy: date | datetime) -> str | None:
    """Fecha dicha por la persona → 'AAAA-MM-DD' (o None si no se entiende)."""
    try:
        return _parse_fecha(texto, _dia(hoy))
    except (OverflowError, ValueError):
        return None  # «en 99999999 días»: fuera de lo que cabe en una fecha


def _parse_fecha(texto: Any, base: date) -> str | None:
    # «del próximo año», «del año que viene», «de este año», «del año pasado» → el año en número
    t = re.sub(r"^el" + _S + "+|^la" + _S + "+", "", sin_acentos(texto), count=1)
    t = _ANIO_DICHO.sub(lambda m: f" de {base.year + {'este': 0, 'pasado': -1}.get(m.group(1) or m.group(2), 1)}", t, count=1)
    if not t:
        return None

    def mas(n: int) -> str:
        return iso(base + timedelta(days=n))

    if m := _F_ISO.fullmatch(t):
        d = _valida(int(m[1]), int(m[2]), int(m[3]))
        return iso(d) if d else None
    if m := _F_NUM.fullmatch(t):  # día primero (Latinoamérica)
        y = (2000 + int(m[3]) if len(m[3]) == 2 else int(m[3])) if m[3] else base.year
        d = _valida(y, int(m[2]), int(m[1]))
        return iso(d) if d else None
    if t == "hoy":
        return mas(0)
    # Lo relativo como lo reescribe el modelo (medido): «un mes desde hoy», «hoy + 1 mes», «30 días a partir de hoy»
    if m := _F_HOY_MAS.fullmatch(t):
        return _parse_fecha(f"en {m[1]} {m[2]}", base)
    if m := _F_DESDE_HOY.fullmatch(t):
        return _parse_fecha(f"en {m[1]} {m[2]}", base)
    if t == "manana":
        return mas(1)
    if t == "pasado manana":
        return mas(2)
    if t == "ayer":
        return mas(-1)
    if m := _F_EN.fullmatch(t):
        n = _N.get(m[1]) or int(m[1])
        if m[2].startswith("dia"):
            return mas(n)
        if m[2].startswith("semana"):
            return mas(7 * n)
        return iso(_mas_meses(base, 12 * n if m[2].startswith("ano") else n))
    if m := _F_HACE.fullmatch(t):
        n = _N.get(m[1]) or int(m[1])
        return mas(-(n if m[2].startswith("dia") else 7 * n))
    # «30 de octubre», «30 octubre 2026», «oct 30»
    if (m := _F_DIA_MES.fullmatch(t)) and _mes(m[2]):
        d = _valida(int(m[3]) if m[3] else base.year, _mes(m[2]), int(m[1]))
        return iso(d) if d else None
    if (m := _F_MES_DIA.fullmatch(t)) and _mes(m[1]):
        d = _valida(int(m[3]) if m[3] else base.year, _mes(m[1]), int(m[2]))
        return iso(d) if d else None
    # «el viernes», «este viernes», «el próximo lunes»: el siguiente que venga (hoy no cuenta)
    if m := _F_SEMANA.fullmatch(t):
        return mas((DIAS.index(m[1]) - _dia_semana(base) + 7) % 7 or 7)
    return None


def fecha_larga(iso_texto: Any) -> str:
    """'AAAA-MM-DD' → «30 de octubre de 2026» (así el modelo repite la fecha exacta, con año)."""
    vacio = iso_texto is None or iso_texto is False or iso_texto == "" or (es_numero(iso_texto) and (iso_texto == 0 or math.isnan(iso_texto)))
    m = re.fullmatch(r"([0-9]{4})-([0-9]{2})-([0-9]{2})", "" if vacio else texto_js(iso_texto))
    if not m:
        return texto_js(iso_texto)
    mes = int(m[2])
    return f"{int(m[3])} de {MESES[mes - 1] if 1 <= mes <= 12 else 'undefined'} de {m[1]}"


# ───────── Periodos ─────────

_P_VENCIDOS = _re(r"vencid[oa]s?|ya vencid[oa]s?|atrasad[oa]s?")
_P_ULTIMOS = _re(r"ultim[oa]s (\d+|un|una|dos|tres) (dia|dias|semana|semanas)")
_P_PROXIMOS = _re(r"(?:proxim[oa]s|siguientes) (\d+|un|una|dos|tres) (dia|dias|semana|semanas)")
_P_MES = _re(r"([a-z]+)(?:\s+(?:de|del)?\s*(\d{4}))?")
_P_DEL_AL_MES = _re(r"(?:del |desde (?:el )?)?(\d{1,2})\s+(?:al|hasta (?:el )?|a)\s+(\d{1,2})\s+(?:de\s+)?([a-z]+)(?:\s+(?:de\s+)?(\d{4}))?")
_P_DEL_AL = _re(r"(?:del |desde (?:el )?)(.+?)\s+(?:al|hasta (?:el )?)\s+(.+)")


def parse_periodo(texto: Any, hoy: date | datetime) -> dict | None:
    """Un periodo dicho por la persona → {desde, hasta} ('AAAA-MM-DD' o None = sin límite), o None si no se entiende.

    «hoy», «esta semana» (lunes a domingo), «la semana pasada», «este mes», «el mes pasado», «el próximo mes», «este año», «los últimos 30
    días», «los próximos 7 días» (de hoy a hoy + 7, como los grupos de lo que vence), «vencidos» (antes de hoy), «octubre», «octubre de
    2025», «del 1 al 15 de octubre» o una fecha suelta.
    """
    # Dos fechas en ISO («2026-10-21 a 2026-10-28»): el modelo a veces calcula el rango él mismo (banco_datos, 21-oct).
    m = re.fullmatch(r"\s*(?:del?\s+)?(\d{4}-\d{2}-\d{2})\s*(?:a|al|-|–|hasta)\s*(\d{4}-\d{2}-\d{2})\s*", str(texto or ""))
    if m:
        try:
            a, b = date.fromisoformat(m.group(1)), date.fromisoformat(m.group(2))
            return {"desde": min(a, b).isoformat(), "hasta": max(a, b).isoformat()}
        except ValueError:
            return None
    try:
        return _parse_periodo(texto, _dia(hoy))
    except (OverflowError, ValueError):
        return None


def _parse_periodo(texto: Any, base: date) -> dict | None:
    t = re.sub(r"^(en |durante |de |para )", "", sin_acentos(texto), count=1)
    t = recortar(re.sub(r"^(el |la |los |las )", "", t, count=1))
    if not t:
        return None

    def dia(n: int) -> str:
        return iso(base + timedelta(days=n))

    def mes_de(y: int, m0: int) -> dict:
        return {"desde": iso(_fecha_js(y, m0, 1)), "hasta": iso(_fecha_js(y, m0 + 1, 0))}

    def semana(sem: int) -> dict:
        lunes = base - timedelta(days=base.weekday()) + timedelta(days=7 * sem)
        return {"desde": iso(lunes), "hasta": iso(lunes + timedelta(days=6))}

    if _P_VENCIDOS.fullmatch(t):
        return {"desde": None, "hasta": dia(-1)}
    if _re(r"esta semana|semana actual").fullmatch(t):
        return semana(0)
    if _re(r"semana pasada|anterior semana").fullmatch(t):
        return semana(-1)
    if _re(r"proxima semana|semana que viene|siguiente semana").fullmatch(t):
        return semana(1)
    if _re(r"este mes|mes actual").fullmatch(t):
        return mes_de(base.year, base.month - 1)
    if _re(r"mes pasado|anterior mes").fullmatch(t):
        return mes_de(base.year, base.month - 2)
    if _re(r"proximo mes|mes que viene|siguiente mes").fullmatch(t):
        return mes_de(base.year, base.month)
    if _re(r"este ano|ano actual").fullmatch(t):
        return {"desde": f"{base.year}-01-01", "hasta": f"{base.year}-12-31"}
    if t == "ano pasado":
        return {"desde": f"{base.year - 1}-01-01", "hasta": f"{base.year - 1}-12-31"}
    if m := _P_ULTIMOS.fullmatch(t):
        n = (_N.get(m[1]) or int(m[1])) * (7 if m[2].startswith("semana") else 1)
        return {"desde": dia(-n), "hasta": dia(0)}
    if m := _P_PROXIMOS.fullmatch(t):
        n = (_N.get(m[1]) or int(m[1])) * (7 if m[2].startswith("semana") else 1)
        return {"desde": dia(0), "hasta": dia(n)}
    if (m := _P_MES.fullmatch(t)) and _mes(m[1]) and len(m[1]) >= 4:
        return mes_de(int(m[2]) if m[2] else base.year, _mes(m[1]) - 1)
    if (m := _P_DEL_AL_MES.fullmatch(t)) and _mes(m[3]):
        y = int(m[4]) if m[4] else base.year
        a, b = _valida(y, _mes(m[3]), int(m[1])), _valida(y, _mes(m[3]), int(m[2]))
        return {"desde": iso(a), "hasta": iso(b)} if a and b and a <= b else None
    if m := _P_DEL_AL.fullmatch(t):
        a, b = _parse_fecha(m[1], base), _parse_fecha(m[2], base)
        return {"desde": a, "hasta": b} if a and b and a <= b else None
    f = _parse_fecha(t, base)
    return {"desde": f, "hasta": f} if f else None


# ───────── Números y horas ─────────

def parse_numero(texto: Any) -> int | float | None:
    """Monto o número dicho por la persona → número (o None). «Q1,200.50», «1.200,50», «$ 300», «500 quetzales», «12,5».

    Regla: si hay coma y punto, el último es el decimal. Solo comas: varias o «1,200» (3 dígitos) = miles; si no, decimal.
    Solo puntos: varios = miles; uno = decimal (como se escribe en Guatemala y México). Los enteros salen sin «.0».
    """
    if es_numero(texto):
        return a_js(texto) if math.isfinite(texto) else None
    t = re.sub(r"[^0-9.,-]", "", texto_js(texto))
    if not re.search(r"[0-9]", t):
        return None
    comas, puntos = t.count(","), t.count(".")
    if comas and puntos:
        t = t.replace(".", "").replace(",", ".", 1) if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    elif comas:
        t = t.replace(",", "") if comas > 1 or re.fullmatch(r"-?[0-9]{1,3},[0-9]{3}", t) else t.replace(",", ".", 1)
    elif puntos > 1:
        t = t.replace(".", "")
    n = numero_js(t)
    return a_js(n) if math.isfinite(n) else None


_HORA = _re(r"(\d{1,2})(?::(\d{2}))?\s*(am|a\.?\s*m\.?|pm|p\.?\s*m\.?|de la manana|de la tarde|de la noche|hrs?|h)?")


def parse_hora(texto: Any) -> str | None:
    """Hora dicha por la persona → 'HH:MM' (o None). «9am», «9:30», «15:00», «3 pm», «3 de la tarde», «mediodía»."""
    t = sin_acentos(texto)
    if not t:
        return None
    if t == "mediodia":
        return "12:00"
    m = _HORA.fullmatch(t)
    if not m:
        return None
    h = int(m[1])
    minutos = int(m[2]) if m[2] else 0
    suf = re.sub("[" + _ESPACIOS + ".]", "", m[3] or "")
    if suf in ("pm", "delatarde", "delanoche") and h < 12:
        h += 12
    if suf == "am" and h == 12:
        h = 0
    if h > 23 or minutos > 59:
        return None
    return f"{h:02d}:{minutos:02d}"


# ───────── Opciones y registros ─────────

def opcion_de(campo: dict, valor: Any) -> str | None:
    """La opción de un estado tal como existe («pausada» → «Pausada»), o None si no existe."""
    v = sin_acentos(valor)
    return next((o for o in (campo.get("opciones") or []) if sin_acentos(o) == v), None)


def _tipo(c: dict) -> Any:
    return c.get("tipo")


def campo_titulo(seccion: dict, campos: list[dict]) -> dict | None:
    """El campo que nombra a un registro: el 1.º de su tarjeta o el primer texto."""
    primero = (((seccion or {}).get("tarjeta") or {}).get("campos") or [None])[0]
    return (next((c for c in campos if c.get("id") == primero), None)
            or next((c for c in campos if _tipo(c) not in TIPOS_NO_TEXTO), None)
            or (campos[0] if campos else None))


def _valores(r: dict) -> dict:
    return r.get("valores") or {}


def buscar_registro(registros: list[dict], seccion: dict, campos: list[dict], consulta: Any) -> dict:
    """¿A qué registro se refiere «consulta»? Primero por id, luego nombre exacto, luego que contenga todas sus palabras en algún texto.

    Devuelve {"registro": r} o {"candidatos": [...]} (varios: hay que preguntar) o {"ninguno": True}.
    """
    por_id = next((r for r in registros if r.get("id") == consulta), None)
    if por_id is not None:
        return {"registro": por_id}
    q = sin_acentos(consulta)
    if not q:
        return {"ninguno": True}
    ct = campo_titulo(seccion, campos)
    textos = [c for c in campos if _tipo(c) not in TIPOS_NO_TEXTO]
    exactos = [r for r in registros if sin_acentos(_valores(r).get(ct["id"])) == q]
    if len(exactos) == 1:
        return {"registro": exactos[0]}
    if len(exactos) > 1:
        return {"candidatos": exactos}
    palabras = [w for w in re.split(_S + "+", q) if len(w) > 1]

    def coincide(r: dict) -> bool:
        return all(
            any(any(x == w or (len(w) >= 4 and x.startswith(w)) for x in re.split(_S + "+", sin_acentos(_valores(r).get(c["id"]))))
                for c in textos)
            for w in palabras)

    parecidos = [r for r in registros if coincide(r)]
    if len(parecidos) == 1:
        return {"registro": parecidos[0]}
    if len(parecidos) > 1:
        return {"candidatos": parecidos}
    return {"ninguno": True}
