"""
Gmail Tool Provider V2.
Refactorizado:
1. Erradicación de Silent Failures (uso estricto de ToolException).
2. Helper _make_tool para inyección automática de handle_tool_error=True.
3. Alineación con Config centralizado.
"""

import base64
import json
import logging
import re as _re
from datetime import datetime, timezone
from email.mime.text import MIMEText
from typing import List, Optional, Dict, Any, Type, Callable
from google.oauth2.credentials import Credentials
from bson.objectid import ObjectId
from googleapiclient.discovery import build
from langchain_core.tools import Tool, StructuredTool, ToolException
from openai import OpenAI
from pydantic import BaseModel, Field
from config import Config
from app.core.mongo import get_sync_database
from app.core.constants import Collections
from app.integrations.providers.google.gmail import get_gmail_creds_for_langchain
from app.core.db_utils import canonicalize_email

logger = logging.getLogger(__name__)


class SendEmailInput(BaseModel):
    recipient: str = Field(..., alias="recipient", description="Email del recipient")
    subject: str = Field(..., alias="subject", description="Asunto del correo")
    body: str = Field(..., alias="body", description="Contenido en texto plano")


class CreateDraftInput(BaseModel):
    recipient: str = Field(..., alias="recipient", description="Email del recipient")
    subject: str = Field(..., alias="subject", description="Asunto del borrador")
    body: str = Field(..., alias="body", description="Contenido en texto plano")


class MoveEmailBySubjectInput(BaseModel):
    subject: str = Field(
        ..., alias="subject", description="Texto del subject del correo a mover"
    )
    target_label: str = Field(
        ..., description="Etiqueta destino: SPAM, TRASH, STARRED, IMPORTANT"
    )


class SearchEmailsBySenderInput(BaseModel):
    sender: str = Field(
        ...,
        alias="sender",
        description="Email o dominio del sender. Ej: 'juan@gmail.com' o '@empresa.com'",
    )
    max_results: int = Field(default=10, description="Número máximo de resultados")


class SendDraftBySubjectInput(BaseModel):
    subject: str = Field(
        ...,
        alias="subject",
        description="Texto del subject del borrador a buscar y enviar",
    )


class GmailReactiveInput(BaseModel):
    state: str = Field(..., alias="state", description="'activar' o 'desactivar'")
    prompt_original: str = Field(
        default="", alias="original_prompt", description="Instrucciones del usuario"
    )


class BuscarArgs(BaseModel):
    query: str = Field(
        ..., description="Query de búsqueda Gmail. Ej: 'from:juan@gmail.com'"
    )


class LabelArgs(BaseModel):
    label: str = Field(
        ..., description="Etiqueta: INBOX, SENT, TRASH, SPAM, STARRED, IMPORTANT, DRAFT"
    )
    max_results: int = Field(default=10)


class SubjectArgs(BaseModel):
    subject: str = Field(
        ..., alias="subject", description="Texto a buscar en el subject del correo"
    )


class TagArgs(BaseModel):
    label_name: str = Field(
        ..., alias="label_name", description="Nombre de la nueva etiqueta personalizada"
    )


