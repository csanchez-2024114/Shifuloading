"""Herramientas extra para el registro de bigtool: útiles, inofensivas y sin efectos reales (no escriben
archivos, no envían nada, no ejecutan código). Las de "mundo" solo LEEN APIs públicas sin clave:
Open-Meteo (clima/geocodificación), Frankfurter (tipo de cambio del BCE) y Wikipedia.
Nombres y descripciones en inglés: mejoran la búsqueda semántica de retrieve_tools."""
import base64
import hashlib
import json
import math
import random
import re
import secrets
import statistics
import string
import uuid
from collections import Counter
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from langchain_core.tools import BaseTool, tool

_UA = "Agente0/0.1 (local personal assistant prototype; https://github.com/langchain-ai) python-httpx"


def _get_json(url: str, params: dict | None = None) -> dict:
    r = httpx.get(url, params=params, timeout=10, follow_redirects=True, headers={"User-Agent": _UA})
    r.raise_for_status()
    return r.json()


def _get_json_same_host(url: str, params: dict | None = None, max_redirects: int = 3) -> dict:
    """Como _get_json, pero solo sigue redirecciones dentro del mismo host (S6): una respuesta que mande a otro
    dominio es un error, no una petición nueva."""
    host = httpx.URL(url).host
    r = httpx.get(url, params=params, timeout=10, follow_redirects=False, headers={"User-Agent": _UA})
    for _ in range(max_redirects):
        if not r.is_redirect or r.next_request is None:
            break
        if r.next_request.url.host != host:
            raise ValueError(f"redirect to another host refused: {r.next_request.url.host}")
        r = httpx.get(r.next_request.url, timeout=10, follow_redirects=False, headers={"User-Agent": _UA})
    r.raise_for_status()
    return r.json()


def _date(s: str) -> date:
    return date.fromisoformat(s.strip()[:10])


# --------------------------------------------------------------------------- conversiones
_FACTORS = {  # unidad -> (dimensión, factor a la unidad base)
    **{u: ("length", f) for u, f in {"mm": .001, "cm": .01, "m": 1, "km": 1000, "in": .0254, "ft": .3048,
                                      "yd": .9144, "mi": 1609.344, "nmi": 1852}.items()},
    **{u: ("mass", f) for u, f in {"mg": 1e-6, "g": .001, "kg": 1, "t": 1000, "oz": .028349523125,
                                    "lb": .45359237}.items()},
    **{u: ("volume", f) for u, f in {"ml": .001, "l": 1, "m3": 1000, "tsp": .00492892, "tbsp": .0147868,
                                      "cup": .236588, "floz": .0295735, "gal": 3.785411784}.items()},
    **{u: ("speed", f) for u, f in {"m/s": 1, "km/h": 1 / 3.6, "mph": .44704, "knot": .514444}.items()},
    **{u: ("area", f) for u, f in {"m2": 1, "km2": 1e6, "ha": 1e4, "ft2": .09290304, "acre": 4046.8564224}.items()},
    **{u: ("data", f) for u, f in {"b": 1, "kb": 1e3, "mb": 1e6, "gb": 1e9, "tb": 1e12, "kib": 1024,
                                    "mib": 1024 ** 2, "gib": 1024 ** 3}.items()},
}
_TO_C = {"c": lambda x: x, "f": lambda x: (x - 32) * 5 / 9, "k": lambda x: x - 273.15}
_FROM_C = {"c": lambda x: x, "f": lambda x: x * 9 / 5 + 32, "k": lambda x: x + 273.15}


