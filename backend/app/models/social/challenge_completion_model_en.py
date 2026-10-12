"""
Challenge Completion Model - records when a user completes a challenge.
"""
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Annotated
from bson import ObjectId
from app.models._base import AppBaseModel
from pydantic import Field, ConfigDict, BeforeValidator
PyObjectId = Annotated[str, BeforeValidator(str)]

class ChallengeCompletionModel(AppBaseModel):
    id: Optional[PyObjectId] = Field(None, alias='_id')
    user_email: str = Field(...)
    challenge_id: str = Field(...)
    completed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)
