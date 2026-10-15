"""Tests con MongoDB real (base assistant_test)."""
from langgraph.checkpoint.memory import InMemorySaver

from conftest import MONGO_URI, TEST_DB, build_test_agent, run_turn, tool_call, types, uid


def test_historial_persiste_tras_reinicio(settings, mongo_client, mongo_checkpointer):
    from assistant import memory
    from assistant.agent import get_history

    thread = uid()
    agent1 = build_test_agent(["Encantado de conocerte"], settings, checkpointer=mongo_checkpointer)
    events = run_turn(agent1, settings, "Hola, me llamo Ana", thread)
    assert types(events)[-1] == "done"

    # "reinicio": cliente, checkpointer y agente nuevos sobre la misma base
    client2 = memory.ping_mongo(MONGO_URI)
    try:
        cp2 = memory.build_checkpointer(client2, TEST_DB)
        agent2 = build_test_agent([], settings, checkpointer=cp2)
        history = get_history(agent2, thread, settings)
    finally:
        client2.close()

    assert history == [
        {"role": "user", "content": "Hola, me llamo Ana"},
        {"role": "assistant", "content": "Encantado de conocerte"},
    ]


def test_memoria_compartida_entre_threads(settings, store):
    user = uid("user")
    agent = build_test_agent(
        [
            tool_call("guardar_recuerdo", {"texto": "Mi color favorito es el verde"}, "call_a"),
            "Guardado",
            tool_call("buscar_recuerdos", {"consulta": "color favorito"}, "call_b"),
            "Tu color favorito es el verde",
        ],
        settings,
        checkpointer=InMemorySaver(),
        store=store,
    )

    ev_a = run_turn(agent, settings, "recuerda que mi color favorito es el verde", uid("thread-a"), user)
    assert next(e for e in ev_a if e["type"] == "tool_end")["status"] == "success"

    ev_b = run_turn(agent, settings, "cual es mi color favorito?", uid("thread-b"), user)
    end = next(e for e in ev_b if e["type"] == "tool_end")
    assert end["name"] == "buscar_recuerdos"
    assert "verde" in end["output"].lower()


def test_memoria_no_se_filtra_a_otro_usuario(settings, store):
    owner, other = uid("owner"), uid("other")
    agent = build_test_agent(
        [
            tool_call("guardar_recuerdo", {"texto": "Mi clave secreta es naranja"}, "call_a"),
            "Guardado",
            tool_call("buscar_recuerdos", {"consulta": "clave secreta naranja"}, "call_b"),
            "No se nada",
        ],
        settings,
        checkpointer=InMemorySaver(),
        store=store,
    )
    run_turn(agent, settings, "guarda mi clave", uid("thread"), owner)
    events = run_turn(agent, settings, "cual es mi clave?", uid("thread"), other)
    end = next(e for e in events if e["type"] == "tool_end")
    assert "naranja" not in end["output"].lower()
