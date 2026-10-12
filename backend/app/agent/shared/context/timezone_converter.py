"""
timezone_converter — general-purpose helper

Deterministic timezone conversion for research text. Pure Python — no LLM.

Finds time+timezone patterns like "7:00 PM ET" or "1:00 PM PDT" in raw text
and injects the user's local equivalent inline:

    "7:00 PM ET"   →  "7:00 PM ET (8:00 PM Guatemala)"
    "7:00 PM (hora local)"  →  unchanged  (no label → venue local, can't convert)

Called in research_curator_node (Phase C) after semantic synthesis, so the
enriched text reaches ShifuState as curated_research — the responder receives
pre-computed values and never has to convert timezones itself.
"""

import logging
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)

# Timezone abbreviation → IANA name.
# Ambiguous abbreviations (e.g. IST = India/Ireland/Israel) are intentionally omitted.
_TZ_MAP: dict[str, str] = {
    # North America
    "ET":  "America/New_York",
    "EST": "America/New_York",
    "EDT": "America/New_York",
    "CT":  "America/Chicago",
    "CST": "America/Chicago",
    "CDT": "America/Chicago",
    "MT":  "America/Denver",
    "MST": "America/Denver",
    "MDT": "America/Denver",
    "PT":  "America/Los_Angeles",
    "PST": "America/Los_Angeles",
    "PDT": "America/Los_Angeles",
    "AKT": "America/Anchorage",
    "AKST": "America/Anchorage",
    "AKDT": "America/Anchorage",
    "HT":  "Pacific/Honolulu",
    "HST": "Pacific/Honolulu",
    # Europe
    "GMT":  "Europe/London",
    "BST":  "Europe/London",
    "CET":  "Europe/Berlin",
    "CEST": "Europe/Berlin",
    "WET":  "Europe/Lisbon",
    "WEST": "Europe/Lisbon",
    # Universal
    "UTC": "UTC",
}

# Match: "7:00 PM" followed by optional separator and an explicit timezone label.
# Does NOT match "hora local", "local time", etc. (no timezone code → no conversion).
_TIME_RE = re.compile(
    r'(\d{1,2}:\d{2}\s*(?:AM|PM))'       # group 1: time  e.g. "7:00 PM"
    r'[ \t]*'                              # optional whitespace
    r'(?:[\(\[–\-/][ \t]*)?'              # optional opening bracket/dash/slash
    r'(AKDT|AKST|CEST|WEST|'              # group 2: tz label (longest first to avoid partial match)
    r'EDT|EST|CDT|CST|MDT|MST|PDT|PST|'
    r'AKT|HT|HST|GMT|BST|CET|WET|UTC|'
    r'ET|CT|MT|PT)'
    r'\b',
    re.IGNORECASE,
)


def convert_times_in_text(text: str | None, user_tz_str: str | None) -> str | None:
    """Scan text for explicit-TZ time patterns and append user local time inline.

    Args:
        text:        Research string (curated or raw). May be None.
        user_tz_str: IANA timezone of the user (e.g. "America/Guatemala").

    Returns:
        Enriched string with inline conversions, or the original if nothing to do.
    """
    if not text or not user_tz_str:
        return text

    try:
        user_tz = ZoneInfo(user_tz_str)
    except (ZoneInfoNotFoundError, KeyError):
        logger.warning("[timezone_converter] unknown user TZ: %s — skipping", user_tz_str)
        return text

    tz_short = user_tz_str.split("/")[-1].replace("_", " ")  # e.g. "Guatemala"
    today    = datetime.now(timezone.utc).date()
    count    = 0

    def _replace(m: re.Match) -> str:
        nonlocal count
        time_raw = m.group(1).strip()   # e.g. "7:00 PM"
        tz_label = m.group(2).upper()   # e.g. "ET"

        src_iana = _TZ_MAP.get(tz_label)
        if not src_iana:
            return m.group(0)

        try:
            src_tz   = ZoneInfo(src_iana)
            # Normalize "7:00 PM" → remove extra spaces before parsing
            time_clean = re.sub(r'\s+', ' ', time_raw).upper()
            naive    = datetime.strptime(f"{today} {time_clean}", "%Y-%m-%d %I:%M %p")
            src_dt   = naive.replace(tzinfo=src_tz)
            local_dt = src_dt.astimezone(user_tz)
            # Cross-platform strftime without leading zero
            local_str = local_dt.strftime("%I:%M %p").lstrip("0") or "12:00 AM"
            count += 1
            return f"{m.group(0)} ({local_str} {tz_short})"
        except Exception as exc:
            logger.debug("[timezone_converter] failed to convert %r: %s", m.group(0), exc)
            return m.group(0)

    result = _TIME_RE.sub(_replace, text)

    if count:
        logger.info("[timezone_converter] converted %d time(s) → %s", count, tz_short)

    return result
