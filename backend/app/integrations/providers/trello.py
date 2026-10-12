import os
import logging
import requests
import urllib.parse
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel
from app.database import get_current_user, get_db
from app.core.constants import Collections
try:
    from app.core.security import encrypt_data
except ImportError:
    logger = logging.getLogger(__name__)
    logger.warning('Módulo de encriptación no encontrado. Se usará texto plano (MODO DEV).')
    encrypt_data = lambda x: x
logger = logging.getLogger('auth.trello')
router = APIRouter()
TRELLO_API_KEY = os.getenv('TRELLO_API_KEY')
TRELLO_REDIRECT_URI = os.getenv('TRELLO_REDIRECT_URI')
TRELLO_AUTHORIZE_URL = 'https://trello.com/1/authorize'
TRELLO_API_BASE = 'https://api.trello.com/1'
FRONTEND_REDIRECT_URL = os.getenv('FRONTEND_REDIRECT_URL', 'https://hypershifu.com/chat')

@router.get('/login')
async def login(user: dict=Depends(get_current_user)):
    """
    Genera la URL de autorización de Trello.
    Trello usa un flujo implicito/token, por lo que no enviamos un 'state' JWT,
    sino que el frontend captura el token en el fragmento (#token=).
    """
    params = {'expiration': 'never', 'name': 'Hyper Shifu', 'scope': 'read,write', 'response_type': 'token', 'key': TRELLO_API_KEY, 'return_url': TRELLO_REDIRECT_URI}
    auth_url = f'{TRELLO_AUTHORIZE_URL}?{urllib.parse.urlencode(params)}'
    return JSONResponse({'url': auth_url})

@router.get('/callback')
async def callback(request: Request):
    """
    Redirección intermedia para Trello. 
    Redirige al frontend para que extraiga el token de la URL.
    """
    token = request.query_params.get('token')
    if not token:
        logger.warning('Trello Callback sin token. Redirigiendo con error.')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=missing_trello_token')
    return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?trello_temp_token={token}')

class TrelloTokenRequest(BaseModel):
    trello_token: str

@router.post('/token')
async def save_trello_token(data: TrelloTokenRequest, user: dict=Depends(get_current_user), db=Depends(get_db)):
    """Valida el token de Trello, lo encripta y lo guarda en la Bóveda Segura."""
    user_id = str(user.get('_id', user.get('id', '')))
    correo = user.get('correo') or user.get('email', '')
    if not user_id or not correo:
        raise HTTPException(status_code=401, detail='Usuario inválido o sin correo')
    email_safe = correo.strip().lower()
    access_token = data.trello_token
    user_url = f'{TRELLO_API_BASE}/members/me'
    params = {'key': TRELLO_API_KEY, 'token': access_token, 'fields': 'username,fullName,email,avatarUrl'}
    try:
        response = requests.get(user_url, params=params, timeout=10)
    except requests.RequestException as e:
        logger.error(f'Trello Network Error: {e}')
        raise HTTPException(status_code=502, detail='Error de conexión con Trello API')
    if response.status_code != 200:
        logger.error(f'Trello Token Validation Failed: {response.text}')
        raise HTTPException(status_code=400, detail='Token de Trello inválido')
    trello_user = response.json()
    trello_account_id = trello_user.get('id')
    if not trello_account_id:
        logger.error('Trello Error: No se pudo obtener el ID de usuario de Trello.')
        raise HTTPException(status_code=400, detail='No se pudo obtener el ID de Trello')
    encrypted_token = encrypt_data(access_token)
    now_utc = datetime.now(timezone.utc)
    new_account_doc = {'user_id': user_id, 'provider': 'trello', 'account_id': trello_account_id, 'access_token': encrypted_token, 'refresh_token': 'n/a', 'expires_in': 315360000, 'status': 'active', 'timestamp': now_utc.strftime('%Y-%m-%d %H:%M:%S'), 'metadata': {'trello_id': trello_account_id, 'username': trello_user.get('username'), 'name': trello_user.get('fullName'), 'email': trello_user.get('email'), 'avatar': trello_user.get('avatarUrl'), 'connected_at': now_utc.isoformat()}}
    try:
        await db[Collections.USER_CONNECTED_ACCOUNTS].update_one({'user_id': user_id, 'provider': 'trello', 'account_id': trello_account_id}, {'$set': new_account_doc, '$setOnInsert': {'created_at': now_utc}}, upsert=True)
    except Exception as e:
        logger.error(f'Error DB guardando Trello V2 para {email_safe}: {e}', exc_info=True)
        raise HTTPException(status_code=500, detail='Error interno al persistir la integración')
    logger.info(f'Trello conectado exitosamente en bóveda para {email_safe}')
    return JSONResponse({'success': True, 'message': 'Trello conectado exitosamente'})

@router.get('/status')
def status():
    return JSONResponse({'connected': True})

@router.delete('')
def disconnect():
    return JSONResponse({'success': True})
