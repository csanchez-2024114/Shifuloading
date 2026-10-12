from typing import List, Optional, Type, Any
from dataclasses import dataclass
from pydantic import BaseModel, Field
from app.tools.connectors.dropbox_tool import DropboxToolProvider, MoveFileInput, CopyFileInput, DeleteFileInput
from app.core.db_utils import canonicalize_email

@dataclass
class BigTool:
    name: str
    description: str
    tool: Any
    args_schema: Optional[Type[BaseModel]] = None

def get_dropbox_bigtools(user_email: str) -> List[BigTool]:
    """
    Factory que genera todas las BigTools de Dropbox para un usuario específico.

    Args:
        user_email: Email del usuario para autenticación en Dropbox

    Returns:
        Lista de BigTools configuradas para ese usuario
    """
    provider = DropboxToolProvider(user_email)
    return [
        BigTool(name='list_dropbox_files', description='Lista todos los archivos y carpetas en Dropbox. No requiere parámetros.', tool=provider.get_tool_list()),
        BigTool(name='get_dropbox_file_details', description='Consigue un archivo de Dropbox y devuelve su información (nombre, tamaño, ruta, fecha de modificación, enlace temporal). Parámetro: ruta del archivo (str).', tool=provider.get_tool_get_file()),
        BigTool(name='get_dropbox_space', description='Obtiene el espacio usado y total de la cuenta de Dropbox. No requiere parámetros.', tool=provider.get_tool_get_space()),
        BigTool(name='search_dropbox_folder_and_list_files', description='Busca una carpeta en Dropbox por nombre y lista los archivos que contiene con enlaces temporales para cada archivo. Parámetro: nombre o ruta de la carpeta (str).', tool=provider.get_tool_search_folder_and_list_files()),
        BigTool(name='get_dropbox_shared_links', description='Obtiene los enlaces compartidos de un archivo o carpeta en Dropbox. Parámetro: ruta (str).', tool=provider.get_tool_get_shared_links()),
        BigTool(name='get_dropbox_versions', description='Obtiene las últimas versiones de un archivo en Dropbox. Parámetro: ruta del archivo (str).', tool=provider.get_tool_get_versions()),
        BigTool(name='create_dropbox_paper_doc', description='Crea un documento en Dropbox Paper con un título y contenido inicial en formato Markdown. Parámetros: título (str), contenido opcional (str).', tool=provider.get_tool_create_paper_doc()),
        BigTool(name='create_dropbox_folder', description='Crea una carpeta en Dropbox. Parámetro: ruta o nombre de la carpeta (str).', tool=provider.get_tool_create_folder()),
        BigTool(name='move_dropbox_file', description='Mueve un archivo en Dropbox a una carpeta destino. Parámetros: archivo (str), carpeta_destino (str).', tool=provider.get_tool_move_file(), args_schema=MoveFileInput),
        BigTool(name='copy_dropbox_file', description='Copia un archivo en Dropbox a una carpeta destino. Parámetros: archivo (str), carpeta_destino (str).', tool=provider.get_tool_copy_file(), args_schema=CopyFileInput),
        BigTool(name='delete_dropbox_item', description='Elimina un archivo o carpeta en Dropbox. Parámetro: ruta del archivo/carpeta (str).', tool=provider.get_tool_delete_file(), args_schema=DeleteFileInput),
    ]

def get_dropbox_tools_by_category(user_email: str, category: str='all') -> List[BigTool]:
    """
    Obtiene herramientas de Dropbox filtradas por categoría.

    Args:
        user_email: Email del usuario
        category: "get" (consulta), "post" (creación), "update" (modificación),
                 "delete" (eliminación), "all" (todas)

    Returns:
        Lista de BigTools filtradas
    """
    all_tools = get_dropbox_bigtools(user_email)
    if category == 'all':
        return all_tools
    category_keywords = {'get': ['list', 'get', 'search'], 'post': ['create'], 'update': ['move', 'copy'], 'delete': ['delete']}
    if category not in category_keywords:
        return all_tools
    keywords = category_keywords[category]
    filtered_tools = []
    for tool in all_tools:
        if any((keyword in tool.name.lower() for keyword in keywords)):
            filtered_tools.append(tool)
    return filtered_tools

def get_file_management_tools(user_email: str) -> List[BigTool]:
    """
    Obtiene herramientas específicas para gestión de archivos en Dropbox.
    Incluye: mover, copiar, eliminar archivos.
    """
    all_tools = get_dropbox_bigtools(user_email)
    file_management_names = ['move_dropbox_file', 'copy_dropbox_file', 'delete_dropbox_item']
    return [tool for tool in all_tools if tool.name in file_management_names]

def get_exploration_tools(user_email: str) -> List[BigTool]:
    """
    Obtiene herramientas específicas para explorar contenido en Dropbox.
    Incluye: listar archivos, buscar carpetas, obtener espacio.
    """
    all_tools = get_dropbox_bigtools(user_email)
    exploration_names = ['list_dropbox_files', 'search_dropbox_folder_and_list_files', 'get_dropbox_space', 'get_dropbox_shared_links', 'get_dropbox_versions']
    return [tool for tool in all_tools if tool.name in exploration_names]

def get_all_storage_tools(user_email: str) -> List[BigTool]:
    """
    Obtiene todas las herramientas de almacenamiento en la nube.
    """
    return get_dropbox_bigtools(user_email)

def get_paper_tools(user_email: str) -> List[BigTool]:
    """
    Obtiene herramientas específicas para Dropbox Paper.
    """
    all_tools = get_dropbox_bigtools(user_email)
    paper_tools_names = ['create_dropbox_paper_doc']
    return [tool for tool in all_tools if tool.name in paper_tools_names]
