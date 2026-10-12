"""
WorkflowExecutor — runs a single workflow_run document step by step.

Execution flow:
  run → running → [step: pending → running → completed/failed] → completed/failed

Step types:
  action    (default) — calls a BigTool with the step's config
  foreach   — iterates a JSON array and calls the action for each item
  condition — evaluates a field and optionally stops remaining steps

On full failure, the parent workflow is flagged as requires_attention.
"""

import asyncio
import inspect
import json
import logging
import os
import re as _re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import redis.asyncio as aioredis
from motor.motor_asyncio import AsyncIOMotorDatabase

from config import Config
from app.services.workflow_run_service import update_run_status, update_step_status
from app.services.workflow_service import (
    update_workflow_status,
    get_workflow_state,
    save_workflow_state,
)
from app.services.workflow_analytics_service import save_run_analytics
from app.services.audit_service import log_event as _audit
from app.services.rate_limit_service import check_tool_rate_limit
from app.utils.events import publish_user_event

logger = logging.getLogger(__name__)

# Workflow execution lifecycle stages (workflow_runs collection status field)
WORKFLOW_RUN_STAGES = frozenset({
    "pending",           # queued, not yet started
    "running",           # actively executing steps
    "completed",         # all steps succeeded (or condition stopped early)
    "failed",            # all steps failed OR critical step failed
    "execution_failed",  # failed after retries exhausted — retry path still available
    "paused",            # waiting for external input
    "cancelled",         # explicitly cancelled
})

_COL_INTENT_OUTCOMES = "intent_outcomes"
_COL_WORKFLOW_RUNS = "workflow_runs"
_SUSPICIOUS_RUN_THRESHOLD = int(os.getenv("SUSPICIOUS_RUN_THRESHOLD", "20"))
_STEP_TIMEOUT_SECONDS = int(os.getenv("STEP_TIMEOUT_SECONDS", "120"))

# Circuit breaker + tool outcome logging
_CB_THRESHOLD = int(os.getenv("CIRCUIT_BREAKER_THRESHOLD", "5"))
_CB_COOLDOWN_SECONDS = int(os.getenv("CIRCUIT_BREAKER_COOLDOWN_SECONDS", "300"))
_CB_COUNTER_TTL = 3600  # 1-hour sliding window for consecutive-failure counter
_COL_TOOL_OUTCOME_LOG = "tool_outcome_log"
_TOOL_RETRY_MAX = int(os.getenv("TOOL_MAX_RETRIES", "1"))
_TOOL_RETRY_DELAY = float(os.getenv("TOOL_RETRY_DELAY_SECONDS", "2.0"))
_TRANSIENT_KEYWORDS = (
    "rate limit", "too many requests", "service unavailable",
    "gateway timeout", "temporarily", "retry after", "quota exceeded",
)

# step_N admite una ruta dentro de la salida: campo (.rows), indice ([0] o .0) y combinaciones (rows[0][0]); las salidas
# de las funciones son anidadas y el planificador escribe esas rutas.
_VAR_RE = _re.compile(
    r"\{\{(step_(\d+)((?:\.\w+|\[\d+\])*)|state\.(\w+)|item(?:\.(\w+))?|trigger(?:\.(\w+))?)\}\}"
)
_PATH_TOKEN_RE = _re.compile(r"\.(\w+)|\[(\d+)\]")
_MISSING = object()


def _walk_path(data: Any, path: str) -> Any:
    """Sigue una ruta (".rows[0][0]", ".header.1") dentro de dict/list. _MISSING si algun tramo no existe."""
    for key, idx in _PATH_TOKEN_RE.findall(path or ""):
        if isinstance(data, dict) and key in data:
            data = data[key]
        elif isinstance(data, list) and (idx or key.isdigit()) and int(idx or key) < len(data):
            data = data[int(idx or key)]
        else:
            return _MISSING
    return data


# ── Circuit breaker + outcome helpers ────────────────────────────────────────

def _is_transient_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    if any(c in msg for c in ("429", "503", "502", "504")):
        return True
    return any(kw in msg for kw in _TRANSIENT_KEYWORDS)


async def _log_tool_outcome(
    db: AsyncIOMotorDatabase,
    user_id: str,
    action: str,
    success: bool,
    error_msg: Optional[str],
    duration_ms: int,
) -> None:
    """Writes one doc to tool_outcome_log. Never raises — logging must not block execution."""
    try:
        now = datetime.now(timezone.utc)
        await db[_COL_TOOL_OUTCOME_LOG].insert_one({
            "user_id": user_id,
            "action": action,
            "success": success,
            "error_msg": error_msg,
            "duration_ms": duration_ms,
            "timestamp": now,
            "ttl": now + timedelta(days=30),
        })
    except Exception:
        pass


async def _update_circuit_breaker(user_id: str, action: str, redis_url: str) -> None:
    """Increments the failure counter; opens the breaker when _CB_THRESHOLD is reached."""
    try:
        r = aioredis.from_url(redis_url, decode_responses=True)
        counter_key = f"circuit_breaker_fails:{user_id}:{action}"
        count = await r.incr(counter_key)
        await r.expire(counter_key, _CB_COUNTER_TTL)
        if count >= _CB_THRESHOLD:
            await r.set(
                f"circuit_breaker:{user_id}:{action}", "1", ex=_CB_COOLDOWN_SECONDS
            )
            logger.warning(
                "[CircuitBreaker] OPEN for user=%s action=%s (consecutive_fails=%d, cooldown=%ds)",
                user_id, action, count, _CB_COOLDOWN_SECONDS,
            )
        await r.aclose()
    except aioredis.RedisError:
        pass


