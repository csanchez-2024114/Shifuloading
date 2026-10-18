"""Tests de caracterización: fijan el comportamiento ACTUAL (antes del refactor núcleo/perfiles) de lo que no tenía
test propio. No juzgan si el comportamiento es bueno: si uno falla tras el refactor, algo cambió.

La huella (tests/snapshots/perfil_por_defecto.json) guarda lo que define al perfil por defecto: variables de entorno
y defaults, herramientas (nombres, descripciones y argumentos), prompt del sistema, grafo, rutas HTTP, textos y
reglas (constantes y regex), la UI y los eventos SSE de escenarios fijos. Para regenerarla A PROPÓSITO:
    set UPDATE_SNAPSHOTS=1 && .venv\\Scripts\\python -m pytest tests/test_caracterizacion.py -k huella
"""
import hashlib
import json
import math
import os
import re
import sys
import types as pytypes
from collections import OrderedDict
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.errors import GraphRecursionError
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command

from conftest import _settings, build_test_agent, fake_llm, run_turn, tool_call, types, uid

SNAPSHOT = Path(__file__).parent / "snapshots" / "perfil_por_defecto.json"
ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- huella del perfil por defecto


def _ser(value):
    """Valor serializable de una constante, o None si no lo es (funciones, clases...)."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, re.Pattern):
        return {"pattern": value.pattern, "flags": int(value.flags)}
    if isinstance(value, (tuple, list)):
        items = [_ser(v) for v in value]
        return None if any(i is None and v is not None for i, v in zip(items, value)) else items
    if isinstance(value, (set, frozenset)):
        items = [_ser(v) for v in value]
        return None if any(i is None for i in items) else sorted(items, key=repr)
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            s = _ser(v)
            if s is None and v is not None:
                return None
            out[str(k)] = s
        return out
    return None


CONST_MODULES = ("agent", "tools", "memory", "context", "citations", "auth", "bigtool_agent", "extra_tools",
                 "tool_spec", "config", "appdata", "server")


def _constants() -> dict:
    """Constantes de módulo en MAYÚSCULAS (textos al usuario y al modelo, regex, topes)."""
    import importlib

    out = {}
    for name in CONST_MODULES:
        mod = importlib.import_module(f"assistant.{name}")
        for attr, value in sorted(vars(mod).items()):
            if not re.fullmatch(r"_?[A-Z][A-Z0-9_]*", attr) or isinstance(value, pytypes.ModuleType):
                continue
            if attr in ("ROOT", "_TURNS", "_ACTIVE_TURNS", "_PAUSED_SPEND"):  # ruta de la máquina y estado en vivo
                continue
            s = _ser(value)
            if s is not None:
                out[f"{name}.{attr}"] = s
    return out


class _EnvSpy(dict):
    """os.environ vacío que anota qué variables se leen."""

    def __init__(self, base):
        super().__init__(base)
        self.read = set()

    def get(self, key, default=None):
        self.read.add(key)
        return super().get(key, default)

    def __getitem__(self, key):
        self.read.add(key)
        return super().__getitem__(key)


def _env_and_defaults(monkeypatch) -> dict:
    from dataclasses import asdict

    from assistant.config import Settings

    spy = _EnvSpy({})
    with monkeypatch.context() as m:  # solo durante from_env: lo demás ve el entorno normal
        m.setattr(os, "environ", spy)
        defaults = asdict(Settings.from_env())
    return {"env_vars": sorted(spy.read), "defaults": defaults}


def _tool_info(tools) -> list:
    return [{"name": t.name, "description": t.description, "args": _ser(json.loads(json.dumps(t.args, default=str)))}
            for t in tools]


def _graph(agent) -> dict:
    g = agent.get_graph()
    return {"nodes": list(g.nodes), "edges": sorted([e.source, e.target, bool(e.conditional)] for e in g.edges)}


def _masked_prompt(text: str) -> str:
    return re.sub(r"User's current local date and time: .*?\(UTC[+-]\d{4}\)\.", "User's current local date and time: "
                  "<DATE> (UTC<TZ>).", text)


def _scenario_events(settings, responses, text, resume=None) -> list:
    from assistant.agent import stream_events

    agent = build_test_agent(responses, settings, checkpointer=InMemorySaver())
    thread = "hilo-fijo"
    events = run_turn(agent, settings, text, thread)
    if resume is not None:
        events += list(stream_events(agent, Command(resume=resume), thread, "u1", settings))
    return [{**e, "id": "<id>"} if e["type"] == "interrupt" else e for e in events]  # id aleatorio


def _huella(monkeypatch) -> dict:
    from assistant import agent as agent_mod
    from assistant import bigtool_agent, memory, server, tools

    s = _settings()
    every = _settings(enable_hitl_demo=True, memory_summarize=True, answer_verify=True, compact_prune_tools=True,
                      memory_verify=True, memory_save_policy="broad", memory_search_economy=True)
    llm = fake_llm("x")
    registry = bigtool_agent.build_registry(llm, s, None)
    registry_demo = bigtool_agent.build_registry(llm, _settings(bigtool_demo_tools=True), None)
    app = server.create_app(agent=build_test_agent(["x"], s, checkpointer=InMemorySaver()), settings=s,
                            store=InMemoryStore())
    huella = {
        "config": _env_and_defaults(monkeypatch),
        "tools_default": _tool_info(tools.build_tools(llm, s)),
        "tools_all_flags": _tool_info(tools.build_tools(llm, every)),
        "system_prompt_default": _masked_prompt(agent_mod.system_prompt_text(s)),
        "system_prompt_all_flags": _masked_prompt(agent_mod.system_prompt_text(every)),
        "memory_policies": {f"{p}|{n}|{e}": memory.memory_policy(p, n, e)
                            for p in ("strict", "broad", "otra") for n in (0, 3) for e in (False, True)},
        "graph_default": _graph(build_test_agent(["x"], s)),
        "graph_all_flags": _graph(build_test_agent(["x"], every)),
        "routes": sorted([r.path, sorted(getattr(r, "methods", None) or [])] for r in app.routes),
        "bigtool_registry": sorted(registry),
        "bigtool_registry_demo": sorted(registry_demo),
        "bigtool_index_docs": {k: bigtool_agent._index_document(t) for k, t in sorted(registry_demo.items())},
        "bigtool_prompt": bigtool_agent.BIGTOOL_PROMPT,
        "index_html_sha256": hashlib.sha256((ROOT / "static" / "index.html").read_bytes()).hexdigest(),
        "system_md_sha256": hashlib.sha256((ROOT / "prompts" / "system.md").read_bytes()).hexdigest(),
        "constants": _constants(),
        "sse": {
            "plain": _scenario_events(s, ["Hola, ¿qué tal?"], "hola"),
            "web_search": _scenario_events(s, [tool_call("web_search", {"query": "clima"}), "Hace sol."], "clima hoy"),
            "hitl_approve": _scenario_events(
                _settings(enable_hitl_demo=True),
                [tool_call("send_simulated_email", {"recipient": "a@b.com", "subject": "S", "body": "B"}), "Enviado."],
                "manda un correo", resume={"decisions": [{"type": "approve"}]}),
            "research_rejected": _scenario_events(
                s, [tool_call("deep_research", {"task": "algo"}), "Sin investigar."], "dame un plan",
                resume={"decisions": [{"type": "reject"}]}),
        },
    }
    return json.loads(json.dumps(huella, ensure_ascii=False, default=str))


def test_huella_del_perfil_por_defecto(monkeypatch):
    update = os.getenv("UPDATE_SNAPSHOTS") == "1"
    actual = _huella(monkeypatch)
    if update or not SNAPSHOT.exists():
        SNAPSHOT.parent.mkdir(exist_ok=True)
        SNAPSHOT.write_text(json.dumps(actual, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        if not update:
            pytest.fail("No había huella: se generó; revísala y vuelve a correr")
    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    for key in sorted(set(expected) | set(actual)):  # una sección a la vez: el diff se lee mejor
        assert actual.get(key) == expected.get(key), f"la huella cambió en '{key}'"


# --------------------------------------------------------------------------- esfuerzo


class _FakeOpenAI:
    """Sustituto de ChatOpenAI: anota los kwargs y responde `reply` (o lanza si es una excepción)."""
    created: list = []
    reply = "medium"

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        _FakeOpenAI.created.append(self)
        self.bound = None

    def invoke(self, prompt, **_):
        self.prompt = prompt
        if isinstance(self.reply, Exception):
            raise self.reply
        return pytypes.SimpleNamespace(text=self.reply)

    def bind_tools(self, tools, **kwargs):
        self.bound = (tools, kwargs)
        return self


@pytest.fixture
def fake_openai(monkeypatch):
    from assistant import agent as agent_mod
    from assistant import tools

    _FakeOpenAI.created = []
    monkeypatch.setattr(agent_mod, "ChatOpenAI", _FakeOpenAI)
    monkeypatch.setattr(tools, "ChatOpenAI", _FakeOpenAI)
    return _FakeOpenAI


@pytest.mark.parametrize("reply,nivel", [("low", "bajo"), ("Medium.", "medio"), ("HIGH", "alto"),
                                         ("no sé", "medio"), ("", "medio")])
def test_clasificador_mapea_la_respuesta_y_cae_a_medio(fake_openai, reply, nivel):
    from assistant.agent import CLASSIFIER_PROMPT, clasificar_esfuerzo

    fake_openai.reply = reply
    assert clasificar_esfuerzo(_settings(), "x" * 3000) == nivel
    llm = fake_openai.created[-1]
    assert llm.kwargs["reasoning"] == {"effort": "none"} and llm.kwargs["max_tokens"] == 16
    assert llm.kwargs["use_responses_api"] is True
    assert llm.prompt == CLASSIFIER_PROMPT + "x" * 2000  # el mensaje se corta a 2000 caracteres


def test_clasificador_con_error_devuelve_medio(fake_openai):
    from assistant.agent import clasificar_esfuerzo

    fake_openai.reply = RuntimeError("sin red")
    assert clasificar_esfuerzo(_settings(), "compara tres bancos") == "medio"


def test_contexto_por_esfuerzo():
    from assistant.agent import ESFUERZOS, Context, contexto_para

    assert ESFUERZOS == {"bajo": (5, "low"), "medio": (15, "medium"), "alto": (15, "high")}
    s = _settings(model_call_limit=0, max_tokens=8000, effort_high_max_calls=9, effort_high_max_tokens=12000)
    assert contexto_para("u", s, "bajo") == Context("u", 5, "low", None)
    assert contexto_para("u", s, "medio") == Context("u", 15, "medium", None)
    assert contexto_para("u", s, "alto") == Context("u", 9, "high", 12000)
    assert contexto_para("u", s, None) == Context("u", 15, None, None)
    # MAX_TOKENS=0 (sin tope) o mayor que el de esfuerzo alto: no se toca
    assert contexto_para("u", _settings(model_call_limit=0, max_tokens=0), "alto").max_tokens is None
    assert contexto_para("u", _settings(model_call_limit=0, max_tokens=20000), "alto").max_tokens is None
    # tope fijo
    assert contexto_para("u", _settings(model_call_limit=7), "alto") == Context("u", 7, None, None)


@pytest.mark.parametrize("texto,necesita", [
    ("hola", False), ("gracias!", False), ("¿cómo estás?", False), ("buenos días", False),
    ("cuánto es 2+2", True), ("¿quién ganó ayer?", True), ("el último partido", True), ("dame un plan", True),
    ("```print(1)```", True), ("escribe código", True), ("compare these", True), ("x" * 61, True),
])
def test_regla_de_mensaje_corto(texto, necesita):
    from assistant.agent import necesita_clasificador

    assert necesita_clasificador(texto) is necesita


# --------------------------------------------------------------------------- modelos


def test_parametros_de_los_modelos():
    from assistant.agent import make_checker_model, make_model, make_summary_model

    s = _settings(max_tokens=8000, compact_model="")
    m = make_model(s)
    assert (m.model_name, m.use_responses_api, m.max_tokens, m.streaming) == ("gpt-6-luna", True, 8000, True)
    assert make_model(_settings(max_tokens=0)).max_tokens is None
    c = make_checker_model(s)
    assert (c.reasoning, c.tags, c.use_responses_api) == ({"effort": "none"}, ["nostream"], True)
    r = make_summary_model(s)
    assert (r.model_name, r.reasoning, r.tags) == ("gpt-6-luna", {"effort": "low"}, ["nostream"])
    assert make_summary_model(_settings(compact_model="otro")).model_name == "otro"


def test_prompt_del_sistema_lleva_archivo_politica_y_fecha():
    from assistant.agent import system_prompt_text
    from assistant.config import read_system_prompt
    from assistant.memory import memory_policy

    text = system_prompt_text(_settings())
    assert text.startswith(read_system_prompt())
    assert memory_policy("strict", 3, False) in text
    assert re.search(r"User's current local date and time: \w+ \d{4}-\d\d-\d\d \d\d:\d\d \(UTC[+-]\d{4}\)\. "
                     r"Treat it as 'today'; never infer the date from search results\.$", text)


# --------------------------------------------------------------------------- errores del stream


class _AgenteQueFalla:
    def __init__(self, exc):
        self.exc = exc

    def stream(self, *args, **kwargs):
        raise self.exc


def test_stream_con_recursion_excedida_da_error_legible_sin_done():
    from assistant.agent import stream_events

    s = _settings(recursion_limit=25)
    ev = list(stream_events(_AgenteQueFalla(GraphRecursionError()), {"messages": []}, "t", "u", s))
    assert ev == [{"type": "error", "message": "Me detuve: la tarea superó 25 pasos internos. Pídeme que continúe o "
                                              "sube RECURSION_LIMIT en .env."}]


def test_stream_con_excepcion_da_tipo_y_mensaje_sin_done():
    from assistant import agent as agent_mod

    ev = list(agent_mod.stream_events(_AgenteQueFalla(RuntimeError("boom")), {"messages": []}, "t", "u", _settings()))
    assert ev == [{"type": "error", "message": "RuntimeError: boom"}]
    assert "t" not in agent_mod._ACTIVE_TURNS  # el contador del turno se limpia


def test_evento_effort_va_primero_con_esfuerzo():
    from assistant.agent import stream_events

    s = _settings(model_call_limit=0)
    agent = build_test_agent(["hola"], s, checkpointer=InMemorySaver())
    ev = list(stream_events(agent, {"messages": [{"role": "user", "content": "hola"}]}, uid(), "u", s, "bajo",
                            "regla"))
    assert ev[0] == {"type": "effort", "level": "bajo", "max_calls": 5, "reasoning": "low", "source": "regla"}
    assert ev[-1]["type"] == "done"


def test_gasto_del_turno_pausado_se_guarda_y_se_retoma_en_resume():
    from assistant import agent as agent_mod

    s = _settings(enable_hitl_demo=True)
    agent = build_test_agent(
        [tool_call("send_simulated_email", {"recipient": "a@b.com", "subject": "S", "body": "B"}), "Listo"], s,
        checkpointer=InMemorySaver())
    thread = uid()
    run_turn(agent, s, "manda un correo", thread)
    assert thread in agent_mod._PAUSED_SPEND
    list(agent_mod.stream_events(agent, Command(resume={"decisions": [{"type": "approve"}]}), thread, "u1", s))
    assert thread not in agent_mod._PAUSED_SPEND
    assert agent.get_state(agent_mod.run_config(thread, s)).values["context_stats"]["turns"] == 1


# --------------------------------------------------------------------------- servidor


def test_compactar_con_aprobacion_pendiente_responde_409():
    from assistant.server import create_app

    class ConPausa:
        compactor = object()

        def get_state(self, config):
            return pytypes.SimpleNamespace(values={"messages": []}, interrupts=("pendiente",))

    client = TestClient(create_app(agent=ConPausa(), settings=_settings(), store=InMemoryStore()))
    r = client.post("/threads/x/compact")
    assert r.status_code == 409 and r.json()["detail"] == "La conversación espera una aprobación"


def test_keepalive_reenvia_la_excepcion_del_productor():
    from assistant.server import with_keepalive

    def eventos():
        yield "a"
        raise ValueError("fallo")

    gen = with_keepalive(eventos(), 5)
    assert next(gen) == "a"
    with pytest.raises(ValueError, match="fallo"):
        next(gen)
    assert list(with_keepalive(iter(["x", "y"]), 0)) == ["x", "y"]  # 0 = sin keepalive


# --------------------------------------------------------------------------- búsqueda web


def test_web_search_hospedado_y_respaldo_duckduckgo(fake_openai, monkeypatch):
    from assistant import tools

    calls = []
    monkeypatch.setattr(tools, "_ddg_search", lambda q: calls.append(q) or "ddg: " + q)
    s = _settings(search_context_size="low", search_max_tool_calls=1)

    fake_openai.reply = "texto con fuentes"
    assert tools.web_search("clima", s) == ("texto con fuentes", "openai_web_search")
    llm = fake_openai.created[-1]
    assert llm.kwargs["tags"] == ["nostream"] and llm.kwargs["use_responses_api"] is True
    assert llm.bound == ([{"type": "web_search", "search_context_size": "low"}], {"max_tool_calls": 1})
    tools.web_search("clima", _settings(search_max_tool_calls=0))
    assert fake_openai.created[-1].bound[1] == {}  # 0 = sin max_tool_calls

    fake_openai.reply = "   "  # respuesta vacía cuenta como fallo
    assert tools.web_search("vacío", s) == ("ddg: vacío", "duckduckgo")
    fake_openai.reply = RuntimeError("caído")
    assert tools.web_search("caído", s) == ("ddg: caído", "duckduckgo")
    assert calls == ["vacío", "caído"]


def test_formato_de_duckduckgo(monkeypatch):
    from assistant import tools

    class DDGS:
        results = [{"title": "T1", "href": "https://a.com", "body": "B1"}, {"title": "T2", "href": "https://b.com"}]

        def text(self, query, max_results):
            assert max_results == 5
            return self.results

    monkeypatch.setitem(sys.modules, "ddgs", pytypes.SimpleNamespace(DDGS=DDGS))
    assert tools._ddg_search("q") == "T1\nhttps://a.com\nB1\n\nT2\nhttps://b.com\n"
    DDGS.results = []
    assert tools._ddg_search("q") == "No results."


def test_presupuesto_de_busqueda_olvida_los_turnos_mas_viejos(monkeypatch):
    from assistant import tools

    monkeypatch.setattr(tools, "_TURNS", OrderedDict())
    first = tools.turn_budget(("h", 0))
    for i in range(1, 300):
        tools.turn_budget(("h", i))
    assert len(tools._TURNS) == 256 and ("h", 0) not in tools._TURNS
    assert tools.turn_budget(None) is None and tools.turn_budget(("h", 299)) is tools.turn_budget(("h", 299))
    assert first.tokens == 0 and first.searches == 0


# --------------------------------------------------------------------------- reglas de intención (regex)


@pytest.mark.parametrize("texto,continua", [
    ("continúa", True), ("Continua por favor", True), ("sigue", True), ("seguí", True), ("dale", True),
    ("continue", True), ("go on", True), ("keep going", True), ("...sigue", True),
    ("hola", False), ("¿y luego qué?", False), ("puedes continuar", False),
])
def test_regex_de_continuar(texto, continua):
    from assistant.agent import _CONTINUE_RE

    assert bool(_CONTINUE_RE.match(texto)) is continua


def _hilo(*textos_y_herramientas):
    msgs = []
    for item in textos_y_herramientas:
        if isinstance(item, str):
            msgs.append(HumanMessage(item, id=uid("h")))
        else:
            msgs.append(ToolMessage(item[1], tool_call_id=uid("c"), name=item[0]))
    return msgs


@pytest.mark.parametrize("texto,confirmar", [
    ("dame un plan de viaje", True), ("¿qué bancos hay?", True), ("investiga los bancos", False),
    ("a fondo, por favor", False), ("en profundidad", False), ("research banks", False), ("in-depth review", False),
    ("haz algo exhaustivo", False), ("Investigación completa", False),
])
def test_cuando_deep_research_pide_confirmacion(texto, confirmar):
    from assistant.tools import research_needs_confirmation

    assert research_needs_confirmation(_hilo(texto)) is confirmar


def test_seguimiento_breve_reutiliza_la_investigacion_anterior():
    from assistant.tools import earlier_research, research_needs_confirmation

    previo = ("deep_research", "Resultados: A, B, C")
    assert earlier_research(_hilo("investiga bancos", previo, "¿y cuál es mejor?")) == "Resultados: A, B, C"
    assert research_needs_confirmation(_hilo("investiga bancos", previo, "¿y cuál es mejor?")) is False
    for nuevo in ("busca de nuevo", "otra vez", "actualiza eso", "search again", "look it up", "x" * 201):
        assert earlier_research(_hilo("investiga bancos", previo, nuevo)) is None
    assert earlier_research(_hilo("investiga", ("deep_research", "Not run: rechazada"), "¿y?")) is None
    assert earlier_research(_hilo("investiga", ("investigador_profundo", "viejo"), "¿y?")) == "viejo"
    assert earlier_research(_hilo("¿y?")) is None


# --------------------------------------------------------------------------- herramientas base


@pytest.mark.parametrize("expr,out", [
    ("10/4", "2.5"), ("4/2", "2"), ("7//2", "3"), ("7%3", "1"), ("-3", "-3"), ("factorial(5)", "120"),
    ("max(1, 9, 3)", "9"), ("abs(-2)", "2"), ("round(2.567, 2)", "2.57"), ("math.pi", str(math.pi)),
    ("tau", str(math.tau)), ("1e16/1", "1e+16"), ("gcd(12, 18)", "6"),
    ("1/0", "Error: division by zero."), ("2**20000", "Error: exponent too large"),
    ("math.foo", "Error: constant not allowed: math.foo"), ("__import__('os')", "Error: expression not allowed"),
    ("True + 1", "Error: expression not allowed"), ("round(x=1)", "Error: expression not allowed"),
    ("2 +", "Error: invalid expression: '2 +'"), ("sqrt(-1)", "Error: math domain error"),
])
def test_calculadora_caracterizada(expr, out):
    from assistant.tools import calculadora

    assert calculadora.invoke({"expression": expr}) == out


def test_fecha_hora_con_zonas():
    from assistant.tools import fecha_hora

    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00 \(\w+\)", fecha_hora.invoke({"time_zone": "utc"}))
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d \(\w+\)",
                        fecha_hora.invoke({"time_zone": "America/Mexico_City"}))
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d \(\w+\)", fecha_hora.invoke({"time_zone": ""}))
    assert fecha_hora.invoke({"time_zone": "Marte/Base"}) == (
        "Error: unknown or unavailable time zone: 'Marte/Base'. Use an IANA name such as 'America/Mexico_City'.")


def test_email_simulado_no_envia_nada():
    from assistant.tools import enviar_email_simulado

    assert enviar_email_simulado.invoke({"recipient": "a@b.com", "subject": "Hola", "body": "12345"}) == (
        "Simulated email sent to a@b.com with subject 'Hola' (5 characters).")


def test_herramientas_por_defecto_y_con_demo_hitl():
    from assistant.tools import build_tools

    nombres = [t.name for t in build_tools(fake_llm("x"), _settings())]
    assert nombres == ["web_search", "calculator", "current_datetime", "check_python_syntax", "save_memory",
                       "search_memories", "update_memory", "deep_research"]
    assert [t.name for t in build_tools(fake_llm("x"), _settings(enable_hitl_demo=True))][-1] == "send_simulated_email"