class GmailToolProvider:

    def __init__(self, user_email: str | None = None, user_id: str | None = None, account_id: str | None = None):
        email_source = user_email
        canonical = canonicalize_email(email_source) or (email_source or "")
        self.user_email = canonical
        self.user_id = user_id
        self.account_id = account_id or None
        self.db = get_sync_database()
        self.collection = self.db[Collections.USERS]
        self.openai_client = OpenAI(api_key=Config.OPENAI_API_KEY)

    def _get_service(self):
        """Inicializa el servicio oficial de Google Gmail API."""
        try:
            # Preferir user_id para localizar credenciales (v2 vault/multi-account)
            if self.user_id:
                creds_dict = get_gmail_creds_for_langchain(self.user_id, account_id=self.account_id)
            else:
                # Fallback: intentar resolver user_id desde el email y usarlo
                user_doc = None
                if self.user_email:
                    user_doc = get_sync_database()[Collections.USERS].find_one(
                        {
                            "$or": [
                                {"email": self.user_email},
                                {"correo": self.user_email},
                            ]
                        }
                    )
                if user_doc and user_doc.get("_id"):
                    creds_dict = get_gmail_creds_for_langchain(str(user_doc.get("_id")), account_id=self.account_id)
                else:
                    raise Exception(
                        "No se proporcionó user_id ni se encontró usuario por email."
                    )
            if "error" in creds_dict:
                raise Exception(creds_dict["error"])
            credentials = Credentials.from_authorized_user_info(creds_dict)
            return build("gmail", "v1", credentials=credentials)
        except Exception as e:
            raise ToolException(f"Error de autenticación con Gmail: {str(e)}")

    def _make_tool(
        self,
        name: str,
        func: Callable,
        description: str,
        args_schema: Optional[Type[BaseModel]] = None,
    ) -> StructuredTool:
        """
        [ENTERPRISE FIX] Helper para instanciar herramientas de forma segura.
        Inyecta handle_tool_error=True para evitar crashes en LangGraph.
        """
        return StructuredTool.from_function(
            name=name,
            func=func,
            description=description,
            args_schema=args_schema,
            handle_tool_error=True,
        )

    def list_emails(self, max_results: int = 10, after: str = "") -> str:
        """Lista los correos más recientes con un snippet condensado del cuerpo.

        `after` acepta una fecha ISO o epoch (ej. '2024-05-01T00:00:00Z') para
        traer solo correos posteriores a esa fecha (útil con {{state.last_run_at}}).
        El cuerpo se trunca a 400 chars para no saturar el contexto del LLM.
        """
        try:
            service = self._get_service()
            # Build query: after-date filter if provided
            q_parts = []
            if after:
                # Gmail accepts epoch seconds or YYYY/MM/DD; convert ISO if needed
                try:
                    from datetime import datetime as _dt, timezone as _tz

                    dt = _dt.fromisoformat(after.replace("Z", "+00:00"))
                    epoch = int(dt.timestamp())
                    q_parts.append(f"after:{epoch}")
                except Exception:
                    q_parts.append(f"after:{after}")
            q = " ".join(q_parts) if q_parts else None

            list_kwargs: dict = {
                "userId": "me",
                "maxResults": max_results,
                "labelIds": ["INBOX"],
            }
            if q:
                list_kwargs["q"] = q

            results = service.users().messages().list(**list_kwargs).execute()
            messages = results.get("messages", [])
            detalle_mensajes = []
            for msg in messages:
                m = service.users().messages().get(userId="me", id=msg["id"]).execute()
                headers = m["payload"]["headers"]
                detalle_mensajes.append(
                    {
                        "id": m["id"],
                        "from": next(
                            (h["value"] for h in headers if h["name"] == "From"),
                            "Desconocido",
                        ),
                        "subject": next(
                            (h["value"] for h in headers if h["name"] == "Subject"),
                            "Sin Asunto",
                        ),
                        "date": next(
                            (h["value"] for h in headers if h["name"] == "Date"), ""
                        ),
                        "snippet": self._condense_body(m),
                    }
                )
            return json.dumps(detalle_mensajes, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[gmail_tool] Error en list_emails: {e}")
            raise ToolException(f"Error al listar correos: {str(e)}")

    def send_email(self, recipient: str, subject: str, body: str) -> str:
        """Crea y envía un correo electrónico de forma inmediata."""
        try:
            service = self._get_service()
            message = MIMEText(body)
            message["to"] = recipient
            message["subject"] = subject
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
            enviado = (
                service.users()
                .messages()
                .send(userId="me", body={"raw": raw_message})
                .execute()
            )
            return json.dumps({"id": enviado["id"], "status": "enviado"})
        except Exception as e:
            logger.error(f"[gmail_tool] Error en send_email: {e}")
            raise ToolException(f"Error al enviar correo a {recipient}: {str(e)}")

    def gmail_reactive_langchain(self, state: str, prompt_original: str = "") -> str:
        """Activa la automatización de correos usando un Watcher de Google."""
        state = state.lower().strip()
        if state not in ["activar", "desactivar"]:
            raise ToolException("Estado inválido. Usa 'activar' o 'desactivar'.")
        try:
            prompt_final = prompt_original
            if state == "activar" and prompt_original:
                res = self.openai_client.chat.completions.create(
                    model=Config.MODEL_NAME,
                    messages=[
                        {
                            "role": "system",
                            "content": "Cambia las instrucciones de correos plurales a SINGULAR (Ej: 'Para este correo...')",
                        },
                        {"role": "user", "content": prompt_original},
                    ],
                )
                prompt_final = res.choices[0].message.content
            if state == "activar":
                try:
                    from app.services.suscripciones.gmail_subscribe_debug import (
                        register_gmail_watch,
                    )

                    register_gmail_watch(self.user_email)
                except Exception as e:
                    logger.warning(
                        f"[gmail_tool] No se pudo activar el watcher, continuando: {e}"
                    )
            update_data = {
                "integrations.Gmail.webhook_langchain_gmail": state == "activar",
                "integrations.Gmail.prompt_restante": prompt_final,
                "integrations.Gmail.prompt_original": prompt_original,
                "integrations.Gmail.webhook_updated": datetime.now(
                    timezone.utc
                ).isoformat(),
            }
            # Actualizar por user_id cuando esté disponible (mejor soporte multicuenta)
            if self.user_id:
                try:
                    oid = ObjectId(self.user_id)
                    self.collection.update_one({"_id": oid}, {"$set": update_data})
                except Exception:
                    # Si user_id no es ObjectId válido, fallback por email
                    self.collection.update_one(
                        {
                            "$or": [
                                {"email": self.user_email},
                                {"correo": self.user_email},
                            ]
                        },
                        {"$set": update_data},
                    )
            else:
                self.collection.update_one(
                    {"$or": [{"email": self.user_email}, {"correo": self.user_email}]},
                    {"$set": update_data},
                )
            return json.dumps(
                {
                    "status": "success",
                    "message": f"Automatización de Gmail {state}da con éxito.",
                }
            )
        except Exception as e:
            logger.error(f"[gmail_tool] Error en reactividad: {e}")
            raise ToolException(f"Error al configurar automatización: {str(e)}")

    def get_email_by_id(self, email_id: str) -> str:
        """Obtiene el contenido completo de un correo específico por su ID."""
        try:
            service = self._get_service()
            message = service.users().messages().get(userId="me", id=email_id).execute()
            headers = message["payload"]["headers"]
            body = self._extract_body(message)
            attachments = [
                part
                for part in message.get("payload", {}).get("parts", [])
                if part.get("filename")
            ]

            email_details = {
                "id": message["id"],
                "from": next(
                    (h["value"] for h in headers if h["name"] == "From"), "Desconocido"
                ),
                "to": next(
                    (h["value"] for h in headers if h["name"] == "To"), "Desconocido"
                ),
                "subject": next(
                    (h["value"] for h in headers if h["name"] == "Subject"),
                    "Sin Asunto",
                ),
                "date": next((h["value"] for h in headers if h["name"] == "Date"), ""),
                "body": body.strip(),
                "has_attachments": len(attachments) > 0,
                "attachment_count": len(attachments),
                "attachments": [
                    {
                        "filename": a.get("filename"),
                        "mimeType": a.get("mimeType"),
                        "partId": a.get("partId"),
                    }
                    for a in attachments
                ],
            }
            return json.dumps(email_details, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[gmail_tool] Error en get_email_by_id: {e}")
            raise ToolException(
                f"Error al obtener el correo con ID '{email_id}': {str(e)}"
            )

    def reply_to_email(self, email_id: str, body: str) -> str:
        """Responde a un correo electrónico existente, manteniéndolo en el mismo hilo de conversación."""
        # Esta es una implementación simplificada. Una versión robusta requeriría obtener el 'Message-ID' y 'References' del correo original.
        raise ToolException(
            "La función 'reply_to_email' aún no está completamente implementada."
        )

    def _extract_body(self, message):
        """Decodifica el contenido del correo de Base64 a texto legible."""
        parts = message.get("payload", {}).get("parts", [])
        if not parts:
            data = message.get("payload", {}).get("body", {}).get("data")
            return (
                base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                if data
                else ""
            )
        for part in parts:
            if part["mimeType"] == "text/plain":
                data = part.get("body", {}).get("data")
                return (
                    base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                    if data
                    else ""
                )
        # Fallback: try any part that has data
        for part in parts:
            data = part.get("body", {}).get("data")
            if data:
                raw = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                return _re.sub(r"<[^>]+>", " ", raw)
        return ""

    def _condense_body(self, message, max_chars: int = 400) -> str:
        """Extract body text, strip HTML and collapse whitespace to a short snippet.

        Keeps token count low so large batches of emails don't overflow context.
        """
        raw = self._extract_body(message)
        if not raw:
            return ""
        text = _re.sub(r"<[^>]+>", " ", raw)  # strip HTML tags
        text = _re.sub(r"\s+", " ", text).strip()  # collapse whitespace
        if len(text) > max_chars:
            text = text[:max_chars] + "…"
        return text

    def get_tool_send_email(self):

        def enviar(recipient: str, subject: str, body: str) -> str:
            return self.send_email(recipient, subject, body)

        return self._make_tool(
            name="send_email",
            func=enviar,
            description="HERRAMIENTA OBLIGATORIA PARA EMAILS. Úsala SIEMPRE que el usuario te pida redactar, mandar, informar o enviar un correo electrónico. Toma el texto proporcionado, redacta un subject profesional si no se provee, y envía el correo.",
            args_schema=SendEmailInput,
        )

    def get_tool_search_email(self):

        def buscar(query: str) -> str:
            try:
                service = self._get_service()
                results = (
                    service.users()
                    .messages()
                    .list(userId="me", q=query, maxResults=10)
                    .execute()
                )
                data = []
                for msg in results.get("messages", []):
                    m = (
                        service.users()
                        .messages()
                        .get(userId="me", id=msg["id"])
                        .execute()
                    )
                    headers = m["payload"]["headers"]
                    data.append(
                        {
                            "id": m["id"],
                            "subject": next(
                                (h["value"] for h in headers if h["name"] == "Subject"),
                                "",
                            ),
                            "from": next(
                                (h["value"] for h in headers if h["name"] == "From"), ""
                            ),
                            "date": next(
                                (h["value"] for h in headers if h["name"] == "Date"), ""
                            ),
                        }
                    )
                return json.dumps(data, ensure_ascii=False)
            except Exception as e:
                raise ToolException(
                    f"Error al buscar correos con query '{query}': {str(e)}"
                )

        return self._make_tool(
            name="find_email",
            func=buscar,
            description="Busca correos en Gmail por query (ej. 'from:juan@gmail.com')",
            args_schema=BuscarArgs,
        )

    def get_tool_search_emails_by_sender(self):

        def buscar(sender: str, max_results: int = 10) -> str:
            try:
                service = self._get_service()
                results = (
                    service.users()
                    .messages()
                    .list(userId="me", q=f"from:{sender}", maxResults=max_results)
                    .execute()
                )
                data = []
                for msg in results.get("messages", []):
                    m = (
                        service.users()
                        .messages()
                        .get(userId="me", id=msg["id"])
                        .execute()
                    )
                    headers = m["payload"]["headers"]
                    data.append(
                        {
                            "id": m["id"],
                            "subject": next(
                                (h["value"] for h in headers if h["name"] == "Subject"),
                                "",
                            ),
                            "date": next(
                                (h["value"] for h in headers if h["name"] == "Date"), ""
                            ),
                            "snippet": self._condense_body(m),
                        }
                    )
                return json.dumps(data, ensure_ascii=False)
            except Exception as e:
                raise ToolException(
                    f"Error al buscar correos del sender '{sender}': {str(e)}"
                )

        return self._make_tool(
            name="find_emails_by_sender",
            func=buscar,
            description="Busca correos de un sender específico y extrae su contenido.",
            args_schema=SearchEmailsBySenderInput,
        )

    def get_tool_list_emails_by_label(self):

        def listar(label: str, max_results: int = 10) -> str:
            try:
                service = self._get_service()
                results = (
                    service.users()
                    .messages()
                    .list(userId="me", labelIds=[label.upper()], maxResults=max_results)
                    .execute()
                )
                data = []
                for msg in results.get("messages", []):
                    m = (
                        service.users()
                        .messages()
                        .get(userId="me", id=msg["id"])
                        .execute()
                    )
                    headers = m["payload"]["headers"]
                    data.append(
                        {
                            "id": m["id"],
                            "subject": next(
                                (h["value"] for h in headers if h["name"] == "Subject"),
                                "",
                            ),
                            "from": next(
                                (h["value"] for h in headers if h["name"] == "From"), ""
                            ),
                        }
                    )
                return json.dumps(data, ensure_ascii=False)
            except Exception as e:
                raise ToolException(
                    f"Error al listar correos de la etiqueta '{label}': {str(e)}"
                )

        return self._make_tool(
            name="list_emails_by_label",
            func=listar,
            description="Lista correos filtrados por una etiqueta específica (INBOX, SENT, SPAM, etc.).",
            args_schema=LabelArgs,
        )

    def get_tool_search_email_by_subject(self):

        def buscar(subject: str) -> str:
            try:
                service = self._get_service()
                results = (
                    service.users()
                    .messages()
                    .list(userId="me", q=f"subject:{subject}", maxResults=10)
                    .execute()
                )
                data = []
                for msg in results.get("messages", []):
                    m = (
                        service.users()
                        .messages()
                        .get(userId="me", id=msg["id"])
                        .execute()
                    )
                    headers = m["payload"]["headers"]
                    data.append(
                        {
                            "id": m["id"],
                            "subject": next(
                                (h["value"] for h in headers if h["name"] == "Subject"),
                                "",
                            ),
                            "from": next(
                                (h["value"] for h in headers if h["name"] == "From"), ""
                            ),
                            "snippet": self._condense_body(m),
                        }
                    )
                return json.dumps(data, ensure_ascii=False)
            except Exception as e:
                raise ToolException(
                    f"Error al buscar correos con el subject '{subject}': {str(e)}"
                )

        return self._make_tool(
            name="find_email_by_subject",
            func=buscar,
            description="Busca y extrae correos que contengan cierto texto en el subject.",
            args_schema=SubjectArgs,
        )

    def get_tool_create_draft(self):

        def crear(recipient: str, subject: str, body: str) -> str:
            try:
                service = self._get_service()
                message = MIMEText(body)
                message["to"] = recipient
                message["subject"] = subject
                raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
                draft = (
                    service.users()
                    .drafts()
                    .create(userId="me", body={"message": {"raw": raw}})
                    .execute()
                )
                return json.dumps({"id": draft["id"], "status": "borrador_creado"})
            except Exception as e:
                raise ToolException(f"Error al crear el borrador: {str(e)}")

        return self._make_tool(
            name="create_draft",
            func=crear,
            description="Crea un borrador en Gmail sin enviarlo.",
            args_schema=CreateDraftInput,
        )

    def get_tool_send_draft_by_subject(self):

        def enviar(subject: str) -> str:
            try:
                service = self._get_service()
                drafts = (
                    service.users()
                    .drafts()
                    .list(userId="me")
                    .execute()
                    .get("drafts", [])
                )
                for d in drafts:
                    draft = (
                        service.users().drafts().get(userId="me", id=d["id"]).execute()
                    )
                    headers = draft["message"]["payload"]["headers"]
                    subject = next(
                        (h["value"] for h in headers if h["name"] == "Subject"), ""
                    )
                    if subject.lower() in subject.lower():
                        service.users().drafts().send(
                            userId="me", body={"id": d["id"]}
                        ).execute()
                        return json.dumps({"status": "enviado", "subject": subject})
                raise ToolException(
                    f"No se encontró ningún borrador con el subject: '{subject}'"
                )
            except Exception as e:
                raise ToolException(f"Error al enviar borrador: {str(e)}")

        return self._make_tool(
            name="send_draft_by_subject",
            func=enviar,
            description="Busca un borrador existente por su subject y procede a enviarlo.",
            args_schema=SendDraftBySubjectInput,
        )

    def get_tool_move_email_by_subject(self):

        def mover(subject: str, etiqueta_destino: str) -> str:
            try:
                service = self._get_service()
                results = (
                    service.users()
                    .messages()
                    .list(userId="me", q=f"subject:{subject}", maxResults=1)
                    .execute()
                )
                messages = results.get("messages", [])
                if not messages:
                    raise ToolException(
                        f"No se encontró correo con subject: '{subject}'"
                    )
                msg_id = messages[0]["id"]
                etiqueta = etiqueta_destino.upper()
                add_labels = (
                    [etiqueta]
                    if etiqueta in ["SPAM", "TRASH", "STARRED", "IMPORTANT"]
                    else []
                )
                service.users().messages().modify(
                    userId="me",
                    id=msg_id,
                    body={"addLabelIds": add_labels, "removeLabelIds": []},
                ).execute()
                return json.dumps({"status": "movido", "label": etiqueta})
            except Exception as e:
                raise ToolException(
                    f"Error al mover correo a la etiqueta {etiqueta_destino}: {str(e)}"
                )

        return self._make_tool(
            name="move_email_by_subject",
            func=mover,
            description="Mueve un correo a una etiqueta (SPAM, TRASH, etc.) buscándolo por el subject.",
            args_schema=MoveEmailBySubjectInput,
        )

    def get_tool_mark_as_unread(self):

        def marcar(subject: str) -> str:
            try:
                service = self._get_service()
                results = (
                    service.users()
                    .messages()
                    .list(userId="me", q=f"subject:{subject}", maxResults=1)
                    .execute()
                )
                messages = results.get("messages", [])
                if not messages:
                    raise ToolException(
                        f"No se encontró correo con el subject: '{subject}'"
                    )
                service.users().messages().modify(
                    userId="me", id=messages[0]["id"], body={"addLabelIds": ["UNREAD"]}
                ).execute()
                return json.dumps({"status": "marcado_no_leido"})
            except Exception as e:
                raise ToolException(f"Error al marcar correo como no leído: {str(e)}")

        return self._make_tool(
            name="mark_as_unread",
            func=marcar,
            description="Marca un correo como no leído buscándolo por su subject.",
            args_schema=SubjectArgs,
        )

    def get_tool_get_email_by_id(self):
        return self._make_tool(
            name="get_email_by_id",
            func=self.get_email_by_id,
            description="Obtiene el contenido completo (cuerpo, remitente, adjuntos) de un correo específico usando su ID. Úsalo después de 'list_emails' o 'find_email' para leer un correo en detalle.",
            args_schema=EmailIdArgs,
        )

    def get_tool_reply_to_email(self):
        class ReplyInput(BaseModel):
            email_id: str = Field(
                ..., description="ID del correo al que se va a responder."
            )
            body: str = Field(..., description="Contenido de la respuesta.")

        return self._make_tool(
            name="reply_to_email",
            func=self.reply_to_email,
            description="Responde a un hilo de correo existente. Necesitas el ID del correo para usar esta función.",
            args_schema=ReplyInput,
        )

    def get_tool_create_label(self):

        def crear(label_name: str) -> str:
            try:
                service = self._get_service()
                label = (
                    service.users()
                    .labels()
                    .create(userId="me", body={"name": label_name})
                    .execute()
                )
                return json.dumps(
                    {"id": label["id"], "name": label["name"], "status": "creada"}
                )
            except Exception as e:
                raise ToolException(f"Error al crear etiqueta '{label_name}': {str(e)}")

        return self._make_tool(
            name="create_label",
            func=crear,
            description="Crea una nueva etiqueta personalizada en Gmail para organizar correos.",
            args_schema=TagArgs,
        )

    def get_tool_gmail_reactive(self):

        def activar(state: str, prompt_original: str = "") -> str:
            return self.gmail_reactive_langchain(
                state="activar", prompt_original=prompt_original
            )

        return self._make_tool(
            name="enable_gmail_reactive",
            func=activar,
            description="Activa el procesamiento automático de correos entrantes.",
            args_schema=GmailReactiveInput,
        )

    def get_tool_gmail_deactivate(self):

        def desactivar(state: str, prompt_original: str = "") -> str:
            return self.gmail_reactive_langchain(
                state="desactivar", prompt_original=prompt_original
            )

        return self._make_tool(
            name="disable_gmail_reactive",
            func=desactivar,
            description="Desactiva el procesamiento automático de correos.",
            args_schema=GmailReactiveInput,
        )

    def get_all_tools(self) -> List[Any]:
        """Registro para compatibilidad legacy (Arrays de LangChain)"""
        return [
            self._make_tool(
                name="list_emails",
                func=self.list_emails,
                description="Muestra los últimos correos recibidos en el INBOX.",
            ),
            self.get_tool_send_email(),
            self.get_tool_gmail_reactive(),
        ]

