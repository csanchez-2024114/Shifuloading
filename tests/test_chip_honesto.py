"""Herramientas que no se ejecutaron (límite de una búsqueda por paso, tope, rechazo): la UI no las marca como hechas
y ANSWER_VERIFY no corre sin evidencia real. Clasificador: palabras de actualidad. Sin tokens."""
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

from conftest import FakeSearch, fake_llm, run_turn, tool_call, uid
from test_memoria_avanzada import _agent, recorder


def _tres_busquedas():
    return AIMessage(content="", tool_calls=[{"name": "web_search", "args": {"query": f"q{i}"}, "id": f"w{i}"}
                                             for i in range(3)])


def test_busquedas_no_realizadas_en_vivo_y_en_el_historial(settings):
    from assistant.agent import build_agent, get_history
    from assistant.tools import build_tools

    llm = fake_llm(_tres_busquedas(), "respuesta")
    agent = build_agent(llm, build_tools(llm, settings, search_fn=FakeSearch()), settings, checkpointer=InMemorySaver())
    thread = uid()
    fines = [e for e in run_turn(agent, settings, "busca", thread) if e["type"] == "tool_end"]
    assert sorted(e["status"] for e in fines) == ["skipped", "skipped", "success"]
    tools = [m for m in get_history(agent, thread, settings) if m["role"] == "tool"]
    assert tools == [{"role": "tool", "name": "web_search"},
                     {"role": "tool", "name": "web_search", "status": "skipped"},
                     {"role": "tool", "name": "web_search", "status": "skipped"}]


def test_answer_verify_no_corre_si_ninguna_busqueda_se_ejecuto(make_settings):
    # presupuesto de búsquedas de 1 token: la única búsqueda no se lanza ("Not run: the web search budget…")
    s = make_settings(answer_verify=True, investigator_token_budget=1, turn_token_cap=0)
    checker = recorder("OK")
    agent = _agent(s, fake_llm(tool_call("web_search", {"query": "q"}, "w1"), "No pude buscar."), checker=checker)
    fines = [e for e in run_turn(agent, s, "busca vuelos", uid()) if e["type"] == "tool_end"]
    assert fines[0]["status"] == "skipped" and checker.seen == []
    # con una búsqueda ejecutada sí verifica
    s2 = make_settings(answer_verify=True, turn_token_cap=0)
    checker2 = recorder("OK")
    agent2 = _agent(s2, fake_llm(tool_call("web_search", {"query": "q"}, "w1"), "Hay vuelos."), checker=checker2)
    run_turn(agent2, s2, "busca vuelos", uid())
    assert len(checker2.seen) == 1


def test_answer_verify_sin_evidencia_real_no_llama_al_verificador(make_settings):
    from assistant.agent import AnswerVerifier
    from langchain_core.messages import HumanMessage, ToolMessage

    checker = recorder("OK")
    mw = AnswerVerifier(checker)

    class Rt:
        def stream_writer(self, _):
            pass

    rechazada = {"messages": [
        HumanMessage("¿y en avión?"),
        AIMessage(content="", tool_calls=[{"name": "web_search", "args": {"query": "x"}, "id": "w1"}]),
        ToolMessage("Not run: this message is close to its token cap. Do not search again.", tool_call_id="w1",
                    name="web_search"),
        AIMessage(content="No pude buscar vuelos.")]}
    assert mw.after_agent(rechazada, Rt()) is None and checker.seen == []
    rechazo_usuario = {"messages": [*rechazada["messages"][:2],
                                    ToolMessage("User rejected the tool call for `deep_research` with reason: no",
                                                tool_call_id="w1", name="deep_research"),
                                    AIMessage(content="Sin investigar.")]}
    assert mw.after_agent(rechazo_usuario, Rt()) is None and checker.seen == []
    ejecutada = {"messages": [*rechazada["messages"][:2],
                              ToolMessage("[engine: duckduckgo]\nVuelos desde 40 €", tool_call_id="w1",
                                          name="web_search"),
                              AIMessage(content="Hay vuelos desde 40 €.")]}
    mw.after_agent(ejecutada, Rt())
    assert len(checker.seen) == 1


MENSAJES = [  # (mensaje, ¿pasa por el clasificador?)
    ("pon una alarma a las 7", True),  # el dígito ya lo mandaba al clasificador
    ("hazme un script en python para leer un CSV y sumar la columna importe", True),
    ("¿qué hora es en Tokio?", False),
    ("planea un viaje de 5 días a Lisboa del 12 al 16 de marzo con 900 euros, me gustan los museos", True),
    ("compara a fondo tres frameworks de agentes con fuentes recientes y dime cuál conviene para producción", True),
    ("calcula el 15% de 2340 y divídelo entre 3", True),
    ("¿quién ganó el último partido del Málaga?", True),
    ("explícame qué es un índice compuesto en una base de datos y cuándo conviene usarlo", True),
    ("demuestra que hay infinitos números primos y luego generaliza la idea a primos de la forma 4k+3", True),
    ("resuelve 3x+2y=7 y x-y=1, y luego calcula x²+y²", True),
    ("investiga en profundidad el impacto de la ley de IA de la UE en startups españolas, con fuentes", True),
    ("mándale un whatsapp a mi jefa diciendo que llego tarde y pon una alarma a las 7", True),
]


def test_palabras_de_actualidad_pasan_por_el_clasificador():
    from assistant.agent import necesita_clasificador

    assert [necesita_clasificador(m) for m, _ in MENSAJES] == [esperado for _, esperado in MENSAJES]
    for corto in ("¿precio del bitcoin?", "noticias de hoy", "who won yesterday?", "latest news", "¿y ayer?"):
        assert necesita_clasificador(corto), corto
    for trivial in ("hola", "gracias", "Hola!", "muchas gracias", "ok", "buenas noches"):
        assert not necesita_clasificador(trivial), trivial


def test_rechazo_de_la_tarjeta_emite_tool_end_skipped():
    """El rechazo de la tarjeta lo escribe el middleware HITL (no el nodo "tools"): también debe llegar a la UI."""
    from langchain_core.messages import AIMessage, ToolMessage

    from assistant.agent import _update_events

    rechazo = ToolMessage("User rejected the tool call for `deep_research` with reason: no", name="deep_research",
                          tool_call_id="r1", status="error")
    update = {"HumanInTheLoopMiddleware.after_model": {"messages": [AIMessage("", tool_calls=[]), rechazo]}}
    [ev] = list(_update_events(update))
    assert ev["type"] == "tool_end" and ev["id"] == "r1" and ev["status"] == "skipped"