@tool
def convert_units(value: float, from_unit: str, to_unit: str) -> str:
    """Convert a value between measurement units: length (mm, cm, m, km, in, ft, yd, mi, nmi), mass (mg, g,
    kg, t, oz, lb), volume (ml, l, m3, tsp, tbsp, cup, floz, gal), speed (m/s, km/h, mph, knot), area (m2,
    km2, ha, ft2, acre), data size (b, kb, mb, gb, tb, kib, mib, gib) and temperature (c, f, k)."""
    a, b = from_unit.strip().lower(), to_unit.strip().lower()
    if a in _TO_C and b in _TO_C:
        return f"{value} {a.upper()} = {_FROM_C[b](_TO_C[a](value)):.4g} {b.upper()}"
    if a not in _FACTORS or b not in _FACTORS or _FACTORS[a][0] != _FACTORS[b][0]:
        return f"Error: cannot convert {from_unit} to {to_unit} (unknown or incompatible units)."
    return f"{value} {from_unit} = {value * _FACTORS[a][1] / _FACTORS[b][1]:.6g} {to_unit}"


@tool
def convert_currency(amount: float, from_currency: str, to_currency: str) -> str:
    """Convert money between currencies (ISO codes like USD, MXN, EUR, GBP, JPY) using today's official
    European Central Bank exchange rate (Frankfurter API)."""
    a, b = from_currency.strip().upper(), to_currency.strip().upper()
    data = _get_json("https://api.frankfurter.dev/v1/latest", {"from": a, "to": b})
    rate = data["rates"][b]
    return f"{amount:,.2f} {a} = {amount * rate:,.2f} {b} (rate {rate}, ECB date {data['date']})"


@tool
def convert_timezone(datetime_text: str, from_timezone: str, to_timezone: str) -> str:
    """Convert a date-time (ISO format, e.g. 2026-10-15 09:30) from one IANA time zone to another
    (e.g. America/Mexico_City -> Europe/Madrid)."""
    dt = datetime.fromisoformat(datetime_text.strip()).replace(tzinfo=ZoneInfo(from_timezone))
    return f"{dt.astimezone(ZoneInfo(to_timezone)):%Y-%m-%d %H:%M %Z (UTC%z)} in {to_timezone}"


# --------------------------------------------------------------------------- fechas
@tool
def days_between_dates(start_date: str, end_date: str) -> str:
    """Count the calendar days between two dates (ISO format YYYY-MM-DD)."""
    d = (_date(end_date) - _date(start_date)).days
    return f"{d} days ({d / 7:.1f} weeks)"


@tool
def add_days_to_date(start_date: str, days: int) -> str:
    """Add (or subtract, with a negative number) a number of days to a date (YYYY-MM-DD)."""
    d = _date(start_date) + timedelta(days=days)
    return f"{d.isoformat()} ({d:%A})"


@tool
def day_of_week(date_text: str) -> str:
    """Return the day of the week for a given date (YYYY-MM-DD)."""
    return f"{_date(date_text):%A}"


@tool
def age_from_birthdate(birthdate: str) -> str:
    """Compute someone's exact age (years, months, days) from a birthdate (YYYY-MM-DD)."""
    b, t = _date(birthdate), date.today()
    years = t.year - b.year - ((t.month, t.day) < (b.month, b.day))
    last = b.replace(year=b.year + years)
    months = (t.year - last.year) * 12 + t.month - last.month - (t.day < last.day)
    return f"{years} years, {months} months; next birthday in {((last.replace(year=last.year + 1)) - t).days} days"


@tool
def business_days_between(start_date: str, end_date: str) -> str:
    """Count working days (Monday to Friday) between two dates (YYYY-MM-DD), both included. Ignores holidays."""
    a, b = _date(start_date), _date(end_date)
    n = sum(1 for i in range((b - a).days + 1) if (a + timedelta(days=i)).weekday() < 5)
    return f"{n} business days (holidays not excluded)"


# --------------------------------------------------------------------------- finanzas
@tool
def loan_payment(principal: float, annual_rate_percent: float, years: float) -> str:
    """Fixed monthly payment of a loan or mortgage (French amortization), plus total paid and total interest."""
    r, n = annual_rate_percent / 100 / 12, round(years * 12)
    pay = principal / n if r == 0 else principal * r / (1 - (1 + r) ** -n)
    return f"monthly payment {pay:,.2f}; total paid {pay * n:,.2f}; total interest {pay * n - principal:,.2f} ({n} months)"


