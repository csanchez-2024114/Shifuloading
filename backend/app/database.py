import os
import asyncio
import inspect
import logging
from typing import Optional, Any, Dict
from motor.motor_asyncio import AsyncIOMotorClient
from fastapi import Request, HTTPException, Depends, status
from jose import jwt, JWTError
from bson import ObjectId
from bson.errors import InvalidId
from config import Config
from app.core.mongo import mongo_manager
try:
    from app.core.security import decrypt_data
except ImportError:
    logger = logging.getLogger(__name__)
    logger.warning('CRÍTICO: Módulo app.core.security no encontrado. Se usará modo texto plano (FALLBACK DE DESARROLLO).')
    decrypt_data = lambda x: x
logger = logging.getLogger(__name__)
SECRET_KEY = Config.SECRET_KEY
ALGORITHM = 'HS256'
MONGO_URI = Config.MONGO_URI
MONGO_DB_NAME = Config.MONGO_DB_NAME
_client: Optional[AsyncIOMotorClient] = None

def _current_mongo_uri() -> str:
    uri = os.getenv('MONGO_URI') or MONGO_URI
    if not uri:
        raise ValueError('Variables de entorno para MONGO_URI no están configuradas.')
    return uri

def _current_mongo_db_name() -> str:
    db_name = os.getenv('MONGO_DB_NAME') or MONGO_DB_NAME
    if not db_name:
        raise ValueError('Variables de entorno para MONGO_DB_NAME no están configuradas.')
    return db_name

def get_db(request: Request) -> Any:
    """Inyector de base de datos. Prioriza el estado de la aplicación (FastAPI Lifespan)."""
    db = getattr(request.app.state, 'db', None)
    if db is None:
        logger.error('La base de datos no fue inicializada en el estado de la aplicación.')
        raise RuntimeError('Database connection not initialized in app state.')
    return db

async def get_current_user(request: Request, db_conn: Any=Depends(get_db)) -> dict:
    """Dependencia de Seguridad Global: Extrae, verifica JWT y retorna usuario de DB."""
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='No se proporcionó un token de autenticación válido.')
    token = auth_header.split(' ')[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get('user_id')
        if not user_id:
            raise HTTPException(status_code=401, detail="Token malformado: claim 'user_id' ausente.")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Token inválido o expirado.')
    try:
        user_oid = ObjectId(user_id)
    except InvalidId:
        raise HTTPException(status_code=401, detail='El ID del token tiene un formato inválido.')
    try:
        user = await db_conn['users'].find_one({'_id': user_oid}, {'password': 0})
        if not user:
            raise HTTPException(status_code=404, detail='Usuario no encontrado en el sistema.')
        user['id'] = str(user['_id'])
        return user
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f'Error en validación de identidad asíncrona: {e}', exc_info=True)
        raise HTTPException(status_code=500, detail='Error interno del servidor al validar credenciales.')

def _decrypt_integration_fields(provider: str, entry: Dict[str, Any], email: str) -> Dict[str, Any]:
    """Desencripta tokens de manera segura y mantiene el valor original (raw) en caso de fallo."""
    result = dict(entry)
    _SKIP_VALUES = {'n/a', '', None}
    for field in ('token', 'refresh_token', 'access_token'):
        raw_value = result.get(field)
        if raw_value in _SKIP_VALUES:
            continue
        try:
            result[field] = decrypt_data(str(raw_value))
        except Exception:
            logger.debug(f'[Vault] Valor en texto plano detectado para {provider}.{field} (Usuario: {email}).')
    return result

def _normalize_integrations(raw: Dict[str, Any], source: str, email: str) -> Dict[str, Any]:
    """
    Normaliza el diccionario de integraciones y aplica 'Key Mirroring'.
    Previene KeyError asegurando compatibilidad hacia atrás.
    """
    normalized: Dict[str, Any] = {}
    for provider, data in raw.items():
        if not isinstance(data, dict):
            normalized[provider] = data
            continue
        entry = dict(data)
        if source == 'vault':
            entry = _decrypt_integration_fields(provider, entry, email)
        main_token = entry.get('token') or entry.get('access_token')
        if main_token:
            entry['token'] = main_token
            entry['access_token'] = main_token
        normalized[provider] = entry
    return normalized

async def get_user_vault_with_fallback(email: str, db_conn: Any, account_id: Optional[str]=None) -> Dict[str, Any]:
    """
    Motor Central de Lectura OAuth.
    Soporta fallback legacy y la firma multicuenta requerida por LangGraph.

    Args:
        email: Correo del usuario a consultar.
        db_conn: Conexión asíncrona de base de datos.
        account_id: (Opcional) ID específico de la cuenta conectada.
    """
    if not email:
        logger.warning('[VaultFallback] Intento de consulta sin correo válido.')
        return {}
    email_safe: str = email.strip().lower()
    try:
        vault_doc = await db_conn['oauth_vault'].find_one({'$or': [{'correo': email_safe}, {'email': email_safe}]})
        if vault_doc and 'integrations' in vault_doc:
            return _normalize_integrations(vault_doc['integrations'], source='vault', email=email_safe)
    except Exception as e:
        logger.error(f'[VaultFallback] Error crítico leyendo oauth_vault para {email_safe}: {e}', exc_info=True)
    try:
        legacy_doc = await db_conn['users'].find_one({'$or': [{'correo': email_safe}, {'email': email_safe}]})
        if legacy_doc and 'integrations' in legacy_doc:
            logger.info(f'[VaultFallback] Usando Legacy Integrations para {email_safe}')
            return _normalize_integrations(legacy_doc['integrations'], source='legacy', email=email_safe)
    except Exception as e:
        logger.error(f'[VaultFallback] Error crítico leyendo legacy db para {email_safe}: {e}', exc_info=True)
    return {}

def get_async_client() -> AsyncIOMotorClient:
    """Retorna o inicializa el cliente asíncrono de MongoDB."""
    if mongo_manager.client is not None:
        return mongo_manager.client
    global _client
    if _client is None:
        mongo_uri = _current_mongo_uri()
        _client = AsyncIOMotorClient(mongo_uri)
    return _client

def get_async_database():
    """Retorna la instancia de la base de datos activa."""
    if mongo_manager.db is not None:
        return mongo_manager.db
    return get_async_client().get_database(_current_mongo_db_name())

def decrypt_integration_fields(provider: str, entry: Dict[str, Any], email: str) -> Dict[str, Any]:
    """English alias for `_decrypt_integration_fields`.

    Keeps original behavior and signature but with English parameter name.
    """
    return _decrypt_integration_fields(provider, entry, email)

def normalize_integrations(raw: Dict[str, Any], source: str, email: str) -> Dict[str, Any]:
    """English alias for `_normalize_integrations`."""
    return _normalize_integrations(raw, source, email)

async def get_user_vault_with_fallback_by_email(email: str, db_conn: Any, account_id: Optional[str]=None) -> Dict[str, Any]:
    """English alias for `get_user_vault_with_fallback`.

    Non-invasive async wrapper to keep compatibility while migrating parameter names.
    """
    return await get_user_vault_with_fallback(email, db_conn, account_id)
