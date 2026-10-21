"""El historial con lo que de verdad corrió (hechos del turno), con modelo simulado: no llama a OpenAI.
banco_descarga (20-oct): con solo el texto de las respuestas viejas, el modelo las imitaba («Ya preparé el Excel…») sin llamar a la
herramienta. Ahora cada respuesta de Shifu guarda sus hechos y el historial los vuelve a poner como llamadas a herramientas."""
import pytest

pytest.importorskip("langchain_core")
from langchain_core.messages import AIMessage, ToolMessage  # noqa: E402

from test_agente_diseno import AHORA, H, URL, _con_modelo, cli, correr, db, dice, doc, llamar  # noqa: E402,F401

from assistant.packs.crm import agente, memoria  # noqa: E402


@pytest.fixture(autouse=True)
def con_diseno(monkeypatch):
    monkeypatch.setenv("CRM_DISENO", "1")
    monkeypatch.setattr(agente, "_pausa_hasta", 0.0)


@pytest.mark.asyncio
async def test_el_turno_devuelve_sus_hechos_cortos(doc):
    r, _ = await correr(doc, "¿cuántos contactos tengo?", dice("", llamar("consultar_datos", seccion="contactos")), dice("Tienes 3."))
    assert r["hechos"] == [{"herramienta": "consultar_datos", "args": {"seccion": "contactos"}, "resultado": r["consultas"][0]["resultado"][:200]}]


def test_el_historial_pone_los_hechos_como_llamadas_reales(doc):
    hist = [{"de": "yo", "t": "pásame el excel"},
            {"de": "shifu", "t": "Listo, tu Excel.", "h": [{"herramienta": "descargar", "args": {"formato": "excel"}, "resultado": "Listo: el archivo…"}]}]
    msgs = agente._mensajes(doc, "otra vez", hist, AHORA, False)
    llamada, resultado, texto = msgs[2], msgs[3], msgs[4]
    assert isinstance(llamada, AIMessage) and llamada.tool_calls[0]["name"] == "descargar" and llamada.tool_calls[0]["args"] == {"formato": "excel"}
    assert isinstance(resultado, ToolMessage) and resultado.tool_call_id == llamada.tool_calls[0]["id"]
    assert isinstance(texto, AIMessage) and texto.content == "Listo, tu Excel."


def test_apagado_el_historial_es_el_de_siempre(doc, monkeypatch):
    monkeypatch.setenv("CRM_HISTORIAL_HECHOS", "0")
    hist = [{"de": "yo", "t": "hola"}, {"de": "shifu", "t": "Listo.", "h": [{"herramienta": "descargar", "args": {}, "resultado": "x"}]}]
    msgs = agente._mensajes(doc, "otra", hist, AHORA, False)
    assert not any(isinstance(m, ToolMessage) for m in msgs) and msgs[2].content == "Listo."


def test_la_ruta_guarda_los_hechos_y_el_siguiente_turno_los_ve(cli, monkeypatch):
    modelo = _con_modelo(monkeypatch, dice("", llamar("descargar", formato="respaldo")), dice("Listo, tu respaldo."), dice("¡Hola!"))
    cli.post(f"{URL}/chat", json={"texto": "hazme un respaldo"}, headers=H)
    cli.post(f"{URL}/chat", json={"texto": "hola"}, headers=H)
    vistos = modelo.recibidos[-1]
    assert any(isinstance(m, AIMessage) and m.tool_calls and m.tool_calls[0]["name"] == "descargar" for m in vistos)
    assert sum(isinstance(m, ToolMessage) for m in vistos) == 1


def test_historial_para_modelo_conserva_los_hechos():
    conv = {"mensajes": [{"de": "yo", "t": "a", "n": 1}, {"de": "shifu", "t": "b", "n": 2, "h": [{"herramienta": "x", "args": {}, "resultado": ""}]}]}
    assert memoria.historial_para_modelo(conv)[1]["h"][0]["herramienta"] == "x"
