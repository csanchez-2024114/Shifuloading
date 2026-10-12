import operator
from typing import Annotated, Any, Dict, List, Literal, Optional, TypedDict
from langgraph.graph import MessagesState

# Etapas del flujo "crear workflow por chat" (req_level). Se conservan 1 y 4 de los 6 niveles viejos para que el router y
# el filtro de semantic_intake sigan funcionando con solo mirar "req_level is not None".
REQ_GATHER = 1
REQ_CONFIRM = 4

# Un flujo nuevo no debe heredar el plan, el borrador ni los contadores del anterior (viven en el checkpoint del hilo).
REQ_FLOW_RESET = {
    "req_plan": None, "req_plan_rounds": None, "req_level_entered": None, "req_pending_questions": None,
    "req_apps_scope": None, "req_preflight_passed": None, "req_preflight_failures": None,
    "req_dry_run_result": None, "req_workflow_id": None, "req_deployed_steps": None, "req_deployed": False,
    "req_schedule": None, "req_schedule_asked": None, "req_adjustment": None, "req_confirm_unclear": None,
    "req_webhook_url": None, "req_trigger_summary": None, "req_goal": None,
    "req_trigger_type": None, "req_trigger_event": None,
}


class ShifuInputState(TypedDict, total=False):
    """Fields the WebSocket handler sends per turn. Subset of ShifuV1State."""
    messages: list
    user_id: Optional[str]
    conversation_id: Optional[str]
    model_name: Optional[str]
    effort_level: Optional[str]
    current_time_utc: Optional[str]
    selected_accounts: Optional[Dict[str, str]]
    available_accounts: Optional[Dict[str, List[Dict[str, str]]]]
    user_preferences_context: Optional[str]
    user_timezone: Optional[str]
    user_location: Optional[str]
    user_country_code: Optional[str]
    # user_name: real first name from the Users collection — grounds the LLM so it
    # never confuses the user's identity with its own (e.g. "Hyper Shifu").
    user_name: Optional[str]
    # ui_offer: ids de acciones de interfaz que ESTE turno puede ofrecer (el cliente las soporta y el plan las permite;
    #   lo calcula chat._build_input con helpers/ui_actions.offer). Se manda en todos los turnos, [] si no hay.
    ui_offer: Optional[List[str]]
    # system_event: el mensaje lo genero la interfaz (p. ej. "la cuenta de X quedo conectada"), no lo escribio el usuario.
    #   Se manda en TODOS los turnos (True/False): un campo de entrada que se omite se hereda del checkpoint.
    system_event: bool
    # turn_resources: attachments sent by the user this turn (Cloudinary-backed).
    # Same shape as ResourceModel: {type, url, title, provider, file_id, metadata}.
    turn_resources: Optional[List[Dict[str, Any]]]


class ShifuOutputState(TypedDict, total=False):
    """Fields returned by ainvoke() to the WS caller."""
    messages: list
    validation_reports: list
    retrieved_sources: Optional[List[dict]]
    requirement_level: Optional[str]
    mood_state: Optional[str]
    agent_error: Optional[Dict[str, Any]]
    structured_extraction: Optional[Dict[str, Any]]
    requested_ui_actions: Optional[List[dict]]
    # Lo que chat._build_ui_actions necesita del flujo de workflows. Sin estos campos aqui ainvoke() no los devolvia y el
    # frontend nunca recibia render_workflow / open_trigger ni el workflow_id (visto el 2026-10-11).
    req_relay: bool
    req_deployed: bool
    req_workflow_id: Optional[str]
    req_deployed_steps: Optional[List[Dict[str, Any]]]
    req_webhook_url: Optional[str]
    req_trigger_summary: Optional[str]
    req_trigger_type: Optional[str]


def _reset_or_add(existing: list, update) -> list:
    """Reducer for validation lists.

    Supports per-turn reset without breaking parallel fan-in:
      None  → reset to []  (written by semantic_intake at the start of each turn)
      list  → append       (written by parallel validation nodes within the turn)
    """
    if update is None:
        return []
    return (existing or []) + (update or [])


