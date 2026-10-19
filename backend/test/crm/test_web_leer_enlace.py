"""leer_enlace en web.py (port de chat.js): sin red real."""
import pytest

from app.crm import web


async def _fake_html(_url: str, _timeout: float, _headers: dict | None) -> tuple[int, str, bytes]:
    html = b"""<html><head><title>Spotify</title><meta name="theme-color" content="#121212">
    <style>#banner { color: #1db954; }</style></head><body><p>Music for everyone</p></body></html>"""
    return 200, "text/html", html


@pytest.mark.asyncio
async def test_enlace_publico_mide_colores():
    r = await web.leer_enlace("https://www.spotify.com", fetcher=_fake_html)
    assert "Spotify" in r["texto"] and "#1db954" in r["texto"] and "theme-color" in r["texto"]


@pytest.mark.asyncio
async def test_solo_https_publico():
    r = await web.leer_enlace("http://127.0.0.1/x")
    assert r["texto"] == "ERROR: solo se abren enlaces públicos https."


@pytest.mark.asyncio
async def test_figma_es_honesto():
    r = await web.leer_enlace("https://www.figma.com/file/abc")
    assert r["texto"].startswith("Figma no deja abrir")
