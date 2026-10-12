"""POST /me/feedback: solo en conversaciones propias; votar de nuevo reemplaza el voto."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routes.me import me


class _Col:
    def __init__(self, docs=None):
        self.docs = docs or []

    async def find_one(self, q, proj=None):
        return next((d for d in self.docs if all(d.get(k) == v for k, v in q.items())), None)

    async def update_one(self, q, upd, upsert=False):
        d = await self.find_one(q)
        if d is None:
            d = dict(q)
            self.docs.append(d)
        d.update(upd["$set"])


def _req(db):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(db=db)))


async def test_feedback_owner_only_and_upsert():
    db = {"chat_context": _Col([{"user_id": "u1", "conversation_id": "c1"}]), "message_feedback": _Col()}
    body = me._Feedback(conversation_id="c1", reply="hola", rating="down", comment="mal")
    await me.rate_reply(body, _req(db), {"id": "u1"})
    await me.rate_reply(body.model_copy(update={"rating": "up"}), _req(db), {"id": "u1"})
    assert [d["rating"] for d in db["message_feedback"].docs] == ["up"]
    with pytest.raises(HTTPException) as e:
        await me.rate_reply(body, _req(db), {"id": "otro"})
    assert e.value.status_code == 404
