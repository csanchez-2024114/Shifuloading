from pydantic import Field, ConfigDict
from typing import Optional, Dict, Any
from datetime import datetime
from app.models._base import AppBaseModel

class ConnectedAccountBase(AppBaseModel):
    provider: str = Field(..., description='Nombre de la app ')
    account_id: str = Field(..., description='ID único del proveedor')
    status: str = Field(default='active', description='Estado de la conexión')
    metadata: Dict[str, Any] = Field(default_factory=dict, description='Campos dinámicos específicos del proveedor ')

class ConnectedAccountResponse(ConnectedAccountBase):
    id: str = Field(alias='_id')
    timestamp: Optional[str] = None
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

class ConnectedAccountInternal(ConnectedAccountBase):
    user_id: str
    access_token: str
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None
    timestamp: Optional[str] = None
