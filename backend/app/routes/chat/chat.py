"""
Shifu commercial chat endpoints.

WebSocket  /ws/chat       — streaming WS (token-by-token via LangChain callback)
HTTP SSE   /chat/stream   — streaming SSE (same logic, fetch-friendly transport)

Both endpoints use the same graph, same auth (JWT), same geo+prefs stack.
Protocol (WS sends as JSON, SSE sends as "data: <json>\\n\\n"):
  token:  {"type": "token",  "text": "<chunk>"}
  done:   {"type": "done",   "text": "<full>", "model": "...", "ui_actions": [...], "workflow_id": "<id>|null"}
  sources: {"type": "sources", "data": [{"title": "...", "url": "...", "domain": "..."}]}  (sent after done, only if any were retrieved this turn)
  error:  {"type": "error",  "message": "..."}
  pong:   {"type": "pong"}  (WS only)
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse
from jose import JWTError, jwt
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import HumanMessage
from langchain_core.outputs import LLMResult

from bson import ObjectId

from config import Config
from app.core import trace_log
from app.core.quota import check_message_quota, track_daily_tokens, maybe_get_token_warning
from app.core.constants import Collections
from app.billing.plans import get_recursion_limit
from app.billing.pricing import cost_usd
from app.agent.shared.helpers.preferences_loader import load_user_prefs_block
from app.agent.shifu_base_v1.graph.node_labels import get_node_label
from app.agent.shared.utils.login_paths import get_auth_type
from app.agent.shared.helpers import ui_actions as ui_catalog
from app.services import file_store  # alias: aqui `ui_actions` es la lista que se le manda al frontend
from app.agent.shared.helpers.situation import drop_shadowed_auth_errors
from app.services.chat_memory import CONTEXT, save_message
from app.agent.version import agent_version
from app.services.geo_service import extract_client_ip, get_geo_from_ip


async def _load_user_plan(user_id: str, db) -> str:
    try:
        user_doc = await db[Collections.USERS].find_one({"_id": ObjectId(user_id)}, {"plan": 1})
        return (user_doc or {}).get("plan") or "free"
    except Exception:
        return "free"


async def _owned_by_other(conversation_id: str, user_id: str, db) -> bool:
    """El conversation_id lo manda el cliente y es el thread_id del checkpoint: sin esto, un usuario cargaba el estado
    de la conversacion de otro (paso en la UI de pruebas con un id guardado en localStorage)."""
    return await db[CONTEXT].find_one({"conversation_id": conversation_id, "user_id": {"$ne": user_id}}, {"_id": 1}) is not None


async def _load_user_name(user_id: str, db) -> str:
    try:
        user_doc = await db[Collections.USERS].find_one({"_id": ObjectId(user_id)}, {"name": 1})
        return (user_doc or {}).get("name", "").strip()
    except Exception:
        return ""

logger = logging.getLogger(__name__)
router = APIRouter()

_SECRET = Config.SECRET_KEY
_ALGO = "HS256"
_ALLOWED_MODELS = {"gpt-4o-mini", "gpt-4.1-nano"}
_DEFAULT_MODEL  = "gpt-4o-mini"
_ALLOWED_EFFORTS = {"low", "medio", "high", "max"}
_DEFAULT_EFFORT  = "medio"
_CHAT_TAG = "shifu-chat"


def dev_ui_enabled() -> bool:
    """Herramientas de desarrollo (trazas con los prompts, interfaz /ui). Apagado salvo SHIFU_DEV_UI=1."""
    return os.getenv("SHIFU_DEV_UI", "").lower() in ("1", "true", "yes")


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


def _ws_json(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _fix_markdown(text: str) -> str:
    if text.count("```") % 2 != 0:
        text = text.rstrip() + "\n```"
    if text.count("**") % 2 != 0:
        text += "**"
    single = text.count("*") - 2 * text.count("**")
    if single % 2 != 0:
        text += "*"
    return text


def _build_ui_actions(final_state: dict) -> list:
    """Projects graph state into the typed `ui_actions` directives the frontend
    renders (see `uiActionsSlice.ts`'s `dispatchUiActions`). Shifu is the only
    thing that drives these — no manual-config UI reads/writes this state.

    Plan-limit upgrades are NOT an ui_action — req_nodes._deploy publishes the
    existing `plan_limit_exceeded` WS event (same channel/modal the run-quota
    path already uses) directly when a limit blocks a deploy.
    """
    actions: list[dict] = []

    # Las que pidio el usuario ("abreme mis workflows"), ya validadas contra el catalogo (helpers/ui_actions.py).
    requested = final_state.get("requested_ui_actions") or []

    # Misma regla que el texto del agente (situation.drop_shadowed_auth_errors): sin boton para apps que no existen o con
    # las que no se puede hacer nada; asi la UI nunca muestra algo que la respuesta contradice.
    for r in drop_shadowed_auth_errors(final_state.get("validation_reports") or []):
        # Si el turno fue "abreme tal pantalla", no se suma un boton de conectar: salia el de Sheets al pedir ver la
        # memoria solo porque la app aparecia en la conversacion.
        if r.get("needs_auth") and r.get("source") == "auth" and not requested:
            app_key = r.get("app_key") or r["app"]  # nombre canonico del catalogo ("sheets" -> "google_sheets"): es el proveedor que se conecta
            actions.append({
                "type":      "connect_app",
                "app":       app_key,
                "reason":    r.get("reason", "not_connected"),
                "auth_url":  r.get("auth_url", ""),
                "auth_type": get_auth_type(app_key.lower()),  # oauth2 | apikey | oauth1 | unknown: decide que control pinta el front
            })

    # Solo en el turno en que el flujo ACTIVO el workflow (req_relay es por turno): el id sigue en el estado en los
    # turnos siguientes y la tarjeta saldria de nuevo en cada respuesta.
    workflow_id = final_state.get("req_workflow_id")
    if workflow_id and final_state.get("req_deployed") and final_state.get("req_relay"):
        actions.append({
            "type":        "render_workflow",
            "workflow_id": workflow_id,
            "steps":       final_state.get("req_deployed_steps") or [],
        })

        webhook_url = final_state.get("req_webhook_url")
        trigger_summary = final_state.get("req_trigger_summary")
        if webhook_url or trigger_summary:
            actions.append({
                "type":         "open_trigger",
                "workflow_id":  workflow_id,
                "trigger_type": final_state.get("req_trigger_type") or "manual",
                "webhook_url":  webhook_url,
                "summary":      trigger_summary or "",
            })

    return actions + requested


def _decode_jwt(token: str) -> str | None:
    try:
        payload = jwt.decode(token, _SECRET, algorithms=[_ALGO])
        return payload.get("user_id", "") or None
    except JWTError:
        return None


# ── Streaming callback (shared by WS and SSE) ─────────────────────────────────

class _ChatStreamer(AsyncCallbackHandler):
    """Captures tokens from the chat LLM and puts them on a queue."""

    def __init__(self, queue: asyncio.Queue, trace: bool = False, hold: bool = False, turn_log=None) -> None:
        super().__init__()
        self.queue = queue
        self.turn_log = turn_log      # app.core.trace_log.TurnTrace o None: registro completo del turno para auditoria
        self._llm_log: dict = {}      # run_id -> datos de la llamada al LLM mientras corre
        self.accumulated = ""
        self.total_tokens = 0
        self.trace = trace  # emite eventos "trace" y "sentinel" (nodos, llamadas LLM, veredictos) para la UI de pruebas
        self.hold = hold    # calidad primero: no transmite tokens; el texto final llega en "done", ya aprobado por el evaluador
        self._runs: dict = {}
        self._responder_starts = 0
        self._llm_meta: dict = {}     # run_id -> (nodo, modelo) de cada llamada al LLM
        self.usage_calls: list[dict] = []  # uso real por llamada: tokens y costo
        self.evals: list[dict] = []  # un veredicto del evaluador por intento; se guarda con la respuesta

    @staticmethod
    def _short(obj: Any, n: int = 2000) -> str:
        s = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False, default=str)
        return s if len(s) <= n else s[:n] + f"… (+{len(s) - n} chars)"

    async def on_chat_model_start(self, serialized, messages, *, run_id, metadata=None, **kwargs) -> None:
        params = kwargs.get("invocation_params") or {}
        self._llm_meta[run_id] = ((metadata or {}).get("langgraph_node"), params.get("model_name") or params.get("model"))
        if self.turn_log is not None:
            self._llm_log[run_id] = {
                "node": (metadata or {}).get("langgraph_node"), "tags": kwargs.get("tags") or [],
                "model": params.get("model_name") or params.get("model"),
                "params": {k: params.get(k) for k in ("temperature", "max_tokens", "stream") if k in params},
                "attempt": self._responder_starts, "t0": time.perf_counter(),
                "messages": [{"role": m.type, "content": m.content} for m in messages[0]],
            }
        if self.trace:
            prompt = "\n\n".join(f"[{m.type}] {m.content}" for m in messages[0])
            self._runs[run_id] = ("llm", (metadata or {}).get("langgraph_node"), time.perf_counter(), prompt)

    async def on_llm_new_token(
        self,
        token: str,
        *,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        if not token or _CHAT_TAG not in (tags or []):
            return
        self.accumulated += token
        if not self.hold:
            await self.queue.put({"type": "token", "text": token})

    async def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: dict[str, Any],
        *,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        name = (metadata or {}).get("langgraph_node") or (serialized or {}).get("name", "")
        label = get_node_label(name)
        if label:
            await self.queue.put({"type": "agent_status", "node": name, "label": label})
        if (metadata or {}).get("langgraph_node") == kwargs.get("name"):  # la corrida del nodo en si
            if name == "responder":
                self._responder_starts += 1
                if self._responder_starts > 1:  # reintento del evaluador: el borrador anterior se descarta, no se concatena
                    self.accumulated = ""
                    await self.queue.put({"type": "reset"})
                    if self.turn_log is not None:
                        self.turn_log.event("retry_reset", attempt=self._responder_starts)
            if self.trace or name == "response_evaluator" or self.turn_log is not None:
                self._runs[kwargs["run_id"]] = ("node", name, time.perf_counter(), None)

    async def on_chain_end(self, outputs: Any, *, run_id, **kwargs: Any) -> None:
        run = self._runs.pop(run_id, None)
        if not run or run[0] != "node":
            return
        if run[1] == "responder" and isinstance(outputs, dict) and outputs.get("messages") and not self.accumulated:
            # El responder entrego un mensaje sin pasar por el modelo (relevo del flujo de workflows): no hubo tokens,
            # asi que se emite completo.
            self.accumulated = str(outputs["messages"][-1].content)
            if not self.hold:
                await self.queue.put({"type": "token", "text": self.accumulated})
        if run[1] == "response_evaluator" and isinstance(outputs, dict) and outputs.get("eval_report"):
            self.evals.append(outputs["eval_report"])
            if outputs.get("messages"):  # se agotaron los intentos y el evaluador eligio un borrador anterior: ese es el texto final
                self.accumulated = str(outputs["messages"][-1].content)
                if not self.hold:
                    await self.queue.put({"type": "reset"})
                    await self.queue.put({"type": "token", "text": self.accumulated})
        if self.turn_log is not None:  # la salida de cada nodo = sus decisiones (intencion, apps, validaciones, veredicto)
            self.turn_log.event("node", node=run[1], attempt=self._responder_starts,
                                ms=round((time.perf_counter() - run[2]) * 1000), output=self._short(outputs, 20000))
        if not self.trace:
            return
        await self.queue.put({"type": "trace", "kind": "node", "node": run[1],
                              "ms": round((time.perf_counter() - run[2]) * 1000), "output": self._short(outputs)})
        if (sentinel := self._sentinel(run[1], outputs)):
            await self.queue.put(sentinel)

    def quality(self) -> dict | None:
        """Resumen de cuantos intentos gasto la respuesta final y por que se rechazaron los anteriores."""
        if not self.evals:
            return None
        return {
            "attempts": len(self.evals),
            "rejections": sum(1 for e in self.evals if not e.get("passed")),
            "final": self.evals[-1].get("action"),  # approved | exhausted | skipped
            "delivered_attempt": self.evals[-1].get("delivered_attempt"),  # cual de los intentos recibio el usuario
            "evals": [
                {"attempt": e.get("attempt"), "action": e.get("action"), "feedback": e.get("feedback") or e.get("reason"),
                 "failed": [{"name": c["name"], "note": c["note"]} for c in e.get("checks", []) if not c.get("passed")]}
                for e in self.evals
            ],
        }

    @staticmethod
    def _sentinel(node: str, outputs: Any) -> dict | None:
        """Veredicto de un centinela (validadores y evaluador de calidad) en forma lista para la UI."""
        if not isinstance(outputs, dict):
            return None
        if node == "response_evaluator":
            report = outputs.get("eval_report")
            return {"type": "sentinel", "node": node, **report} if report else None
        if node in ("auth_validator", "catalog_checker"):
            items = [
                {"app": r.get("app"), "status": r.get("status"), "reason": r.get("reason") or r.get("message")}
                for r in (outputs.get("validation_reports") or []) if isinstance(r, dict)
            ]
            blocked = any(i["status"] != "ok" for i in items)
            return {"type": "sentinel", "node": node, "action": "blocked" if blocked else "approved", "items": items}
        return None

    def _log_llm(self, run_id, *, response: LLMResult | None = None, usage: dict | None = None, error: str | None = None) -> None:
        """Una llamada a un modelo en el registro del turno: lo que recibio, lo que respondio, cuanto costo y como le fue."""
        call = self._llm_log.pop(run_id, None)
        if self.turn_log is None or call is None:
            return
        output, tool_calls = "", []
        for gen_list in (response.generations if response else []):
            for gen in gen_list:
                output += getattr(gen, "text", "") or ""
                tool_calls += [tc.get("args") for tc in (getattr(getattr(gen, "message", None), "tool_calls", None) or [])]
        if not tool_calls and output.lstrip().startswith("{"):   # salida estructurada devuelta como texto JSON
            try:
                tool_calls = [json.loads(output)]
            except ValueError:
                pass
        self.turn_log.event(
            "llm", node=call["node"], tags=call["tags"], model=call["model"], params=call["params"], attempt=call["attempt"],
            ms=round((time.perf_counter() - call["t0"]) * 1000), messages=call["messages"],
            output=output, structured_output=tool_calls or None,
            usage=({k: usage[k] for k in ("model", "input", "output", "cached", "usd")} if usage else None), error=error,
        )

    async def on_llm_error(self, error: BaseException, *, run_id=None, **kwargs: Any) -> None:
        self._llm_meta.pop(run_id, None)
        self._log_llm(run_id, error=f"{type(error).__name__}: {error}")

    def _record_usage(self, response: LLMResult, run_id) -> None:
        """Tokens y costo reales de una llamada, segun lo que reporta el proveedor (no una estimacion)."""
        node, model = self._llm_meta.pop(run_id, (None, None))
        usage, gen_model = None, None
        for gen_list in response.generations:
            for gen in gen_list:
                msg = getattr(gen, "message", None)
                if msg is not None and getattr(msg, "usage_metadata", None):
                    usage = msg.usage_metadata
                    gen_model = (getattr(msg, "response_metadata", None) or {}).get("model_name")
        if usage is None:
            tu = (response.llm_output or {}).get("token_usage") or {}
            if not tu:
                return
            usage = {"input_tokens": tu.get("prompt_tokens", 0), "output_tokens": tu.get("completion_tokens", 0)}
        model = gen_model or (response.llm_output or {}).get("model_name") or model or "?"
        cached = ((usage.get("input_token_details") or {}).get("cache_read")) or 0
        self.usage_calls.append({
            "node": node, "model": model, "input": usage.get("input_tokens", 0), "output": usage.get("output_tokens", 0),
            "cached": cached, "usd": cost_usd(model, usage.get("input_tokens", 0), usage.get("output_tokens", 0), cached),
        })

    def usage(self) -> dict | None:
        """Resumen del gasto de esta peticion. 'unpriced' cuenta llamadas de un modelo que no esta en la tabla de precios."""
        if not self.usage_calls:
            return None
        priced = [c["usd"] for c in self.usage_calls if c["usd"] is not None]
        return {
            "calls": self.usage_calls,
            "input": sum(c["input"] for c in self.usage_calls),
            "output": sum(c["output"] for c in self.usage_calls),
            "usd": round(sum(priced), 6),
            "unpriced": len(self.usage_calls) - len(priced),
            "agent_version": getattr(self, "agent_version", None),  # que version del agente (codigo+prompts) respondio
        }

    @staticmethod
    def _extract_total_tokens(response: LLMResult) -> int:
        """Real token usage from the LLM response, when the provider exposes it.
        Same extraction logic as debug_ws.py's _ShifuDebugStreamer — mirrors two
        possible shapes across LangChain versions: llm_output.token_usage/usage,
        or AIMessage.usage_metadata."""
        llm_output = response.llm_output or {}
        usage = llm_output.get("token_usage") or llm_output.get("usage")
        if isinstance(usage, dict) and usage.get("total_tokens"):
            return int(usage["total_tokens"])
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
        run_id=None,
        **kwargs: Any,
    ) -> None:
        before = len(self.usage_calls)
        self._record_usage(response, run_id)
        self._log_llm(run_id, response=response, usage=self.usage_calls[-1] if len(self.usage_calls) > before else None)
        run = self._runs.pop(run_id, None)
        if run and run[0] == "llm":
            gen = response.generations[0][0] if response.generations and response.generations[0] else None
            await self.queue.put({"type": "trace", "kind": "llm", "node": run[1],
                                  "ms": round((time.perf_counter() - run[2]) * 1000),
                                  "tokens": self._extract_total_tokens(response),
                                  "prompt": self._short(run[3], 30000), "output": self._short(getattr(gen, "text", ""))})
        if _CHAT_TAG not in (tags or []):
            return
        tokens = self._extract_total_tokens(response)
        if tokens > 0:
            self.total_tokens += tokens


async def _build_input(
    user_id: str,
    conversation_id: str,
    user_text: str,
    model_name: str,
    effort_level: str,
    db,
    ip: str | None,
    plan: str = "free",
    save_user_message: bool = True,
    now_override: str | None = None,
    ui_supported: list | None = None,
    file_ids: list | None = None,
) -> tuple[dict, dict]:
    """Shared input builder for WS and SSE handlers.
    file_ids: archivos subidos antes por POST /api/v1/files; solo entran los del propio usuario.
    save_user_message=False: evento del sistema (p. ej. "ya conecte X"); llega al agente pero no es algo que el usuario escribio.
    now_override: reloj simulado (ISO UTC) para probar memoria con fechas; solo con SHIFU_DEV_UI=1, si no se ignora."""
    current_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if now_override and dev_ui_enabled():
        try:
            parsed = datetime.fromisoformat(str(now_override).replace("Z", "+00:00"))
            current_time = parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            logger.warning("[chat] 'now' ilegible, se usa el reloj real: %r", now_override)
    prefs_block, user_timezone = await load_user_prefs_block(user_id, db)
    user_name = await _load_user_name(user_id, db)
    turn_resources = await file_store.resources(db, user_id, file_ids)
    if save_user_message:
        await save_message(user_id, conversation_id, "user", user_text, db, resources=turn_resources)

    geo = get_geo_from_ip(ip)
    if not user_timezone and geo.timezone:
        user_timezone = geo.timezone

    input_state = {
        "messages":                 [HumanMessage(content=user_text)],
        "user_id":                  user_id,
        "conversation_id":          conversation_id,
        "model_name":               model_name,
        "effort_level":             effort_level,
        "current_time_utc":         current_time,
        "user_timezone":            user_timezone,
        "user_location":            geo.location,
        "user_country_code":        geo.country_code,
        "user_preferences_context": prefs_block,
        "user_name":                user_name,
        "system_event":             not save_user_message,  # aviso de la interfaz, no una respuesta del usuario
        # Acciones de interfaz que este cliente dijo saber pintar y que el plan permite (doc/agente/UI_ACTIONS.md).
        "ui_offer":                 await ui_catalog.offer(ui_supported, plan),
        # Siempre se manda (None si no hay): sin eso el checkpoint repetiria los adjuntos del turno anterior.
        "turn_resources":           turn_resources or None,
    }
    lg_config = {
        "configurable": {"thread_id": conversation_id},
        "recursion_limit": get_recursion_limit(plan),
    }
    return input_state, lg_config


# ── WebSocket /ws/chat ─────────────────────────────────────────────────────────

@router.websocket("/ws/chat")
async def chat_ws(
    websocket: WebSocket,
    token: str = Query(...),
    conversation_id: str = Query(...),
):
    user_id = _decode_jwt(token)
    if not user_id:
        await websocket.close(code=4001, reason="Token inválido")
        return

    await websocket.accept()
    db = websocket.app.state.db
    shifu_graph = getattr(websocket.app.state, "shifu_graph", None)
    redis_client = getattr(websocket.app.state, "redis", None)
    if await _owned_by_other(conversation_id, user_id, db):
        await websocket.close(code=4004, reason="Conversación no encontrada")
        return
    user_plan = await _load_user_plan(user_id, db)
    logger.info("[ShifuWS] connected user=%s conv=%s", user_id, conversation_id)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(_ws_json({"type": "error", "message": "JSON inválido"}))
                continue

            if msg.get("type") == "ping":
                await websocket.send_text(_ws_json({"type": "pong"}))
                continue

            if msg.get("type") != "user_message":
                continue

            user_text = msg.get("text", "").strip()
            if not user_text:
                continue

            model_name = msg.get("model", _DEFAULT_MODEL)
            if model_name not in _ALLOWED_MODELS:
                model_name = _DEFAULT_MODEL
            effort_level = msg.get("effort", _DEFAULT_EFFORT)
            if effort_level not in _ALLOWED_EFFORTS:
                effort_level = _DEFAULT_EFFORT

            if not await check_message_quota(redis_client, user_id, plan=user_plan):
                await websocket.send_text(_ws_json({"type": "error", "message": "Too many messages. Wait a moment and try again."}))
                continue

            if shifu_graph is None:
                await websocket.send_text(_ws_json({"type": "error", "message": "Agent not ready."}))
                continue

            ip = websocket.client.host if websocket.client else None
            input_state, lg_config = await _build_input(
                user_id, conversation_id, user_text, model_name, effort_level, db,
                extract_client_ip(dict(websocket.headers), ip),
                plan=user_plan, ui_supported=msg.get("ui_supported"), file_ids=msg.get("files"),
            )

            queue: asyncio.Queue = asyncio.Queue()
            streamer = _ChatStreamer(queue)
            final_state_holder: dict = {}

            async def run_graph() -> None:
                try:
                    final_state_holder.update(
                        await shifu_graph.ainvoke(
                            input_state, {**lg_config, "callbacks": [streamer]}
                        ) or {}
                    )
                except (WebSocketDisconnect, RuntimeError):
                    raise
                except Exception as exc:
                    logger.error("[ShifuWS] graph error user=%s: %s", user_id, exc, exc_info=True)
                    await queue.put({"type": "error", "message": str(exc)})
                finally:
                    await queue.put(None)  # sentinel

            graph_task = asyncio.create_task(run_graph())

            had_error = False
            while True:
                ev = await queue.get()
                if ev is None:
                    break
                await websocket.send_text(_ws_json(ev))
                if ev.get("type") == "error":
                    had_error = True
                    break

            await graph_task

            if had_error:
                continue

            final_state = final_state_holder
            accumulated = _fix_markdown(streamer.accumulated)
            ui_actions = _build_ui_actions(final_state)
            if accumulated:
                try:
                    await save_message(user_id, conversation_id, "ai", accumulated, db, ui_actions=ui_actions)
                except Exception as exc:
                    logger.error("[ShifuWS] save error conv=%s: %s", conversation_id, exc)

            await websocket.send_text(_ws_json({
                "type":        "done",
                "text":        accumulated,
                "model":       model_name,
                "ui_actions":  ui_actions,
                "workflow_id": final_state.get("req_workflow_id"),
            }))

            sources = final_state.get("retrieved_sources")
            if sources:
                await websocket.send_text(_ws_json({"type": "sources", "data": sources}))

            logger.info("[ShifuWS] done user=%s model=%s len=%d", user_id, model_name, len(accumulated))

    except WebSocketDisconnect:
        logger.info("[ShifuWS] disconnected user=%s conv=%s", user_id, conversation_id)
    except RuntimeError as exc:
        if "not connected" in str(exc).lower() or "accept" in str(exc).lower():
            logger.info("[ShifuWS] client closed abruptly user=%s", user_id)
        else:
            logger.exception("[ShifuWS] unexpected error user=%s: %s", user_id, exc)
    except Exception as exc:
        logger.exception("[ShifuWS] unexpected error user=%s: %s", user_id, exc)


# ── SSE /chat/stream ───────────────────────────────────────────────────────────

@router.post("/chat/stream")
async def chat_stream(request: Request):
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.removeprefix("Bearer ").strip()
    user_id = _decode_jwt(token)
    if not user_id:
        return JSONResponse({"detail": "Token inválido"}, status_code=401)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"detail": "Body JSON inválido"}, status_code=400)

    conversation_id = body.get("conversation_id") or user_id
    user_text = body.get("text", "").strip()
    if not user_text:
        return JSONResponse({"detail": "text es requerido"}, status_code=422)

    model_name = body.get("model", _DEFAULT_MODEL)
    if model_name not in _ALLOWED_MODELS:
        model_name = _DEFAULT_MODEL
    effort_level = body.get("effort", _DEFAULT_EFFORT)
    if effort_level not in _ALLOWED_EFFORTS:
        effort_level = _DEFAULT_EFFORT

    db = request.app.state.db
    redis_client = getattr(request.app.state, "redis", None)
    shifu_graph = getattr(request.app.state, "shifu_graph", None)
    if await _owned_by_other(conversation_id, user_id, db):
        return JSONResponse({"detail": "Conversación no encontrada"}, status_code=404)
    user_plan = await _load_user_plan(user_id, db)

    if not await check_message_quota(redis_client, user_id, plan=user_plan):
        return JSONResponse({"detail": "Too many messages"}, status_code=429)

    if shifu_graph is None:
        return JSONResponse({"detail": "Agent not ready"}, status_code=503)

    client_ip = extract_client_ip(dict(request.headers), request.client.host if request.client else None)
    input_state, lg_config = await _build_input(
        user_id, conversation_id, user_text, model_name, effort_level, db, client_ip,
        plan=user_plan, save_user_message=not body.get("silent"), now_override=body.get("now"),
        ui_supported=body.get("ui_supported"), file_ids=body.get("files"),
    )

    queue: asyncio.Queue = asyncio.Queue()
    version = await agent_version()
    turn_log = trace_log.new_turn({
        "conversation_id": conversation_id, "user_id": user_id, "user_text": user_text, "requested_model": model_name,
        "effort": effort_level, "plan": user_plan, "agent_id": os.getenv("SHIFU_AGENT_ID", "shifu_v1"), "agent_version": version,
    })
    # "trace" devuelve al cliente los prompts completos del sistema: solo con SHIFU_DEV_UI=1 (un usuario real no debe poder pedirlo).
    streamer = _ChatStreamer(queue, trace=bool(body.get("trace")) and dev_ui_enabled(), hold=bool(body.get("hold")), turn_log=turn_log)
    streamer.agent_version = version  # viaja en usage: queda guardado con cada respuesta
    done_event = asyncio.Event()
    turn_end: dict = {"reply": None, "error": None}

    async def run_graph() -> None:
        final_state: dict = {}
        try:
            final_state = await shifu_graph.ainvoke(
                input_state,
                {**lg_config, "callbacks": [streamer]},
            ) or {}
        except Exception as exc:
            logger.error("[ShifuSSE] graph error user=%s: %s", user_id, exc, exc_info=True)
            turn_end["error"] = f"{type(exc).__name__}: {exc}"
            await queue.put({"type": "error", "message": str(exc)})
        else:
            accumulated = _fix_markdown(streamer.accumulated)
            turn_end["reply"] = accumulated
            ui_actions = _build_ui_actions(final_state)  # antes de guardar: el boton tiene que sobrevivir al reabrir la conversacion
            if accumulated:
                try:
                    await save_message(user_id, conversation_id, "ai", accumulated, db, quality=streamer.quality(), usage=streamer.usage(), ui_actions=ui_actions)
                except Exception as exc:
                    logger.error("[ShifuSSE] save error conv=%s: %s", conversation_id, exc)

                # Daily token quota tracking — informational only, never blocks the chat.
                # Prefer the real usage reported by the LLM provider; fall back to a rough
                # chars/4 estimate when the provider/model doesn't expose token_usage.
                tokens = streamer.total_tokens or (len(accumulated) // 4)
                daily_total = await track_daily_tokens(redis_client, user_id, tokens)
                await maybe_get_token_warning(redis_client, user_id, user_plan, daily_total, db=db)
            await queue.put({
                "type":        "done",
                "text":        accumulated,
                "model":       model_name,
                "ui_actions":  ui_actions,
                "workflow_id": final_state.get("req_workflow_id"),
                "quality":     streamer.quality(),
                "usage":       streamer.usage(),
            })

            sources = final_state.get("retrieved_sources")
            if sources:
                await queue.put({"type": "sources", "data": sources})
        finally:
            if turn_log is not None:  # siempre se cierra, tambien si el turno fallo: lo que fallo es justo lo que hay que auditar
                turn_log.finish(
                    reply=turn_end["reply"], error=turn_end["error"], quality=streamer.quality(), usage=streamer.usage(),
                    decisions={k: final_state.get(k) for k in (
                        "semantic_intake_debug", "apps_involved", "validation_reports", "requirement_level", "mood_state",
                        "user_sentiment", "req_level", "eval_report", "active_mandates") if final_state.get(k) is not None},
                )
            await queue.put(None)  # sentinel
            done_event.set()

    graph_task = asyncio.create_task(run_graph())

    async def event_gen():
        try:
            while True:
                ev = await queue.get()
                if ev is None:
                    break
                yield _sse(ev)
        except asyncio.CancelledError:
            graph_task.cancel()
        logger.info("[ShifuSSE] done user=%s model=%s", user_id, model_name)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":   "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
