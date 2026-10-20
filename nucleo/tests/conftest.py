"""Fixtures y utilidades compartidas. Nada de red externa: LLM falso, web search falso,
MongoDB local solo en la base `assistant_test`."""
import importlib
import json
import os
import re
import uuid

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk

MONGO_URI = os.environ.get("TEST_MONGODB_URI", "mongodb://127.0.0.1:27017")  # otra Mongo local sin tocar la del puerto por defecto
TEST_DB = "assistant_test"  # NUNCA "assistant"


# --------------------------------------------------------------------------- LLM falso
class FakeChat(GenericFakeChatModel):
    """Modelo falso: `bind_tools` devuelve self y el streaming soporta tool calls
    (GenericFakeChatModel no emite chunks si el contenido esta vacio)."""

    def bind_tools(self, tools, **kwargs):
        return self

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        msg = next(self.messages)
        if isinstance(msg, str):
            msg = AIMessage(content=msg)
        text = msg.content if isinstance(msg.content, str) else ""
        for piece in re.findall(r"\S+\s*", text):
            chunk = ChatGenerationChunk(message=AIMessageChunk(content=piece))
            if run_manager:
                run_manager.on_llm_new_token(piece, chunk=chunk)
            yield chunk
        tool_chunks = [
            {"name": tc["name"], "args": json.dumps(tc["args"]), "id": tc["id"],
             "index": i, "type": "tool_call_chunk"}
            for i, tc in enumerate(msg.tool_calls)
        ]
        yield ChatGenerationChunk(
            message=AIMessageChunk(content="", tool_call_chunks=tool_chunks, chunk_position="last")
        )


def tool_call(name: str, args: dict, call_id: str = "call_1") -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


def fake_llm(*responses) -> FakeChat:
    """Respuestas en orden: str (texto) o AIMessage (p. ej. `tool_call(...)`)."""
    return FakeChat(messages=iter(list(responses)))


# --------------------------------------------------------------------------- web search falso
class FakeSearch:
    def __init__(self, engine: str = "duckduckgo"):
        self.engine = engine
        self.calls: list[str] = []

    def __call__(self, query, settings):
        self.calls.append(query)
        return f"Resultado falso para {query}", self.engine


# --------------------------------------------------------------------------- utilidades
def uid(prefix: str = "t") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def build_test_agent(responses, settings, checkpointer=None, store=None, search_fn=None):
    """Agente real (create_agent) con LLM falso y web search falso."""
    tools_mod = importlib.import_module("assistant.tools")
    agent_mod = importlib.import_module("assistant.agent")
    llm = fake_llm(*responses)
    tools = tools_mod.build_tools(llm, settings, search_fn=search_fn or FakeSearch())
    return agent_mod.build_agent(llm, tools, settings, checkpointer=checkpointer, store=store)


def run_turn(agent, settings, text, thread_id, user_id="u1"):
    agent_mod = importlib.import_module("assistant.agent")
    payload = {"messages": [{"role": "user", "content": text}]}
    return list(agent_mod.stream_events(agent, payload, thread_id, user_id, settings))


def types(events):
    return [e["type"] for e in events]


# --------------------------------------------------------------------------- fixtures
@pytest.fixture(autouse=True)
def _env(monkeypatch):
    """Clave falsa y base de pruebas, para que ningun test toque OpenAI ni la base real."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake")
    monkeypatch.setenv("MONGODB_URI", MONGO_URI)
    monkeypatch.setenv("MONGODB_DB", TEST_DB)
    # TestClient manda Host: testserver (Settings.from_env en create_app sin settings)
    monkeypatch.setenv("TRUSTED_HOSTS", "localhost,127.0.0.1,testserver")


def _settings(**overrides):
    from assistant.config import Settings

    base = dict(
        openai_api_key="sk-test-fake",
        llm_model="gpt-6-luna",
        mongodb_uri=MONGO_URI,
        mongodb_db=TEST_DB,
        max_tokens=4000,
        recursion_limit=25,
        model_call_limit=15,
        memory_semantic=False,
        enable_hitl_demo=False,
        trusted_hosts=("localhost", "127.0.0.1", "testserver"),  # TestClient manda Host: testserver
    )
    base.update(overrides)
    return Settings(**base)


@pytest.fixture
def settings():
    return _settings()


@pytest.fixture
def hitl_settings():
    return _settings(enable_hitl_demo=True)


@pytest.fixture
def make_settings():
    return _settings


@pytest.fixture(scope="session")
def mongo_client():
    """MongoDB real, solo base `assistant_test`. Se salta si no hay conexion."""
    from assistant.config import ConfigError
    from assistant import memory

    try:
        client = memory.ping_mongo(MONGO_URI)
    except ConfigError as exc:
        pytest.skip(f"MongoDB local no disponible: {exc}")
    client.drop_database(TEST_DB)
    yield client
    client.drop_database(TEST_DB)
    client.close()


@pytest.fixture
def store(mongo_client):
    from assistant import memory

    return memory.build_store(mongo_client, TEST_DB)


@pytest.fixture
def mongo_checkpointer(mongo_client):
    from assistant import memory

    return memory.build_checkpointer(mongo_client, TEST_DB)