@tool
def compound_interest(principal: float, annual_rate_percent: float, years: float, monthly_contribution: float = 0) -> str:
    """Future value of savings/investment with monthly compounding and optional monthly contributions."""
    r, n = annual_rate_percent / 100 / 12, round(years * 12)
    fv = principal * (1 + r) ** n + (monthly_contribution * ((1 + r) ** n - 1) / r if r else monthly_contribution * n)
    invested = principal + monthly_contribution * n
    return f"future value {fv:,.2f}; invested {invested:,.2f}; interest earned {fv - invested:,.2f}"


@tool
def percentage_change(old_value: float, new_value: float) -> str:
    """Percentage increase or decrease from an old value to a new value."""
    return f"{(new_value - old_value) / old_value * 100:+.2f}%"


@tool
def add_sales_tax(amount: float, tax_percent: float = 16, amount_includes_tax: bool = False) -> str:
    """Add sales tax / VAT (IVA, 16% in Mexico by default) to an amount, or break it down if the amount already includes it."""
    sub = amount / (1 + tax_percent / 100) if amount_includes_tax else amount
    return f"subtotal {sub:,.2f}; tax {sub * tax_percent / 100:,.2f}; total {sub * (1 + tax_percent / 100):,.2f}"


@tool
def split_bill(total: float, people: int, tip_percent: float = 10) -> str:
    """Split a restaurant bill between people, including the tip."""
    with_tip = total * (1 + tip_percent / 100)
    return f"total with tip {with_tip:,.2f}; each person pays {with_tip / people:,.2f}"


# --------------------------------------------------------------------------- datos
@tool
def describe_numbers(numbers: list[float]) -> str:
    """Descriptive statistics of a list of numbers: count, sum, mean, median, mode, standard deviation, min, max."""
    sd = statistics.stdev(numbers) if len(numbers) > 1 else 0
    return (f"count {len(numbers)}; sum {sum(numbers):g}; mean {statistics.mean(numbers):.4g}; "
            f"median {statistics.median(numbers):g}; mode {statistics.mode(numbers):g}; stdev {sd:.4g}; "
            f"min {min(numbers):g}; max {max(numbers):g}")


@tool
def linear_regression(x_values: list[float], y_values: list[float]) -> str:
    """Fit a straight line y = slope*x + intercept to data points and report the correlation (r and r²).
    Useful for trends and simple forecasts."""
    lr = statistics.linear_regression(x_values, y_values)
    r = statistics.correlation(x_values, y_values)
    return f"y = {lr.slope:.6g}*x + {lr.intercept:.6g}; r = {r:.4f}; r² = {r * r:.4f}"


@tool
def body_mass_index(weight_kg: float, height_m: float) -> str:
    """Body mass index (BMI) from weight in kg and height in meters, with the WHO category."""
    bmi = weight_kg / height_m ** 2
    cat = "underweight" if bmi < 18.5 else "normal" if bmi < 25 else "overweight" if bmi < 30 else "obesity"
    return f"BMI {bmi:.1f} ({cat})"


# --------------------------------------------------------------------------- mundo (solo lectura)
def _geocode(place: str) -> dict:
    res = _get_json("https://geocoding-api.open-meteo.com/v1/search",
                    {"name": place, "count": 1, "language": "es"}).get("results") or []
    if not res:
        raise ValueError(f"place not found: {place}")
    return res[0]


@tool
def geocode_place(place: str) -> str:
    """Find a city or place: country, region, latitude/longitude, population and time zone."""
    g = _geocode(place)
    return (f"{g['name']}, {g.get('admin1', '')}, {g.get('country', '')}: lat {g['latitude']}, lon {g['longitude']}, "
            f"population {g.get('population', 'n/a')}, time zone {g.get('timezone', 'n/a')}")


