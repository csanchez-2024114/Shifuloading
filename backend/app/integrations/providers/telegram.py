"""
Telegram Authentication Module (Widget Login).
Migrated to Secure OAuth Vault
Verifies HMAC-SHA256 signature from Telegram Login Widget and persists user data.
"""
import os
import hmac
import hashlib
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.database import get_current_user, get_db
from app.core.constants import Collections
logger = logging.getLogger('auth.telegram')
router = APIRouter()
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

class TelegramPayload(BaseModel):
    id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    photo_url: str | None = None
    auth_date: int
    hash: str
    model_config = {'extra': 'allow'}

def verify_telegram_auth(data: dict) -> bool:
    """Verifica la firma HMAC-SHA256 enviada por el widget de Telegram."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error('TELEGRAM_BOT_TOKEN no está configurado en el entorno.')
        return False
    auth_data = data.copy()
    received_hash = auth_data.pop('hash', None)
    if not received_hash:
        return False
    data_check_list = [f'{k}={v}' for k, v in sorted(auth_data.items()) if v is not None]
    data_check_string = '\n'.join(data_check_list)
    secret_key = hashlib.sha256(TELEGRAM_BOT_TOKEN.encode()).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(calculated_hash, received_hash)

@router.post('/callback')
async def telegram_callback(payload: TelegramPayload, user: dict=Depends(get_current_user), db=Depends(get_db)):
    """
    Recibe payload desde Telegram Widget + JWT del Frontend.
    Verifica firma HMAC-SHA256 y guarda en la Bóveda Segura de forma asíncrona.
    """
    user_id = str(user.get('_id', user.get('id', '')))
    correo = user.get('correo') or user.get('email', '')
    if not user_id or not correo:
        raise HTTPException(status_code=401, detail='Usuario inválido o sin correo')
    email_safe = correo.strip().lower()
    data_dict = payload.model_dump(exclude_none=True)
    if not verify_telegram_auth(data_dict):
        logger.warning(f'Firma de Telegram inválida detectada para el usuario {email_safe}')
        raise HTTPException(status_code=401, detail='Firma de Telegram inválida o alterada')
    telegram_user_id = str(payload.id)
    now_utc = datetime.now(timezone.utc)
    new_account_doc = {'user_id': user_id, 'provider': 'telegram', 'account_id': telegram_user_id, 'access_token': 'n/a', 'refresh_token': 'n/a', 'status': 'active', 'timestamp': now_utc.strftime('%Y-%m-%d %H:%M:%S'), 'metadata': {'telegram_id': telegram_user_id, 'username': payload.username or 'unknown', 'first_name': payload.first_name or 'unknown', 'last_name': payload.last_name or 'unknown', 'photo_url': payload.photo_url or '', 'auth_date': payload.auth_date, 'connected_at': now_utc.isoformat()}}
    try:
        await db[Collections.USER_CONNECTED_ACCOUNTS].update_one({'user_id': user_id, 'provider': 'telegram', 'account_id': telegram_user_id}, {'$set': new_account_doc, '$setOnInsert': {'created_at': now_utc}}, upsert=True)
    except Exception as e:
        logger.error(f'Error en base de datos al guardar Telegram: {e}', exc_info=True)
        raise HTTPException(status_code=500, detail='Error interno al persistir la integración')
    logger.info(f'Integración de Telegram (@{payload.username}) conectada en bóveda para {email_safe}')
    return {'status': 'success', 'message': 'Telegram conectado exitosamente a la bóveda'}

@router.get('/status')
def status():
    return {'connected': True}

@router.delete('')
def disconnect():
    return {'success': True}
