"""Resumen por tokens (uno por turno), respaldo por palabras en recuerdos, topes del investigador y del esfuerzo,
clasificador opcional, aviso de corte por MAX_TOKENS, keep-alive SSE y LaTeX legible en la UI.
Sin tokens: modelos falsos; sin Mongo."""
import json
import re
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_core.embeddings.fake import DeterministicFakeEmbedding
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.messages.utils import count_tokens_approximately
from langchain_core.outputs import ChatGenerationChunk
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from conftest import FakeChat, FakeSearch, fake_llm, run_turn, tool_call, uid
from test_memoria_avanzada import FILLER, _agent, recorder

HTML = Path(__file__).resolve().parents[1] / "static" / "index.html"


# --------------------------------------------------------------------------- 1. resumen


def test_un_solo_resumen_por_turno_aunque_lo_conservado_siga_grande(make_settings):
    # cada búsqueda devuelve ~400 tokens (la consulta va en el resultado): tras resumir, el par llamada+resultado
    # que no se puede separar ya supera el umbral. El middleware nativo resumiría antes de cada llamada.
    trigger = 600
    s = make_settings(memory_summarize=True, summary_trigger_tokens=trigger, summary_keep_tokens=250)
    grande = FILLER * 2
    main = recorder(*[f"respuesta {i}" for i in range(3)],
                    *[tool_call("web_search", {"query": f"{grande} {i}"}, f"w{i}") for i in range(4)],
                    "respuesta final")
    summarizer = recorder(*["- The user said their name is Zorba."] * 10)
    agent = _agent(s, main, summarizer=summarizer)
    thread = uid()
    for i in range(3):
        run_turn(agent, s, f"Mensaje {i}. Me llamo Zorba. " + FILLER, thread)
    antes = len(summarizer.seen)

    eventos = run_turn(agent, s, "busca cuatro cosas", thread)
    assert [e["type"] for e in eventos].count("summarized") <= 1
    assert len(summarizer.seen) - antes <= 1, "más de un resumen en el mismo turno"
    assert eventos[-1]["type"] == "done"


def test_lo_conservado_tras_resumir_queda_bajo_el_umbral(make_settings):
    trigger, keep = 600, 250
    s = make_settings(memory_summarize=True, summary_trigger_tokens=trigger, summary_keep_tokens=keep)
    main = recorder(*[f"respuesta {i}" for i in range(6)])
    summarizer = recorder(*["- The user said their name is Zorba."] * 6)
    agent = _agent(s, main, summarizer=summarizer)
    thread = uid()
    resumidos = 0
    for i in range(6):
        eventos = run_turn(agent, s, f"Mensaje {i}. " + FILLER, thread)
        if any(e["type"] == "summarized" for e in eventos):  # se resumió en este turno
            resumidos += 1
            state = agent.get_state({"configurable": {"thread_id": thread}}).values["messages"]
            conservado = count_tokens_approximately(state[1:-1])  # sin el resumen ni la respuesta de este turno
            assert conservado <= keep < trigger, conservado
    assert resumidos, "no hubo resumen"
    assert max(main.tokens) < trigger


def test_prompt_del_resumen_pide_lista_de_problemas_resueltos():
    from assistant.agent import SUMMARY_PROMPT

    assert "Problems solved so far" in SUMMARY_PROMPT and "VERBATIM" in SUMMARY_PROMPT
    # sin mezcla de idiomas ni contradicciones (prueba real: "The user said vive en Mérida…" y "No hay tareas
    # resueltas" junto a una tarea resuelta)
    assert '"The user said ..."' not in SUMMARY_PROMPT and "never mix languages within a sentence" in SUMMARY_PROMPT
    assert "keep this heading in English" in SUMMARY_PROMPT and 'write a single "-"' in SUMMARY_PROMPT
    assert "must not contradict itself" in SUMMARY_PROMPT


# --------------------------------------------------------------------------- 2. recuerdos con varios temas


