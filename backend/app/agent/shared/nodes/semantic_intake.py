"""
semantic_intake — agente_v3

Runs first. Three jobs, one LLM call (gpt-4o-mini):
  1. NORMALIZE  — fix typos, brand names, abbreviations.
  2. DECODE     — understand slang, idioms, implicit references.
  3. STRUCTURE  — produce structured_prompt_en (for agent) + ES (for debug).
                  Also extract apps_involved and needs_external_info for the
                  validation pipeline.

Multi-account resolution:
  If state.available_accounts is non-empty, the user may be replying to an
  account-selection prompt. The LLM is asked to detect the selection and write
  "account_selection": {"<app>": "<email>"}. When detected, selected_accounts
  is updated, validation state is reset, and apps_involved is preserved so the
  next validation pass can re-check with the chosen account.

State writes every turn:
  validation_reports   → None  (reset for this turn's fresh validation)
  missing_variables    → None  (same)
  structured_prompt    → English intent or None
  semantic_intake_debug
  apps_involved
  needs_external_info

Additional writes when resolving account selection:
  selected_accounts    → updated with user's choice
  available_accounts   → remaining unresolved apps (or None if all resolved)
  apps_involved        → preserved from previous turn (no re-extraction)

Console debug (SHIFUDEV_MODE=true): full analysis box with EN/ES outputs.
"""

import json
import logging
import re
from datetime import datetime, timezone

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.agent.shared.helpers import ui_actions

from app.agent.shared.helpers.catalog_cache import get_catalog_apps
from app.agent.shared.helpers.chrono_parser import parse_schedule
from app.agent.shared.context.geo_context import build_geo_block
from app.agent.shared.helpers.identity_loader import get_agent_personality, get_closing_signals
from app.agent.shared.helpers.pending_confirm import DEFAULT_TTL_MINUTES, active_pending, classify_pending
from app.agent.shared.helpers.stage_logger import log_stage_created
from app.agent.shared.prompts.semantic_intake import SEMANTIC_INTAKE_SYSTEM
from app.agent.shifu_base_v1.graph.state import REQ_CONFIRM, REQ_FLOW_RESET, ShifuState
from app.agent.shared.utils.log_utils import DEV_MODE, dev_print

logger = logging.getLogger(__name__)

_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, max_tokens=600, timeout=30).with_retry(
    stop_after_attempt=3, wait_exponential_jitter=True
)
# Tiny classifier used only while a req_investigator flow is active (see
# _classify_flow_action) — separate low-token-cap singleton, not the main analysis call.
_flow_gate_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, max_tokens=50, timeout=15).with_retry(
    stop_after_attempt=3, wait_exponential_jitter=True
)
_HISTORY_TURNS = 3

_CANCEL_PHRASES = [
    "cancela", "cancelar", "cancel", "olvídalo", "olvidalo", "ya no quiero",
    "mejor no", "detente", "para ya", "nevermind", "never mind", "forget it",
    "no quiero seguir", "déjalo así", "dejalo asi", "olvida eso",
]

_TRIVIAL_RE = re.compile(
    r"^\s*(hola|hello|hi|hey|ok|okay|sí|si|no|gracias|thanks|bye|chao|👍|😊|🙏)\s*[!?.]*\s*$",
    re.IGNORECASE,
)

