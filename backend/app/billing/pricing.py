"""Costo en USD de una llamada a un modelo, a partir de app/billing/model_prices.json (los precios son datos, no codigo)."""
import json
from functools import lru_cache
from pathlib import Path
from typing import Optional


@lru_cache(maxsize=1)
def _prices() -> dict:
    return json.loads((Path(__file__).with_name("model_prices.json")).read_text(encoding="utf-8"))["usd_per_1m_tokens"]


def price_for(model: str) -> Optional[dict]:
    """Precio de un modelo. Acepta nombres con fecha ('gpt-4o-mini-2024-07-18') usando el prefijo mas largo que coincida."""
    prices = _prices()
    if model in prices:
        return prices[model]
    match = max((k for k in prices if (model or "").startswith(k)), key=len, default=None)
    return prices[match] if match else None


def cost_usd(model: str, input_tokens: int, output_tokens: int, cached_tokens: int = 0) -> Optional[float]:
    """None si el modelo no esta en la tabla (no se inventa un precio). cached_tokens va incluido en input_tokens."""
    p = price_for(model)
    if p is None:
        return None
    fresh = max(input_tokens - cached_tokens, 0)
    return (fresh * p["input"] + cached_tokens * p.get("cached_input", p["input"]) + output_tokens * p["output"]) / 1_000_000
