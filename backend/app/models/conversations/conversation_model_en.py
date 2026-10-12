"""
Conversation and Message Models (EN) - Pydantic V2.
English field names with aliases to support legacy Spanish DB fields.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Annotated
from bson import ObjectId
from app.models._base import AppBaseModel
from pydantic import Field, ConfigDict, BeforeValidator
PyObjectId = Annotated[str, BeforeValidator(str)]

class ResourceModelEN(AppBaseModel):
    """Attachment model for chat messages."""
    type: str = Field(..., description='image, link, file, video')
    url: str = Field(..., description='Secure URL')
    title: Optional[str] = None
    provider: str = Field(default='Others', description='Google Drive, Dropbox, Gmail, etc.')
    file_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    model_config = ConfigDict(populate_by_name=True, json_schema_extra={'example': {'type': 'file', 'url': 'https://drive.google.com/...', 'title': 'Report.pdf', 'provider': 'Google Drive'}})

class MessageModelEN(AppBaseModel):
    conversation_id: PyObjectId = Field(..., description='Parent conversation id')
    role: str = Field(..., description='user or assistant')
    content: str = Field(..., description='Message text')
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None
    tokens_used: Optional[int] = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)
    resources: List[ResourceModelEN] = Field(default_factory=list)
    user_feedback: Optional[str] = None
    model_config = ConfigDict(arbitrary_types_allowed=True)

class ConversationModelEN(AppBaseModel):
    user_id: PyObjectId = Field(..., description='Owner of the conversation')
    title: str = Field(..., description='AI-generated title')
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    message_count: int = Field(default=0)
    last_message_preview: Optional[str] = Field(default=None)
    is_pinned: bool = Field(default=False)
    is_archived: bool = Field(default=False)
    model_used: str = Field(default='gpt-4o-mini')
    temperature: float = Field(default=0.0)
    tags: List[str] = Field(default_factory=list)
    model_config = ConfigDict(arbitrary_types_allowed=True, json_schema_extra={'example': {'title': 'Sales Q1 Analysis', 'message_count': 5, 'model_used': 'gpt-4o-mini'}})
