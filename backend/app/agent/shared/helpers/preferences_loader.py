"""
preferences_loader — agente_v3

Loads user preferences from MongoDB (user_preferences collection) and formats
them into a system-prompt block annotated with data staleness.

Staleness annotation:
  - Fresh  (< 30 days since updated_at)  → "- {key}: {value}"
  - Stale  (≥ 30 days)                   → "- {key} (hace {N} días): {value}"
  - No timestamp                         → treated as fresh (no annotation)

This lets the LLM deprioritize old preferences that may no longer be accurate
(e.g. a timezone set 5 months ago when the user was in a different country).

Also extracts user_timezone for the time_context helper.

Reuses app.services.chat_memory.load_preferences() — no duplicate DB logic.
"""

import logging
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.services.chat_memory import load_preferences

logger = logging.getLogger(__name__)

_STALE_DAYS = 30   # threshold for adding staleness annotation
_SKIP_KEYS  = {"user_id", "_id"}  # fields to never show in prompt


async def load_user_prefs_block(
    user_id: str,
    db: AsyncIOMotorDatabase,
) -> tuple[str | None, str | None]:
    """Load user preferences and format with staleness annotations.

    Returns:
        (formatted_block, user_timezone)

        formatted_block: Markdown section for system prompt injection, or None
                         if the user has no preferences stored.
        user_timezone:   IANA timezone string (e.g. "America/Mexico_City") or None.
    """
    try:
        prefs = await load_preferences(user_id, db)
    except Exception as exc:
        logger.warning("[preferences_loader] load failed for user=%s: %s", user_id, exc)
        return None, None

    if not prefs:
        return None, None

    now          = datetime.now(timezone.utc)
    lines: list[str] = []
    user_timezone: str | None = None

    for key, entry in prefs.items():
        if key in _SKIP_KEYS:
            continue

        value = entry.get("value") if isinstance(entry, dict) else entry
        if value is None or value == "":
            continue

        # Extract timezone before formatting
        if key == "user_timezone":
            user_timezone = str(value)

        # Staleness calculation
        updated_at = entry.get("updated_at") if isinstance(entry, dict) else None
        staleness_note = ""

        if updated_at is not None:
            try:
                if updated_at.tzinfo is None:
                    updated_at = updated_at.replace(tzinfo=timezone.utc)
                days_since = (now - updated_at).days
                if days_since >= _STALE_DAYS:
                    staleness_note = f" (hace {days_since} días)"
            except Exception:
                pass

        lines.append(f"- {key}{staleness_note}: {value}")

    if not lines:
        return None, user_timezone

    block = "## User Preferences [internal — context about this user]\n" + "\n".join(lines)
    logger.info("[preferences_loader] user=%s  prefs=%d  timezone=%s",
                user_id, len(lines), user_timezone or "unknown")
    return block, user_timezone
