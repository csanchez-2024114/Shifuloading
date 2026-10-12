"""
Brevo API Key Integration Module
"""
import logging
import requests
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from app.database import get_current_user, get_db
from app.core.constants import Collections
try:
    from app.core.security import encrypt_data
except ImportError:
    logger = logging.getLogger(__name__)
    logger.warning('Módulo de encriptación no encontrado. Se usará texto plano (MODO DEV).')
    encrypt_data = lambda x: x
router = APIRouter()
logger = logging.getLogger('auth.brevo')

class BrevoKeyPayload(BaseModel):
    api_key: str

@router.post('/key')
async def save_brevo_key(payload: BrevoKeyPayload, user: dict=Depends(get_current_user), db=Depends(get_db)):
    user_id = str(user.get('_id', user.get('id', '')))
    headers = {'api-key': payload.api_key, 'Accept': 'application/json'}
    try:
        user_resp = requests.get('https://api.brevo.com/v3/account', headers=headers, timeout=10)
        if user_resp.status_code != 200:
            logger.warning(f'Rechazo de Brevo al validar API Key: {user_resp.text}')
            raise HTTPException(status_code=400, detail='La API Key es inválida o ha expirado.')
        user_data = user_resp.json()
    except requests.RequestException as e:
        logger.error(f'Error de red contactando a Brevo: {e}')
        raise HTTPException(status_code=500, detail='Error conectando con los servidores de Brevo.')
    brevo_email = user_data.get('email', 'unknown_account')
    company_name = user_data.get('companyName', 'Unknown')
    encrypted_key = encrypt_data(payload.api_key)
    now_utc = datetime.now(timezone.utc)
    new_account_doc = {'user_id': user_id, 'provider': 'brevo', 'account_id': brevo_email, 'access_token': encrypted_key, 'refresh_token': 'n/a', 'status': 'active', 'timestamp': now_utc.strftime('%Y-%m-%d %H:%M:%S'), 'metadata': {'brevo_email': brevo_email, 'company': company_name, 'auth_type': 'api_key', 'connected_at': now_utc.isoformat()}}
    try:
        await db[Collections.USER_CONNECTED_ACCOUNTS].update_one({'user_id': user_id, 'provider': 'brevo', 'account_id': brevo_email}, {'$set': new_account_doc, '$setOnInsert': {'created_at': now_utc}}, upsert=True)
    except Exception as e:
        logger.error(f'Error en DB guardando Brevo V2: {e}', exc_info=True)
        raise HTTPException(status_code=500, detail='Error interno guardando la integración.')
    logger.info(f'Brevo API Key validada y guardada para cuenta: {brevo_email}')
    return JSONResponse({'success': True, 'message': 'Brevo conectado exitosamente.'})
