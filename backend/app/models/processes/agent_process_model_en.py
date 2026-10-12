"""
Agent Process Model - procesos_agente / agent processes.
"""
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Annotated
from bson import ObjectId
from app.models._base import AppBaseModel
from pydantic import Field, ConfigDict, BeforeValidator
PyObjectId = Annotated[str, BeforeValidator(str)]

class AgentStepItem(AppBaseModel):
    step_number: int
    action: str
    result: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class AgentProcessModel(AppBaseModel):
    id: Optional[PyObjectId] = Field(None, alias='_id')
    user_email: str = Field(...)
    agent_id: Optional[str] = None
    name: Optional[str] = Field(None)
    status: str = Field(default='running')
    steps: List[AgentStepItem] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)
