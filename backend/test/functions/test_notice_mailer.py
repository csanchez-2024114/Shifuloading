"""Avisos por correo (v0.7.2): apagado por defecto, un correo por usuario, tope diario y respeto a la preferencia."""
from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId
from mongomock_motor import AsyncMongoMockClient

from app.workers import notice_mailer

NOW = datetime(2026, 10, 12, 15, 0, tzinfo=timezone.utc)


@pytest.fixture
def env(monkeypatch):
    sent = []
    monkeypatch.setenv("SHIFU_NOTICE_EMAILS", "1")
    monkeypatch.setattr(notice_mailer, "validate_smtp_config", lambda: None)
    monkeypatch.setattr(notice_mailer, "send_smtp_email", lambda to, subject, body: sent.append((to, subject, body)) or True)
    return sent


async def _seed(db, *notices, **user):
    uid = (await db["users"].insert_one({"email": "ana@empresa.test", "name": "Ana", **user})).inserted_id
    for n in notices:
        await db["user_notifications"].insert_one({"user_id": str(uid), "read": False, "created_at": NOW, "title": "Workflow falló",
                                                   "message": "A falló", "type": "run_failed", **n})
    return str(uid)


def _db():
    return AsyncMongoMockClient()["t"]


async def test_off_by_default_and_without_smtp(env, monkeypatch):
    db = _db()
    await _seed(db, {})
    monkeypatch.delenv("SHIFU_NOTICE_EMAILS")
    assert await notice_mailer.tick(db, NOW) == 0 and env == []
    monkeypatch.setenv("SHIFU_NOTICE_EMAILS", "1")

    def no_smtp():
        raise ValueError("falta SMTP")
    monkeypatch.setattr(notice_mailer, "validate_smtp_config", no_smtp)
    assert await notice_mailer.tick(db, NOW) == 0 and env == []
    assert await db["user_notifications"].count_documents({"emailed_at": {"$ne": None}}) == 0  # nada marcado: saldra despues


async def test_one_email_per_user_with_all_pending_notices_and_never_twice(env):
    db = _db()
    await _seed(db, {}, {"type": "commitment_due", "title": "Vence hoy", "message": "nómina"},
                {"type": "run_completed", "title": "ok"},                      # tipo que no se manda
                {"read": True},                                                # ya lo leyo en la app
                {"created_at": NOW - timedelta(days=3)})                       # viejo
    assert await notice_mailer.tick(db, NOW) == 1
    to, subject, body = env[0]
    assert to == "ana@empresa.test" and subject == "Shifu: Tienes 2 avisos de Shifu"
    assert "A falló" in body and "nómina" in body and "Hola, Ana" in body
    assert await notice_mailer.tick(db, NOW) == 0 and len(env) == 1


async def test_user_who_turned_them_off_gets_nothing(env):
    db = _db()
    await _seed(db, {}, email_notices=False)
    assert await notice_mailer.tick(db, NOW) == 0 and env == []


async def test_daily_cap_keeps_the_rest_in_the_app(env, monkeypatch):
    monkeypatch.setenv("SHIFU_NOTICE_EMAIL_DAILY_CAP", "1")
    db = _db()
    uid = await _seed(db, {})
    assert await notice_mailer.tick(db, NOW) == 1
    await db["user_notifications"].insert_one({"user_id": uid, "read": False, "created_at": NOW, "title": "t", "message": "otro", "type": "run_failed"})
    assert await notice_mailer.tick(db, NOW + timedelta(minutes=1)) == 0 and len(env) == 1


async def test_failed_send_is_not_retried(env, monkeypatch):
    monkeypatch.setattr(notice_mailer, "send_smtp_email", lambda *a: False)
    db = _db()
    await _seed(db, {})
    assert await notice_mailer.tick(db, NOW) == 0
    assert (await db["user_notifications"].find_one({}))["email_error"] is True
    assert await db["notice_emails"].count_documents({}) == 0


async def test_unknown_user_id_does_not_break_the_tick(env):
    db = _db()
    await db["user_notifications"].insert_one({"user_id": "no-es-un-id", "read": False, "created_at": NOW, "title": "t", "message": "m", "type": "run_failed"})
    await db["user_notifications"].insert_one({"user_id": str(ObjectId()), "read": False, "created_at": NOW, "title": "t", "message": "m", "type": "run_failed"})
    assert await notice_mailer.tick(db, NOW) == 0 and env == []
