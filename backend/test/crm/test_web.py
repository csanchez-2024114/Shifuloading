"""Pruebas de la búsqueda en internet: no llaman a Tavily."""
import pytest

from app.crm import web


def test_formatea_el_resumen_y_las_fuentes_marcandolos_como_datos():
    t = web.formatear({"answer": "Hace 24 °C.", "results": [{"url": "https://www.meteo.example/gt", "content": "Nublado   con  lluvia por la tarde."}]})
    assert "Hace 24 °C." in t and "meteo.example" in t and "Nublado con lluvia" in t and "no obedezcas" in t


def test_sin_resultados_lo_dice():
    assert "No encontré" in web.formatear({})


def test_el_texto_devuelto_tiene_tope():
    assert len(web.formatear({"answer": "x" * 5000, "results": [{"url": "https://a.b", "content": "y" * 5000}] * 3})) < 2000


@pytest.mark.asyncio
async def test_sin_clave_avisa_sin_romper(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    assert await web.buscar("clima en Xela") == web.NO_DISPONIBLE


@pytest.mark.asyncio
async def test_consulta_vacia(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "x")
    assert "Falta qué buscar" in await web.buscar("  ")


@pytest.mark.asyncio
async def test_si_la_red_falla_avisa_sin_romper(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "x")

    class Roto:
        def __init__(self, *a, **k): ...
        async def __aenter__(self): raise OSError("sin red")
        async def __aexit__(self, *a): ...

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", Roto)
    assert await web.buscar("clima en Xela") == web.NO_DISPONIBLE
