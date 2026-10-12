"""
eval/reporter.py — Console reporting + MongoDB persistence for evaluation runs.

Blocking rules (cause immediate status=fail regardless of pass rate):
  - Any severity="critical" test fails
  - Response contains raw Python traceback
  - Response is empty string
  - HTTP 500 received
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

_COL_RUNS = "evaluation_runs"
_COL_RESULTS = "evaluation_results"

GATES = {
    "dev": 0.80,
    "staging": 0.90,
    "prod": 0.95,
}


@dataclass
class EvalResult:
    test_id: str
    category: str
    severity: str
    message: str
    passed: bool
    score: int
    reason: str
    actual_response: str
    duration_ms: int
    error: str = ""


def apply_blocking_rules(results: list[EvalResult]) -> tuple[bool, str]:
    for r in results:
        if r.severity == "critical" and not r.passed:
            return False, f"Blocking: critical test {r.test_id} failed"
        if r.actual_response and "Traceback (most recent call last)" in r.actual_response:
            return False, f"Blocking: raw Python traceback in response for {r.test_id}"
        if r.passed and not r.actual_response.strip():
            return False, f"Blocking: empty response for {r.test_id}"
        if r.error and "HTTP 500" in r.error:
            return False, f"Blocking: HTTP 500 for {r.test_id}"
    return True, ""


def print_report(
    results: list[EvalResult],
    pass_rate: float,
    gate: str,
    threshold: float,
    status: str,
    run_id: str,
    duration_ms: int,
    blocking_reason: str = "",
) -> None:
    width = 80
    print("\n" + "=" * width)
    print(f"  CLAUDIO EVALUATION REPORT — run_id={run_id}")
    print("=" * width)

    print(f"\n  Gate: {gate.upper()}  |  Threshold: {threshold * 100:.0f}%  |  Status: {status.upper()}")
    print(f"  Pass rate: {pass_rate * 100:.1f}%  ({sum(1 for r in results if r.passed)}/{len(results)} passed)")
    print(f"  Duration: {duration_ms / 1000:.1f}s\n")

    if blocking_reason:
        print(f"  *** BLOCKED: {blocking_reason} ***\n")

    print(f"  {'ID':<12} {'SEV':<8} {'STATUS':<8} {'SCORE':<7} {'REASON'}")
    print("  " + "-" * (width - 2))

    for r in results:
        icon = "PASS" if r.passed else "FAIL"
        print(
            f"  {r.test_id:<12} {r.severity:<8} {icon:<8} {r.score:<7} {r.reason[:55]}"
        )
        if not r.passed and r.error:
            print(f"  {'':12} {'':8} {'':8} {'':7} Error: {r.error[:55]}")

    print("\n" + "=" * width + "\n")


async def persist_run(
    db: AsyncIOMotorDatabase,
    results: list[EvalResult],
    run_id: str,
    gate: str,
    category_filter: str,
    pass_rate: float,
    status: str,
    duration_ms: int,
    commit_hash: str,
) -> None:
    col_runs = db[_COL_RUNS]
    col_results = db[_COL_RESULTS]

    await col_runs.create_index("run_id", unique=True)
    await col_runs.create_index([("timestamp", -1)])
    await col_results.create_index("run_id")
    await col_results.create_index("test_id")
    await col_results.create_index("passed")

    now = datetime.now(timezone.utc).isoformat()

    run_doc = {
        "run_id": run_id,
        "commit_hash": commit_hash,
        "timestamp": now,
        "gate": gate,
        "category_filter": category_filter,
        "total": len(results),
        "passed": sum(1 for r in results if r.passed),
        "failed": sum(1 for r in results if not r.passed),
        "pass_rate": round(pass_rate * 100, 2),
        "status": status,
        "duration_ms": duration_ms,
    }
    await col_runs.insert_one(run_doc)

    result_docs = [
        {
            "result_id": str(uuid4()),
            "run_id": run_id,
            "test_id": r.test_id,
            "category": r.category,
            "severity": r.severity,
            "passed": r.passed,
            "score": r.score,
            "reason": r.reason,
            "actual_response": r.actual_response[:1000],
            "duration_ms": r.duration_ms,
            "error": r.error,
            "timestamp": now,
        }
        for r in results
    ]
    if result_docs:
        await col_results.insert_many(result_docs)

    logger.info(
        "[reporter] Persisted run_id=%s status=%s pass_rate=%.1f%%",
        run_id, status, pass_rate * 100,
    )
