from conftest import uid


def test_memory_namespace():
    from assistant.memory import memory_namespace

    assert memory_namespace("u1") == ("user", "u1", "memories")


def test_save_y_search_con_filtro(store):
    from assistant.memory import save_memory, search_memories

    user = uid("user")
    save_memory(store, user, "Me encanta la pizza napolitana")
    save_memory(store, user, "Mi perro se llama Rex")

    res = search_memories(store, user, "pizza")
    assert res and "pizza" in res[0].lower()
    res = search_memories(store, user, "perro")
    assert res and "rex" in res[0].lower()


def test_search_query_vacia_devuelve_todo(store):
    from assistant.memory import save_memory, search_memories

    user = uid("user")
    save_memory(store, user, "recuerdo uno")
    save_memory(store, user, "recuerdo dos")

    assert len(search_memories(store, user)) == 2
    assert len(search_memories(store, user, "", limit=1)) == 1


def test_memorias_aisladas_por_usuario(store):
    from assistant.memory import save_memory, search_memories

    a, b = uid("a"), uid("b")
    save_memory(store, a, "secreto de a: color verde")
    assert search_memories(store, b, "verde") == []
    assert search_memories(store, b) == []
    assert any("verde" in t for t in search_memories(store, a, "verde"))


def test_semantic_sin_atlas_cae_a_palabras(mongo_client):
    from assistant import memory

    store = memory.build_store(mongo_client, "assistant_test", semantic=True, api_key="sk-test-fake")
    assert not store.index_config  # Mongo local: sin índice vectorial, sin fallar
    u = uid()
    memory.save_memory(store, u, "Le gusta el café")
    assert memory.search_memories(store, u, "cafe") == ["Le gusta el café"]
