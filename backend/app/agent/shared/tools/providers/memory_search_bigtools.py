"""
Memory search tool — lets the agent search across ALL past conversations using
semantic similarity on global memory chunks.

Use this when the user asks about something they mentioned before (country, company,
boss, projects, decisions) that isn't available in the current context window,
or when global_memory hasn't been built yet and the user expects the agent to remember.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, List, Optional, Type

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


@dataclass
class BigTool:
    name: str
    description: str
    tool: Any
    args_schema: Optional[Type[BaseModel]] = None


class SearchUserHistoryInput(BaseModel):
    query: str = Field(
        ...,
        description=(
            "What to search for in the user's conversation history. "
            "Be specific: 'user country Guatemala', 'company name', 'boss name', "
            "'automation project Gmail', etc."
        ),
    )


def get_memory_search_bigtools(
    user_id: str,
    db: Any,
    **kwargs,
) -> List[BigTool]:
    """
    Factory for the cross-conversation memory search tool.
    Requires user_id and db — injected by the registry.
    """

    async def _search_history(query: str) -> str:
        """
        Search across ALL past conversations using semantic similarity on
        global memory chunks, then fall back to plain text search on raw messages.
        """
        if db is None or not user_id:
            return "(Memory search unavailable — missing context.)"

        # Primary: search agente_v2 global memory text
        try:
            mem_doc = await db["user_global_memory"].find_one({"user_id": user_id}, {"_id": 0, "memory_text": 1})
            if mem_doc and mem_doc.get("memory_text"):
                logger.info(f"[MemorySearchTool] global memory hit user={user_id}")
                return f"Found in long-term memory:\n\n{mem_doc['memory_text'][:1500]}"
        except Exception as exc:
            logger.warning(f"[MemorySearchTool] global memory search failed user={user_id}: {exc}")

        # Fallback: plain text search on raw chat_messages (for new users without global memory yet)
        try:
            search_term = query[:60]
            raw_msgs = (
                await db["chat_messages"]
                .find(
                    {
                        "user_id": user_id,
                        "content": {"$regex": search_term, "$options": "i"},
                    }
                )
                .sort("created_at", -1)
                .limit(6)
                .to_list(6)
            )
            if raw_msgs:
                lines = []
                for m in reversed(raw_msgs):
                    role = "User" if m.get("role") == "user" else "Assistant"
                    content = (m.get("content") or "")[:200]
                    lines.append(f"{role}: {content}")
                logger.info(f"[MemorySearchTool] text fallback hit user={user_id} msgs={len(lines)}")
                return f"Found in raw conversation history:\n\n" + "\n".join(lines)
        except Exception as exc:
            logger.warning(f"[MemorySearchTool] text fallback failed user={user_id}: {exc}")

        return (
            "No matching information found in your conversation history for this query. "
            "The user may not have mentioned this before, or the memory hasn't been built yet."
        )

    return [
        BigTool(
            name="buscar_en_historial",
            description=(
                "Search across ALL past conversations to find something the user mentioned before — "
                "their country, company, email, boss, past projects, decisions, or any specific fact. "
                "Call this when: (1) the user asks 'do you remember X?' and it's not in the current context, "
                "(2) the user says 'I already told you X' and you don't have it, "
                "(3) you need a specific personal fact (country, company, role) that isn't in the identity block. "
                "Do NOT call this for general questions — only when looking for user-specific past information. "
                "Returns relevant passages from the user's history."
            ),
            tool=_search_history,
            args_schema=SearchUserHistoryInput,
        )
    ]
