"""
Instagram Tool para LangGraph / LangChain
Migración a Bóveda Segura, Soporte Multicuenta y Resiliencia.
- Implementa el motor de lectura centralizado (get_user_vault_with_fallback).
- Utiliza puente asíncrono seguro para compatibilidad con el grafo.
- Erradicación de fallos silenciosos (uso estricto de ToolException).
- Añade timeouts (15s) para resiliencia del Agente IA.
"""

import json
import logging
import requests
import asyncio
import concurrent.futures
from typing import List, Any, Callable, Dict, Optional
from dotenv import load_dotenv
from langchain_core.tools import StructuredTool, ToolException
from pydantic import BaseModel, Field
from app.database import get_user_vault_with_fallback, get_async_database
from app.core.db_utils import canonicalize_email

try:
    from asgiref.sync import async_to_sync
except ImportError:
    async_to_sync = None
load_dotenv()
logger = logging.getLogger("tools.instagram")
_REQUEST_TIMEOUT = 15


class EmptyInput(BaseModel):
    empty: str = Field(
        default="", description="Sin parámetros requeridos. Dejar vacío."
    )


class MediaIdInput(BaseModel):
    media_id: str = Field(
        ..., alias="id_media", description="ID de la publicación (media) en Instagram."
    )


class StoryIdInput(BaseModel):
    story_id: str = Field(
        ..., alias="id_historia", description="ID de la historia (story) en Instagram."
    )


class HashtagInput(BaseModel):
    hashtag_name: str = Field(
        ...,
        alias="nombre_hashtag",
        description="Nombre del hashtag a buscar sin el símbolo #.",
    )


class ConversationIdInput(BaseModel):
    conversation_id: str = Field(
        ..., alias="id_conversacion", description="ID de la conversación de Instagram."
    )


class CreateCommentInput(BaseModel):
    media_id: str = Field(
        ...,
        alias="id_media",
        description="ID de la publicación en la que se comentará.",
    )
    message: str = Field(
        ..., alias="mensaje", description="Texto del comentario a publicar."
    )


class ReplyCommentInput(BaseModel):
    comment_id: str = Field(
        ...,
        alias="id_comentario",
        description="ID del comentario al que se responderá.",
    )
    message: str = Field(..., alias="mensaje", description="Texto de la respuesta.")


class DeleteCommentInput(BaseModel):
    comment_id: str = Field(
        ..., alias="id_comentario", description="ID del comentario a eliminar."
    )


class SendMessageInput(BaseModel):
    recipient_id: str = Field(
        ..., alias="id_receptor", description="ID del usuario receptor del mensaje."
    )
    message: str = Field(
        ..., alias="mensaje", description="Contenido del mensaje a enviar."
    )


class UpdateBioInput(BaseModel):
    biography_text: str = Field(
        ..., alias="biografia", description="Nuevo texto para la biografía del perfil."
    )


class UpdateCommentInput(BaseModel):
    comment_id: str = Field(
        ..., alias="id_comentario", description="ID del comentario a editar."
    )
    new_text: str = Field(
        ..., alias="nuevo_texto", description="Nuevo texto del comentario."
    )


class ReplyMessageInput(BaseModel):
    conversation_id: str = Field(
        ...,
        alias="id_conversacion",
        description="ID de la conversación donde se responderá.",
    )
    message: str = Field(
        ..., alias="mensaje", description="Texto de la respuesta a enviar."
    )


class AutoReplyInput(BaseModel):
    reply_text: str = Field(
        ...,
        alias="texto_respuesta",
        description="Texto que se enviará como respuesta automática.",
    )


