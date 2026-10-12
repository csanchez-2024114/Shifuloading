import asyncio
from types import SimpleNamespace

# Lightweight stubs to avoid hitting external LLM/OpenAI during tests.
# These are intentionally permissive: they return an object with a `.content`
# attribute which existing code calls like `(await llm.ainvoke(prompt)).content`.

async def _fake_ainvoke(self, prompt, *args, **kwargs):
    try:
        # Try to produce a useful short reply based on prompt text
        if isinstance(prompt, str):
            txt = prompt[:120]
        else:
            txt = str(prompt)[:120]
    except Exception:
        txt = "DUMMY"
    return SimpleNamespace(content=str(txt))

def _fake_invoke(self, prompt, *args, **kwargs):
    return SimpleNamespace(content=str(prompt) if isinstance(prompt, str) else "DUMMY")

def _fake_agenerate(self, prompts, *args, **kwargs):
    return SimpleNamespace(content=(prompts[0] if isinstance(prompts, (list, tuple)) else prompts))

def _fake_generate(self, prompts, *args, **kwargs):
    return SimpleNamespace(content=(prompts[0] if isinstance(prompts, (list, tuple)) else prompts))


# Apply best-effort monkeypatches to common entrypoints used by LangChain / LangGraph
def _patch_langchain_models():
    try:
        import langchain_core.language_models.chat_models as lc_chat
        lc_chat.ChatModel.ainvoke = _fake_ainvoke
        lc_chat.ChatModel.invoke = _fake_invoke
        lc_chat.ChatModel.agenerate = _fake_agenerate
        lc_chat.ChatModel.generate = _fake_generate
    except Exception:
        pass

    try:
        import langchain_openai.chat_models.base as lc_openai
        lc_openai.ChatOpenAI.ainvoke = _fake_ainvoke
        lc_openai.ChatOpenAI.invoke = _fake_invoke
        lc_openai.ChatOpenAI.agenerate = _fake_agenerate
        lc_openai.ChatOpenAI.generate = _fake_generate
    except Exception:
        pass


def _patch_openai_sdk():
    try:
        import openai

        def _openai_create(*args, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="DUMMY"))], content=None)

        async def _openai_acreate(*args, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="DUMMY"))], content=None)

        # Patch common callpaths used in older/newer SDKs
        if hasattr(openai, "ChatCompletion"):
            openai.ChatCompletion.create = _openai_create
            try:
                openai.ChatCompletion.acreate = _openai_acreate
            except Exception:
                pass

        try:
            # some code uses openai.chat.completions.create
            if hasattr(openai, "chat") and hasattr(openai.chat, "completions"):
                openai.chat.completions.create = _openai_create
        except Exception:
            pass

    except Exception:
        pass


# Run patches eagerly when tests import this conftest
_patch_langchain_models()
_patch_openai_sdk()


# Also provide an autouse fixture to ensure third-party classes created later are patched
import pytest


@pytest.fixture(autouse=True, scope="session")
def ensure_patches():
    _patch_langchain_models()
    _patch_openai_sdk()
    yield


# ── Network guard — second-line safety net ────────────────────────────────────
# Blocks real HTTP calls to OpenAI/Tavily so no test can accidentally burn tokens.
# The patches above cover LangChain entry points; this guard covers any path that
# escapes to raw httpx (e.g. a new ChatOpenAI instance bypassing the class patch).

def _install_network_guard():
    try:
        import httpx

        _original_send = httpx.AsyncClient.send

        async def _guard_send(self, request, *args, **kwargs):
            host = getattr(request.url, "host", "") or ""
            if "openai" in host or "tavily" in host:
                raise AssertionError(
                    f"Real HTTP call blocked in test: {request.url}\n"
                    "Add a mock for this node's LLM or API call."
                )
            return await _original_send(self, request, *args, **kwargs)

        httpx.AsyncClient.send = _guard_send
    except Exception:
        pass


_install_network_guard()


@pytest.fixture(autouse=True, scope="session")
def ensure_network_guard():
    _install_network_guard()
    yield
