from typing import Any, List, Optional, Type
from dataclasses import dataclass
from pydantic import BaseModel

@dataclass
class BigTool:
    name: str
    description: str
    tool: Any
    args_schema: Optional[Type[BaseModel]] = None

def get_facebook_bigtools(user_email: str) -> List[BigTool]:
    """
    Obtiene las BigTools de Facebook.
    Actualmente solo hay 1: obtener detalles de cuenta.
    """
    from app.tools.connectors.facebookTool import FacebookToolProvider
    provider = FacebookToolProvider(user_email)
    return [BigTool(name='get_account_details_facebook', description='Obtiene información de tu perfil de Facebook: nombre, email, foto, ID', tool=provider.get_tool_account_details())]