def _semantic_store():
    return InMemoryStore(index={"dims": 32, "embed": DeterministicFakeEmbedding(size=32), "fields": ["text"]})


def test_respaldo_por_palabras_trae_varios_temas_marcado_como_menos_confiable():
    from assistant import memory

    st = _semantic_store()
    trabajo = memory.save_memory(st, "u", "Tomás trabaja como arquitecto de software en una fintech.")
    ciudad = memory.save_memory(st, "u", "Tomás vive en Querétaro.")
    memory.save_memory(st, "u", "Su perro se llama Rex.")
    out = memory.recall(st, "u", "dónde trabajo y dónde vivo", 0.99)  # umbral imposible: solo el respaldo
    assert f"[id {trabajo}] {memory.KEYWORD_MARK}" in out and f"[id {ciudad}] {memory.KEYWORD_MARK}" in out
    assert "Rex" not in out


def test_sinonimos_de_vivienda_y_trabajo():
    # prueba real R2: la consulta "ciudad" sacó 0.674 (bajo el umbral) y no comparte palabras con el recuerdo
    from assistant import memory

    st = _semantic_store()
    ciudad = memory.save_memory(st, "u", "El usuario vive en Querétaro.")
    trabajo = memory.save_memory(st, "u", "El usuario trabaja como arquitecto de software.")
    assert f"[id {ciudad}]" in memory.recall(st, "u", "ciudad", 0.99)
    assert f"[id {trabajo}]" in memory.recall(st, "u", "profesión", 0.99)
    assert memory.recall(st, "u", "dónde estudié", 0.99) == memory.NO_RELEVANT_MSG


@pytest.mark.parametrize("query", ["nombre de mi gato", "fecha de nacimiento del usuario", "qué tomo",
                                      "color favorito", "equipo de fútbol favorito"])
def test_respaldo_por_palabras_no_trae_irrelevantes(query):
    from assistant import memory

    st = _semantic_store()
    for t in ("Su perro se llama Rex.", "La hermana del usuario, Lucía, cumple años el 12 de mayo.",
              "Tomás vive en Querétaro.", "La bebida favorita del usuario es el té verde."):
        memory.save_memory(st, "u", t)
    assert memory.recall(st, "u", query, 0.99) == memory.NO_RELEVANT_MSG


def test_sin_busqueda_semantica_no_cambia_el_formato():
    from assistant import memory

    st = InMemoryStore()
    key = memory.save_memory(st, "u", "Tomás vive en Querétaro.")
    assert memory.recall(st, "u", "Querétaro") == f"- [id {key}] Tomás vive en Querétaro."


# --------------------------------------------------------------------------- 3. investigador


def _inv_settings(**kw):
    from conftest import _settings
    return _settings(**{"investigator_max_searches": 4, "investigator_token_budget": 0, **kw})


class SearchConUso:
    """Búsqueda falsa que, como la hospedada, hace una llamada al modelo que reporta tokens."""

    def __init__(self, tokens=0):
        self.tokens, self.calls = tokens, []

    def __call__(self, query, settings):
        self.calls.append(query)
        msg = AIMessage(content="ok", response_metadata={"model_name": "fake"},
                        usage_metadata={"input_tokens": self.tokens, "output_tokens": 0, "total_tokens": self.tokens})
        FakeChat(messages=iter([msg]), disable_streaming=True).invoke("x")  # sin streaming conserva el uso
        return f"Resultado falso para {query}", "openai_web_search"


def test_investigador_respeta_el_tope_de_busquedas_y_lo_dice():
    from assistant.tools import SEARCH_LIMIT_MSG, investigar

    search = SearchConUso()
    model = fake_llm(*[tool_call("web_search", {"query": f"q{i}"}, f"s{i}") for i in range(4)], "Resumen final")
    out = investigar(model, _inv_settings(investigator_max_searches=2), search, "task", lambda e: None)
    assert search.calls == ["q0", "q1"]
    assert "search limit" in out and "Resumen final" in out
    assert SEARCH_LIMIT_MSG not in out