async def _reset_circuit_breaker(user_id: str, action: str, redis_url: str) -> None:
    """Clears the failure counter and any open breaker key on success."""
    try:
        r = aioredis.from_url(redis_url, decode_responses=True)
        await r.delete(
            f"circuit_breaker_fails:{user_id}:{action}",
            f"circuit_breaker:{user_id}:{action}",
        )
        await r.aclose()
    except aioredis.RedisError:
        pass


class WorkflowExecutor:
    def __init__(self, run: dict, db: AsyncIOMotorDatabase, dry_run: bool = False):
        self.run = run
        self.run_id: str = run.get("_id", "dry-run")
        self.user_id: str = run["user_id"]
        self.user_email: str = run.get("user_email", "")
        self.workflow_id: str = run["workflow_id"]
        self.workflow_name: str = run.get("workflow_name", "")
        self.db = db
        self.dry_run = dry_run
        self._redis: Optional[aioredis.Redis] = None
        self._redis_channel = f"wf:{self.user_id}"

    # ── Public entry point ────────────────────────────────────────────────────

    async def execute(self):
        if Config.REDIS_URL:
            self._redis = aioredis.from_url(Config.REDIS_URL, decode_responses=True)
        try:
            await self._run()
        finally:
            if self._redis:
                await self._redis.aclose()

    async def _run(self):
        from bson import ObjectId

        state = await get_workflow_state(self.workflow_id, self.db)

        # Load workflow document for metrics schema, charts config, and webhook URL
        try:
            wf_doc = await self.db["workflows"].find_one(
                {"_id": ObjectId(self.workflow_id)}
            ) or {}
        except Exception:
            wf_doc = {}
        metrics_schema: list = wf_doc.get("metrics", [])
        webhook_url: str = wf_doc.get("webhook_url", "")

        now = datetime.now(timezone.utc)
        await update_run_status(
            self.run_id, "running", self.db, extra={"started_at": now}
        )
        _audit(
            self.user_id, "workflow_run_started", self.workflow_id, self.db,
            extra={"run_id": self.run_id, "workflow_name": self.workflow_name},
        )
        await self._emit(
            {
                "type": "run_started",
                "run_id": self.run_id,
                "workflow_id": self.workflow_id,
                "workflow_name": self.workflow_name,
                "timestamp": now.isoformat(),
            }
        )

        steps = sorted(self.run.get("steps", []), key=lambda s: s.get("order", 0))
        steps_by_order: Dict[int, dict] = {s.get("order", 0): s for s in steps}
        failed = 0
        step_results: Dict[int, str] = {}
        stop_execution = False
        completed_steps_stack: list[dict] = []  # for compensation on failure

        # Track which step to execute next (supports branch jumps)
        pending_orders = [s.get("order", 0) for s in steps]
        executed_orders: set[int] = set()

        i = 0
        while i < len(pending_orders):
            if stop_execution:
                break
            order = pending_orders[i]
            if order in executed_orders:
                i += 1
                continue
            executed_orders.add(order)
            step = steps_by_order.get(order)
            if step is None:
                i += 1
                continue

            step_type = step.get("type", "action")
            if step_type == "condition":
                should_continue, jump_to = await self._execute_condition_branching(
                    step, step_results, state
                )
                if jump_to is not None:
                    # Insert jump_to at next position if not already queued
                    if jump_to not in executed_orders and jump_to in steps_by_order:
                        pending_orders.insert(i + 1, jump_to)
                if not should_continue:
                    stop_execution = True
            elif step_type == "foreach":
                ok = await self._execute_foreach(step, step_results, state)
                if not ok:
                    failed += 1
                else:
                    completed_steps_stack.append(step)
            else:
                ok = await self._execute_step(step, step_results, state)
                if ok:
                    completed_steps_stack.append(step)
                else:
                    failed += 1
                    # Run compensation for previously completed steps (reverse order)
                    await self._run_compensations(
                        list(reversed(completed_steps_stack)), step_results, state
                    )
            i += 1

        # Persist last_run_at so subsequent runs can use {{state.last_run_at}}
        finished_at = datetime.now(timezone.utc)
        await save_workflow_state(
            self.workflow_id,
            {**state, "last_run_at": finished_at.isoformat()},
            self.db,
        )

        duration_ms = int((finished_at - now).total_seconds() * 1000)

        if stop_execution:
            final_status = "completed"
        elif failed == len(steps) and bool(steps):
            final_status = "failed"
        else:
            final_status = "failed" if failed > 0 else "completed"

        # Extract metrics from step_results using the workflow's schema
        metrics = self._extract_metrics(step_results, metrics_schema)

        # Save analytics record for the dashboard
        try:
            await save_run_analytics(
                workflow_id=self.workflow_id,
                run_id=self.run_id,
                workflow_name=self.workflow_name,
                user_id=self.user_id,
                status=final_status,
                metrics=metrics,
                duration_ms=duration_ms,
                db=self.db,
                workspace_id=self.run.get("workspace_id"),
                board_id=self.run.get("board_id"),
            )
        except Exception as exc:
            logger.warning(f"[Executor] Failed to save analytics: {exc}")

        # Emit analytics event for the dashboard (Redis pub/sub)
        await self._emit(
            {
                "type": "run_analytics",
                "run_id": self.run_id,
                "workflow_id": self.workflow_id,
                "workflow_name": self.workflow_name,
                "status": final_status,
                "metrics": metrics,
                "duration_ms": duration_ms,
                "timestamp": finished_at.isoformat(),
            }
        )

        # Call HTTP webhook if configured
        if webhook_url:
            await self._call_webhook(
                webhook_url,
                {
                    "event": "run_completed",
                    "workflow_id": self.workflow_id,
                    "run_id": self.run_id,
                    "workflow_name": self.workflow_name,
                    "status": final_status,
                    "metrics": metrics,
                    "duration_ms": duration_ms,
                    "timestamp": finished_at.isoformat(),
                },
            )

        # Write intent_outcomes record — sole owner of this collection.
        # intent_id comes from the run document if workflow was triggered by an agent action.
        # Placed here so all code paths (stop_execution + normal) are covered.
        try:
            from uuid import uuid4
            _is_success = final_status == "completed"
            _all_failed_flag = final_status == "failed" and failed == len(steps) and bool(steps)
            outcome_doc = {
                "intent_id": self.run.get("intent_id") or str(uuid4()),
                "user_id": self.user_id,
                "conversation_id": self.run.get("conversation_id"),
                "workflow_id": self.workflow_id,
                "run_id": str(self.run_id),
                "timestamp": finished_at.isoformat(),
                "intent_type": self.run.get("intent_type") or "workflow_create",
                "confidence": self.run.get("intent_confidence"),
                "tool_used": self.workflow_name or None,
                "success": _is_success,
                "execution_time_ms": duration_ms,
                "error_type": (
                    "all_steps_failed" if _all_failed_flag
                    else (None if _is_success else "partial_failure")
                ),
                "workspace_id": self.run.get("workspace_id"),
                "board_id": self.run.get("board_id"),
            }
            await self.db[_COL_INTENT_OUTCOMES].insert_one(outcome_doc)
        except Exception as exc:
            logger.warning(f"[Executor] intent_outcomes write failed: {exc}")

        if stop_execution:
            await update_run_status(
                self.run_id,
                "completed",
                self.db,
                extra={"finished_at": finished_at},
            )
            await self._emit(
                {
                    "type": "run_completed",
                    "run_id": self.run_id,
                    "workflow_id": self.workflow_id,
                    "workflow_name": self.workflow_name,
                    "steps_failed": failed,
                    "stopped_early": True,
                    "timestamp": finished_at.isoformat(),
                }
            )
            return

        all_failed = final_status == "failed" and failed == len(steps) and bool(steps)
        if all_failed:
            await update_run_status(
                self.run_id,
                "failed",
                self.db,
                extra={"finished_at": finished_at, "error": "All steps failed"},
            )
            await self._emit(
                {
                    "type": "run_failed",
                    "run_id": self.run_id,
                    "workflow_id": self.workflow_id,
                    "error": "All steps failed",
                    "timestamp": finished_at.isoformat(),
                }
            )
            await update_workflow_status(self.workflow_id, "requires_attention", self.db)
        else:
            await update_run_status(
                self.run_id,
                final_status,
                self.db,
                extra={"finished_at": finished_at},
            )
            await self._emit(
                {
                    "type": f"run_{final_status}",
                    "run_id": self.run_id,
                    "workflow_id": self.workflow_id,
                    "workflow_name": self.workflow_name,
                    "steps_failed": failed,
                    "timestamp": finished_at.isoformat(),
                }
            )

        logger.info(
            f"[Executor] run={self.run_id} workflow={self.workflow_id} "
            f"steps={len(steps)} failed={failed} duration_ms={duration_ms}"
        )

        # Audit: run completion
        _audit(
            self.user_id,
            "workflow_run_completed" if final_status == "completed" else "workflow_run_failed",
            self.workflow_id,
            self.db,
            outcome=final_status,
            extra={"run_id": self.run_id, "failed_steps": failed, "duration_ms": duration_ms},
        )

        # Suspicious activity: check if user exceeded threshold in the last hour
        asyncio.create_task(self._check_suspicious_activity())

    # ── Step execution ────────────────────────────────────────────────────────

    async def _execute_step(
        self, step: dict, step_results: Dict[int, str], state: Dict[str, Any]
    ) -> bool:
        order = step.get("order", 0)
        name = step.get("name", f"Paso {order}")
        max_retries = int(step.get("max_retries", 0))
        retry_delay = float(step.get("retry_delay", 1.0))
        started_at = datetime.now(timezone.utc)

        await update_step_status(
            self.run_id, order, "running", self.db, started_at=started_at
        )
        await self._emit(
            {
                "type": "step_started",
                "run_id": self.run_id,
                "step_order": order,
                "step_name": name,
                "app": step.get("app", ""),
                "action": step.get("action", ""),
                "timestamp": started_at.isoformat(),
            }
        )

        last_exc: Optional[Exception] = None
        for attempt in range(max_retries + 1):
            try:
                result = await self._call_tool(step, step_results, state=state)
                step_results[order] = result
                finished_at = datetime.now(timezone.utc)

                # Per-step observation (ReAct tool chaining, DoD item 3):
                # Run the verifier for this tool to confirm the expected outcome.
                # Result is included in the step_completed event for observability.
                # If verification fails, a warning is logged but execution continues
                # (the step itself succeeded — the observation is a quality signal).
                observation_status: bool | None = None
                observation_note: str = ""
                try:
                    from app.services.observation_verifiers import VERIFIERS
                    _tool_key = step.get("app", "").lower().replace(" ", "_")
                    # Los verificadores leen la forma de salida de las BigTools; las funciones ya validan su salida.
                    _verifier = None if step.get("function_id") else VERIFIERS.get(_tool_key)
                    if _verifier:
                        _result_dict: dict = {}
                        try:
                            _result_dict = json.loads(result)
                        except Exception:
                            _result_dict = {"raw": result}
                        _obs = _verifier.verify(_result_dict, step.get("action", ""), step.get("action", ""))
                        observation_status = _obs.status
                        observation_note = (
                            f"VERIFIED: {_obs.expected}" if _obs.status
                            else f"FAILED: {_obs.actual}"
                        )
                        if _obs.status is False:
                            logger.warning(
                                "[Executor] Step %d observation FAILED tool=%r "
                                "expected=%r actual=%r",
                                order, _tool_key, _obs.expected, _obs.actual,
                            )
                        else:
                            logger.debug(
                                "[Executor] Step %d observation OK tool=%r expected=%r",
                                order, _tool_key, _obs.expected,
                            )
                except Exception as _obs_exc:
                    logger.debug("[Executor] Step %d observation check error: %s", order, _obs_exc)

                await update_step_status(
                    self.run_id,
                    order,
                    "completed",
                    self.db,
                    result=result,
                    finished_at=finished_at,
                )
                await self._emit(
                    {
                        "type": "step_completed",
                        "run_id": self.run_id,
                        "step_order": order,
                        "step_name": name,
                        "result": result,
                        "observation_status": observation_status,
                        "observation_note": observation_note,
                        "timestamp": finished_at.isoformat(),
                    }
                )
                return True
            except Exception as exc:
                last_exc = exc
                if attempt < max_retries:
                    wait = retry_delay * (2**attempt)
                    logger.info(
                        f"[Executor] Step {order} attempt {attempt + 1} failed, "
                        f"retrying in {wait:.1f}s: {exc}"
                    )
                    await asyncio.sleep(wait)

        error = str(last_exc)
        finished_at = datetime.now(timezone.utc)
        logger.warning(
            f"[Executor] Step {order} failed after {max_retries + 1} attempt(s): {error}"
        )
        await update_step_status(
            self.run_id,
            order,
            "failed",
            self.db,
            error=error,
            finished_at=finished_at,
        )
        await self._emit(
            {
                "type": "step_failed",
                "run_id": self.run_id,
                "step_order": order,
                "step_name": name,
                "error": error,
                "timestamp": finished_at.isoformat(),
            }
        )
        return False

    async def _execute_foreach(
        self, step: dict, step_results: Dict[int, str], state: Dict[str, Any]
    ) -> bool:
        """Iterates a JSON array and calls the step's action for each item."""
        order = step.get("order", 0)
        name = step.get("name", f"Paso {order}")
        source_tpl = step.get("source", "")
        started_at = datetime.now(timezone.utc)

        await update_step_status(
            self.run_id, order, "running", self.db, started_at=started_at
        )
        await self._emit(
            {
                "type": "step_started",
                "run_id": self.run_id,
                "step_order": order,
                "step_name": name,
                "app": step.get("app", ""),
                "action": step.get("action", ""),
                "timestamp": started_at.isoformat(),
            }
        )

        resolved_source = self._substitute_vars(
            {"_v": source_tpl}, step_results, state
        ).get("_v", "")
        try:
            items = json.loads(resolved_source) if resolved_source else []
            if not isinstance(items, list):
                items = [items]
        except Exception:
            items = []

        results = []
        errors = []
        for idx, item in enumerate(items):
            try:
                result = await self._call_tool(step, step_results, state=state, item=item)
                results.append(result)
            except Exception as exc:
                logger.warning(
                    f"[Executor] foreach step {order} item {idx} failed: {exc}"
                )
                errors.append(str(exc))

        step_results[order] = json.dumps(results)
        finished_at = datetime.now(timezone.utc)
        summary = f"Processed {len(results)}/{len(items)} items"
        if errors:
            summary += f" ({len(errors)} errors)"

        await update_step_status(
            self.run_id,
            order,
            "completed",
            self.db,
            result=summary,
            finished_at=finished_at,
        )
        await self._emit(
            {
                "type": "step_completed",
                "run_id": self.run_id,
                "step_order": order,
                "step_name": name,
                "result": summary,
                "timestamp": finished_at.isoformat(),
            }
        )
        return True

    async def _execute_condition(
        self, step: dict, step_results: Dict[int, str], state: Dict[str, Any]
    ) -> bool:
        """Legacy entry point — delegates to _execute_condition_branching."""
        should_continue, _ = await self._execute_condition_branching(step, step_results, state)
        return should_continue

    async def _execute_condition_branching(
        self, step: dict, step_results: Dict[int, str], state: Dict[str, Any]
    ) -> tuple[bool, Optional[int]]:
        """
        Evaluates a condition step.
        Returns (should_continue, jump_to_order).

        Branch fields (optional):
          then_step: order of step to jump to when condition PASSES (overrides linear next)
          else_step: order of step to jump to when condition FAILS (overrides stop)
          on_false: "stop" (default) | "continue" — used when else_step is not set
        """
        order = step.get("order", 0)
        name = step.get("name", f"Condición {order}")
        source_tpl = step.get("source", "")
        field = step.get("field", "answer")
        operator = step.get("operator", "eq")
        expected = step.get("value", True)
        on_false = step.get("on_false", "stop")
        then_step: Optional[int] = step.get("then_step")
        else_step: Optional[int] = step.get("else_step")

        resolved = self._substitute_vars(
            {"_v": source_tpl}, step_results, state
        ).get("_v", "")
        try:
            data = json.loads(resolved)
            actual = data.get(field) if isinstance(data, dict) else data
        except Exception:
            actual = resolved

        try:
            if operator == "eq":
                passed = actual == expected
            elif operator == "neq":
                passed = actual != expected
            elif operator == "gt":
                passed = float(actual) > float(expected)
            elif operator == "lt":
                passed = float(actual) < float(expected)
            elif operator == "contains":
                passed = str(expected).lower() in str(actual).lower()
            else:
                passed = bool(actual)
        except Exception:
            passed = False

        await self._emit(
            {
                "type": "step_condition",
                "run_id": self.run_id,
                "step_order": order,
                "step_name": name,
                "passed": passed,
                "on_false": on_false,
                "then_step": then_step,
                "else_step": else_step,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

        if passed:
            jump_to = then_step  # None = continue linearly
            return True, jump_to
        else:
            if else_step is not None:
                return True, else_step  # jump to else branch
            return (on_false != "stop"), None

    async def _run_compensations(
        self,
        completed_steps: list[dict],
        step_results: Dict[int, str],
        state: Dict[str, Any],
    ) -> None:
        """
        Executes compensation_action for each completed step (in reverse order).
        Called when a step fails after all retries. Never raises — logs errors only.
        """
        for step in completed_steps:
            compensation = step.get("compensation_action")
            if not compensation:
                continue
            order = step.get("order", 0)
            try:
                result = await self._call_tool(compensation, step_results, state=state)
                logger.info(
                    "[Executor] Compensation step=%d action=%r result=%r",
                    order, compensation.get("action"), result[:80] if result else "",
                )
                await self._emit({
                    "type": "step_compensated",
                    "run_id": self.run_id,
                    "step_order": order,
                    "compensation_action": compensation.get("action"),
                    "result": result,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
            except Exception as exc:
                logger.warning(
                    "[Executor] Compensation failed step=%d action=%r: %s",
                    order, compensation.get("action"), exc,
                )

    def _substitute_vars(
        self,
        config: Dict[str, Any],
        step_results: Dict[int, str],
        state: Optional[Dict[str, Any]] = None,
        item: Any = None,
    ) -> Dict[str, Any]:
        """Replace template variables in config string values.

        Supported patterns:
          {{step_N}}         → full output of step N
          {{step_N.field}}   → JSON field from step N's output
          {{step_N.rows[0][0]}} / {{step_N.rows.0.0}} → path into nested output (dict keys and list indexes)
          {{state.field}}    → field from the workflow's persisted state
          {{item}}           → current foreach item (as JSON)
          {{item.field}}     → field from the current foreach item
          {{trigger}}        → JSON the webhook received (the run's trigger_payload)
          {{trigger.field}}  → field from that JSON
        """
        # getattr: algunas pruebas crean el ejecutor sin __init__ (no tiene self.run).
        payload = (getattr(self, "run", None) or {}).get("trigger_payload")

        def _text(val: Any) -> str:
            if val is None:
                return ""
            return json.dumps(val, ensure_ascii=False) if isinstance(val, (dict, list)) else str(val)

        def _replace(m: _re.Match) -> str:
            full = m.group(1)
            if full.startswith("trigger"):
                field = m.group(6)
                if field is None:
                    return _text(payload)
                return _text(payload.get(field)) if isinstance(payload, dict) else ""
            if full.startswith("step_"):
                n = int(m.group(2))
                field = m.group(3)
                raw = step_results.get(n, "")
                if not raw:
                    return ""
                if field:
                    try:
                        val = _walk_path(json.loads(raw), field)
                        if val is not _MISSING:
                            return _text(val) if isinstance(val, (dict, list)) else str(val)
                    except Exception:
                        pass
                return raw
            elif full.startswith("state."):
                field = m.group(4)
                val = (state or {}).get(field, "")
                return str(val) if val is not None else ""
            elif full.startswith("item"):
                field = m.group(5)
                if item is None:
                    return ""
                if field is None:
                    return json.dumps(item) if not isinstance(item, str) else item
                if isinstance(item, dict):
                    val = item.get(field, "")
                    return str(val) if val is not None else ""
                return ""
            return m.group(0)

        def _typed(m: _re.Match) -> Any:
            """Valor con su tipo (lista, dict, numero) cuando la plantilla es TODO el valor: "{{step_1.items}}" debe
            llegar a la funcion como lista, no como su texto (las fichas validan tipos)."""
            full = m.group(1)
            if full.startswith("trigger"):
                if m.group(6) is None:
                    return payload if payload is not None else ""
                return payload.get(m.group(6), "") if isinstance(payload, dict) else ""
            if full.startswith("step_"):
                raw = step_results.get(int(m.group(2)), "")
                try:
                    data = json.loads(raw) if raw else None
                except Exception:
                    return _replace(m)
                if m.group(3):
                    val = _walk_path(data, m.group(3))
                    return _replace(m) if val is _MISSING else val
                return data if data is not None else ""
            if full.startswith("state."):
                return (state or {}).get(m.group(4), "")
            if full.startswith("item") and isinstance(item, dict) and m.group(5):
                return item.get(m.group(5), "")
            if full == "item" and item is not None:
                return item
            return _replace(m)

        def _resolve(value: Any) -> Any:
            # Recurse into strings, lists and dicts so templates inside a `values`
            # list (e.g. ['{{step_2.name}}', '{{step_2.email}}']) are resolved too.
            if isinstance(value, str):
                whole = _VAR_RE.fullmatch(value.strip())
                if whole:
                    return _typed(whole)
                return _VAR_RE.sub(_replace, value)
            if isinstance(value, list):
                return [_resolve(v) for v in value]
            if isinstance(value, dict):
                return {k: _resolve(v) for k, v in value.items()}
            return value

        result: Dict[str, Any] = {}
        for key, value in config.items():
            result[key] = _resolve(value)
        return result

    # ── Tool resolution ───────────────────────────────────────────────────────

    async def _plan_filtered_providers(self, connected_providers: set) -> set:
        """Intersecta los proveedores conectados con el whitelist de tools del plan del usuario."""
        from bson import ObjectId
        from app.core.constants import Collections
        from app.billing.plans import filter_providers_by_plan

        try:
            user_doc = await self.db[Collections.USERS].find_one(
                {"_id": ObjectId(self.user_id)}, {"plan": 1}
            )
        except Exception:
            user_doc = None
        plan = (user_doc or {}).get("plan") or "free"
        return filter_providers_by_plan(plan, connected_providers)

    async def _check_guards(self, action: str) -> None:
        """Limite de ritmo y circuit breaker por (usuario, accion). Sin Redis no hace nada (falla abierto)."""
        # Rate limiting: check per-user, per-tool, per-hour quota before calling tool
        if not self.dry_run and action:
            allowed, count = await check_tool_rate_limit(
                self.user_id, action, Config.REDIS_URL if hasattr(Config, "REDIS_URL") else None
            )
            if not allowed:
                _audit(
                    self.user_id, "rate_limit_exceeded", action, self.db,
                    outcome="blocked",
                    extra={"count": count, "limit": os.getenv("BIGTOOL_RATE_LIMIT_PER_HOUR", "100")},
                )
                raise ValueError(
                    f"Rate limit exceeded for tool '{action}' — {count} calls this hour. "
                    f"Limit: {os.getenv('BIGTOOL_RATE_LIMIT_PER_HOUR', '100')} per hour."
                )

        # Circuit breaker: refuse to call a tool that has been failing consecutively
        _redis_url = Config.REDIS_URL if hasattr(Config, "REDIS_URL") else None
        if not self.dry_run and action and _redis_url:
            try:
                _r = aioredis.from_url(_redis_url, decode_responses=True)
                _cb_key = f"circuit_breaker:{self.user_id}:{action}"
                if await _r.exists(_cb_key):
                    _ttl = await _r.ttl(_cb_key)
                    await _r.aclose()
                    raise ValueError(
                        f"Circuit breaker OPEN for tool '{action}' — too many consecutive failures. "
                        f"Cooldown: {max(_ttl, 0)}s remaining. "
                        f"(env CIRCUIT_BREAKER_COOLDOWN_SECONDS to adjust, default {_CB_COOLDOWN_SECONDS}s)"
                    )
                await _r.aclose()
            except aioredis.RedisError:
                pass  # fail open — Redis unavailable, allow call

    # ── Funciones de apps (sistema nuevo) ─────────────────────────────────────

    def _simulate(self) -> bool:
        """Simulado: no se llama a la app externa, se devuelve el ejemplo de la ficha."""
        return (
            self.dry_run
            or bool(self.run.get("simulate"))
            or os.getenv("SHIFU_FUNCTIONS_SIMULATE", "") == "1"
        )

    @staticmethod
    def _resolve_function(step: dict):
        """Busca la funcion registrada; carga el registro solo si hace falta (una vez por proceso en la practica)."""
        from app.functions import registry

        fid, ver = step["function_id"], step.get("function_version")
        try:
            return registry.get_function(fid, ver)
        except registry.RegistryError:
            registry.load_all()
            return registry.get_function(fid, ver)

    @staticmethod
    def _function_refusal(fn) -> Optional[str]:
        """Eliminar exige a una persona en el momento: un workflow corre sin nadie delante, asi que se niega.
        Lo irreversible que no borra (enviar un correo, sobrescribir celdas) si pasa: el usuario confirmo el plan del
        workflow, paso por paso, en el nivel 3. Sin esto "cada lunes mandame el total por Gmail" no se podia armar."""
        from app.functions.spec import Verb

        if fn.spec.verb == Verb.delete:
            return (
                f"La funcion '{fn.spec.id}' elimina o es irreversible y necesita confirmacion de una persona; "
                "un workflow no puede ejecutarla por su cuenta."
            )
        return None

    async def _call_function(
        self,
        step: dict,
        step_results: Dict[int, str],
        state: Optional[Dict[str, Any]] = None,
        item: Any = None,
        force_simulate: bool = False,
    ) -> str:
        """Corre un paso por app.functions.runner. Devuelve el `data` como JSON (para que {{step_N.campo}} siga
        funcionando) y lanza RuntimeError("codigo: mensaje") si falla, para que reintentos y compensacion apliquen igual."""
        from app.functions import runner

        fn = self._resolve_function(step)
        refusal = self._function_refusal(fn)
        if refusal:
            raise RuntimeError(refusal)

        function_id = fn.spec.id
        simulate = force_simulate or self._simulate()  # el dry run siempre simula, aunque no se creara con dry_run=True
        if not simulate:
            await self._check_guards(function_id)

        config = self._substitute_vars(step.get("config") or {}, step_results, state=state or {}, item=item)
        # nodeType es una marca del flujo de requisitos, no un argumento de la funcion.
        args = {k: v for k, v in config.items() if k != "nodeType"}

        res = None
        for attempt in range(_TOOL_RETRY_MAX + 1):
            res = await runner.execute(
                fn, args, db=self.db, user_id=self.user_id,
                account_id=step.get("account_id") or None, simulate=simulate,
                timeout=_STEP_TIMEOUT_SECONDS,
            )
            if res.ok or not (res.error and res.error.retryable) or attempt >= _TOOL_RETRY_MAX:
                break
            await asyncio.sleep(_TOOL_RETRY_DELAY * (2 ** attempt))

        error_msg = None if res.ok else f"{res.error.code.value}: {res.error.message}"
        if not simulate:  # un simulacro no debe contaminar la tasa de fallos ni el circuit breaker
            await _log_tool_outcome(
                self.db, self.user_id, function_id, success=res.ok, error_msg=error_msg,
                duration_ms=res.meta.duration_ms if res.meta else 0,
            )
            redis_url = Config.REDIS_URL if hasattr(Config, "REDIS_URL") else None
            if redis_url:
                if res.ok:
                    await _reset_circuit_breaker(self.user_id, function_id, redis_url)
                else:
                    await _update_circuit_breaker(self.user_id, function_id, redis_url)

        if not res.ok:
            raise RuntimeError(error_msg)
        return json.dumps(res.data, ensure_ascii=False, default=str)

    async def _call_tool(
        self,
        step: dict,
        step_results: Dict[int, str],
        state: Optional[Dict[str, Any]] = None,
        item: Any = None,
    ) -> str:
        """Resolves the BigTool by exact action name and invokes it with the step config."""
        # Sistema nuevo: un paso con function_id va por app.functions; sin function_id sigue el camino BigTools de abajo.
        # (va antes de los imports de BigTools: importarlos arrastra Tavily y exige sus claves).
        if step.get("function_id"):
            return await self._call_function(step, step_results, state=state, item=item)

        from app.services.chat_memory import load_user_integrations
        from app.services.bigtools_loader import get_all_bigtools, bigtool_to_lc as _bigtool_to_lc
        from langchain_core.tools import BaseTool

        action = step.get("action", "")
        app_name = step.get("app", "")
        config: Dict[str, Any] = step.get("config") or {}
        account_id = step.get("account_id", "")

        await self._check_guards(action)
        _redis_url = Config.REDIS_URL if hasattr(Config, "REDIS_URL") else None

        config = self._substitute_vars(config, step_results, state=state or {}, item=item)

        connected_accounts = await load_user_integrations(self.user_id, self.db)
        provider_to_account_map: Dict[str, str] = {
            acc["provider"]: acc.get("account_id", "")
            for acc in connected_accounts
            if acc.get("provider")
        }
        if account_id and app_name:
            provider_to_account_map[app_name] = account_id
        connected_providers = {c["provider"] for c in connected_accounts}
        allowed_providers = await self._plan_filtered_providers(connected_providers)

        bigtools_raw = await asyncio.to_thread(
            get_all_bigtools,
            self.user_id,
            self.user_email,
            self.db,
            provider_to_account_map,
            allowed_providers,
        )
        tool_map: Dict[str, Any] = {bt.name: bt.tool for bt in bigtools_raw}
        lc_tools_map: Dict[str, BaseTool] = {
            t.name: t for bt in bigtools_raw if (t := _bigtool_to_lc(bt)) is not None
        }

        tool = tool_map.get(action)
        lc_tool = lc_tools_map.get(action)

        if not tool and not lc_tool:
            available = sorted(tool_map.keys())
            raise ValueError(
                f"No tool found for action='{action}' (app='{app_name}'). "
                f"Available tools: {available}"
            )

        # Warn loudly when config is empty so it's easy to spot in logs.
        # An empty config almost always means Shifu skipped filling required fields.
        if not config:
            logger.warning(
                f"[Executor] action='{action}' step={step.get('order')} "
                f"has empty config — likely missing required fields. "
                f"The tool will probably raise a validation error."
            )

        # Self-recovery: wrap tool call with timeout (DoD item 6 — step timeout)
        # If a tool hangs longer than STEP_TIMEOUT_SECONDS, it is treated as a failure.
        # The step then goes through the normal retry / compensation path.
        async def _invoke() -> str:
            if lc_tool:
                return str(await lc_tool.ainvoke(config))
            elif isinstance(tool, BaseTool):
                return str(await tool.ainvoke(config))
            elif inspect.iscoroutinefunction(tool):
                r = await tool(**config) if config else await tool()
                return str(r) if r is not None else "OK"
            else:
                r = tool(**config) if config else tool()
                return str(r) if r is not None else "OK"

        # Retry loop: 1 retry for transient HTTP errors (429/503); outcome logged after each attempt
        _started = datetime.now(timezone.utc)
        _success = False
        _last_exc: Optional[Exception] = None

        for _attempt in range(_TOOL_RETRY_MAX + 1):
            try:
                result = await asyncio.wait_for(_invoke(), timeout=_STEP_TIMEOUT_SECONDS)
                _success = True
                break
            except asyncio.TimeoutError:
                _last_exc = ValueError(
                    f"Tool '{action}' timed out after {_STEP_TIMEOUT_SECONDS}s — "
                    "step marked as failed. Increase STEP_TIMEOUT_SECONDS env var if needed."
                )
                break  # timeouts are not retried
            except Exception as _exc:
                _last_exc = _exc
                if _attempt < _TOOL_RETRY_MAX and _is_transient_error(_exc):
                    logger.info(
                        "[Executor] Transient error for action='%s' attempt %d/%d, retrying in %.1fs: %s",
                        action, _attempt + 1, _TOOL_RETRY_MAX + 1, _TOOL_RETRY_DELAY * (2 ** _attempt), _exc,
                    )
                    await asyncio.sleep(_TOOL_RETRY_DELAY * (2 ** _attempt))
                else:
                    break

        _duration_ms = int((datetime.now(timezone.utc) - _started).total_seconds() * 1000)

        # Outcome logging (fire-and-forget; never blocks)
        if not self.dry_run and action:
            await _log_tool_outcome(
                self.db, self.user_id, action,
                success=_success,
                error_msg=str(_last_exc) if _last_exc else None,
                duration_ms=_duration_ms,
            )
            if _redis_url:
                if _success:
                    await _reset_circuit_breaker(self.user_id, action, _redis_url)
                else:
                    await _update_circuit_breaker(self.user_id, action, _redis_url)

        if not _success and _last_exc is not None:
            raise _last_exc

        return result

    # ── Analytics helpers ─────────────────────────────────────────────────────

    def _extract_metrics(
        self, step_results: Dict[int, str], metrics_schema: list
    ) -> Dict[str, Any]:
        """Extract dashboard metrics from step_results using the workflow's schema."""
        metrics: Dict[str, Any] = {}
        for m in metrics_schema:
            key = m.get("key", "")
            source = m.get("source", "")
            field = m.get("field", "")
            if not key:
                continue
            match = _re.match(r"step_(\d+)", source)
            if not match:
                metrics[key] = None
                continue
            n = int(match.group(1))
            raw = step_results.get(n, "")
            if field:
                try:
                    data = json.loads(raw)
                    metrics[key] = data.get(field) if isinstance(data, dict) else raw
                except Exception:
                    metrics[key] = raw
            else:
                # Try to parse as number if it looks numeric
                try:
                    metrics[key] = float(raw) if raw else None
                except (ValueError, TypeError):
                    metrics[key] = raw
        return metrics

    async def _call_webhook(self, url: str, payload: Dict[str, Any]) -> None:
        """POST the run payload to an external HTTP webhook URL."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                logger.info(f"[Executor] Webhook POST {url} → {resp.status_code}")
        except Exception as exc:
            logger.warning(f"[Executor] Webhook POST failed ({url}): {exc}")

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _check_suspicious_activity(self) -> None:
        """
        Counts workflow runs for this user in the last hour.
        Logs a suspicious_activity audit event if the count exceeds the threshold.
        Never raises.
        """
        try:
            since = datetime.now(timezone.utc) - timedelta(hours=1)
            count = await self.db[_COL_WORKFLOW_RUNS].count_documents(
                {"user_id": self.user_id, "started_at": {"$gte": since}}
            )
            if count >= _SUSPICIOUS_RUN_THRESHOLD:
                logger.warning(
                    "[Executor] suspicious activity user=%s runs_last_hour=%d threshold=%d",
                    self.user_id, count, _SUSPICIOUS_RUN_THRESHOLD,
                )
                _audit(
                    self.user_id, "suspicious_activity", "workflow_runs", self.db,
                    outcome="flagged",
                    extra={"runs_last_hour": count, "threshold": _SUSPICIOUS_RUN_THRESHOLD},
                )
        except Exception as exc:
            logger.debug("[Executor] suspicious activity check failed: %s", exc)

    async def _emit(self, event: dict):
        if self.dry_run:
            return
        await publish_user_event(self.user_id, event)

        # Persist run-level completion events to `user_notifications` — the WS broadcast above
        # is "live only"; this is the history/read-state the REST notifications endpoints serve.
        # Step-level events (step_started/step_completed/...) and run_analytics are intentionally
        # skipped — a notification per step would flood the user's inbox.
        event_type = event.get("type")
        if event_type in ("run_completed", "run_failed"):
            from app.services.notification_service import create_notification
            wf_name = self.workflow_name or "tu workflow"
            if event_type == "run_completed":
                title = "Workflow completado"
                message = f'"{wf_name}" terminó su ejecución correctamente.'
            else:
                title = "Workflow falló"
                message = f'"{wf_name}" falló durante la ejecución. Pregúntale a Shifu por qué falló y te lo explica.'
            await create_notification(self.db, self.user_id, event_type, title, message)

    # ── Dry-run ───────────────────────────────────────────────────────────────

    async def run_undo(self, steps: list) -> dict:
        """
        Public entry point for undoing a workflow run.
        Executes compensation_action for each step that has one, in reverse order.
        Returns count of steps that had compensations available.
        """
        if Config.REDIS_URL:
            self._redis = aioredis.from_url(Config.REDIS_URL, decode_responses=True)
        try:
            compensatable = [s for s in steps if s.get("compensation_action")]
            await self._run_compensations(list(reversed(compensatable)), {}, {})
            return {
                "status": "undone",
                "workflow_id": self.workflow_id,
                "compensated_steps": len(compensatable),
                "total_steps": len(steps),
            }
        finally:
            if self._redis:
                await self._redis.aclose()

    async def execute_dry_run(self) -> dict:
        """
        Simulates workflow execution without calling any tools or writing to DB/Redis.
        Condition steps are evaluated for real (branch logic is verified).
        All action/foreach steps return a mock result string.
        Returns a trace dict with per-step simulation results.
        """
        state = await get_workflow_state(self.workflow_id, self.db)
        steps = sorted(self.run.get("steps", []), key=lambda s: s.get("order", 0))
        steps_by_order: Dict[int, dict] = {s.get("order", 0): s for s in steps}
        step_results: Dict[int, str] = {}
        step_trace: list = []
        pending_orders = [s.get("order", 0) for s in steps]
        executed_orders: set[int] = set()
        stop_execution = False

        i = 0
        while i < len(pending_orders):
            if stop_execution:
                break
            order = pending_orders[i]
            if order in executed_orders:
                i += 1
                continue
            executed_orders.add(order)
            step = steps_by_order.get(order)
            if step is None:
                i += 1
                continue

            step_type = step.get("type", "action")
            if step_type == "condition":
                should_continue, jump_to = await self._execute_condition_branching(
                    step, step_results, state
                )
                step_trace.append({
                    "order": order,
                    "type": "condition",
                    "name": step.get("name"),
                    "passed": should_continue,
                    "jump_to": jump_to,
                    "skipped_real_call": False,
                })
                if jump_to is not None and jump_to not in executed_orders and jump_to in steps_by_order:
                    pending_orders.insert(i + 1, jump_to)
                if not should_continue:
                    stop_execution = True
            elif step.get("function_id"):
                # Con funcion real se usa el ejemplo de su ficha: datos realistas y {{step_N.campo}} se resuelve.
                entry = {
                    "order": order,
                    "type": step_type,
                    "name": step.get("name"),
                    "action": step.get("action"),
                    "app": step.get("app"),
                    "function_id": step.get("function_id"),
                    "skipped_real_call": True,
                }
                try:
                    result = await self._call_function(step, step_results, state=state, force_simulate=True)
                    step_results[order] = result
                    entry["mock_result"] = result
                except Exception as exc:  # p. ej. una funcion que exige humano: se ve al planear, no al correr
                    step_results[order] = ""
                    entry["error"] = str(exc)
                step_trace.append(entry)
            else:
                mock_result = (
                    f"[DRY RUN] {step.get('action', 'unknown')} "
                    f"(app={step.get('app', '')}) — simulated OK"
                )
                step_results[order] = mock_result
                step_trace.append({
                    "order": order,
                    "type": step_type,
                    "name": step.get("name"),
                    "action": step.get("action"),
                    "app": step.get("app"),
                    "mock_result": mock_result,
                    "skipped_real_call": True,
                })
            i += 1

        steps_simulated = sum(1 for t in step_trace if t.get("skipped_real_call"))
        return {
            "dry_run": True,
            "workflow_id": self.workflow_id,
            "workflow_name": self.workflow_name,
            "total_steps": len(steps),
            "steps_simulated": steps_simulated,
            "stopped_early": stop_execution,
            "trace": step_trace,
            "status": "simulated",
        }
