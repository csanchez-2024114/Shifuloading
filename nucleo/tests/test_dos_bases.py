"""Dos bases de datos (IA y negocio): arranque, compatibilidad con MONGODB_*, repositorios de negocio y borrado en
la base de la IA. Sin tokens. Mongo solo en assistant_test (IA) y app_test (negocio)."""
import pytest

from conftest import uid

APP_TEST_DB = "app_test"  # NUNCA una base real


@pytest.fixture
def app_db(mongo_client):
    mongo_client.drop_database(APP_TEST_DB)
    yield APP_TEST_DB
    mongo_client.drop_database(APP_TEST_DB)


@pytest.fixture(params=["memoria", "mongo"])
def appdata(request):
    if request.param == "memoria":
        from assistant.appdata.memory import MemoryAppData

        return MemoryAppData()
    from assistant.appdata.mongo import MongoAppData

    return MongoAppData(request.getfixturevalue("mongo_client"), request.getfixturevalue("app_db"))


def test_arranque_exige_bases_distintas(make_settings):
    from assistant.config import ConfigError
    from assistant.memory import app_startup, same_database
    from assistant.packs.i18n.es import SAME_DB_MSG

    assert same_database("mongodb+srv://u:clave@cl.mongodb.net/", "ai", "mongodb+srv://otro:x@CL.mongodb.net", "ai")
    assert not same_database("mongodb+srv://u:p@cl.mongodb.net", "ai", "mongodb+srv://u:p@cl.mongodb.net", "app")
    s = make_settings(auth_enabled=True, mongodb_uri="mongodb://127.0.0.1:27017", mongodb_db="ia",
                      app_mongodb_uri="mongodb://127.0.0.1:27017/", app_mongodb_db="ia")
    with pytest.raises(ConfigError) as e:
        app_startup(s)
    assert str(e.value) == SAME_DB_MSG and "clave" not in str(e.value)
    with pytest.raises(ConfigError, match="APP_MONGODB_URI"):
        app_startup(make_settings(auth_enabled=True))
    assert app_startup(make_settings()) is None  # sin cuentas y sin base de negocio: como antes


def test_variables_ai_con_compatibilidad(monkeypatch):
    from assistant.config import Settings

    monkeypatch.delenv("AI_MONGODB_URI", raising=False)
    monkeypatch.delenv("AI_MONGODB_DB", raising=False)
    s = Settings.from_env()
    assert s.mongodb_uri == "mongodb://127.0.0.1:27017" and s.mongodb_db == "assistant_test"  # MONGODB_* (conftest)
    monkeypatch.setenv("AI_MONGODB_DB", "ai_test")
    assert Settings.from_env().mongodb_db == "ai_test"


def test_hilos_por_dueno_y_titulo(appdata):
    from assistant.appdata import thread_title

    appdata.threads.create("t1", "u1", thread_title("Hola, quiero planear un viaje a Oaxaca en diciembre con amigos"))
    appdata.threads.create("t2", "u2")
    appdata.threads.touch("t2", "Otro título")
    assert appdata.threads.get("t1")["title"] == "Hola, quiero planear un viaje a…"
    assert [t["thread_id"] for t in appdata.threads.list_for_user("u1")] == ["t1"]
    assert appdata.threads.get("t2")["title"] == "Otro título"
    appdata.threads.delete_for_user("u1")
    assert appdata.threads.get("t1") is None and appdata.threads.get("t2")


def test_borrado_de_datos_de_la_ia(mongo_checkpointer, store):
    from langchain_core.messages import HumanMessage

    from assistant import ai_data, memory

    user, t1, t2 = uid("u"), uid("t"), uid("t")
    for t in (t1, t2):
        cfg = {"configurable": {"thread_id": t, "checkpoint_ns": ""}}
        from langgraph.checkpoint.base import empty_checkpoint

        ck = empty_checkpoint()
        ck["channel_values"] = {"messages": [HumanMessage("hola")]}
        mongo_checkpointer.put(cfg, ck, {}, {})
    for i in range(3):
        memory.save_memory(store, user, f"Dato {i} distinto")
    otro = uid("u")
    memory.save_memory(store, otro, "Dato ajeno")
    rep = ai_data.delete_user_ai_data(mongo_checkpointer, store, user, [t1, t2])
    assert rep == {"threads": 2, "memories": 3}
    assert mongo_checkpointer.get_tuple({"configurable": {"thread_id": t1}}) is None
    assert memory.list_memories(store, user) == [] and len(memory.list_memories(store, otro)) == 1
