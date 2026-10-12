"""Panel de metricas: la agregacion pura (listas de documentos) y la ruta con mongomock."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.database import get_current_user, get_db
from app.routes.dev import metrics as mt

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)


def _msg(usd, version="v1", conv="c1", attempts=1, rejections=0, final="approved", failed=(), at=NOW):
    q = {"attempts": attempts, "rejections": rejections, "final": final,
         "evals": [{"failed": [{"name": n, "note": ""} for n in failed]}]}
    return {"conversation_id": conv, "created_at": at, "content": "respuesta",
            "usage": {"usd": usd, "agent_version": version} if version else {"usd": usd}, "quality": q}


def _row(out, key, value):
    return next(r for r in out[key] if r.get("version", r.get("day")) == value)


def test_costs_rates_and_top_failing_per_version():
    msgs = [
        _msg(0.01), _msg(0.02, attempts=2, rejections=1, failed=("grounded", "tone")),
        _msg(0.03, attempts=3, rejections=2, final="exhausted", failed=("grounded",)), _msg(0.10),
    ]
    r = _row(mt.aggregate(msgs, [], []), "by_version", "v1")
    assert r["replies"] == 4 and r["usd_total"] == 0.16 and r["usd_avg"] == 0.04
    assert r["usd_p95"] == 0.10  # con 4 datos el p95 por rango mas cercano es el mayor
    assert r["attempts_avg"] == 1.75
    assert r["rejection_rate"] == 50.0 and r["exhausted_rate"] == 25.0
    assert r["top_failing"][0] == {"name": "grounded", "count": 2}


def test_missing_fields_are_tolerated_and_grouped_without_version():
    msgs = [{"conversation_id": "c", "created_at": NOW}, _msg(0.01, version=None), {"usage": None, "quality": None}]
    out = mt.aggregate(msgs, [{"rating": "up"}], [{"ok": True}])
    r = _row(out, "by_version", mt.NO_VERSION)
    assert r["replies"] == 3 and r["attempts_avg"] == 1.0 and r["up"] == 1 and r["writes"] == 1


def test_feedback_joins_by_version_and_day():
    fb = [
        {"rating": "up", "agent_version": "v1", "updated_at": NOW},
        {"rating": "down", "agent_version": "v1", "updated_at": NOW, "comment": "mal"},
        {"rating": "up", "agent_version": "v2", "updated_at": NOW - timedelta(days=1)},
    ]
    out = mt.aggregate([_msg(0.01, "v1"), _msg(0.01, "v2")], fb, [])
    v1 = _row(out, "by_version", "v1")
    assert (v1["up"], v1["down"], v1["up_pct"]) == (1, 1, 50.0)
    assert _row(out, "by_version", "v2")["up_pct"] == 100.0
    assert _row(out, "by_day", "2026-10-09")["up"] == 1


def test_actions_take_version_of_previous_reply_in_conversation():
    msgs = [_msg(0.01, "v1", conv="a", at=NOW), _msg(0.01, "v2", conv="a", at=NOW + timedelta(hours=1))]
    acts = [
        {"conversation_id": "a", "ok": True, "via": "assumed", "ts": NOW + timedelta(minutes=5)},
        {"conversation_id": "a", "ok": False, "via": "confirmed", "ts": NOW + timedelta(hours=2)},
        {"conversation_id": "a", "ok": True, "via": "confirmed", "ts": NOW + timedelta(hours=2)},
    ]
    out = mt.aggregate(msgs, [], acts)
    assert _row(out, "by_version", "v1")["writes"] == 1 and _row(out, "by_version", "v1")["assumed"] == 1
    v2 = _row(out, "by_version", "v2")
    assert (v2["writes"], v2["writes_ok_pct"], v2["confirmed"]) == (2, 50.0, 2)


def test_recent_down_only_with_comment_newest_first_and_capped():
    fb = [{"rating": "down", "comment": f"c{i}", "agent_version": "v1", "conversation_id": "c1",
           "updated_at": NOW + timedelta(minutes=i), "reply": "x" * 500} for i in range(25)]
    fb += [{"rating": "down", "comment": "  ", "updated_at": NOW}, {"rating": "up", "comment": "bien", "updated_at": NOW}]
    down = mt.aggregate([], fb, [])["recent_down"]
    assert len(down) == 20 and down[0]["comment"] == "c24" and len(down[0]["reply"]) == 200


def test_route_reads_mongo_and_filters_by_days(monkeypatch):
    monkeypatch.delenv("ADMIN_EMAILS", raising=False)
    monkeypatch.setenv("SHIFU_DEV_UI", "1")  # sin lista de admins, el modo local deja pasar
    db = AsyncMongoMockClient()["t"]
    now = datetime.now(timezone.utc)
    app = FastAPI()
    app.include_router(mt.router, prefix="/api/v1/dev")
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1"}
    app.dependency_overrides[get_db] = lambda: db

    import asyncio
    asyncio.run(db["chat_messages"].insert_many([
        {"role": "ai", **_msg(0.05, "v1", at=now)},
        {"role": "ai", **_msg(0.05, "v1", at=now - timedelta(days=30))},   # fuera del rango
        {"role": "user", "content": "hola", "created_at": now},          # no es respuesta del agente
    ]))
    out = TestClient(app).get("/api/v1/dev/metrics?days=7").json()
    assert out["truncated"] is False and out["by_version"][0]["replies"] == 1


def test_admin_in_list_is_allowed_case_insensitive(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", " Alan@X.com , otro@x.com ")
    mt._require_admin({"email": "alan@x.COM"})  # no lanza


def test_user_not_in_list_gets_403(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "alan@x.com")
    monkeypatch.setenv("SHIFU_DEV_UI", "1")  # aunque sea local, con lista manda la lista
    with pytest.raises(HTTPException) as e:
        mt._require_admin({"correo": "otro@x.com"})
    assert e.value.status_code == 403


def test_empty_list_with_dev_ui_allows_any_user(monkeypatch):
    monkeypatch.delenv("ADMIN_EMAILS", raising=False)
    monkeypatch.setenv("SHIFU_DEV_UI", "1")
    mt._require_admin({"email": "cualquiera@x.com"})  # no lanza


def test_empty_list_without_dev_ui_gets_403(monkeypatch):
    monkeypatch.delenv("ADMIN_EMAILS", raising=False)
    monkeypatch.delenv("SHIFU_DEV_UI", raising=False)
    with pytest.raises(HTTPException) as e:
        mt._require_admin({"email": "alan@x.com"})
    assert e.value.status_code == 403
