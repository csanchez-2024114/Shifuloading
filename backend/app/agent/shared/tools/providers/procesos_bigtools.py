from dataclasses import dataclass
from typing import Any, List, Optional, Type
from pydantic import BaseModel, Field
from app.tools.connectors.process_tool import RecoverAndModifyProcessInput, ProcessToolProvider, ViewProcessInput

@dataclass
class BigTool:
    name: str
    description: str
    tool: Any
    args_schema: Optional[Type[BaseModel]] = None

class DeleteProcessByIdInput(BaseModel):
    process_id: str = Field(description='El ID exacto (_id de MongoDB) del proceso que se desea eliminar. NUNCA inventes este ID.')

def get_process_bigtools(user_email: str, user_id: str | None = None) -> List[BigTool]:
    """
    Factory que genera todas las BigTools de Procesos para un usuario específico.

    Args:
        user_email: Email del usuario para filtrar y aislar sus procesos.
        user_id: Optional user_id — used as fallback query when user_email is empty.

    Returns:
        Lista de BigTools configuradas con contexto aislado para el usuario.
    """
    provider = ProcessToolProvider(user_email, user_id=user_id)
    return [
        BigTool(
            name='listar_procesos',
            description=(
                "SIEMPRE llama esta herramienta cuando el usuario pregunte sobre sus procesos, automatizaciones o workflows guardados. "
                "Úsala para: '¿qué procesos tengo?', '¿cuáles son mis automatizaciones?', '¿tengo procesos activos o completados?', "
                "'muéstrame mis procesos', 'qué automatizaciones he configurado', 'lista mis procesos'. "
                "NUNCA respondas sobre procesos desde memoria — siempre consulta la base de datos con esta herramienta primero."
            ),
            tool=provider.get_tool_list_processes(),
        ),
        BigTool(
            name='ver_proceso',
            description=(
                "Muestra el detalle completo, pasos y resultados de un proceso específico. "
                "Úsalo cuando el usuario pida ver, leer o revisar el contenido de un proceso en particular. "
                "Requiere el ID o nombre del proceso — usa 'listar_procesos' primero si no lo tienes."
            ),
            tool=provider.get_tool_view_process(),
            args_schema=ViewProcessInput,
        ),
        BigTool(
            name='recuperar_y_modificar_proceso',
            description=(
                "Actualiza o corrige por completo las instrucciones de un proceso ya guardado mediante su ID. "
                "Úsalo cuando el usuario quiera cambiar el objetivo original y volver a ejecutarlo con la nueva instrucción."
            ),
            tool=provider.get_tool_recover_and_modify_process_langgraph(),
            args_schema=RecoverAndModifyProcessInput,
        ),
        BigTool(
            name='eliminar_proceso_por_id',
            description=(
                "Elimina permanentemente un proceso de la base de datos usando su ID. "
                "Úsalo SOLO cuando el usuario confirme explícitamente que desea borrar o eliminar un proceso. "
                "El process_id DEBE ser el valor exacto del campo 'id' que devuelve listar_procesos "
                "(un ObjectId hexadecimal de 24 caracteres, ej: '6a14dc8119f66c283a813b49'). "
                "NUNCA uses números secuenciales (1, 2, 3) como ID. "
                "Si quieres eliminar varios, llama esta herramienta una vez por cada proceso con su ID real. "
                "Si no tienes los IDs, llama primero listar_procesos."
            ),
            tool=provider.get_tool_delete_process_by_id(),
            args_schema=DeleteProcessByIdInput,
        ),
    ]
