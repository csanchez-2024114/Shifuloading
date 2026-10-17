"""Aislamiento entre las dos bases (Mongo local: IA en assistant_test, negocio en app_test). Con 2 usuarios y varias
conversaciones: ninguna colección de la IA contiene correos, hashes de contraseña ni nombres de usuario; ninguna
colección de negocio contiene mensajes, resúmenes ni recuerdos. Sin tokens: modelo falso."""
from conftest import FakeChat
from test_propiedad import PW, _app, _chat, _login

APP_TEST_DB = "app_test"


def _texts(value) -> list[str]:
    """Todo el texto de un documento, incluido el de los campos binarios: los checkpoints van en msgpack, que guarda
    las cadenas en claro (UTF-8) dentro de los bytes."""
    if isinstance(value, dict):
        return [t for k, v in value.items() for t in [str(k), *_texts(v)]]
    if isinstance(value, (list, tuple)):
        return [t for v in value for t in _texts(v)]
    if isinstance(value, (bytes, bytearray)):
        return [bytes(value).decode("utf-8", errors="ignore")]
    return [str(value)]


def _dump(db) -> dict[str, str]:
    return {name: "\n".join(t for doc in db[name].find() for t in _texts(doc)) for name in db.list_collection_names()}


def test_ninguna_base_guarda_lo_de_la_otra(make_settings, mongo_client, mongo_checkpointer, store):
    from assistant.appdata.mongo import MongoAppData
    from conftest import TEST_DB

    mongo_client.drop_database(APP_TEST_DB)
    try:
        appdata = MongoAppData(mongo_client, APP_TEST_DB)
        resumidor = FakeChat(messages=iter(["- El usuario saludó y envió mensajes de relleno."] * 50))
        app, *_ = _app(make_settings, appdata=appdata, checkpointer=mongo_checkpointer, store=store,
                       summarizer=resumidor, summary_trigger_tokens=600, summary_keep_tokens=250, memory_summarize=True)
        usuarios = [("zacarias.prueba@ejemplo.com", "Zacarías Pruebaúnica"), ("wenceslaa.test@ejemplo.com", "Wenceslaa Testeo")]
        hechos = ["guarda: Vive en Tlacotalpan junto al río", "guarda: Colecciona trompos de madera tallada"]
        relleno = " ".join(["relleno para que el hilo crezca y se resuma."] * 12)
        for (email, nombre), hecho in zip(usuarios, hechos):
            c = _login(app, email, nombre)
            for _ in range(2):  # varias conversaciones por usuario
                tid = c.post("/threads").json()["thread_id"]
                _chat(c, tid, "Hola, buenos días")
                _chat(c, tid, hecho)
                for i in range(4):
                    _chat(c, tid, f"Mensaje {i}. {relleno}")

        ai = _dump(mongo_client[TEST_DB])
        assert {"checkpoints", "checkpoint_writes", "memories"} <= set(ai)
        hashes = [u["password_hash"] for u in mongo_client[APP_TEST_DB]["users"].find()]
        prohibidos = [e for e, _ in usuarios] + [n for _, n in usuarios] + hashes + ["argon2id", PW]
        for col, texto in ai.items():
            for p in prohibidos:
                assert p not in texto, f"la base de la IA ({col}) contiene {p[:20]}…"
        assert any("Tlacotalpan" in t for t in ai.values())  # control: los mensajes sí están en la IA
        assert "Summary of the OLDEST part" in ai["checkpoints"] + ai["checkpoint_writes"]  # hubo resumen

        negocio = _dump(mongo_client[APP_TEST_DB])
        assert set(negocio) <= {"users", "sessions", "threads", "login_attempts", "login_locks", "password_resets"}
        for col, texto in negocio.items():
            for p in ["Tlacotalpan", "trompos", "relleno para que", "Summary of the OLDEST", "messages",
                      "memories", "Vive en", "buenos días, "]:
                assert p not in texto, f"la base de negocio ({col}) contiene {p!r}"
        titulos = [t["title"] for t in mongo_client[APP_TEST_DB]["threads"].find()]
        assert titulos == ["Hola, buenos días"] * 4  # solo las primeras palabras del primer mensaje
    finally:
        mongo_client.drop_database(APP_TEST_DB)
