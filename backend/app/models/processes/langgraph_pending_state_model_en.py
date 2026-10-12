"""
LangGraph Pending State Model - langgraph_pending_states collection.
"""
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Annotated
from bson import ObjectId
from app.models._base import AppBaseModel
from pydantic import Field, ConfigDict, BeforeValidator
PyObjectId = Annotated[str, BeforeValidator(str)]

class LangGraphPendingStateModel(AppBaseModel):
    id: Optional[PyObjectId] = Field(None, alias='_id')
    session_id: str = Field(...)
    state: Dict[str, Any] = Field(default_factory=dict)
    attempts: int = Field(default=0)
    expires_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)
