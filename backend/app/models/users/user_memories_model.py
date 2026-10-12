"""
User Memories Model - El ADN del aprendizaje del usuario.
Define la estructura del grafo de conocimiento personal y preferencias.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Annotated
from bson import ObjectId
from app.models._base import AppBaseModel
from pydantic import Field, ConfigDict, BeforeValidator, EmailStr
PyObjectId = Annotated[str, BeforeValidator(str)]

class MemoryItemModel(AppBaseModel):
    """Representa un 'recuerdo' o preferencia individual."""
    memory_id: str = Field(default_factory=lambda: str(ObjectId()), description='ID único del recuerdo')
    key: str = Field(..., description="Nombre técnico (ej: 'favorite_language')")
    value: Any = Field(..., description='El dato guardado')
    category: str = Field(default='other', description='Categoría semántica')
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    update_count: int = Field(default=1)
    source: Optional[str] = None
    description: Optional[str] = Field(None, description='Explicación en lenguaje natural')
    semantic_tags: List[str] = Field(default_factory=list)
    subject: Dict[str, str] = Field(default_factory=lambda: {'entity_id': 'user_main', 'entity_type': 'user', 'entity_name': 'Usuario'})
    relations: List[Dict[str, str]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    model_config = ConfigDict(arbitrary_types_allowed=True)

class UserMemoriesModel(AppBaseModel):
    """Contenedor de todos los recuerdos de un usuario específico."""
    user_id: Optional[PyObjectId] = None
    user_email: EmailStr = Field(..., description="Primary search id / user's email")
    memories: List[MemoryItemModel] = Field(default_factory=list)
    entity_registry: Dict[str, Any] = Field(default_factory=dict)
    total_memories: int = 0
    average_confidence: float = 0.0
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)
