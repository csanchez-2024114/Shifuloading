"""
Schedule Process Tool para LangGraph / LangChain
Migración a Bóveda Segura y Resiliencia V2.
- Manejo estricto de ToolException y handle_tool_error=True.
- Salidas estandarizadas a JSON Strings.
- Logging de errores de base de datos.
- Contexto temporal alineado al usuario.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional
from langchain_core.tools import StructuredTool, ToolException
from pydantic import BaseModel, Field
from zoneinfo import ZoneInfo
from app.services.mongo_schedule_manager import MongoScheduleManager
from app.core.db_utils import canonicalize_email
logger = logging.getLogger('tools.scheduler')

class ScheduleProcessInput(BaseModel):
    user_input: str = Field(..., alias='instruccion', description='Instrucción que se ejecutará cuando llegue el momento')
    run_at: datetime = Field(..., alias='fecha_ejecucion', description="Fecha y hora UTC de ejecución. IMPORTANTE: Debes convertir la fecha relativa del usuario a UTC. Si el usuario dice 'a las 3pm' o 'mañana', calcula la fecha correcta basándote en la fecha/hora actual y zona horaria del usuario.")
    repeat_every_seconds: Optional[int] = Field(default=None, description='Si se define, el proceso se ejecutará periódicamente')
    schedule_type: Optional[str] = Field(default='once', description="Tipo de schedule: 'once', 'interval', 'daily'")
    time_of_day: Optional[str] = Field(default=None, description="Hora del día en formato HH:MM (UTC) para schedule_type='daily'")
    start_at: Optional[datetime] = Field(default=None, description='Fecha/hora de inicio (UTC) opcional. Si no se proporciona, se usará `run_at`.')
    end_at: Optional[datetime] = Field(default=None, description='Fecha/hora final (UTC) opcional para dejar de repetir')

class ScheduleToolProvider:

    def __init__(self, user_email: str | None=None):
        email_source = user_email
        canonical = canonicalize_email(email_source) or (email_source or '')
        self.user_email = canonical
        self.manager = MongoScheduleManager()

    def schedule_process(self, user_input: str, run_at: datetime, repeat_every_seconds: int | None=None, schedule_type: str='once', time_of_day: str | None=None, start_at: datetime | None=None, end_at: datetime | None=None) -> str:
        try:
            if run_at.tzinfo is None:
                run_at = run_at.replace(tzinfo=timezone.utc)
            if start_at and start_at.tzinfo is None:
                start_at = start_at.replace(tzinfo=timezone.utc)
            if end_at and end_at.tzinfo is None:
                end_at = end_at.replace(tzinfo=timezone.utc)
            job_id = self.manager.create_job(user_email=self.user_email, user_input=user_input, run_at=run_at, repeat_every_seconds=repeat_every_seconds, schedule_type=schedule_type, time_of_day=time_of_day, start_at=start_at or run_at, end_at=end_at)
            return json.dumps({'status': 'success', 'mensaje': 'Proceso agendado exitosamente', 'job_id': str(job_id), 'run_at': run_at.isoformat(), 'repeat_every_seconds': repeat_every_seconds}, ensure_ascii=False)
        except Exception as e:
            logger.error(f'[ScheduleTool] Error crítico al agendar job en MongoDB para {self.user_email}: {e}')
            raise ToolException(f'Error de base de datos al agendar proceso: {str(e)}')

    def get_tool_schedule_process(self) -> StructuredTool:
        now_utc = datetime.now(ZoneInfo('UTC'))
        now_local = now_utc.astimezone(ZoneInfo('America/Argentina/Buenos_Aires'))
        return StructuredTool.from_function(func=self.schedule_process, name='schedule_process', description=f"Agenda la ejecución de un proceso para una fecha futura. CONTEXTO ACTUAL DEL USUARIO: UTC={now_utc.strftime('%Y-%m-%d %H:%M')}, Hora Local={now_local.strftime('%Y-%m-%d %H:%M')}. IMPORTANTE: run_at debe calcularse y enviarse estrictamente en UTC.", args_schema=ScheduleProcessInput, handle_tool_error=True)
