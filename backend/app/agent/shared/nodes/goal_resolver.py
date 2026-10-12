"""
goal_resolver — agente_v3

First node in the graph. Resolves which active goal is relevant to this turn.

Strategy:
  1. Load all active goals for the user (sorted newest first).
  2. If only one goal → use it directly.
  3. If multiple → keyword match against the last HumanMessage as tiebreaker.
  4. If no goals → goal_id = None (rest of the graph works normally).
"""

import logging

from langchain_core.messages import HumanMessage

from app.agent.shifu_base_v1.graph.state import ShifuState
from app.agent.shared.memory.goal_memory_helper import load_active_goals
from app.agent.shared.utils.log_utils import DEV_MODE, dev_print
from app.core.mongo import mongo_manager

logger = logging.getLogger(__name__)

_LINE = "─" * 63


async def goal_resolver_node(state: ShifuState) -> dict:
    user_id = state.get("user_id")
    if not user_id:
        return {"goal_id": None}

    db = mongo_manager.db
    active_goals = await load_active_goals(db, user_id)

    if not active_goals:
        if DEV_MODE:
            dev_print(
                f"\n┌─ Memory · Goal Resolver {_LINE[24:]}\n"
                f"│ user_id  : {user_id}\n"
                f"│ goals    : 0 activos\n"
                f"│ resolved : None — sin goals activos\n"
                f"└{_LINE}"
            )
        return {"goal_id": None}

    # Keyword tiebreaker using last HumanMessage
    last_msg = next(
        (m.content.lower() for m in reversed(state.get("messages") or [])
         if isinstance(m, HumanMessage)),
        "",
    )

    keyword_hit = False
    resolved_id = active_goals[0]["goal_id"]  # default: most recent

    if len(active_goals) > 1 and last_msg:
        for goal in active_goals:
            title_words = [w for w in goal.get("title", "").lower().split() if len(w) > 3]
            if any(w in last_msg for w in title_words):
                resolved_id = goal["goal_id"]
                keyword_hit = True
                break

    strategy = "keyword match" if keyword_hit else "most recent"

    if DEV_MODE:
        dev_print(
            f"\n┌─ Memory · Goal Resolver {_LINE[24:]}\n"
            f"│ user_id  : {user_id}\n"
            f"│ goals    : {len(active_goals)} activos\n"
            f"│ resolved : {resolved_id}\n"
            f"│ strategy : {strategy}\n"
            f"└{_LINE}"
        )

    logger.info("[goal_resolver] user=%s  goal_id=%s  strategy=%s", user_id, resolved_id, strategy)
    return {"goal_id": resolved_id}

