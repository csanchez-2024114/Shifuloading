"""Memoria del usuario: memory_learner escribe, los lectores lo traen y el prompt/juez lo reciben.
Usa mongomock-motor: el FakeDB de agente_v3 ignora los operadores ($inc, $setOnInsert, filtros)."""
import pytest
from langchain_core.messages import AIMessage, HumanMessage
from mongomock_motor import AsyncMongoMockClient

from app.agent.shared.helpers.identity_loader import build_system_messages
from app.agent.shared.memory import memory_learner as ml
from app.agent.shared.memory.episodic_memory_helper import load_episodic_memories
from app.agent.shared.memory.semantic_memory_helper import load_semantic_memories
from app.agent.shared.nodes import memory_updater
from app.agent.shared.nodes.memory_retriever import format_user_memory


@pytest.fixture
def db():
    return AsyncMongoMockClient()["t"]


def _fake(learned):
    async def f(model, prompt, exchange):
        f.prompt = prompt
        return learned
    return f


async def _learn(db, monkeypatch, learned, conv="c1"):
    monkeypatch.setattr(ml, "_extract", _fake(learned))
    return await ml.learn(db, user_id="u1", conversation_id=conv, user_text="x", reply="y", policy={})


async def test_learns_facts_and_activity_with_me_memories_schema(db, monkeypatch):
    learned = ml._Learned(
        facts=[ml._Fact(key="Role", value="contadora"), ml._Fact(key="tools", value="Google Sheets")],
        activity=ml._Activity(summary="reporte de nómina semanal", pending="elegir la hoja"),
    )
    out = await _learn(db, monkeypatch, learned)
    assert [f["key"] for f in out["facts"]] == ["role", "tools"]
    doc = await db[ml.FACTS].find_one({"user_id": "u1", "key": "role"})
    assert doc["value"] == "contadora" and doc["status"] == "active" and doc["mention_count"] == 1 and doc["created_at"]
    diary = await db[ml.DIARY].find_one({"user_id": "u1", "conversation_id": "c1"})
    assert diary["activities"] == ["reporte de nómina semanal"] and diary["pending"] == "elegir la hoja"

    # update reutiliza la llave; forget archiva (igual que DELETE /me/memories)
    await _learn(db, monkeypatch, ml._Learned(facts=[ml._Fact(key="role", value="contralora", action="update"),
                                                     ml._Fact(key="tools", value="", action="forget")]))
    assert await db[ml.FACTS].count_documents({"user_id": "u1", "key": "role"}) == 1
    assert (await db[ml.FACTS].find_one({"key": "role"}))["mention_count"] == 2
    assert (await db[ml.FACTS].find_one({"key": "tools"}))["status"] == "archived"
    assert [f["key"] for f in await load_semantic_memories(db, "u1")] == ["role"]

    # el modelo repite un hecho sin cambios: no se reescribe
    out = await _learn(db, monkeypatch, ml._Learned(facts=[ml._Fact(key="role", value="Contralora")]))
    assert out["facts"] == [] and (await db[ml.FACTS].find_one({"key": "role"}))["mention_count"] == 2


async def test_never_stores_credentials_even_if_model_returns_them(db, monkeypatch):
    await _learn(db, monkeypatch, ml._Learned(facts=[
        ml._Fact(key="gmail_password", value="abc123"),
        ml._Fact(key="note", value="mi contraseña es abc123"),
        ml._Fact(key="company", value="Despacho Ruiz"),
    ]))
    assert [d["key"] async for d in db[ml.FACTS].find({})] == ["company"]


async def test_known_facts_go_into_the_prompt(db, monkeypatch):
    await db[ml.FACTS].insert_one({"user_id": "u1", "key": "role", "value": "contadora", "status": "active"})
    fake = _fake(ml._Learned())
    monkeypatch.setattr(ml, "_extract", fake)
    await ml.learn(db, user_id="u1", conversation_id="c1", user_text="x", reply="y", policy={"remember": "SOLO ROL"})
    assert "role: contadora" in fake.prompt and "SOLO ROL" in fake.prompt


