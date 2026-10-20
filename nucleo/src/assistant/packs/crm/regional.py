"""Configuración regional del CRM: país → idioma, moneda y formatos (port de `laboratorio/src/plantillas/regional.js`).

En el laboratorio todo el formato pasa por `Intl` (ICU). Aquí no hay ICU, así que cada país lleva escrita su forma, copiada de lo que
da Node 22 (ICU 78) y verificada caso por caso contra él:
  GT  Q 11,600.50 · 1,250   ·  MX $11,600.50 · 1,250  ·  CO $ 11.601 (sin decimales) · 1.250
  ES  11.600,50 € · 1250    ·  US $11,600.50          ·  Otro: USD 11,600.50 (es-419)
Los espacios son los mismos que pone ICU: el que va junto al símbolo es duro (U+00A0).

Funciones puras. `region_de(pais)` devuelve los formatos de un país; un país desconocido usa los de Guatemala (como el laboratorio).
"""
from __future__ import annotations

import math
import unicodedata
from dataclasses import dataclass
from datetime import date, tzinfo
from decimal import ROUND_HALF_UP, Context, Decimal
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from assistant.packs.crm.valores import numero_js, texto_js

PAISES: dict[str, dict[str, str]] = {
    "gt": {"nombre": "Guatemala", "locale": "es-GT", "moneda": "GTQ"},
    "mx": {"nombre": "México", "locale": "es-MX", "moneda": "MXN"},
    "co": {"nombre": "Colombia", "locale": "es-CO", "moneda": "COP"},
    "es": {"nombre": "España", "locale": "es-ES", "moneda": "EUR"},
    "us": {"nombre": "Estados Unidos", "locale": "es-US", "moneda": "USD"},
    "otro": {"nombre": "Otro país", "locale": "es-419", "moneda": "USD"},
}

_DURO = " "
_MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sept", "oct", "nov", "dic"]
_MESES_MX = [*_MESES[:8], "sep", *_MESES[9:]]


@dataclass(frozen=True)
class _Forma:
    """Cómo escribe un país sus números (lo que en el laboratorio resuelve Intl)."""
    decimal: str
    miles: str
    agrupar_desde: int        # cifras enteras a partir de las cuales se separan miles (es-ES: 5 → «1250» pero «11.600»)
    antes: str                # símbolo de la moneda delante (sin el espacio que ICU agrega solo junto a una cifra)
    despues: str              # símbolo detrás
    espacio_si_cifra: bool    # ICU pone un espacio duro entre el símbolo y la cifra («Q 1», «USD 1»), pero no ante «NaN»/«∞»
    decimales_moneda: int
    pct: str                  # «%» o « %» (es-ES)
    meses: list[str]
    con_de: bool              # es-CO: «5 de oct» y «5 de oct de 2025»
    doce_horas: bool          # «9:00 a. m.» / «9:00 a.m.» o «9:00» (es-ES)
    am: str
    pm: str


_FORMAS: dict[str, _Forma] = {
    "es-GT": _Forma(".", ",", 4, "Q", "", True, 2, "%", _MESES, False, True, "a. m.", "p. m."),
    "es-MX": _Forma(".", ",", 4, "$", "", False, 2, "%", _MESES_MX, False, True, "a.m.", "p.m."),
    "es-CO": _Forma(",", ".", 4, "$" + _DURO, "", False, 0, "%", _MESES, True, True, "a. m.", "p. m."),
    "es-ES": _Forma(",", ".", 5, "", _DURO + "€", False, 2, _DURO + "%", _MESES, False, False, "", ""),
    "es-US": _Forma(".", ",", 4, "$", "", False, 2, "%", _MESES, False, True, "a.m.", "p.m."),
    "es-419": _Forma(".", ",", 4, "USD", "", True, 2, "%", _MESES, False, True, "a.m.", "p.m."),
}

_CTX = Context(prec=400)


