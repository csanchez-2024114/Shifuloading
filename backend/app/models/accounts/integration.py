from datetime import datetime, timezone
from typing import Optional, Dict, Any
from enum import Enum
from app.models._base import AppBaseModel
from pydantic import Field, BeforeValidator, HttpUrl, ConfigDict
from typing_extensions import Annotated
PyObjectId = Annotated[str, BeforeValidator(str)]

class ProviderType(str, Enum):
    GMAIL = 'gmail'
    SLACK = 'slack'
    HUBSPOT = 'hubspot'
    DRIVE = 'drive'

class IntegrationPayload(AppBaseModel):
    """
    DTO: Datos sensibles en memoria volátil (Input del Frontend).
    """
    access_token: str
    refresh_token: Optional[str] = None
    api_key: Optional[str] = None
    webhook_url: Optional[HttpUrl] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)

class IntegrationDB(AppBaseModel):
    """
    ENTIDAD: Modelo de persistencia seguro en MongoDB.
    """
    id: Optional[PyObjectId] = Field(alias='_id', default=None)
    user_id: str = Field(..., description='ID del usuario propietario')
    provider: ProviderType = Field(..., description='Proveedor del servicio')
    encrypted_credentials: str = Field(..., description='Credenciales cifradas')
    is_active: bool = Field(default=True)
    status: str = Field(default='connected')
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    model_config = ConfigDict(populate_by_name=True, use_enum_values=True)
