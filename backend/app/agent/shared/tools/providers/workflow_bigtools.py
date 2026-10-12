from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, List, Optional, Type, Dict
import json

from pydantic import BaseModel, Field

from app.services.workflow_service import (
    list_user_workflows,
    get_workflow_by_id,
    update_workflow_status,
    update_workflow_metrics,
    update_workflow_webhook,
    delete_workflow,
    set_draft_conversation,
)
from app.services.workflow_service import (
    create_workflow,
    add_step_to_workflow,
    get_current_draft,
    remove_step_from_workflow,
    replace_step_in_workflow,
    set_workflow_frequency,
    update_workflow_metadata,
    WorkflowLimitExceededError,
    WorkflowAppsLimitExceededError,
)
from app.services.scheduled_task_service import (
    create_scheduled_task,
    list_user_tasks,
    pause_task,
    resume_task,
    delete_task,
)
from app.core.mongo import mongo_manager
from config import Config
from app.utils.events import publish_user_event


@dataclass
class BigTool:
    name: str
    description: str
    tool: Any
    args_schema: Optional[Type[BaseModel]] = None


class WorkflowIdInput(BaseModel):
    workflow_id: str = Field(description="Workflow ID (MongoDB ObjectId)")


class DeleteWorkflowInput(BaseModel):
    workflow_id: str = Field(description="Workflow ID (MongoDB ObjectId)")
    confirm: bool = Field(
        default=False,
        description=(
            "Set to true only after the user has explicitly confirmed they want to delete the workflow. "
            "The tool will refuse to delete without this confirmation."
        ),
    )


class CreateWorkflowInput(BaseModel):
    name: str = Field(..., description="Workflow name (e.g. 'Weekly report')")
    description: str = Field(default="", description="Optional description")


class AddStepInput(BaseModel):
    order: int = Field(..., description="Step order number (starts at 1)")
    name: str = Field(..., description="Step human-readable name shown in the UI")
    type: str = Field(
        default="action",
        description=(
            "Step type: 'action' (default, calls a single tool), "
            "'foreach' (iterates a JSON array and calls action for each item), "
            "'condition' (evaluates a field and optionally stops remaining steps)."
        ),
    )
    app: str = Field(
        default="",
        description="Integration name (e.g. 'gmail', 'slides', 'google_sheets')",
    )
    action: str = Field(
        default="",
        description=(
            "MUST be the EXACT BigTool name returned by consultar_herramientas_disponibles "
            "(e.g. 'listar_correos', 'create_presentation', 'insert_text_in_presentation'). "
            "NEVER invent an action name — copy it verbatim from the tool list. "
            "Leave empty for 'condition' steps (they don't call a tool)."
        ),
    )
    source: str = Field(
        default="",
        description=(
            "Template variable pointing to the data source for 'foreach' and 'condition' steps. "
            "Examples: '{{step_1}}' (full output of step 1), '{{step_2.items}}' (field from step 2). "
            "Leave empty for 'action' steps."
        ),
    )
    description: str = Field(
        default="", description="Human-readable description of what this step does"
    )
    account_id: str = Field(
        default="", description="Account id for multi-account setups"
    )
    config: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Config dict with ALL required_config fields for this action "
            "(use the field names exactly as shown in required_config from consultar_herramientas_disponibles). "
            "For fields whose value comes from a previous step's output at runtime, "
            "use the template: '{{step_N.field}}' where N=step order, field=JSON key "
            "(e.g. '{{step_1.id}}' to use the ID returned by step 1). "
            "For 'foreach' steps, use '{{item.field}}' to reference each item's fields. "
            "For 'condition' steps, use: field (str), operator ('eq'/'neq'/'gt'/'lt'/'contains'), "
            "value (the expected value), on_false ('stop' to halt remaining steps). "
            "NEVER leave required_config fields empty or omit them — the workflow WILL fail."
        ),
    )
    max_retries: int = Field(
        default=0,
        description="Number of retry attempts on failure (0 = no retry). Delay doubles each attempt.",
    )
    retry_delay: float = Field(
        default=1.0,
        description="Initial delay in seconds between retries (doubles each attempt via exponential backoff).",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Structured metadata for this workflow step. "
            "Use this to store AI-friendly facts about the step that are not part of the raw user prompt."
        ),
    )


