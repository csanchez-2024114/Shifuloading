"""
v3_debug_ws — LangGraph-backed WebSocket for agente_v3.

Connect: ws[s]://<host>/api/v4/ws/chat-debug?token=<JWT>&conversation_id=<id>

Streaming strategy:
  Uses graph.ainvoke() (NOT astream/astream_events) + a LangChain
  AsyncCallbackHandler to capture tokens from the chat LLM.

  LangGraph's streaming APIs (astream_events v2 / stream_mode="messages")
  both emit the same response twice — once as streaming chunks and once
  as the final AIMessage stored in state. The callback approach fires
  exactly once per token, at the LLM level, before LangGraph touches it.

  The chat node tags its LLM with "shifu-chat". The callback ignores
  tokens from all other nodes (e.g. bigtools_inspector).

Frontend → Backend:
  {"type": "user_message", "text": "...", "model": "gpt-4o-mini",
   "resources": [{"type": "file", "url": "https://res.cloudinary.com/...", "title": "factura.pdf",
                  "provider": "Others", "file_id": "...", "metadata": {}}]}
  {"type": "ping"}

  resources: attachments already uploaded via POST /api/v2/uploads/file (Cloudinary),
  attached to this message so document_analyzer can read them. Same shape as
  ResourceModel. Optional, capped at 10 per turn.

Backend → Frontend:
  {"type": "token", "text": "<chunk>"}
  {"type": "done",  "text": "<full_reply>", "model": "..."}
  {"type": "error", "message": "..."}
  {"type": "pong"}
  {"type": "document_status", "processed": [...], "errors": [...]}
  {"type": "document_extraction", "data": {...}}
  {"type": "usage_warning", "message": "..."}
    — CTA de upgrade al cruzar el 80% de la cuota diaria de tokens del plan.
    Se envía una sola vez por día (UTC). Nunca bloquea el chat.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import HumanMessage
from langchain_core.outputs import LLMResult

from bson import ObjectId

from config import Config
from app.core.quota import check_message_quota, track_daily_tokens, maybe_get_token_warning
from app.core.constants import Collections
from app.billing.plans import get_recursion_limit
from app.agent.shared.helpers.preferences_loader import load_user_prefs_block
from app.agent.shifu_base_v1.graph.node_labels import get_node_label
from app.agent.shared.nodes.document_analyzer import file_id_for as _document_file_id
from app.services.chat_memory import save_message
from app.services.geo_service import extract_client_ip, get_geo_from_ip
from app.routes.chat.chat import _build_ui_actions, _owned_by_other

logger = logging.getLogger(__name__)
router = APIRouter()

_SECRET = Config.SECRET_KEY
_ALGO = "HS256"
_ALLOWED_MODELS = {"gpt-4o-mini", "gpt-4.1-nano"}
_DEFAULT_MODEL  = "gpt-4o-mini"

_ALLOWED_EFFORTS = {"low", "medio", "high", "max"}
_DEFAULT_EFFORT  = "medio"

_CHAT_TAG = "shifu-chat"  # must match the tag set on the LLM in nodes/responder.py


def _ws_json(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False)


_MAX_TURN_RESOURCES = 10


def _validate_resources(raw: Any) -> list[dict]:
    """Validates the optional 'resources' array from the incoming payload —
    same shape as ResourceModel, kept as plain dicts to avoid coupling the WS
    hot path to a model designed for the REST V2 flow. Drops malformed
    entries (missing type/url) instead of rejecting the whole message."""
    if not isinstance(raw, list):
        return []
    validated = []
    for item in raw[:_MAX_TURN_RESOURCES]:
        if not isinstance(item, dict):
            continue
        if not item.get("type") or not item.get("url"):
            continue
        validated.append({
            "type": str(item["type"]),
            "url": str(item["url"]),
            "title": item.get("title"),
            "provider": item.get("provider", "Others"),
            "file_id": item.get("file_id"),
            "metadata": item.get("metadata") or {},
        })
    return validated


def _fix_markdown(text: str) -> str:
    """Close any Markdown constructs truncated mid-stream (zero token cost)."""
    if text.count("```") % 2 != 0:
        text = text.rstrip() + "\n```"
    if text.count("**") % 2 != 0:
        text += "**"
    single = text.count("*") - 2 * text.count("**")
    if single % 2 != 0:
        text += "*"
    return text


# ── Streaming callback ─────────────────────────────────────────────────────────

class _WsChatStreamer(AsyncCallbackHandler):
    """
    Fires on_llm_new_token for every streaming token produced by the chat LLM.

    Only processes tokens tagged with _CHAT_TAG so tokens from other nodes
    (bigtools_inspector, semantic_intake) are silently ignored.

    LangGraph's streaming APIs (astream / astream_events) emit the same content
    twice — once per chunk and once when the message is stored in state.
    This callback fires exactly once per token at the LLM level, guaranteeing
    no duplication regardless of LangGraph version or graph topology.
    """

    def __init__(
        self,
        ws: WebSocket,
        redis_client: Any = None,
        user_id: str | None = None,
        plan: str = "free",
    ) -> None:
        super().__init__()
        self.ws = ws
        self.accumulated = ""
        self._redis_client = redis_client
        self._user_id = user_id
        self._plan = plan

    async def on_llm_new_token(
        self,
        token: str,
        *,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        if not token:
            return
        if _CHAT_TAG not in (tags or []):
            return
        self.accumulated += token
        try:
            await self.ws.send_text(_ws_json({"type": "token", "text": token}))
        except Exception:
            pass  # WebSocket may have closed mid-stream

    async def on_chain_start(
        self,
        serialized: dict,
        inputs: dict,
        *,
        metadata: dict | None = None,
        **kwargs: Any,
    ) -> None:
        node = (metadata or {}).get("langgraph_node") or (serialized or {}).get("name", "")
        label = get_node_label(node)
        if not label:
            return
        try:
            await self.ws.send_text(_ws_json({"type": "agent_status", "node": node, "label": label}))
        except Exception:
            pass

    @staticmethod
    def _extract_total_tokens(response: LLMResult) -> int:
        llm_output = response.llm_output or {}
        usage = llm_output.get("token_usage") or llm_output.get("usage")
        if isinstance(usage, dict) and usage.get("total_tokens"):
            return int(usage["total_tokens"])
        # Fallback: langchain más reciente expone usage_metadata en el AIMessage generado
        for gen_list in response.generations:
            for gen in gen_list:
                msg = getattr(gen, "message", None)
                usage_metadata = getattr(msg, "usage_metadata", None) if msg else None
                if usage_metadata and usage_metadata.get("total_tokens"):
                    return int(usage_metadata["total_tokens"])
        return 0

    async def on_llm_end(
        self,
        response: LLMResult,
        *,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        # Cuota diaria de tokens de chat — solo avisa (CTA de upgrade), nunca bloquea.
        if _CHAT_TAG not in (tags or []) or not self._user_id:
            return
        tokens = self._extract_total_tokens(response)
        if tokens <= 0:
            return
        daily_total = await track_daily_tokens(self._redis_client, self._user_id, tokens)
        warning = await maybe_get_token_warning(self._redis_client, self._user_id, self._plan, daily_total)
        if warning:
            try:
                await self.ws.send_text(_ws_json({"type": "usage_warning", "message": warning}))
            except Exception:
                pass


# ── WebSocket handler ──────────────────────────────────────────────────────────

@router.websocket("/ws/chat-debug")
async def v3_debug_ws(
    websocket: WebSocket,
    token: str = Query(...),
    conversation_id: str = Query(...),
):
    try:
        payload = jwt.decode(token, _SECRET, algorithms=[_ALGO])
        user_id: str = payload.get("user_id", "")
        if not user_id:
            await websocket.close(code=4001, reason="Token sin user_id")
            return
    except JWTError:
        await websocket.close(code=4001, reason="Token inválido")
        return

    await websocket.accept()
    db = websocket.app.state.db
    if await _owned_by_other(conversation_id, user_id, db):
        await websocket.close(code=4004, reason="Conversación no encontrada")
        return
    logger.info(f"[ShifuDebugWS] connected user={user_id} conv={conversation_id}")

    # Plan cargado una vez por conexión (no cambia a mitad de sesión) — usado
    # para el rate-limit por minuto y para el tope de iteraciones del agente.
    user_plan = "free"
    user_name = ""
    try:
        user_doc = await db[Collections.USERS].find_one({"_id": ObjectId(user_id)}, {"plan": 1, "name": 1})
        if user_doc and user_doc.get("plan"):
            user_plan = user_doc["plan"]
        user_name = (user_doc or {}).get("name", "").strip()
    except Exception:
        logger.warning(f"[ShifuDebugWS] No se pudo cargar el plan del usuario {user_id}, usando 'free'")

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(_ws_json({"type": "error", "message": "JSON inválido"}))
                continue

            msg_type = msg.get("type", "")

            if msg_type == "ping":
                await websocket.send_text(_ws_json({"type": "pong"}))
                continue

            if msg_type != "user_message":
                continue

            user_text: str = msg.get("text", "").strip()
            if not user_text:
                continue

            turn_resources = _validate_resources(msg.get("resources"))

            model_name = msg.get("model", _DEFAULT_MODEL)
            if model_name not in _ALLOWED_MODELS:
                model_name = _DEFAULT_MODEL

            effort_level = msg.get("effort", _DEFAULT_EFFORT)
            if effort_level not in _ALLOWED_EFFORTS:
                effort_level = _DEFAULT_EFFORT

            redis_client = getattr(websocket.app.state, "redis", None)
            if not await check_message_quota(redis_client, user_id, plan=user_plan):
                await websocket.send_text(_ws_json({"type": "error", "message": "Too many messages. Wait a moment and try again."}))
                continue

            # Load preferences and persist user message.
            # History and session state (selected_accounts, available_accounts)
            # are managed by the LangGraph checkpointer — no manual load needed.
            current_time_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            prefs_block, user_timezone = await load_user_prefs_block(user_id, db)
            await save_message(user_id, conversation_id, "user", user_text, db, resources=turn_resources)

            # GeoIP: resolve client IP → timezone + location.
            # Preference from DB takes priority; GeoIP is the fallback.
            client_ip = extract_client_ip(
                dict(websocket.headers),
                websocket.client.host if websocket.client else None,
            )
            geo = get_geo_from_ip(client_ip)
            if not user_timezone and geo.timezone:
                user_timezone = geo.timezone
            user_location = geo.location

            logger.info(
                "[ShifuDebugWS] geo ip=%s tz=%s location=%s",
                client_ip, user_timezone or "—", user_location or "—",
            )

            input_state = {
                # Only the new message — checkpointer appends to existing history
                "messages":                 [HumanMessage(content=user_text)],
                "user_id":                  user_id,
                "conversation_id":          conversation_id,
                "model_name":               model_name,
                "effort_level":             effort_level,
                "current_time_utc":         current_time_utc,
                "user_timezone":            user_timezone,
                "user_location":            user_location,
                "user_country_code":        geo.country_code,
                "user_preferences_context": prefs_block,
                "turn_resources":           turn_resources or None,
                "user_name":                user_name,
                # selected_accounts / available_accounts are NOT included here —
                # the checkpointer restores them automatically from the last checkpoint
            }
            lg_config = {
                "configurable": {"thread_id": conversation_id},
                "recursion_limit": get_recursion_limit(user_plan),
            }

            streamer = _WsChatStreamer(websocket, redis_client=redis_client, user_id=user_id, plan=user_plan)
            final_state: dict = {}
            shifu_graph = getattr(websocket.app.state, "shifu_graph", None)
            if shifu_graph is None:
                await websocket.send_text(_ws_json({"type": "error", "message": "Agent not ready. Try again in a moment."}))
                continue
            try:
                # ainvoke runs the full graph. Tokens arrive via streamer callback —
                # no LangGraph streaming mode, no duplication risk.
                final_state = await shifu_graph.ainvoke(
                    input_state,
                    {**lg_config, "callbacks": [streamer]},
                ) or {}
            except (WebSocketDisconnect, RuntimeError):
                raise
            except Exception as exc:
                logger.error(f"[ShifuDebugWS] graph error user={user_id}: {exc}", exc_info=True)
                await websocket.send_text(_ws_json({"type": "error", "message": str(exc)}))
                continue

            accumulated = _fix_markdown(streamer.accumulated)

            # Persist AI reply
            if accumulated:
                try:
                    await save_message(user_id, conversation_id, "ai", accumulated, db)
                except Exception as exc:
                    logger.error(f"[ShifuDebugWS] save error conv={conversation_id}: {exc}")

            # Reuse the same typed ui_actions protocol production chat uses (connect_app /
            # render_workflow / open_trigger) — was a separate, connect_app-only copy here
            # that had already drifted out of sync.
            ui_actions = _build_ui_actions(final_state)

            await websocket.send_text(_ws_json({
                "type":       "done",
                "text":       accumulated,
                "model":      model_name,
                "ui_actions": ui_actions,
                # Debug-only: lets ChatDebug.tsx show which req_investigator level (1-6,
                # None=inactive) this turn ended on.
                "req_level":  final_state.get("req_level"),
            }))

            # Send cited sources when Tavily ran (enables frontend source cards)
            sources = final_state.get("retrieved_sources")
            if sources:
                await websocket.send_text(_ws_json({"type": "sources", "data": sources}))

            # document_analyzer status — errors go through validation_reports (same
            # channel catalog/auth use); "processed" summarizes this turn's uploads.
            reports = final_state.get("validation_reports") or []
            doc_errors = [r for r in reports if r.get("source") == "document" and r.get("status") == "error"]
            if turn_resources or doc_errors:
                session_documents = final_state.get("session_documents") or {}
                turn_file_ids = {_document_file_id(r) for r in turn_resources}
                processed = [
                    {"file_id": fid, **info}
                    for fid, info in session_documents.items()
                    if fid in turn_file_ids
                ]
                await websocket.send_text(_ws_json({
                    "type": "document_status",
                    "processed": processed,
                    "errors": doc_errors,
                }))

            if extraction := final_state.get("structured_extraction"):
                await websocket.send_text(_ws_json({"type": "document_extraction", "data": extraction}))
            logger.info(
                f"[ShifuDebugWS] done user={user_id} model={model_name} "
                f"len={len(accumulated)} conv={conversation_id}"
            )

    except WebSocketDisconnect:
        logger.info(f"[ShifuDebugWS] disconnected user={user_id} conv={conversation_id}")
    except RuntimeError as exc:
        if "not connected" in str(exc).lower() or "accept" in str(exc).lower():
            logger.info(f"[ShifuDebugWS] client closed abruptly user={user_id}")
        else:
            logger.exception(f"[ShifuDebugWS] unexpected error user={user_id}: {exc}")
    except Exception as exc:
        logger.exception(f"[ShifuDebugWS] unexpected error user={user_id}: {exc}")

