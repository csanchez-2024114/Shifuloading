"""
responder — agente_v3

Single convergence node. Replaces the separate aggregator + chat nodes.

Receives ALL outputs from the parallel validation pipeline (catalog_checker,
auth_validator, tavily_searcher, bigtools_inspector) already in ShifuState,
then does two things in one pass:

  1. Aggregation (pure Python, no LLM):
       Reads validation_reports + missing_variables → determines requirement_level
       and builds error_context when validation failed.

  2. Presentation (LLM, streaming):
       Builds the system prompt from MongoDB identity/personality with explicit
       Markdown formatting directives, then calls the chat LLM to generate the
       user-facing response.

Conditional graph routing (handled in graph.py):
  - is_closing=True  → semantic_intake routes DIRECTLY to responder, bypassing
                        all parallel validators (no wasted API calls).
  - is_closing=False → validators run first, then fan-in here.

Prompt block order (for LLM provider cache efficiency):
  1. Static block       — identity + principles + restrictions + style (CACHED)
  2. Greeting rule      — changes only turn-1 vs. turn-N+1
  3. Auth policy        — only during level_1 validation errors
  4. Error context      — aggregated validation errors (level_1 only)
  5. External research  — tavily results (when available)
  6. Clarified intent   — structured EN intent (not shown to user)
"""

import json
import logging
import os
import re
from datetime import datetime, timezone as _utc
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, SystemMessage
from app.agent.shared.nodes.action_runner import format_action_results, format_pending_block
from app.agent.shared.helpers.platform_context import app_capability, build_platform_context
from app.agent.shared.helpers.situation import drop_shadowed_auth_errors, flow_facts, has_connectable_block, mood_fact, pause_facts
from langchain_openai import ChatOpenAI

from app.agent.shared.context.geo_context import get_language_hint
from app.agent.shared.utils.log_utils import DEV_MODE, dev_print
from app.agent.shared.helpers.identity_loader import (
    build_system_messages,
    get_agent_identity,
    get_agent_personality,
)
from app.agent.shared.memory.conversation_compactor import window_messages
from app.agent.shared.helpers.stage_logger import (
    log_stage_completed,
    log_stage_suspended,
    log_stage_updated,
)
from app.agent.shared.context.time_context import build_time_context_block
from app.agent.shifu_base_v1.graph.state import ShifuState

logger = logging.getLogger(__name__)

# Respaldo de agent_personality.prompt_snippets.web_unavailable (el texto es dato; este es el generico).
_WEB_UNAVAILABLE = (
    "WEB SEARCH: this request needed information from the internet and the search returned nothing this turn (it is "
    "unavailable right now). Say plainly, in one sentence, that you could not search the web right now. Do NOT say you "
    "lack the ability to search, and do NOT answer with facts from memory as if they were current (prices, news, dates, "
    "latest versions). Then offer what you can do without the search."
)
_WEB_FOUND = (
    "WEB SEARCH: you DID search the internet this turn and the research above is what it found. Answer the question "
    "from it, directly: give the fact with the date it refers to and say it comes from a web search. The user wants "
    "CURRENT information: when the research has facts from different dates, use the most recent and leave the older "
    "ones out unless the user asked for history; never present a fact from a past month or year as the current one. "
    "If the most recent fact is older than what the user asked for (they said today and the data is from days ago), "
    "say that date plainly. If two sources give different values for the same thing, give both with their source "
    "instead of silently choosing one. Do NOT say you cannot access current or real-time information, and do not send"
    " the user to look elsewhere for what the research already answers. If the research does not answer the question,"
    " say what it did find and what it did not."
    " The research starts with an ANALYST JUDGMENT that already reasoned about the sources: build your answer on "
    "its conclusion, in your own words; never use a source it discarded; tell the user its caveats; and when its "
    "confidence is medium or low say plainly what is solid and what is not instead of sounding certain."
)

_ALLOWED_MODELS = {"gpt-4o-mini", "gpt-4.1-nano"}
_DEFAULT_MODEL  = "gpt-4o-mini"
# ── Inference-Time Scaling — effort tier config ───────────────────────────────
_EFFORT_DIRECTIVES: dict[str, str] = {
    "low":   "EFFORT DIRECTIVE: Be extremely brief. Answer in 1 short paragraph. Skip complex details.",
    "medio": "EFFORT DIRECTIVE: Use structured Markdown lists. Be precise and clear.",
    "high":  (
        "EFFORT DIRECTIVE: Provide an in-depth analysis in Markdown. "
        "Use ## headers and bold text. Cite concrete facts and data from retrieved research."
    ),
    "max":   (
        "EFFORT DIRECTIVE: Produce a research-grade synthesis structured as: "
        "## Executive Summary — ## Detailed Fact Analysis (exact dates, statistics, citations) — "
        "## Identified Gaps. Expose your full logical reasoning. Omit no relevant data."
    ),
}
_EFFORT_TEMPERATURE: dict[str, float] = {
    "low": 0.5, "medio": 0.5, "high": 0.3, "max": 0.1,
}
_EFFORT_MAX_TOKENS: dict[str, int] = {
    "low": 300, "medio": 600, "high": 1_500, "max": 4_000,
}
_DEFAULT_EFFORT = "medio"


# ── Mood state ────────────────────────────────────────────────────────────────

# Injected at the END of the system prompt so it never breaks the static cache prefix.
_MOOD_DIRECTIVES: dict[str, str] = {
    "DEFAULT":        "TONE DIRECTIVE: Maintain casual-professional tone. Keep questions to 1 per turn.",
    "HELPFUL":        "TONE DIRECTIVE: Be warm, encouraging, and explain steps simply.",
    "DIRECT_EMPATHY": (
        "TONE DIRECTIVE: The user is frustrated or in a hurry. "
        "Absolutely NO emojis. Be concise, extremely empathetic, and do not make excuses. "
        "Solve the issue in under 50 words. Do not repeat information already given."
    ),
    "CLOSING":        "TONE DIRECTIVE: User is leaving. Say a warm goodbye in 1 turn. Do not ask any follow-up questions.",
}


