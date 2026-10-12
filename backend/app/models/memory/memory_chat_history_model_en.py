"""
Memory Chat History Model - memory_chat_history collection.
"""
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Annotated
from bson import ObjectId
from app.models._base import AppBaseModel
from pydantic import Field, ConfigDict, BeforeValidator
PyObjectId = Annotated[str, BeforeValidator(str)]

class ChatMessageItem(AppBaseModel):
    message_id: str = Field(..., description='Message id or reference')
    role: str = Field(..., description='user|assistant')
    content: str = Field(...)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class MemoryChatHistoryModel(AppBaseModel):
    id: Optional[PyObjectId] = Field(None, alias='_id')
    user_email: str = Field(...)
    session_id: Optional[str] = Field(default=None)
    messages: List[ChatMessageItem] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)