class InstagramToolProvider:

    def __init__(
        self,
        user_email: str | None = None,
        active_accounts: Optional[Dict[str, str]] = None,
    ):
        """
        Inicializa el proveedor con soporte para inyección dinámica de cuentas activas.
        """
        email_source = user_email
        canonical = canonicalize_email(email_source) or (email_source or "")
        self.user_email = canonical
        self.baseUrl = "https://graph.instagram.com"
        self.active_accounts = active_accounts or {}
        self.account_id = self.active_accounts.get(
            "instagram"
        ) or self.active_accounts.get("Instagram")

    def _run_async_safely(self, coro_func: Callable) -> Any:
        """Puente arquitectónico seguro para ejecutar corrutinas en hilos sincrónicos."""
        if async_to_sync:
            return async_to_sync(coro_func)()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                return executor.submit(lambda: asyncio.run(coro_func())).result()
        else:
            return asyncio.run(coro_func())

    def _get_secure_token(self) -> str:
        """
        Obtiene el token desencriptado usando la arquitectura de 'user_connected_accounts'.
        """
        if not self.user_email:
            raise ToolException("Error de identidad: correo de usuario ausente.")

        async def fetch_token():
            db_conn = get_async_database()
            vault = await get_user_vault_with_fallback(
                self.user_email, db_conn, account_id=self.account_id
            )
            ig_creds = vault.get("instagram") or vault.get("Instagram")
            if not ig_creds or not ig_creds.get("token"):
                raise ToolException(
                    "Instagram no está conectado o el token es inválido. Por favor, conecta tu cuenta."
                )
            return ig_creds["token"]

        return self._run_async_safely(fetch_token)

    def _make_tool(
        self,
        name: str,
        func: Callable,
        description: str,
        args_schema: type[BaseModel] = EmptyInput,
    ) -> StructuredTool:
        """Helper Enterprise para inyectar handle_tool_error=True en todas las herramientas."""
        return StructuredTool.from_function(
            func=func,
            name=name,
            description=description,
            args_schema=args_schema,
            handle_tool_error=True,
        )

    def get_user_profile(self, vacio: str = "") -> str:
        try:
            token = self._get_secure_token()
            params = {"fields": "id,username,account_type", "access_token": token}
            response = requests.get(
                f"{self.baseUrl}/me", params=params, timeout=_REQUEST_TIMEOUT
            )
            if response.status_code == 200:
                return json.dumps(response.json(), ensure_ascii=False)
            raise ToolException(
                f"Instagram API Error ({response.status_code}): {response.text}"
            )
        except ToolException:
            raise
        except Exception as e:
            logger.error(
                f"[InstagramTool] Error en get_user_profile: {e}", exc_info=True
            )
            raise ToolException(f"Error interno: {str(e)}")

    def get_comments(self, media_id: str) -> str:
        try:
            token = self._get_secure_token()
            params = {"fields": "id,text,username,timestamp", "access_token": token}
            response = requests.get(
                f"{self.baseUrl}/{media_id}/comments",
                params=params,
                timeout=_REQUEST_TIMEOUT,
            )
            if response.status_code == 200:
                return json.dumps(response.json(), ensure_ascii=False)
            raise ToolException(
                f"Instagram API Error ({response.status_code}): {response.text}"
            )
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f"Error interno: {str(e)}")

    def get_insights(self, media_id: str) -> str:
        try:
            token = self._get_secure_token()
            params = {
                "metric": "impressions,reach,engagement,saved",
                "access_token": token,
            }
            response = requests.get(
                f"{self.baseUrl}/{media_id}/insights",
                params=params,
                timeout=_REQUEST_TIMEOUT,
            )
            if response.status_code == 200:
                return json.dumps(response.json(), ensure_ascii=False)
            raise ToolException(
                f"Instagram API Error ({response.status_code}): {response.text}"
            )
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f"Error interno: {str(e)}")

    def get_extended_profile(self, vacio: str = "") -> str:
        try:
            token = self._get_secure_token()
            params = {
                "fields": "id,username,account_type,media_count,name,biography,followers_count,follows_count",
                "access_token": token,
            }
            response = requests.get(
                f"{self.baseUrl}/me", params=params, timeout=_REQUEST_TIMEOUT
            )
            if response.status_code == 200:
                return json.dumps(response.json(), ensure_ascii=False)
            raise ToolException(
                f"Instagram API Error ({response.status_code}): {response.text}"
            )
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f"Error interno: {str(e)}")

    def get_story_insights(self, story_id: str) -> str:
        try:
            token = self._get_secure_token()
            params = {
                "metric": "exits,impressions,reach,replies,taps_forward,taps_back",
                "access_token": token,
            }
            response = requests.get(
                f"{self.baseUrl}/{story_id}/insights",
                params=params,
                timeout=_REQUEST_TIMEOUT,
            )
            if response.status_code == 200:
                return json.dumps(response.json(), ensure_ascii=False)
            raise ToolException(
                f"Instagram API Error ({response.status_code}): {response.text}"
            )
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f"Error interno: {str(e)}")

    def get_media_from_account(self, vacio: str = "") -> str:
        try:
            token = self._get_secure_token()
            params = {
                "fields": "id,caption,media_type,permalink,timestamp,username,comments_count",
                "access_token": token,
            }
            response = requests.get(
                f"{self.baseUrl}/me/media", params=params, timeout=_REQUEST_TIMEOUT
            )
            if response.status_code == 200:
                return json.dumps(response.json(), ensure_ascii=False)
            raise ToolException(
                f"Instagram API Error ({response.status_code}): {response.text}"
            )
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f"Error interno: {str(e)}")

    def get_media_details(self, media_id: str) -> str:
        try:
            token = self._get_secure_token()
            params = {
                "fields": "id,caption,media_type,username,timestamp,permalink",
                "access_token": token,
            }
            response = requests.get(
                f"{self.baseUrl}/{media_id}", params=params, timeout=_REQUEST_TIMEOUT
            )
            if response.status_code == 200:
                return json.dumps(response.json(), ensure_ascii=False)
            raise ToolException(
                f"Instagram API Error ({response.status_code}): {response.text}"
            )
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f"Error interno: {str(e)}")

    def get_followers_count(self, vacio: str = "") -> str:
        try:
            token = self._get_secure_token()
            params = {
                "fields": "followers_count,username,account_type",
                "access_token": token,
            }
            response = requests.get(
                f"{self.baseUrl}/me", params=params, timeout=_REQUEST_TIMEOUT
            )
            if response.status_code == 200:
                data = response.json()
                res = {
                    "username": data.get("username"),
                    "followers_count": data.get("followers_count"),
                    "account_type": data.get("account_type"),
                }
                return json.dumps(res, ensure_ascii=False)
            raise ToolException(
                f"Instagram API Error ({response.status_code}): {response.text}"
            )
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f"Error interno: {str(e)}")

    def get_mentions(self, vacio: str = "") -> str:
        try:
            token = self._get_secure_token()
            params = {
                "fields": "id,caption,media_type,permalink,timestamp,username",
                "access_token": token,
            }
            response = requests.get(
                f"{self.baseUrl}/me/mentioned_media",
                params=params,
                timeout=_REQUEST_TIMEOUT,
            )
            if response.status_code == 200:
                return json.dumps(response.json(), ensure_ascii=False)
            raise ToolException(
                f"Instagram API Error ({response.status_code}): {response.text}"
            )
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f"Error interno: {str(e)}")

    def get_hashtag_info(self, hashtag_name: str) -> str:
        try:
            token = self._get_secure_token()
            user_data = requests.get(
                f"{self.baseUrl}/me?fields=id,username&access_token={token}",
                timeout=_REQUEST_TIMEOUT,
            ).json()
            user_id = user_data.get("id")
            if not user_id:
                raise ToolException(
                    "No se pudo obtener el ID del usuario para buscar hashtags."
                )
            params = {"user_id": user_id, "q": hashtag_name, "access_token": token}
            response = requests.get(
                f"{self.baseUrl}/ig_hashtag_search",
                params=params,
                timeout=_REQUEST_TIMEOUT,
            )
            if response.status_code == 200:
                data = response.json()
                if "data" in data and len(data["data"]) > 0:
                    return json.dumps(data["data"][0], ensure_ascii=False)
                raise ToolException("No se encontró el hashtag especificado.")
            raise ToolException(
                f"Instagram API Error ({response.status_code}): {response.text}"
            )
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f"Error interno: {str(e)}")

    def get_conversations(self, vacio: str = "") -> str:
        try:
            token = self._get_secure_token()
            params = {"fields": "id,participants,updated_time", "access_token": token}
            response = requests.get(
                "https://graph.facebook.com/v19.0/me/conversations",
                params=params,
                timeout=_REQUEST_TIMEOUT,
            )
            if response.status_code == 200:
                return json.dumps(response.json(), ensure_ascii=False)
            raise ToolException(f"API Error ({response.status_code}): {response.text}")
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f"Error interno: {str(e)}")

    def get_messages(self, conversation_id: str) -> str:
        try:
            token = self._get_secure_token()
            params = {
                "fields": "id,from,to,message,created_time",
                "access_token": token,
            }
            response = requests.get(
                f"https://graph.facebook.com/v19.0/{conversation_id}/messages",
                params=params,
                timeout=_REQUEST_TIMEOUT,
            )
            if response.status_code == 200:
                return json.dumps(response.json(), ensure_ascii=False)
            raise ToolException(f"API Error ({response.status_code}): {response.text}")
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f"Error interno: {str(e)}")

    def create_comment(self, media_id: str, message: str) -> str:
        try:
            token = self._get_secure_token()
            data = {"message": message, "access_token": token}
            response = requests.post(
                f"{self.baseUrl}/{media_id}/comments",
                data=data,
                timeout=_REQUEST_TIMEOUT,
            )
            if response.status_code == 200:
                return json.dumps(response.json(), ensure_ascii=False)
            raise ToolException(
                f"Instagram API Error ({response.status_code}): {response.text}"
            )
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f"Error interno: {str(e)}")

    def reply_comment(self, comment_id: str, message: str) -> str:
        try:
            token = self._get_secure_token()
            data = {"message": message, "access_token": token}
            response = requests.post(
                f"{self.baseUrl}/{comment_id}/replies",
                data=data,
                timeout=_REQUEST_TIMEOUT,
            )
            if response.status_code == 200:
                return json.dumps(response.json(), ensure_ascii=False)
            raise ToolException(
                f"Instagram API Error ({response.status_code}): {response.text}"
            )
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f"Error interno: {str(e)}")

    def delete_comment(self, comment_id: str) -> str:
        try:
            token = self._get_secure_token()
            params = {"access_token": token}
            response = requests.delete(
                f"{self.baseUrl}/{comment_id}", params=params, timeout=_REQUEST_TIMEOUT
            )
            if response.status_code == 200:
                return json.dumps(
                    {"success": True, "message": "Comentario eliminado correctamente."},
                    ensure_ascii=False,
                )
            raise ToolException(
                f"Instagram API Error ({response.status_code}): {response.text}"
            )
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f"Error interno: {str(e)}")

    def like_media(self, media_id: str) -> str:
        try:
            token = self._get_secure_token()
            data = {"access_token": token}
            response = requests.post(
                f"{self.baseUrl}/{media_id}/likes", data=data, timeout=_REQUEST_TIMEOUT
            )
            if response.status_code == 200:
                return json.dumps(
                    {
                        "success": True,
                        "message": "Publicación marcada con 'me gusta' correctamente.",
                    },
                    ensure_ascii=False,
                )
            raise ToolException(
                f"Instagram API Error ({response.status_code}): {response.text}"
            )
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f"Error interno: {str(e)}")

    def unlike_media(self, media_id: str) -> str:
        try:
            token = self._get_secure_token()
            params = {"access_token": token}
            response = requests.delete(
                f"{self.baseUrl}/{media_id}/likes",
                params=params,
                timeout=_REQUEST_TIMEOUT,
            )
            if response.status_code == 200:
                return json.dumps(
                    {
                        "success": True,
                        "message": "Se quitó el 'me gusta' correctamente.",
                    },
                    ensure_ascii=False,
                )
            raise ToolException(
                f"Instagram API Error ({response.status_code}): {response.text}"
            )
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f"Error interno: {str(e)}")

    def send_message(self, recipient_id: str, message: str) -> str:
        try:
            token = self._get_secure_token()
            data = {
                "recipient": json.dumps({"id": recipient_id}),
                "message": json.dumps({"text": message}),
                "access_token": token,
            }
            response = requests.post(
                "https://graph.facebook.com/v19.0/me/messages",
                data=data,
                timeout=_REQUEST_TIMEOUT,
            )
            if response.status_code == 200:
                return json.dumps(
                    {"success": True, "message": "Mensaje enviado correctamente."},
                    ensure_ascii=False,
                )
            raise ToolException(f"API Error ({response.status_code}): {response.text}")
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f"Error interno: {str(e)}")

    def mark_message_read(self, conversation_id: str) -> str:
        try:
            token = self._get_secure_token()
            data = {
                "recipient": json.dumps({"id": conversation_id}),
                "sender_action": "mark_seen",
                "access_token": token,
            }
            response = requests.post(
                "https://graph.facebook.com/v19.0/me/messages",
                data=data,
                timeout=_REQUEST_TIMEOUT,
            )
            if response.status_code == 200:
                return json.dumps(
                    {"success": True, "message": "Mensajes marcados como leídos."},
                    ensure_ascii=False,
                )
            raise ToolException(f"API Error ({response.status_code}): {response.text}")
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f"Error interno: {str(e)}")

    def update_bio(self, biography_text: str) -> str:
        try:
            token = self._get_secure_token()
            data = {"biography": biography_text, "access_token": token}
            response = requests.post(
                "https://graph.facebook.com/v19.0/me",
                data=data,
                timeout=_REQUEST_TIMEOUT,
            )
            if response.status_code == 200:
                return json.dumps(
                    {
                        "success": True,
                        "message": "Biografía actualizada correctamente.",
                    },
                    ensure_ascii=False,
                )
            raise ToolException(f"API Error ({response.status_code}): {response.text}")
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f"Error interno: {str(e)}")

    def update_comment(self, comment_id: str, new_text: str) -> str:
        try:
            token = self._get_secure_token()
            data = {"message": new_text, "access_token": token}
            response = requests.post(
                f"{self.baseUrl}/{comment_id}", data=data, timeout=_REQUEST_TIMEOUT
            )
            if response.status_code == 200:
                return json.dumps(
                    {
                        "success": True,
                        "message": "Comentario actualizado correctamente.",
                    },
                    ensure_ascii=False,
                )
            raise ToolException(
                f"Instagram API Error ({response.status_code}): {response.text}"
            )
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f"Error interno: {str(e)}")

    def reply_message(self, conversation_id: str, message: str) -> str:
        try:
            token = self._get_secure_token()
            data = {
                "recipient": json.dumps({"id": conversation_id}),
                "message": json.dumps({"text": message}),
                "access_token": token,
            }
            response = requests.post(
                "https://graph.facebook.com/v19.0/me/messages",
                data=data,
                timeout=_REQUEST_TIMEOUT,
            )
            if response.status_code == 200:
                return json.dumps(
                    {"success": True, "message": "Respuesta enviada correctamente."},
                    ensure_ascii=False,
                )
            raise ToolException(f"API Error ({response.status_code}): {response.text}")
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f"Error interno: {str(e)}")

    def set_auto_reply(self, reply_text: str) -> str:
        try:
            token = self._get_secure_token()
            data = {
                "message_auto_reply": json.dumps(
                    {"message": reply_text, "enabled": True}
                ),
                "access_token": token,
            }
            response = requests.post(
                "https://graph.facebook.com/v19.0/me/message_auto_replies",
                data=data,
                timeout=_REQUEST_TIMEOUT,
            )
            if response.status_code == 200:
                return json.dumps(
                    {
                        "success": True,
                        "message": "Respuesta automática configurada correctamente.",
                    },
                    ensure_ascii=False,
                )
            raise ToolException(f"API Error ({response.status_code}): {response.text}")
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f"Error interno: {str(e)}")

    def get_tool_user_profile(self) -> StructuredTool:
        return self._make_tool(
            func=self.get_user_profile,
            name="get_instagram_user_profile",
            description="Obtiene información básica del usuario autenticado en Instagram. Devuelve el id, username y tipo de cuenta.",
        )

    def get_tool_media_from_account(self) -> StructuredTool:
        return self._make_tool(
            func=self.get_media_from_account,
            name="list_instagram_media",
            description="Obtiene todas las publicaciones del usuario autenticado en Instagram.",
        )

    def get_tool_media_details(self) -> StructuredTool:
        return self._make_tool(
            func=self.get_media_details,
            name="get_instagram_media_details",
            description="Obtiene los detalles de una publicación específica en Instagram a partir de su ID.",
            args_schema=MediaIdInput,
        )

    def get_tool_comments(self) -> StructuredTool:
        return self._make_tool(
            func=self.get_comments,
            name="get_instagram_comments",
            description="Obtiene todos los comentarios asociados a una publicación específica de Instagram a partir de su ID.",
            args_schema=MediaIdInput,
        )

    def get_tool_insights(self) -> StructuredTool:
        return self._make_tool(
            func=self.get_insights,
            name="get_instagram_media_insights",
            description="Obtiene métricas de rendimiento (insights) de una publicación de Instagram.",
            args_schema=MediaIdInput,
        )

    def get_tool_extended_profile(self) -> StructuredTool:
        return self._make_tool(
            func=self.get_extended_profile,
            name="get_instagram_extended_profile",
            description="Obtiene información extendida del perfil de Instagram del usuario autenticado.",
        )

    def get_tool_story_insights(self) -> StructuredTool:
        return self._make_tool(
            func=self.get_story_insights,
            name="get_instagram_story_insights",
            description="Obtiene las métricas de una historia específica de Instagram. Solo disponible mientras la historia esté activa.",
            args_schema=StoryIdInput,
        )

    def get_tool_followers_count(self) -> StructuredTool:
        return self._make_tool(
            func=self.get_followers_count,
            name="get_instagram_followers_count",
            description="Obtiene la cantidad de seguidores del usuario autenticado en Instagram.",
        )

    def get_tool_mentions(self) -> StructuredTool:
        return self._make_tool(
            func=self.get_mentions,
            name="get_instagram_mentions",
            description="Obtiene las publicaciones en las que el usuario autenticado ha sido mencionado en Instagram.",
        )

    def get_tool_hashtag_info(self) -> StructuredTool:
        return self._make_tool(
            func=self.get_hashtag_info,
            name="get_instagram_hashtag_info",
            description="Busca un hashtag en Instagram y devuelve su información básica, incluyendo su ID y nombre.",
            args_schema=HashtagInput,
        )

    def get_tool_conversations(self) -> StructuredTool:
        return self._make_tool(
            func=self.get_conversations,
            name="list_instagram_conversations",
            description="Obtiene la lista de conversaciones (chats) recientes del usuario autenticado en Instagram.",
        )

    def get_tool_messages(self) -> StructuredTool:
        return self._make_tool(
            func=self.get_messages,
            name="get_instagram_conversation_messages",
            description="Obtiene todos los mensajes de una conversación específica de Instagram a partir de su ID.",
            args_schema=ConversationIdInput,
        )

    def get_tool_create_comment(self) -> StructuredTool:
        return self._make_tool(
            func=self.create_comment,
            name="create_instagram_comment",
            description="Publica un comentario de texto en una publicación específica de Instagram a partir de su ID.",
            args_schema=CreateCommentInput,
        )

    def get_tool_reply_comment(self) -> StructuredTool:
        return self._make_tool(
            func=self.reply_comment,
            name="reply_instagram_comment",
            description="Publica una respuesta de texto a un comentario existente en Instagram a partir del ID del comentario.",
            args_schema=ReplyCommentInput,
        )

    def get_tool_delete_comment(self) -> StructuredTool:
        return self._make_tool(
            func=self.delete_comment,
            name="delete_instagram_comment",
            description="Elimina un comentario hecho por la cuenta autenticada en Instagram a partir del ID del comentario.",
            args_schema=DeleteCommentInput,
        )

    def get_tool_like_media(self) -> StructuredTool:
        return self._make_tool(
            func=self.like_media,
            name="like_instagram_media",
            description="Da 'me gusta' a una publicación específica de Instagram a partir de su ID.",
            args_schema=MediaIdInput,
        )

    def get_tool_unlike_media(self) -> StructuredTool:
        return self._make_tool(
            func=self.unlike_media,
            name="unlike_instagram_media",
            description="Quita el 'me gusta' de una publicación específica de Instagram a partir de su ID.",
            args_schema=MediaIdInput,
        )

    def get_tool_send_message(self) -> StructuredTool:
        return self._make_tool(
            func=self.send_message,
            name="send_instagram_message",
            description="Envía un mensaje de texto directo (DM) a un usuario en Instagram a partir de su ID.",
            args_schema=SendMessageInput,
        )

    def get_tool_mark_message_read(self) -> StructuredTool:
        return self._make_tool(
            func=self.mark_message_read,
            name="mark_instagram_messages_read",
            description="Marca todos los mensajes de una conversación específica de Instagram como leídos.",
            args_schema=ConversationIdInput,
        )

    def get_tool_update_bio(self) -> StructuredTool:
        return self._make_tool(
            func=self.update_bio,
            name="update_instagram_bio",
            description="Actualiza la biografía del perfil de Instagram autenticado con el texto proporcionado.",
            args_schema=UpdateBioInput,
        )

    def get_tool_update_comment(self) -> StructuredTool:
        return self._make_tool(
            func=self.update_comment,
            name="edit_instagram_comment",
            description="Edita el texto de un comentario existente en Instagram a partir de su ID.",
            args_schema=UpdateCommentInput,
        )

    def get_tool_reply_message(self) -> StructuredTool:
        return self._make_tool(
            func=self.reply_message,
            name="reply_instagram_message",
            description="Envía una respuesta de texto dentro de una conversación existente de Instagram.",
            args_schema=ReplyMessageInput,
        )

    def get_tool_set_auto_reply(self) -> StructuredTool:
        return self._make_tool(
            func=self.set_auto_reply,
            name="set_instagram_auto_reply",
            description="Configura una respuesta automática de texto para los mensajes directos en Instagram.",
            args_schema=AutoReplyInput,
        )

    def get_all_tools(self) -> List[Any]:
        """Registro para inyectar al agente de LangGraph"""
        return [
            self.get_tool_user_profile(),
            self.get_tool_media_from_account(),
            self.get_tool_media_details(),
            self.get_tool_comments(),
            self.get_tool_insights(),
            self.get_tool_extended_profile(),
            self.get_tool_story_insights(),
            self.get_tool_followers_count(),
            self.get_tool_mentions(),
            self.get_tool_hashtag_info(),
            self.get_tool_conversations(),
            self.get_tool_messages(),
            self.get_tool_create_comment(),
            self.get_tool_reply_comment(),
            self.get_tool_delete_comment(),
            self.get_tool_like_media(),
            self.get_tool_unlike_media(),
            self.get_tool_send_message(),
            self.get_tool_mark_message_read(),
            self.get_tool_update_bio(),
            self.get_tool_update_comment(),
            self.get_tool_reply_message(),
            self.get_tool_set_auto_reply(),
        ]


if __name__ == "__main__":
    logger.info("Modulo InstagramTool inicializado.")
