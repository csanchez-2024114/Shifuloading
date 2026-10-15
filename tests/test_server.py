import json

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from conftest import build_test_agent, uid


@pytest.fixture
def client(settings):
    from assistant import server

    agent = build_test_agent(["Hola desde el servidor"], settings, checkpointer=InMemorySaver())
    with TestClient(server.create_app(agent=agent)) as c:
        yield c


def _sse_events(response):
    events = []
    for block in response.text.split("\n\n"):
        block = block.strip()
        if block:
            assert block.startswith("data: "), block
            events.append(json.loads(block[len("data: "):]))
    return events


def test_index_devuelve_html(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "<html" in r.text.lower()


def test_chat_stream_sse_y_history(client):
    thread = uid()
    r = client.post("/chat", json={"message": "hola", "thread_id": thread, "user_id": "u1"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")

    events = _sse_events(r)
    kinds = [e["type"] for e in events]
    assert "token" in kinds
    assert events[-1] == {"type": "done", "thread_id": thread}

    h = client.get(f"/history/{thread}")
    assert h.status_code == 200
    body = h.json()
    assert body["thread_id"] == thread
    assert body["messages"] == [
        {"role": "user", "content": "hola"},
        {"role": "assistant", "content": "Hola desde el servidor"},
    ]


def test_history_thread_inexistente_vacio(client):
    body = client.get(f"/history/{uid('nuevo')}").json()
    assert body["messages"] == []


def test_health(client):
    body = client.get("/health").json()
    assert body["ok"] is True and "model" in body
