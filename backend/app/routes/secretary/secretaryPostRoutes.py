from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, model_validator
from typing import Optional, Dict, Any, List
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import re
import json
import base64
from config import Config
import openai
from email.mime.text import MIMEText
import logging
from app.database import get_db

logger = logging.getLogger(__name__)
openai.api_key = Config.OPENAI_API_KEY
router = APIRouter()


class EmailActionRequest(BaseModel):
    email: EmailStr
    action_text: str
    message_id: str



class NotionActionRequest(BaseModel):
    email: EmailStr
    action_text: str
    message_id: str



class SlackActionRequest(BaseModel):
    email: EmailStr
    action_text: str
    message_id: Optional[str] = None
    channel: str
    reply_text: Optional[str] = None



class DriveActionRequest(BaseModel):
    email: EmailStr
    action_text: str
    message_id: Optional[str] = None



class AsanaActionRequest(BaseModel):
    email: EmailStr
    action_text: str
    message_id: Optional[str] = None



class ClickUpActionRequest(BaseModel):
    email: EmailStr
    action_text: str
    message_id: Optional[str] = None



class HubSpotActionRequest(BaseModel):
    email: EmailStr
    action_text: str
    deal_id: str



class DropboxActionRequest(BaseModel):
    email: EmailStr
    action_text: str
    message_id: Optional[str] = None



class OneDriveActionRequest(BaseModel):
    email: EmailStr
    action_text: str
    file_id: Optional[str] = None



