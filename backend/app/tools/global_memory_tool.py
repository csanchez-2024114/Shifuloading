import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from bson import json_util
from dotenv import load_dotenv
from langchain_core.tools import StructuredTool
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field
from app.database import get_async_database
from app.core.db_utils import canonicalize_email
from app.core.constants import Collections
load_dotenv()
logger = logging.getLogger(__name__)

class SavePreferenceInput(BaseModel):
    key: str = Field(..., description='Clave de preferencia, ej: tono, idioma')
    value: Any = Field(..., description='Valor de la preferencia')

class DummyInput(BaseModel):
    dummy: Optional[str] = None

class MemoryUserPreferencesToolProvider:

    def __init__(self, user_email: str, db: Optional[AsyncIOMotorDatabase]=None):
        self.user_email = canonicalize_email(user_email)
        self.db = db

    @property
    def preferences_collection(self):
        return (self.db or get_async_database())[Collections.MEMORY_USERS_PREFERENCES]

    def get_tool_save_preference(self):
        return StructuredTool.from_function(name='memory_users_preferences_save', description="GUARDAR una nueva preferencia del usuario. USA ESTA HERRAMIENTA CUANDO el usuario QUIERA GUARDAR o ESTABLECER una preferencia como: 'mi idioma favorito es...', 'prefiero tono formal', 'me gusta el color azul', 'configura mi idioma a inglés'. NO USAR para consultar preferencias existentes.", func=self.save_preference_sync, coroutine=self.save_preference, args_schema=SavePreferenceInput)

    async def save_preference(self, key: str, value: Any) -> Dict[str, Any]:
        logger.debug(f"Guardando preferencia '{key}' para {self.user_email}")
        now_utc = datetime.now(timezone.utc)
        try:
            await self.preferences_collection.update_one({'$or': [{'correo': self.user_email}, {'email': self.user_email}]}, {'$set': {f'preferencias.{key}': value, 'updated_at': now_utc}, '$setOnInsert': {'correo': self.user_email, 'email': self.user_email, 'created_at': now_utc}, '$push': {'historial': {'key': key, 'value': value, 'timestamp': now_utc}}}, upsert=True)
            return {'success': True, 'correo': self.user_email, 'updated': {key: value}}
        except Exception as e:
            logger.error(f'Error de BD guardando preferencia para {self.user_email}: {str(e)}')
            return {'success': False, 'error': 'No se pudo guardar la preferencia debido a un error interno de base de datos.'}

    def save_preference_sync(self, key: str, value: Any) -> Dict[str, Any]:
        return self._run_sync_bridge(self.save_preference(key, value))

    def get_tool_get_preferences(self):
        return StructuredTool.from_function(name='memory_users_preferences_get', description="CONSULTAR u OBTENER las preferencias guardadas del usuario. USA ESTA HERRAMIENTA CUANDO el usuario QUIERA VER, CONSULTAR, o LEER sus preferencias existentes como: 'muéstrame mis preferencias', 'qué preferencias tengo guardadas?', 'dime mis preferencias', 'qué idioma tengo configurado?', 'cómo tengo configurado mi tono?'. NO USAR para guardar nuevas preferencias.", func=self.get_preferences_sync, coroutine=self.get_preferences, args_schema=DummyInput)

    async def get_preferences(self, dummy: Optional[str]=None) -> Dict[str, Any]:
        logger.debug(f'Consultando preferencias para {self.user_email}')
        try:
            user_prefs = await self.preferences_collection.find_one({'$or': [{'correo': self.user_email}, {'email': self.user_email}]})
            if not user_prefs:
                return {'success': True, 'correo': self.user_email, 'preferencias': {}}
            return {'success': True, 'correo': self.user_email, 'preferencias': json_util.loads(json_util.dumps(user_prefs.get('preferencias', {})))}
        except Exception as e:
            logger.error(f'Error de BD obteniendo preferencias para {self.user_email}: {str(e)}')
            return {'success': False, 'error': 'No se pudieron obtener las preferencias debido a un error interno.'}

    def get_preferences_sync(self, dummy: Optional[str]=None) -> Dict[str, Any]:
        return self._run_sync_bridge(self.get_preferences(dummy))

    @staticmethod
    def _run_sync_bridge(coroutine):
        """
        Puente de seguridad. LangChain puede intentar invocar herramientas de forma síncrona.
        Si estamos en un event loop activo, fallará intencionalmente pidiendo 'ainvoke'.
        Si no hay loop, lo crea y lo corre (útil para tests o workers).
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coroutine)
        raise RuntimeError("CRÍTICO: Intentaste ejecutar una herramienta asíncrona de forma bloqueante. Asegúrate de usar 'await agent.ainvoke()' en lugar de 'agent.invoke()'.")
