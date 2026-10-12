from typing import Any, List, Optional, Type
from dataclasses import dataclass
from pydantic import BaseModel, Field
from langchain.tools import Tool, StructuredTool
from app.tools.connectors.asana_tool import AsanaToolProvider
from app.core.db_utils import canonicalize_email

@dataclass
class BigTool:
    name: str
    description: str
    tool: Any
    args_schema: Optional[Type[BaseModel]] = None

class ListTasksInput(BaseModel):
    project_id: str = Field(..., description='ID del proyecto de Asana')

class ListTeamsInput(BaseModel):
    workspace_id: str = Field(..., description='ID del workspace de Asana')

class SearchTaskInput(BaseModel):
    task_name: str = Field(..., description='Nombre o parte del nombre de la tarea a buscar')

class ProjectSummaryInput(BaseModel):
    identifier: str = Field(..., description='Nombre o ID del proyecto para obtener su resumen')

class CompletedTasksInput(BaseModel):
    identifier: str = Field(..., description='Nombre o ID del proyecto para listar tareas completadas')

class AsanaEventsInput(BaseModel):
    request: str = Field(..., description='Solicitud con el nombre del proyecto o tarea para listar eventos')

class IncompleteTasksInput(BaseModel):
    identifier: str = Field(..., description='Nombre o ID del proyecto para listar tareas no completadas')

class ProjectMembersInput(BaseModel):
    identifier: str = Field(..., description='Nombre o ID del proyecto para listar sus miembros')

class CreateTaskInput(BaseModel):
    request: str = Field(..., description="Solicitud completa para crear tarea. Ej: 'Crea una tarea llamada X en el proyecto Y con fecha 2025-10-15 y descripción Z'")

class AssignTaskInput(BaseModel):
    request: str = Field(..., description="Solicitud para asignar tarea. Ej: 'Asigna la tarea X a Y'")

class AddTagInput(BaseModel):
    request: str = Field(..., description="Solicitud para agregar etiqueta. Ej: 'Agrega la etiqueta X a la tarea Y'")

class TasksByTagInput(BaseModel):
    request: str = Field(..., description="Solicitud para listar tareas por etiqueta. Ej: 'Muéstrame las tareas con la etiqueta X'")

class CreateCommentInput(BaseModel):
    request: str = Field(..., description="Solicitud para crear comentario. Ej: 'Agrega un comentario a la tarea X que diga Y'")

class UpdateStatusInput(BaseModel):
    request: str = Field(..., description="Solicitud para actualizar estado. Ej: 'Marca la tarea X como completada'")

class UpdateDescriptionInput(BaseModel):
    request: str = Field(..., description="Solicitud para actualizar descripción. Ej: 'Actualiza la descripción de la tarea X a Y'")

class DuplicateTaskInput(BaseModel):
    request: str = Field(..., description="Solicitud para duplicar tarea. Ej: 'Duplica la tarea X como Y'")

def get_asana_bigtools(user_email: str) -> List[BigTool]:
    """
    Factory que genera todas las BigTools de Asana para un usuario específico.
    
    Args:
        user_email: Email del usuario para autenticación en Asana
        
    Returns:
        Lista de BigTools configuradas para ese usuario
    """
    provider = AsanaToolProvider(user_email)
    return [BigTool(name='listar_proyectos_asana', description='Lista todos los proyectos disponibles en el workspace del usuario, mostrando nombre, propietario, fecha y descripción.', tool=provider.get_tool_list_projects()), BigTool(name='listar_tareas_asana', description='Lista todas las tareas de un proyecto específico de Asana.', tool=provider.get_tool_list_tasks()), BigTool(name='obtener_informacion_usuario_asana', description='Obtiene la información del usuario autenticado en Asana (nombre, correo y workspaces asociados).', tool=provider.get_tool_get_user_info()), BigTool(name='listar_equipos_asana', description='Lista todos los equipos (teams) dentro de un workspace específico de Asana.', tool=provider.get_tool_list_teams()), BigTool(name='obtener_detalle_tarea_por_nombre_asana', description='Busca una tarea por su nombre y obtiene los detalles completos (responsable, fechas, descripción, etc.).', tool=provider.get_tool_get_task_detail_by_name()), BigTool(name='listar_comentarios_tarea_por_nombre_asana', description='Busca una tarea por su nombre y lista todos sus comentarios (stories).', tool=provider.get_tool_list_task_comments_by_name()), BigTool(name='obtener_resumen_proyecto_asana', description='Obtiene un resumen de avance de un proyecto (tareas totales, completadas, pendientes y porcentaje).', tool=provider.get_tool_get_project_summary()), BigTool(name='listar_usuarios_asana', description='Lista todos los miembros del workspace actual (nombre, correo y rol).', tool=provider.get_tool_list_users()), BigTool(name='listar_etiquetas_asana', description='Lista todas las etiquetas disponibles en el workspace (nombre, color, descripción e ID).', tool=provider.get_tool_list_tags()), BigTool(name='listar_tareas_completadas_asana', description='Lista únicamente las tareas completadas dentro de un proyecto.', tool=provider.get_tool_list_completed_tasks()), BigTool(name='listar_eventos_asana', description='Muestra los eventos recientes de un proyecto o tarea (creación, comentarios, modificaciones).', tool=provider.get_tool_list_events()), BigTool(name='listar_tareas_no_completadas_asana', description='Lista únicamente las tareas NO completadas dentro de un proyecto.', tool=provider.get_tool_list_incomplete_tasks()), BigTool(name='listar_miembros_proyecto_asana', description='Muestra todos los miembros asociados a un proyecto.', tool=provider.get_tool_list_project_members()), BigTool(name='listar_tareas_por_etiqueta_asana', description='Muestra todas las tareas que poseen una etiqueta determinada.', tool=provider.get_tool_list_tasks_by_tag()), BigTool(name='crear_tarea_asana', description='Crea una nueva tarea en Asana con nombre, proyecto, fecha y descripción.', tool=provider.get_tool_create_task_asana()), BigTool(name='asignar_tarea_a_usuario_por_nombre_asana', description='Asigna una tarea existente a un usuario, buscándolos por nombre.', tool=provider.get_tool_assign_task_to_user_by_name()), BigTool(name='agregar_etiqueta_a_tarea_por_nombre_asana', description='Agrega una etiqueta existente (o crea una nueva) a una tarea.', tool=provider.get_tool_add_tag_to_task_by_name()), BigTool(name='crear_comentario_tarea_asana', description='Agrega un comentario a una tarea en Asana.', tool=provider.get_tool_create_task_comment()), BigTool(name='actualizar_estado_tarea_por_nombre_asana', description='Marca una tarea como completada o pendiente.', tool=provider.get_tool_update_task_status_by_name()), BigTool(name='actualizar_descripcion_tarea_por_nombre_asana', description='Actualiza la descripción (notas) de una tarea.', tool=provider.get_tool_update_task_description_by_name()), BigTool(name='duplicar_tarea_por_nombre_asana', description='Duplica una tarea existente en Asana.', tool=provider.get_tool_duplicate_task_by_name())]

def get_all_asana_tools(user_email: str) -> List[BigTool]:
    """
    Obtiene todas las herramientas de Asana en formato BigTool.
    
    Args:
        user_email: Email del usuario para autenticación
        
    Returns:
        Lista completa de herramientas de Asana
    """
    return get_asana_bigtools(user_email)
