"""
Rewards Model - definitions of rewards available in the system.
"""
from datetime import datetime, timezone
from typing import Optional, Annotated
from bson import ObjectId
from app.models._base import AppBaseModel
from pydantic import Field, ConfigDict, BeforeValidator
PyObjectId = Annotated[str, BeforeValidator(str)]

class RewardModel(AppBaseModel):
    id: Optional[PyObjectId] = Field(None, alias='_id')
    code: str = Field(..., description='Unique reward code')
    description: Optional[str] = None
    points: int = Field(default=0)
    expires_at: Optional[datetime] = None
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)