def _es_negativo(n: float) -> bool:
    # Intl («signDisplay: auto») pone el signo a todo lo negativo, también a -0 y a lo que redondea a 0 («-0»).
    return not math.isnan(n) and math.copysign(1.0, n) < 0


def _cifras(n: float, f: _Forma, maximo: int, minimo: int = 0) -> str:
    """El número sin signo, redondeado como Intl (mitad hacia afuera sobre el decimal más corto) y con sus separadores."""
    if math.isnan(n):
        return "NaN"
    if math.isinf(n):
        return "∞"
    d = Decimal(repr(abs(float(n)))).quantize(Decimal(1).scaleb(-maximo), rounding=ROUND_HALF_UP, context=_CTX)
    entero, _, fraccion = format(d, "f").partition(".")
    fraccion = fraccion.rstrip("0")
    fraccion = fraccion + "0" * (minimo - len(fraccion))
    if len(entero) >= f.agrupar_desde:
        grupos = []
        while len(entero) > 3:
            grupos.insert(0, entero[-3:])
            entero = entero[:-3]
        entero = f.miles.join([entero, *grupos])
    return entero + (f.decimal + fraccion if fraccion else "")


def _redondear_js(x: float) -> float:
    """`Math.round` de JS: la mitad sube hacia +∞ (-2.5 → -2)."""
    if math.isnan(x) or math.isinf(x):
        return x
    piso = math.floor(x)
    return float(piso + 1 if x - piso >= 0.5 else piso)


class Region:
    """Los formatos de un país. Mismos nombres que `regionDe` del laboratorio, en snake_case."""

    def __init__(self, pais: Any):
        p = PAISES.get(pais) if isinstance(pais, str) else None
        p = p or PAISES["gt"]
        self.pais = pais
        self.nombre = p["nombre"]
        self.locale = p["locale"]
        self.moneda = p["moneda"]
        self._f = _FORMAS[self.locale]

    def _moneda(self, n: float, decimales: int) -> str:
        f = self._f
        cuerpo = _cifras(n, f, decimales, decimales)
        antes = f.antes + (_DURO if f.espacio_si_cifra and cuerpo[0].isdigit() else "")
        return ("-" if _es_negativo(n) else "") + antes + cuerpo + f.despues

    def _escala(self, n: float) -> str:
        a = abs(n)
        if a >= 1e6:
            return f"{self._uno(n / 1e6)} M"
        if a >= 1e3:
            return f"{self._uno(n / 1e3)} mil"
        return self._uno(n)

    def _uno(self, n: float) -> str:
        return ("-" if _es_negativo(n) else "") + _cifras(n, self._f, 1)

    def dinero(self, n: float) -> str:
        """Monto con su moneda. Montos enteros sin «,00» (en tablas y tarjetas se lee mejor «Q 1,250» que «Q 1,250.00»)."""
        n = float(n)
        r = _redondear_js(n * 100) / 100
        sin_centavos = not math.isinf(r) and not math.isnan(r) and r == math.floor(r) and self._f.decimales_moneda > 0
        return self._moneda(n, 0 if sin_centavos else self._f.decimales_moneda)

    def dinero_corto(self, n: float) -> str:
        n = float(n)
        f = self._f
        # Dónde va el símbolo y con qué espacio, tal como lo pone ese país ante una cifra («Q 1», «$1», «1 €»).
        antes = f.antes + (_DURO if f.espacio_si_cifra else "")
        return f"{'−' if n < 0 else ''}{antes}{self._escala(abs(n))}{f.despues}"

    def numero(self, n: float) -> str:
        n = float(n)
        return ("-" if _es_negativo(n) else "") + _cifras(n, self._f, 2)

    def numero_corto(self, n: float) -> str:
        return self._escala(float(n))

    def pct(self, fraccion: float) -> str:
        x = float(fraccion)
        if math.isnan(x) or math.isinf(x):
            cuerpo = _cifras(x, self._f, 1)
        else:
            # Intl multiplica por 100 en decimal (0.035 → 3.5, no 3.5000000000000004).
            cuerpo = _cifras(float(Decimal(repr(abs(x))) * 100), self._f, 1)
        return ("-" if _es_negativo(x) else "") + cuerpo + self._f.pct

    def fecha(self, iso: Any, hoy: date | None = None) -> str:
        """«30 oct» (este año) o «5 sept 2025». `hoy` fija el año actual (en el laboratorio es el reloj del navegador)."""
        try:
            d = date.fromisoformat(str(iso)) if len(str(iso)) == 10 else None
        except ValueError:
            d = None
        if d is None:
            return str(iso if iso is not None else "")  # el laboratorio fallaría (Invalid Date); aquí se muestra tal cual
        hoy = hoy or date.today()
        f = self._f
        de = " de " if f.con_de else " "
        texto = f"{d.day}{de}{f.meses[d.month - 1]}"
        return texto if d.year == hoy.year else f"{texto}{de}{d.year}"

    def hora(self, hhmm: Any) -> str:
        """«15:30» → «3:30 p. m.» (o «15:30» en España). Un valor que no es hora se muestra tal cual en vez de fallar."""
        # Como `String(hhmm).split(':').map(Number)`: «9» → 9:00, «» → 0:00, «9:75» → 10:15.
        crudo = "" if hhmm is None else texto_js(hhmm)
        partes = [numero_js(x) for x in (crudo if hhmm is not None else "null").split(":")]
        h = partes[0]
        if math.isnan(h) or math.isinf(h) or h < 0 or h > 23:
            return crudo
        m = partes[1] if len(partes) > 1 else 0.0
        if math.isnan(m):
            m = 0.0
        if math.isinf(m):
            return crudo
        total = (int(h) * 60 + int(m)) % 1440  # setHours: los minutos de más pasan a la hora siguiente
        hh, mm = divmod(total, 60)
        f = self._f
        if not f.doce_horas:
            return f"{hh}:{mm:02d}"
        return f"{hh % 12 or 12}:{mm:02d} {f.am if hh < 12 else f.pm}"


