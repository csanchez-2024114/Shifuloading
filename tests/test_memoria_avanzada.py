"""Memoria larga y control de alucinaciones (MEMORY_SUMMARIZE, procedencia, MEMORY_VERIFY, gestión de recuerdos,
ANSWER_VERIFY). Sin tokens: modelos falsos; Mongo solo en assistant_test."""
from fastapi.testclient import TestClient
from langchain_core.embeddings.fake import DeterministicFakeEmbedding
from langchain_core.messages import HumanMessage
from langchain_core.messages.utils import count_tokens_approximately
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from conftest import FakeChat, FakeSearch, fake_llm, run_turn, tool_call, uid


class Recorder(FakeChat):
    """Modelo falso que además guarda el texto de cada entrada."""
    seen: list = []
    tokens: list = []  # tokens de la conversación en cada entrada (sin el system prompt, como cuenta el umbral)

    def _record(self, messages):
        self.seen.append(" ".join(str(m.content) for m in messages))
        self.tokens.append(count_tokens_approximately([m for m in messages if m.type != "system"]))

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self._record(messages)
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        self._record(messages)
        yield from super()._stream(messages, stop=stop, run_manager=run_manager, **kwargs)


def recorder(*responses) -> Recorder:
    return Recorder(messages=iter(list(responses)), seen=[], tokens=[])


def _agent(settings, llm, store=None, checker=None, summarizer=None, checkpointer=None):
    from assistant.agent import build_agent
    from assistant.tools import build_tools

    tools = build_tools(llm, settings, search_fn=FakeSearch(), checker=checker)
    return build_agent(llm, tools, settings, checkpointer=checkpointer or InMemorySaver(), store=store,
                       summarizer=summarizer, checker=checker)


def _values(store, user):
    from assistant.memory import memory_namespace

    return [i.value for i in store.search(memory_namespace(user), limit=50)]


# --------------------------------------------------------------------------- 1. resumen


FILLER = " ".join(["relleno sintético para ocupar tokens en la conversación."] * 12)


def test_resumen_se_dispara_en_el_umbral_y_conserva_el_dato(make_settings):
    from assistant.agent import SUMMARY_PROMPT

    trigger = 600
    s = make_settings(memory_summarize=True, summary_trigger_tokens=trigger, summary_keep_tokens=250)
    turnos = 7
    main = recorder(*[f"respuesta {i}" for i in range(turnos)])
    summarizer = recorder(*["- The user said their name is Zorba and their favorite color is turquoise."] * turnos)
    agent = _agent(s, main, summarizer=summarizer)
    thread = uid()

    eventos = [run_turn(agent, s, "Me llamo Zorba y mi color favorito es el turquesa. " + FILLER, thread)]
    assert not summarizer.seen  # por debajo del umbral no resume
    for i in range(1, turnos):
        eventos.append(run_turn(agent, s, f"Mensaje {i}. " + FILLER, thread))

    assert summarizer.seen, "el umbral se superó y no hubo resumen"
    assert "Zorba" in summarizer.seen[0] and SUMMARY_PROMPT.split("\n")[0][:40] in summarizer.seen[0]
    planos = [e for ev in eventos for e in ev]
    assert any(e["type"] == "summarized" for e in planos)
    assert not any("Zorba" in e.get("text", "") for e in planos if e["type"] == "token")  # el resumen no se streamea

    assert max(main.tokens) < trigger  # el modelo nunca recibió una conversación por encima del umbral
    state = agent.get_state({"configurable": {"thread_id": thread}}).values["messages"]
    assert state[0].additional_kwargs.get("lc_source") == "summarization" and "Zorba" in state[0].content
    assert "Zorba" in main.seen[-1]  # el modelo principal sigue recibiendo el dato inicial

    from assistant.agent import get_history
    assert get_history(agent, thread, s)[0] == {"role": "summary"}


def test_sin_interruptor_no_hay_resumen(settings):
    from assistant.agent import build_agent

    nodes = build_agent(fake_llm("x"), [], settings).get_graph().nodes
    assert not any("ResumenPorTurno" in n or "Summarization" in n or "AnswerVerifier" in n for n in nodes)


# --------------------------------------------------------------------------- 2. procedencia y compatibilidad


