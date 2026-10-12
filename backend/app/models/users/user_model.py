"""
User Model - The Master Profile for Shifu.
Centralizes identity, access keys (OAuth), and account state.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Annotated
from app.models._base import AppBaseModel
from pydantic import Field, EmailStr, ConfigDict, BeforeValidator
from bson import ObjectId
PyObjectId = Annotated[str, BeforeValidator(str)]

class IntegrationModel(AppBaseModel):
    """
    Token vault for external services.
    Uses 'extra=allow' to support API-specific params (HubSpot, Slack, etc.)
    """
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_expiry: Optional[datetime] = None
    google_id: Optional[str] = None
    workspace_id: Optional[str] = None
    team_id: Optional[str] = None
    model_config = ConfigDict(extra='allow')

class UserModel(AppBaseModel):
    """
    Main User Model.
    Collection: users
    """
    email: EmailStr = Field(..., description='Unique user email')
    name: Optional[str] = Field(None)
    last_name: Optional[str] = Field(None)
    password: Optional[str] = Field(None, exclude=True)
    google_id: Optional[str] = None
    integrations: Dict[str, IntegrationModel] = Field(default_factory=dict)
    preferences: Dict[str, Any] = Field(default_factory=dict)
    subscriptions: Dict[str, Any] = Field(default_factory=dict)
    plan: str = Field(default='free')
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_login: Optional[datetime] = None
    referral_code: Optional[str] = Field(None)
    rewards: Dict[str, Any] = Field(default_factory=dict)
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True, json_schema_extra={'example': {'email': 'alan.turing@shifu.ai', 'name': 'Alan', 'last_name': 'Turing', 'plan': 'pro', 'integrations': {'google': {'access_token': 'ya29...', 'google_id': '123'}}}})
