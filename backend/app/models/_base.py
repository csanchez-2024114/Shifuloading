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

    @field_serializer(ObjectId, mode='plain', check_fields=False)
    def _serialize_objectid(self, v, _info):
        if v is None:
            return None
        return str(v)

    @field_serializer(datetime, mode='plain', check_fields=False)
    def _serialize_datetime(self, v, _info):
        if v is None:
            return None
        return v.isoformat()