def test_recuerdos_viejos_sin_campos_siguen_funcionando(store):
    from assistant import memory

    u = uid()
    store.put(memory.memory_namespace(u), "viejo1", {"text": "Le gusta el jazz", "created_at": "2025-01-01T00:00:00+00:00"})
    store.put(memory.memory_namespace(u), "viejo2", {"text": "Vive en Puebla"})
    memory.save_memory(store, u, "Prefiere té", thread_id="t1", evidence="prefiero té", confidence="quoted")

    lista = memory.list_memories(store, u)
    assert [m["text"] for m in lista][0] == "Prefiere té"
    viejo = next(m for m in lista if m["key"] == "viejo1")
    assert viejo["evidence"] == "" and viejo["confidence"] == "unverified" and viejo["thread_id"] is None
    assert memory.search_memories(store, u, "jazz") == ["Le gusta el jazz"]
    assert len(memory.search_memories(store, u)) == 3


def test_cita_literal_da_quoted_y_cita_inventada_queda_sin_evidencia(settings):
    store = InMemoryStore()
    agent = _agent(settings, fake_llm(
        tool_call("save_memory", {"text": "El usuario se llama Ana", "evidence": "me llamo Ana"}, "g1"),
        tool_call("save_memory", {"text": "El usuario es médico", "evidence": "soy médico"}, "g2"),
        "Anotado"), store=store)
    thread = uid()
    run_turn(agent, settings, "Hola, me llamo Ana y busco recetas", thread, user_id="ana")

    por_texto = {v["text"]: v for v in _values(store, "ana")}  # se guardan en forma neutra, sin "El usuario"
    assert por_texto["Se llama Ana"]["confidence"] == "quoted"
    assert por_texto["Se llama Ana"]["evidence"] == "me llamo Ana"
    assert por_texto["Se llama Ana"]["thread_id"] == thread
    # sin MEMORY_VERIFY se guarda, pero sin evidencia (no se usa el último mensaje como evidencia)
    assert por_texto["Es médico"]["evidence"] == ""
    assert por_texto["Es médico"]["confidence"] == "unverified"


# --------------------------------------------------------------------------- 3. verificación al guardar


def test_recuerdo_no_respaldado_no_se_guarda(make_settings):
    s = make_settings(memory_verify=True)
    store = InMemoryStore()
    checker = fake_llm('{"supported": false, "quote": ""}')
    agent = _agent(s, fake_llm(tool_call("save_memory", {"text": "El usuario es médico"}, "g1"),
                               "No lo guardé"), store=store, checker=checker)
    ev = run_turn(agent, s, "¿Qué opinas de los hospitales?", uid(), user_id="u-v")

    fin = next(e for e in ev if e["type"] == "tool_end" and e["name"] == "save_memory")
    assert fin["output"].startswith("Not saved")
    assert _values(store, "u-v") == []


def test_recuerdo_respaldado_se_guarda_verificado(make_settings):
    s = make_settings(memory_verify=True)
    store = InMemoryStore()
    checker = fake_llm('{"supported": true, "quote": "mi perro se llama Rex"}')
    agent = _agent(s, fake_llm(tool_call("save_memory", {"text": "Su perro se llama Rex"}, "g1"), "Listo"),
                   store=store, checker=checker)
    thread = uid()
    run_turn(agent, s, "Oye, mi perro se llama Rex", thread, user_id="u-ok")

    [v] = _values(store, "u-ok")
    assert v["confidence"] == "verified" and v["evidence"] == "mi perro se llama Rex" and v["thread_id"] == thread


def test_dato_solo_en_el_resumen_no_cuenta_como_evidencia():
    from assistant import memory

    resumen = HumanMessage("Here is a summary of the conversation to date:\n\n- The user said their name is Zorba.",
                           additional_kwargs={"lc_source": "summarization"})
    mensajes = [resumen, HumanMessage("¿Cómo me llamo?")]
    textos = memory.user_texts(mensajes)
    assert textos == ["¿Cómo me llamo?"]  # el resumen es texto del modelo, no del usuario

    def verificador_literal(candidato, texts):  # respalda solo si el dato aparece en lo que escribió el usuario
        return any("zorba" in t.lower() for t in texts), ""

    store = InMemoryStore()
    out = memory.remember(store, "u-z", "El usuario se llama Zorba", "their name is Zorba", textos,
                          verifier=verificador_literal)
    assert out.startswith("Not saved") and _values(store, "u-z") == []
    out = memory.remember(store, "u-z", "El usuario se llama Zorba", "their name is Zorba", textos)
    assert _values(store, "u-z")[0]["evidence"] == ""  # sin verificar: se guarda pero sin evidencia