def test_investigador_cortado_devuelve_lo_hallado_nunca_vacio():
    from assistant.tools import investigar

    cortado = AIMessage(content="", response_metadata={"status": "incomplete",
                                                       "incomplete_details": {"reason": "max_output_tokens"}})
    model = fake_llm(tool_call("web_search", {"query": "python 3.15"}, "s0"), cortado)
    out = investigar(model, _inv_settings(), SearchConUso(), "task", lambda e: None)
    assert "cut before it finished" in out and "Resultado falso para python 3.15" in out


def test_investigador_respeta_el_presupuesto_de_tokens_por_turno():
    from assistant.tools import investigar

    usage = {"input_tokens": 70000, "output_tokens": 1000, "total_tokens": 71000}
    respuestas = [AIMessage(content="", usage_metadata=usage,
                            tool_calls=[{"name": "web_search", "args": {"query": f"q{i}"}, "id": f"s{i}"}])
                  for i in range(2)] + [AIMessage(content="Resumen parcial", usage_metadata=usage)]
    search = SearchConUso()
    out = investigar(fake_llm(*respuestas), _inv_settings(investigator_token_budget=120000), search, "task",
                     lambda e: None, turn_key=("hilo", uid()))
    assert len(search.calls) == 1  # tras 71k + 71k (+ el estimado de la búsqueda) ya no hay presupuesto
    # se corta antes de otra llamada al modelo: devuelve lo hallado y el agente principal lo resume
    assert "research token budget for this message (120,000 tokens)" in out and "overall token cap" not in out
    assert "Resultado falso para q0" in out and "Resumen parcial" not in out


def test_investigador_respeta_el_tope_aunque_pida_busquedas_en_paralelo():
    # prueba real: el subagente pidió 3 y luego 4 búsquedas a la vez y todas pasaban la comprobación
    from assistant.tools import investigar

    search = SearchConUso()
    paralelo = AIMessage(content="", tool_calls=[{"name": "web_search", "args": {"query": f"q{i}"}, "id": f"p{i}"}
                                                 for i in range(4)])
    out = investigar(fake_llm(paralelo, "Resumen"), _inv_settings(investigator_max_searches=2), search, "task",
                     lambda e: None)
    assert len(search.calls) == 2 and "search limit" in out


def _agente(s, llm, search):
    from assistant.agent import build_agent
    from assistant.tools import build_tools
    return build_agent(llm, build_tools(llm, s, search_fn=search), s, checkpointer=InMemorySaver())


def test_buscar_web_del_agente_comparte_el_presupuesto_del_turno(make_settings):
    from assistant.tools import WEB_BUDGET_MSG

    # estimado = costo real: el presupuesto nunca se supera (60k + reserva de 60k > 100k: la segunda no se lanza)
    s = make_settings(investigator_token_budget=100000, search_cost_estimate=60000, turn_token_cap=0)
    search = SearchConUso(60000)
    llm = fake_llm(*[tool_call("web_search", {"query": f"q{i}"}, f"w{i}") for i in range(3)], "fin",
                   tool_call("web_search", {"query": "otra"}, "w9"), "fin 2")
    agent = _agente(s, llm, search)
    thread = uid()
    fines = [e for e in run_turn(agent, s, "busca", thread) if e["type"] == "tool_end"]
    assert search.calls == ["q0"]
    assert [f["output"] for f in fines[1:]] == [WEB_BUDGET_MSG, WEB_BUDGET_MSG]
    otro = [e for e in run_turn(agent, s, "busca otra", thread) if e["type"] == "tool_end"]
    assert search.calls[-1] == "otra" and otro[0]["status"] == "success"  # el presupuesto es por mensaje


