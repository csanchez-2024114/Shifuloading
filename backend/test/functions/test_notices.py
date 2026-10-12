"""Avisos (v0.7.1): recordatorio de compromisos y avisos que el agente cuenta una sola vez."""
from datetime import datetime, timezone

from mongomock_motor import AsyncMongoMockClient

from app.agent.shared.nodes.memory_retriever import format_user_memory
from app.services.notification_service import create_notification, take_untold
from app.workers import reminder_loop

NOW = datetime(2026, 10, 12, 15, 0, tzinfo=timezone.utc)


def _db():
    return AsyncMongoMockClient()["t"]


async def test_reminder_notifies_once_for_what_is_due_and_skips_done_future_and_stale():
    db = _db()
    await db["user_daily_diary"].insert_many([
        {"user_id": "u1", "activities": ["entregar la nomina"], "pending": "revisar totales", "due_date": "2026-10-12"},
        {"user_id": "u1", "activities": ["reporte"], "pending": "enviarlo", "due_date": "2026-10-10"},                 # vencido hace 2 dias
        {"user_id": "u1", "activities": ["ya hecho"], "pending": "x", "due_date": "2026-10-12", "done_at": NOW},
        {"user_id": "u1", "activities": ["futuro"], "pending": "x", "due_date": "2026-10-20"},
        {"user_id": "u1", "activities": ["viejo"], "pending": "x", "due_date": "2026-08-01"},
        {"user_id": "u1", "activities": ["sin fecha"], "pending": "x", "due_date": None},
    ])
    assert await reminder_loop.tick(db, NOW) == 2
    assert await reminder_loop.tick(db, NOW) == 0  # no repite
    rows = await db["user_notifications"].find({}).to_list(10)
    assert sorted(r["title"] for r in rows) == ["Compromiso vencido", "Vence hoy"]
    assert all(r["type"] == "commitment_due" and r["user_id"] == "u1" and not r["read"] for r in rows)


async def test_take_untold_returns_each_notice_once_and_only_the_asked_types():
    db = _db()
    await create_notification(db, "u1", "run_failed", "Workflow falló", "A falló")
    await create_notification(db, "u1", "run_completed", "Workflow completado", "B terminó")
    await create_notification(db, "u2", "run_failed", "Workflow falló", "de otro usuario")
    got = await take_untold(db, "u1", ["run_failed", "trigger_disabled"])
    assert [n["message"] for n in got] == ["A falló"] and set(got[0]) == {"type", "title", "message", "date"}  # solo texto (checkpoint)
    assert await take_untold(db, "u1", ["run_failed", "trigger_disabled"]) == []
    assert await db["user_notifications"].count_documents({"user_id": "u1", "read": False}) == 2  # siguen sin leer en su lista


def test_notices_block_is_painted_before_commitments():
    text = format_user_memory({"notices": [{"message": "A falló", "date": "2026-10-12"}],
                               "commitments": [{"activities": ["nomina"], "pending": "revisar", "due_date": "2026-10-12", "days_left": 0}]})
    assert "- 2026-10-12: A falló" in text and text.index("Notices the user has NOT seen") < text.index("Commitments with a date")
    assert "Notices" not in format_user_memory({"notices": []})


async def test_a_new_notice_is_also_pushed_live(monkeypatch):
    seen = []

    async def fake(user_id, event):
        seen.append((user_id, event))
    monkeypatch.setattr("app.utils.events.publish_user_event", fake)
    await create_notification(_db(), "u1", "trigger_disabled", "Workflow detenido", "X se detuvo")
    assert seen == [("u1", {"type": "notification", "notification_type": "trigger_disabled", "title": "Workflow detenido", "message": "X se detuvo"})]