# --------------------------------------------------------------------------- 4. listar y borrar por user_id


def test_endpoints_listan_y_borran_aislados_por_usuario(settings, store):
    from assistant import memory, server

    a, b = uid("a"), uid("b")
    ka = memory.save_memory(store, a, "A: le gusta el verde")
    memory.save_memory(store, a, "A: vive en Mérida")
    kb = memory.save_memory(store, b, "B: le gusta el rojo")

    app = server.create_app(agent=object(), settings=settings, store=store)
    with TestClient(app) as c:
        lista_a = c.get(f"/memories/{a}").json()["memories"]
        assert {m["text"] for m in lista_a} == {"A: le gusta el verde", "A: vive en Mérida"}
        assert [m["text"] for m in c.get(f"/memories/{b}").json()["memories"]] == ["B: le gusta el rojo"]

        assert c.delete(f"/memories/{b}/{ka}").status_code == 404  # B no puede borrar los de A
        assert len(c.get(f"/memories/{a}").json()["memories"]) == 2
        assert c.delete(f"/memories/{a}/{ka}").json() == {"deleted": ka}
        assert [m["text"] for m in c.get(f"/memories/{a}").json()["memories"]] == ["A: vive en Mérida"]
        assert [m["key"] for m in c.get(f"/memories/{b}").json()["memories"]] == [kb]


def test_endpoints_sin_store_responden_503(settings):
    from assistant import server

    with TestClient(server.create_app(agent=object(), settings=settings)) as c:
        assert c.get("/memories/x").status_code == 503


# --------------------------------------------------------------------------- 6. verificación de respuestas


def test_answer_verify_corrige_con_evidencia_y_conserva_original(make_settings):
    from assistant.agent import get_history

    s = make_settings(answer_verify=True)
    checker = recorder("París tiene unos 2.1 millones de habitantes.")
    # FakeSearch repite la consulta: así la evidencia contiene la cifra correcta (2.1 millones)
    agent = _agent(s, fake_llm(tool_call("web_search", {"query": "población de París 2.1 millones"}, "w1"),
                               "París tiene 50 millones de habitantes."), checker=checker)
    thread = uid()
    ev = run_turn(agent, s, "¿Cuántos habitantes tiene París?", thread)

    [v] = [e for e in ev if e["type"] == "verify"]
    assert v["status"] == "corrected" and v["original"] == "París tiene 50 millones de habitantes."
    assert v["text"].startswith("París tiene unos 2.1")
    assert "Resultado falso para población de París" in checker.seen[0]  # la evidencia llegó al verificador
    assert get_history(agent, thread, s)[-1] == {"role": "assistant", "content": v["text"], "original": v["original"],
                                                 "verify": {"status": "corrected", "notes": []}}


def test_answer_verify_ok_y_sin_busqueda_no_llama(make_settings):
    s = make_settings(answer_verify=True)
    checker = recorder("OK")
    agent = _agent(s, fake_llm(tool_call("web_search", {"query": "x"}, "w1"), "Dato con respaldo",
                               "Hola, ¿qué tal?"), checker=checker)
    thread = uid()
    ev = run_turn(agent, s, "busca x", thread)
    assert [e["status"] for e in ev if e["type"] == "verify"] == ["ok"]

    ev = run_turn(agent, s, "hola", thread)  # sin búsqueda en el turno: 0 llamadas extra
    assert not any(e["type"] == "verify" for e in ev) and len(checker.seen) == 1


# --------------------------------------------------------------------------- 7. bigtool