async def test_extract_failure_never_breaks_the_turn(db, monkeypatch):
    async def boom(*a):
        raise RuntimeError("openai caido")
    monkeypatch.setattr(ml, "_extract", boom)
    assert await ml.learn(db, user_id="u1", conversation_id="c1", user_text="x", reply="y", policy={}) == {"facts": [], "activity": None, "closed": []}


async def test_diary_excludes_current_conversation(db):
    from datetime import datetime
    for i, c in enumerate(["old", "cur", "new"]):
        await db[ml.DIARY].insert_one({"user_id": "u1", "conversation_id": c, "date": "2026-10-0%d" % i,
                                       "activities": [c], "updated_at": datetime(2026, 10, 1 + i)})
    rows = await load_episodic_memories(db, "u1", limit=3, exclude_conversation="cur")
    assert [r["conversation_id"] for r in rows] == ["new", "old"]


def test_format_and_prompt_block():
    text = format_user_memory({
        "semantic": [{"key": "role", "value": "contadora"}],
        "episodic": [{"date": "2026-10-09", "activities": ["reporte de nómina"], "pending": "elegir la hoja"}],
    })
    assert "role: contadora" in text and "reporte de nómina (pending: elegir la hoja)" in text
    assert format_user_memory({}) == ""
    msgs = build_system_messages({}, {}, is_first_turn=True, requirement_level=None, is_closing=False,
                                 user_name="Ana", user_memory=text)
    assert any("What you remember about the user" in m.content and "contadora" in m.content for m in msgs)


async def test_updater_skips_learning_on_system_event(monkeypatch):
    called = []

    async def fake_learn(*a, **k):
        called.append(1)
        return {}

    async def personality():
        return {}
    monkeypatch.setattr(memory_updater, "learn", fake_learn)
    monkeypatch.setattr(memory_updater, "get_agent_personality", personality)
    state = {"user_id": "u1", "conversation_id": "c1", "messages": [HumanMessage("[aviso]"), AIMessage("ok")]}
    await memory_updater._learn({**state, "system_event": True})
    assert called == []
    await memory_updater._learn(state)
    assert called == [1]


async def test_greeting_turns_do_not_overwrite_the_diary(db, monkeypatch):
    # al saludar el agente recuerda lo pendiente y el modelo lo copiaba como tarea nueva de ESTA conversacion
    learned = ml._Learned(activity=ml._Activity(summary="resumen de nomina", pending="conectar Gmail"))
    monkeypatch.setattr(ml, "_extract", _fake(learned))
    await ml.learn(db, user_id="u1", conversation_id="c2", user_text="hola", reply="Hola Ana, ¿seguimos con la nomina?",
                   policy={}, allow_activity=False)
    assert await db[ml.DIARY].count_documents({}) == 0


async def test_updater_blocks_activity_only_on_chat_intent(monkeypatch):
    seen = []

    async def fake_learn(*a, **k):
        seen.append(k["allow_activity"])
        return {}

    async def personality():
        return {}
    monkeypatch.setattr(memory_updater, "learn", fake_learn)
    monkeypatch.setattr(memory_updater, "get_agent_personality", personality)
    base = {"user_id": "u1", "conversation_id": "c1", "messages": [HumanMessage("x"), AIMessage("y")]}
    await memory_updater._learn({**base, "semantic_intake_debug": {"detected_intent": "chat"}})
    await memory_updater._learn({**base, "semantic_intake_debug": {"detected_intent": "create_workflow"}})
    assert seen == [False, True]


def test_earlier_conversations_are_oldest_first_and_facts_have_dates():
    from datetime import datetime
    text = format_user_memory({
        "semantic": [{"key": "tools", "value": "Excel", "last_seen_at": datetime(2026, 10, 9)}],
        "episodic": [{"date": "2026-10-10", "activities": ["recordatorio cada lunes"]},       # mas nueva primero (Mongo)
                     {"date": "2026-10-09", "activities": ["solicitudes de Gmail a la hoja Bodas"]}],
    })
    assert "tools: Excel (as of 2026-10-09)" in text
    assert text.index("solicitudes de Gmail") < text.index("recordatorio cada lunes") and "(oldest)" in text


# ── Recuerdo por significado de conversaciones viejas (parte A de la memoria global) ──────────────────────────────

