"""
Memory Chat Summary Model - memory_chat_summaries collection.
"""
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Annotated
from bson import ObjectId
from app.models._base import AppBaseModel
from pydantic import Field, ConfigDict, BeforeValidator
PyObjectId = Annotated[str, BeforeValidator(str)]

class MemoryChatSummaryModel(AppBaseModel):
    id: Optional[PyObjectId] = Field(None, alias='_id')
    user_email: str = Field(...)
    session_id: Optional[str] = None
    summary: str = Field(...)
    summary_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = Field(default_factory=dict)
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)