def test_bigtool_guarda_con_procedencia_y_verificacion(make_settings):
    from assistant.bigtool_agent import build_bigtool_agent, build_registry

    s = make_settings(use_bigtool=True, memory_verify=True)
    t = build_registry(None, s, InMemoryStore(), checker=fake_llm())["save_memory"]
    query = f"{t.name}: {t.description}"
    store = InMemoryStore()
    checker = fake_llm('{"supported": true, "quote": "me gusta el café de olla"}', '{"supported": false, "quote": ""}')
    agent = build_bigtool_agent(fake_llm(
        tool_call("retrieve_tools", {"query": query}, "r1"),
        tool_call("save_memory", {"text": "Le gusta el café de olla"}, "g1"),
        tool_call("save_memory", {"text": "Es vegetariano"}, "g2"),
        "Anotado"), s, checkpointer=InMemorySaver(), memories_store=store,
        embeddings=DeterministicFakeEmbedding(size=64), search_fn=FakeSearch(), checker=checker)
    thread = uid()
    ev = run_turn(agent, s, "Oye, me gusta el café de olla", thread, user_id="u-bt")

    [v] = _values(store, "u-bt")  # el no respaldado no se guardó
    assert v["text"] == "Le gusta el café de olla" and v["confidence"] == "verified"
    assert v["evidence"] == "me gusta el café de olla" and v["thread_id"] == thread
    outs = [e["output"] for e in ev if e["type"] == "tool_end" and e["name"] == "save_memory"]
    from assistant.memory import SAVED_MSG
    assert outs[0] == SAVED_MSG and outs[1].startswith("Not saved")


# --------------------------------------------------------------------------- actualizar_recuerdo


def _end(ev, name):
    return next(e for e in ev if e["type"] == "tool_end" and e["name"] == name)["output"]


def test_resolver_cafe_vs_te_deja_un_solo_recuerdo_con_previous_text(make_settings, store):
    from assistant import memory

    s = make_settings(memory_verify=True)
    u = uid("u")
    key = memory.save_memory(store, u, "Su bebida favorita es el café de olla", confidence="verified")
    agent = _agent(s, fake_llm(
        tool_call("search_memories", {"query": "bebida favorita"}, "b1"),
        tool_call("update_memory", {"id": key, "text": "Su bebida favorita es el té verde",
                                          "evidence": "ahora mi bebida favorita es el té verde"}, "a1"),
        "Actualizado"), store=store, checker=fake_llm('{"supported": true, "quote": "ahora mi bebida favorita es el té verde"}'))
    thread = uid()
    ev = run_turn(agent, s, "Sí, ahora mi bebida favorita es el té verde", thread, user_id=u)

    assert f"[id {key}] Su bebida favorita es el café de olla" in _end(ev, "search_memories")
    assert _end(ev, "update_memory") == memory.UPDATED_MSG
    [m] = memory.list_memories(store, u)  # uno solo, no dos contradictorios
    assert m["key"] == key and m["text"] == "Su bebida favorita es el té verde"
    assert m["previous_text"] == "Su bebida favorita es el café de olla" and m["updated_at"]
    assert m["confidence"] == "verified" and m["evidence"] == "ahora mi bebida favorita es el té verde"
    assert m["thread_id"] == thread


def test_id_de_otro_usuario_se_rechaza_sin_revelar_y_no_cambia(settings, store):
    from assistant import memory

    a, b = uid("a"), uid("b")
    key_b = memory.save_memory(store, b, "B: su color es el rojo")
    agent = _agent(settings, fake_llm(
        tool_call("update_memory", {"id": key_b, "text": "su color es el azul", "evidence": "mi color es el azul"}, "a1"),
        tool_call("update_memory", {"id": "no-existe-123", "text": "su color es el azul",
                                          "evidence": "mi color es el azul"}, "a2"),
        "No pude"), store=store)
    ev = run_turn(agent, settings, "mi color es el azul", uid(), user_id=a)

    outs = [e["output"] for e in ev if e["type"] == "tool_end" and e["name"] == "update_memory"]
    assert outs[0] == outs[1] == memory.NOT_FOUND_MSG  # mismo mensaje: no revela que el id existe
    [m] = memory.list_memories(store, b)
    assert m["text"] == "B: su color es el rojo" and m["previous_text"] is None
    assert memory.list_memories(store, a) == []