from app.agent.shared.memory import message_index as mi  # noqa: E402
from app.agent.shared.memory.episodic_memory_helper import search_older, search_older_messages  # noqa: E402
from app.agent.shared.nodes import memory_retriever as mr  # noqa: E402


def _const_emb(vec):
    async def emb(text):
        return vec
    return emb


async def _messages(db, rows, user="u1"):
    for conv, emb, text in rows:
        await db[mi.INDEX].insert_one({"user_id": user, "conversation_id": conv, "date": "2026-09-03", "text": text,
                                       **({"embedding": emb} if emb else {})})


async def test_learner_stores_embedding_and_survives_embedding_failure(db, monkeypatch):
    seen = []

    async def emb(text):
        seen.append(text)
        return [1.0, 0.0]
    monkeypatch.setattr(ml, "embed_text", emb)
    learned = ml._Learned(activity=ml._Activity(summary="reporte de nómina", pending="elegir la hoja"))
    await _learn(db, monkeypatch, learned)
    assert seen == ["reporte de nómina elegir la hoja"]
    assert (await db[ml.DIARY].find_one({"conversation_id": "c1"}))["embedding"] == [1.0, 0.0]

    async def none(text):
        return None
    monkeypatch.setattr(ml, "embed_text", none)
    await _learn(db, monkeypatch, ml._Learned(activity=ml._Activity(summary="otra cosa")))
    doc = await db[ml.DIARY].find_one({"conversation_id": "c1"})
    assert doc["activities"] == ["otra cosa"] and "embedding" not in doc  # el embedding viejo ya no corresponde


async def _diary(db, rows):
    for conv, emb in rows:
        await db[ml.DIARY].insert_one({"user_id": "u1", "conversation_id": conv, "date": "2026-10-01",
                                       "activities": [conv], "pending": None, **({"embedding": emb} if emb else {})})


async def test_search_older_respects_exclude_min_score_top_k_and_hides_embedding(db):
    await _diary(db, [("exacta", [1, 0]), ("parecida", [0.8, 0.6]), ("lejana", [0, 1]), ("excluida", [1, 0]), ("sin_emb", None)])
    db_other = {"user_id": "otro", "conversation_id": "ajena", "activities": ["x"], "embedding": [1, 0]}
    await db[ml.DIARY].insert_one(db_other)

    rows = await search_older(db, "u1", [1, 0], {"excluida"}, top_k=5, min_score=0.5)
    assert [r["conversation_id"] for r in rows] == ["exacta", "parecida"]  # sin la excluida, la lejana, la sin embedding ni la ajena
    assert all("embedding" not in r and {"date", "activities", "pending", "score"} <= r.keys() for r in rows)
    assert len(await search_older(db, "u1", [1, 0], {"excluida"}, top_k=1, min_score=0.5)) == 1
    assert await search_older(db, "u1", [1, 0], set(), top_k=5, min_score=0.99) != []
    assert await search_older(db, "u1", [0.6, 0.8], {"exacta", "excluida"}, top_k=5, min_score=0.99) == []
    assert await search_older(db, "u1", None, set(), top_k=2, min_score=0.1) == []


async def test_recall_skips_trivial_messages_and_calls_search_otherwise(db, monkeypatch):
    calls = []

    async def emb(text):
        calls.append(text)
        return [1.0, 0.0]
    monkeypatch.setattr(mr, "embed_text", emb)
    await _diary(db, [("vieja", [1, 0]), ("reciente", [1, 0]), ("actual", [1, 0])])

    empty = {"diary": [], "messages": []}
    for trivial in ["hola", "ok", "muchas gracias", "hola, buenos días", "  ", ""]:
        assert await mr._recall(db, "u1", trivial, "actual", {}, {}) == empty
    assert calls == []

    memories = {"episodic": [{"conversation_id": "reciente"}]}
    rows = (await mr._recall(db, "u1", "¿qué hoja usamos para la nómina?", "actual", memories, {}))["diary"]
    assert [r["conversation_id"] for r in rows] == ["vieja"]  # ni la actual ni las que ya trajo la recencia

    assert await mr._recall(db, "u1", "¿qué hoja usamos para la nómina?", "actual", memories, {"recall": {"enabled": False}}) == empty
    assert len(calls) == 1