def region_de(pais: Any) -> Region:
    """Formatos de un país sin cambiar la región activa (el chat escribe montos y fechas como los ve la persona)."""
    return Region(pais)


# ───────── Hora del negocio (punto 47) ─────────
# La zona IANA de cada país del cuestionario. México usa la del centro (CDMX; sin horario de verano desde 2022) y Estados Unidos
# la del centro (Chicago: igual a UTC-6 en invierno, con horario de verano): un solo país con varias zonas se resuelve con la
# más poblada para quien usa el CRM en español, no adivinando la ciudad. «otro» o un país desconocido: la zona de respaldo.
ZONAS: dict[str, str | None] = {
    "gt": "America/Guatemala",
    "mx": "America/Mexico_City",
    "co": "America/Bogota",
    "es": "Europe/Madrid",
    "us": "America/Chicago",
    "otro": None,
}


def _llano(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn").strip()


def codigo_pais(valor: Any) -> str | None:
    """El código de `PAISES` («gt», «mx»…) a partir del código o del nombre («México»). None si no es ninguno."""
    if not isinstance(valor, str) or not valor.strip():
        return None
    k = _llano(valor)
    if k in PAISES:
        return k
    return next((c for c, v in PAISES.items() if _llano(v["nombre"]) == k), None)


def zona_del_pais(pais: Any, respaldo: tzinfo) -> tzinfo:
    """La zona horaria del negocio según su país; `respaldo` si es «otro», desconocido o la base de zonas no está instalada."""
    nombre = ZONAS.get(codigo_pais(pais) or "")
    if not nombre:
        return respaldo
    try:
        return ZoneInfo(nombre)
    except (ZoneInfoNotFoundError, ValueError):  # sin `tzdata` (Windows sin el paquete): mejor la hora de respaldo que caerse
        return respaldo
