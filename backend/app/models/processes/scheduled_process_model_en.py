"""
Scheduled Process Model - scheduled_processes collection.
EN model with aliases for legacy Spanish fields.
"""
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Annotated
from bson import ObjectId
from app.models._base import AppBaseModel
from pydantic import Field, ConfigDict, BeforeValidator
PyObjectId = Annotated[str, BeforeValidator(str)]

class ScheduledProcessModel(AppBaseModel):
    id: Optional[PyObjectId] = Field(None, alias='_id')
    user_email: str = Field(..., description='Owner email / primary search id')
    process_name: str = Field(..., description='Descriptive process name')
    scheduled_at: datetime = Field(..., description='When the process should run (always UTC)')
    scheduled_timezone: Optional[str] = Field(None, description='IANA timezone the user was in when scheduling, e.g. "America/Guatemala"')
    cron: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    status: str = Field(default='scheduled')
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)
