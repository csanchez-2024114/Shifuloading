"""
Reward Redeem Model - records of reward redemptions.
"""
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Annotated
from bson import ObjectId
from app.models._base import AppBaseModel
from pydantic import Field, ConfigDict, BeforeValidator
PyObjectId = Annotated[str, BeforeValidator(str)]

class RewardRedeemModel(AppBaseModel):
    id: Optional[PyObjectId] = Field(None, alias='_id')
    user_email: str = Field(...)
    reward_id: str = Field(..., description='Reference to reward definition')
    redeemed_at: Optional[datetime] = None
    status: str = Field(default='pending')
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)
