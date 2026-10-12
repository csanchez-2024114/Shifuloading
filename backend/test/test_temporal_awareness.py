"""
test_temporal_awareness.py — agente_v3 Temporal Awareness audit suite

Tests the three temporal-awareness layers deterministically without hitting
external APIs (LLMs, MongoDB, Tavily).

  Layer 1 — System Time Grounding:
    build_time_context_block() produces a UTC + local-time block that changes
    every second, so tests freeze time with unittest.mock.patch.

  Layer 2 — Chrono Parsing:
    parse_schedule() converts natural-language expressions to cron + next_run
    using only Python math + dateutil. No LLM involved.

  Layer 3 — Memory Staleness:
    load_user_prefs_block() annotates preferences older than 30 days with
    "hace N días". Tests use a mock MongoDB object.

  Temporal anchoring:
    The _build_user_prompt() helper in semantic_intake receives current_time_utc
    and appends it to the user message so the intake LLM knows the actual date.

Run with:
  .venv/Scripts/pytest test/test_temporal_awareness.py -v
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.asyncio


# ─────────────────────────────────────────────────────────────────────────────
# Layer 1 — System Time Grounding
# ─────────────────────────────────────────────────────────────────────────────

class TestTimeContextBlock:
    def test_utc_fallback_when_no_timezone(self):
        """With no timezone, block defaults to UTC and shows a missing-tz note."""
        from app.agent.shared.context.time_context import build_time_context_block

        block = build_time_context_block(None)

        assert "UTC:" in block
        assert "TZ:    UTC" in block
        assert "user_timezone is unknown" in block

    def test_valid_timezone_renders_local_time(self):
        """With a valid IANA timezone, local time appears in the block."""
        from app.agent.shared.context.time_context import build_time_context_block

        block = build_time_context_block("America/Mexico_City")

        assert "TZ:    America/Mexico_City" in block
        assert "Local:" in block
        assert "user_timezone is unknown" not in block

    def test_invalid_timezone_falls_back_to_utc(self):
        """An unrecognized timezone string must fall back to UTC gracefully."""
        from app.agent.shared.context.time_context import build_time_context_block

        block = build_time_context_block("Mars/Olympus_Mons")

        assert "TZ:    UTC" in block

    def test_block_contains_temporal_rules(self):
        """The block must include the resolution rules that the LLM needs."""
        from app.agent.shared.context.time_context import build_time_context_block

        block = build_time_context_block("America/Bogota")

        assert "hoy" in block
        assert "mañana" in block
        assert "próximo lunes" in block

    def test_utc_timestamp_format(self):
        """UTC timestamp must follow ISO 8601 with Z suffix."""
        from app.agent.shared.context.time_context import build_time_context_block

        block = build_time_context_block(None)
        # Find the UTC line and verify format
        utc_line = next(line for line in block.splitlines() if line.startswith("UTC:"))
        timestamp = utc_line.replace("UTC:", "").strip()
        # Must parse as ISO 8601 ending in Z
        assert timestamp.endswith("Z")
        datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ")  # raises if invalid


# ─────────────────────────────────────────────────────────────────────────────
# Layer 2 — Chrono Parsing
# ─────────────────────────────────────────────────────────────────────────────

ANCHOR = datetime(2026, 6, 11, 13, 20, 0, tzinfo=timezone.utc)   # Thursday


class TestChronoParser:
    def _parse(self, expr: str) -> dict | None:
        from app.agent.shared.helpers.chrono_parser import parse_schedule
        return parse_schedule(expr, ANCHOR)

    def test_weekly_spanish_lunes_9am(self):
        result = self._parse("todos los lunes a las 9am")
        assert result is not None
        assert result["cron"] == "0 9 * * 1"
        assert result["type"] == "weekly"
        assert "Monday" in result["human"]
        assert result["next_run"].startswith("2026-06-15")  # next Monday from anchor

    def test_weekly_english_friday(self):
        result = self._parse("every friday at 3pm")
        assert result is not None
        assert result["cron"] == "0 15 * * 5"
        assert result["type"] == "weekly"
        assert "Friday" in result["human"]

    def test_daily_spanish(self):
        result = self._parse("diariamente a las 8am")
        assert result is not None
        assert result["cron"] == "0 8 * * *"
        assert result["type"] == "daily"

    def test_daily_english(self):
        result = self._parse("every day at 6pm")
        assert result is not None
        assert result["cron"] == "0 18 * * *"
        assert result["type"] == "daily"

    def test_hourly(self):
        result = self._parse("cada hora")
        assert result is not None
        assert result["cron"] == "0 * * * *"
        assert result["type"] == "hourly"

    def test_monthly_spanish(self):
        result = self._parse("mensualmente a las 10am")
        assert result is not None
        assert result["cron"] == "0 10 1 * *"
        assert result["type"] == "monthly"

    def test_unknown_expression_returns_none(self):
        result = self._parse("cuando me acuerde")
        assert result is None

    def test_empty_expression_returns_none(self):
        from app.agent.shared.helpers.chrono_parser import parse_schedule
        assert parse_schedule("", ANCHOR) is None

    def test_next_run_is_in_the_future(self):
        """next_run must always be after the anchor datetime."""
        result = self._parse("todos los martes a las 9am")
        assert result is not None
        next_run = datetime.strptime(result["next_run"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        assert next_run > ANCHOR

    def test_next_monday_from_anchor_thursday(self):
        """From Thursday June 11, next Monday should be June 15."""
        result = self._parse("lunes a las 9am")
        assert result is not None
        assert "2026-06-15" in result["next_run"]

    def test_cron_format_has_five_fields(self):
        result = self._parse("every wednesday at 2pm")
        assert result is not None
        fields = result["cron"].split()
        assert len(fields) == 5


# ─────────────────────────────────────────────────────────────────────────────
# Layer 3 — Memory Staleness
# ─────────────────────────────────────────────────────────────────────────────

class TestPreferencesLoader:
    def _make_db(self, prefs: dict) -> MagicMock:
        """Build a minimal mock that load_preferences() will return prefs from."""
        return MagicMock()  # actual patching is done per-test

    async def test_stale_preference_annotated(self):
        """Preferences older than 30 days must include 'hace N días'."""
        from app.agent.shared.helpers.preferences_loader import load_user_prefs_block

        stale_date = datetime.now(timezone.utc) - timedelta(days=45)
        fake_prefs = {
            "user_language": {"value": "es", "updated_at": stale_date},
        }

        with patch("app.agent.shared.helpers.preferences_loader.load_preferences",
                   new_callable=AsyncMock, return_value=fake_prefs):
            block, _ = await load_user_prefs_block("user_test", MagicMock())

        assert block is not None
        assert "hace 45 días" in block or "hace 4" in block  # allow ±1 day rounding

    async def test_fresh_preference_not_annotated(self):
        """Preferences updated within 30 days must appear without staleness note."""
        from app.agent.shared.helpers.preferences_loader import load_user_prefs_block

        fresh_date = datetime.now(timezone.utc) - timedelta(days=5)
        fake_prefs = {
            "user_language": {"value": "en", "updated_at": fresh_date},
        }

        with patch("app.agent.shared.helpers.preferences_loader.load_preferences",
                   new_callable=AsyncMock, return_value=fake_prefs):
            block, _ = await load_user_prefs_block("user_test", MagicMock())

        assert block is not None
        assert "hace" not in block

    async def test_timezone_extracted_from_prefs(self):
        """user_timezone field in prefs must be returned as the second tuple element."""
        from app.agent.shared.helpers.preferences_loader import load_user_prefs_block

        fresh_date = datetime.now(timezone.utc)
        fake_prefs = {
            "user_timezone": {"value": "America/Bogota", "updated_at": fresh_date},
        }

        with patch("app.agent.shared.helpers.preferences_loader.load_preferences",
                   new_callable=AsyncMock, return_value=fake_prefs):
            _, user_timezone = await load_user_prefs_block("user_test", MagicMock())

        assert user_timezone == "America/Bogota"

    async def test_no_prefs_returns_none_block(self):
        """When user has no preferences, both return values must be None."""
        from app.agent.shared.helpers.preferences_loader import load_user_prefs_block

        with patch("app.agent.shared.helpers.preferences_loader.load_preferences",
                   new_callable=AsyncMock, return_value={}):
            block, tz = await load_user_prefs_block("user_test", MagicMock())

        assert block is None
        assert tz is None

    async def test_load_failure_returns_none(self):
        """DB errors must be swallowed — node must not crash."""
        from app.agent.shared.helpers.preferences_loader import load_user_prefs_block

        with patch("app.agent.shared.helpers.preferences_loader.load_preferences",
                   new_callable=AsyncMock, side_effect=Exception("DB timeout")):
            block, tz = await load_user_prefs_block("user_test", MagicMock())

        assert block is None
        assert tz is None


# ─────────────────────────────────────────────────────────────────────────────
# Temporal Anchoring — current_time_utc propagation
# ─────────────────────────────────────────────────────────────────────────────

class TestTemporalAnchoring:
    def test_build_user_prompt_includes_system_date(self):
        """When current_time_utc is provided, the user prompt must contain it."""
        from app.agent.shared.nodes.semantic_intake import _build_user_prompt

        prompt = _build_user_prompt(
            original="busca noticias recientes",
            history="",
            current_time_utc="2026-06-11T13:20:00Z",
        )

        assert "2026-06-11T13:20:00Z" in prompt
        assert "SYSTEM DATE" in prompt

    def test_build_user_prompt_no_date_when_empty(self):
        """When current_time_utc is empty, the prompt must not add a SYSTEM DATE line."""
        from app.agent.shared.nodes.semantic_intake import _build_user_prompt

        prompt = _build_user_prompt(
            original="hola",
            history="",
            current_time_utc="",
        )

        assert "SYSTEM DATE" not in prompt

    def test_build_user_prompt_preserves_history(self):
        """History must always appear before the current message."""
        from app.agent.shared.nodes.semantic_intake import _build_user_prompt

        prompt = _build_user_prompt(
            original="y ahora qué?",
            history="User: hola\nShifu: Hola!",
            current_time_utc="2026-06-11T13:20:00Z",
        )

        assert "RECENT CONVERSATION" in prompt
        assert prompt.index("RECENT CONVERSATION") < prompt.index("CURRENT MESSAGE")
        assert "2026-06-11T13:20:00Z" in prompt

