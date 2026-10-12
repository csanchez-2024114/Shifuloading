"""Memoria global, parte B: compromisos con fecha (due_date), reloj del turno, cierre y bloque de lectura.
Usa mongomock-motor: el FakeDB de agente_v3 ignora los operadores de los filtros."""
from datetime import datetime, timezone

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from mongomock_motor import AsyncMongoMockClient

from app.agent.shared.memory import memory_learner as ml
from app.agent.shared.memory.episodic_memory_helper import load_commitments, parse_now
from app.agent.shared.nodes import memory_updater
from app.agent.shared.nodes.memory_retriever import format_user_memory
from app.routes.chat import chat

MONDAY = datetime(2026, 10, 12, 15, 0, tzinfo=timezone.utc)
SATURDAY = datetime(2026, 10, 17, 15, 0, tzinfo=timezone.utc)


@pytest.fixture
def db():
    return AsyncMongoMockClient()["t"]


def _fake(learned):
    async def f(model, prompt, exchange):
        f.prompt = prompt
        return learned
    return f


async def _learn(db, monkeypatch, learned, *, user="u1", conv="c1", now=MONDAY, policy=None):
    fake = _fake(learned)
    monkeypatch.setattr(ml, "_extract", fake)

    async def no_embedding(text):
        return None
    monkeypatch.setattr(ml, "embed_text", no_embedding)
    out = await ml.learn(db, user_id=user, conversation_id=conv, user_text="x", reply="y", policy=policy or {}, now=now)
    return out, fake


def _commit(due, **kw):
    return ml._Learned(activity=ml._Activity(summary="nómina de 5 empleados", pending="entregar la nómina", due_date=due, **kw))


async def test_due_date_is_stored_and_prompt_carries_today_with_weekday(db, monkeypatch):
    out, fake = await _learn(db, monkeypatch, _commit("2026-10-16"))
    assert out["activity"]["due_date"] == "2026-10-16"
    assert (await db[ml.DIARY].find_one({"conversation_id": "c1"}))["due_date"] == "2026-10-16"
    # la fecha relativa se resuelve contra el reloj del turno, no contra datetime.now
    assert "TODAY: 2026-10-12 (Monday)" in fake.prompt


async def test_invalid_or_pending_less_due_date_is_dropped(db, monkeypatch):
    await _learn(db, monkeypatch, _commit("el viernes"))
    assert (await db[ml.DIARY].find_one({"conversation_id": "c1"}))["due_date"] is None
    learned = ml._Learned(activity=ml._Activity(summary="charla de nómina", due_date="2026-10-16"))  # sin pending
    await _learn(db, monkeypatch, learned, conv="c2")
    assert (await db[ml.DIARY].find_one({"conversation_id": "c2"}))["due_date"] is None


async def test_disabled_commitments_ignore_due_date_and_closed(db, monkeypatch):
    await db[ml.DIARY].insert_one({"user_id": "u1", "conversation_id": "old", "pending": "x", "due_date": "2026-10-16"})
    learned = _commit("2026-10-16")
    learned.closed = ["old"]
    out, fake = await _learn(db, monkeypatch, learned, policy={"commitments": {"enabled": False}})
    assert out["activity"]["due_date"] is None and out["closed"] == []
    assert "old: x" not in fake.prompt and "done_at" not in await db[ml.DIARY].find_one({"conversation_id": "old"})


async def test_open_commitments_from_other_conversations_go_into_the_prompt(db, monkeypatch):
    await _learn(db, monkeypatch, _commit("2026-10-16"), conv="nomina")
    _, fake = await _learn(db, monkeypatch, ml._Learned(), conv="otra", now=SATURDAY)
    assert "nomina: entregar la nómina — 2026-10-16" in fake.prompt
    _, fake = await _learn(db, monkeypatch, ml._Learned(), conv="nomina", now=SATURDAY)  # la propia no se ofrece
    assert "nomina: entregar" not in fake.prompt


async def test_closed_marks_done_only_for_offered_ids_of_the_same_user(db, monkeypatch):
    await _learn(db, monkeypatch, _commit("2026-10-16"), conv="nomina")
    await _learn(db, monkeypatch, _commit("2026-10-16"), conv="ajena", user="otro")

    out, _ = await _learn(db, monkeypatch, ml._Learned(closed=["nomina", "ajena", "inventada"]), conv="hoy", now=SATURDAY)
    assert out["closed"] == ["nomina"]
    mine = await db[ml.DIARY].find_one({"user_id": "u1", "conversation_id": "nomina"})
    assert mine["pending"] is None and mine["done_at"] == SATURDAY.replace(tzinfo=None)
    other = await db[ml.DIARY].find_one({"user_id": "otro", "conversation_id": "ajena"})
    assert other["pending"] == "entregar la nómina" and "done_at" not in other
    assert await load_commitments(db, "u1", SATURDAY, 3) == []


async def test_closing_works_even_when_the_turn_is_a_greeting(db, monkeypatch):
    await _learn(db, monkeypatch, _commit("2026-10-16"), conv="nomina")
    monkeypatch.setattr(ml, "_extract", _fake(ml._Learned(activity=ml._Activity(summary="x"), closed=["nomina"])))
    out = await ml.learn(db, user_id="u1", conversation_id="hoy", user_text="sí, ya la entregué", reply="ok", policy={},
                         allow_activity=False, now=SATURDAY)
    assert out["closed"] == ["nomina"] and out["activity"] is None


