"""
WorkflowRun — execution record for a single run of a workflow.
Collection: workflow_runs

Each run captures the real-time status of every step so the frontend
can display live progress via WebSocket.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from pydantic import Field
from app.models._base import AppBaseModel

WorkflowRunStepStatus = Literal["pending", "running", "completed", "failed", "skipped"]
WorkflowRunStatus = Literal["queued", "running", "completed", "failed", "cancelled"]


class WorkflowRunStep(AppBaseModel):
    order: int
    name: str
    app: str
    action: str
    account_id: str = ""
    config: Dict[str, Any] = Field(default_factory=dict)
    status: WorkflowRunStepStatus = "pending"
    result: Optional[str] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class WorkflowRun(AppBaseModel):
    workflow_id: str
    workflow_name: str
    user_id: str
    user_email: str
    status: WorkflowRunStatus = "queued"
    steps: List[WorkflowRunStep] = Field(default_factory=list)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
