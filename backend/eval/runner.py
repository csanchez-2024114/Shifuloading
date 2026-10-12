"""
eval/runner.py — CLI entry point for the Claudio Evaluation Framework.

Usage:
  python -m eval.runner [options]

Options:
  --url      Base URL (default: http://localhost:5000)
  --gate     dev|staging|prod (default: dev)
  --category Filter by category slug (default: all)
  --seed     Re-seed cases from YAML before running
  --output   console|json (default: console)

Exit codes:
  0 = PASS
  1 = FAIL

Environment variables required:
  MONGO_URI
  MONGO_DB_NAME
  OPENAI_API_KEY
  EVAL_USER_EMAIL
  EVAL_USER_PASSWORD
  EVAL_BASE_URL  (optional, overrides --url)
"""

import argparse
import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

from motor.motor_asyncio import AsyncIOMotorClient

from .auth import EvalAuthError, get_test_token
from .client import ChatResponse, EvalClientError, send_message
from .judge import JudgeResult, judge
from .reporter import (
    GATES,
    EvalResult,
    apply_blocking_rules,
    persist_run,
    print_report,
)
from .seeder import seed

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("claudio.runner")

_CASES_DIR = Path(__file__).parent / "cases"
_MAX_CONCURRENT = 5


def _get_commit_hash() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return "unknown"


async def _run_single_case(
    case: dict,
    base_url: str,
    token: str,
    semaphore: asyncio.Semaphore,
) -> EvalResult:
    test_id = case["test_id"]
    category = case.get("category", "")
    severity = case.get("severity", "medium")
    multi_turn = case.get("multi_turn", False)

    async with semaphore:
        if multi_turn:
            return await _run_multi_turn_case(case, base_url, token)
        return await _run_single_turn_case(case, base_url, token)


async def _run_single_turn_case(case: dict, base_url: str, token: str) -> EvalResult:
    test_id = case["test_id"]
    message = case["message"]
    expected = case.get("expected_behavior", [])
    severity = case.get("severity", "medium")
    category = case.get("category", "")
    conversation_id = str(uuid4())

    start = time.monotonic()
    try:
        resp = await send_message(base_url, token, message, conversation_id)
        reply = resp.reply
        duration_ms = resp.duration_ms
        error = ""
    except EvalClientError as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        return EvalResult(
            test_id=test_id, category=category, severity=severity,
            message=message, passed=False, score=0,
            reason=f"HTTP error: {exc.status_code}",
            actual_response="", duration_ms=duration_ms,
            error=str(exc),
        )
    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        return EvalResult(
            test_id=test_id, category=category, severity=severity,
            message=message, passed=False, score=0,
            reason="Client exception",
            actual_response="", duration_ms=duration_ms,
            error=str(exc)[:200],
        )

    verdict = await judge(message, expected, reply)

    return EvalResult(
        test_id=test_id, category=category, severity=severity,
        message=message, passed=verdict.passed, score=verdict.score,
        reason=verdict.reason, actual_response=reply,
        duration_ms=duration_ms, error="",
    )


async def _run_multi_turn_case(case: dict, base_url: str, token: str) -> EvalResult:
    test_id = case["test_id"]
    turns = case.get("turns", [])
    severity = case.get("severity", "medium")
    category = case.get("category", "")
    conversation_id = str(uuid4())

    total_ms = 0
    final_verdict = JudgeResult(passed=True, score=10, reason="All turns passed")
    last_reply = ""

    for i, turn in enumerate(turns):
        message = turn["message"]
        expected = turn.get("expected_behavior", [])

        try:
            resp = await send_message(base_url, token, message, conversation_id)
            last_reply = resp.reply
            total_ms += resp.duration_ms
        except EvalClientError as exc:
            return EvalResult(
                test_id=test_id, category=category, severity=severity,
                message=message, passed=False, score=0,
                reason=f"Turn {i + 1} HTTP error: {exc.status_code}",
                actual_response="", duration_ms=total_ms,
                error=str(exc),
            )

        if expected:
            verdict = await judge(message, expected, last_reply)
            if not verdict.passed:
                final_verdict = JudgeResult(
                    passed=False,
                    score=verdict.score,
                    reason=f"Turn {i + 1}: {verdict.reason}",
                )
                break
            if verdict.score < final_verdict.score:
                final_verdict = verdict

    return EvalResult(
        test_id=test_id, category=category, severity=severity,
        message=f"[multi-turn: {len(turns)} turns]",
        passed=final_verdict.passed, score=final_verdict.score,
        reason=final_verdict.reason, actual_response=last_reply,
        duration_ms=total_ms, error="",
    )


