"""
Cognitive regression evaluator — compares semantic_intake output against golden_dataset.json.

Usage:
    python -m eval.run_eval                        # run all cases
    python -m eval.run_eval --update-baseline      # overwrite baseline_scores.json
    python -m eval.run_eval --fail-delta 0.05      # fail if any score drops >5%

What it checks per case:
  - apps_involved matches expected_apps_involved (exact set equality)
  - needs_external_info matches
  - catalog_query_mode matches expected_catalog_query_mode
  - is_closing matches expected_is_closing (when present)

Exit code 0 = all pass, 1 = regressions detected.
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_DATASET = Path(__file__).parent / "golden_dataset.json"
_BASELINE = Path(__file__).parent / "baseline_scores.json"


def _load_dataset() -> list[dict]:
    with open(_DATASET) as f:
        return json.load(f)


def _score_case(case: dict, result: dict) -> dict:
    """Returns {passed, details} for a single eval case."""
    checks = {}

    expected_apps = set(case.get("expected_apps_involved") or [])
    got_apps = set(result.get("apps_involved") or [])
    checks["apps_involved"] = expected_apps == got_apps

    if "expected_needs_external_info" in case:
        checks["needs_external_info"] = (
            bool(result.get("needs_external_info")) == bool(case["expected_needs_external_info"])
        )

    if "expected_catalog_query_mode" in case:
        checks["catalog_query_mode"] = (
            result.get("catalog_query_mode") == case["expected_catalog_query_mode"]
        )

    if "expected_is_closing" in case:
        checks["is_closing"] = (
            bool(result.get("is_closing")) == bool(case["expected_is_closing"])
        )

    passed_count = sum(1 for v in checks.values() if v)
    total = len(checks)
    return {
        "id": case["id"],
        "passed": all(checks.values()),
        "score": passed_count / total if total else 1.0,
        "details": checks,
    }


async def _run_intake(user_text: str) -> dict:
    """Run only the semantic_intake node against a test message."""
    os.environ.setdefault("SHIFUDEV_MODE", "false")

    from app.agent.shared.nodes.semantic_intake import semantic_intake_node
    from app.agent.shifu_base_v1.graph.state import ShifuState
    from langchain_core.messages import HumanMessage

    fake_state = ShifuState(
        messages=[HumanMessage(content=user_text)],
        user_id="eval-test",
        conversation_id="eval-conv",
        current_time_utc="2026-06-20T12:00:00Z",
        apps_involved=[],
        validation_reports=[],
        missing_variables=[],
        needs_external_info=False,
        is_closing=False,
        location_aware=False,
        needs_fact_verification=False,
        account_selection_resolved=False,
        decision_logged=False,
        eval_retry_count=0,
    )
    return await semantic_intake_node(fake_state)


async def main(update_baseline: bool = False, fail_delta: float = 0.0) -> int:
    dataset = _load_dataset()
    results = []

    for case in dataset:
        print(f"  [{case['id']}] {case['input'][:60]}", end="  ", flush=True)
        try:
            result = await _run_intake(case["input"])
            score = _score_case(case, result)
            status = "✓" if score["passed"] else "✗"
            print(status, score["details"])
        except Exception as exc:
            score = {"id": case["id"], "passed": False, "score": 0.0, "details": {"error": str(exc)}}
            print(f"ERROR: {exc}")
        results.append(score)

    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    print(f"\n{'='*60}")
    print(f"Results: {passed}/{total} passed ({100*passed//total}%)")

    if update_baseline:
        with open(_BASELINE, "w") as f:
            json.dump({r["id"]: r["score"] for r in results}, f, indent=2)
        print(f"Baseline updated → {_BASELINE}")
        return 0

    if fail_delta > 0 and _BASELINE.exists():
        baseline = json.loads(_BASELINE.read_text())
        regressions = []
        for r in results:
            prev = baseline.get(r["id"], 1.0)
            if prev - r["score"] > fail_delta:
                regressions.append(f"  {r['id']}: {prev:.2f} → {r['score']:.2f} (Δ={prev-r['score']:.2f})")
        if regressions:
            print(f"\nREGRESSIONS (delta > {fail_delta}):")
            print("\n".join(regressions))
            return 1

    return 0 if passed == total else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--fail-delta", type=float, default=0.0)
    args = parser.parse_args()
    sys.exit(asyncio.run(main(update_baseline=args.update_baseline, fail_delta=args.fail_delta)))