@tool
def distance_between_places(place_a: str, place_b: str) -> str:
    """Straight-line (great-circle) distance in km between two cities or places."""
    a, b = _geocode(place_a), _geocode(place_b)
    p1, p2 = math.radians(a["latitude"]), math.radians(b["latitude"])
    dl = math.radians(b["longitude"] - a["longitude"])
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    km = 2 * 6371.0088 * math.asin(math.sqrt(h))
    return f"{a['name']} ({a.get('country', '')}) -> {b['name']} ({b.get('country', '')}): {km:,.0f} km in a straight line"


_WMO = {0: "clear", 1: "mainly clear", 2: "partly cloudy", 3: "overcast", 45: "fog", 48: "fog", 51: "drizzle",
        53: "drizzle", 55: "drizzle", 61: "light rain", 63: "rain", 65: "heavy rain", 71: "snow", 73: "snow",
        75: "heavy snow", 80: "showers", 81: "showers", 82: "violent showers", 95: "thunderstorm",
        96: "thunderstorm with hail", 99: "thunderstorm with hail"}


@tool
def weather_forecast(place: str) -> str:
    """Current weather and the forecast for the next 3 days in a city (temperature, rain probability, wind)."""
    g = _geocode(place)
    d = _get_json("https://api.open-meteo.com/v1/forecast", {
        "latitude": g["latitude"], "longitude": g["longitude"], "timezone": "auto", "forecast_days": 3,
        "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code"})
    c, dl = d["current"], d["daily"]
    lines = [f"{g['name']}, {g.get('country', '')} now: {c['temperature_2m']}°C, {_WMO.get(c['weather_code'], '?')}, "
             f"humidity {c['relative_humidity_2m']}%, wind {c['wind_speed_10m']} km/h"]
    for i, day in enumerate(dl["time"]):
        lines.append(f"{day}: {dl['temperature_2m_min'][i]}–{dl['temperature_2m_max'][i]}°C, "
                     f"{_WMO.get(dl['weather_code'][i], '?')}, rain {dl['precipitation_probability_max'][i]}%")
    return "\n".join(lines)


@tool
def wikipedia_summary(topic: str, language: str = "es") -> str:
    """Short encyclopedia summary of a topic, person, place or concept from Wikipedia (language code: es, en...)."""
    # S6: el código va al nombre del host; sin validar, "atacante.com/x?" mandaba la petición a otro dominio
    if not re.fullmatch(r"[a-z]{2,3}(-[a-z]{2,8})*|simple", language or ""):
        return f"Error: invalid Wikipedia language code {language!r}. Use a code such as es, en or pt-br."
    base = f"https://{language}.wikipedia.org"
    hits = _get_json_same_host(f"{base}/w/api.php", {"action": "query", "list": "search", "srsearch": topic,
                                           "srlimit": 1, "format": "json"})["query"]["search"]
    if not hits:
        return f"No Wikipedia article found for {topic!r}."
    title = hits[0]["title"]
    s = _get_json_same_host(f"{base}/api/rest_v1/page/summary/{title.replace(' ', '_')}")
    return f"{s.get('title', title)}: {s.get('extract', '')}\n{s.get('content_urls', {}).get('desktop', {}).get('page', '')}"


# --------------------------------------------------------------------------- texto y utilidades
@tool
def word_frequency(text: str, top: int = 10) -> str:
    """Most frequent words in a text (ignores words shorter than 3 letters)."""
    words = [w for w in re.findall(r"\w+", text.lower()) if len(w) >= 3]
    return ", ".join(f"{w} ({n})" for w, n in Counter(words).most_common(top)) or "no words"


@tool
def extract_emails_and_urls(text: str) -> str:
    """Extract all email addresses and web URLs found in a text."""
    emails = sorted(set(re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)))
    urls = sorted(set(re.findall(r"https?://[^\s<>\"')]+", text)))
    return f"emails: {emails or 'none'}\nurls: {urls or 'none'}"


