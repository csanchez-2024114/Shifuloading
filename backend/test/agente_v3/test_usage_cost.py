"""Costo real por peticion: tokens que reporta el proveedor x precios de app/billing/model_prices.json."""
import asyncio

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from app.billing.pricing import cost_usd, price_for
from app.routes.chat.chat import _ChatStreamer


def _result(input_tokens, output_tokens, model="gpt-4o-mini", cached=0):
    meta = {"input_tokens": input_tokens, "output_tokens": output_tokens, "total_tokens": input_tokens + output_tokens}
    if cached:
        meta["input_token_details"] = {"cache_read": cached}
    return LLMResult(generations=[[ChatGeneration(message=AIMessage(content="x", usage_metadata=meta, response_metadata={"model_name": model}))]])


def test_price_lookup_accepts_dated_model_names_and_never_invents_one():
    assert price_for("gpt-4o-mini-2024-07-18")["input"] == 0.15
    assert price_for("gpt-4.1-nano-2025-04-14")["input"] == 0.10
    assert price_for("modelo-que-no-existe") is None and cost_usd("modelo-que-no-existe", 10, 10) is None


def test_heavy_models_are_not_in_the_price_table_so_any_use_shows_up_as_unpriced():
    # decision del proyecto: solo gpt-4o-mini y gpt-4.1-nano. Si algo llamara a un modelo grande, el costo lo marcaria "sin precio".
    for heavy in ("gpt-4o", "gpt-4o-2024-08-06", "gpt-4.1", "gpt-4.1-2025-04-14"):
        assert price_for(heavy) is None, heavy


def test_cost_formula_and_cached_tokens():
    assert cost_usd("gpt-4o-mini", 2000, 300) == pytest.approx((2000 * 0.15 + 300 * 0.60) / 1e6)
    # 1000 de los 2000 de entrada vinieron de cache (mitad de precio): se cobran aparte, sin contarse dos veces
    assert cost_usd("gpt-4o-mini", 2000, 0, cached_tokens=1000) == pytest.approx((1000 * 0.15 + 1000 * 0.075) / 1e6)


async def test_streamer_records_real_usage_per_call_and_sums_the_request():
    s = _ChatStreamer(asyncio.Queue())  # sin trace: el costo se mide siempre
    for run_id, node, model, i, o in (("a", "semantic_intake", "gpt-4o-mini", 2900, 230), ("b", "response_evaluator", "gpt-4.1-nano", 2300, 300)):
        await s.on_chat_model_start({}, [[]], run_id=run_id, metadata={"langgraph_node": node}, invocation_params={"model_name": model})
        await s.on_llm_end(_result(i, o, model), run_id=run_id)
    u = s.usage()
    assert [c["node"] for c in u["calls"]] == ["semantic_intake", "response_evaluator"]
    assert u["input"] == 5200 and u["output"] == 530 and u["unpriced"] == 0
    assert u["usd"] == pytest.approx(cost_usd("gpt-4o-mini", 2900, 230) + cost_usd("gpt-4.1-nano", 2300, 300), abs=1e-6)


async def test_a_model_without_a_price_is_counted_but_not_priced():
    s = _ChatStreamer(asyncio.Queue())
    await s.on_chat_model_start({}, [[]], run_id="a", metadata={"langgraph_node": "responder"}, invocation_params={"model_name": "modelo-nuevo"})
    await s.on_llm_end(_result(100, 50, "modelo-nuevo"), run_id="a")
    u = s.usage()
    assert u["usd"] == 0 and u["unpriced"] == 1 and u["calls"][0]["usd"] is None


def test_no_calls_means_no_usage():
    assert _ChatStreamer(asyncio.Queue()).usage() is None