async def test_recall_failures_never_break_the_turn(db, monkeypatch):
    async def none(text):
        return None

    async def boom(text):
        raise RuntimeError("openai caido")
    empty = {"diary": [], "messages": []}
    for fn in (none, boom):
        monkeypatch.setattr(mr, "embed_text", fn)
        assert await mr._recall(db, "u1", "¿qué hoja usamos para la nómina?", "c", {}, {}) == empty

    async def emb(text):
        return [1.0]

    async def bad_search(*a, **k):
        raise RuntimeError("mongo caido")
    monkeypatch.setattr(mr, "embed_text", emb)
    monkeypatch.setattr(mr, "search_older", bad_search)
    monkeypatch.setattr(mr, "search_older_messages", bad_search)
    assert await mr._recall(db, "u1", "¿qué hoja usamos para la nómina?", "c", {}, {}) == empty

    # si falla solo una busqueda, la otra sigue entregando
    await _messages(db, [("vieja", [1, 0], "hoja Pedidos Navidad")])
    monkeypatch.setattr(mr, "search_older_messages", search_older_messages)  # la de diario sigue rota
    monkeypatch.setattr(mr, "embed_text", _const_emb([1.0, 0.0]))
    out = await mr._recall(db, "u1", "¿cómo se llamaba la hoja de pedidos?", "c", {}, {})
    assert out["diary"] == [] and [m["text"] for m in out["messages"]] == ["hoja Pedidos Navidad"]


async def test_retriever_node_puts_recalled_in_memory_and_prompt_block(db, monkeypatch):
    await _diary(db, [("vieja", [1, 0])])

    async def fake_retrieve(*a, **k):
        return {"goals": [], "semantic": [], "episodic": [], "decisions": [], "structured": {}}

    async def personality():
        return {"memory_policy": {"recall": {"min_score": 0.5}}}

    async def emb(text):
        return [1.0, 0.0]
    monkeypatch.setattr(mr, "retrieve_memories", fake_retrieve)
    monkeypatch.setattr(mr, "get_agent_personality", personality)
    monkeypatch.setattr(mr, "embed_text", emb)
    monkeypatch.setattr(mr.mongo_manager, "_db", db, raising=False)
    monkeypatch.setattr(type(mr.mongo_manager), "db", property(lambda self: db), raising=False)
    out = await mr.memory_retriever_node({"user_id": "u1", "conversation_id": "c9",
                                          "messages": [HumanMessage("¿en qué quedó mi reporte de nómina?")]})
    assert [r["conversation_id"] for r in out["raw_memories"]["recalled"]] == ["vieja"]
    assert "Older conversations that may be related" in out["user_memory_context"]


def test_format_renders_recalled_block():
    text = format_user_memory({"recalled": [{"date": "2026-09-01", "activities": ["alta de clientes en HubSpot"], "pending": "conectar HubSpot"},
                                            {"date": "2026-09-02", "activities": ["recordatorio lunes"]}]})
    assert "Older conversations that may be related (found by meaning; use only if relevant):" in text
    assert "- 2026-09-01: alta de clientes en HubSpot (pending: conectar HubSpot)" in text
    assert "- 2026-09-02: recordatorio lunes" in text
    assert "Older conversations" not in format_user_memory({"recalled": []})


# ── Mensajes originales del usuario (user_message_index) ──────────────────────────────────────────────────────────

