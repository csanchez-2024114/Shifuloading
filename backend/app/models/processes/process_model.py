"""
Process Model - Agent execution trace.
Defines how step sequences and results are stored in MongoDB.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Annotated
from bson import ObjectId
from app.models._base import AppBaseModel
from pydantic import Field, ConfigDict, BeforeValidator
PyObjectId = Annotated[str, BeforeValidator(str)]

class StepModel(AppBaseModel):
    """Represents a step in the execution chain."""
    step_number: int = Field(..., description='Sequential order')
    tool: Optional[str] = Field(None, description='Tool used (None if chat)')
    tool_input: Any = Field(default=None, description='Input sent to the tool')
    observation: str = Field(..., description='Tool or analysis response')
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    model_config = ConfigDict(arbitrary_types_allowed=True, populate_by_name=True)

class ProcessBase(AppBaseModel):
    """Fields shared between temp and confirmed processes."""
    process_name: str = Field(..., description='Descriptive process name')
    user_email: str = Field(..., description="Owner's email")
    user_id: Optional[PyObjectId] = None
    user_input: str = Field(..., description='Original instruction')
    steps: List[StepModel] = Field(default_factory=list)
    total_steps: int = 0
    output: Optional[str] = None
    ai_summary: Optional[str] = None
    processed_apps: List[str] = Field(default_factory=list)
    resource_links: List[Dict[str, str]] = Field(default_factory=list)
    charts_visualization_json: Optional[Dict[str, Any]] = None
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

class ProcessModel(ProcessBase):
    """Model for the 'processes' collection (confirmed)."""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    confirmed_at: Optional[datetime] = None

class ProcessTempModel(ProcessBase):
    """Model for the 'processes_temp' collection (drafts that expire)."""
    status: str = 'PENDING_CONFIRMATION'
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime
    processes_id: Optional[PyObjectId] = None