def _merge_dicts(a: dict | None, b: dict | None) -> dict | None:
    """Reducer for dicts that may be written by multiple parallel nodes.

    None is treated as "no update" (not "clear the field"):
      None, None  → None
      None, {...} → {...}  (keeps the other side)
      {...}, None → {...}
      {...}, {...} → merged (b takes priority on key collision)
    """
    if a is None:
        return b
    if b is None:
        return a
    return {**a, **b}



class ShifuState(MessagesState):
    # Identity — populated by the WebSocket handler
    user_id: Optional[str]
    conversation_id: Optional[str]
    user_email: Optional[str]
    # user_name: real first name from the Users collection — see ShifuInputState.
    user_name: Optional[str]
    # ui_offer: ids de acciones de interfaz que ESTE turno puede ofrecer (el cliente las soporta y el plan las permite;
    #   lo calcula chat._build_input con helpers/ui_actions.offer). Se manda en todos los turnos, [] si no hay.
    ui_offer: Optional[List[str]]
    # system_event: el mensaje lo genero la interfaz (p. ej. "la cuenta de X quedo conectada"), no lo escribio el usuario.
    #   Se manda en TODOS los turnos (True/False): un campo de entrada que se omite se hereda del checkpoint.
    system_event: bool

    # ── Turn timestamp (set by WS handler — shared by ALL nodes) ─────────────
    # ISO 8601 UTC string, e.g. "2026-06-11T13:20:00Z".
    # Set once per turn before graph.ainvoke() so every node reads the same "now".
    # Injected into semantic_intake user prompt to prevent training-cutoff date drift.
    current_time_utc: Optional[str]

    # ── Semantic Intake outputs ────────────────────────────────────────────────
    structured_prompt: Optional[str]           # English, used by agent nodes
    semantic_intake_debug: Optional[Dict[str, Any]]
    apps_involved: List[str]                   # e.g. ["gmail", "drive"]
    needs_external_info: bool                  # trigger tavily research
    # Clean SEO query generated by semantic_intake LLM when needs_external_info=True.
    # Strips conversational phrasing so tavily_searcher never sees automation prefixes.
    optimized_search_query: Optional[str]

    # ── Multi-account support ─────────────────────────────────────────────────
    # Apps with 2+ active accounts awaiting user selection.
    # {"gmail": [{"account_id": "...", "email": "a@..."}, ...]}
    available_accounts: Annotated[Optional[Dict[str, List[Dict[str, str]]]], _merge_dicts]
    # Chosen account per app — persists across turns until the user changes it.
    # {"gmail": "a@gmail.com"}
    selected_accounts: Annotated[Optional[Dict[str, str]], _merge_dicts]

    # ── Validation layer (parallel nodes write here via reducer) ───────────────
    # Each report: {"source": "catalog"|"auth"|"bigtools", "app": str,
    #               "status": "ok"|"error"|"pending_selection", ...}
    # semantic_intake writes None at the start of each turn to reset.
    validation_reports: Annotated[List[dict], _reset_or_add]
    retrieved_research: Optional[str]          # from tavily_searcher — full text for LLM
    retrieved_sources: Optional[List[dict]]   # from tavily_searcher — [{title, url, domain}] for UI
    curated_research: Optional[str]           # from research_curator — compressed facts for responder
    missing_variables: List[str]

    # ── Conversational flags (set by semantic_intake) ─────────────────────────
    # True when user's message matches a closing_behavior.signal phrase.
    # semantic_intake resets this to False on every turn unless detected.
    is_closing: bool

    # ── Mood / sentiment (set by semantic_intake → finalized by responder) ────
    # user_sentiment: raw emotion detected in the user's message this turn.
    #   Values: "calm" | "polite" | "neutral" | "confused" | "frustrated" | "urgent"
    # mood_state: Shifu's response tone for this turn — computed by responder
    #   from user_sentiment + validation context.
    #   Values: "DEFAULT" | "HELPFUL" | "DIRECT_EMPATHY" | "CLOSING"
    user_sentiment: Optional[str]
    mood_state: Optional[str]

    # ── Temporal Awareness (Capa 1 + 2 + 3) ──────────────────────────────────
    # user_timezone: IANA string — from user_preferences (DB) or GeoIP fallback.
    #   Used by time_context.py to build the local-time block.
    user_timezone: Optional[str]
    # user_location: human-readable city/country string from GeoIP, e.g.
    #   "Guatemala City, Guatemala". Informs location-sensitive queries.
    user_location: Optional[str]
    # user_country_code: ISO 3166-1 alpha-2 from GeoIP, e.g. "GT", "MX", "US".
    #   Used to infer language hint for LLM nodes via geo_context.get_language_hint().
    user_country_code: Optional[str]
    # location_aware: set by semantic_intake each turn.
    #   True when the user's query requires location-specific results (local events,
    #   schedules in local timezone, weather, nearby places, etc.).
    #   tavily_searcher uses this to conditionally append user_location to the query.
    location_aware: bool
    # search_recency: day|week|month|year|any, de semantic_intake; filtro de fecha de tavily_searcher.
    search_recency: Optional[str]
    # search_topic: news|general, de semantic_intake; indice de Tavily (solo "news" devuelve fecha de publicacion).
    search_topic: Optional[str]
    # research_freshness: frase de tavily_searcher con la ventana de fechas que se uso de verdad (si hubo que ampliarla, lo dice).
    research_freshness: Optional[str]
    # needs_fact_verification: set by semantic_intake each turn.
    #   True when the query involves dynamic/time-sensitive data where facts could be stale
    #   or contradictory: news, live data, prices, current events, political outcomes, etc.
    #   research_curator uses this to conditionally run _verify_facts() via Tavily.
    needs_fact_verification: bool
    # catalog_query_mode: intent for catalog/auth meta-queries — set by semantic_intake.
    #   "list_available" → user asks what apps are available on the platform.
    #   "list_connected" → user asks which apps they personally have connected.
    #   "validate"       → normal validation of specific apps_involved.
    #   None             → no catalog intent (pass-through).
    catalog_query_mode: Optional[str]
    # Results of listing queries — populated by catalog_checker / auth_validator.
    # Plain Optional (no Annotated): each field is written by exactly ONE parallel node
    # (catalog_checker for catalog fields, auth_validator for user_connected_apps).
    # Using Annotated+_reset_or_replace here caused the reducer to be called with None
    # for nodes that did not return the key, silently erasing the data on fan-in.
    catalog_available_apps: Optional[List[str]]
    # Grouped version of catalog_available_apps — {"productivity": ["Gmail", ...], ...}
    # Populated only in list_available mode by catalog_checker.
    catalog_apps_grouped: Optional[Dict[str, List[str]]]
    # {"gmail": ["a@gmail.com", "b@work.com"], "drive": ["a@gmail.com"]}
    # Dict key = provider (lowercase), value = sorted list of connected account emails.
    user_connected_apps: Optional[Dict[str, List[str]]]
    # schedule_context: resolved cron from a scheduling expression in this turn.
    #   Set by semantic_intake via chrono_parser.py. Consumed by workflow planner.
    #   {"cron": "0 9 * * 1", "human": "Every Monday at 9:00", "type": "weekly",
    #    "next_run": "2026-06-16T09:00:00Z"}
    schedule_context: Optional[Dict[str, Any]]
    # user_preferences_context: formatted staleness-annotated preferences block.
    #   Pre-loaded by the WS handler and passed in input_state.
    user_preferences_context: Optional[str]

    # ── Pipeline level (set by responder aggregation) ─────────────────────────
    # level_1 → validation errors or pending account selection
    # level_2 → all checks passed, ready for workflow_planner
    requirement_level: Optional[Literal["level_1", "level_2"]]

    # ── Inference-Time Scaling (set by WS handler per turn) ───────────────────
    # Controls Tavily search depth, research char cap, LLM temperature, and
    # max output tokens. Absent or invalid → treated as "medio" by all nodes.
    effort_level: Optional[Literal["low", "medio", "high", "max"]]
    # model_name: OpenAI model chosen by the client (validated by WS handler).
    # Passed via input_state and read by responder to create the chat LLM.
    model_name: Optional[str]

    # ── Routing helpers (set by semantic_intake) ─────────────────────────────
    # account_selection_resolved: True when the user's message resolved a pending
    # account-selection prompt. Routes semantic_intake → responder directly (skips
    # the fan-out) to avoid a concurrent write to selected_accounts from auth_validator.
    # semantic_intake resets this to False via _EMPTY_RESULT on every non-selection turn.
    account_selection_resolved: bool

    # ── Cognitive Memory System (set by goal_resolver + memory_retriever) ─────
    # goal_id: active goal for this turn, resolved by goal_resolver from user_active_goals.
    #   None when the user has no active goals (rest of the graph works normally).
    goal_id: Optional[str]
    # raw_memories: unscored output from memory_engine.retrieve_memories().
    #   {"goals": [...], "semantic": [...], "episodic": [...], "decisions": [...], "structured": {...}}
    raw_memories: Optional[Dict[str, Any]]
    # ranked_context: scored+filtered string from context_ranker.rank_memories().
    #   Injected into the responder system prompt as "MEMORY CONTEXT:".
    #   None when no goals/decisions/preferences are available (cold start).
    ranked_context: Optional[str]
    # user_memory_context: hechos del usuario + en que iba en otras conversaciones (memory_retriever); va en el bloque
    #   "## User" del responder y lo ve el juez. Fuera del ranker: es corto y siempre aplica.
    user_memory_context: Optional[str]
    # memory_learned: lo que memory_learner escribio este turno (para la traza y la UI de pruebas).
    memory_learned: Optional[Dict[str, Any]]
    # conversation_summary / summary_upto: resumen rodante de los mensajes viejos (Human/AI) y cuantos ya estan
    #   plegados en el. Los escribe solo memory_updater; el responder manda resumen + ventana. Viven en el checkpoint:
    #   NO estan en _EMPTY_RESULT de semantic_intake (se perderian cada turno). Los mensajes no se borran del hilo.
    conversation_summary: Optional[str]
    summary_upto: Optional[int]
    # action_results: llamadas que action_runner hizo este turno (modo act): fn, app, args, ok, data|error, ms.
    action_results: Optional[List[Dict[str, Any]]]
    action_stop: Optional[str]
    # pending_action: escrituras que esperan el "si" del usuario (modo act, fase 2): {calls:[{fn,app,args,policy}],
    #   created_at, conversation_id}. Vive entre turnos (NO esta en _EMPTY_RESULT). Solo la escribe action_runner,
    #   salvo "cancel", que la borra semantic_intake (ese turno no hay ramas en paralelo).
    pending_action: Optional[Dict[str, Any]]
    # pending_decision: lo que el usuario hizo con pending_action este turno (confirm|cancel|change|digress|unclear).
    #   Por turno: semantic_intake la reinicia.
    pending_decision: Optional[str]
    # decision_logged: True when memory_updater persisted a decision this turn.
    #   Only set when requirement_level == "level_2" and ranked_context exists.
    decision_logged: bool

    # ── Reliability layer ─────────────────────────────────────────────────────
    # agent_error: set by _safe_node in graph.py when a wrapped node raises an
    #   unexpected exception. {"node": str, "exc": str, "traceback": str}
    #   Routes the graph to error_handler_node instead of propagating the exception.
    agent_error: Optional[Dict[str, Any]]
    # eval_retry_count: incremented by response_evaluator_node each time it
    #   sends the responder back for a correction. Capped at 2 to prevent loops.
    eval_retry_count: int
    # eval_feedback: short correction string from response_evaluator_node,
    #   injected into the responder system prompt on the retry turn.
    eval_feedback: Optional[str]
    # eval_report: veredicto estructurado del evaluador este turno ({passed, attempt, action, checks, feedback, ...}).
    #   La UI lo muestra como "centinela"; action = approved | retry | exhausted | skipped.
    eval_report: Optional[Dict[str, Any]]
    # eval_drafts: cada borrador del turno con sus fallas graves confirmadas ({attempt, content, majors}). Si se agotan
    #   los intentos se entrega el MEJOR, no el ultimo: un juez equivocado no puede cambiar una respuesta buena por una peor.
    eval_drafts: Optional[List[Dict[str, Any]]]
    # active_mandates: instrucciones obligatorias que recibio el responder este turno (pausa por app no conectada,
    #   directiva de animo/esfuerzo). El evaluador juzga la respuesta contra ellas, no solo contra la peticion.
    active_mandates: Optional[List[str]]

    # ── Deliberative planning (set by workflow_planner) ───────────────────────
    # Private execution plan generated before the responder. Never shown to user.
    # None when no apps are involved (pure chat or closing turns).
    planning_trace: Optional[str]

    # ── Requirements Investigator (multi-turn workflow builder) ───────────────
    # req_level drives the state machine. None=inactive. Solo hay dos etapas (REQ_GATHER y REQ_CONFIRM, abajo):
    #   1=reunir (apps conectadas, plan, datos faltantes), 4=confirmar (borrador guardado + simulacion, espera el "si").
    # A stage does not advance while req_pending_questions is non-empty — see
    # req_pending_questions below.
    req_level: Optional[int]
    # req_relay: este turno el flujo produjo un mensaje (structured_prompt) que el responder debe entregar tal cual.
    #   Es por turno (semantic_intake lo reinicia). No basta con "req_level is not None": el mensaje de activacion o de
    #   cancelacion sale con req_level=None y se trataba como una simple intencion aclarada.
    req_relay: bool
    # requested_ui_actions: acciones de interfaz que el usuario pidio este turno ("abreme mis workflows"), ya validadas
    #   contra el catalogo de Mongo (helpers/ui_actions.py). Por turno. chat._build_ui_actions las emite.
    requested_ui_actions: Optional[List[dict]]
    # user_language: idioma en que escribe el usuario ("English", "Portuguese"...), de semantic_intake. Persiste entre turnos
    #   (un "yes" no lo cambia). Lo usa el flujo de workflows para entregar sus mensajes fijos, escritos en espanol, en
    #   el idioma del usuario.
    user_language: Optional[str]
    # req_compose: este turno el flujo dejo HECHOS en structured_prompt (que falta conectar, que app solo lee) y el
    #   responder arma UNA respuesta con ellos y con la pregunta del usuario, en vez de entregar el texto fijo: el aviso
    #   de "conecta esto" ignoraba lo que el usuario preguntaba en ese turno (tienda_gmail). Por turno, como req_relay.
    req_compose: bool
    # req_adjustment: correccion del usuario sobre el plan mostrado; la deja CONFIRM y la consume GATHER en el mismo turno.
    req_adjustment: Optional[str]
    # req_schedule: {"cron","human"} que se le mostro al usuario en CONFIRM; es el que se programa al activar.
    req_schedule: Optional[Dict[str, Any]]
    # req_confirm_unclear: veces que CONFIRM no entendio la respuesta (el clasificador fallo o fue ambigua).
    req_confirm_unclear: Optional[int]
    # req_pending_questions: queue of individual questions still to ask within the
    # CURRENT level (one-question-per-turn — never batch multiple into one
    # message). req_investigator_node pops one per turn before running any level
    # logic; the level only advances once this drains.
    req_pending_questions: Optional[List[str]]
    # req_level_entered: which level a question batch was last generated for —
    # lets a level function tell "first visit" (generate + queue questions) apart
    # from "queue just drained, resolve and advance" without re-asking. Reset to
    # None by the level itself once it advances.
    req_level_entered: Optional[int]
    # req_flow_action: recomputed by semantic_intake_node every turn while
    # req_level is active — "continue" (answering what was asked), "cancel"
    # (abandon the flow), or "digress" (unrelated question, flow stays paused).
    # Same "reset every turn" idiom as is_closing — never read across turns.
    req_flow_action: Optional[Literal["continue", "cancel", "digress"]]
    req_goal: Optional[str]
    req_apps_scope: Optional[List[str]]
    req_trigger_type: Optional[str]
    req_trigger_event: Optional[str]
    req_plan: Optional[Dict[str, Any]]
    # req_plan_rounds: cuantas veces el nivel 3 pidio datos que faltaban para armar el plan (argumentos de funciones que el
    # usuario no dio). Con 2 rondas ya no pregunta mas: deja fuera el paso incompleto y lo avisa.
    req_plan_rounds: Optional[int]
    req_preflight_passed: Optional[bool]
    req_preflight_failures: Optional[List[str]]
    # req_dry_run_result: simulated execution trace from
    # WorkflowExecutor.execute_dry_run() — {"dry_run": True, "steps_simulated", ...}. Que exista (junto con
    # req_workflow_id) es lo que marca que CONFIRM ya mostro el plan y espera la respuesta.
    req_dry_run_result: Optional[Dict[str, Any]]
    req_workflow_id: Optional[str]
    req_deployed: bool
    # req_schedule_asked: GATHER ya pregunto el horario porque no habia uno entendible; evita preguntar dos veces.
    req_schedule_asked: Optional[bool]
    # req_deployed_steps: the exact step dicts written to Mongo by _deploy (post
    # node_type fallback) — lets _build_ui_actions emit render_workflow without a
    # second DB round-trip.
    req_deployed_steps: Optional[List[Dict[str, Any]]]
    # req_webhook_url / req_trigger_summary: set by _deploy when the plan's
    # trigger_type is "webhook"/"schedule" — surfaced via the open_trigger ui_action.
    req_webhook_url: Optional[str]
    req_trigger_summary: Optional[str]

    # ── Document understanding (set by document_analyzer) ────────────────────
    # turn_resources: same as ShifuInputState — carried into ShifuState so
    # document_analyzer can read it via the normal state dict.
    turn_resources: Optional[List[Dict[str, Any]]]
    # session_documents: registry of every file seen in this conversation
    # (thread), keyed by file_id. Persists across turns via the MongoDB
    # checkpointer — lets the user reference a document uploaded turns ago
    # ("compare that excel with the invoice from before") without re-uploading.
    # _merge_dicts is safe here: reprocessing the same file_id just overwrites
    # its own entry, never another file's.
    session_documents: Annotated[Optional[Dict[str, Dict[str, Any]]], _merge_dicts]
    # turn_document_context: plain-text block for SHORT documents relevant this
    # turn (new attachments + previously-referenced docs when
    # needs_document_context is True), ready to inject into the responder
    # prompt. document_analyzer ALWAYS returns this key (even as None) to clear
    # stale context from a previous turn — never inherited by omission.
    turn_document_context: Optional[str]
    # retrieved_document_chunks: top-K Atlas Vector Search chunks for LARGE
    # documents relevant this turn. [{"file_id","filename","text","score"}, ...]
    retrieved_document_chunks: Optional[List[Dict[str, Any]]]
    # structured_extraction: latest structured extraction result (invoice/
    # contract/generic), including "needs_review"/"uncertain_fields".
    structured_extraction: Optional[Dict[str, Any]]
    # extraction_review_pending: req_level-style multi-turn HITL state for
    # low-confidence extractions. None = no review pending. When set,
    # document_analyzer dispatches to _resolve_extraction_review next turn
    # instead of re-ingesting attachments.
    extraction_review_pending: Optional[Dict[str, Any]]
    # needs_document_context / document_intent / document_extraction_hint:
    # set by semantic_intake (same pattern as needs_external_info) so
    # document_analyzer knows whether to pull in previously-uploaded documents
    # and what the user wants done with them.
    needs_document_context: bool
    document_intent: Optional[Literal["qa", "compare", "extract_structured"]]
    document_extraction_hint: Optional[Literal["invoice", "contract", "generic"]]