async def test_search_older_messages_respects_exclude_min_score_top_k_and_hides_embedding(db):
    await _messages(db, [("c3", [1, 0], "hoja Pedidos Navidad"), ("c4", [0.8, 0.6], "pedidos de fin de año"),
                         ("c5", [0, 1], "otra cosa"), ("actual", [1, 0], "mensaje de ahora"), ("c6", None, "sin embedding")])
    await _messages(db, [("ajena", [1, 0], "de otro usuario")], user="otro")

    rows = await search_older_messages(db, "u1", [1, 0], {"actual"}, top_k=5, min_score=0.5)
    assert [r["text"] for r in rows] == ["hoja Pedidos Navidad", "pedidos de fin de año"]
    assert all("embedding" not in r and {"date", "text", "conversation_id", "score"} <= r.keys() for r in rows)
    assert len(await search_older_messages(db, "u1", [1, 0], {"actual"}, top_k=1, min_score=0.5)) == 1
    assert [r["conversation_id"] for r in await search_older_messages(db, "u1", [1, 0], set(), top_k=5, min_score=0.99)] == ["c3", "actual"]
    assert await search_older_messages(db, "u1", [0.6, 0.8], {"actual"}, top_k=5, min_score=0.99) == []
    assert await search_older_messages(db, "u1", None, set(), top_k=3, min_score=0.1) == []
    assert await search_older_messages(None, "u1", [1, 0], set()) == []


async def test_recall_reuses_one_query_embedding_for_both_searches(db, monkeypatch):
    calls = []

    async def emb(text):
        calls.append(text)
        return [1.0, 0.0]
    monkeypatch.setattr(mr, "embed_text", emb)
    await _diary(db, [("vieja", [1, 0])])
    await _messages(db, [("c3", [1, 0], "hoja Pedidos Navidad"), ("actual", [1, 0], "ahora")])
    out = await mr._recall(db, "u1", "¿cómo se llamaba la hoja de los pedidos?", "actual", {}, {})
    assert len(calls) == 1
    assert [r["conversation_id"] for r in out["diary"]] == ["vieja"]
    assert [m["conversation_id"] for m in out["messages"]] == ["c3"]  # la actual no entra

    # los umbrales y el top_k de los mensajes son datos
    await _messages(db, [("c7", [0.5, 0.87], "algo lejano")])
    cfg = {"recall": {"messages_top_k": 5, "messages_min_score": 0.4}}
    out = await mr._recall(db, "u1", "¿cómo se llamaba la hoja de los pedidos?", "actual", {}, cfg)
    assert [m["conversation_id"] for m in out["messages"]] == ["c3", "c7"]
    out = await mr._recall(db, "u1", "¿cómo se llamaba la hoja de los pedidos?", "actual", {}, {"recall": {"messages_top_k": 0}})
    assert out["messages"] == []


def test_format_renders_user_messages_block():
    long = "x" * 500
    text = format_user_memory({"recalled_messages": [{"date": "2026-09-03", "text": "empecé a llevar los pedidos en una hoja llamada Pedidos Navidad"},
                                                     {"date": "2026-09-04", "text": long}]})
    assert "What the user said in older conversations (found by meaning; use only if relevant):" in text
    assert '- 2026-09-03: "empecé a llevar los pedidos en una hoja llamada Pedidos Navidad"' in text
    assert f'- 2026-09-04: "{"x" * 300}"' in text and "x" * 301 not in text
    assert "What the user said" not in format_user_memory({"recalled_messages": []})


async def test_retriever_node_exposes_recalled_messages(db, monkeypatch):
    await _messages(db, [("c3", [1, 0], "empecé a llevar los pedidos en una hoja llamada Pedidos Navidad")])

    async def fake_retrieve(*a, **k):
        return {"goals": [], "semantic": [], "episodic": [], "decisions": [], "structured": {}}

    async def personality():
        return {}
    monkeypatch.setattr(mr, "retrieve_memories", fake_retrieve)
    monkeypatch.setattr(mr, "get_agent_personality", personality)
    monkeypatch.setattr(mr, "embed_text", _const_emb([1.0, 0.0]))
    monkeypatch.setattr(type(mr.mongo_manager), "db", property(lambda self: db), raising=False)
    out = await mr.memory_retriever_node({"user_id": "u1", "conversation_id": "c12",
                                          "messages": [HumanMessage("¿cómo se llamaba la hoja donde llevo los pedidos de navidad?")]})
    assert out["raw_memories"]["recalled_messages"][0]["conversation_id"] == "c3"
    assert "Pedidos Navidad" in out["user_memory_context"]


