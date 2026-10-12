"""
LearningReflectionWorker — Learning System (Phase 7)

Reads intent_outcomes + observation_events, synthesizes failure/success patterns
per user via LLM (gpt-4o-mini), and writes them to agent_learning_memory.

Design:
  - Runs every LEARNING_REFLECTION_HOURS (default 6h).
  - Per-user synthesis only triggered when >= LEARNING_MIN_NEW_OUTCOMES (default 5)
    new outcomes exist since last synthesis AND >= LEARNING_MIN_HOURS_BETWEEN_SYNTH
    (default 1h) have elapsed — prevents thrashing on active users.
  - Reads last 50 intent_outcomes + last 20 observation_events per user.
  - LLM extracts failure_patterns and success_patterns.
  - Upserts one document per user in agent_learning_memory (never appends).

agent_learning_memory schema:
  {
    user_id, failure_patterns: [{failure_type, description, occurrences,
    confidence, last_confirmed}], success_patterns: [{pattern, occurrences,
    confidence, last_confirmed}], last_synthesized_at, synth_count,
    outcomes_processed
  }
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

from config import Config
from app.workers.heartbeat import worker_heartbeat

logger = logging.getLogger(__name__)

_REFLECTION_HOURS       = int(os.getenv("LEARNING_REFLECTION_HOURS", "6"))
_MIN_NEW_OUTCOMES       = int(os.getenv("LEARNING_MIN_NEW_OUTCOMES", "2"))
_MIN_HOURS_BETWEEN_SYNTH = int(os.getenv("LEARNING_MIN_HOURS_BETWEEN_SYNTH", "1"))
_OUTCOMES_LOOKBACK      = int(os.getenv("LEARNING_OUTCOMES_LOOKBACK", "50"))
_OBS_LOOKBACK           = int(os.getenv("LEARNING_OBS_LOOKBACK", "20"))

_COL_OUTCOMES   = "intent_outcomes"
_COL_OBS        = "observation_events"
_COL_LEARNING   = "agent_learning_memory"

_MODEL = os.getenv("V3_MEMORY_MODEL", "gpt-4o-mini")

_SYNTH_PROMPT = """You are analyzing an AI assistant's execution history to extract behavioral patterns.

INTENT OUTCOMES (most recent first — what actions were attempted and whether they succeeded):
{outcomes_text}

OBSERVATION EVENTS (most recent first — post-execution verification results):
{observations_text}

Extract patterns from this data. Return ONLY valid JSON with this exact structure:
{{
  "failure_patterns": [
    {{
      "failure_type": "tool_misuse|wrong_intent|verification_fail|partial_failure|slow_execution",
      "description": "Specific, actionable description of the recurring failure (max 120 chars)",
      "occurrences": <integer>,
      "confidence": <float 0.0-1.0>
    }}
  ],
  "success_patterns": [
    {{
      "pattern": "Specific description of what consistently works well (max 120 chars)",
      "occurrences": <integer>,
      "confidence": <float 0.0-1.0>
    }}
  ]
}}

