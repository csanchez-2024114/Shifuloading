"""
Conversation and Message Models - Estándar Pydantic V2.
Define la estructura de persistencia para el historial y recursos de la IA.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Annotated
from bson import ObjectId
from app.models._base import AppBaseModel
from pydantic import Field, ConfigDict, BeforeValidator
PyObjectId = Annotated[str, BeforeValidator(str)]

class ResourceModel(AppBaseModel):
    """Modelo para adjuntos (archivos, links, imágenes) en el chat."""
    type: str = Field(..., description='image, link, file, video')
    url: str = Field(..., description='URL segura de Cloudinary o el proveedor')
    title: Optional[str] = None
    provider: str = Field(default='Others', description='Google Drive, Dropbox, Gmail, etc.')
    file_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    model_config = ConfigDict(populate_by_name=True, json_schema_extra={'example': {'type': 'file', 'url': 'https://drive.google.com/...', 'title': 'Reporte.pdf', 'provider': 'Google Drive'}})

class MessageModel(AppBaseModel):
    """Representa un mensaje individual (un globo de texto)."""
    conversation_id: PyObjectId = Field(..., description='ID de la conversación padre')
    role: str = Field(..., description='user o assistant')
    content: str = Field(..., description='Texto del mensaje')
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None
    tokens_used: Optional[int] = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)
    resources: List[ResourceModel] = Field(default_factory=list)
    user_feedback: Optional[str] = None
    model_config = ConfigDict(arbitrary_types_allowed=True)

class ConversationModel(AppBaseModel):
    """Contenedor de la sesión (lo que se ve en la barra lateral)."""
    user_id: PyObjectId = Field(..., description='Dueño de la conversación')
    title: str = Field(..., description='Título generado por IA')
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    message_count: int = 0
    last_message_preview: Optional[str] = None
    is_pinned: bool = False
    is_archived: bool = False
    model_used: str = Field(default='gpt-4o')
    temperature: float = 0.0
    tags: List[str] = Field(default_factory=list)
    model_config = ConfigDict(arbitrary_types_allowed=True, json_schema_extra={'example': {'title': 'Análisis de Ventas Q1', 'message_count': 5, 'model_used': 'gpt-4o'}})