class SetWorkflowMetadataInput(BaseModel):
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Arbitrary structured metadata for the active workflow draft. "
            "This metadata can be used by AI to reason without relying on raw user text."
        ),
    )


class ConfigureMetricsInput(BaseModel):
    metrics: List[Dict[str, Any]] = Field(
        ...,
        description=(
            "List of metric extraction rules. Each entry: "
            "{'key': 'metric_name', 'source': 'step_N', 'field': 'json_field', 'label': 'Human label'}. "
            "'source' must be 'step_N' where N is the step order. "
            "'field' is the JSON key to extract from that step's result (leave empty to use the full result). "
            "Example: [{'key': 'emails_count', 'source': 'step_1', 'field': 'total', 'label': 'Emails procesados'}]"
        ),
    )
    charts: List[Dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "List of chart configurations for the dashboard. Each entry: "
            "{'id': 'unique_id', 'type': 'line|bar|pie|area', 'title': 'Chart title', "
            "'metric_key': 'key_from_metrics', 'icon': 'LucideIconName', 'iconColor': 'text-blue-600', 'w': 3, 'h': 3}. "
            "type 'line': tracks a numeric metric over time (best for counts, totals). "
            "type 'pie': shows distribution of a categorical metric (JSON dict of {category: count}). "
            "type 'bar': compares two metrics per run using 'metric_key' as 'key1|key2'. "
            "Example: [{'id': 'emails', 'type': 'line', 'title': 'Emails Procesados', 'metric_key': 'emails_count', 'icon': 'Mail', 'iconColor': 'text-blue-600'}]"
        ),
    )


class ConfigureWebhookInput(BaseModel):
    webhook_url: str = Field(
        ...,
        description=(
            "HTTPS URL to POST after every workflow run. "
            "The payload includes: event, workflow_id, run_id, status, metrics, duration_ms, timestamp. "
            "Leave empty to disable. Example: 'https://your-app.com/webhooks/workflow'"
        ),
    )


class StepOrderInput(BaseModel):
    step_order: int = Field(..., description="Order number of step to delete")


class ModifyStepInput(BaseModel):
    step_order: int = Field(..., description="Order number of the step to modify")
    name: str = Field(..., description="New step name")
    app: str = Field(..., description="Integration to use")
    action: str = Field(..., description="Action name to execute")
    description: str = Field(default="", description="Step description")
    account_id: str = Field(default="", description="Account id for multi-account")
    config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Required parameters for this action (same as AddStepInput.config).",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Structured metadata for this workflow step. Useful for AI reasoning and annotations.",
    )


class ScheduleWorkflowInput(BaseModel):
    workflow_id: str = Field(
        default="", description="Workflow ID to schedule; leave empty to error"
    )
    schedule_type: str = Field(..., description="'once' or 'interval'")
    every_seconds: int = Field(default=3600)
    run_at: str = Field(default="")
    max_runs: Optional[int] = Field(default=None)
    start_at: str = Field(default="")


class SetFrequencyInput(BaseModel):
    frequency_type: str = Field(
        ...,
        description=(
            "Canonical frequency type. Must be one of: "
            "'every_3m' (3 min), 'every_5m' (5 min), 'every_15m', 'hourly', 'every_4h', "
            "'daily', 'weekly', 'monthly', 'once'."
        ),
    )
    every_seconds: int = Field(
        default=0,
        description=(
            "Interval in seconds derived from frequency_type. "
            "Use 0 for 'once'. "
            "every_3m→180, every_5m→300, every_15m→900, hourly→3600, every_4h→14400, "
            "daily→86400, weekly→604800, monthly→2592000."
        ),
    )
    frequency_label: str = Field(
        ...,
        description="Human-readable label in Spanish, e.g. 'Cada hora', 'Diario', 'Una sola vez'.",
    )


class TaskIdInput(BaseModel):
    task_id: str = Field(..., description="Task ID for schedule operations")


def _resolve_user_id(user_email: str, db) -> Optional[str]:
    """Resolve user_id synchronously by querying the DB inside the async tool call.
    This helper returns None here; each tool will lookup the user_id when executed.
    """
    # Intentionally left as a stub; resolution happens inside async tools where `db` is available.
    return None