def test_agente_e_investigador_juntos_respetan_presupuesto_y_maximo_en_paralelo(make_settings):
    from assistant.tools import TurnBudget, _TURNS

    # el agente pide a la vez el investigador y 3 búsquedas; el investigador pide 4 más, también en paralelo
    s = make_settings(investigator_token_budget=100000, search_cost_estimate=20000, turn_max_searches=10,
                      turn_token_cap=0, investigator_max_searches=4)
    search = SearchConUso(20000)
    batch = AIMessage(content="", tool_calls=[{"name": "deep_research", "args": {"task": "t"}, "id": "inv"}] + [
        {"name": "web_search", "args": {"query": f"m{i}"}, "id": f"m{i}"} for i in range(3)])
    sub = AIMessage(content="", tool_calls=[{"name": "web_search", "args": {"query": f"s{i}"}, "id": f"s{i}"}
                                            for i in range(4)])
    llm = fake_llm(batch, sub, "resumen del investigador", "respuesta final")
    thread = uid()
    run_turn(_agente(s, llm, search), s, "investiga a fondo", thread)
    gasto = [b for k, b in _TURNS.items() if k[0] == thread][0]
    assert isinstance(gasto, TurnBudget)
    assert len(search.calls) == 5 and gasto.tokens == 100000  # 5 × 20k: justo el presupuesto, ni una más
    # con máximo de búsquedas por mensaje
    s2 = make_settings(investigator_token_budget=0, turn_max_searches=3, turn_token_cap=0)
    search2 = SearchConUso(1)
    run_turn(_agente(s2, fake_llm(batch, sub, "resumen", "fin"), search2), s2, "investiga a fondo", uid())
    assert len(search2.calls) == 3


class ConUso(FakeChat):
    """Modelo falso que reporta tokens también en streaming (para TURN_TOKEN_CAP)."""

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        yield from super()._stream(messages, stop=stop, run_manager=run_manager, **kwargs)
        yield ChatGenerationChunk(message=AIMessageChunk(content="", usage_metadata={
            "input_tokens": 30000, "output_tokens": 0, "total_tokens": 30000}))


def test_tope_general_por_turno_aborta_con_aviso_y_deja_el_hilo_usable(make_settings):
    from assistant.agent import turn_cap_msg, get_history

    s = make_settings(turn_token_cap=50000, model_call_limit=15)
    respuestas = [tool_call("calculator", {"expression": f"{i}+1"}, f"c{i}") for i in range(6)] + ["sigo bien"]
    llm = ConUso(messages=iter(respuestas))
    agent = _agente(s, llm, SearchConUso())
    thread = uid()
    ev = run_turn(agent, s, "calcula mucho", thread)
    texto = "".join(e["text"] for e in ev if e["type"] == "token")
    assert turn_cap_msg(50000) in texto and ev[-1]["type"] == "done"
    assert sum(e["type"] == "tool_start" for e in ev) <= 2  # 30k + 30k ≥ 50k: no siguió llamando
    state = agent.get_state({"configurable": {"thread_id": thread}}).values["messages"]
    llamadas = {c["id"] for m in state if m.type == "ai" for c in m.tool_calls}
    respondidas = {m.tool_call_id for m in state if m.type == "tool"}
    assert llamadas <= respondidas  # ninguna llamada a herramienta quedó colgando
    assert get_history(agent, thread, s)[-1]["content"] == turn_cap_msg(50000).strip()
    llm.messages = iter(["otra respuesta"])  # el hilo sigue funcionando en el siguiente mensaje
    s2 = make_settings(turn_token_cap=0, model_call_limit=15)
    ev2 = run_turn(agent, s2, "hola de nuevo", thread)
    assert ev2[-1]["type"] == "done" and "otra respuesta" in "".join(e.get("text", "") for e in ev2)