Rules:
- Only include failure_patterns with occurrences >= 2 and confidence >= 0.5.
- Only include success_patterns with occurrences >= 2 and confidence >= 0.6.
- failure_type must be exactly one of: tool_misuse, wrong_intent, verification_fail, partial_failure, slow_execution.
- Descriptions must be specific (not generic like "be more careful"). Reference the tool or intent_type.
- Max 4 failure_patterns, max 3 success_patterns.
- Return ONLY the JSON object. No markdown, no explanation."""


def _fmt_outcomes(docs: list[dict]) -> str:
    lines = []
    for d in docs:
        lines.append(
            f"- intent={d.get('intent_type','?')} tool={d.get('tool_used','?')} "
            f"success={d.get('success')} err={d.get('error_type','none')} "
            f"ms={d.get('execution_time_ms','?')}"
        )
    return "\n".join(lines) if lines else "(none)"


def _fmt_observations(docs: list[dict]) -> str:
    lines = []
    for d in docs:
        status = d.get("verification_status")
        lines.append(
            f"- tool={d.get('tool','?')} verified={status} "
            f"expected={str(d.get('expected_outcome',''))[:60]} "
            f"actual={str(d.get('actual_outcome',''))[:60]}"
        )
    return "\n".join(lines) if lines else "(none)"


async def _synthesize_user(user_id: str, db: AsyncIOMotorDatabase) -> None:
    """Run LLM reflection synthesis for one user."""
    from langchain_openai import ChatOpenAI
    now = datetime.now(timezone.utc)

    # Load existing doc to check timing + count
    existing = await db[_COL_LEARNING].find_one({"user_id": user_id}, {"_id": 0})
    last_synth = (existing or {}).get("last_synthesized_at")
    synth_count = int((existing or {}).get("synth_count", 0))

    if last_synth:
        hours_since = (now - last_synth).total_seconds() / 3600
        if hours_since < _MIN_HOURS_BETWEEN_SYNTH:
            logger.debug(
                "[LearningReflection] skip user=%s (synth %dh ago)", user_id, int(hours_since)
            )
            return

        # Check new outcomes since last synthesis
        new_count = await db[_COL_OUTCOMES].count_documents(
            {"user_id": user_id, "timestamp": {"$gt": last_synth.isoformat()}}
        )
        if new_count < _MIN_NEW_OUTCOMES:
            logger.debug(
                "[LearningReflection] skip user=%s (only %d new outcomes)", user_id, new_count
            )
            return

    # Load recent outcomes + observations
    outcomes = await (
        db[_COL_OUTCOMES]
        .find(
            {"user_id": user_id},
            {"_id": 0, "intent_type": 1, "tool_used": 1, "success": 1,
             "error_type": 1, "execution_time_ms": 1},
        )
        .sort("timestamp", -1)
        .limit(_OUTCOMES_LOOKBACK)
        .to_list(_OUTCOMES_LOOKBACK)
    )

    if not outcomes:
        return

    observations = await (
        db[_COL_OBS]
        .find(
            {"user_id": user_id, "verification_status": {"$ne": None}},
            {"_id": 0, "tool": 1, "verification_status": 1,
             "expected_outcome": 1, "actual_outcome": 1},
        )
        .sort("timestamp", -1)
        .limit(_OBS_LOOKBACK)
        .to_list(_OBS_LOOKBACK)
    )

    prompt = _SYNTH_PROMPT.format(
        outcomes_text=_fmt_outcomes(outcomes),
        observations_text=_fmt_observations(observations),
    )

    try:
        llm = ChatOpenAI(model=_MODEL, temperature=0, max_tokens=600, timeout=30)
        resp = await llm.ainvoke(prompt)
        raw = (resp.content or "").strip()
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        parsed = json.loads(raw)
    except Exception as exc:
        logger.warning("[LearningReflection] LLM/parse failed user=%s: %s", user_id, exc)
        return

    failure_patterns = []
    for p in (parsed.get("failure_patterns") or [])[:4]:
        failure_patterns.append({
            "failure_type":   p.get("failure_type", "tool_misuse"),
            "description":    str(p.get("description", ""))[:120],
            "occurrences":    max(2, int(p.get("occurrences", 2))),
            "confidence":     min(1.0, max(0.0, float(p.get("confidence", 0.6)))),
            "last_confirmed": now,
        })

    success_patterns = []
    for p in (parsed.get("success_patterns") or [])[:3]:
        success_patterns.append({
            "pattern":        str(p.get("pattern", ""))[:120],
            "occurrences":    max(2, int(p.get("occurrences", 2))),
            "confidence":     min(1.0, max(0.0, float(p.get("confidence", 0.7)))),
            "last_confirmed": now,
        })

    await db[_COL_LEARNING].update_one(
        {"user_id": user_id},
        {
            "$set": {
                "failure_patterns":    failure_patterns,
                "success_patterns":    success_patterns,
                "last_synthesized_at": now,
                "synth_count":         synth_count + 1,
                "outcomes_processed":  len(outcomes),
                "updated_at":          now,
            },
            "$setOnInsert": {"created_at": now, "user_id": user_id},
        },
        upsert=True,
    )
    logger.info(
        "[LearningReflection] synthesized user=%s failures=%d successes=%d synth_count=%d",
        user_id, len(failure_patterns), len(success_patterns), synth_count + 1,
    )


async def _tick(db: AsyncIOMotorDatabase) -> None:
    """Scan all users with recent outcomes and synthesize if due."""
    since = datetime.now(timezone.utc) - timedelta(hours=_REFLECTION_HOURS * 2)
    try:
        # Find distinct user_ids with recent outcomes
        user_ids = await db[_COL_OUTCOMES].distinct(
            "user_id", {"timestamp": {"$gt": since.isoformat()}}
        )
        if not user_ids:
            logger.debug("[LearningReflection] no users with recent outcomes")
            return
        logger.info("[LearningReflection] tick — candidates=%d", len(user_ids))
        for user_id in user_ids:
            try:
                await _synthesize_user(user_id, db)
            except Exception as exc:
                logger.warning(
                    "[LearningReflection] synthesis failed user=%s: %s", user_id, exc
                )
    except Exception as exc:
        logger.warning("[LearningReflection] tick failed: %s", exc)


class LearningReflectionWorker:
    """
    Background worker that periodically synthesizes per-user learning patterns
    from intent_outcomes + observation_events into agent_learning_memory.
    """

    def __init__(self, poll_hours: int = _REFLECTION_HOURS):
        self.poll_seconds = poll_hours * 3600
        self._running = False

    async def start(self, db: AsyncIOMotorDatabase) -> None:
        self._running = True
        logger.info(
            "[LearningReflectionWorker] Started (poll every %dh, min_outcomes=%d)",
            self.poll_seconds // 3600, _MIN_NEW_OUTCOMES,
        )
        if Config.REDIS_URL:
            asyncio.create_task(
                worker_heartbeat("learning_reflection", Config.REDIS_URL, lambda: self._running)
            )
        while self._running:
            try:
                await _tick(db)
            except Exception as exc:
                logger.exception("[LearningReflectionWorker] Unhandled error: %s", exc)
            await asyncio.sleep(self.poll_seconds)
        logger.info("[LearningReflectionWorker] Stopped.")

    def stop(self) -> None:
        self._running = False


# Module-level singleton — imported by main.py
learning_reflection_worker = LearningReflectionWorker()