# ── Escritura: memory_updater._index ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def indexer(db, monkeypatch):
    calls = []

    async def emb(text):
        calls.append(text)
        return [1.0, 0.0]

    async def personality():
        return {}
    monkeypatch.setattr(mi, "embed_text", emb)
    monkeypatch.setattr(memory_updater, "get_agent_personality", personality)
    monkeypatch.setattr(type(memory_updater.mongo_manager), "db", property(lambda self: db), raising=False)
    return calls


def _state(text, **extra):
    return {"user_id": "u1", "conversation_id": "c3", "messages": [HumanMessage(text), AIMessage("ok")], **extra}


async def test_updater_indexes_a_normal_message(db, indexer):
    text = "empecé a llevar los pedidos en una hoja llamada Pedidos Navidad"
    assert await memory_updater._index(_state(text)) is True
    doc = await db[mi.INDEX].find_one({"user_id": "u1"})
    assert doc["text"] == text and doc["conversation_id"] == "c3" and doc["embedding"] == [1.0, 0.0]
    assert len(doc["date"]) == 10 and doc["created_at"]
    assert indexer == [text]  # un embedding por mensaje


async def test_updater_truncates_long_messages_to_1000_chars(db, indexer):
    await memory_updater._index(_state("palabra " * 300))
    assert len((await db[mi.INDEX].find_one({}))["text"]) <= 1000


@pytest.mark.parametrize("text,extra", [
    ("hola", {}), ("muchas gracias", {}), ("ok", {}),                                   # triviales
    ("mi contraseña de Gmail es abc123 para la hoja", {}), ("usa este token sk-abc para entrar", {}),  # credenciales
    ("mi tarjeta termina en 4242 y quiero pagar", {}),
    ("[aviso] la cuenta de Gmail quedó conectada ahora mismo", {"system_event": True}),  # evento / turno silent
])
async def test_updater_skips_trivial_credential_and_system_event(db, indexer, text, extra):
    assert await memory_updater._index(_state(text, **extra)) is False
    assert await db[mi.INDEX].count_documents({}) == 0 and indexer == []


async def test_updater_respects_policy_switches(db, indexer, monkeypatch):
    for policy in ({"memory_policy": {"enabled": False}}, {"memory_policy": {"recall": {"enabled": False}}},
                   {"memory_policy": {"recall": {"index_messages": False}}}):
        async def personality(p=policy):
            return p
        monkeypatch.setattr(memory_updater, "get_agent_personality", personality)
        assert await memory_updater._index(_state("quiero revisar la hoja de pedidos")) is False
    assert await db[mi.INDEX].count_documents({}) == 0


async def test_indexing_failures_never_break_the_turn(db, monkeypatch):
    async def boom(text):
        raise RuntimeError("openai caido")

    async def personality():
        return {}

    class BadDB:
        def __getitem__(self, name):
            raise RuntimeError("mongo caido")
    monkeypatch.setattr(memory_updater, "get_agent_personality", personality)
    monkeypatch.setattr(type(memory_updater.mongo_manager), "db", property(lambda self: db), raising=False)
    monkeypatch.setattr(mi, "embed_text", boom)
    assert await memory_updater._index(_state("quiero revisar la hoja de pedidos")) is False

    async def none(text):
        return None
    monkeypatch.setattr(mi, "embed_text", none)
    assert await memory_updater._index(_state("quiero revisar la hoja de pedidos")) is False
    assert await db[mi.INDEX].count_documents({}) == 0

    monkeypatch.setattr(mi, "embed_text", _const_emb([1.0]))
    assert await mi.index_message(BadDB(), user_id="u1", conversation_id="c", text="quiero revisar la hoja de pedidos") is False

    async def bad_personality():
        raise RuntimeError("mongo caido")
    monkeypatch.setattr(memory_updater, "get_agent_personality", bad_personality)
    assert await memory_updater._index(_state("quiero revisar la hoja de pedidos")) is False


async def test_node_runs_index_after_learning_without_breaking(db, indexer, monkeypatch):
    async def fake_learn(*a, **k):
        return {}
    monkeypatch.setattr(memory_updater, "learn", fake_learn)
    out = await memory_updater.memory_updater_node(_state("quiero revisar la hoja de pedidos"))
    assert out["decision_logged"] is False and await db[mi.INDEX].count_documents({}) == 1