async def main(args: argparse.Namespace) -> int:
    base_url = os.environ.get("EVAL_BASE_URL", args.url).rstrip("/")
    gate = args.gate
    category = args.category
    run_id = str(uuid4())

    mongo_uri = os.environ.get("MONGO_URI")
    mongo_db_name = os.environ.get("MONGO_DB_NAME", "shifu_production")

    if not mongo_uri:
        logger.error("MONGO_URI environment variable is required.")
        return 1

    mongo_client = AsyncIOMotorClient(mongo_uri)
    db = mongo_client[mongo_db_name]

    # Seed if requested
    if args.seed:
        logger.info("[runner] Seeding evaluation cases from %s ...", _CASES_DIR)
        seeded = await seed(db, _CASES_DIR)
        logger.info("[runner] Seeded %d cases.", seeded)

    # Load cases from MongoDB
    query: dict = {}
    if category and category != "all":
        query["category"] = category

    cursor = db["evaluation_cases"].find(query)
    cases = await cursor.to_list(length=500)

    if not cases:
        logger.error(
            "[runner] No evaluation cases found. Run with --seed to populate them."
        )
        return 1

    logger.info("[runner] Loaded %d cases (category=%s)", len(cases), category or "all")

    # Authenticate
    try:
        token = await get_test_token(base_url)
        logger.info("[runner] Authenticated as %s", os.environ.get("EVAL_USER_EMAIL", "?"))
    except EvalAuthError as exc:
        logger.error("[runner] Auth failed: %s", exc)
        return 1

    # Run cases with concurrency limit
    semaphore = asyncio.Semaphore(_MAX_CONCURRENT)
    start_total = time.monotonic()

    tasks = [_run_single_case(case, base_url, token, semaphore) for case in cases]
    results: list[EvalResult] = await asyncio.gather(*tasks)

    total_ms = int((time.monotonic() - start_total) * 1000)

    # Compute metrics
    passed_count = sum(1 for r in results if r.passed)
    total_count = len(results)
    pass_rate = passed_count / total_count if total_count else 0.0

    threshold = GATES.get(gate, GATES["dev"])
    blocking_ok, blocking_reason = apply_blocking_rules(results)

    if not blocking_ok:
        status = "fail"
    elif pass_rate >= threshold:
        status = "pass"
    else:
        status = "fail"

    commit_hash = _get_commit_hash()

    # Output
    if args.output == "json":
        output = {
            "run_id": run_id,
            "gate": gate,
            "threshold": threshold,
            "pass_rate": round(pass_rate * 100, 2),
            "status": status,
            "blocking_reason": blocking_reason,
            "commit_hash": commit_hash,
            "results": [
                {
                    "test_id": r.test_id,
                    "passed": r.passed,
                    "score": r.score,
                    "reason": r.reason,
                    "duration_ms": r.duration_ms,
                }
                for r in results
            ],
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print_report(
            results, pass_rate, gate, threshold, status,
            run_id, total_ms, blocking_reason,
        )

    # Persist to MongoDB
    try:
        await persist_run(
            db, results, run_id, gate,
            category_filter=category or "all",
            pass_rate=pass_rate,
            status=status,
            duration_ms=total_ms,
            commit_hash=commit_hash,
        )
    except Exception as exc:
        logger.warning("[runner] Failed to persist run to MongoDB: %s", exc)

    mongo_client.close()
    return 0 if status == "pass" else 1


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Claudio — Shifu Agent OS Evaluation Framework"
    )
    parser.add_argument("--url", default="http://localhost:5000", help="Base server URL")
    parser.add_argument("--gate", choices=["dev", "staging", "prod"], default="dev")
    parser.add_argument("--category", default="all", help="Filter by category (e.g. decision_engine)")
    parser.add_argument("--seed", action="store_true", help="Seed cases from YAML before running")
    parser.add_argument("--output", choices=["console", "json"], default="console")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    exit_code = asyncio.run(main(args))
    sys.exit(exit_code)
