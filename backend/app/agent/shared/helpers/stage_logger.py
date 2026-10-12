"""
stage_logger — agente_v3

Structured console audit for the Stage lifecycle (dev mode only).
Guards every function with DEV_MODE so there is zero overhead in production.

Lifecycle phases:
  CREATED   — semantic_intake detected a workflow intent (apps_involved non-empty)
  UPDATED   — responder aggregation produced a new requirement_level
  SUSPENDED — aggregation returned level_1 (errors / pending account selection)
  COMPLETED — aggregation returned level_2 (all validations passed)
"""

import os

from app.agent.shared.utils.log_utils import DEV_MODE, dev_print
_LINE = "─" * 63


def _print_box(title: str, lines: list[str]) -> None:
    header = f"┌─ {title} "
    pad = _LINE[len(header) - 1:]
    body = "\n".join(f"│  {line}" for line in lines)
    dev_print(f"\n{header}{pad}\n{body}\n└{_LINE}")


def log_stage_created(session_id: str, intent: str, apps: list[str]) -> None:
    if not DEV_MODE:
        return
    _print_box(
        "SHIFU STAGE — CREATED",
        [
            f"Session  : {session_id}",
            f"Node     : semantic_intake",
            f"Intent   : {intent}",
            f"Apps     : {apps}",
        ],
    )


def log_stage_updated(
    session_id: str,
    old_level: str | None,
    new_level: str,
    reason: str,
) -> None:
    if not DEV_MODE:
        return
    old_label = old_level or "none"
    _print_box(
        "SHIFU STAGE — UPDATED",
        [
            f"Session    : {session_id}",
            f"Transition : [{old_label}] ──► [{new_level}]",
            f"Reason     : {reason}",
        ],
    )


def log_stage_suspended(
    session_id: str,
    current_level: str,
    reason: str,
    wait_for: list[str],
) -> None:
    if not DEV_MODE:
        return
    _print_box(
        "SHIFU STAGE — SUSPENDED",
        [
            f"Session  : {session_id}",
            f"Status   : Paused on [{current_level}]",
            f"Reason   : {reason}",
            f"Wait For : {wait_for}",
        ],
    )


def log_stage_completed(session_id: str, apps: list[str]) -> None:
    if not DEV_MODE:
        return
    _print_box(
        "SHIFU STAGE — COMPLETED",
        [
            f"Session  : {session_id}",
            f"Apps     : {apps}",
            f"Status   : All validations passed — ready for workflow planner",
        ],
    )