def get_workflow_bigtools(
    user_email: str,
    db=None,
    active_accounts: Optional[Dict[str, str]] = None,
    conversation_id: Optional[str] = None,
) -> List[BigTool]:
    """Factory que expone herramientas de workflows a nivel de usuario.

    Nota: las funciones devueltas son coroutines que usarán `db` en tiempo de ejecución
    para resolver `user_id` a partir de `user_email`.
    """

    async def _list_my_workflows() -> str:
        if db is None:
            return json.dumps({"error": "DB not available"})
        user = await db["users"].find_one(
            {"$or": [{"correo": user_email}, {"email": user_email}]}
        )
        if not user:
            return json.dumps({"status": "not_found", "message": "User not found"})
        user_id = str(user["_id"])
        wfs = await list_user_workflows(user_id, db)
        if not wfs:
            return json.dumps({"status": "empty", "message": "No workflows yet."})
        return json.dumps(wfs, ensure_ascii=False, default=str)

    async def _view_workflow(workflow_id: str) -> str:
        if db is None:
            return json.dumps({"error": "DB not available"})
        user = await db["users"].find_one(
            {"$or": [{"correo": user_email}, {"email": user_email}]}
        )
        if not user:
            return json.dumps({"status": "not_found", "message": "User not found"})
        user_id = str(user["_id"])
        wf = await get_workflow_by_id(user_id, workflow_id, db)
        if not wf:
            return json.dumps(
                {
                    "status": "not_found",
                    "message": f"Workflow '{workflow_id}' not found.",
                }
            )
        return json.dumps(wf, ensure_ascii=False, default=str)

    async def _create_workflow(name: str, description: str = "") -> str:
        if db is None:
            return json.dumps({"error": "DB not available"})
        user = await db["users"].find_one(
            {"$or": [{"correo": user_email}, {"email": user_email}]}
        )
        if not user:
            return json.dumps({"error": "User not found"})
        user_id = str(user["_id"])
        try:
            wf_id = await create_workflow(
                user_id, user_email, name, description, conversation_id or "", db
            )
        except WorkflowLimitExceededError as exc:
            return json.dumps(
                {
                    "error": "workflow_limit_exceeded",
                    "message": f"Tu plan permite hasta {exc.limit} workflows activos. Desactiva alguno o mejora tu plan.",
                }
            )
        event = {
            "type": "workflow_creating",
            "workflow_id": wf_id,
            "workflow_name": name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await publish_user_event(user_id, event)
        return json.dumps(
            {
                "status": "created",
                "workflow_id": wf_id,
                "message": f"Draft '{name}' created.",
            }
        )

    async def _set_frequency(
        frequency_type: str,
        every_seconds: int = 0,
        frequency_label: str = "",
    ) -> str:
        """Store the inferred frequency intent on the active draft workflow."""
        if db is None:
            return json.dumps({"error": "DB not available"})
        user = await db["users"].find_one(
            {"$or": [{"correo": user_email}, {"email": user_email}]}
        )
        if not user:
            return json.dumps({"error": "User not found"})
        user_id = str(user["_id"])
        draft = await get_current_draft(user_id, conversation_id or "", db)
        if not draft:
            return json.dumps(
                {"error": "No active draft found. Create a workflow first."}
            )
        secs = every_seconds if every_seconds > 0 else None
        ok = await set_workflow_frequency(
            draft["_id"], frequency_type, secs, frequency_label, db
        )
        return json.dumps(
            {
                "status": "ok" if ok else "not_modified",
                "workflow_id": draft["_id"],
                "frequency_type": frequency_type,
                "every_seconds": secs,
                "frequency_label": frequency_label,
            }
        )

    async def _add_step(
        order: int,
        name: str,
        type: str = "action",
        app: str = "",
        action: str = "",
        source: str = "",
        description: str = "",
        account_id: str = "",
        config: Dict[str, Any] = None,
        max_retries: int = 0,
        retry_delay: float = 1.0,
        metadata: Dict[str, Any] = None,
    ) -> str:
        if db is None:
            return json.dumps({"error": "DB not available"})
        user = await db["users"].find_one(
            {"$or": [{"correo": user_email}, {"email": user_email}]}
        )
        if not user:
            return json.dumps({"error": "User not found"})
        user_id = str(user["_id"])
        draft = await get_current_draft(user_id, conversation_id or "", db)
        if not draft:
            return json.dumps(
                {"error": "No active draft in this conversation. Create one first."}
            )
        # Guard: reject action steps with no config for write/create/send actions.
        # Read/list actions with all-optional args (listar_correos, etc.) are allowed to have empty config.
        resolved_config = config or {}
        action_lower = (action or "").lower()
        # AI-step recovery: an AI step almost always transforms the PREVIOUS step's
        # output. If the LLM left config empty, auto-fill the obvious 'text' input so
        # the build never stalls. ai_extract/ai_classify second field is optional now.
        if (
            not resolved_config
            and action_lower.startswith("ai_")
            and isinstance(order, int)
            and order > 1
        ):
            resolved_config = {"text": f"{{{{step_{order - 1}}}}}"}
        _READ_PREFIXES = ("listar", "list_", "ver_", "view_", "get_", "obtener_", "buscar_correos_por")
        is_read_action = any(action_lower.startswith(p) for p in _READ_PREFIXES)
        if type == "action" and not resolved_config and not is_read_action:
            hints: list[str] = []
            # AI processing steps — exact required fields per action
            _AI_ACTION_FIELDS = {
                "ai_summarize": ["'text': '{{step_N}}'  (text to summarize)"],
                "ai_transform": ["'text': '{{step_N}}'", "'instruction': '<how to transform/translate/rewrite>'"],
                "ai_extract": ["'text': '{{step_N}}'  (source text)", "'fields': 'name, email, empresa, asunto'  (comma-separated field names)"],
                "ai_classify": ["'text': '{{step_N}}'", "'categories': 'urgente, normal, spam'  (comma-separated)"],
                "ai_generate": ["'instruction': '<what to generate>'"],
                "ai_filter": ["'items': '{{step_N}}'  (JSON array)", "'criteria': '<filter rule>'"],
                "ai_decide": ["'context': '{{step_N}}'", "'question': '<yes/no question>'"],
            }
            if action_lower in _AI_ACTION_FIELDS:
                hints.extend(_AI_ACTION_FIELDS[action_lower])
            if "tavily" in action_lower or "search" in action_lower:
                hints.append(
                    "'query': '<search string>'  (e.g. 'precio del dólar hoy')"
                )
            if (
                "sheet" in action_lower
                or "append" in action_lower
                or "row" in action_lower
            ):
                hints.append(
                    "'spreadsheet_id': '<the sheet ID>' — if you don't have it, FIRST call "
                    "search_sheets_files('<sheet name the user gave>') to get it, then use that id here"
                )
                hints.append(
                    "'values': ['{{step_N.field}}', ...] — one entry per column, "
                    "referencing the fields from the previous extract step"
                )
            if "enviar" in action_lower or "send" in action_lower or "correo" in action_lower:
                hints.append("'to': '<email address>'")
                hints.append("'subject': '<email subject>'")
                hints.append("'body': '<email body or {{step_N.field}}>'")
            if "buscar" in action_lower:
                hints.append("'query': '<search string>'")
            hint_str = (
                " Put these fields INSIDE the 'config' dict (NOT at the top level of the tool call):\n"
                "  config = {\n    " + ",\n    ".join(hints) + "\n  }"
                if hints
                else " Call consultar_herramientas_disponibles first to get the required_config fields, then fill them all inside config."
            )
            return json.dumps(
                {
                    "error": (
                        f"STEP REJECTED — config is empty for action '{action}'. "
                        f"The executor will fail with 'Field required' at runtime. "
                        f"Retry agregar_paso_workflow with the SAME order/name/action but a filled 'config' dict.\n{hint_str}"
                    )
                }
            )

        step: Dict[str, Any] = {
            "order": order,
            "type": type,
            "name": name,
            "description": description,
            "app": app,
            "account_id": account_id,
            "action": action,
            "config": resolved_config,
        }
        if source:
            step["source"] = source
        if max_retries > 0:
            step["max_retries"] = max_retries
            step["retry_delay"] = retry_delay
        if metadata:
            step["metadata"] = metadata
        try:
            ok = await add_step_to_workflow(draft["_id"], step, db)
        except WorkflowAppsLimitExceededError as exc:
            return json.dumps(
                {
                    "error": "apps_per_workflow_limit_exceeded",
                    "message": f"Tu plan permite hasta {exc.limit} apps distintas en un mismo workflow. Simplifica este workflow o mejora tu plan.",
                }
            )
        if not ok:
            return json.dumps({"error": "Could not add the step."})
        event = {
            "type": "workflow_step_added",
            "workflow_id": draft["_id"],
            "step_order": order,
            "step": step,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await publish_user_event(user_id, event)
        return json.dumps(
            {"status": "step_added", "workflow_id": draft["_id"], "step_order": order}
        )

    async def _view_draft() -> str:
        if db is None:
            return json.dumps({"error": "DB not available"})
        user = await db["users"].find_one(
            {"$or": [{"correo": user_email}, {"email": user_email}]}
        )
        if not user:
            return json.dumps({"status": "not_found", "message": "User not found"})
        user_id = str(user["_id"])
        draft = await get_current_draft(user_id, conversation_id or "", db)
        if not draft:
            return json.dumps(
                {
                    "status": "no_draft",
                    "message": "No active draft in this conversation.",
                }
            )
        return json.dumps(draft, ensure_ascii=False, default=str)

    async def _confirm_workflow() -> str:
        if db is None:
            return json.dumps({"error": "DB not available"})
        user = await db["users"].find_one(
            {"$or": [{"correo": user_email}, {"email": user_email}]}
        )
        if not user:
            return json.dumps({"error": "User not found"})
        user_id = str(user["_id"])
        draft = await get_current_draft(user_id, conversation_id or "", db)
        if not draft:
            return json.dumps({"error": "No active draft. Create a workflow first."})
        ok = await update_workflow_status(
            draft["_id"],
            "active",
            db,
            extra={"confirmed_at": datetime.now(timezone.utc)},
        )
        if not ok:
            return json.dumps({"error": "Could not confirm the workflow."})
        event = {
            "type": "workflow_confirmed",
            "workflow_id": draft["_id"],
            "workflow_name": draft.get("name"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await publish_user_event(user_id, event)
        return json.dumps(
            {
                "status": "confirmed",
                "workflow_id": draft["_id"],
                "name": draft.get("name"),
            }
        )

    async def _set_workflow_metadata(metadata: Dict[str, Any]) -> str:
        if db is None:
            return json.dumps({"error": "DB not available"})
        user = await db["users"].find_one(
            {"$or": [{"correo": user_email}, {"email": user_email}]}
        )
        if not user:
            return json.dumps({"error": "User not found"})
        user_id = str(user["_id"])
        draft = await get_current_draft(user_id, conversation_id or "", db)
        if not draft:
            return json.dumps(
                {"error": "No active draft in this conversation. Create one first."}
            )
        ok = await update_workflow_metadata(draft["_id"], metadata, db)
        return json.dumps(
            {
                "status": "metadata_updated" if ok else "error",
                "workflow_id": draft["_id"],
                "metadata": metadata,
            },
            ensure_ascii=False,
        )

    async def _delete_step(step_order: int) -> str:
        if db is None:
            return json.dumps({"error": "DB not available"})
        user = await db["users"].find_one(
            {"$or": [{"correo": user_email}, {"email": user_email}]}
        )
        if not user:
            return json.dumps({"error": "User not found"})
        user_id = str(user["_id"])
        draft = await get_current_draft(user_id, conversation_id or "", db)
        if not draft:
            return json.dumps({"error": "No active draft."})
        ok = await remove_step_from_workflow(draft["_id"], step_order, db)
        return json.dumps(
            {"status": "step_deleted" if ok else "error", "step_order": step_order}
        )

    async def _modify_step(
        step_order: int,
        name: str,
        app: str,
        action: str,
        description: str = "",
        account_id: str = "",
        config: Dict[str, Any] = None,
        metadata: Dict[str, Any] = None,
    ) -> str:
        if db is None:
            return json.dumps({"error": "DB not available"})
        user = await db["users"].find_one(
            {"$or": [{"correo": user_email}, {"email": user_email}]}
        )
        if not user:
            return json.dumps({"error": "User not found"})
        user_id = str(user["_id"])
        draft = await get_current_draft(user_id, conversation_id or "", db)
        if not draft:
            return json.dumps({"error": "No active draft."})
        resolved_config = config or {}
        if not resolved_config:
            return json.dumps(
                {
                    "error": (
                        f"STEP REJECTED — config is empty for action '{action}'. "
                        f"Fill all required_config fields before calling reemplazar_paso_workflow."
                    )
                }
            )
        new_step = {
            "order": step_order,
            "name": name,
            "description": description,
            "app": app,
            "account_id": account_id,
            "action": action,
            "config": resolved_config,
        }
        if metadata:
            new_step["metadata"] = metadata
        ok = await replace_step_in_workflow(draft["_id"], step_order, new_step, db)
        return json.dumps(
            {"status": "step_modified" if ok else "error", "step_order": step_order}
        )

    async def _edit_workflow(workflow_id: str) -> str:
        if db is None:
            return json.dumps({"error": "DB not available"})
        user = await db["users"].find_one(
            {"$or": [{"correo": user_email}, {"email": user_email}]}
        )
        if not user:
            return json.dumps({"error": "User not found"})
        user_id = str(user["_id"])
        ok = await set_draft_conversation(workflow_id, conversation_id or "", db)
        if not ok:
            return json.dumps({"error": f"Workflow '{workflow_id}' not found."})
        wf = await get_workflow_by_id(user_id, workflow_id, db)
        return json.dumps(
            {"status": "editing", "workflow_id": workflow_id, "workflow": wf},
            ensure_ascii=False,
            default=str,
        )

    async def _pause_workflow(workflow_id: str) -> str:
        if db is None:
            return json.dumps({"error": "DB not available"})
        user = await db["users"].find_one(
            {"$or": [{"correo": user_email}, {"email": user_email}]}
        )
        if not user:
            return json.dumps({"error": "User not found"})
        user_id = str(user["_id"])
        ok = await update_workflow_status(workflow_id, "paused", db)
        # publish event
        event = {"type": "workflow_paused", "workflow_id": workflow_id}
        await publish_user_event(user_id, event)
        return json.dumps(
            {"status": "paused" if ok else "error", "workflow_id": workflow_id}
        )

    async def _reactivate_workflow(workflow_id: str) -> str:
        if db is None:
            return json.dumps({"error": "DB not available"})
        user = await db["users"].find_one(
            {"$or": [{"correo": user_email}, {"email": user_email}]}
        )
        if not user:
            return json.dumps({"error": "User not found"})
        user_id = str(user["_id"])
        ok = await update_workflow_status(workflow_id, "active", db)
        event = {"type": "workflow_reactivated", "workflow_id": workflow_id}
        await publish_user_event(user_id, event)
        return json.dumps(
            {"status": "active" if ok else "error", "workflow_id": workflow_id}
        )

    async def _delete_workflow(workflow_id: str, confirm: bool = False) -> str:
        if db is None:
            return json.dumps({"error": "DB not available"})
        if not confirm:
            return json.dumps(
                {
                    "error": (
                        "Delete prevented. Please ask the user to confirm before deleting this workflow. "
                        "Call eliminar_workflow again with confirm=true once the user approves."
                    ),
                    "workflow_id": workflow_id,
                }
            )
        user = await db["users"].find_one(
            {"$or": [{"correo": user_email}, {"email": user_email}]}
        )
        if not user:
            return json.dumps({"error": "User not found"})
        user_id = str(user["_id"])
        ok = await delete_workflow(user_id, workflow_id, db)
        if ok:
            await publish_user_event(
                user_id,
                {
                    "type": "workflow_deleted",
                    "workflow_id": workflow_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
        return json.dumps(
            {"status": "deleted" if ok else "error", "workflow_id": workflow_id}
        )

    async def _schedule_workflow(
        workflow_id: str,
        schedule_type: str = "interval",
        every_seconds: int = 3600,
        run_at: str = "",
        max_runs: Optional[int] = None,
        start_at: str = "",
    ) -> str:
        if db is None:
            return json.dumps({"error": "DB not available"})
        user = await db["users"].find_one(
            {"$or": [{"correo": user_email}, {"email": user_email}]}
        )
        if not user:
            return json.dumps({"error": "User not found"})
        user_id = str(user["_id"])
        # build schedule_config
        if schedule_type == "once":
            schedule_config = {"run_at": run_at or None}
        else:
            schedule_config = {
                "every_seconds": max(60, every_seconds),
                "max_runs": max_runs,
                "start_at": start_at or None,
            }
        task_id = await create_scheduled_task(
            user_id=user_id,
            user_email=user_email,
            workflow_id=workflow_id,
            name="scheduled_workflow",
            schedule_type=schedule_type,
            schedule_config=schedule_config,
            db=db,
        )
        return json.dumps(
            {"status": "scheduled", "task_id": task_id, "workflow_id": workflow_id}
        )

    async def _list_schedules() -> str:
        if db is None:
            return json.dumps({"error": "DB not available"})
        user = await db["users"].find_one(
            {"$or": [{"correo": user_email}, {"email": user_email}]}
        )
        if not user:
            return json.dumps({"error": "User not found"})
        user_id = str(user["_id"])
        tasks = await list_user_tasks(user_id, db)
        if not tasks:
            return json.dumps({"status": "empty", "message": "No scheduled tasks."})
        return json.dumps(tasks, ensure_ascii=False, default=str)

    async def _pause_schedule(task_id: str) -> str:
        if db is None:
            return json.dumps({"error": "DB not available"})
        ok = await pause_task(task_id, db)
        return json.dumps({"status": "paused" if ok else "error", "task_id": task_id})

    async def _resume_schedule(task_id: str) -> str:
        if db is None:
            return json.dumps({"error": "DB not available"})
        ok = await resume_task(task_id, db)
        return json.dumps({"status": "resumed" if ok else "error", "task_id": task_id})

    async def _delete_schedule(task_id: str) -> str:
        if db is None:
            return json.dumps({"error": "DB not available"})
        ok = await delete_task(task_id, db)
        return json.dumps({"status": "deleted" if ok else "error", "task_id": task_id})

    async def _configure_metrics(
        metrics: List[Dict[str, Any]],
        charts: List[Dict[str, Any]] = None,
    ) -> str:
        if db is None:
            return json.dumps({"error": "DB not available"})
        user = await db["users"].find_one(
            {"$or": [{"correo": user_email}, {"email": user_email}]}
        )
        if not user:
            return json.dumps({"error": "User not found"})
        user_id = str(user["_id"])
        draft = await get_current_draft(user_id, conversation_id or "", db)
        if not draft:
            return json.dumps({"error": "No active draft. Create a workflow first."})
        ok = await update_workflow_metrics(draft["_id"], metrics, db)
        if charts and ok:
            from bson import ObjectId

            await db["workflows"].update_one(
                {"_id": ObjectId(draft["_id"])},
                {"$set": {"charts": charts or []}},
            )
        return json.dumps(
            {
                "status": "metrics_configured" if ok else "error",
                "workflow_id": draft["_id"],
                "metrics_count": len(metrics),
                "charts_count": len(charts or []),
            }
        )

    async def _configure_webhook(webhook_url: str) -> str:
        if db is None:
            return json.dumps({"error": "DB not available"})
        user = await db["users"].find_one(
            {"$or": [{"correo": user_email}, {"email": user_email}]}
        )
        if not user:
            return json.dumps({"error": "User not found"})
        user_id = str(user["_id"])
        draft = await get_current_draft(user_id, conversation_id or "", db)
        if not draft:
            return json.dumps({"error": "No active draft. Create a workflow first."})
        ok = await update_workflow_webhook(draft["_id"], webhook_url, db)
        return json.dumps(
            {
                "status": "webhook_configured" if ok else "error",
                "workflow_id": draft["_id"],
                "webhook_url": webhook_url,
            }
        )

    return [
        BigTool(
            name="crear_workflow",
            description="Creates a new draft workflow linked to this conversation.",
            tool=_create_workflow,
            args_schema=CreateWorkflowInput,
        ),
        BigTool(
            name="agregar_paso_workflow",
            description="Adds a step to the active draft workflow.",
            tool=_add_step,
            args_schema=AddStepInput,
        ),
        BigTool(
            name="ver_borrador_workflow",
            description="Shows the current draft workflow for this conversation.",
            tool=_view_draft,
        ),
        BigTool(
            name="confirmar_workflow",
            description="Activates the draft workflow (confirm).",
            tool=_confirm_workflow,
        ),
        BigTool(
            name="eliminar_paso_workflow",
            description="Removes a step from the active draft.",
            tool=_delete_step,
            args_schema=StepOrderInput,
        ),
        BigTool(
            name="reemplazar_paso_workflow",
            description="Replaces an existing step in the active draft.",
            tool=_modify_step,
            args_schema=ModifyStepInput,
        ),
        BigTool(
            name="editar_workflow",
            description="Loads an existing workflow for editing in this conversation.",
            tool=_edit_workflow,
            args_schema=WorkflowIdInput,
        ),
        BigTool(
            name="listar_mis_workflows",
            description="Lists user's workflows.",
            tool=_list_my_workflows,
        ),
        BigTool(
            name="ver_workflow",
            description="Get workflow by id.",
            tool=_view_workflow,
            args_schema=WorkflowIdInput,
        ),
        BigTool(
            name="pausar_workflow",
            description="Pause a workflow.",
            tool=_pause_workflow,
            args_schema=WorkflowIdInput,
        ),
        BigTool(
            name="reactivar_workflow",
            description="Reactivate a workflow.",
            tool=_reactivate_workflow,
            args_schema=WorkflowIdInput,
        ),
        BigTool(
            name="eliminar_workflow",
            description=(
                "Deletes a workflow only after explicit user confirmation. "
                "Call this with confirm=true once the user has approved the deletion."
            ),
            tool=_delete_workflow,
            args_schema=DeleteWorkflowInput,
        ),
        BigTool(
            name="fijar_frecuencia_workflow",
            description=(
                "Stores the inferred frequency intent on the active draft workflow. "
                "Call this during Phase 1, right after crear_workflow, "
                "to record how often the workflow should run based on its purpose."
            ),
            tool=_set_frequency,
            args_schema=SetFrequencyInput,
        ),
        BigTool(
            name="programar_workflow",
            description="Schedule a workflow.",
            tool=_schedule_workflow,
            args_schema=ScheduleWorkflowInput,
        ),
        BigTool(
            name="listar_programaciones_workflow",
            description="List scheduled tasks.",
            tool=_list_schedules,
        ),
        BigTool(
            name="pausar_programacion",
            description="Pause scheduled task.",
            tool=_pause_schedule,
            args_schema=TaskIdInput,
        ),
        BigTool(
            name="reanudar_programacion",
            description="Resume scheduled task.",
            tool=_resume_schedule,
            args_schema=TaskIdInput,
        ),
        BigTool(
            name="eliminar_programacion",
            description="Delete scheduled task.",
            tool=_delete_schedule,
            args_schema=TaskIdInput,
        ),
        BigTool(
            name="configurar_metadata_workflow",
            description=(
                "Stores structured metadata on the active draft workflow. "
                "REQUIRED at Phase 2 start: call with plan_steps=[{order,desc,produces},...] to anchor your Phase 1 plan — "
                "this is the build checklist you compare against at step 10 (ver_borrador_workflow). "
                "Also used for workflow tags, step categories, or any AI-friendly annotation fields."
            ),
            tool=_set_workflow_metadata,
            args_schema=SetWorkflowMetadataInput,
        ),
        BigTool(
            name="configurar_metricas_workflow",
            description=(
                "Sets the metrics extraction schema and chart configuration on the active draft workflow. "
                "Call AFTER confirming the workflow, when the user asks to track data or see analytics. "
                "Defines what step outputs to capture as dashboard metrics and how to visualize them."
            ),
            tool=_configure_metrics,
            args_schema=ConfigureMetricsInput,
        ),
        BigTool(
            name="configurar_webhook_workflow",
            description=(
                "Sets an HTTP webhook URL on the active draft workflow. "
                "After every run, the executor will POST a JSON payload to this URL "
                "with: event, workflow_id, run_id, status, metrics, duration_ms, timestamp."
            ),
            tool=_configure_webhook,
            args_schema=ConfigureWebhookInput,
        ),
    ]