async def test_load_commitments_filters_and_sorts(db):
    d = lambda conv, due, pending="tarea", user="u1", **kw: db[ml.DIARY].insert_one(  # noqa: E731
        {"user_id": user, "conversation_id": conv, "activities": [conv], "pending": pending, "due_date": due, **kw})
    await d("vencida", "2026-10-14")
    await d("hoy", "2026-10-17")
    await d("pronto", "2026-10-19")
    await d("lejana", "2026-10-25")            # fuera del horizonte
    await d("cerrada", "2026-10-15", done_at=SATURDAY)
    await d("sin_pendiente", "2026-10-15", pending=None)
    await d("sin_fecha", None)
    await d("actual", "2026-10-16")
    await d("ajena", "2026-10-15", user="otro")
    await d("rota", "viernes")

    rows = await load_commitments(db, "u1", SATURDAY, 3, exclude_conversation="actual")
    assert [r["conversation_id"] for r in rows] == ["vencida", "hoy", "pronto"]
    assert [r["days_left"] for r in rows] == [-3, 0, 2]
    assert all("done_at" not in r and "_id" not in r for r in rows)
    assert "lejana" in [r["conversation_id"] for r in await load_commitments(db, "u1", SATURDAY, 30)]
    assert await load_commitments(None, "u1", SATURDAY) == []


async def test_load_commitments_caps_at_five(db):
    for i in range(8):
        await db[ml.DIARY].insert_one({"user_id": "u1", "conversation_id": f"c{i}", "pending": "t", "due_date": f"2026-10-1{i}"})
    rows = await load_commitments(db, "u1", SATURDAY, 30)
    assert [r["conversation_id"] for r in rows] == ["c0", "c1", "c2", "c3", "c4"]


def test_format_renders_overdue_today_and_upcoming():
    text = format_user_memory({"commitments": [
        {"pending": "entregar la nómina", "activities": ["nómina de 5 empleados"], "due_date": "2026-10-16", "days_left": -1},
        {"pending": "pagar el IVA", "activities": ["impuestos"], "due_date": "2026-10-10", "days_left": -7},
        {"pending": "llamar al banco", "activities": [], "due_date": "2026-10-17", "days_left": 0},
        {"pending": "enviar catálogo", "activities": ["catálogo"], "due_date": "2026-10-19", "days_left": 2},
        {"pending": "revisar", "activities": ["x"], "due_date": "2026-10-18", "days_left": 1},
    ]})
    assert "Commitments with a date:" in text
    # El compromiso primero y el paso despues (fecha_v054e: con el paso primero el saludo preguntaba por el paso).
    assert "- nómina de 5 empleados — due 2026-10-16 (overdue 1 day); next step was: entregar la nómina" in text
    assert "- impuestos — due 2026-10-10 (overdue 7 days); next step was: pagar el IVA" in text
    assert "- llamar al banco — due 2026-10-17 (today)" in text
    assert "- catálogo — due 2026-10-19 (in 2 days); next step was: enviar catálogo" in text
    assert "(in 1 day)" in text
    assert "Commitments" not in format_user_memory({"commitments": []})


def test_parse_now():
    assert parse_now("2026-10-17T15:00:00Z") == SATURDAY
    assert parse_now("2026-10-17T15:00:00") == SATURDAY
    assert abs((parse_now(None) - datetime.now(timezone.utc)).total_seconds()) < 5
    assert abs((parse_now("basura") - datetime.now(timezone.utc)).total_seconds()) < 5


async def test_updater_passes_the_turn_clock_to_the_learner(monkeypatch):
    seen = []

    async def fake_learn(*a, **k):
        seen.append(k["now"])
        return {}

    async def personality():
        return {}
    monkeypatch.setattr(memory_updater, "learn", fake_learn)
    monkeypatch.setattr(memory_updater, "get_agent_personality", personality)
    state = {"user_id": "u1", "conversation_id": "c1", "messages": [HumanMessage("x"), AIMessage("y")],
             "current_time_utc": "2026-10-17T15:00:00Z"}
    await memory_updater._learn(state)
    assert seen == [SATURDAY]


# ── Reloj simulado en el chat (solo desarrollo) ───────────────────────────────────────────────────────────────────

@pytest.fixture
def chat_stubs(monkeypatch):
    async def prefs(user_id, db):
        return "", "UTC"

    async def name(user_id, db):
        return "Ana"
    monkeypatch.setattr(chat, "load_user_prefs_block", prefs)
    monkeypatch.setattr(chat, "_load_user_name", name)


async def _clock(now_override):
    state, _ = await chat._build_input("u1", "c1", "hola", "m", "low", None, None, save_user_message=False,
                                       now_override=now_override)
    return state["current_time_utc"]


async def test_now_override_only_applies_with_dev_ui(chat_stubs, monkeypatch):
    monkeypatch.setenv("SHIFU_DEV_UI", "1")
    assert await _clock("2026-10-17T15:00:00Z") == "2026-10-17T15:00:00Z"
    assert await _clock("2026-10-17T10:00:00-05:00") == "2026-10-17T15:00:00Z"
    assert (await _clock("basura")).startswith(str(datetime.now(timezone.utc).year))  # ilegible: reloj real

    monkeypatch.delenv("SHIFU_DEV_UI")
    assert await _clock("2026-10-17T15:00:00Z") != "2026-10-17T15:00:00Z"
    monkeypatch.setenv("SHIFU_DEV_UI", "0")
    assert await _clock("2026-10-17T15:00:00Z") != "2026-10-17T15:00:00Z"