def test_seguimiento_breve_no_relanza_la_investigacion(make_settings):
    # H13 de la prueba larga: "De esas novedades, ¿cuál afecta más al backend de una fintech? Breve." relanzó
    # el investigador (10 búsquedas, 240k tokens)
    s = make_settings(turn_token_cap=0)
    search = SearchConUso()
    llm = fake_llm(
        tool_call("deep_research", {"task": "novedades de Python 3.15"}, "i1"),
        tool_call("web_search", {"query": "python 3.15"}, "s1"), "RESUMEN: lazy imports y UTF-8", "Respuesta 1",
        tool_call("deep_research", {"task": "cuál afecta más a una fintech"}, "i2"), "Respuesta 2",
        tool_call("deep_research", {"task": "investiga de nuevo"}, "i3"),
        tool_call("web_search", {"query": "python 3.15 fintech"}, "s2"), "RESUMEN 2", "Respuesta 3")
    agent = _agente(s, llm, search)
    thread = uid()
    run_turn(agent, s, "Investiga a fondo las novedades de Python 3.15", thread)
    assert search.calls == ["python 3.15"]
    ev = run_turn(agent, s, "De esas novedades, ¿cuál afecta más al backend de una fintech? Breve.", thread)
    fin = next(e for e in ev if e["type"] == "tool_end")
    assert search.calls == ["python 3.15"]  # no se relanzó
    assert fin["output"].startswith("Not run: this conversation already has research") and "lazy imports" in fin["output"]
    run_turn(agent, s, "Investiga de nuevo con fuentes más recientes", thread)  # pedido explícito: sí se relanza
    assert search.calls == ["python 3.15", "python 3.15 fintech"]


def test_max_tokens_por_defecto_deja_lugar_al_razonamiento(monkeypatch):
    from assistant.config import Settings

    monkeypatch.delenv("MAX_TOKENS", raising=False)  # .env ya se cargó al importar config
    assert Settings.from_env().max_tokens == 8000


def test_investigador_no_usa_max_tokens_del_agente(make_settings):
    from assistant.agent import make_model
    from assistant.tools import investigator_model

    s = make_settings(max_tokens=2000, investigator_max_tokens=6000)
    assert investigator_model(make_model(s), s).max_tokens == 6000
    assert investigator_model(make_model(s), make_settings(max_tokens=2000, investigator_max_tokens=0)).max_tokens is None


# --------------------------------------------------------------------------- 4. esfuerzo y clasificador


@pytest.mark.parametrize("mensaje,clasifica", [
    ("hola", False), ("gracias", False), ("¿Qué tal tu día?", False),
    ("17 por 23", True), ("calcula la raíz", True), ("dame un plan", True), ("```print(1)```", True),
    ("Diseña una función", True), ("x" * 80, True),
])
def test_clasificador_solo_cuando_hace_falta(mensaje, clasifica):
    from assistant.agent import necesita_clasificador

    assert necesita_clasificador(mensaje) is clasifica


def test_servidor_salta_el_clasificador_y_respeta_el_selector(make_settings):
    from assistant import server
    from conftest import build_test_agent

    llamadas = []

    def classify(s, m):
        llamadas.append(m)
        return "medio"

    s = make_settings(model_call_limit=0)
    agent = build_test_agent(["ok"] * 5, s, checkpointer=InMemorySaver())
    with TestClient(server.create_app(agent=agent, settings=s, classify=classify)) as c:
        def effort(msg, elegido=None):
            r = c.post("/chat", json={"message": msg, "thread_id": uid(), "effort": elegido})
            return next(json.loads(b[6:]) for b in r.text.split("\n\n") if b.startswith("data: ")
                        and json.loads(b[6:])["type"] == "effort")

        assert effort("hola") == {"type": "effort", "level": "bajo", "max_calls": 5, "reasoning": "low", "source": "regla"}
        assert effort("gracias")["source"] == "regla"
        assert llamadas == []
        assert effort("17 por 23")["source"] == "auto" and llamadas == ["17 por 23"]
        manual = effort("17 por 23", "alto")
        assert manual["level"] == "alto" and manual["source"] == "manual" and manual["max_calls"] == 15
        assert llamadas == ["17 por 23"]  # el selector manda: no se clasifica


def test_esfuerzo_alto_usa_el_tope_configurable(make_settings):
    from assistant.agent import contexto_para

    assert contexto_para("u", make_settings(model_call_limit=0), "alto").max_llamadas == 15
    assert contexto_para("u", make_settings(model_call_limit=0, effort_high_max_calls=7), "alto").max_llamadas == 7


