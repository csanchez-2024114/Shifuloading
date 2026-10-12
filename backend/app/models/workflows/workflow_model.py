"""
Workflow Definition Model.
Stores user-defined automation workflows with state management.
Collection: workflows
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from pydantic import Field
from app.models._base import AppBaseModel

WorkflowStatus = Literal[
    "creating", "active", "paused", "deactivated", "requires_attention"
]


class WorkflowStep(AppBaseModel):
    order: int = Field(..., description="Execution order (1-based)")
    name: str = Field(..., description="Step name")
    description: str = Field(default="", description="What this step does")
    app: str = Field(
        ..., description="Integration provider (e.g. gmail, drive, sheets)"
    )
    account_id: str = Field(
        default="", description="Account ID for multi-account support"
    )
    action: str = Field(
        ..., description="Action to execute (e.g. send_email, create_doc)"
    )
    config: Dict[str, Any] = Field(
        default_factory=dict, description="Action parameters"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Machine-friendly metadata for this workflow step. Useful for AI reasoning and structured filtering.",
    )


class WorkflowModel(AppBaseModel):
    user_id: str
    user_email: str
    name: str
    description: str = ""
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Machine-friendly metadata about the workflow that can be used by the AI without relying on raw user text.",
    )
    status: WorkflowStatus = "creating"
    trigger_type: str = Field(
        default="manual", description="manual | scheduled | event"
    )
    trigger_config: Dict[str, Any] = Field(default_factory=dict)
    steps: List[WorkflowStep] = Field(default_factory=list)
    conversation_id: str = Field(
        default="", description="Conversation that built this workflow"
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    confirmed_at: Optional[datetime] = None