def _compute_mood(
    user_sentiment: str | None,
    requirement_level: str | None,
    is_closing: bool,
) -> tuple[str, str]:
    """Determine the final mood_state for this turn. Returns (mood, reason).

    Business rules (applied in priority order):
      1. is_closing → always CLOSING
      2. frustrated / urgent → DIRECT_EMPATHY
      3. level_1 errors + confused → DIRECT_EMPATHY (user hit a wall)
      4. calm / polite / neutral → HELPFUL
      5. fallback → DEFAULT
    """
    if is_closing:
        return "CLOSING", "is_closing=True"
    sentiment = (user_sentiment or "neutral").lower()
    if sentiment in ("frustrated", "urgent"):
        return "DIRECT_EMPATHY", f"sentiment={sentiment}"
    if requirement_level == "level_1" and sentiment == "confused":
        return "DIRECT_EMPATHY", f"level_1 + sentiment=confused"
    if sentiment in ("calm", "polite", "neutral"):
        return "HELPFUL", f"sentiment={sentiment}"
    return "DEFAULT", "fallback (no matching rule)"


def _fmt_tz(tz_name: str | None, utc_iso: str = "") -> str:
    """Return 'America/Guatemala (UTC-6)' — computes offset from the given UTC moment."""
    if not tz_name:
        return "UTC (unknown)"
    try:
        tz = ZoneInfo(tz_name)
        try:
            dt = datetime.fromisoformat(utc_iso.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            dt = datetime.now(_utc.utc)
        offset_h = int(dt.astimezone(tz).utcoffset().total_seconds() / 3600)
        sign = "+" if offset_h >= 0 else ""
        return f"{tz_name} (UTC{sign}{offset_h})"
    except (ZoneInfoNotFoundError, Exception):
        return tz_name


def _dev_box_temporal(state: ShifuState, current_time_block: str, effort: str = "medio") -> None:
    """Print a single consolidated temporal + effort audit box (only in dev mode)."""
    current_time_utc   = state.get("current_time_utc") or "unknown"
    user_tz            = _fmt_tz(state.get("user_timezone"), current_time_utc)
    user_location      = state.get("user_location") or "unknown"
    sched              = state.get("schedule_context")
    prefs              = state.get("user_preferences_context")

    sched_line = (
        f"{sched.get('cron')} / {sched.get('human')} (next: {sched.get('next_run')})"
        if sched else "none"
    )
    prefs_line = f"{len(prefs)} chars loaded" if prefs else "none"
    temp       = _EFFORT_TEMPERATURE.get(effort, 0.7)
    max_tok    = _EFFORT_MAX_TOKENS.get(effort, 600)

    dev_print(
        f"\n┌─ Temporal + Effort Audit ──────────────────────────────────\n"
        f"│ system_time  : {current_time_utc}\n"
        f"│ user_tz      : {user_tz}\n"
        f"│ location     : {user_location}\n"
        f"│ schedule     : {sched_line}\n"
        f"│ preferences  : {prefs_line}\n"
        f"│ effort       : {effort}  (temp={temp}  max_tokens={max_tok})\n"
        f"└────────────────────────────────────────────────────────────"
    )


def _dev_box_mood(
    prev_mood: str | None,
    new_mood: str,
    sentiment: str | None,
    reason: str = "",
) -> None:
    prev_label = prev_mood or "DEFAULT"
    changed    = "→ changed" if prev_label != new_mood else "→ no change"
    dev_print(
        f"├─ Mood Transition ──────────────────────────────────────────\n"
        f"│  [Old Mood] {prev_label}  {changed}\n"
        f"│      ▼\n"
        f"│  [New Mood] {new_mood}\n"
        f"│  Sentiment : {sentiment or 'neutral'}\n"
        f"│  Reason    : {reason}\n"
        f"└────────────────────────────────────────────────────────────"
    )


# ── Catalog helpers ────────────────────────────────────────────────────────────

def _format_catalog_by_category(grouped: dict) -> str:
    """Build a markdown bullet list of apps grouped by category."""
    lines: list[str] = []
    for category, apps in grouped.items():
        lines.append(f"**{category.title()}**")
        for app in apps:
            lines.append(f"• {app}")
        lines.append("")
    return "\n".join(lines).strip()


# ── Aggregation helpers (was aggregator_node) ─────────────────────────────────

def _build_error_context(reports: list[dict], missing_vars: list[str]) -> str:
    reports         = drop_shadowed_auth_errors(reports)
    catalog_errors  = [r for r in reports if r.get("source") == "catalog"  and r.get("status") == "error"]
    auth_errors     = [r for r in reports if r.get("source") == "auth"     and r.get("status") == "error"]
    pending         = [r for r in reports if r.get("status") == "pending_selection"]
    tools_errors    = [r for r in reports if r.get("source") == "bigtools" and r.get("status") == "error"]
    add_accounts    = [r for r in reports if r.get("status") == "add_account"]

    parts = [
        "VALIDATION PAUSED — inform the user about what needs to be resolved. Be helpful and specific.\n"
    ]
    if add_accounts:
        app_names  = [r["app"].title() for r in add_accounts]
        apps_list  = ", ".join(app_names[:-1]) + (" y " + app_names[-1] if len(app_names) > 1 else app_names[0])
        btns_list  = ", ".join(f"'Conectar {a}'" for a in app_names)
        parts.append(
            f"ADD ACCOUNT: The user wants to connect: {apps_list}. "
            f"All connect buttons ({btns_list}) are ALREADY rendered in the UI just below this message. "
            f"Tone: warm, personal, companion — make the user feel you are WITH them through the process, "
            f"not just pointing at buttons and leaving. Use 'nosotros'/'juntos' framing when natural. "
            f"Convey it's quick and easy. Mention ALL apps by name. "
            f"Tell them you'll be here once each one is connected. "
            f"Do NOT describe manual steps. Do NOT say 'go to settings'. 3-4 sentences max."
        )
        read_only = [r["app"].title() for r in add_accounts if app_capability(r["app"]) == "read"]
        if read_only:
            # 1 de cada 3 abria con "conectemos Discord para que recibas notificaciones" y lo corregia despues (v043).
            parts.append(f"READ-ONLY: {', '.join(read_only)} can only be READ by the platform today: it cannot send "
                         f"messages or notifications there. If the user wants alerts through it, your FIRST sentence says "
                         f"it cannot send alerts there yet; never write 'connect it so you receive notifications' or similar, "
                         f"not even before correcting it. Then offer an app that can send.")
    if pending:
        for r in pending:
            accounts = r.get("accounts", [])
            emails   = [a.get("email") or a.get("account_id", "?") for a in accounts]
            parts.append(
                f"MULTIPLE ACCOUNTS: '{r['app']}' has {len(emails)} connected accounts. "
                f"Ask the user which one to use for this workflow: {emails}"
            )
    if catalog_errors:
        for r in catalog_errors:
            reason = r.get("reason", "not_found")
            app    = r["app"]
            if reason == "maintenance":
                parts.append(f"APP IN MAINTENANCE: '{app}' is temporarily unavailable. Inform the user to try later.")
            else:
                parts.append(f"APP NOT INTEGRATED YET: '{app}' is not integrated yet — the team keeps adding new integrations, so it may be possible later (no dates, no guarantees); today it cannot be connected, used as a trigger or used for any action, so offer what works today.")
    if auth_errors:
        for r in auth_errors:
            reason = r.get("reason", "not_connected")
            app    = r["app"]
            if reason == "expired":
                parts.append(
                    f"EXPIRED CONNECTION: '{app}' token expired — user must reconnect. "
                    "The reconnect button is ALREADY rendered in the UI below. "
                    "Tell the user to click it in 1-2 sentences. This limits only the note about the connection: if the user asked for something else (e.g. the steps of the automation, a list, bullet points), also answer it, in the format they asked."
                )
            elif reason == "revoked":
                parts.append(
                    f"REVOKED ACCESS: '{app}' was revoked — user must reauthorize. "
                    "The connect button is ALREADY rendered in the UI below. "
                    "Tell the user to click it in 1-2 sentences. This limits only the note about the connection: if the user asked for something else (e.g. the steps of the automation, a list, bullet points), also answer it, in the format they asked."
                )
            else:
                parts.append(
                    f"NOT CONNECTED: '{app}'. "
                    "The connect button is ALREADY rendered in the UI just below this message. "
                    "Tell the user to click it in 1-2 sentences; do NOT describe manual steps to connect or say 'go to settings'. This limits only the note about the connection: if the user asked for something else (e.g. the steps of the automation, a list, bullet points), also answer it, in the format they asked."
                )
    if tools_errors:
        for r in tools_errors:
            parts.append(f"TOOLS UNAVAILABLE: {r.get('message', 'Cannot map intent to tools')}")
    if missing_vars:
        parts.append(f"MISSING PARAMETERS: {missing_vars} — ask the user for these.")

    return "\n".join(parts)


def _aggregate(state: ShifuState) -> tuple[str | None, str | None]:
    """Pure Python aggregation. Returns (requirement_level, error_context)."""
    reports      = state.get("validation_reports") or []
    missing_vars = state.get("missing_variables")  or []
    apps         = state.get("apps_involved")       or []
    is_closing   = bool(state.get("is_closing"))
    catalog_mode = state.get("catalog_query_mode")

    if is_closing or not apps or catalog_mode in ("list_connected", "list_available"):
        return None, None
    # Pregunta informativa que ya se respondio buscando en internet ("novedades de la API de Gmail"): nombrar una app no
    # es querer usarla, asi que la cuenta sin conectar no pausa la respuesta (v0.9.3; contestaba "primero conecta Gmail").
    intent = (state.get("semantic_intake_debug") or {}).get("detected_intent")
    if (state.get("curated_research") or state.get("retrieved_research")) and intent in ("question", "exploring", "chat"):
        return None, None

    errors       = [r for r in reports if r.get("status") == "error"]
    pending      = [r for r in reports if r.get("status") == "pending_selection"]
    add_accounts = [r for r in reports if r.get("status") == "add_account"]

    if errors or pending or add_accounts:
        return "level_1", _build_error_context(reports, missing_vars)
    return "level_2", None


def _log_stage_lifecycle(state: ShifuState, new_level: str | None) -> None:
    """Emit the appropriate Stage lifecycle event based on aggregation result."""
    if not DEV_MODE or not new_level:
        return
    session_id  = state.get("conversation_id") or "—"
    apps        = state.get("apps_involved") or []
    prev_level  = state.get("requirement_level")
    reports     = state.get("validation_reports") or []

    if prev_level != new_level:
        reason = (
            "All validations passed" if new_level == "level_2"
            else "Validation errors or pending account selection"
        )
        log_stage_updated(session_id, prev_level, new_level, reason)

    if new_level == "level_1":
        pending = [r for r in reports if r.get("status") == "pending_selection"]
        errors  = [r for r in reports if r.get("status") == "error"]
        if pending:
            wait_for = [
                email
                for r in pending
                for a in (r.get("accounts") or [])
                for email in [a.get("email") or a.get("account_id", "?")]
            ]
            reason = f"Multiple accounts for: {[r['app'] for r in pending]}"
        else:
            wait_for = [r.get("app", "?") for r in errors]
            reason   = f"Auth or catalog errors: {[r.get('message', '') for r in errors]}"
        log_stage_suspended(session_id, new_level, reason, wait_for)

    elif new_level == "level_2":
        log_stage_completed(session_id, apps)


def _dev_box_aggregation(state: ShifuState, requirement_level: str | None) -> None:
    reports          = state.get("validation_reports") or []
    missing_vars     = state.get("missing_variables")  or []
    raw_research     = state.get("retrieved_research")
    curated_research = state.get("curated_research")
    apps             = state.get("apps_involved")       or []

    ok_reports  = [r for r in reports if r.get("status") == "ok"]
    err_reports = [r for r in reports if r.get("status") == "error"]
    pnd_reports = [r for r in reports if r.get("status") == "pending_selection"]

    ok_lines  = [f"  ✓ [{r.get('source')}] {r.get('app') or r.get('apps')}" for r in ok_reports]
    err_lines = [f"  ✗ [{r.get('source')}] {r.get('app') or r.get('apps')} — {r.get('message','')}" for r in err_reports]
    pnd_lines = [f"  ⏳ [auth] {r.get('app')} — {len(r.get('accounts',[]))} accounts" for r in pnd_reports]

    decision = (
        "closing — skip validation" if state.get("is_closing")
        else (f"level_1 ({len(err_reports)} errors  {len(pnd_reports)} pending)" if requirement_level == "level_1"
              else "level_2 (ready)" if requirement_level == "level_2"
              else "none (pure chat)")
    )

    if curated_research:
        raw_chars = len(raw_research) if raw_research else 0
        research_line = f"curated ({len(curated_research):,} chars  raw was {raw_chars:,})"
    elif raw_research:
        research_line = f"raw ({len(raw_research):,} chars)"
    else:
        research_line = "none"

    dev_print(
        f"\n┌─ Responder [Aggregation] ───────────────────────────────────\n"
        f"│ apps        : {apps}\n"
        f"│ reports     : {len(reports)} total  ({len(ok_reports)} ok  {len(err_reports)} error  {len(pnd_reports)} pending)\n"
        + "".join(f"│ {l}\n" for l in ok_lines + err_lines + pnd_lines)
        + f"│ missing     : {missing_vars}\n"
        f"│ research    : {research_line}\n"
        f"│ → decision  : {decision}\n"
        f"└────────────────────────────────────────────────────────────"
    )


# ── Responder node ─────────────────────────────────────────────────────────────

def _last_user_text(state) -> str:
    last = next((m for m in reversed(state.get("messages") or []) if isinstance(m, HumanMessage)), None)
    return str(getattr(last, "content", "") or "")


# Una contraseña o llave pegada en el chat. Es angosto a proposito: una palabra de credencial seguida de "es / is / : / ="
# y un valor. Lo usa solo para recordarle al responder lo que la identidad ya manda.
_CREDENTIAL = re.compile(r"(contrase[ñn]a|password|passwd|clave|token|api[ _-]?key|secret)\b[^.\n]{0,30}?(\bes\b|\bis\b|\bson\b|:|=)\s*\S{4,}", re.IGNORECASE)

_OTHER_REQUESTS = (
    "The user sent ONE message that may contain several requests. An automation-setup flow already wrote FLOW MESSAGE; it "
    "will be shown to the user exactly as it is, right after your text, and it covers the automation they asked to "
    "create. Write ONLY the reply to the OTHER things the user asked in USER MESSAGE that FLOW MESSAGE does not cover:\n"
    "- if RESEARCH (web search results) answers one, answer it from RESEARCH, with its date if it has one;\n"
    "- if one needs data from their apps (their emails, a sheet, their tasks) or is not in RESEARCH, say in one short "
    "sentence that you will get to it right after they answer the question below. Never answer from memory.\n"
    "Everything the automation itself does is ALREADY covered and is NOT another request: what it reads (the sheet, the "
    "emails), what it sends, to whom and when. Another request is a separate question or task the user wants answered "
    "NOW, in this reply (\"y de paso dime…\", \"also tell me…\", a numbered list where some items are not the "
    "automation).\n"
    "If the user asked for nothing else, or you are not sure, reply exactly NONE.\n"
    "Same language as USER MESSAGE. No greeting, no question, at most 4 sentences. Do not mention, repeat or change "
    "the plan, its steps or its schedule."
)
_other_llm: dict = {}


async def _other_requests(state, flow_message: str) -> str:
    """Lo demas que el usuario pidio en el mismo mensaje. El mensaje del flujo (confirmacion del plan) se entrega tal cual
    y antes dejaba fuera el resto: "dime mis correos sin leer, el total de la hoja, arma un workflow y quien gano el
    mundial" recibia solo el plan (1 de 3, prueba extrema del 2026-10-11). Si falla, no se agrega nada."""
    if "llm" not in _other_llm:
        _other_llm["llm"] = ChatOpenAI(model="gpt-4o-mini", temperature=0, max_tokens=350, timeout=30, tags=["req_addendum"])
    try:
        resp = await _other_llm["llm"].ainvoke([
            SystemMessage(content=_OTHER_REQUESTS),
            HumanMessage(content=(f"USER MESSAGE:\n{_last_user_text(state)[:2000]}\n\nFLOW MESSAGE:\n{flow_message[:2500]}\n\n"
                                  f"RESEARCH:\n{str(state.get('curated_research') or '(none)')[:3500]}"))])
        text = str(resp.content or "").strip()
    except Exception as exc:
        logger.warning("[responder] other-requests addendum failed: %s", exc)
        return ""
    return "" if not text or text.upper().strip(" .") == "NONE" else text


async def responder_node(state: ShifuState) -> dict:
    model_name = state.get("model_name") or _DEFAULT_MODEL
    if model_name not in _ALLOWED_MODELS:
        model_name = _DEFAULT_MODEL

    # ── 1. Aggregation (pure Python) ──────────────────────────────────────────
    requirement_level, error_context = _aggregate(state)

    logger.info(
        "[responder] aggregation → apps=%s  level=%s  closing=%s",
        state.get("apps_involved") or [],
        requirement_level or "none",
        state.get("is_closing"),
    )

    if DEV_MODE:
        _dev_box_aggregation(state, requirement_level)
        _log_stage_lifecycle(state, requirement_level)

    # ── 2. Mood computation ───────────────────────────────────────────────────
    user_sentiment = state.get("user_sentiment")
    prev_mood      = state.get("mood_state")
    is_closing     = bool(state.get("is_closing"))

    mood_state, mood_reason = _compute_mood(user_sentiment, requirement_level, is_closing)

    logger.info(
        "[responder] mood → sentiment=%s  prev=%s  new=%s  reason=%s",
        user_sentiment or "—", prev_mood or "—", mood_state, mood_reason,
    )

    if DEV_MODE:
        _dev_box_mood(prev_mood, mood_state, user_sentiment, mood_reason)

    # ── 3. Presentation (LLM, streaming) ─────────────────────────────────────
    messages                  = list(state.get("messages") or [])
    # Reintento del evaluador: el borrador rechazado ni ancla al modelo ni se queda en el historial del hilo.
    # Se quita ANTES de calcular is_first_turn, para que el reintento reciba las mismas reglas que el primer intento.
    discarded_drafts = []
    if state.get("eval_feedback"):
        while messages and isinstance(messages[-1], AIMessage):
            discarded_drafts.append(RemoveMessage(id=messages.pop().id))
    structured                = state.get("structured_prompt")
    retrieved_research        = state.get("retrieved_research")
    curated_research          = state.get("curated_research")
    research_to_use           = curated_research or retrieved_research  # curated takes priority (already TZ-enriched)
    retrieved_sources_list    = state.get("retrieved_sources") or []
    user_timezone             = state.get("user_timezone")
    user_location             = state.get("user_location")
    user_country_code         = state.get("user_country_code")
    user_preferences_context  = state.get("user_preferences_context")
    user_name                 = state.get("user_name")
    effort_level              = (state.get("effort_level") or _DEFAULT_EFFORT)
    language_hint             = get_language_hint(user_country_code)

    is_first_turn = not any(isinstance(m, AIMessage) for m in messages)

    identity    = await get_agent_identity()
    personality = await get_agent_personality()
    # Textos de comportamiento editables por un admin (agent_personality.prompt_snippets); el codigo solo los coloca.
    snippets = personality.get("prompt_snippets") or {}
    # prompt_mode "brief": hechos de la situacion en vez de directivas apiladas (ver helpers/situation.py)
    brief = personality.get("prompt_mode") == "brief"
    if brief and requirement_level == "level_1":
        error_context = pause_facts(state.get("validation_reports") or [], state.get("missing_variables") or [])
    if error_context and snippets.get("paused_commitment") and has_connectable_block(state.get("validation_reports") or []):
        error_context += "\n" + snippets["paused_commitment"]
    greeting_intents = (personality.get("greeting_behavior") or {}).get("applies_to_intents") or ["chat"]

    system_msgs = build_system_messages(
        identity,
        personality,
        is_first_turn=is_first_turn,
        requirement_level=requirement_level,
        is_closing=is_closing,
        error_context=error_context,
        retrieved_research=research_to_use,
        user_preferences_context=user_preferences_context,
        user_name=user_name,
        user_memory=state.get("user_memory_context"),
        is_greeting=(state.get("semantic_intake_debug") or {}).get("detected_intent") in greeting_intents,
    )

    llm_messages = list(system_msgs)

    # ── 6. Clarified intent (internal) ───────────────────────────────────────
    # req_flow_action == "digress": the flow is paused (req_level untouched, on purpose —
    # see semantic_intake_node) but THIS turn was routed through the normal pipeline to
    # actually answer what the user asked, so it must NOT be treated as req_investigator
    # content to relay verbatim.
    req_flow_action = state.get("req_flow_action")
    # relay: este turno req_investigator escribio el mensaje (req_level puede ser None: activacion o cancelacion). Se entrega
    # tal cual; el resto del prompt que invita a improvisar (conocimiento de la plataforma, esfuerzo, anti-bucle) se omite.
    relay = bool(state.get("req_relay")) and bool(structured) and req_flow_action != "digress" and not is_closing
    if relay:
        # Se entrega TAL CUAL, sin pasar por el modelo: aun con la orden de "transmitir fiel", el responder quito el horario
        # y la pregunta "¿Lo activo asi?" e invento "asegurate de que la hoja sea publica" (v065_wf). El mensaje ya lo
        # redacto el flujo con hechos verificados; el streamer lo emite completo (no hay tokens de LLM).
        # Solo en el turno que paso por el analisis completo del intake (el primero del flujo): ahi es donde el mensaje
        # puede traer otros pedidos. Un "si" de confirmacion no llama a ningun modelo.
        other = await _other_requests(state, str(structured)) if state.get("semantic_intake_debug") else ""
        return {
            "messages":          [AIMessage(content=f"{other}\n\n{structured}" if other else str(structured))],
            "active_mandates":   None,
            "mood_state":        state.get("mood_state"),
            "requirement_level": state.get("requirement_level"),
        }
    if structured and not is_closing:
        if state.get("req_compose") and req_flow_action != "digress":
            # El flujo dejo hechos, no un mensaje final: UNA respuesta con ellos y con lo que el usuario pregunto.
            llm_messages.append(SystemMessage(content=flow_facts(str(structured))))
        else:
            llm_messages.append(
                SystemMessage(content=f"[Clarified user intent — internal use only]: {structured}")
            )

    # ── 6.5 Paused-flow digression ───────────────────────────────────────────
    if req_flow_action == "digress":
        llm_messages.append(SystemMessage(content=(
            "The user is in the middle of setting up an automation, but this message is "
            "about something else. Answer what they actually asked, naturally. Briefly "
            "mention at the end that you can pick the automation setup back up whenever "
            "they're ready — do not repeat or summarize the paused question."
        )))

    # ── 6.25 Planning trace (workflow_planner deliberative output) ───────────
    # Injected only when workflow_planner generated a trace (apps present + validated).
    # Acts as a binding execution blueprint: responder reads the plan and focuses
    # on natural language synthesis rather than re-deriving the execution logic.
    if planning_trace := state.get("planning_trace"):
        llm_messages.append(
            SystemMessage(content=f"EXECUTION PLAN (internal — do not reveal to user):\n{planning_trace}")
        )

    # ── 6.5 Cognitive memory context ─────────────────────────────────────────
    # ranked_context is scored+filtered by context_ranker from 5 memory types.
    # Injected here so the LLM has user goals and past decisions before responding.
    if ranked_context := state.get("ranked_context"):
        llm_messages.append(SystemMessage(content=f"MEMORY CONTEXT:\n{ranked_context}"))

    # ── 6.55 Document understanding (document_analyzer) ──────────────────────
    # turn_document_context: full text of short documents attached/referenced
    # this turn. retrieved_document_chunks: top-K passages for large documents
    # (Fase 3). structured_extraction: last structured extraction result, if any.
    if turn_document_context := state.get("turn_document_context"):
        llm_messages.append(SystemMessage(content=(
            f"DOCUMENT CONTEXT (files attached/referenced by the user this conversation):\n"
            f"{turn_document_context}"
        )))

    elif session_documents := state.get("session_documents"):
        # Turno siguiente sin adjunto nuevo: sin este hecho contestaba "no tengo acceso a archivos" sobre el que acababa de leer.
        names = ", ".join(d.get("title") or "file" for d in session_documents.values())
        llm_messages.append(SystemMessage(content=(
            f"FACT (from the system): earlier in this conversation the user attached these files and you read them: {names}. "
            "What you said about them came from those files. Never say you cannot access, open or read files.")))

    if retrieved_chunks := state.get("retrieved_document_chunks"):
        chunks_block = "\n\n".join(
            f"[{c.get('filename', '?')} — relevance {c.get('score', 0):.2f}]\n{c.get('text', '')}"
            for c in retrieved_chunks
        )
        llm_messages.append(SystemMessage(content=(
            f"RETRIEVED DOCUMENT EXCERPTS (most relevant passages from large documents, "
            f"not the full text):\n{chunks_block}"
        )))

    if structured_extraction := state.get("structured_extraction"):
        llm_messages.append(SystemMessage(content=(
            "STRUCTURED EXTRACTION RESULT (present this to the user clearly; if "
            "uncertain_fields/needs_review is present, explicitly ask the user to confirm "
            f"those specific fields):\n{json.dumps(structured_extraction, ensure_ascii=False)}"
        )))

    # ── 6.6 Self-correction feedback (response_evaluator retry) ─────────────
    # Injected only on retry turns. Placed after memory context so it overrides
    # cached persona without breaking the prompt cache prefix.
    if eval_feedback := state.get("eval_feedback"):
        correction = snippets.get("retry_correction") or (
            "[CORRECCIÓN] Tu respuesta anterior tuvo problemas. Corrígelos: {feedback}"
        )
        llm_messages.append(SystemMessage(content=correction.replace("{feedback}", eval_feedback)))

    # ── 6.7 Anti-looping rule ─────────────────────────────────────────────────
    # En un aviso de la interfaz no aplica: "no repitas la pregunta, varia" empujaba al modelo a abrir OTRA pregunta.
    if not brief and not state.get("system_event") and not relay:  # en relay repetir la pregunta del flujo es lo correcto
        llm_messages.append(SystemMessage(content=(
            "CRITICAL ANTI-LOOPING RULE: Review the last 2 AIMessages in the chat history. "
            "DO NOT repeat the exact same closing question, greeting, or call-to-action "
            "(e.g., '¿Hay algo más en lo que te pueda ayudar?'). "
            "If that support line was already generated in recent turns, transition naturally "
            "into a concise conclusion or stop generating without adding any boilerplate phrases."
        )))

    # ── 7. Mood directive — never breaks the static cache prefix ─────────────
    # Los textos viven en agent_personality.mood_directives / effort_directives (editables por admin);
    # los de este archivo son el respaldo si el documento no los trae.
    if brief:
        mood_directive = mood_fact(mood_state, user_sentiment)  # hecho observado o nada
    else:
        mood_directive = (
            (personality.get("mood_directives") or {}).get(mood_state)
            or _MOOD_DIRECTIVES.get(mood_state, _MOOD_DIRECTIVES["DEFAULT"])
        )
        # Pure conversational mode: no active workflow, no catalog query → no boilerplate closings
        _apps_for_mood = state.get("apps_involved") or []
        _cat_for_mood  = state.get("catalog_query_mode")
        # (con el flujo de requisitos activo SI hay un workflow en curso: este texto lo contradecia)
        if not _apps_for_mood and not _cat_for_mood and not is_closing and state.get("req_level") is None and not relay:
            mood_directive += (
                " CONVERSATIONAL MODE: No active workflow. "
                "Reply naturally as a direct continuation of the conversation. "
                "Omit boilerplate support closings or repeated greetings."
            )
    if mood_directive:
        llm_messages.append(SystemMessage(content=mood_directive))

    # ── 7.5 Effort grounding directive ───────────────────────────────────────
    # DIRECT_EMPATHY already constrains length to under 50 words — skip effort
    # length directive to avoid conflicting instructions. En modo "brief" el largo lo decide el modelo.
    effort_directive = None
    if mood_state != "DIRECT_EMPATHY" and not brief and not relay:  # el largo lo manda el mensaje del flujo
        effort_directive = (
            (personality.get("effort_directives") or {}).get(effort_level)
            or _EFFORT_DIRECTIVES.get(effort_level, _EFFORT_DIRECTIVES[_DEFAULT_EFFORT])
        )
        llm_messages.append(SystemMessage(content=effort_directive))

    # ── 7.55 Platform knowledge — el agente guia con las apps y funciones reales, no con consejos genericos ─
    if not is_closing and not relay:  # el flujo ya dijo lo que hay que decir; este bloque invitaba a improvisar capacidades
        platform_knowledge = await build_platform_context(state)
        if platform_knowledge:
            llm_messages.append(SystemMessage(content=platform_knowledge))
    if state.get("needs_external_info") and not (state.get("curated_research") or state.get("retrieved_research")):
        # Hacia falta buscar en internet y no llego nada (sin llave, error o tiempo agotado). Sin este aviso el agente
        # decia "no tengo la capacidad de buscar", que es falso, o contestaba de memoria como si fuera actual (v0.9.2).
        llm_messages.append(SystemMessage(content=snippets.get("web_unavailable") or _WEB_UNAVAILABLE))
    elif research_to_use:
        # Con resultados en la mano el modelo seguia diciendo "no tengo acceso a datos en tiempo real" (v092_web_real).
        llm_messages.append(SystemMessage(content=snippets.get("web_found") or _WEB_FOUND))
    if state.get("action_results") is not None:  # modo act: los datos reales de sus apps
        llm_messages.append(SystemMessage(content=format_action_results(state["action_results"], state.get("action_stop"))))
    if pending_block := format_pending_block(state):  # escrituras que esperan el "si", cancelacion o "si" poco claro
        llm_messages.append(SystemMessage(content=pending_block))

    # Lo que el evaluador debe exigir este turno (es lo que de verdad llego al modelo, no una suposicion).
    active_mandates = [
        m for m in (error_context if requirement_level == "level_1" else None, mood_directive, effort_directive) if m
    ]

    # ── 7.6 Research grounding directive — only when research is available ────
    # Prevents the LLM from paraphrasing specific facts into generalities.
    # When sources are available, instructs the LLM to embed [N] citation markers
    # after each sentence so the frontend can render them as inline source chips.
    # TODAY anchor: prevents the LLM from using source publication dates as "today".
    if research_to_use:
        _today_raw  = state.get("current_time_utc") or ""
        _date_line  = f"TODAY: {_today_raw}. " if _today_raw else ""
        if state.get("research_freshness"):  # que ventana de fechas se busco de verdad (y si hubo que ampliarla)
            _date_line += f"SEARCH WINDOW: {state['research_freshness']} "
        _date_rule  = (
            "DATE RULE: Use TODAY as the reference date in your response. "
            "If the research sources are from an earlier date, note it naturally "
            "(e.g. 'según información del 12 de junio') — never present old data as if it were today's.\n"
        )
        _catalog_mode = state.get("catalog_query_mode")
        _allow_citations = _catalog_mode not in ("list_available", "list_connected")
        if retrieved_sources_list and _allow_citations:
            source_map = "\n".join(
                f"[{i+1}] {s.get('title') or s.get('domain', '')} — {s.get('domain', '')}"
                + (f" — published {s['published']}" if s.get("published") else "")
                for i, s in enumerate(retrieved_sources_list[:10])
            )
            llm_messages.append(SystemMessage(content=(
                f"{_date_line}"
                "RESEARCH DIRECTIVE: Specific facts are provided above in External Research. "
                "Cite concrete facts, names, dates, and figures — do not paraphrase into generalities.\n"
                f"{_date_rule}"
                "CITATION RULE: After each sentence that uses information from a specific source, "
                "append its number in square brackets immediately after the sentence — e.g. [1] or [2]. "
                "Only cite where the fact actually came from that source. Do not fabricate citations.\n"
                f"AVAILABLE SOURCES:\n{source_map}"
            )))
        else:
            llm_messages.append(SystemMessage(content=(
                f"{_date_line}"
                "RESEARCH DIRECTIVE: Specific facts are provided above in External Research. "
                "Cite concrete facts, names, dates, and figures — do not paraphrase into generalities.\n"
                f"{_date_rule}"
            )))

    # ── 8. Current time block (Capa 1) — always mutable, always last ─────────
    current_time_block = build_time_context_block(user_timezone, user_location, language_hint)
    llm_messages.append(SystemMessage(content=current_time_block))

    if DEV_MODE:
        _dev_box_temporal(state, current_time_block, effort_level)

    # ── 9. Catalog / connected listing — always last, closest to generation ───
    # Pre-fill + LLM reasoning: the list is embedded in a RESPONSE FRAME so the
    # LLM fills in intro/closing placeholders rather than generating the list itself.
    catalog_mode      = state.get("catalog_query_mode")
    catalog_available = state.get("catalog_available_apps") if catalog_mode == "list_available" else None
    catalog_grouped   = state.get("catalog_apps_grouped")   if catalog_mode == "list_available" else None
    user_connected    = state.get("user_connected_apps")    if catalog_mode == "list_connected"  else None

    if catalog_available is not None:
        if catalog_grouped:
            formatted_list = _format_catalog_by_category(catalog_grouped)
            # El catalogo es dato, no un texto a copiar: con "reproduce la lista EXACTA" el agente no podia responder
            # "que apps de comunicacion hay" y el evaluador lo rechazaba hasta agotar los intentos.
            llm_messages.append(SystemMessage(content=(
                "PLATFORM CATALOG (ground truth — the only apps that exist on the platform, by category):\n\n"
                f"{formatted_list}\n\n"
                "Answer what the user actually asked from this list: if they asked about a category or a specific "
                "app, show only that part; if they asked for everything, show it all. Never add, rename or invent apps."
            )))
        elif catalog_available:
            apps_str = "\n".join(f"• {a}" for a in catalog_available)
            llm_messages.append(SystemMessage(content=(
                "RESPONSE FRAME — complete this response for the user:\n\n"
                "---\n"
                "[Write a 1-2 sentence intro in the user's language]\n\n"
                f"{apps_str}\n\n"
                "[Write 1 closing sentence]\n"
                "---\n\n"
                "CRITICAL: The app list above is FIXED. Reproduce it EXACTLY. "
                "Only replace the [bracketed placeholders] with actual text."
            )))
        else:
            llm_messages.append(SystemMessage(content=(
                "PLATFORM INTEGRATIONS: No apps are currently available. "
                "Inform the user there are no integrations configured yet. "
                "Do NOT suggest or invent any apps."
            )))

    if user_connected is not None:
        if user_connected:
            # Build per-provider list with account emails as sub-bullets
            lines: list[str] = []
            for provider, emails in user_connected.items():
                lines.append(f"• **{provider}**")
                for email in emails:
                    if email:
                        lines.append(f"  - {email}")
                    else:
                        lines.append(f"  - (cuenta conectada)")
            connected_str = "\n".join(lines)
            llm_messages.append(SystemMessage(content=(
                "RESPONSE FRAME — complete this response for the user:\n\n"
                "---\n"
                "[Write a 1-2 sentence intro — confirm these are their connected apps and accounts]\n\n"
                f"{connected_str}\n\n"
                "[Optional: 1 closing sentence — e.g. mention they can connect more from settings]\n"
                "---\n\n"
                "CRITICAL: The app/account list above is FIXED. Reproduce it EXACTLY — same providers, "
                "same account emails as sub-bullets. Only replace the [bracketed placeholders] with actual text."
            )))
        else:
            llm_messages.append(SystemMessage(content=(
                "USER CONNECTED APPS: The user has no apps connected yet. "
                "Invite them warmly to connect their first integration. "
                "Do NOT say 'go to settings' or describe manual steps."
            )))
    elif catalog_mode == "list_connected":
        # Specific providers queried but not connected (user_connected_apps = None)
        # The connect button is already rendered in the UI via ui_actions
        missing_apps = [
            r["app"] for r in (state.get("validation_reports") or [])
            if r.get("source") == "auth" and r.get("needs_auth")
        ]
        if missing_apps:
            apps_str = ", ".join(missing_apps)
            llm_messages.append(SystemMessage(content=(
                "RESPONSE FRAME — complete this response for the user:\n\n"
                "---\n"
                f"[1-2 sentences: tell the user {apps_str} is not connected yet "
                "and invite them to click the connect button below]\n"
                "---\n\n"
                f"CRITICAL: Do NOT say you lack access to their accounts. "
                f"Shifu has full access to their data — {apps_str} simply hasn't been authorized yet. "
                "Do NOT describe manual steps to connect or mention settings. The frame covers only the connection note: if the "
                "user asked for the steps of the automation, a list or bullet points, give them too, in that format."
            )))

    # Compactacion: con resumen se manda resumen + ventana (los mensajes viejos siguen en el checkpoint, solo no se envian).
    if state.get("conversation_summary"):
        llm_messages.append(SystemMessage(content=(
            "Earlier in this conversation (summary of older messages; the user said these things):\n"
            f"{state['conversation_summary']}"
        )))
        messages = window_messages(messages, state.get("summary_upto"))
    llm_messages += messages

    # Aviso de la interfaz (system_event): va al FINAL, pegado a la generacion. A mitad del prompt le ganaban la voz
    # ("termina con una pregunta") y la regla anti-bucle, y el agente dejaba dos preguntas abiertas seguidas.
    # El texto es dato: prompt_snippets.system_event.
    if state.get("system_event"):
        llm_messages.append(SystemMessage(content=snippets.get("system_event") or (
            "The last message is an automatic notice from the interface, not something the user wrote. Acknowledge it "
            "in one short sentence. If your previous message asked the user something they have not answered yet, do "
            "not ask anything new and do not repeat that question: the conversation is waiting for their answer."
        )))

    # Preferencias vigentes del usuario (idioma, formato): tambien al FINAL. En el bloque de memoria, a mitad del prompt,
    # el agente guardaba "respondeme en ingles" y en la sesion siguiente contestaba en espanol (preferencia_respetada).
    # Que claves cuentan y el texto son dato: memory_policy.standing_keys / standing_note.
    policy = personality.get("memory_policy") or {}
    standing = [f for f in ((state.get("raw_memories") or {}).get("semantic") or [])
                if f.get("value") and f.get("key") in (policy.get("standing_keys") or ["language", "preferences"])]
    if standing and not relay:
        llm_messages.append(SystemMessage(content=(policy.get("standing_note") or (
            "STANDING PREFERENCES — the user told you this in an earlier conversation and it still applies. Whatever in "
            "it is about HOW to answer (language, format, length, tone) is an instruction for THIS reply: follow it "
            "without being asked again, even if their message is written in another language. If they want short or "
            "brief answers, that overrides your usual length: at most three sentences, only the essential, no "
            "closing offer.")
        ) + "\n" + "\n".join(f"- {f['key']}: {f['value']}" for f in standing)))

    # Credencial pegada en el chat: la identidad ya manda no usarla y pedir que la cambie, pero en un mensaje con varios
    # pedidos el agente solo decia "no puedo usarla". El codigo detecta el caso y lo recuerda al final.
    if not relay and _CREDENTIAL.search(_last_user_text(state)):
        llm_messages.append(SystemMessage(content=(
            "SECURITY (fact): the user's last message contains a password, key or token. In this reply, besides "
            "answering the rest: say you will not use it, ask them not to share credentials in the chat, and tell them "
            "to change that password or key now, because it was exposed. Never repeat the credential.")))

    # Accion de interfaz pedida por el usuario: el boton sale bajo la respuesta. Sin este hecho el modelo decia "no puedo
    # abrir pantallas" mientras la interfaz mostraba el boton.
    if (shown := state.get("requested_ui_actions")) and not relay:
        llm_messages.append(SystemMessage(content=(
            "INTERFACE (fact): right under your reply the interface is showing a button for what the user asked to open: "
            + "; ".join(f"«{a.get('label')}»" for a in shown)
            + ". Tell them in ONE short sentence that it is there to click. Do not say you cannot open it, and do not "
              "describe the screen's contents (you do not see them).")))

    if os.getenv("SHIFU_LOG_SYSTEM_PROMPT", "").lower() in ("1", "true"):
        logger.info(
            "[responder] system prompt:\n%s",
            "\n\n---\n\n".join(f"[{m.type}] {m.content}" for m in llm_messages),
        )

    llm = ChatOpenAI(
        model=model_name,
        temperature=_EFFORT_TEMPERATURE.get(effort_level, 0.7),
        max_tokens=max(_EFFORT_MAX_TOKENS.get(effort_level, 600), 900) if relay else _EFFORT_MAX_TOKENS.get(effort_level, 600),
        timeout=60,
        streaming=True,
        tags=["shifu-chat"],
        frequency_penalty=0.4,
        presence_penalty=0.2,
    )
    response = await llm.ainvoke(llm_messages)

    logger.info(
        "[responder] chat done → model=%s  effort=%s  level=%s  mood=%s  closing=%s  first=%s  reply_len=%d",
        model_name,
        effort_level,
        requirement_level or "none",
        mood_state,
        is_closing,
        is_first_turn,
        len(response.content or ""),
    )

    return {
        "messages":          discarded_drafts + [response],
        "active_mandates":   active_mandates,
        "mood_state":        mood_state,
        "requirement_level": requirement_level,
    }

