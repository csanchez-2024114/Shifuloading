"""
Mongo User Preferences Tool para LangGraph / LangChain
Migración a Bóveda Segura y Resiliencia V2.
- Uso estricto de ToolException y handle_tool_error=True.
- Logging estructurado para operaciones de Base de Datos.
- Salidas estandarizadas a JSON Strings.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional, Any
from bson import json_util
from langchain_core.tools import StructuredTool, ToolException
from pydantic import BaseModel, Field
from app.core.mongo import get_sync_database
from app.core.db_utils import find_user_by_email, update_user_preferences, canonicalize_email
logger = logging.getLogger('tools.preferences')
db = get_sync_database()

class SaveUserPreferenceInput(BaseModel):
    key: str = Field(..., alias='clave', description="Nombre de la preferencia (ej: 'tono', 'tema', 'idioma').")
    value: Any = Field(..., alias='valor', description="Valor de la preferencia (ej: 'amigable', 'oscuro', 'es').")

class GetPreferencesInput(BaseModel):
    query: Optional[str] = Field(default='', description='Parámetro opcional, dejar vacío.')

class MongoUserPreferencesToolProvider:

    def __init__(self, user_email: str | None=None):
        email_source = user_email
        canonical = canonicalize_email(email_source) or (email_source or '')
        self.user_email = canonical

    def save_user_preference(self, key: str, value: Any, query: str='') -> str:
        try:
            logger.info(f"[MongoUserPrefs] Guardando preferencia '{key}' para '{self.user_email}'")
            user = find_user_by_email(db, self.user_email)
            if not user:
                logger.warning(f"[MongoUserPrefs] Intento de guardado en usuario inexistente: '{self.user_email}'")
                raise ToolException(f"El usuario '{self.user_email}' no existe en la base de datos.")
            res = update_user_preferences(db, self.user_email, key, value)
            logger.info(f"[MongoUserPrefs] Preferencia guardada exitosamente: {key}={value} (matched={res.get('matched_count')})")
            return json.dumps({'status': 'success', 'mensaje': 'Preferencia guardada exitosamente.', 'updated': {key: value}}, ensure_ascii=False)
        except ToolException:
            raise
        except Exception as e:
            logger.error(f'[MongoUserPrefs] Error crítico guardando preferencia: {e}')
            raise ToolException(f'Error de base de datos al guardar preferencia: {str(e)}')

    def get_tool_save_preference(self) -> StructuredTool:
        return StructuredTool.from_function(name='save_user_preference', description='Guarda o actualiza una preferencia permanente del usuario autenticado en la base de datos. El correo NO se pide, ya está vinculado internamente. Ideal para: establecer el tono del bot, idioma, temas de UI, o gustos personales.', func=self.save_user_preference, args_schema=SaveUserPreferenceInput, handle_tool_error=True)

    def get_user_preferences(self, query: Optional[str]=None) -> str:
        try:
            logger.debug(f"[MongoUserPrefs] Consultando preferencias para '{self.user_email}'")
            user = find_user_by_email(db, self.user_email)
            if not user:
                logger.warning(f"[MongoUserPrefs] Intento de lectura de usuario inexistente: '{self.user_email}'")
                raise ToolException(f"Usuario '{self.user_email}' no existe en la base de datos.")
            raw_prefs = user.get('preferencias') or user.get('preferences') or {}
            clean_prefs = json_util.loads(json_util.dumps(raw_prefs))
            return json.dumps({'status': 'success', 'email': self.user_email, 'preferencias': clean_prefs, 'preferences': clean_prefs}, ensure_ascii=False)
        except ToolException:
            raise
        except Exception as e:
            logger.error(f'[MongoUserPrefs] Error crítico obteniendo preferencias: {e}')
            raise ToolException(f'Error de base de datos al obtener preferencias: {str(e)}')

    def get_tool_get_preferences(self) -> StructuredTool:
        return StructuredTool.from_function(name='get_user_preferences', description='Devuelve todas las preferencias y configuraciones guardadas del usuario autenticado. No requiere parámetros. Úsalo para saber cómo el usuario prefiere ser tratado o sus gustos.', func=self.get_user_preferences, args_schema=GetPreferencesInput, handle_tool_error=True)
