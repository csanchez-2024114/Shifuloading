"""
time_context — agente_v3

Builds the current-time system message block injected at the END of the
system prompt every turn so the LLM can resolve relative temporal expressions
("mañana", "el próximo lunes", "en dos horas") using the server's real clock
instead of guessing from its training cutoff.

Position rule (Prefix Stability / cache efficiency):
  This block MUST be placed LAST in the system message list — after identity,
  greeting, auth, research, preferences, clarified intent, and mood directive.
  Any change earlier in the list would break the LLM provider cache prefix and
  increase token costs on every turn.

Adapted from app/agents/agente_v2/prompts/time_context.py.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def build_time_context_block(
    user_tz_str: str | None,
    user_location: str | None = None,
    language_hint: str | None = None,
) -> str:
    """Return a Markdown system message block with UTC + local time + optional geo context.

    Args:
        user_tz_str:   IANA timezone string (e.g. "America/Mexico_City"). Falls back to UTC.
        user_location: Human-readable city/country from GeoIP (e.g. "Guatemala City, Guatemala").
        language_hint: Language label from geo_context (e.g. "Spanish (Latin American — Guatemala)").
    """
    tz_str  = (user_tz_str or "").strip() or "UTC"
    now_utc = datetime.now(timezone.utc)

    try:
        tz        = ZoneInfo(tz_str)
        now_local = now_utc.astimezone(tz)
    except (ZoneInfoNotFoundError, KeyError):
        tz_str    = "UTC"
        now_local = now_utc

    # Compute UTC offset as a human-readable label, e.g. "America/Guatemala (UTC-6)"
    offset_td    = now_local.utcoffset()
    offset_secs  = int(offset_td.total_seconds()) if offset_td else 0
    offset_h     = offset_secs // 3600
    offset_m     = abs(offset_secs % 3600) // 60
    sign         = "+" if offset_secs >= 0 else ""
    utc_offset   = f"UTC{sign}{offset_h}" + (f":{offset_m:02d}" if offset_m else "")
    tz_label     = f"{tz_str} ({utc_offset})"

    missing_tz_note = (
        "\n- user_timezone is unknown — use UTC as reference. "
        "If the user mentions scheduling, ask for their city or timezone first."
        if tz_str == "UTC" and not user_tz_str
        else ""
    )

    geo_lines = ""
    if user_location:
        geo_lines += f"\nLocation: {user_location}"
    if language_hint:
        geo_lines += (
            f"\nLanguage: {language_hint} — understand regional expressions, "
            "local slang, and cultural references accordingly."
        )

    return (
        "## Current Time [internal — use this to resolve all temporal expressions]\n"
        f"UTC:   {now_utc.strftime('%Y-%m-%dT%H:%M:%SZ')}\n"
        f"TZ:    {tz_label}\n"
        f"Local: {now_local.strftime('%Y-%m-%dT%H:%M:%S')} "
        f"({now_local.strftime('%A, %d %B %Y')})"
        f"{geo_lines}\n\n"
        "Rules:\n"
        "- Resolve ALL relative temporal expressions using Local datetime above.\n"
        "  'hoy' = today's local date. 'mañana' = tomorrow. "
        "'el próximo lunes' = next Monday from local date.\n"
        "- When confirming a scheduled time with the user, always state the local time and timezone.\n"
        "- Times in the research that carry an explicit timezone label (ET, PT, PDT, CET…) have "
        "already been converted to your local time by the system — show the pre-computed value as given.\n"
        "- If a source says only 'local time' / 'hora local' WITHOUT a timezone label, "
        "it refers to the venue's local time. Present it exactly as given — do NOT attempt to convert.\n"
        f"- Never invent or assume the current date — always use the value above.{missing_tz_note}"
    )
