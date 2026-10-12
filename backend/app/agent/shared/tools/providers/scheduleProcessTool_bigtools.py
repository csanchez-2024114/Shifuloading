from dataclasses import dataclass
from datetime import datetime
from typing import Any, List, Optional, Type
from zoneinfo import ZoneInfo
from pydantic import BaseModel
from app.tools.connectors.scheduleProcessTool import ScheduleProcessInput, ScheduleToolProvider
from app.core.db_utils import canonicalize_email

@dataclass
class BigTool:
    name: str
    description: str
    tool: Any
    args_schema: Optional[Type[BaseModel]] = None

def get_schedule_bigtools(user_email: str) -> List[BigTool]:
    """
    Factory que genera todas las BigTools relacionadas con agendamiento
    para un usuario específico.
    
    Args:
        user_email: Email del usuario para inicializar el provider.
        
    Returns:
        Lista de BigTools configuradas para agendamiento.
    """
    provider = ScheduleToolProvider(user_email)
    now_utc = datetime.now(ZoneInfo('UTC'))
    now_local = now_utc.astimezone(ZoneInfo('America/Lima'))
    return [BigTool(name='schedule_process', description=f"Agenda la ejecución de un proceso para una fecha futura. CONTEXTO ACTUAL: UTC={now_utc.strftime('%Y-%m-%d %H:%M')}, Local={now_local.strftime('%Y-%m-%d %H:%M')}. REGLA CRÍTICA: El parámetro 'run_at' debe estar OBLIGATORIAMENTE en UTC.", tool=provider.get_tool_schedule_process(), args_schema=ScheduleProcessInput)]