@tool
def generate_password(length: int = 16, include_symbols: bool = True) -> str:
    """Generate a cryptographically secure random password."""
    length = max(8, min(length, 128))
    alphabet = string.ascii_letters + string.digits + ("!@#$%^&*-_=+?" if include_symbols else "")
    return "".join(secrets.choice(alphabet) for _ in range(length))


@tool
def generate_uuid(count: int = 1) -> str:
    """Generate one or more random UUID v4 identifiers."""
    return "\n".join(str(uuid.uuid4()) for _ in range(max(1, min(count, 20))))


@tool
def hash_text(text: str, algorithm: str = "sha256") -> str:
    """Compute the hash of a text (md5, sha1, sha256, sha512)."""
    if algorithm.lower() not in {"md5", "sha1", "sha256", "sha512"}:
        return "Error: use md5, sha1, sha256 or sha512."
    return hashlib.new(algorithm.lower(), text.encode()).hexdigest()


@tool
def base64_encode(text: str) -> str:
    """Encode a text in Base64."""
    return base64.b64encode(text.encode()).decode()


@tool
def base64_decode(encoded: str) -> str:
    """Decode a Base64 string back to text."""
    return base64.b64decode(encoded.encode(), validate=True).decode("utf-8", errors="replace")


@tool
def format_json(json_text: str) -> str:
    """Validate a JSON text and return it pretty-printed (or the syntax error location)."""
    try:
        return json.dumps(json.loads(json_text), indent=2, ensure_ascii=False)
    except json.JSONDecodeError as exc:
        return f"Invalid JSON: {exc}"


_CURP_CHARS = "0123456789ABCDEFGHIJKLMNÑOPQRSTUVWXYZ"


@tool
def validate_curp(curp: str) -> str:
    """Validate a Mexican CURP (personal ID code): format, birth date, sex, state and check digit."""
    c = curp.strip().upper()
    m = re.fullmatch(r"[A-Z][AEIOUX][A-Z]{2}(\d{2})(\d{2})(\d{2})([HMX])([A-Z]{2})[B-DF-HJ-NP-TV-Z]{3}[A-Z\d](\d)", c)
    if not m:
        return "Invalid CURP: wrong format."
    total = sum(_CURP_CHARS.index(ch) * (18 - i) for i, ch in enumerate(c[:17]))
    ok = (10 - total % 10) % 10 == int(c[17])
    yy, mm, dd, sex, state = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
    century = "20" if c[16].isalpha() else "19"
    return (f"{'Valid' if ok else 'Invalid check digit'}: born {century}{yy}-{mm}-{dd}, "
            f"sex {'male' if sex == 'H' else 'female' if sex == 'M' else 'non-binary'}, state code {state}")


# --------------------------------------------------------------------------- azar
@tool
def roll_dice(sides: int = 6, count: int = 1) -> str:
    """Roll one or more dice with the given number of sides."""
    rolls = [random.randint(1, max(2, sides)) for _ in range(max(1, min(count, 100)))]
    return f"rolls {rolls}; total {sum(rolls)}"


@tool
def random_choice(options: list[str], count: int = 1) -> str:
    """Pick one or more random options from a list (without repetition), e.g. to decide or draw lots."""
    return ", ".join(random.sample(options, max(1, min(count, len(options)))))


def extra_tools() -> list[BaseTool]:
    return [convert_units, convert_currency, convert_timezone, days_between_dates, add_days_to_date, day_of_week,
            age_from_birthdate, business_days_between, loan_payment, compound_interest, percentage_change,
            add_sales_tax, split_bill, describe_numbers, linear_regression, body_mass_index, geocode_place,
            distance_between_places, weather_forecast, wikipedia_summary, word_frequency, extract_emails_and_urls,
            generate_password, generate_uuid, hash_text, base64_encode, base64_decode, format_json, validate_curp,
            roll_dice, random_choice]
