"""Herramientas renombradas a inglés: los hilos guardados con los nombres antiguos (en español) se siguen cargando y
respondiendo, y en bigtool los ids guardados que ya no existen se ignoran. Sin tokens: modelos falsos."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from langchain_core.embeddings.fake import DeterministicFakeEmbedding
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from conftest import FakeChat, FakeSearch, run_turn, uid

ROOT = Path(__file__).resolve().parents[1]

HILO_VIEJO = [
    HumanMessage("¿Cuánto es 2+2? Y busca langgraph", id="h1"),
    AIMessage(content="", id="a1", tool_calls=[
        {"name": "calculadora", "args": {"expresion": "2+2"}, "id": "c1"},
        {"name": "buscar_web", "args": {"consulta": "langgraph"}, "id": "w1"}]),
    ToolMessage("4", tool_call_id="c1", name="calculadora", id="t1"),
    ToolMessage("[motor: duckduckgo]\nLangGraph es...", tool_call_id="w1", name="buscar_web", id="t2"),
    AIMessage(content="Son 4 y LangGraph es una librería.", id="a2"),
]


class Espia(FakeChat):
    """Guarda los nombres de herramientas que ve el modelo en el historial y las que recibe enlazadas."""
    vistos: list = []
    enlazadas: list = []

    def bind_tools(self, tools, **kwargs):
        self.enlazadas.append(sorted(getattr(t, "name", str(t)) for t in tools))
        return self

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        for m in messages:
            self.vistos += [c["name"] for c in getattr(m, "tool_calls", [])]
            if m.type == "tool":
                self.vistos.append(m.name)
        yield from super()._stream(messages, stop=stop, run_manager=run_manager, **kwargs)

    _generate_orig = FakeChat._generate

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        for m in messages:
            self.vistos += [c["name"] for c in getattr(m, "tool_calls", [])]
            if m.type == "tool":
                self.vistos.append(m.name)
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


def test_hilo_con_nombres_antiguos_se_carga_y_responde(settings):
    from assistant.agent import build_agent, get_history
    from assistant.tools import build_tools

    llm = Espia(messages=iter(["Sigo aquí."]), vistos=[], enlazadas=[])
    agent = build_agent(llm, build_tools(llm, settings, search_fn=FakeSearch()), settings, checkpointer=InMemorySaver())
    thread = uid()
    agent.update_state({"configurable": {"thread_id": thread}}, {"messages": HILO_VIEJO}, as_node="model")

    hist = get_history(agent, thread, settings)  # se carga tal como está guardado
    assert {"role": "tool", "name": "calculadora"} in hist and hist[-1]["content"].startswith("Son 4")

    ev = run_turn(agent, settings, "¿Sigues ahí?", thread)
    assert ev[-1]["type"] == "done" and "error" not in [e["type"] for e in ev]
    assert "Sigo aquí." in "".join(e.get("text", "") for e in ev)
    assert set(llm.vistos) == {"calculator", "web_search"}  # el modelo solo ve nombres actuales


def test_bigtool_ignora_ids_guardados_que_ya_no_existen(make_settings):
    from assistant.bigtool_agent import build_bigtool_agent

    s = make_settings(use_bigtool=True)
    llm = Espia(messages=iter(["Listo."]), vistos=[], enlazadas=[])
    agent = build_bigtool_agent(llm, s, checkpointer=InMemorySaver(), memories_store=InMemoryStore(),
                                embeddings=DeterministicFakeEmbedding(size=64), search_fn=FakeSearch())
    thread = uid()
    agent.update_state({"configurable": {"thread_id": thread}},
                       {"messages": HILO_VIEJO,
                        "selected_tool_ids": ["calculadora", "calculator", "herramienta_que_ya_no_existe"]},
                       as_node="tools")
    ev = run_turn(agent, s, "hola", thread)
    assert ev[-1]["type"] == "done" and "error" not in [e["type"] for e in ev]
    assert llm.enlazadas[-1] == ["calculator", "retrieve_tools"]  # id viejo resuelto, duplicado y desconocido fuera
    assert set(llm.vistos) == {"calculator", "web_search"}


def test_la_interfaz_muestra_etiquetas_en_espanol_para_nombres_viejos_y_nuevos():
    node = shutil.which("node")
    if not node:
        pytest.skip("node no está instalado")
    src = re.search(r"/\* TOOL-NAMES-START \*/(.*?)/\* TOOL-NAMES-END \*/",
                    (ROOT / "static" / "index.html").read_text(encoding="utf-8"), re.S).group(1)
    nombres = ["web_search", "buscar_web", "calculator", "calculadora", "current_datetime", "fecha_hora",
               "save_memory", "guardar_recuerdo", "search_memories", "buscar_recuerdos", "update_memory",
               "actualizar_recuerdo", "deep_research", "investigador_profundo"]
    js = f"{src}\nconsole.log(JSON.stringify({json.dumps(nombres)}.map(function(n){{return TOOL_DONE[canonicalTool(n)];}})));"
    out = json.loads(subprocess.run([node, "-e", js], capture_output=True, text=True, check=True, encoding="utf-8").stdout)
    assert all(out), dict(zip(nombres, out))
    assert out[0] == out[1] == "🔎 Búsqueda web" and out[2] == out[3] == "🧮 Cálculo"


def test_todas_las_herramientas_se_llaman_en_ingles(make_settings):
    from assistant.profiles.default.policies import OLD_TOOL_NAMES
    from assistant.bigtool_agent import build_registry
    from assistant.tools import build_tools
    from conftest import fake_llm

    s = make_settings(enable_hitl_demo=True, bigtool_demo_tools=True)
    nombres = {t.name for t in build_tools(fake_llm("x"), s)} | set(build_registry(None, s, InMemoryStore()))
    assert not nombres & set(OLD_TOOL_NAMES)
    assert set(OLD_TOOL_NAMES.values()) <= nombres | {"send_simulated_email"}
