"""
User Connected Account Model - user_connected_accounts collection.
"""
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Annotated
from bson import ObjectId
from app.models._base import AppBaseModel
from pydantic import Field, ConfigDict, BeforeValidator
PyObjectId = Annotated[str, BeforeValidator(str)]

class UserConnectedAccountModel(AppBaseModel):
    id: Optional[PyObjectId] = Field(None, alias='_id')
    user_email: str = Field(...)
    provider: str = Field(..., description='Provider name')
    account_id: str = Field(..., description='Provider account id')
    metadata: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)
