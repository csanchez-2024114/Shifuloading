from datetime import datetime
from bson import ObjectId
from pydantic import BaseModel, ConfigDict, field_serializer

class AppBaseModel(BaseModel):
    """Base model for the project.

    - Centralizes common Model config like `populate_by_name` and
      `arbitrary_types_allowed`.
    - Provides field serializers for `ObjectId` and `datetime` so
      individual models don't need to set `json_encoders`.
    """
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

    # Antes: @field_serializer(ObjectId)/(datetime). Pydantic 2.11 lo aceptaba sin efecto (espera nombres de campo); 2.14 lo
    # rechaza. Mismo propósito, solo al pasar a JSON: en modo Python los valores quedan igual que antes.
    @field_serializer('*', mode='wrap', check_fields=False)
    def _serializar_tipos(self, v, handler, info):
        if info.mode == 'json':
            if isinstance(v, ObjectId):
                return str(v)
            if isinstance(v, datetime):
                return v.isoformat()
        return handler(v)