def test_ultima_llamada_permitida_va_sin_herramientas_y_avisa(make_settings):
    from assistant.agent import LAST_STEP_NOTE, stream_events

    s = make_settings(model_call_limit=0)
    main = recorder(*[tool_call("calculator", {"expression": "1+1"}, f"c{i}") for i in range(4)],
                    "Con lo que tengo: 2. Me detuve en el límite de pasos.")
    agent = _agent(s, main)
    ev = list(stream_events(agent, {"messages": [{"role": "user", "content": "x"}]}, uid(), "u", s, "bajo"))
    assert len(main.seen) == 5
    assert LAST_STEP_NOTE in main.seen[4] and not any(LAST_STEP_NOTE in t for t in main.seen[:4])
    assert "límite de pasos" in "".join(e["text"] for e in ev if e["type"] == "token")


def test_tope_de_herramienta_repetida(make_settings):
    from assistant.agent import REPEAT_LIMIT_MSG

    s = make_settings(tool_repeat_limit=2)
    agent = _agent(s, fake_llm(*[tool_call("calculator", {"expression": f"{i}+1"}, f"c{i}") for i in range(3)], "fin"))
    fines = [e for e in run_turn(agent, s, "suma", uid()) if e["type"] == "tool_end"]
    assert [e["status"] for e in fines] == ["success", "success", "skipped"]  # no se ejecutó: la UI no pone "✓"
    assert fines[2]["output"] == REPEAT_LIMIT_MSG.format(name="calculator", limit=2)


# --------------------------------------------------------------------------- 5. corte por MAX_TOKENS y keep-alive


class Cortado(FakeChat):
    """Como FakeChat, pero la respuesta llega marcada como cortada por max_output_tokens."""

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        yield from super()._stream(messages, stop=stop, run_manager=run_manager, **kwargs)
        yield ChatGenerationChunk(message=AIMessageChunk(content="", response_metadata={
            "status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"}}))


def test_respuesta_cortada_por_max_tokens_lo_dice_y_ofrece_seguir(settings):
    from assistant.agent import CUT_NOTE, get_history

    agent = _agent(settings, Cortado(messages=iter(["Semana 1: rodaje suave de"])))
    thread = uid()
    text = "".join(e["text"] for e in run_turn(agent, settings, "plan largo", thread) if e["type"] == "token")
    assert text.endswith(CUT_NOTE) and "continúa" in CUT_NOTE
    assert get_history(agent, thread, settings)[-1]["content"].endswith(CUT_NOTE)  # también al recargar


class CortadoPrimero(FakeChat):
    """La primera respuesta llega vacía y cortada por max_output_tokens (todo fue razonamiento); las demás, normales."""
    calls: int = 0
    settings_seen: list = []

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        self.calls += 1
        self.settings_seen.append(kwargs.get("reasoning"))
        if self.calls == 1:
            yield ChatGenerationChunk(message=AIMessageChunk(content="", response_metadata={
                "status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"}}))
            return
        yield from super()._stream(messages, stop=stop, run_manager=run_manager, **kwargs)


def test_respuesta_vacia_por_max_tokens_se_reintenta_una_vez_con_razonamiento_bajo(settings):
    from assistant.agent import CUT_NOTE

    llm = CortadoPrimero(messages=iter(["Resumen con lo investigado."]), settings_seen=[])
    texto = "".join(e["text"] for e in run_turn(_agent(settings, llm), settings, "investiga", uid())
                    if e["type"] == "token")
    assert llm.calls == 2 and texto == "Resumen con lo investigado." and CUT_NOTE not in texto


def test_keepalive_envia_ping_en_silencios_sin_tocar_los_eventos():
    from assistant.server import PING, with_keepalive

    def lento():
        yield "data: 1\n\n"
        time.sleep(0.35)
        yield "data: 2\n\n"

    out = list(with_keepalive(lento(), 0.1))
    assert [x for x in out if x != PING] == ["data: 1\n\n", "data: 2\n\n"]
    assert out.count(PING) >= 2 and out[0] == "data: 1\n\n"
    assert list(with_keepalive(iter(["a"]), 0)) == ["a"]  # 0 = apagado


