"""
Conversation context tool — lets the agent dynamically recover the conversation
history from MongoDB when it feels it lacks context (e.g. during process discovery
when the user says "don't you remember what we were talking about?").

The agent calls this tool proactively when the current session data is insufficient
to understand what the user wants, rather than asking them to repeat themselves.
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


class RecoverConversationContextInput(BaseModel):
    last_n: int = Field(
        default=10,
        description=(
            "Number of recent messages to recover from this conversation. "
            "Use 5–10 to get enough context without overwhelming. Default: 10."
        ),
    )


def get_conversation_context_bigtools(
    user_id: str,
    db: Any,
    conversation_id: Optional[str] = None,
    **kwargs,
) -> List[BigTool]:
    """
    Factory for the conversation context recovery tool.
    Requires user_id, db, and conversation_id — injected by the registry.
    """

    async def _recover_context(last_n: int = 10) -> str:
        """
        Fetch the last N messages from the current conversation in MongoDB
        and return them as a formatted transcript the agent can reason about.
        """
        if db is None or not user_id or not conversation_id:
            return "(No conversation history available — missing db or conversation_id.)"

        try:
            raw_msgs = (
                await db["chat_messages"]
                .find({"user_id": user_id, "conversation_id": conversation_id})
                .sort("created_at", -1)
                .limit(max(1, min(last_n, 30)))
                .to_list(length=max(1, min(last_n, 30)))
            )
        except Exception as exc:
            logger.warning(f"[ConvContextTool] DB error user={user_id}: {exc}")
            return "(Error loading conversation history — please try again.)"

        if not raw_msgs:
            return "(No previous messages found in this conversation.)"

        lines = []
        for m in reversed(raw_msgs):
            role = "User" if m.get("role") == "user" else "Assistant"
            content = (m.get("content") or "")[:300]
            lines.append(f"{role}: {content}")

        return (
            f"Last {len(lines)} messages from this conversation:\n\n"
            + "\n".join(lines)
        )

    return [
        BigTool(
            name="recuperar_contexto_conversacion",
            description=(
                "Recovers the recent message history from this conversation from the database. "
                "Use this tool proactively when you feel you lack context — for example, "
                "when the user says 'don't you remember what we were talking about?', "
                "'we already discussed this', or references something you don't have in your current context. "
                "Do NOT ask the user to repeat themselves — call this tool first and read the history. "
                "Returns the last N messages as a transcript you can reason about."
            ),
            tool=_recover_context,
            args_schema=RecoverConversationContextInput,
        )
    ]
