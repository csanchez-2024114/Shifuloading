"""
context_ranker — agente_v3

Heuristic scoring of retrieved memories to produce a ranked_context string
injected into the responder system prompt.

Priority order: Goal > Decision > Structured > Semantic > Episodic
Bonus: +2.0 when the memory text matches any app in apps_involved.
Threshold: only blocks with score > 0.5 are included.
Cap: top 5 blocks.
"""

import logging

logger = logging.getLogger(__name__)


def rank_memories(
    memories: dict,
    intent: str,
    apps_involved: list[str],
) -> str:
    """Score memory blocks and return a formatted string for the LLM prompt."""
    scored_blocks: list[tuple[float, str]] = []
    intent_lower  = intent.lower()
    apps_lower    = [a.lower() for a in (apps_involved or [])]

    def _app_bonus(text: str) -> float:
        return 2.0 if any(a in text.lower() for a in apps_lower) else 0.0

    # ── Goals (base 3.0 — highest priority) ──────────────────────────────────
    for goal in memories.get("goals") or []:
        title  = goal.get("title", "")
        status = goal.get("status", "active")
        score  = 3.0 + _app_bonus(title)
        if any(w in intent_lower for w in title.lower().split() if len(w) > 3):
            score += 1.5
        scored_blocks.append((score, f"[GOAL] {title} (status: {status})"))

    # ── Decisions (base 2.5) ──────────────────────────────────────────────────
    for dec in memories.get("decisions") or []:
        context  = dec.get("context", "")
        decision = dec.get("decision", "")
        reason   = dec.get("reason", "")
        score    = 2.5 + _app_bonus(context + decision)
        if any(w in intent_lower for w in context.lower().split() if len(w) > 3):
            score += 1.0
        scored_blocks.append((
            score,
            f"[DECISION] {decision[:120]} — razón: {reason[:80]}",
        ))

    # ── Structured preferences (base 1.5) ────────────────────────────────────
    structured = memories.get("structured") or {}
    for key, entry in structured.items():
        val   = entry.get("value", entry) if isinstance(entry, dict) else entry
        score = 1.5 + _app_bonus(str(val))
        if key.lower() in intent_lower:
            score += 1.0
        scored_blocks.append((score, f"[PREFERENCE] {key}: {val}"))

    # ── Semantic inferences (base 1.0) ────────────────────────────────────────
    for inf in memories.get("semantic") or []:
        aspect = inf.get("aspect", "")
        value  = inf.get("value", "")
        conf   = float(inf.get("confidence", 0.5))
        score  = 1.0 * conf + _app_bonus(aspect + str(value))
        if aspect.lower() in intent_lower:
            score += 1.5
        scored_blocks.append((score, f"[INFERENCE] {aspect}: {value}"))

    # ── Episodic diary (base 0.5) ─────────────────────────────────────────────
    for entry in memories.get("episodic") or []:
        date       = entry.get("date", "")
        activities = entry.get("activities", [])
        text       = ", ".join(str(a) for a in activities) if isinstance(activities, list) else str(activities)
        score      = 0.5 + _app_bonus(text)
        if any(w in intent_lower for w in text.lower().split() if len(w) > 3):
            score += 1.0
        scored_blocks.append((score, f"[EPISODIC {date}] {text[:120]}"))

    # ── Rank and filter ───────────────────────────────────────────────────────
    scored_blocks.sort(key=lambda x: x[0], reverse=True)
    top_blocks = [block for score, block in scored_blocks if score > 0.5][:5]

    if not top_blocks:
        return ""

    return "\n".join(top_blocks)