_EMPTY_RESULT = {
    "structured_prompt":       None,
    "req_relay":               False, # reset — solo req_investigator lo enciende, y solo para ese turno
    "req_compose":             False, # idem
    "requested_ui_actions":    None,  # acciones de interfaz pedidas en ESTE turno (helpers/ui_actions.py)
    "semantic_intake_debug":   None,
    "apps_involved":           [],
    "needs_external_info":     False,
    "optimized_search_query":  None,  # reset
    "location_aware":          False, # reset — set True when query is location-sensitive
    "search_topic":            None,  # reset — news|general, indice de Tavily
    "search_recency":          None,  # reset — day|week|month|year|any, lo usa tavily_searcher como filtro de fecha
    "research_freshness":      None,  # reset — lo escribe tavily_searcher: que ventana de fechas se uso de verdad
    "needs_fact_verification": False, # reset — set True when query involves dynamic/time-sensitive data
    "catalog_query_mode":      None,  # reset — "list_available"|"list_connected"|"validate"|"add_account"|None
    # catalog_available_apps / catalog_apps_grouped / user_connected_apps are NOT reset here.
    # catalog_checker and auth_validator ALWAYS write these fields in every path (returning None
    # when not applicable), so they self-reset each turn via the parallel branch. Resetting from
    # semantic_intake would cause a multi-write conflict because LangGraph batches semantic_intake
    # writes with parallel-node writes in the same apply_writes super-step.
    "validation_reports":          None,  # reset
    "missing_variables":           [],    # reset
    "planning_trace":              None,  # reset: workflow_planner ya no corre (v0.8.0); sin esto quedaria el de un checkpoint viejo
    "is_closing":                  False, # reset
    "user_sentiment":              None,  # reset — responder reads this
    "mood_state":                  None,  # reset — responder computes final value
    "schedule_context":            None,  # reset — set when scheduling expression found
    "requirement_level":           None,  # reset — prevents stale mood computation at turn start
    "account_selection_resolved":  False, # reset — set True only when user resolved a pending selection
    "eval_retry_count":            0,     # reset — evaluator self-correction counter must start at 0 each turn
    "eval_feedback":               None,  # reset — stale feedback from a prior turn must not bleed into the next
    "eval_report":                 None,  # reset — veredicto del evaluador es por turno
    "eval_drafts":                 None,  # reset — borradores del turno (para entregar el mejor si se agotan los intentos)
    "active_mandates":             None,  # reset — las instrucciones obligatorias se recalculan cada turno
    "action_results":              None,  # reset — lo que action_runner ejecuto es del turno
    "action_stop":                 None,  # reset
    # pending_action NO se reinicia aqui: la escritura que espera confirmacion vive entre turnos (modo act, fase 2).
    # pending_decision es por turno: semantic_intake_node la fija siempre al terminar (ver abajo).
    "needs_document_context":      False, # reset — set True when the message references an earlier upload
    "document_intent":             None,  # reset — "qa"|"compare"|"extract_structured"|None
    "document_extraction_hint":    None,  # reset — "invoice"|"contract"|"generic"|None
    # Research fields are written by tavily_subgraph in a LATER super-step (after the parallel fan-out),
    # so resetting them here (semantic_intake's own super-step) is safe — no concurrent write conflict.
    "retrieved_research":          None,  # reset — prevents stale research bleeding into pure-chat turns
    "retrieved_sources":           None,  # reset
    "curated_research":            None,  # reset
}

_VALID_SENTIMENTS = {"calm", "polite", "neutral", "confused", "frustrated", "urgent"}
_VALID_MOODS      = {"DEFAULT", "HELPFUL", "DIRECT_EMPATHY"}


