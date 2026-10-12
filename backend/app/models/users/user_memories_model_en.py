"""
User Memories Model (EN) - Personal knowledge graph and preferences.
Provides Pydantic models with English field names and aliases for compatibility
with existing Spanish DB fields during migration.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Annotated
from bson import ObjectId
from app.models._base import AppBaseModel
from pydantic import Field, ConfigDict, BeforeValidator, EmailStr
PyObjectId = Annotated[str, BeforeValidator(str)]

class MemoryItemModelEN(AppBaseModel):
    """Represents a single memory or preference item."""
    memory_id: str = Field(default_factory=lambda: str(ObjectId()), description='Unique memory id')
    key: str = Field(..., description="Technical name (e.g. 'favorite_language')")
    value: Any = Field(..., description='Stored value')
    category: str = Field(default='other', description='Semantic category')
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    update_count: int = Field(default=1)
    source: Optional[str] = None
    description: Optional[str] = Field(None, description='Natural language explanation')
    semantic_tags: List[str] = Field(default_factory=list)
    subject: Dict[str, str] = Field(default_factory=lambda: {'entity_id': 'user_main', 'entity_type': 'user', 'entity_name': 'User'})
    relations: List[Dict[str, str]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    model_config = ConfigDict(arbitrary_types_allowed=True)

class UserMemoriesModelEN(AppBaseModel):
    """Container for all memories belonging to a specific user."""
    user_id: Optional[PyObjectId] = None
    user_email: EmailStr = Field(..., description="Primary search id / user's email")
    memories: List[MemoryItemModelEN] = Field(default_factory=list)
    entity_registry: Dict[str, Any] = Field(default_factory=dict)
    total_memories: int = Field(default=0)
    average_confidence: float = Field(default=0.0)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)
