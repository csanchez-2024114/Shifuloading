"""El conversation_id es el thread_id del checkpoint: un usuario no puede usar el de otro."""
from mongomock_motor import AsyncMongoMockClient

from app.routes.chat.chat import _owned_by_other
from app.services.chat_memory import CONTEXT


async def test_conversation_of_another_user_is_rejected():
    db = AsyncMongoMockClient()["t"]
    await db[CONTEXT].insert_one({"user_id": "ana", "conversation_id": "c1"})
    assert await _owned_by_other("c1", "beto", db) is True
    assert await _owned_by_other("c1", "ana", db) is False
    assert await _owned_by_other("nueva", "beto", db) is False  # conversacion nueva: se permite
