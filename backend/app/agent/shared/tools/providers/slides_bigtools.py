from typing import List, Optional, Type, Any
from dataclasses import dataclass
from pydantic import BaseModel
from langchain.tools import StructuredTool
from app.tools.connectors.google_slides import (
    GoogleSlidesToolProvider,
    PresentationIdInput,
    GetSlideIdsInput,
    InsertSlideTextInput,
    SearchSlideByNameInput,
    GetSlideListInput,
    ReplaceSlideTextInput,
    ChangeSlideTitleInput,
    CreateSlideInput,
    AddSlideInput,
    DuplicateSlideInput,
    CreateShapeInput,
    CreateTableInput,
    ShareSlideInput,
)
from app.core.db_utils import canonicalize_email


@dataclass
class BigTool:
    name: str
    description: str
    tool: Any
    args_schema: Optional[Type[BaseModel]] = None


def get_slides_bigtools(
    user_id: str, user_email: str, active_accounts: Optional[dict] = None
) -> List[BigTool]:
    """
    Factory que genera todas las BigTools de Google Slides para un usuario específico.

    Args:
        user_id: ID del usuario para buscar credenciales.
        user_email: Email del usuario (contexto).
        active_accounts: Mapa de `provider -> account_id` para la sesión actual.

    Returns:
        Lista de BigTools configuradas para ese usuario
    """
    account_id = active_accounts.get("google") if active_accounts else None
    provider = GoogleSlidesToolProvider(user_email=user_email, user_id=user_id, account_id=account_id)
    return [
        BigTool(
            name="get_presentation_content",
            description="Obtiene el contenido de texto de una presentación de Google Slides usando SOLO su ID alfanumérico.",
            tool=provider.get_tool_obtener_contenido(),
            args_schema=PresentationIdInput,
        ),
        BigTool(
            name="find_presentation_by_name",
            description="Busca una presentación de Google Slides por nombre exacto o parcial y devuelve id, enlace y contenido básico.",
            tool=provider.get_tool_obtener_slide_por_nombre(),
            args_schema=SearchSlideByNameInput,
        ),
        BigTool(
            name="list_presentations",
            description="Recupera presentaciones de Google Slides filtrando por nombres, propietario, o fecha de modificación (ej. 'hoy', 'ayer', 'este mes').",
            tool=provider.get_tool_obtener_lista_slides(),
            args_schema=GetSlideListInput,
        ),
        BigTool(
            name="get_presentation_info",
            description="Obtiene información detallada de una presentación por nombre: enlace, fechas, propietarios, último editor y cantidad de diapositivas.",
            tool=provider.get_tool_obtener_info_slide(),
            args_schema=SearchSlideByNameInput,
        ),
        BigTool(
            name="get_presentation_comments",
            description="Recupera los comentarios de una presentación de Google Slides buscada por nombre.",
            tool=provider.get_tool_obtener_comentarios_slide(),
            args_schema=SearchSlideByNameInput,
        ),
        BigTool(
            name="get_presentation_slide_ids",
            description="Obtiene los IDs internos (objectId) de cada una de las páginas o diapositivas de la presentación.",
            tool=provider.get_tool_obtener_ids_slides(),
            args_schema=GetSlideIdsInput,
        ),
        BigTool(
            name="create_presentation",
            description="Crea una nueva presentación vacía de Google Slides con un título especificado. Devuelve el ID generado.",
            tool=provider.get_tool_crear_slide(),
            args_schema=CreateSlideInput,
        ),
        BigTool(
            name="insert_text_in_presentation",
            description="Escribe o inserta texto dentro de una presentación de Google Slides QUE YA EXISTE.",
            tool=provider.get_tool_insertar_texto(),
            args_schema=InsertSlideTextInput,
        ),
        BigTool(
            name="replace_text_in_presentation",
            description="Busca una palabra y la reemplaza por otra en una presentación específica.",
            tool=provider.get_tool_reemplazar_texto(),
            args_schema=ReplaceSlideTextInput,
        ),
        BigTool(
            name="change_presentation_title",
            description="Modifica únicamente el nombre o título de archivo de la presentación de Google Slides en Drive.",
            tool=provider.get_tool_cambiar_titulo(),
            args_schema=ChangeSlideTitleInput,
        ),
        BigTool(
            name="add_slide",
            description="Añade una nueva página/diapositiva en blanco a la presentación.",
            tool=provider.get_tool_agregar_diapositiva(),
            args_schema=AddSlideInput,
        ),
        BigTool(
            name="duplicate_slide",
            description="Clona una diapositiva específica de la presentación.",
            tool=provider.get_tool_duplicar_diapositiva(),
            args_schema=DuplicateSlideInput,
        ),
        BigTool(
            name="create_shape",
            description="Dibuja una figura geométrica en una diapositiva con texto opcional en su interior.",
            tool=provider.get_tool_crear_figura(),
            args_schema=CreateShapeInput,
        ),
        BigTool(
            name="create_table",
            description="Inserta una tabla en una diapositiva y opcionalmente la rellena con datos.",
            tool=provider.get_tool_crear_tabla(),
            args_schema=CreateTableInput,
        ),
        BigTool(
            name="share_presentation",
            description="Asigna o modifica los permisos de visualización o edición de la presentación.",
            tool=provider.get_tool_compartir_slide(),
            args_schema=ShareSlideInput,
        ),
    ]
