"""Punto 46: trazas de los turnos del chat (CRM_TRAZA=1 → JSONL por día en una carpeta configurable). Sin OpenAI."""
import json
from datetime import datetime, timezone

import pytest

pytest.importorskip("langchain_core")
from langchain_core.messages import AIMessage  # noqa: E402

from app.crm import agente, traza  # noqa: E402
from app.crm import operaciones as op  # noqa: E402
from app.crm.generador import generar  # noqa: E402

AHORA = datetime(2026, 10, 13, 15, 0, tzinfo=timezone.utc)
BRIEF = {"nombre": "Clínica Sol", "rubro": "salud", "equipo": "chico", "canales": ["whatsapp"], "objetivos": ["seguimientos"]}


class Modelo:
    def __init__(self, *guion):
        self.guion = list(guion)

    def bind_tools(self, herramientas, **kw):
        return self

    async def ainvoke(self, mensajes):
        r = self.guion.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def dice(texto="", *llamadas):
    return AIMessage(content=texto, tool_calls=list(llamadas))


@pytest.fixture(autouse=True)
def con_diseno(monkeypatch):
    monkeypatch.setenv("CRM_DISENO", "1")
    monkeypatch.setattr(agente, "_pausa_hasta", 0.0)


@pytest.fixture
def doc():
    d = generar("u1", BRIEF, AHORA)
    return op.contactos_crear(d, [{"n": "Ana Morales"}], "WhatsApp", ahora=AHORA)


def _lineas(carpeta):
    archivos = sorted(carpeta.glob("*.jsonl"))
    return archivos, [json.loads(l) for a in archivos for l in a.read_text(encoding="utf-8").splitlines()]


@pytest.mark.asyncio
async def test_sin_variable_no_escribe_nada(doc, tmp_path, monkeypatch):
    monkeypatch.delenv("CRM_TRAZA", raising=False)
    monkeypatch.setenv("CRM_TRAZA_DIR", str(tmp_path))
    r = await agente.responder(doc, "hola", [], AHORA, modelo=Modelo(dice("¡Hola! ¿En qué te ayudo?")))
    assert r["respuesta"]
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_turno_con_herramienta_queda_en_el_archivo_del_dia(doc, tmp_path, monkeypatch):
    monkeypatch.setenv("CRM_TRAZA", "1")
    monkeypatch.setenv("CRM_TRAZA_DIR", str(tmp_path / "trazas"))
    modelo = Modelo(dice("", {"name": "agregar_contactos", "args": {"contactos": [{"nombre": "Pedro Castillo"}]}, "id": "t1"}),
                    dice("Listo, agregué a Pedro Castillo."))
    r = await agente.responder(doc, "agrega a Pedro Castillo, mi clave es sk-abcdefghijklmnopqrstuvwx", [{"rol": "usuario", "texto": "x"}], AHORA,
                               modelo=modelo, seccion="contactos", adjunto="contenido largo del archivo")
    archivos, lineas = _lineas(tmp_path / "trazas")
    assert len(lineas) == 1 and archivos[0].name == f"{datetime.now(timezone.utc).date().isoformat()}.jsonl"
    t = lineas[0]
    assert "Pedro Castillo" in t["texto"] and "sk-abc" not in t["texto"] and "[oculto]" in t["texto"]
    assert t["respuesta"] == r["respuesta"] and t["modo"] == "ia"
    assert [p["tipo"] for p in t["pasos"]] == ["modelo", "herramienta", "modelo"]
    assert t["pasos"][0]["pidio"] == ["agregar_contactos"]
    herr = t["pasos"][1]
    assert herr["nombre"] == "agregar_contactos" and "Pedro Castillo" in herr["args"] and herr["resultado"]
    assert all(isinstance(p["ms"], int) and p["ms"] >= 0 for p in t["pasos"]) and t["ms_total"] >= 0
    assert [c["herramienta"] for c in t["cambios"]] == ["agregar_contactos"]
    # Sin el documento, sin el adjunto (solo su largo), sin el historial (solo cuántos)
    crudo = json.dumps(t, ensure_ascii=False)
    assert "contactos\": [{\"id\"" not in crudo and "contenido largo" not in crudo and "Ana Morales" not in crudo
    assert t["adjunto_largo"] == len("contenido largo del archivo") and t["historial_mensajes"] == 1
    assert t["seccion"] == "contactos" and t["negocio"] == "Clínica Sol"


@pytest.mark.asyncio
async def test_aviso_del_codigo_queda_en_la_traza(doc, tmp_path, monkeypatch):
    monkeypatch.setenv("CRM_TRAZA", "1")
    monkeypatch.setenv("CRM_TRAZA_DIR", str(tmp_path))
    # Dice que agregó sin haber llamado ninguna herramienta: el código lo corrige y queda el aviso.
    modelo = Modelo(dice("Listo, agregué a Pedro Castillo."), dice("Todavía no lo agregué. ¿Me confirmas su nombre?"))
    r = await agente.responder(doc, "agrega a Pedro Castillo", [], AHORA, modelo=modelo)
    _, lineas = _lineas(tmp_path)
    assert lineas[0]["avisos"] == r["avisos"] and r["avisos"]
    assert [p["tipo"] for p in lineas[0]["pasos"]] == ["modelo", "modelo"]


@pytest.mark.asyncio
async def test_si_el_modelo_falla_queda_el_error_y_la_excepcion_sigue(doc, tmp_path, monkeypatch):
    monkeypatch.setenv("CRM_TRAZA", "1")
    monkeypatch.setenv("CRM_TRAZA_DIR", str(tmp_path))
    with pytest.raises(TimeoutError):
        await agente.responder(doc, "hola", [], AHORA, modelo=Modelo(TimeoutError("lento")))
    _, lineas = _lineas(tmp_path)
    assert lineas[0]["error"] == "TimeoutError" and "respuesta" not in lineas[0]


@pytest.mark.asyncio
async def test_si_no_se_puede_escribir_la_persona_recibe_su_respuesta(doc, tmp_path, monkeypatch):
    bloqueo = tmp_path / "archivo"
    bloqueo.write_text("no soy carpeta")
    monkeypatch.setenv("CRM_TRAZA", "1")
    monkeypatch.setenv("CRM_TRAZA_DIR", str(bloqueo / "sub"))
    r = await agente.responder(doc, "hola", [], AHORA, modelo=Modelo(dice("¡Hola! ¿En qué te ayudo?")))
    assert r["respuesta"] == "¡Hola! ¿En qué te ayudo?"


def test_carpeta_por_defecto_en_el_proyecto_e_ignorada_por_git(monkeypatch):
    monkeypatch.delenv("CRM_TRAZA_DIR", raising=False)
    assert traza.carpeta().name == "trazas_chat" and traza.carpeta().parent.name == "backend"
    raiz = traza.carpeta().parent.parent
    assert "backend/trazas_chat/" in (raiz / ".gitignore").read_text(encoding="utf-8")


def test_recorta_y_tapa_claves():
    assert traza._limpio("Bearer abcdefghijklmnop123", 100) == "[oculto]"
    assert traza._limpio("eyJhbGciOiJIUzI1.eyJzdWIiOiIxMjM0.SflKxwRJSMeKKF2Q", 100) == "[oculto]"
    assert traza._limpio("x" * 30, 10) == "x" * 10 + "…(+20)"
