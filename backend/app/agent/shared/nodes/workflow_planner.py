"""
workflow_planner — deliberative planning node

Runs AFTER bigtools_inspector, BEFORE responder.

Separates the cognitive load of the responder into two phases:
  1. Planning (this node): given validated tools + intent, generate a private
     step-by-step execution trace — never shown to the user.
  2. Synthesis (responder): reads the planning_trace as a binding blueprint
     and focuses solely on natural language generation.

Skip conditions (returns {"planning_trace": None}):
  - No apps_involved → pure chat turn, nothing to plan.
  - No bigtools report with status="ok" → validation failed, responder handles it.

Model: gpt-4o-mini, temp=0 — deterministic, structured reasoning only.
"""

import logging
import os

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.agent.shifu_base_v1.graph.state import ShifuState
from app.agent.shared.utils.log_utils import DEV_MODE, dev_print

logger = logging.getLogger(__name__)

_PLANNER_SYSTEM = """\
You are a silent execution planner for an AI workflow automation system.
Given the user's intent and the validated tool mapping, generate a concise \
step-by-step execution plan.

Focus on:
1. Execution order and data dependencies between steps
2. Required parameters per step — flag any that are missing or ambiguous
3. Write-risk operations (create, update, delete, send) that need user confirmation
4. Any constraint violations or prerequisite gaps you detect

Rules:
- Output plain text only. No markdown headers, no JSON, no conversational language.
- This plan is strictly internal — the user never sees it.
- Be terse: one line per step maximum.
- End with a one-line RECOMMENDATION to the responder (what to ask/do next).
"""

_llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0,
    max_tokens=500,
    timeout=30,
).with_retry(stop_after_attempt=3, wait_exponential_jitter=True)


def _extract_tool_mapping(validation_reports: list) -> list:
    for r in validation_reports:
        if r.get("source") == "bigtools" and r.get("status") == "ok":
            return r.get("tool_mapping") or []
    return []


def _dev_box(structured: str, tool_mapping: list, trace: str) -> None:
    steps = "\n│  ".join(
        f"step {t.get('step')}: [{t.get('app')}] {t.get('tool')} — {t.get('purpose', '')}"
        for t in tool_mapping
    ) or "(none)"
    trace_preview = trace[:200] + ("..." if len(trace) > 200 else "")
    dev_print(
        f"\n┌─ Workflow Planner ─────────────────────────────────────────\n"
        f"│ intent    : {structured[:100]}{'...' if len(structured) > 100 else ''}\n"
        f"│ tools     : {steps}\n"
        f"│ trace     :\n│  {trace_preview}\n"
        f"└────────────────────────────────────────────────────────────"
    )


async def workflow_planner_node(state: ShifuState) -> dict:
    apps_involved      = state.get("apps_involved") or []
    validation_reports = state.get("validation_reports") or []

    if not apps_involved:
        logger.info("[workflow_planner] skip — no apps_involved (pure chat)")
        return {"planning_trace": None}

    tool_mapping = _extract_tool_mapping(validation_reports)
    if not tool_mapping:
        logger.info("[workflow_planner] skip — no bigtools ok report (validation failed or no tools)")
        return {"planning_trace": None}

    structured     = state.get("structured_prompt") or ""
    missing_vars   = state.get("missing_variables") or []
    curated        = state.get("curated_research") or ""

    steps_block = "\n".join(
        f"Step {t.get('step')}: [{t.get('app')}] {t.get('tool')} — {t.get('purpose', '')}"
        for t in tool_mapping
    )
    missing_block = f"\nMISSING PARAMETERS: {missing_vars}" if missing_vars else ""
    research_block = f"\nCONTEXT FROM RESEARCH:\n{curated[:600]}" if curated else ""

    user_prompt = (
        f"USER INTENT:\n{structured}\n\n"
        f"VALIDATED TOOL MAPPING:\n{steps_block}"
        f"{missing_block}"
        f"{research_block}"
    )

    logger.info("[workflow_planner] calling LLM — apps=%s  steps=%d", apps_involved, len(tool_mapping))

    try:
        resp = await _llm.ainvoke([
            SystemMessage(content=_PLANNER_SYSTEM),
            HumanMessage(content=user_prompt),
        ])
        trace = (resp.content or "").strip()
    except Exception as exc:
        logger.error("[workflow_planner] LLM failed: %s — skipping trace", exc)
        return {"planning_trace": None}

    if DEV_MODE:
        _dev_box(structured, tool_mapping, trace)

    logger.info("[workflow_planner] trace generated (%d chars)", len(trace))
    return {"planning_trace": trace}