async def _resolve_apps_by_intent(
    unresolved: list[str],
    catalog: list[str],
    user_message: str,
) -> dict[str, str]:
    """
    Capa-2: micro-call LLM para resolver referencias ambiguas o por intención.
    Solo se invoca cuando Capa-1 no pudo mapear algún app al catalog.
    Usa el conocimiento general del LLM — sin dicts estáticos, escala automáticamente.
    """
    system = (
        "You are an app name resolver. Given a user message and a list of canonical app keys, "
        "determine which canonical key each ambiguous reference maps to.\n"
        "Use your general knowledge of what each app does to resolve descriptions, "
        "nicknames, partial names, abbreviations, and intent-based references "
        "(e.g. 'celdas y filas de cálculo' → 'google_sheets', 'presentaciones' → 'google_slides').\n"
        "Respond ONLY with a valid JSON object: {\"ambiguous_ref\": \"canonical_key\"}.\n"
        "If a reference cannot be confidently resolved to any catalog app, map it to null.\n"
        f"Available catalog keys: {', '.join(catalog)}"
    )
    human = (
        f"User message: {user_message}\n"
        f"Unresolved references to map: {', '.join(unresolved)}\n"
        "Return only the JSON mapping."
    )
    _resolver_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, max_tokens=200, timeout=15).with_retry(
        stop_after_attempt=3, wait_exponential_jitter=True
    )
    try:
        resp    = await _resolver_llm.ainvoke([SystemMessage(content=system), HumanMessage(content=human)])
        raw     = (resp.content or "").strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\n?", "", raw).rstrip("```").strip()
        mapping = json.loads(raw)
        catalog_set = set(catalog)
        resolved = {k: v for k, v in mapping.items() if isinstance(v, str) and v in catalog_set}
        if resolved:
            logger.info("[semantic_intake] Capa-2 resolved: %s", resolved)
        return resolved
    except Exception as exc:
        logger.warning("[semantic_intake] Capa-2 resolver failed: %s", exc)
        return {}


def _last_human(messages: list) -> HumanMessage | None:
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return msg
    return None


def _last_ai(messages: list) -> AIMessage | None:
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            return msg
    return None


async def _classify_flow_action(state: ShifuState) -> str:
    """Decide whether the user's message continues the active req_investigator flow,
    cancels it, or digresses to something unrelated — evaluated fresh every turn so
    the flow is a state the agent can pause/drop, never a trap it can't route around.
    Deterministic cancel-phrase check first (free); LLM classification only as fallback.
    """
    messages = list(state.get("messages") or [])
    last_human = _last_human(messages)
    if not last_human:
        return "continue"
    text = last_human.content if isinstance(last_human.content, str) else str(last_human.content)
    text = text.strip()
    text_lower = text.lower()

    if any(p in text_lower for p in _CANCEL_PHRASES):
        return "cancel"

    last_ai = _last_ai(messages)
    pending_q = last_ai.content if last_ai and isinstance(last_ai.content, str) else ""
    # La pregunta real del flujo (el responder a veces la parafrasea mal o la sustituye): sin ella el clasificador
    # juzgaba "no, asi esta bien" contra una respuesta ajena y lo tomaba por cancelacion.
    flow_q = state.get("structured_prompt") or ""
    if flow_q and flow_q not in pending_q:
        pending_q = f"{flow_q[:300]}\n(assistant's reply to the user: {pending_q[:300]})"

    system = (
        "You are classifying a user's reply during a guided workflow-automation setup "
        "conversation. The assistant just asked ONE specific question. Classify the "
        "user's new message as:\n"
        "- \"continue\": it answers (fully or partially) the question that was asked.\n"
        "- \"cancel\": the user clearly wants to stop/abandon setting up this automation. Declining an optional "
        "suggestion, a plain yes/no answer, or saying it is fine as is (\"no, asi esta bien\") is NOT cancel: it is \"continue\". "
        "Use cancel only when they ask to stop or drop the whole automation.\n"
        "- \"digress\": it's about something else entirely — not an answer, not a "
        "cancellation, e.g. an unrelated question.\n"
        "Respond ONLY with JSON: {\"action\": \"continue\"|\"cancel\"|\"digress\"}."
    )
    human = f"Question just asked: {pending_q[:500]}\n\nUser's new message: {text[:500]}"
    try:
        resp = await _flow_gate_llm.ainvoke([SystemMessage(content=system), HumanMessage(content=human)])
        action = _parse(resp.content or "").get("action")
        if action in ("continue", "cancel", "digress"):
            return action
    except Exception as exc:
        logger.warning("[semantic_intake] flow-gate classification failed: %s — defaulting to continue", exc)
    return "continue"


def _build_history(messages: list, current: HumanMessage) -> str:
    lines: list[str] = []
    for msg in messages:
        if msg is current:
            break
        if isinstance(msg, HumanMessage):
            text = msg.content if isinstance(msg.content, str) else str(msg.content)
            lines.append(f"User: {text[:200]}")
        elif isinstance(msg, AIMessage):
            text = msg.content if isinstance(msg.content, str) else str(msg.content)
            lines.append(f"Shifu: {text[:200]}")
    return "\n".join(lines[-(_HISTORY_TURNS * 2):])


def _parse(raw: str) -> dict:
    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {}


def _format_account_options(available_accounts: dict) -> str:
    lines = []
    for app, accts in available_accounts.items():
        emails = [a.get("email") or a.get("account_id", "?") for a in accts]
        lines.append(f"  {app}: {emails}")
    return "\n".join(lines)


def _build_user_prompt(
    original: str,
    history: str,
    account_hint: str = "",
    current_time_utc: str = "",
    geo_block: str = "",
) -> str:
    base = (
        f"RECENT CONVERSATION:\n{history}\n\nCURRENT MESSAGE:\n{original}"
        if history
        else f"CURRENT MESSAGE:\n{original}"
    )
    time_hint = (
        f"\n\nSYSTEM DATE: {current_time_utc}"
        " — Use this date as reference when generating optimized_search_query."
        if current_time_utc else ""
    )
    geo_section = f"\n\n{geo_block}" if geo_block else ""
    return base + account_hint + time_hint + geo_section


def _print_dev_box(original: str, analysis: dict, schedule_ctx: dict | None = None) -> None:
    normalized        = analysis.get("normalized", "")
    intent            = analysis.get("detected_intent", "?")
    patterns          = analysis.get("language_patterns", [])
    prompt_en         = analysis.get("structured_prompt_en", "")
    prompt_es         = analysis.get("structured_prompt_es", "")
    apps              = analysis.get("apps_involved", [])
    research          = analysis.get("needs_external_info", False)
    loc_aware         = analysis.get("location_aware", False)
    selection         = analysis.get("account_selection")
    sentiment         = analysis.get("detected_sentiment", "—")
    rec_mood          = analysis.get("recommended_mood", "—")
    sched_expr        = analysis.get("scheduling_expression")
    catalog_mode      = analysis.get("catalog_query_mode") or "null"
    fact_verify       = analysis.get("needs_fact_verification", False)

    patterns_fmt = "\n│            ".join(f"• {p}" for p in patterns) if patterns else "(none)"
    box = (
        "\n┌─ Semantic Intake ─────────────────────────────────────────────\n"
        f"│ intent    : {intent}\n"
        f"│ apps      : {apps}  research={research}  location_aware={loc_aware}\n"
        f"│ catalog   : catalog_query_mode={catalog_mode}  fact_verify={fact_verify}\n"
        f"│ original  : {original}\n"
        f"│ normal    : {normalized if normalized != original else '(sin cambios)'}\n"
        f"│ patterns  : {patterns_fmt}\n"
        + (f"│ → SELECTION: {selection}\n" if selection else "")
        + f"│ → EN      : {prompt_en}\n"
        f"│ → ES      : {prompt_es}\n"
        f"├─ Mood Detection ──────────────────────────────────────────────\n"
        f"│ sentiment : {sentiment}\n"
        f"│ rec_mood  : {rec_mood}\n"
        + (
            f"├─ Chrono Parser ───────────────────────────────────────────────\n"
            f"│ expr      : {sched_expr}\n"
            f"│ cron      : {schedule_ctx.get('cron') if schedule_ctx else '(unresolved)'}\n"
            f"│ human     : {schedule_ctx.get('human') if schedule_ctx else '—'}\n"
            f"│ next_run  : {schedule_ctx.get('next_run') if schedule_ctx else '—'}\n"
            if sched_expr else ""
        )
        + "└───────────────────────────────────────────────────────────────"
    )
    dev_print(box)


async def _intake(state: ShifuState) -> dict:
    # Mid-requirements flow: decide fresh, every turn, whether this message continues
    # the flow, cancels it, or digresses to something unrelated — never a blind
    # dispatch (see _classify_flow_action). "continue" skips full analysis exactly
    # like before; "cancel"/"digress" fall through to the normal analysis below so
    # the user gets a real, context-aware reply instead of a canned flow message.
    in_flow = state.get("req_level") is not None
    # Aviso de la interfaz ("la cuenta de X quedo conectada"): no es una respuesta a la pregunta pendiente. Antes se
    # clasificaba como "continue", el flujo avanzaba solo y el agente dejaba dos preguntas abiertas seguidas.
    if state.get("system_event"):
        return {**_EMPTY_RESULT, **({"req_flow_action": "system_event"} if in_flow else {})}
    flow_action: str | None = None
    if in_flow:
        flow_action = await _classify_flow_action(state)
        if flow_action == "cancel" and state.get("req_level") == REQ_CONFIRM:
            # En CONFIRM ya hay un borrador guardado: cancelar exige descartarlo y decirle al usuario que no se activo
            # nada. Eso lo hace req_investigator (con su propio clasificador), no el camino normal de cancelacion.
            flow_action = "continue"
        if flow_action == "continue":
            return {**_EMPTY_RESULT, "req_flow_action": "continue"}

    def _flow_extra() -> dict:
        """Merged into every early-return below when in_flow — makes sure "cancel"
        actually clears the flow instead of silently leaving req_level dangling
        because a short-circuit branch (closing/trivial/LLM-failure) fired first."""
        if not in_flow:
            return {}
        extra: dict = {"req_flow_action": flow_action}
        if flow_action == "cancel":
            extra["req_level"] = None
            extra["req_pending_questions"] = None
            extra["req_schedule_asked"] = None  # que un flujo cancelado no deje "ya pregunte el horario" al siguiente
        return extra

    messages = list(state.get("messages") or [])
    last_human = _last_human(messages)

    if not last_human:
        return {**_EMPTY_RESULT, **_flow_extra()}

    original = last_human.content if isinstance(last_human.content, str) else str(last_human.content)
    original = original.strip()

    if not original:
        return {**_EMPTY_RESULT, **_flow_extra()}

    # ── Closing signal detection (deterministic Python — no LLM needed) ─────────
    # Checked BEFORE the trivial RE so "bye", "chao", etc. can be in the signals
    # list without being incorrectly handled as social small-talk.
    personality       = await get_agent_personality()
    closing_signals   = get_closing_signals(personality)
    original_lower    = original.lower()
    if closing_signals and any(sig in original_lower for sig in closing_signals):
        if DEV_MODE:
            dev_print(f"\n[Semantic Intake] closing signal detected → {original!r}")
        logger.info("[semantic_intake] closing detected: %r", original[:80])
        return {**_EMPTY_RESULT, "is_closing": True, **_flow_extra()}

    if _TRIVIAL_RE.match(original):
        if DEV_MODE:
            dev_print(f"\n[Semantic Intake] short-circuit (social) → {original!r}")
        logger.info("[semantic_intake] short-circuit (social): %r", original)
        # "hola" a secas es el saludo mas comun: sin la intencion, el responder no aplicaba greeting_behavior.
        greet = {"semantic_intake_debug": {"detected_intent": "chat", "short_circuit": "social"}} \
            if re.match(r"^\s*(hola|hello|hi|hey)\b", original_lower) else {}
        return {**_EMPTY_RESULT, **greet, **_flow_extra()}

    # Build context for pending account selections
    available_accounts = state.get("available_accounts") or {}
    account_hint = ""
    if available_accounts:
        options_text = _format_account_options(available_accounts)
        account_hint = (
            f"\n\nPENDING ACCOUNT SELECTION:\n"
            f"The user needs to choose an account for these apps:\n{options_text}\n"
            f"If the current message SELECTS one of these existing accounts (full email, prefix, "
            f"alias like 'la de trabajo', 'la personal', 'la primera', 'la segunda', etc.), "
            f"include in your JSON: \"account_selection\": {{\"<app>\": \"<exact_email_from_the_list>\"}}\n"
            f"Match even partial mentions — pick the closest email from the list above.\n"
            f"CRITICAL DISAMBIGUATION: If the message says 'conectar otra cuenta', "
            f"'agregar otra cuenta', 'add another account', 'necesito otra cuenta', "
            f"or any phrase expressing desire to ADD A NEW account — "
            f"this is NOT a selection from the list above. "
            f"In that case: omit 'account_selection' entirely and set catalog_query_mode = 'add_account'.\n"
            f"If the message is about something else entirely, omit 'account_selection'."
        )

    current_time_utc = (state.get("current_time_utc") or "").strip()
    history   = _build_history(messages, last_human)
    geo_block = build_geo_block(
        state.get("user_timezone"),
        state.get("user_location"),
        state.get("user_country_code"),
    )
    user_prompt = _build_user_prompt(original, history, account_hint, current_time_utc, geo_block)
    # Adjuntos: el modelo no ve los archivos, asi que sin este hecho "en que mes gaste mas segun la hoja?" con un
    # .xlsx adjunto pedia conectar Google Sheets, y una pregunta sobre un .txt se iba a buscar a la web.
    attached = [r.get("title") or "file" for r in state.get("turn_resources") or []]
    earlier = [d.get("title") or "file" for d in (state.get("session_documents") or {}).values()]
    if attached:
        user_prompt += (
            f"\n\nFACT (from the system): the user attached these files to THIS message: {', '.join(attached)}. "
            "They are already read and the answer will be written from their content. The message is about those "
            "files unless it clearly asks for something else: needs_external_info is false, and no app goes in "
            "apps_involved just to read them (an attached .xlsx or .csv is a file, NOT Google Sheets). Set document_intent."
        )
    elif earlier:
        user_prompt += (
            f"\n\nFACT (from the system): files the user uploaded earlier in this conversation: {', '.join(earlier)}. "
            "If the message refers to them or follows up on what they say, needs_document_context is true and "
            "no app or web search is needed to read them."
        )

    catalog_apps = await get_catalog_apps()
    dynamic_block = (
        f"## Platform Apps (live catalog — use as keys in apps_involved)\n"
        f"{', '.join(catalog_apps)}\n\n"
        if catalog_apps else "## Platform Apps\n(none currently active)\n\n"
    )
    # Acciones de interfaz que el usuario puede pedir ("abreme mis workflows"): el catalogo es dato en Mongo.
    # Solo las que este turno puede ofrecer (ui_offer: lo que el cliente soporta y el plan permite; lo calcula chat.py).
    ui_catalog = ui_actions.offered(await ui_actions.get_catalog(), state.get("ui_offer"))
    system_content = dynamic_block + ui_actions.prompt_block(ui_catalog) + SEMANTIC_INTAKE_SYSTEM

    try:
        resp = await _llm.ainvoke([
            SystemMessage(content=system_content),
            HumanMessage(content=user_prompt),
        ])
        analysis = _parse(resp.content or "")
    except Exception as exc:
        logger.warning("[semantic_intake] LLM failed: %s — using original", exc)
        return {**_EMPTY_RESULT, **_flow_extra()}

    if not analysis:
        logger.warning("[semantic_intake] empty parse — using original")
        return {**_EMPTY_RESULT, **_flow_extra()}

    # ── Account selection resolution ──────────────────────────────────────────
    account_selection = analysis.get("account_selection") or {}
    if account_selection and available_accounts:
        existing_selected = dict(state.get("selected_accounts") or {})
        for app, chosen in account_selection.items():
            if app in available_accounts:
                existing_selected[app] = chosen
                logger.info("[semantic_intake] account resolved: %s → %s", app, chosen)

        # Keep only apps that still have no selection
        remaining = {
            app: accts
            for app, accts in available_accounts.items()
            if app not in account_selection
        }
        logger.info("[semantic_intake] selections resolved=%s  still_pending=%s",
                    list(account_selection.keys()), list(remaining.keys()))

        return {
            "selected_accounts":           existing_selected,
            "available_accounts":          remaining or None,
            "apps_involved":               state.get("apps_involved") or [],
            "validation_reports":          None,
            "missing_variables":           [],
            "structured_prompt":           None,
            "semantic_intake_debug":       {"mode": "account_selection", "selections": account_selection},
            "needs_external_info":         False,
            "is_closing":                  False,
            "catalog_query_mode":          None,
            "optimized_search_query":      None,
            "location_aware":              False,
            "search_recency":              None,
            "search_topic":                None,
            "needs_fact_verification":     False,
            # Signal to _route_from_intake to skip the fan-out (auth_validator would
            # see OLD state and create a concurrent write conflict on selected_accounts)
            "account_selection_resolved":  True,
            **_flow_extra(),
        }

    # ── Normal flow ───────────────────────────────────────────────────────────
    prompt_en    = (analysis.get("structured_prompt_en") or "").strip()
    intent       = analysis.get("detected_intent", "?")
    apps         = [a.lower().strip() for a in (analysis.get("apps_involved") or []) if a]
    research     = bool(analysis.get("needs_external_info", False))
    final_prompt = prompt_en if prompt_en and prompt_en != original else None

    # ── Capa 1: canonical app key normalization (determinista) ───────────────
    # catalog_apps is already in memory (fetched above for the LLM prompt).
    # Two passes:
    #   1. Collapse spaces → underscores ("google slides" → "google_slides")
    #   2. Suffix alias map: short names ("slides") → full canonical key ("google_slides")
    catalog_set: set[str] = set()
    if catalog_apps and apps:
        apps        = [a.replace(" ", "_") for a in apps]
        catalog_set = set(catalog_apps)
        alias_map   = {
            key.split("_")[-1]: key
            for key in catalog_set if "_" in key
        }
        apps = [alias_map.get(a, a) if a not in catalog_set else a for a in apps]

    # ── Capa 2: LLM intent resolver (solo si quedan apps sin resolver) ────────
    # Fires only when Capa-1 leaves unresolved references (not in catalog).
    # Uses LLM general knowledge — no static dict, scales with catalog automatically.
    if catalog_apps and apps:
        unresolved = [a for a in apps if a not in catalog_set]
        if unresolved:
            resolved_map = await _resolve_apps_by_intent(unresolved, catalog_apps, original)
            if resolved_map:
                apps = [resolved_map.get(a, a) for a in apps]

    raw_sentiment = (analysis.get("detected_sentiment") or "neutral").lower().strip()
    raw_mood      = (analysis.get("recommended_mood")   or "DEFAULT").upper().strip()
    sentiment     = raw_sentiment if raw_sentiment in _VALID_SENTIMENTS else "neutral"
    rec_mood      = raw_mood      if raw_mood      in _VALID_MOODS      else "DEFAULT"

    # ── Chrono parsing (Capa 2) ───────────────────────────────────────────────
    sched_expr  = (analysis.get("scheduling_expression") or "").strip() or None
    sched_ctx   = None
    if sched_expr:
        sched_ctx = parse_schedule(sched_expr, datetime.now(timezone.utc))
        if sched_ctx:
            logger.info("[semantic_intake] schedule resolved: expr=%r  cron=%s",
                        sched_expr, sched_ctx.get("cron"))
        else:
            logger.info("[semantic_intake] schedule expression found but not resolved: %r", sched_expr)

    optimized_query         = (analysis.get("optimized_search_query") or "").strip() or None
    location_aware          = bool(analysis.get("location_aware", False))
    search_recency          = str(analysis.get("search_recency") or "").strip().lower() or None
    search_topic            = str(analysis.get("search_topic") or "").strip().lower() or None
    needs_fact_verification = bool(analysis.get("needs_fact_verification", False))
    needs_document_context  = bool(analysis.get("needs_document_context", False))
    _valid_doc_intents      = {"qa", "compare", "extract_structured"}
    document_intent         = (analysis.get("document_intent") or "").strip() or None
    if document_intent not in _valid_doc_intents:
        document_intent = None
    _valid_doc_hints        = {"invoice", "contract", "generic"}
    document_extraction_hint = (analysis.get("document_extraction_hint") or "").strip() or None
    if document_extraction_hint not in _valid_doc_hints:
        document_extraction_hint = None
    _valid_modes            = {"list_available", "list_connected", "validate", "add_account"}
    catalog_query_mode      = (analysis.get("catalog_query_mode") or "").strip() or None
    if catalog_query_mode not in _valid_modes:
        catalog_query_mode = None

    # LLMs occasionally place a catalog-mode value (e.g. "add_account") in detected_intent
    # instead of catalog_query_mode, leaving catalog_query_mode null. If intent contains a
    # valid catalog mode and apps are present, infer the mapping here — deterministic and safe.
    if catalog_query_mode is None and intent in _valid_modes and apps:
        catalog_query_mode = intent
        logger.info("[semantic_intake] inferred catalog_query_mode=%s from detected_intent", catalog_query_mode)

    # Architectural override: catalog intent is NEVER answered by external research.
    # catalog_checker and auth_validator query internal DB; Tavily must not run.
    if catalog_query_mode is not None:
        research = False
        logger.info("[semantic_intake] catalog_mode=%s → override research=False", catalog_query_mode)

    logger.info(
        "[semantic_intake] intent=%s apps=%s research=%s catalog=%s structured=%s "
        "sentiment=%s rec_mood=%s schedule=%s",
        intent, apps, research, catalog_query_mode, bool(final_prompt), sentiment, rec_mood,
        sched_ctx.get("cron") if sched_ctx else "—",
    )

    if DEV_MODE:
        _print_dev_box(original, analysis, sched_ctx)
        if apps:
            log_stage_created(
                session_id=state.get("conversation_id") or "—",
                intent=intent,
                apps=apps,
            )

    result = {
        "structured_prompt":       final_prompt,
        "req_relay":               False,
        "req_compose":             False,
        "requested_ui_actions":    ui_actions.resolve(analysis.get("ui_actions"), ui_catalog,
                                                      analysis.get("user_language") or state.get("user_language")) or None,
        # No va en _EMPTY_RESULT a proposito: un "yes" no dice el idioma y debe conservarse el del turno anterior.
        **({"user_language": str(analysis["user_language"]).strip()[:30]} if analysis.get("user_language") else {}),
        "semantic_intake_debug":   analysis,
        "apps_involved":           apps,
        "needs_external_info":     research,
        "optimized_search_query":  optimized_query,
        "location_aware":          location_aware,
        "search_recency":          search_recency,
        "search_topic":            search_topic,
        "needs_fact_verification": needs_fact_verification,
        "catalog_query_mode":      catalog_query_mode,
        "validation_reports":      None,  # reset validation state for this turn
        "missing_variables":       None,
        "is_closing":              False,
        "user_sentiment":          sentiment,
        "mood_state":              rec_mood,   # responder may override based on context
        "schedule_context":        sched_ctx,
        "needs_document_context":   needs_document_context,
        "document_intent":          document_intent,
        "document_extraction_hint": document_extraction_hint,
        # El estado del evaluador es por turno. Este camino (el normal) no lo reiniciaba: tras un turno con
        # reintentos gastados, los turnos siguientes del hilo se quedaban sin reintentos.
        "eval_retry_count":         0,
        "eval_feedback":            None,
        "eval_report":              None,
        "eval_drafts":              None,
        "active_mandates":          None,
        "action_results":           None,
        "action_stop":              None,
    }

    if in_flow:
        # cancel/digress reaching here (no earlier short-circuit fired). "cancel"
        # clears the flow; "digress" leaves req_level/req_pending_questions
        # untouched entirely so req_investigator resumes where it paused —
        # and neither lets a stray create_workflow detection stomp it.
        result.update(_flow_extra())
    elif intent == "create_workflow":
        # Trigger requirements investigator when LLM detects workflow creation intent.
        result["req_level"] = 1
        result.update(REQ_FLOW_RESET)
        logger.info("[semantic_intake] create_workflow intent detected → req_level=1")

    return result



async def semantic_intake_node(state: ShifuState) -> dict:
    """Modo act, fase 2: si hay una escritura esperando el "si" del usuario, primero se decide que hizo con ella.
    Va antes del analisis normal porque "si" o "dale" caerian en los atajos (trivial/cierre) y se perderian."""
    pending = state.get("pending_action")
    last_human = _last_human(list(state.get("messages") or []))
    decision = None
    if pending and last_human and not state.get("system_event"):
        ttl = ((await get_agent_personality()).get("action_policy") or {}).get("confirm_ttl_minutes", DEFAULT_TTL_MINUTES)
        if active_pending(pending, ttl):  # vencida: se ignora (no se confirma algo de hace horas)
            msgs = list(state.get("messages") or [])
            last_ai = next((m for m in reversed(msgs) if getattr(m, "type", "") == "ai"), None)
            decision = await classify_pending(pending, str(last_human.content), str(getattr(last_ai, "content", "") or ""))
            logger.info("[semantic_intake] pending_action decision=%s", decision)
    if decision in ("confirm", "change"):
        # Directo a action_runner (ver _route_from_intake): sin ramas en paralelo ni analisis del mensaje.
        return {**_EMPTY_RESULT, "pending_decision": decision,
                "semantic_intake_debug": {"detected_intent": "act", "mode": f"pending_{decision}"}}
    if decision == "cancel":
        # Es seguro borrarla aqui: este turno va semantic_intake -> responder, nadie mas la escribe.
        return {**_EMPTY_RESULT, "pending_decision": "cancel", "pending_action": None}
    # digress / unclear / sin pendiente: turno normal; unclear y digress dejan pending_action intacta.
    return {**(await _intake(state)), "pending_decision": decision}