def setup_routes_secretary_posts(refresh_functions):
    """
    Configure the secretary post routes with dependencies.
    Returns the configured router.
    """
    from app.routes.secretary.secretaryGetRoutes import setup_routes_secretary_gets

    functions = setup_routes_secretary_gets(refresh_functions)
    get_gmail_headers = functions["get_gmail_headers"]
    get_outlook_headers = functions["get_outlook_headers"]
    get_slack_headers = functions["get_slack_headers"]
    get_hubspot_headers = functions["get_hubspot_headers"]
    get_notion_headers = functions["get_notion_headers"]
    get_clickup_headers = functions["get_clickup_headers"]
    get_teams_headers = functions["get_teams_headers"]
    get_onedrive_headers = functions["get_onedrive_headers"]
    get_dropbox_headers = functions["get_dropbox_headers"]
    get_asana_headers = functions["get_asana_headers"]
    get_google_drive_headers = functions["get_google_drive_headers"]
    get_refresh_tokens_from_db = refresh_functions["get_refresh_tokens_from_db"]
    refresh_tokens_func = refresh_functions["refresh_tokens"]
    _refresh_cache = {}

    def should_refresh_tokens(email: str) -> bool:
        """Determina si se deben refrescar los tokens basado en el tiempo desde el último refresco."""
        last_refresh = _refresh_cache.get(f"last_refresh_{email}")
        current_time = datetime.utcnow()
        if last_refresh is None:
            logger.info(
                f"No hay registro de último refresco para {email}, forzando refresco"
            )
            return True
        refresh_interval = timedelta(minutes=30)
        time_since_last_refresh = current_time - last_refresh
        if time_since_last_refresh >= refresh_interval:
            logger.info(
                f"Han pasado {time_since_last_refresh} desde el último refresco para {email}, refrescando"
            )
            return True
        logger.info(
            f"Tokens de {email} aún vigentes, faltan {refresh_interval - time_since_last_refresh} para refrescar"
        )
        return False

    def get_user_from_database(email: str):
        """Obtiene el usuario de la base de datos."""
        db = get_db()
        user = db.query("SELECT * FROM usuarios WHERE email = ?", [email])
        return user[0] if user else None

    def get_user_with_refreshed_tokens(email: str):
        """Obtiene el usuario y refresca tokens solo si es necesario."""
        try:
            user = get_user_from_database(email)
            if not user:
                logger.error(f"Usuario {email} no encontrado en DB")
                return None
            if not should_refresh_tokens(email):
                logger.info(
                    f"Tokens de {email} no necesitan refresco, devolviendo usuario"
                )
                return user
            refresh_tokens_dict = get_refresh_tokens_from_db(email)
            if not refresh_tokens_dict:
                logger.info(
                    f"No hay refresh tokens para {email}, marcando tiempo y devolviendo usuario"
                )
                _refresh_cache[f"last_refresh_{email}"] = datetime.utcnow()
                return user
            integrations = user.get("integrations", {})
            tokens_to_refresh = {
                service: refresh_tokens_dict[service]
                for service in integrations
                if service in refresh_tokens_dict
                and integrations[service].get("refresh_token") not in (None, "n/a")
            }
            if not tokens_to_refresh:
                logger.info(
                    f"No hay tokens válidos para refrescar para {email}, marcando tiempo"
                )
                _refresh_cache[f"last_refresh_{email}"] = datetime.utcnow()
                return user
            logger.info(
                f"Refrescando tokens para {email}: {list(tokens_to_refresh.keys())}"
            )
            refreshed_tokens, errors = refresh_tokens_func(tokens_to_refresh, email)
            if refreshed_tokens:
                logger.info(
                    f"Tokens refrescados para {email}: {list(refreshed_tokens.keys())}"
                )
                user = get_user_from_database(email)
                if not user:
                    logger.error(f"No se pudo recargar usuario {email} tras refresco")
                    return None
                _refresh_cache[f"last_refresh_{email}"] = datetime.utcnow()
                return user
            if errors:
                logger.warning(f"Errores al refrescar tokens para {email}: {errors}")
                _refresh_cache[f"last_refresh_{email}"] = datetime.utcnow()
                return user
            logger.info(f"No se refrescaron tokens para {email}, marcando tiempo")
            _refresh_cache[f"last_refresh_{email}"] = datetime.utcnow()
            return user
        except Exception as e:
            logger.error(f"Error en get_user_with_refreshed_tokens para {email}: {e}")
            return None

    def interpretar_accion_email(texto: str) -> str:
        prompt = f"El usuario dijo: '{texto}'. Determina si quiere 'eliminar' o 'delete' (eliminar), 'spam' (mover a spam), 'schedule' (agendar cita), 'draft' (crear borrador) o 'send' (enviar correo). Si no está claro, responde 'unknown'."
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": "Eres un asistente que analiza intenciones en correos electrónicos.",
                },
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content.strip().lower()

    def interpretar_accion_productividad(texto: str) -> str:
        prompt = f"El usuario dijo: '{texto}'. Determina si quiere 'mark_done' (marcar como completado), 'assign' (asignar a alguien más), 'comment' (comentar en la tarea), 'delete' (eliminar la tarea) o 'change_status' (cambiar estado). Si no está claro, responde 'unknown'."
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": "Eres un asistente que analiza intenciones en plataformas de productividad.",
                },
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content.strip().lower()

    def interpretar_accion_hubspot(texto: str) -> str:
        prompt = f"El usuario dijo: '{texto}'. Determina si quiere 'update' (actualizar un negocio), 'create' (crear un negocio), 'comment' (comentar en un negocio), 'create_contact' (crear un contacto), 'delete_contact' (eliminar un contacto), 'create_company' (crear una empresa) o 'delete_company' (eliminar una empresa). Si no está claro, responde 'unknown'."
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": "Eres un asistente que analiza intenciones en plataformas CRM como HubSpot.",
                },
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content.strip().lower()

    def interpretar_accion_archivos(texto: str) -> str:
        prompt = f"El usuario dijo: '{texto}'. Determina si quiere 'download' (descargar archivo), 'share' (compartir con alguien más), 'delete' (eliminar archivo), 'restore' (restaurar archivo), 'create_folder' (crear carpeta) o 'move' (mover archivo). Si no está claro, responde 'unknown'."
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": "Eres un asistente que analiza intenciones en plataformas de almacenamiento en la nube.",
                },
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content.strip().lower()

    def interpretar_accion_mensajeria(texto: str) -> str:
        prompt = f"El usuario dijo: '{texto}'. Determina si quiere 'reply' (responder un mensaje), 'react' (reaccionar con emoji) o 'mention' (mencionar a alguien). Si no está claro, responde 'unknown'."
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": "Eres un asistente que analiza intenciones en plataformas de mensajería.",
                },
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content.strip().lower()

    @router.post("/accion-gmail")
    async def execute_gmail_action(data: EmailActionRequest):
        user = get_user_with_refreshed_tokens(data.email)
        if not user:
            raise HTTPException(
                status_code=404,
                detail="No te encontré en el sistema, ¿seguro que estás registrado?",
            )
        token = user.get("integrations", {}).get("Gmail", {}).get("token")
        if not token:
            raise HTTPException(
                status_code=400,
                detail="No tengo acceso a tu Gmail, ¿revisamos la conexión?",
            )
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        action = interpretar_accion_email(data.action_text)
        logger.info(f"Gmail action: {action}")
        if action == "delete" or "eliminar":
            response = requests.post(
                f"https://www.googleapis.com/gmail/v1/users/me/messages/{data.message_id}/trash",
                headers=headers,
            )
            return {"success": "¡Listo! El correo está en la papelera."}
        elif action == "spam":
            response = requests.post(
                f"https://www.googleapis.com/gmail/v1/users/me/messages/{data.message_id}/modify",
                headers=headers,
                json={"addLabelIds": ["SPAM"], "removeLabelIds": ["INBOX"]},
            )
            if response.status_code == 200:
                return {"success": "¡Hecho! Ese correo ya está en spam."}
            raise HTTPException(
                status_code=response.status_code,
                detail="No pude moverlo a spam, ¿probamos otra vez?",
            )
        raise HTTPException(
            status_code=400,
            detail="No entendí, ¿quieres 'eliminar', 'responde' o 'spam'?",
        )

    @router.post("/accion-outlook")
    async def execute_outlook_action(data: EmailActionRequest):
        user = get_user_with_refreshed_tokens(data.email)
        if not user:
            raise HTTPException(
                status_code=404, detail="No te encontré, ¿estás registrado?"
            )
        token = user.get("integrations", {}).get("Outlook", {}).get("token")
        if not token:
            raise HTTPException(
                status_code=400,
                detail="No tengo acceso a tu Outlook, ¿revisamos la conexión?",
            )
        headers = get_outlook_headers(token)
        action = interpretar_accion_email(data.action_text)
        if action == "delete":
            response = requests.delete(
                f"https://graph.microsoft.com/v1.0/me/messages/{data.message_id}",
                headers=headers,
            )
            return {"success": "¡Listo! El correo está eliminado."}
        elif action == "spam":
            response = requests.post(
                f"https://graph.microsoft.com/v1.0/me/messages/{data.message_id}/move",
                headers=headers,
                json={"destinationId": "JunkEmail"},
            )
            if response.status_code == 201:
                return {"success": "¡Hecho! El correo está en spam."}
            return {"success": "¡Listo! Correo movido a spam (Outlook confirma raro)."}
        raise HTTPException(
            status_code=400,
            detail="No entendí, ¿quieres 'elimina', 'responde' o 'spam'?",
        )

    @router.post("/accion-notion")
    async def execute_notion_action(data: NotionActionRequest):
        user = get_user_with_refreshed_tokens(data.email)
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        token = user.get("integrations", {}).get("Notion", {}).get("token")
        if not token:
            raise HTTPException(status_code=400, detail="Token no disponible")
        action = interpretar_accion_productividad(data.action_text)
        headers = get_notion_headers(token)
        if "mark_done" in action:
            payload = {"properties": {"Estado": {"status": {"name": "Listo"}}}}
            response = requests.patch(
                f"https://api.notion.com/v1/pages/{data.message_id}",
                headers=headers,
                json=payload,
            )
            logger.info(
                f"Notion PATCH response (mark_done): {response.status_code} {response.text}"
            )
            if response.status_code == 200:
                return {"success": "Página marcada como completada"}
            error_detail = response.json().get("message", response.text)
            raise HTTPException(
                status_code=response.status_code,
                detail={"error": "Error al actualizar estado", "details": error_detail},
            )
        elif "delete" in action:
            response = requests.patch(
                f"https://api.notion.com/v1/pages/{data.message_id}",
                headers=headers,
                json={"archived": True},
            )
            if response.status_code == 200:
                return {"success": "Página archivada"}
            raise HTTPException(
                status_code=response.status_code, detail="Error al archivar"
            )
        raise HTTPException(status_code=400, detail="Acción no reconocida")

    @router.post("/accion-slack")
    async def execute_slack_action(data: SlackActionRequest):
        user = get_user_with_refreshed_tokens(data.email)
        if not user:
            raise HTTPException(
                status_code=404, detail="No te encontré, ¿estás registrado?"
            )
        token = user.get("integrations", {}).get("Slack", {}).get("token")
        if not token:
            raise HTTPException(
                status_code=400, detail="No tengo acceso a tu Slack, ¿revisamos?"
            )
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        action = interpretar_accion_mensajeria(data.action_text)
        if action == "reply":
            if not data.message_id:
                raise HTTPException(
                    status_code=400,
                    detail="Necesito el ID del mensaje para responder, ¿me lo pasas?",
                )
            reply_text = data.reply_text or ""
            if not reply_text:
                match = re.search(
                    "responde(?: con)?:\\s*(.+)", data.action_text, re.IGNORECASE
                )
                if not match:
                    raise HTTPException(
                        status_code=400,
                        detail="Dime qué responder (ej: 'responde: Hola')",
                    )
                reply_text = match.group(1).strip()
            response = requests.post(
                "https://slack.com/api/chat.postMessage",
                headers=headers,
                json={
                    "channel": data.channel,
                    "thread_ts": data.message_id,
                    "text": reply_text,
                },
            )
            if response.status_code == 200 and response.json().get("ok"):
                return {"success": f"¡Enviado! Respondí con: '{reply_text}'."}
            raise HTTPException(
                status_code=response.status_code,
                detail="No pude responder, ¿lo intentamos otra vez?",
            )
        elif action == "react":
            if not data.message_id:
                raise HTTPException(
                    status_code=400,
                    detail="Dime qué mensaje reaccionar con el ID, por favor.",
                )
            match = re.search(
                "reacciona(?: con)?:?\\s*:?(\\w+):?", data.action_text, re.IGNORECASE
            )
            if not match:
                raise HTTPException(
                    status_code=400,
                    detail="Dime qué emoji usar (ej: 'reacciona: smile')",
                )
            emoji = match.group(1).strip()
            response = requests.post(
                "https://slack.com/api/reactions.add",
                headers=headers,
                json={
                    "channel": data.channel,
                    "timestamp": data.message_id,
                    "name": emoji,
                },
            )
            if response.status_code == 200 and response.json().get("ok"):
                return {"success": f"¡Listo! Puse un '{emoji}' al mensaje."}
            raise HTTPException(
                status_code=response.status_code,
                detail="No pude reaccionar, ¿probamos de nuevo?",
            )
        elif action == "mention":
            match = re.search(
                "menciona(?: a)?:\\s*(.+)", data.action_text, re.IGNORECASE
            )
            if not match:
                raise HTTPException(
                    status_code=400,
                    detail="Dime a quién mencionar (ej: 'menciona: @juan')",
                )
            mention_target = match.group(1).strip()
            if not mention_target.startswith("@"):
                mention_target = f"@{mention_target}"
            response = requests.post(
                "https://slack.com/api/chat.postMessage",
                headers=headers,
                json={"channel": data.channel, "text": f"Hola {mention_target}"},
            )
            if response.status_code == 200 and response.json().get("ok"):
                return {"success": f"¡Hecho! Mencioné a {mention_target}."}
            raise HTTPException(
                status_code=response.status_code,
                detail="No pude mencionarlo, ¿lo intentamos otra vez?",
            )
        raise HTTPException(
            status_code=400,
            detail="No entendí, ¿quieres 'responde', 'reacciona' o 'menciona'?",
        )

    @router.post("/accion-drive")
    async def execute_drive_action(data: DriveActionRequest):
        logger.info(f"user_text: {data.action_text}")
        logger.info(f"message_id (file_id): {data.message_id}")
        user = get_user_with_refreshed_tokens(data.email)
        if not user:
            raise HTTPException(
                status_code=404, detail="No te encontré, ¿estás registrado?"
            )
        token = user.get("integrations", {}).get("Drive", {}).get("token")
        logger.info(f"Token: {token}")
        if not token:
            raise HTTPException(
                status_code=400, detail="No tengo acceso a tu Drive, ¿revisamos?"
            )
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        action = interpretar_accion_archivos(data.action_text)
        logger.info(f"action: {action}")
        if not action:
            raise HTTPException(
                status_code=400,
                detail="No entendí, ¿quieres 'eliminar', 'mover', 'crear carpeta' o 'compartir'?",
            )
        if action in ["delete", "move"] and (not data.message_id):
            raise HTTPException(
                status_code=400, detail="Necesito el ID del archivo para esta acción"
            )
        if "delete" in action:
            metadata_response = requests.get(
                f"https://www.googleapis.com/drive/v3/files/{data.message_id}",
                headers=headers,
                params={"fields": "name,permissions,ownedByMe,trashed"},
            )
            if metadata_response.status_code != 200:
                logger.error(f"Metadata error: {metadata_response.text}")
                raise HTTPException(
                    status_code=metadata_response.status_code,
                    detail={
                        "error": "No pude verificar el archivo",
                        "details": metadata_response.text,
                    },
                )
            file_data = metadata_response.json()
            logger.info(f"File data: {file_data}")
            file_name = file_data.get("name", "archivo")
            owned_by_me = file_data.get("ownedByMe", False)
            permissions = file_data.get("permissions", [])
            is_trashed = file_data.get("trashed", False)
            if is_trashed:
                return {
                    "message": f"⚠️ El archivo '{file_name}' ya está en la papelera."
                }
            can_delete = owned_by_me or any(
                (p.get("role") in ["owner", "writer"] for p in permissions)
            )
            if not can_delete:
                raise HTTPException(
                    status_code=403,
                    detail=f"No tienes permiso para eliminar el archivo '{file_name}'",
                )
            trash_url = f"https://www.googleapis.com/drive/v3/files/{data.message_id}"
            trash_data = {"trashed": True}
            response = requests.patch(trash_url, headers=headers, json=trash_data)
            if response.status_code == 200:
                return {
                    "success": f"🗑️ El archivo '{file_name}' ha sido movido a la papelera de Google Drive con éxito! 🚀"
                }
            logger.error(f"Delete error details: {response.text}")
            raise HTTPException(
                status_code=response.status_code,
                detail={
                    "error": "No pude eliminar el archivo",
                    "details": response.text,
                },
            )
        if "move" in action:
            match = re.search("(?:carpeta\\s+(.+))", data.action_text, re.IGNORECASE)
            logger.info(f"Match object: {match}")
            if not match:
                raise HTTPException(
                    status_code=400,
                    detail="Dime a qué carpeta moverlo (ej: 'mueve el archivo a la carpeta Trabajo')",
                )
            folder_name = match.group(1).strip()
            logger.info(f"Folder name to move to: {folder_name}")
            search_url = "https://www.googleapis.com/drive/v3/files"
            params = {
                "q": f'name contains "{folder_name}" and mimeType = "application/vnd.google-apps.folder" and trashed=false',
                "fields": "files(id, name)",
            }
            response = requests.get(search_url, headers=headers, params=params)
            logger.info(f"Search status code: {response.status_code}")
            logger.info(f"Search response: {response.text}")
            if response.status_code != 200 or not response.json().get("files"):
                return {
                    "message": f"⚠️ No se encontró una carpeta con el nombre '{folder_name}'. ¿Podrías verificar y especificar el nombre correcto?"
                }
            folders = response.json().get("files", [])
            if len(folders) > 1:
                options = "\n".join(
                    [f"{i + 1}. {folder['name']}" for i, folder in enumerate(folders)]
                )
                return {
                    "message": f"⚠️ Se encontraron varias carpetas con el nombre '{folder_name}'. Por favor, elige una:\n{options}"
                }
            folder_id = folders[0]["id"]
            logger.info(f"Folder ID: {folder_id}")
            file_info = requests.get(
                f"https://www.googleapis.com/drive/v3/files/{data.message_id}",
                headers=headers,
                params={"fields": "parents,name"},
            )
            if file_info.status_code != 200:
                raise HTTPException(
                    status_code=500,
                    detail={
                        "error": "No pude obtener info del archivo",
                        "details": file_info.text,
                    },
                )
            file_data = file_info.json()
            current_parents = file_data.get("parents", [])
            file_name = file_data.get("name", "archivo")
            logger.info(f"Current parents (before): {current_parents}")
            logger.info(f"File name: {file_name}")
            file_url = f"https://www.googleapis.com/drive/v3/files/{data.message_id}"
            move_data = {
                "addParents": folder_id,
                "removeParents": ",".join(current_parents) if current_parents else None,
            }
            logger.info(f"Move file data: {move_data}")
            headers_with_content = headers.copy()
            headers_with_content["Content-Type"] = "application/json"
            move_response = requests.patch(
                file_url,
                headers=headers_with_content,
                json=move_data,
                params={"fields": "id,name,parents"},
            )
            logger.info(f"Move status code: {move_response.status_code}")
            logger.info(f"Move response: {move_response.text}")
            if move_response.status_code == 200:
                return {
                    "success": f"🎉 El archivo '{file_name}' ha sido movido a la carpeta '{folder_name}' en Google Drive con éxito! 🚀"
                }
            raise HTTPException(
                status_code=move_response.status_code,
                detail={
                    "error": "No pude mover el archivo",
                    "details": move_response.text,
                },
            )
        if action == "create_folder":
            match = re.search(
                "crear\\s*carpeta:\\s*(.+)", data.action_text, re.IGNORECASE
            )
            if not match:
                raise HTTPException(
                    status_code=400,
                    detail="Dime el nombre de la carpeta (ej: 'crear carpeta: Nueva')",
                )
            folder_name = match.group(1).strip()
            response = requests.post(
                "https://www.googleapis.com/drive/v3/files",
                headers=headers,
                json={
                    "name": folder_name,
                    "mimeType": "application/vnd.google-apps.folder",
                },
            )
            if response.status_code == 200:
                return {
                    "message": f"🎉 ¡La carpeta '{folder_name}' ha sido creada con éxito en Drive! 📂"
                }
            raise HTTPException(
                status_code=response.status_code,
                detail={"error": "No pude crear la carpeta", "details": response.text},
            )
        if "share" in action:
            if not data.message_id:
                raise HTTPException(
                    status_code=400,
                    detail="Necesito el ID del archivo para compartirlo",
                )
            match = re.search(
                "compartir\\s*(?:el\\s*)?archivo\\s*(?:con)?\\s*[:\\s]*(.+)",
                data.action_text,
                re.IGNORECASE,
            )
            if not match:
                raise HTTPException(
                    status_code=400,
                    detail="Dime con quién compartirlo (ej: 'compartir archivo con: user@example.com')",
                )
            emails = [email.strip() for email in match.group(1).split(",")]
            for email in emails:
                response = requests.post(
                    f"https://www.googleapis.com/drive/v3/files/{data.message_id}/permissions",
                    headers=headers,
                    json={"type": "user", "role": "writer", "emailAddress": email},
                )
                if response.status_code != 200:
                    raise HTTPException(
                        status_code=response.status_code,
                        detail={
                            "error": f"No pude compartir con '{email}'",
                            "details": response.text,
                        },
                    )
            return {
                "success": f"🎉 ¡Archivo compartido con {', '.join(emails)} con éxito! 🤝"
            }
        raise HTTPException(
            status_code=400, detail="No entendí, ¿qué acción quieres realizar?"
        )

    def get_file_id_by_name(
        name: str, is_folder: bool = False, headers: dict = None
    ) -> Optional[str]:
        url = "https://www.googleapis.com/drive/v3/files"
        mime_type = "application/vnd.google-apps.folder" if is_folder else None
        params = {
            "q": f"'me' in owners name contains '{name}' trashed=false",
            "fields": "files(id)",
        }
        if mime_type:
            params["q"] += f" mimeType='{mime_type}'"
        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200:
            return None
        files = response.json().get("files", [])
        return files[0]["id"] if files else None

    @router.post("/accion-asana")
    async def execute_asana_action(data: AsanaActionRequest):
        task_id = data.message_id
        if not task_id:
            logger.info("No se proporcionó task_id, intentando buscar por nombre...")
        user = get_user_with_refreshed_tokens(data.email)
        if not user:
            raise HTTPException(
                status_code=404, detail="No te encontré, ¿estás registrado?"
            )
        token = user.get("integrations", {}).get("Asana", {}).get("token")
        if not token:
            raise HTTPException(
                status_code=400, detail="No tengo acceso a tu Asana, ¿revisamos?"
            )
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        action = interpretar_accion_productividad(data.action_text)
        logger.info(
            f"Acción interpretada: {action} (tipo: {type(action)}, valor: '{action}')"
        )
        if not task_id:
            match = re.search(
                "marca como completada la tarea (.+)|asigna(?: a)?:\\s*(.+)|elimina la tarea (.+)",
                data.action_text,
                re.IGNORECASE,
            )
            if match:
                task_name = next((g for g in match.groups() if g), None)
                if task_name:
                    task_id = get_task_id_asana(task_name, token)
                    if not task_id:
                        raise HTTPException(
                            status_code=404,
                            detail=f"No se encontró la tarea '{task_name}' en Asana",
                        )
                    logger.info(f"Tarea '{task_name}' encontrada, task_id: {task_id}")
                else:
                    raise HTTPException(
                        status_code=400,
                        detail="No se encontró una tarea válida en la consulta",
                    )
            else:
                raise HTTPException(
                    status_code=400,
                    detail="No entendí, ¿quieres 'marca como hecha', 'elimina' o 'asigna' con un nombre de tarea?",
                )
        else:
            try:
                task_response = requests.get(
                    f"https://app.asana.com/api/1.0/tasks/{task_id}",
                    headers=headers,
                    timeout=10,
                )
                logger.info(
                    f"Task GET response: {task_response.status_code} {task_response.text}"
                )
                if task_response.status_code != 200:
                    raise HTTPException(
                        status_code=task_response.status_code,
                        detail={
                            "error": "No encontré la tarea, ¿revisamos el ID?",
                            "details": task_response.text,
                        },
                    )
            except requests.exceptions.RequestException as e:
                logger.error(f"Error en Task GET: {str(e)}")
                raise HTTPException(
                    status_code=500,
                    detail={"error": "Error al validar la tarea", "details": str(e)},
                )
            task_data = task_response.json().get("data", {})
            task_name = task_data.get("name", "la tarea")
        if "mark_done" in action:
            try:
                payload = {"data": {"completed": True}}
                logger.info(f"Intentando marcar como completado con payload: {payload}")
                response = requests.put(
                    f"https://app.asana.com/api/1.0/tasks/{task_id}",
                    headers=headers,
                    json=payload,
                    timeout=10,
                )
                if response.status_code == 200:
                    return {
                        "success": f"¡Listo! La tarea '{task_name}' está marcada como hecha."
                    }
                raise HTTPException(
                    status_code=response.status_code,
                    detail={
                        "error": "No pude marcarla, ¿lo intentamos otra vez?",
                        "details": response.text,
                    },
                )
            except requests.exceptions.RequestException as e:
                logger.error(f"Error en mark_done PUT: {str(e)}")
                raise HTTPException(
                    status_code=500,
                    detail={"error": "Error al marcar la tarea", "details": str(e)},
                )
        elif "delete" in action:
            try:
                response = requests.delete(
                    f"https://app.asana.com/api/1.0/tasks/{task_id}",
                    headers=headers,
                    timeout=10,
                )
                logger.info(f"Delete response: {response.status_code} {response.text}")
                if response.status_code == 204:
                    return {
                        "success": f"¡Hecho! La tarea '{task_name}' está eliminada."
                    }
                raise HTTPException(
                    status_code=response.status_code,
                    detail={
                        "error": "No pude eliminarla, ¿probamos de nuevo?",
                        "details": response.text,
                    },
                )
            except requests.exceptions.RequestException as e:
                logger.error(f"Error en delete: {str(e)}")
                raise HTTPException(
                    status_code=500,
                    detail={"error": "Error al eliminar la tarea", "details": str(e)},
                )
        elif action == "assign":
            match = re.search("asigna(?: a)?:\\s*(.+)", data.action_text, re.IGNORECASE)
            if not match:
                raise HTTPException(
                    status_code=400,
                    detail="Dime a quién asignarla (ej: 'asigna: juan@example.com')",
                )
            assignee_email = match.group(1).strip()
            try:
                workspaces_response = requests.get(
                    "https://app.asana.com/api/1.0/workspaces",
                    headers=headers,
                    timeout=10,
                )
                logger.info(
                    f"Workspaces response: {workspaces_response.status_code} {workspaces_response.text}"
                )
                if workspaces_response.status_code != 200:
                    raise HTTPException(
                        status_code=workspaces_response.status_code,
                        detail={
                            "error": "No se pudo obtener el workspace",
                            "details": workspaces_response.text,
                        },
                    )
            except requests.exceptions.RequestException as e:
                logger.error(f"Error en Workspaces GET: {str(e)}")
                raise HTTPException(
                    status_code=500,
                    detail={
                        "error": "Error al obtener el workspace",
                        "details": str(e),
                    },
                )
            workspace_id = workspaces_response.json().get("data", [])[0]["gid"]
            try:
                users_response = requests.get(
                    f"https://app.asana.com/api/1.0/users?workspace={workspace_id}&opt_fields=email,gid",
                    headers=headers,
                    timeout=10,
                )
                logger.info(
                    f"Users response: {users_response.status_code} {users_response.text}"
                )
                if users_response.status_code != 200:
                    raise HTTPException(
                        status_code=users_response.status_code,
                        detail={
                            "error": "No se pudo buscar el usuario",
                            "details": users_response.text,
                        },
                    )
            except requests.exceptions.RequestException as e:
                logger.error(f"Error en Users GET: {str(e)}")
                raise HTTPException(
                    status_code=500,
                    detail={"error": "Error al buscar el usuario", "details": str(e)},
                )
            users = users_response.json().get("data", [])
            assignee = next(
                (user for user in users if user["email"] == assignee_email), None
            )
            if not assignee:
                raise HTTPException(
                    status_code=404,
                    detail=f"No encontré al usuario '{assignee_email}' en Asana",
                )
            assignee_gid = assignee["gid"]
            try:
                response = requests.put(
                    f"https://app.asana.com/api/1.0/tasks/{task_id}",
                    headers=headers,
                    json={"data": {"assignee": assignee_gid}},
                    timeout=10,
                )
                logger.info(
                    f"Assign PUT response: {response.status_code} {response.text}"
                )
                if response.status_code == 200:
                    return {
                        "success": f"¡Listo! Asigné la tarea '{task_name}' a '{assignee_email}'."
                    }
                raise HTTPException(
                    status_code=response.status_code,
                    detail={
                        "error": "No pude asignarla, ¿lo intentamos otra vez?",
                        "details": response.text,
                    },
                )
            except requests.exceptions.RequestException as e:
                logger.error(f"Error en assign PUT: {str(e)}")
                raise HTTPException(
                    status_code=500,
                    detail={"error": "Error al asignar la tarea", "details": str(e)},
                )
        raise HTTPException(
            status_code=400,
            detail="No entendí, ¿quieres 'marca como hecha', 'elimina' o 'asigna' con un nombre o ID de tarea?",
        )

    def get_task_id_asana(task_name: str, asana_token: str) -> Optional[str]:
        """Obtiene el task_id de una tarea por su nombre en Asana."""
        try:
            headers = {"Authorization": f"Bearer {asana_token}"}
            workspaces_response = requests.get(
                "https://app.asana.com/api/1.0/workspaces", headers=headers, timeout=10
            )
            logger.info(
                f"Workspaces GET response: {workspaces_response.status_code} {workspaces_response.text}"
            )
            if workspaces_response.status_code != 200:
                return None
            workspace_id = workspaces_response.json().get("data", [])[0]["gid"]
            tasks_response = requests.get(
                f"https://app.asana.com/api/1.0/tasks?workspace={workspace_id}&opt_fields=gid,name",
                headers=headers,
                timeout=10,
            )
            logger.info(
                f"Tasks GET response: {tasks_response.status_code} {tasks_response.text}"
            )
            if tasks_response.status_code != 200:
                return None
            tasks = tasks_response.json().get("data", [])
            for task in tasks:
                if task.get("name", "").lower() == task_name.lower():
                    return task["gid"]
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Error al buscar task_id: {str(e)}")
            return None

    @router.post("/accion-clickup")
    async def execute_clickup_action(data: ClickUpActionRequest):
        user = get_user_with_refreshed_tokens(data.email)
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        token = user.get("integrations", {}).get("ClickUp", {}).get("token")
        if not token:
            raise HTTPException(status_code=400, detail="Token de ClickUp no disponible")
        headers = get_clickup_headers(token)
        action = interpretar_accion_productividad(data.action_text)
        if "mark_done" in action:
            response = requests.put(
                f"https://api.clickup.com/api/v2/task/{data.message_id}",
                headers=headers,
                json={"status": "closed"},
            )
            if response.status_code == 200:
                return {"success": "Tarea marcada como completada en ClickUp"}
            raise HTTPException(status_code=response.status_code, detail="Error al actualizar tarea")
        elif "delete" in action:
            response = requests.delete(
                f"https://api.clickup.com/api/v2/task/{data.message_id}",
                headers=headers,
            )
            if response.status_code == 204:
                return {"success": "Tarea eliminada en ClickUp"}
            raise HTTPException(status_code=response.status_code, detail="Error al eliminar tarea")
        raise HTTPException(status_code=400, detail="Acción no reconocida para ClickUp")

    @router.post("/accion-hubspot")
    async def execute_hubspot_action(data: HubSpotActionRequest):
        user = get_user_with_refreshed_tokens(data.email)
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        token = user.get("integrations", {}).get("HubSpot", {}).get("token")
        if not token:
            raise HTTPException(status_code=400, detail="Token de HubSpot no disponible")
        headers = get_hubspot_headers(token)
        action = interpretar_accion_hubspot(data.action_text)
        if "update" in action:
            response = requests.patch(
                f"https://api.hubapi.com/crm/v3/objects/deals/{data.deal_id}",
                headers=headers,
                json={"properties": {"hs_notes_body": data.action_text}},
            )
            if response.status_code == 200:
                return {"success": "Negocio actualizado en HubSpot"}
            raise HTTPException(status_code=response.status_code, detail="Error al actualizar negocio")
        elif "comment" in action:
            response = requests.post(
                f"https://api.hubapi.com/crm/v3/objects/deals/{data.deal_id}/associations/notes",
                headers=headers,
                json={"properties": {"hs_note_body": data.action_text}},
            )
            if response.status_code in (200, 201):
                return {"success": "Comentario agregado al negocio"}
            raise HTTPException(status_code=response.status_code, detail="Error al comentar")
        raise HTTPException(status_code=400, detail="Acción no reconocida para HubSpot")

    @router.post("/accion-dropbox")
    async def execute_dropbox_action(data: DropboxActionRequest):
        user = get_user_with_refreshed_tokens(data.email)
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        token = user.get("integrations", {}).get("Dropbox", {}).get("token")
        if not token:
            raise HTTPException(status_code=400, detail="Token de Dropbox no disponible")
        headers = get_dropbox_headers(token)
        action = interpretar_accion_archivos(data.action_text)
        if "delete" in action and data.message_id:
            response = requests.post(
                "https://api.dropboxapi.com/2/files/delete_v2",
                headers={**headers, "Content-Type": "application/json"},
                json={"path": data.message_id},
            )
            if response.status_code == 200:
                return {"success": "Archivo eliminado de Dropbox"}
            raise HTTPException(status_code=response.status_code, detail="Error al eliminar archivo")
        elif "share" in action and data.message_id:
            response = requests.post(
                "https://api.dropboxapi.com/2/sharing/create_shared_link_with_settings",
                headers={**headers, "Content-Type": "application/json"},
                json={"path": data.message_id},
            )
            if response.status_code == 200:
                url = response.json().get("url", "")
                return {"success": f"Enlace compartido: {url}"}
            raise HTTPException(status_code=response.status_code, detail="Error al compartir archivo")
        raise HTTPException(status_code=400, detail="Acción no reconocida para Dropbox")

    @router.post("/accion-onedrive")
    async def execute_onedrive_action(data: OneDriveActionRequest):
        user = get_user_with_refreshed_tokens(data.email)
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        token = user.get("integrations", {}).get("OneDrive", {}).get("token")
        if not token:
            raise HTTPException(status_code=400, detail="Token de OneDrive no disponible")
        headers = get_onedrive_headers(token)
        action = interpretar_accion_archivos(data.action_text)
        if "delete" in action and data.file_id:
            response = requests.delete(
                f"https://graph.microsoft.com/v1.0/me/drive/items/{data.file_id}",
                headers=headers,
            )
            if response.status_code == 204:
                return {"success": "Archivo eliminado de OneDrive"}
            raise HTTPException(status_code=response.status_code, detail="Error al eliminar archivo")
        elif "share" in action and data.file_id:
            response = requests.post(
                f"https://graph.microsoft.com/v1.0/me/drive/items/{data.file_id}/createLink",
                headers={**headers, "Content-Type": "application/json"},
                json={"type": "view"},
            )
            if response.status_code == 200:
                url = response.json().get("link", {}).get("webUrl", "")
                return {"success": f"Enlace compartido: {url}"}
            raise HTTPException(status_code=response.status_code, detail="Error al compartir archivo")
        raise HTTPException(status_code=400, detail="Acción no reconocida para OneDrive")

    @router.post("/accion-teams")
    async def execute_teams_action(data: SlackActionRequest):
        user = get_user_with_refreshed_tokens(data.email)
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        token = user.get("integrations", {}).get("Teams", {}).get("token")
        if not token:
            raise HTTPException(status_code=400, detail="Token de Teams no disponible")
        headers = get_teams_headers(token)
        action = interpretar_accion_mensajeria(data.action_text)
        if "reply" in action and data.message_id:
            match = re.search("responde(?: con)?:\\s*(.+)", data.action_text, re.IGNORECASE)
            reply_text = data.reply_text or (match.group(1).strip() if match else "")
            if not reply_text:
                raise HTTPException(status_code=400, detail="Dime qué responder")
            response = requests.post(
                f"https://graph.microsoft.com/v1.0/teams/{data.message_id}/replies",
                headers={**headers, "Content-Type": "application/json"},
                json={"body": {"content": reply_text}},
            )
            if response.status_code in (200, 201):
                return {"success": f"Respuesta enviada en Teams: '{reply_text}'"}
            raise HTTPException(status_code=response.status_code, detail="Error al responder en Teams")
        raise HTTPException(status_code=400, detail="Acción no reconocida para Teams")

    return router
