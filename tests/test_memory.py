import pytest

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


# --------------------------------------------------------------------------- modo por palabras (MEMORY_SEMANTIC=0)
# Prueba real: "¿en qué trabajo?" y "¿qué me gusta comer?" dieron "no sé" con los 3 recuerdos guardados: la consulta
# del modelo ("…del usuario?") solo coincidía por la palabra genérica "usuario" con "El usuario vive en Querétaro".
REALES = ["El usuario vive en Querétaro.", "La usuaria trabaja como ingeniera de datos en una aseguradora.",
          "La comida favorita de la usuaria es el pozole."]


def _store_por_palabras(textos, *, tal_cual=True):
    from langgraph.store.memory import InMemoryStore

    from assistant import memory

    st = InMemoryStore()  # sin índice: búsqueda por palabras
    for i, t in enumerate(textos):
        if tal_cual:  # como los recuerdos ya guardados (no se migran): sin pasar por save_memory
            st.put(memory.memory_namespace("u"), f"k{i}", {"text": t, "created_at": f"2026-01-{i + 1:02d}"})
        else:
            memory.save_memory(st, "u", t)
    return st


@pytest.mark.parametrize("consulta, esperado", [
    ("¿en qué trabajo?", "ingeniera"), ("¿Cuál es el trabajo del usuario?", "ingeniera"),
    ("¿qué me gusta comer?", "pozole"), ("¿Qué le gusta comer al usuario?", "pozole"),
    ("¿dónde vivo?", "Querétaro")])
def test_por_palabras_encuentra_el_recuerdo_correcto_primero(consulta, esperado):
    from assistant import memory

    st = _store_por_palabras(REALES + [f"Dato viejo número {i}." for i in range(6)])  # más de 5: sin el respaldo
    resultado = memory.search_memory_items(st, "u", consulta)
    assert esperado in resultado[0][1], resultado
    assert esperado in memory.recall(st, "u", consulta) and memory.NO_MATCH_HEADER not in memory.recall(st, "u", consulta)


def test_por_palabras_sin_coincidencias_devuelve_los_5_mas_recientes():
    from assistant import memory

    st = _store_por_palabras([f"Dato {i} sobre astronomía." for i in range(8)])
    resultado = memory.search_memory_items(st, "u", "¿cuál es mi color favorito?")
    assert [t for _, t in resultado] == [f"Dato {i} sobre astronomía." for i in (7, 6, 5, 4, 3)]
    texto = memory.recall(st, "u", "¿cuál es mi color favorito?")
    assert texto.startswith(memory.NO_MATCH_HEADER) and texto.count("[id ") == 5


@pytest.mark.parametrize("texto, neutro", [
    ("El usuario vive en Querétaro.", "Vive en Querétaro."),
    ("La usuaria trabaja como ingeniera de datos.", "Trabaja como ingeniera de datos."),
    ("Al usuario le gusta el pozole.", "Le gusta el pozole."),
    ("The user works as a nurse.", "Works as a nurse."),
    ("Su comida favorita es el pozole.", "Su comida favorita es el pozole."),
    ("El usuario", "El usuario")])
def test_recuerdos_nuevos_se_guardan_en_forma_neutra(texto, neutro):
    from assistant import memory

    st = _store_por_palabras([texto], tal_cual=False)
    assert [t for _, t in memory.search_memory_items(st, "u", "")] == [neutro]


def test_recuerdos_neutros_se_encuentran_por_raiz():
    from assistant import memory

    st = _store_por_palabras(["Trabaja como ingeniera de datos.", "Vive en Querétaro.", "Tomás vive en Lima."]
                             + [f"Dato viejo número {i}." for i in range(6)], tal_cual=False)
    assert "ingeniera" in memory.search_memory_items(st, "u", "¿en qué trabajo?")[0][1]
    # "Tomás" a inicio de frase sigue siendo nombre propio: "qué tomo" no casa con él por raíz
    assert memory._keyword_search(st, "u", "qué tomo")[1] is False