def test_actualizacion_sin_respaldo_se_rechaza(make_settings, store):
    from assistant import memory

    s = make_settings(memory_verify=True)
    u = uid("u")
    key = memory.save_memory(store, u, "Vive en Puebla")
    agent = _agent(s, fake_llm(tool_call("update_memory", {"id": key, "text": "Vive en Monterrey"}, "a1"),
                               "No lo actualicé"),
                   store=store, checker=fake_llm('{"supported": false, "quote": ""}'))
    ev = run_turn(agent, s, "Tal vez algún día me mude, no sé", uid(), user_id=u)

    assert _end(ev, "update_memory").startswith("Not updated: the user never stated")
    [m] = memory.list_memories(store, u)
    assert m["text"] == "Vive en Puebla" and m["previous_text"] is None


def test_recuerdo_viejo_sin_campos_se_puede_actualizar(settings, store):
    from assistant import memory

    u = uid("u")
    store.put(memory.memory_namespace(u), "viejo", {"text": "Le gusta el jazz"})
    agent = _agent(settings, fake_llm(
        tool_call("update_memory", {"id": "viejo", "text": "Le gusta el blues", "evidence": "ahora me gusta el blues"}, "a1"),
        "Listo"), store=store)
    ev = run_turn(agent, settings, "ya no el jazz, ahora me gusta el blues", uid(), user_id=u)

    assert _end(ev, "update_memory") == memory.UPDATED_MSG
    [m] = memory.list_memories(store, u)
    assert m["text"] == "Le gusta el blues" and m["previous_text"] == "Le gusta el jazz"
    assert m["confidence"] == "quoted" and m["evidence"] == "ahora me gusta el blues"
    assert memory.search_memories(store, u, "blues") == ["Le gusta el blues"]


def test_bigtool_tiene_actualizar_recuerdo_sin_argumentos_inyectados(make_settings):
    from assistant.bigtool_agent import build_registry

    t = build_registry(None, make_settings(use_bigtool=True), InMemoryStore())["update_memory"]
    assert set(t.args) == {"id", "text", "evidence"}
    from assistant.tools import build_tools
    assert "update_memory" in {x.name for x in build_tools(fake_llm(), make_settings(), search_fn=FakeSearch())}


# --------------------------------------------------------------------------- MEMORY_MIN_SCORE


def _semantic_store():
    # mismo texto -> mismo vector (coseno 1); textos distintos -> vectores casi ortogonales (coseno ~0)
    return InMemoryStore(index={"embed": DeterministicFakeEmbedding(size=64), "dims": 64, "fields": ["text"]})


def test_umbral_relevante_si_irrelevante_no_y_es_configurable():
    from assistant import memory

    st = _semantic_store()
    key = memory.save_memory(st, "u", "Su perro se llama Rex")
    assert memory.recall(st, "u", "Su perro se llama Rex", 0.68) == f"- [id {key}] Su perro se llama Rex"
    assert memory.recall(st, "u", "equipo de fútbol favorito", 0.68) == memory.NO_RELEVANT_MSG  # no el menos malo
    assert "Rex" in memory.recall(st, "u", "equipo de fútbol favorito", -1.0)  # umbral configurable
    assert memory.recall(st, "otro", "equipo de fútbol favorito", 0.68) == memory.NO_MEMORIES_MSG
    # la búsqueda vacía (recientes) y el panel no usan el umbral
    assert "Rex" in memory.recall(st, "u", "", 0.99)
    assert [m["text"] for m in memory.list_memories(st, "u")] == ["Su perro se llama Rex"]


def test_buscar_recuerdos_usa_memory_min_score_de_settings(make_settings):
    st = _semantic_store()
    from assistant import memory
    memory.save_memory(st, "u-s", "Su perro se llama Rex")

    def turno(min_score):
        s = make_settings(memory_min_score=min_score)
        agent = _agent(s, fake_llm(tool_call("search_memories", {"query": "nombre de mi gato"}, "b1"), "ok"), store=st)
        return _end(run_turn(agent, s, "¿cómo se llama mi gato?", uid(), user_id="u-s"), "search_memories")

    assert turno(0.68) == memory.NO_RELEVANT_MSG
    assert "Rex" in turno(-1.0)