# --------------------------------------------------------------------------- LaTeX legible en la UI


def _tex(samples):
    node = shutil.which("node")
    if not node:
        pytest.skip("node no está instalado")
    src = re.search(r"/\* MATH-START \*/(.*?)/\* MATH-END \*/", HTML.read_text(encoding="utf-8"), re.S).group(1)
    js = (f"{src}\nvar st=[];function keep(h){{st.push(h);return '['+(st.length-1)+']';}}\n"
          f"console.log(JSON.stringify({json.dumps(samples)}.map(function(s){{st=[];var r=replaceMath(s,keep);"
          f"return r.replace(/\\[(\\d+)\\]/g,function(m,i){{return st[+i];}});}})));")
    return json.loads(subprocess.run([node, "-e", js], capture_output=True, text=True, check=True,
                                     encoding="utf-8").stdout)


def test_latex_se_muestra_legible_sin_texto_crudo():
    out = _tex([r"La recurrencia \(a_n = a_{n-1} + a_{n-2}\) da \(\frac{3}{4}\).",
                r"\[\binom{25}{3} \cdot 2^{10} \le \sqrt{x+1}\]",
                r"$$\sum_{i=1}^{n} i = \frac{n(n+1)}{2}$$",
                "Precio: $5 y $10, sin fórmulas"])
    assert out[0] == ('La recurrencia <span class="math">a<sub>n</sub> = a<sub>n-1</sub> + a<sub>n-2</sub></span> '
                      'da <span class="math">3/4</span>.')
    assert out[1] == '<span class="math block">C(25, 3) · 2<sup>10</sup> ≤ √(x+1)</span>'
    assert out[2] == '<span class="math block">Σ<sub>i=1</sub><sup>n</sup> i = (n(n+1))/2</span>'
    assert out[3] == "Precio: $5 y $10, sin fórmulas"
    assert not any("\\" in o for o in out)


def test_investigador_sin_busquedas_no_da_fuentes_ni_urls():
    """Prueba real: sin ninguna búsqueda, el investigador escribió 5 URLs de memoria bajo "Fuentes"."""
    from assistant.tools import NO_WEB_NOTE, investigar

    inventadas = [f"https://ejemplo{i}.gob/ley-{i}" for i in range(5)]
    texto = ("## Comparación\nLa UE tiene un reglamento ([texto](" + inventadas[0] + ")).\n\n"
             "### Fuentes oficiales o fiables\n" + "\n".join(f"- Fuente {i}: {u}" for i, u in enumerate(inventadas[1:])))
    search = SearchConUso()
    out = investigar(fake_llm(texto), _inv_settings(), search, "task", lambda e: None)
    assert search.calls == []
    assert not [u for u in inventadas if u in out] and "http" not in out
    assert "Fuentes oficiales" not in out and "Fuente 1" not in out  # sin sección de fuentes
    assert NO_WEB_NOTE in out and "La UE tiene un reglamento (texto)" in out


def test_investigador_quita_las_urls_que_no_salieron_de_sus_busquedas():
    from assistant.tools import NO_WEB_NOTE, investigar

    real, falsa = "https://www.sat.gob.gt/ley-iva", "https://inventada.example/iva"

    def search(query, settings):
        return f"Resultado para {query}: ver {real}?utm_source=openai", "openai_web_search"

    model = fake_llm(tool_call("web_search", {"query": "iva"}, "s0"), tool_call("web_search", {"query": "credito"}, "s1"),
                     f"Resumen.\n\nFuentes:\n- [SAT]({real})\n- [Otra]({falsa})\n- {falsa}/pdf")
    out = investigar(model, _inv_settings(), search, "task", lambda e: None)
    assert f"[SAT]({real})" in out  # la real se conserva (coincide sin los parámetros)
    assert "inventada.example" not in out and "- Otra" in out
    assert NO_WEB_NOTE not in out
