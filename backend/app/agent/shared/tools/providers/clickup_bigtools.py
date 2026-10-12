from typing import List, Optional, Type, Any
from dataclasses import dataclass
from pydantic import BaseModel
from app.tools.connectors.clickup_tool import ClickUpToolProvider
from app.core.db_utils import canonicalize_email

@dataclass
class BigTool:
    name: str
    description: str
    tool: Any
    args_schema: Optional[Type[BaseModel]] = None

def get_clickup_bigtools(user_email: str) -> List[BigTool]:
    """
    Factory que genera todas las BigTools de ClickUp para un usuario específico.

    Args:
        user_email: Email del usuario para autenticación en ClickUp

    Returns:
        Lista de BigTools configuradas para ese usuario
    """
    provider = ClickUpToolProvider(user_email)
    return [
        BigTool(name='list_clickup_spaces', description='Lista todos los espacios del usuario en ClickUp, agrupados por equipo', tool=provider.get_tool_list_spaces()),
        BigTool(name='list_clickup_folders', description='Lista las carpetas dentro de un espacio de ClickUp. Requiere el ID del espacio', tool=provider.get_tool_list_folders()),
        BigTool(name='list_clickup_lists', description="Busca las listas de un proyecto o carpeta en ClickUp por su nombre. Ejemplo: 'muéstrame las listas del proyecto Prácticas' o 'qué listas hay en mi carpeta de desarrollo'. No se necesita ningún ID", tool=provider.get_tool_list_lists()),
        BigTool(name='list_clickup_tasks', description="Busca y lista tareas en ClickUp según el nombre del proyecto, carpeta o lista. Ejemplo: 'Dime las tareas pendientes del proyecto Prácticas IA'. Admite filtros por estado, urgencia, prioridad y asignado. No necesita IDs", tool=provider.get_tool_list_tasks()),
        BigTool(name='get_clickup_task', description='Obtiene los detalles de una tarea específica de ClickUp. Requiere el ID de la tarea', tool=provider.get_tool_get_task()),
        BigTool(name='list_clickup_members', description='Lista los miembros de un equipo en ClickUp. Requiere el ID del equipo', tool=provider.get_tool_list_members()),
        BigTool(name='get_clickup_document', description='Obtiene los detalles de un documento específico en ClickUp. Requiere el ID del documento', tool=provider.get_tool_get_document()),
        BigTool(name='list_clickup_documents_by_name', description="Busca documentos (workdocs) en ClickUp según el nombre del proyecto, carpeta o lista. No requiere IDs. Ejemplo: 'Muéstrame los documentos del proyecto Prácticas' o 'Dime mis documentos en ClickUp'", tool=provider.get_tool_list_documents_by_name()),
        BigTool(name='create_clickup_task', description="Crea una nueva tarea en ClickUp dentro de una lista. Ejemplo: 'Crea una tarea llamada si funciona longchain en mi proyecto practicas'. Extrae automáticamente el nombre de la tarea y la lista destino del texto", tool=provider.get_tool_create_task()),
        BigTool(name='create_clickup_list', description="Crea una nueva lista en ClickUp dentro de una carpeta o espacio. Ejemplo: 'Crea una lista llamada Backend en la carpeta Desarrollo' o 'Crea una lista de pruebas en el espacio API'. Extrae automáticamente los parámetros del texto", tool=provider.get_tool_create_list()),
        BigTool(name='create_clickup_folder', description="Crea una carpeta en ClickUp dentro de un espacio o proyecto. Ejemplo: 'Crea una carpeta llamada Backend en el espacio Prácticas' o 'Crea una carpeta llamada API tests en mi proyecto Automatización'. Extrae automáticamente los parámetros del texto", tool=provider.get_tool_create_folder()),
        BigTool(name='assign_clickup_task', description='Asigna un miembro a una tarea existente en ClickUp. Requiere ID de tarea e ID de miembro', tool=provider.get_tool_assign_task()),
        BigTool(name='add_clickup_comment', description="Agrega un comentario a una tarea en ClickUp usando lenguaje natural. Ejemplo: 'Agrega el comentario listo en la tarea Revisar API del proyecto Prácticas'. Extrae automáticamente el comentario, nombre de tarea y proyecto del texto", tool=provider.get_tool_add_comment()),
        BigTool(name='update_clickup_due_date', description="Actualiza la fecha de entrega de una tarea en ClickUp usando lenguaje natural. Ejemplo: 'Cambia la fecha de entrega de si funciona longchain a 09/10/2025' o 'Actualiza la fecha de la tarea si funciona longchain a mañana'. Interpreta fechas naturales como 'mañana', 'hoy', 'pasado mañana' y fechas en formato dd/mm/yyyy", tool=provider.get_tool_update_due_date()),
    ]

def get_all_clickup_tools(user_email: str) -> List[BigTool]:
    """
    Obtiene todas las BigTools de ClickUp para un usuario.
    """
    return get_clickup_bigtools(user_email)

def get_clickup_tools_by_category(user_email: str, category: str='all') -> List[BigTool]:
    """
    Obtiene herramientas de ClickUp filtradas por categoría.

    Args:
        user_email: Email del usuario
        category: "get" (consulta), "post" (creación), "update" (modificación), "all" (todas)

    Returns:
        Lista de BigTools filtradas
    """
    all_tools = get_clickup_bigtools(user_email)
    if category == 'all':
        return all_tools
    category_map = {'get': ['list', 'get', 'search'], 'post': ['create'], 'update': ['assign', 'add', 'update']}
    if category not in category_map:
        return all_tools
    keywords = category_map[category]
    filtered_tools = []
    for tool in all_tools:
        if any((keyword in tool.name.lower() for keyword in keywords)):
            filtered_tools.append(tool)
    return filtered_tools
