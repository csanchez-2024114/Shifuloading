from typing import Any, List, Optional, Type
from dataclasses import dataclass
from pydantic import BaseModel, Field
from langchain.tools import Tool, StructuredTool
from app.tools.connectors.google_docs_tool import (
    GoogleDocsToolProvider,
    DocIdInput,
    SearchDocumentArgs,
    SearchDocumentsByAuthorArgs,
    SearchDocumentsByDateArgs,
    ChangeTitleInput,
    CreateDocumentArgs,
    DeleteTextByContentInput,
    InsertTableInput,
    InsertTextInput,
    FillTableInput,
    ReplaceTextInput,
    DocumentNamesInput,
)
from app.core.db_utils import canonicalize_email


@dataclass
class BigTool:
    name: str
    description: str
    tool: Any
    args_schema: Optional[Type[BaseModel]] = None


def get_docs_bigtools(
    user_id: str, user_email: str, active_accounts: Optional[dict] = None
) -> List[BigTool]:
    """
    Factory que genera todas las BigTools de Google Docs para un usuario específico.

    Args:
        user_id: ID del usuario para buscar credenciales.
        user_email: Email del usuario (contexto).
        active_accounts: Mapa de `provider -> account_id` para la sesión actual.

    Returns:
        Lista de BigTools configuradas para ese usuario
    """
    account_id = active_accounts.get("google") if active_accounts else None
    provider = GoogleDocsToolProvider(user_email=user_email, user_id=user_id, account_id=account_id)
    return [
        BigTool(
            name="get_doc_content",
            description="Obtiene el contenido de un documento de Google Docs usando SOLO su ID alfanumérico. Incluye metadatos como fecha, propietarios, editores y enlace.",
            tool=provider.get_tool_get_content(),
            args_schema=DocIdInput,
        ),
        BigTool(
            name="find_doc_by_name",
            description="Busca un documento de Google Docs por nombre (exacto o aproximado) y obtiene su contenido completo.",
            tool=provider.get_tool_search_document_by_name(),
            args_schema=SearchDocumentArgs,
        ),
        BigTool(
            name="list_docs_by_names",
            description="Recupera múltiples documentos por nombres separados por comas. Ej: 'Informe1, ProyectoX, ActaReunión'",
            tool=provider.get_tool_get_document_lists(),
            args_schema=DocumentNamesInput,
        ),
        BigTool(
            name="get_doc_info",
            description="Obtiene información detallada de un documento: propietarios, permisos, fecha de creación, modificación, enlace y resumen.",
            tool=provider.get_tool_get_document_info(),
            args_schema=DocIdInput,
        ),
        BigTool(
            name="get_doc_with_suggestions",
            description="Recupera un documento incluyendo sugerencias de edición en línea y listado de sugerencias detectadas.",
            tool=provider.get_tool_get_document_with_suggestions(),
            args_schema=DocIdInput,
        ),
        BigTool(
            name="get_doc_comments",
            description="Recupera los comentarios de un documento: autor, contenido, fecha, estado y texto comentado.",
            tool=provider.get_tool_get_document_comments(),
            args_schema=DocIdInput,
        ),
        BigTool(
            name="find_docs_by_author",
            description="Busca documentos de Google Docs por autor (correo del propietario o colaborador).",
            tool=provider.get_tool_search_documents_by_author(),
            args_schema=SearchDocumentsByAuthorArgs,
        ),
        BigTool(
            name="find_docs_by_date_range",
            description="Busca documentos por fecha: 'hoy', 'ayer', 'esta semana', 'el mes pasado', o rangos específicos.",
            tool=provider.get_tool_search_documents_by_date(),
            args_schema=SearchDocumentsByDateArgs,
        ),
        BigTool(
            name="create_doc",
            description="Crea un nuevo documento en Google Docs vacío con un título especificado. Devuelve ID y enlace.",
            tool=provider.get_tool_create_doc(),
            args_schema=CreateDocumentArgs,
        ),
        BigTool(
            name="insert_text_in_doc",
            description="Escribe o inserta texto en un documento de Google Docs QUE YA EXISTE. Debe usarse SOLO después de que un documento haya sido creado y cuando la tarea sea escribir contenido en él. NO crea documentos nuevos.",
            tool=provider.get_tool_insert_text(),
            args_schema=InsertTextInput,
        ),
        BigTool(
            name="change_doc_title",
            description="Modifica ÚNICAMENTE el título/nombre del documento de Google Docs. NO inserta contenido ni texto dentro del documento. Usa esta herramienta solo cuando necesites renombrar el documento. Si necesitas escribir contenido, usa 'insert_text_in_doc'.",
            tool=provider.get_tool_change_title(),
            args_schema=ChangeTitleInput,
        ),
        BigTool(
            name="replace_doc_text",
            description="Reemplaza texto en un documento. Puede reemplazar todas, primera o una ocurrencia específica.",
            tool=provider.get_tool_replace_text(),
            args_schema=ReplaceTextInput,
        ),
        BigTool(
            name="delete_doc_text_by_content",
            description="Elimina texto de un documento buscando su contenido. Permite especificar qué ocurrencia eliminar.",
            tool=provider.get_tool_delete_text_by_content(),
            args_schema=DeleteTextByContentInput,
        ),
        BigTool(
            name="insert_table_in_doc",
            description="Inserta una tabla en un documento con un número específico de filas y columnas.",
            tool=provider.get_tool_insert_table(),
            args_schema=InsertTableInput,
        ),
        BigTool(
            name="fill_table_in_doc",
            description="Llena una tabla existente con datos. Los datos deben ser una lista de listas (filas).",
            tool=provider.get_tool_fill_table(),
            args_schema=FillTableInput,
        ),
    ]
