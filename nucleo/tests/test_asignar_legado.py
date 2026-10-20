"""scripts/assign_legacy_data.py sobre una copia temporal (Mongo local: assistant_test y app_test). Dry-run por
defecto; con apply asigna hilos y COPIA recuerdos sin borrar nada, y no toca hilos de otro dueño."""
import importlib.util
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.base import empty_checkpoint

from conftest import uid

APP_TEST_DB = "app_test"
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "assign_legacy_data.py"


def _script():
    spec = importlib.util.spec_from_file_location("assign_legacy_data", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _thread(saver, tid, first):
    ck = empty_checkpoint()
    ck["channel_values"] = {"messages": [HumanMessage(first), AIMessage("respuesta")]}
    saver.put({"configurable": {"thread_id": tid, "checkpoint_ns": ""}}, ck, {}, {})


def test_dry_run_lista_y_apply_asigna_y_copia(mongo_client, mongo_checkpointer, store):
    from assistant import memory
    from assistant.appdata.mongo import MongoAppData
    from assistant.auth import AuthService
    from conftest import TEST_DB

    mongo_client.drop_database(APP_TEST_DB)
    try:
        app = MongoAppData(mongo_client, APP_TEST_DB)
        ai_db = mongo_client[TEST_DB]
        legado = uid("legado")
        t1, t2, ajeno = uid("t"), uid("t"), uid("t")
        _thread(mongo_checkpointer, t1, "Hola, quiero ideas para un viaje a Oaxaca en diciembre")
        _thread(mongo_checkpointer, t2, "Calcula el 15% de 2480")
        _thread(mongo_checkpointer, ajeno, "Hilo de otra persona")
        memory.save_memory(store, legado, "Vive en Mérida")
        memory.save_memory(store, legado, "Tiene una perrita llamada Canela")
        ana = AuthService(app).register("ana@ejemplo.com", "contraseña-larga-1", "Ana")
        otro = AuthService(app).register("otro@ejemplo.com", "contraseña-larga-2", "Otro")
        app.threads.create(ajeno, otro["user_id"], "Hilo de otra")
        s = _script()

        inv = s.inventory(ai_db, app)
        ids = {t["thread_id"]: t["owner"] for t in inv["threads"]}
        assert ids[t1] is None and ids[ajeno] == otro["user_id"] and inv["memories_by_legacy_user"][legado] == 2

        seco = s.assign(ai_db, mongo_checkpointer, app, "ana@ejemplo.com", legado, [t1, t2, ajeno], apply=False)
        assert seco["threads_assigned"] == [t1, t2] and seco["memories_copied"] == 2
        assert app.threads.get(t1) is None and memory.list_memories(store, ana["user_id"]) == []  # nada escrito

        hecho = s.assign(ai_db, mongo_checkpointer, app, "ANA@ejemplo.com", legado, [t1, t2, ajeno], apply=True)
        assert hecho["threads_skipped"] == [{"thread_id": ajeno, "reason": "ya tiene dueño"}]
        assert app.threads.get(t1)["user_id"] == ana["user_id"] and app.threads.get(t1)["title"].startswith("Hola, quiero")
        assert app.threads.get(ajeno)["user_id"] == otro["user_id"]  # no se toca
        copiados = sorted(m["text"] for m in memory.list_memories(store, ana["user_id"]))
        assert copiados == ["Tiene una perrita llamada Canela", "Vive en Mérida"]
        assert len(memory.list_memories(store, legado)) == 2  # copia: el original sigue

        otra_vez = s.assign(ai_db, mongo_checkpointer, app, "ana@ejemplo.com", legado, [t1], apply=True)
        assert otra_vez["memories_copied"] == 0 and otra_vez["memories_skipped"] == 2  # idempotente
        assert len(memory.list_memories(store, ana["user_id"])) == 2
    finally:
        mongo_client.drop_database(APP_TEST_DB)
