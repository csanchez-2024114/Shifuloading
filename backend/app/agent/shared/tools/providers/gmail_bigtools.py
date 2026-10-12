from dataclasses import dataclass
from typing import Any, List, Optional, Type, Dict
from pydantic import BaseModel, Field
from app.tools.connectors.gmail_tool import (
    GmailToolProvider,
    SendEmailInput,
    CreateDraftInput,
    MoveEmailBySubjectInput,
    SearchEmailsBySenderInput,
    SendDraftBySubjectInput,
    GmailReactiveInput,
)
from app.core.db_utils import canonicalize_email


@dataclass
class BigTool:
    name: str
    description: str
    tool: Any
    args_schema: Optional[Type[BaseModel]] = None


class ListEmailsArgs(BaseModel):
    max_results: int = Field(default=10, description="Número máximo de correos a traer")
    after: str = Field(
        default="",
        description=(
            "Fecha ISO (ej. '2024-05-01T00:00:00Z') para traer solo correos posteriores. "
            "Usa {{state.last_run_at}} en workflows para deduplicar ejecuciones."
        ),
    )


def get_gmail_bigtools(
    user_id: str, user_email: str, active_accounts: Optional[Dict[str, str]] = None
) -> List[BigTool]:
    """
    Factory que genera todas las BigTools de Gmail para un usuario específico.

    Args:
        user_id: ID del usuario para buscar credenciales.
        user_email: Email del usuario (contexto).
        active_accounts: Mapa de `provider -> account_id` para la sesión actual.

    Returns:
        Lista de BigTools configuradas para ese usuario
    """
    account_id = active_accounts.get("google") if active_accounts else None
    provider = GmailToolProvider(user_email=user_email, user_id=user_id, account_id=account_id)
    return [
        BigTool(
            name="listar_correos",
            description=(
                "Lista los últimos correos del INBOX. Devuelve id, remitente, asunto, fecha y un snippet "
                "condensado del cuerpo (400 chars, HTML eliminado). "
                "Usa `after` con {{state.last_run_at}} en workflows para traer solo correos nuevos."
            ),
            tool=provider.list_emails,
            args_schema=ListEmailsArgs,
        ),
        BigTool(
            name="buscar_correo",
            description="Busca correos en Gmail según un query de búsqueda",
            tool=provider.get_tool_search_email(),
        ),
        BigTool(
            name="buscar_correos_por_remitente",
            description="Busca correos de un remitente específico (persona o dominio). Ej: 'juan@gmail.com' o '@empresa.com'",
            tool=provider.get_tool_search_emails_by_sender(),
            args_schema=SearchEmailsBySenderInput,
        ),
        BigTool(
            name="listar_correos_por_label",
            description="Lista correos por etiqueta: INBOX, SENT, TRASH, SPAM, STARRED, IMPORTANT, DRAFT",
            tool=provider.get_tool_list_emails_by_label(),
        ),
        BigTool(
            name="buscar_correo_por_asunto",
            description="Busca correos que contengan cierto texto en el asunto",
            tool=provider.get_tool_search_email_by_subject(),
        ),
        BigTool(
            name="enviar_correo",
            description="HERRAMIENTA OBLIGATORIA PARA EMAILS. Úsala SIEMPRE que el usuario te pida redactar, mandar, informar o enviar un correo electrónico, mail o mensaje vía Gmail a un contacto. Toma el texto proporcionado por el usuario, redacta un asunto profesional si no se provee, y envía el correo. Requiere los campos: destinatario, asunto y cuerpo.",
            tool=provider.get_tool_send_email(),
            args_schema=SendEmailInput,
        ),
        BigTool(
            name="crear_borrador",
            description="Crea un borrador en Gmail sin enviarlo",
            tool=provider.get_tool_create_draft(),
            args_schema=CreateDraftInput,
        ),
        BigTool(
            name="enviar_borrador_por_asunto",
            description="Busca un borrador por asunto y lo envía inmediatamente",
            tool=provider.get_tool_send_draft_by_subject(),
            args_schema=SendDraftBySubjectInput,
        ),
        BigTool(
            name="mover_correo_por_asunto",
            description="Mueve un correo a SPAM, DESTACADO u otra etiqueta usando el asunto",
            tool=provider.get_tool_move_email_by_subject(),
            args_schema=MoveEmailBySubjectInput,
        ),
        BigTool(
            name="marcar_como_no_leido",
            description="Marca un correo como NO LEÍDO buscándolo por asunto",
            tool=provider.get_tool_mark_as_unread(),
        ),
        BigTool(
            name="crear_etiqueta",
            description="Crea una nueva etiqueta personalizada en Gmail. Ej: 'Universidad', 'Facturas'",
            tool=provider.get_tool_create_label(),
        ),
        BigTool(
            name="gmail_reactivo",
            description="ACTIVA el procesamiento automático de correos. Úsala cuando el usuario diga: 'para cada correo', 'automáticamente', 'cuando llegue un correo'. Guarda instrucciones para procesar correos entrantes.",
            tool=provider.get_tool_gmail_reactive(),
            args_schema=GmailReactiveInput,
        ),
        BigTool(
            name="gmail_desactivar",
            description="DESACTIVA el procesamiento automático de correos. Úsala cuando el usuario pida detener la automatización.",
            tool=provider.get_tool_gmail_deactivate(),
            args_schema=GmailReactiveInput,
        ),
    ]
