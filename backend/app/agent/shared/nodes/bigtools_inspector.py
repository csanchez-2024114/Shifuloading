"""
bigtools_inspector — agente_v3 validation layer

Runs AFTER catalog_checker + auth_validator complete (fan-in).
Only inspects apps that passed BOTH checks.

For each validated app:
  - Loads available tool names from BIGTOOLS_REGISTRY
  - Uses gpt-4o-mini to match user intent → tools and detect missing parameters

Writes to validation_reports + missing_variables.
"""

import json
import logging
import os

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from langchain_core.runnables import RunnableConfig

from app.agent.shared.helpers.bigtools_registry import load_tools_context
from app.agent.shared.context.geo_context import build_geo_block
from app.agent.shifu_base_v1.graph.state import ShifuState
from app.agent.shared.utils.log_utils import DEV_MODE, dev_print

logger = logging.getLogger(__name__)

_INSPECTOR_SYSTEM = """\
You are the BigTools Inspector for Shifu, an AI workflow automation assistant.

Given the user's intent and the available tools for each validated app, determine:
1. Whether the intent can be mapped to available tools
2. What critical parameters are missing to build the automation (e.g. repo name, sheet ID, email address)

Return ONLY valid JSON:
{
  "can_proceed": true | false,
  "tool_mapping": [
    {"step": 1, "app": "<app>", "tool": "<tool_name>", "purpose": "<brief description>"}
  ],
  "missing_variables": ["<param1>", "<param2>"],
  "notes": "<brief explanation if can_proceed is false>"
}

Rules:
- can_proceed = true if at least one tool matches the intent
- missing_variables: only list parameters CRITICAL for execution (not optional ones)
- If the app has no tools yet (empty list), can_proceed = false with explanation
"""


def _parse(raw: str) -> dict:
    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {}


def _dev_box(validated: list, structured: str, result: dict) -> None:
    tool_mapping  = result.get("tool_mapping") or []
    missing       = result.get("missing_variables") or []
    can_proceed   = result.get("can_proceed", False)
    notes         = result.get("notes", "")

    mapping_fmt = "\n│             ".join(
        f"step {t.get('step')}: [{t.get('app')}] {t.get('tool')} — {t.get('purpose', '')}"
        for t in tool_mapping
    ) or "(none)"

    dev_print(
        f"\n┌─ BigTools Inspector ───────────────────────────────────────\n"
        f"│ apps        : {validated}\n"
        f"│ intent      : {structured[:100]}{'...' if len(structured) > 100 else ''}\n"
        f"│ can_proceed : {can_proceed}\n"
        f"│ tool_map    : {mapping_fmt}\n"
        f"│ missing     : {missing}\n"
        + (f"│ notes       : {notes}\n" if notes else "")
        + f"└────────────────────────────────────────────────────────────"
    )


_DEFAULT_INSPECTOR_MODEL = "gpt-4o-mini"
_llm = ChatOpenAI(model=_DEFAULT_INSPECTOR_MODEL, temperature=0, max_tokens=400, timeout=30).with_retry(
    stop_after_attempt=3, wait_exponential_jitter=True
)


async def bigtools_inspector_node(state: ShifuState, config: RunnableConfig = None) -> dict:
    cfg = (config or {}).get("configurable", {})
    inspector_model = cfg.get("inspector_model", _DEFAULT_INSPECTOR_MODEL)
    # Use module-level singleton unless the caller requests a different model
    llm = _llm if inspector_model == _DEFAULT_INSPECTOR_MODEL else \
          ChatOpenAI(model=inspector_model, temperature=0, max_tokens=400, timeout=30).with_retry(
              stop_after_attempt=3, wait_exponential_jitter=True
          )
    reports       = state.get("validation_reports") or []
    structured    = state.get("structured_prompt") or ""
    apps_involved = state.get("apps_involved") or []

    logger.info("[bigtools_inspector] ▶ apps_involved=%s  reports_so_far=%d",
                apps_involved, len(reports))

    if not apps_involved:
        logger.info("[bigtools_inspector] skip — no apps_involved")
        return {}

    # Find apps that passed BOTH catalog AND auth
    catalog_ok = {r["app"] for r in reports if r.get("source") == "catalog" and r.get("status") == "ok"}
    auth_ok    = {r["app"] for r in reports if r.get("source") == "auth"    and r.get("status") == "ok"}
    validated  = sorted(catalog_ok & auth_ok)

    logger.info("[bigtools_inspector] catalog_ok=%s  auth_ok=%s  → validated=%s",
                sorted(catalog_ok), sorted(auth_ok), validated)

    if not validated:
        logger.info("[bigtools_inspector] skip — no apps passed both catalog + auth")
        return {}

    tools_context = await load_tools_context(validated)
    geo_block = build_geo_block(
        state.get("user_timezone"),
        state.get("user_location"),
        state.get("user_country_code"),
    )
    # Fix #11: use last HumanMessage as fallback when structured_prompt is None
    fallback_prompt = next(
        (m.content for m in reversed(state.get("messages") or []) if isinstance(m, HumanMessage)),
        "",
    )
    intent_section = f"USER INTENT:\n{structured or fallback_prompt}"
    user_prompt = (
        f"{geo_block}\n\n{intent_section}" if geo_block else intent_section
    ) + f"\n\nVALIDATED APPS AND THEIR TOOLS:\n{tools_context}"

    logger.info("[bigtools_inspector] calling LLM for tool mapping (apps=%s)...", validated)

    try:
        resp = await llm.ainvoke([
            SystemMessage(content=_INSPECTOR_SYSTEM),
            HumanMessage(content=user_prompt),
        ])
        result = _parse(resp.content or "")
    except Exception as exc:
        logger.error("[bigtools_inspector] LLM failed: %s", exc)
        return {}

    if not result:
        logger.error("[bigtools_inspector] empty LLM parse result")
        return {}

    can_proceed  = result.get("can_proceed", False)
    missing      = [str(v) for v in (result.get("missing_variables") or [])]
    tool_mapping = result.get("tool_mapping") or []
    notes        = result.get("notes", "")

    if DEV_MODE:
        _dev_box(validated, structured, result)

    if can_proceed:
        report = {
            "source": "bigtools", "status": "ok",
            "apps": validated, "tool_mapping": tool_mapping,
        }
        logger.info("[bigtools_inspector] ◀ can_proceed=True  tool_steps=%d  missing=%s",
                    len(tool_mapping), missing)
    else:
        report = {
            "source": "bigtools", "status": "error",
            "apps": validated, "message": notes or "Cannot map intent to available tools",
        }
        logger.info("[bigtools_inspector] ◀ can_proceed=False  notes=%r", notes)

    return {
        "validation_reports": [report],
        "missing_variables":  missing,
    }

