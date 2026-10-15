"""Herramientas extra del registro bigtool. Sin red: las de "mundo" usan respuestas simuladas."""
import pytest

from assistant import extra_tools as x


def run(t, **kw):
    return t.invoke(kw)


def test_conversiones():
    assert run(x.convert_units, value=100, from_unit="C", to_unit="F") == "100.0 C = 212 F"
    assert run(x.convert_units, value=0, from_unit="K", to_unit="C").endswith("-273.1 C")
    assert "1.60934 km" in run(x.convert_units, value=1, from_unit="mi", to_unit="km")
    assert run(x.convert_units, value=1, from_unit="kg", to_unit="km").startswith("Error")
    assert "2026-10-15 16:30" in run(x.convert_timezone, datetime_text="2026-10-15 08:30",
                                     from_timezone="America/Mexico_City", to_timezone="Europe/Madrid")


def test_fechas():
    assert run(x.days_between_dates, start_date="2026-01-01", end_date="2026-12-25").startswith("358 days")
    assert run(x.add_days_to_date, start_date="2026-10-15", days=30).startswith("2026-11-14")
    assert run(x.day_of_week, date_text="2026-10-15") == "Thursday"
    assert run(x.business_days_between, start_date="2026-10-12", end_date="2026-10-18").startswith("5 ")


def test_finanzas_y_datos():
    # mismas cifras verificadas antes con el préstamo de 350,000 al 14.5% a 5 años
    assert "monthly payment 8,234.90" in run(x.loan_payment, principal=350000, annual_rate_percent=14.5, years=5)
    assert "future value 3,784,057.69" in run(x.compound_interest, principal=0, annual_rate_percent=9, years=15,
                                              monthly_contribution=10000)
    assert run(x.percentage_change, old_value=80, new_value=100) == "+25.00%"
    assert "total 116.00" in run(x.add_sales_tax, amount=100)
    assert "subtotal 100.00" in run(x.add_sales_tax, amount=116, amount_includes_tax=True)
    assert "each person pays 27.50" in run(x.split_bill, total=100, people=4)
    assert "mean 3" in run(x.describe_numbers, numbers=[1, 2, 3, 4, 5])
    assert "y = 2*x + 1" in run(x.linear_regression, x_values=[1, 2, 3], y_values=[3, 5, 7])
    assert run(x.body_mass_index, weight_kg=70, height_m=1.75) == "BMI 22.9 (normal)"


def test_texto_y_utilidades():
    assert run(x.word_frequency, text="hola hola mundo") == "hola (2), mundo (1)"
    out = run(x.extract_emails_and_urls, text="escribe a ana@x.com o ve a https://a.mx/b.")
    assert "ana@x.com" in out and "https://a.mx/b." in out
    assert len(run(x.generate_password, length=20)) == 20
    assert run(x.hash_text, text="abc").startswith("ba7816bf")
    assert run(x.base64_decode, encoded=run(x.base64_encode, text="café")) == "café"
    assert run(x.format_json, json_text="{bad").startswith("Invalid JSON")
    assert run(x.validate_curp, curp="GORS800101HDFNML09").startswith(("Valid", "Invalid check digit"))
    assert run(x.validate_curp, curp="NOVALIDA").startswith("Invalid CURP")
    assert run(x.random_choice, options=["a"]) == "a"


@pytest.fixture
def fake_api(monkeypatch):
    def fake(url, params=None):
        if "geocoding" in url:
            places = {"Monterrey": (25.68, -100.32), "Guadalajara": (20.67, -103.39)}
            lat, lon = places[params["name"]]
            return {"results": [{"name": params["name"], "country": "México", "latitude": lat, "longitude": lon}]}
        if "frankfurter" in url:
            return {"date": "2026-10-14", "rates": {params["to"]: 18.0}}
        if "open-meteo" in url:
            return {"current": {"temperature_2m": 24, "relative_humidity_2m": 50, "wind_speed_10m": 10, "weather_code": 0},
                    "daily": {"time": ["2026-10-15"], "temperature_2m_min": [17], "temperature_2m_max": [29],
                              "precipitation_probability_max": [10], "weather_code": [1]}}
        raise AssertionError(url)

    monkeypatch.setattr(x, "_get_json", fake)


def test_mundo_con_api_simulada(fake_api):
    assert run(x.convert_currency, amount=250, from_currency="usd", to_currency="mxn").startswith("250.00 USD = 4,500.00 MXN")
    assert "24°C, clear" in run(x.weather_forecast, place="Monterrey")
    km = run(x.distance_between_places, place_a="Monterrey", place_b="Guadalajara")
    assert "km in a straight line" in km and 600 < int(km.split(": ")[1].split(" km")[0].replace(",", "")) < 750
