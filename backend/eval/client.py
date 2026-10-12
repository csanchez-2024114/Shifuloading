"""
eval/client.py — HTTP client wrapper for POST /api/v4/chat.

Performs Level 1 validation inline:
  - HTTP status == 200
  - Required fields: reply, conversation_id
  - Records response_time_ms
"""

import time
from dataclasses import dataclass, field

import httpx


@dataclass
class ChatResponse:
    reply: str
    conversation_id: str
    conversation_context: dict
    status_code: int
    duration_ms: int


class EvalClientError(Exception):
    def __init__(self, status_code: int, body: str):
        self.status_code = status_code
        self.body = body
        super().__init__(f"HTTP {status_code}: {body[:300]}")


_REQUIRED_FIELDS = ("reply", "conversation_id")


async def send_message(
    base_url: str,
    token: str,
    text: str,
    conversation_id: str,
    model: str = "gpt-4o-mini",
) -> ChatResponse:
    start = time.monotonic()

    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.post(
            f"{base_url}/api/v4/chat",
            json={"text": text, "conversation_id": conversation_id, "model": model},
            headers={"Authorization": f"Bearer {token}"},
        )

    duration_ms = int((time.monotonic() - start) * 1000)

    if resp.status_code != 200:
        raise EvalClientError(resp.status_code, resp.text)

    data = resp.json()

    missing = [f for f in _REQUIRED_FIELDS if not data.get(f)]
    if missing:
        raise EvalClientError(
            200,
            f"Response missing required fields: {missing}. Got: {list(data.keys())}",
        )

    return ChatResponse(
        reply=data["reply"],
        conversation_id=data["conversation_id"],
        conversation_context=data.get("conversation_context") or {},
        status_code=resp.status_code,
        duration_ms=duration_ms,
    )
