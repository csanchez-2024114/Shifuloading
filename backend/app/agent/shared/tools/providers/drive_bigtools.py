from typing import List, Optional, Type, Any
from dataclasses import dataclass
from pydantic import BaseModel, Field
from app.tools.connectors.google_drive_tool import GoogleDriveToolProvider
from app.core.db_utils import canonicalize_email


@dataclass
class BigTool:
    name: str
    description: str
    tool: Any
    args_schema: Optional[Type[BaseModel]] = None


class CreateFileArgs(BaseModel):
    name: str = Field(
        ...,
        description="Nombre exacto del archivo o carpeta. Solo el sustantivo del título, sin verbos ni contexto.",
    )
    parent_id: Optional[str] = Field(
        None, description="ID de carpeta destino en Drive. Omitir si no se especificó."
    )


def get_drive_bigtools(
    user_id: str, user_email: str, active_accounts: Optional[dict] = None
) -> List[BigTool]:
    """
    Factory que genera todas las BigTools de Google Drive para un usuario específico.

    Args:
        user_id: ID del usuario para buscar credenciales.
        user_email: Email del usuario (contexto).
        active_accounts: Mapa de `provider -> account_id` para la sesión actual.

    Returns:
        Lista de BigTools configuradas para ese usuario
    """
    account_id = active_accounts.get("google") if active_accounts else None
    provider = GoogleDriveToolProvider(user_email=user_email, user_id=user_id, account_id=account_id)
    return [
        BigTool(
            name="list_drive_files",
            description="HERRAMIENTA OBLIGATORIA PARA GOOGLE DRIVE. Úsala SIEMPRE que el usuario pida ver, mostrar, listar o explorar sus archivos, documentos o carpetas en Google Drive. Devuelve todos los archivos y carpetas visibles del usuario autenticado.",
            tool=provider.get_tool(),
        ),
        BigTool(
            name="find_drive_file",
            description="HERRAMIENTA OBLIGATORIA PARA GOOGLE DRIVE. Úsala SIEMPRE que el usuario pida buscar, encontrar, localizar o verificar si existe un archivo o documento en Google Drive por nombre. Acepta filtros opcionales de tipo de archivo y carpeta. Retorna JSON con el archivo encontrado.",
            tool=provider.get_tool_search_one(),
        ),
        BigTool(
            name="create_drive_folder",
            description="Crea una nueva carpeta o directorio en Google Drive.",
            tool=provider.get_tool_create_folder(),
            args_schema=CreateFileArgs,
        ),
        BigTool(
            name="create_drive_doc",
            description="Crea un nuevo documento de Google Docs en Drive.",
            tool=provider.get_tool_create_doc(),
            args_schema=CreateFileArgs,
        ),
        BigTool(
            name="create_drive_sheet",
            description="Crea una nueva hoja de cálculo de Google Sheets en Drive.",
            tool=provider.get_tool_create_sheet(),
            args_schema=CreateFileArgs,
        ),
        BigTool(
            name="create_drive_slide",
            description="Crea una nueva presentación de Google Slides en Drive.",
            tool=provider.get_tool_create_slide(),
            args_schema=CreateFileArgs,
        ),
        BigTool(
            name="delete_drive_file",
            description="Elimina un archivo o carpeta de Google Drive de forma permanente. Requiere confirmación explícita.",
            tool=provider.get_tool_delete_file(),
        ),
        BigTool(
            name="move_drive_file",
            description="HERRAMIENTA OBLIGATORIA PARA GOOGLE DRIVE. Úsala SIEMPRE que el usuario pida mover, trasladar, reubicar o cambiar de carpeta un archivo en Google Drive. Interpreta lenguaje natural. Ejemplo: 'Mueve el archivo Reporte X a la carpeta Proyectos'.",
            tool=provider.get_tool_move_file_by_name(),
        ),
        BigTool(
            name="rename_drive_file",
            description="HERRAMIENTA OBLIGATORIA PARA GOOGLE DRIVE. Úsala SIEMPRE que el usuario pida renombrar, cambiar el nombre o actualizar el título de un archivo en Google Drive. Interpreta lenguaje natural. Ejemplo: 'Renombra el archivo Reporte 2024 a Reporte Final 2024'.",
            tool=provider.get_tool_rename_file_by_name(),
        ),
    ]
