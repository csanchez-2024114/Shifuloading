"""
Threads OAuth 2.0 
Migrated to Secure OAuth Vault
"""
import os
import jwt
import secrets
import logging
import urllib.parse
import requests
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from app.database import get_current_user, get_db, SECRET_KEY
from app.core.constants import Collections
try:
    from app.core.security import encrypt_data
except ImportError:
    logger = logging.getLogger(__name__)
    logger.warning('Módulo de encriptación no encontrado. Se usará texto plano (MODO DEV).')
    encrypt_data = lambda x: x
logger = logging.getLogger('auth.threads')
router = APIRouter()
THREADS_AUTH_URL = 'https://threads.net/oauth/authorize'
THREADS_TOKEN_URL = 'https://graph.threads.net/oauth/access_token'
THREADS_ME_URL = 'https://graph.threads.net/v1/me'
THREADS_SCOPES = ['threads_basic', 'threads_content_publish']
FRONTEND_REDIRECT_URL = os.getenv('FRONTEND_REDIRECT_URL', 'https://hypershifu.com/chat')
THREADS_CLIENT_ID = os.getenv('THREADS_CLIENT_ID')
THREADS_CLIENT_SECRET = os.getenv('THREADS_CLIENT_SECRET')
THREADS_REDIRECT_URI = os.getenv('THREADS_REDIRECT_URI')

@router.get('/login')
async def login(user: dict=Depends(get_current_user)):
    user_id = str(user.get('_id', user.get('id', '')))
    correo = user.get('correo') or user.get('email', '')
    if not user_id or not correo:
        raise HTTPException(status_code=401, detail='Usuario inválido o sin correo')
    if not THREADS_CLIENT_ID or not THREADS_REDIRECT_URI:
        logger.error('Credenciales de Threads faltantes en el servidor')
        raise HTTPException(status_code=500, detail='Server misconfiguration')
    nonce = secrets.token_urlsafe(32)
    state_payload = {'u': user_id, 'email': correo, 'correo': correo, 'exp': datetime.now(timezone.utc).timestamp() + 600}
    state = jwt.encode(state_payload, SECRET_KEY, algorithm='HS256')
    params = {'client_id': THREADS_CLIENT_ID, 'redirect_uri': THREADS_REDIRECT_URI, 'scope': ','.join(THREADS_SCOPES), 'response_type': 'code', 'state': state, 'auth_type': 'reauthenticate'}
    auth_url = f'{THREADS_AUTH_URL}?{urllib.parse.urlencode(params)}'
    return JSONResponse({'url': auth_url})

@router.get('/callback')
async def callback(request: Request, db=Depends(get_db)):
    state_jwt = request.query_params.get('state')
    code = request.query_params.get('code')
    error = request.query_params.get('error')
    if error:
        logger.warning(f'Threads Auth Error: {error}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=auth_failed')
    user_id, correo = (None, None)
    if state_jwt:
        try:
            payload = jwt.decode(state_jwt, SECRET_KEY, algorithms=['HS256'])
            user_id = payload.get('u')
            correo = payload.get('correo') or payload.get('email')
        except Exception as e:
            logger.warning(f'Invalid state JWT en Threads: {e}')
    if not user_id or not correo:
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=session_lost')
    if not code:
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=missing_code')
    email_safe = correo.strip().lower()
    data = {'client_id': THREADS_CLIENT_ID, 'client_secret': THREADS_CLIENT_SECRET, 'grant_type': 'authorization_code', 'redirect_uri': THREADS_REDIRECT_URI, 'code': code}
    try:
        token_resp = requests.post(THREADS_TOKEN_URL, data=data, timeout=15)
        token_json = token_resp.json()
    except requests.RequestException as e:
        logger.error(f'Threads Network Error (Token): {e}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=token_exchange_network_error')
    if 'access_token' not in token_json:
        logger.error(f'Threads token error: {token_json}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=token_exchange_failed')
    access_token = token_json['access_token']
    me_data = {}
    try:
        me_resp = requests.get(THREADS_ME_URL, params={'fields': 'id,username,name,threads_profile_picture_url', 'access_token': access_token}, timeout=10)
        if me_resp.status_code == 200:
            me_data = me_resp.json()
    except requests.RequestException as e:
        logger.warning(f'Error fetching Threads /me: {e}')
    threads_account_id = me_data.get('id') or token_json.get('user_id')
    if not threads_account_id or threads_account_id == 'unknown':
        logger.error('Threads Error: No se pudo obtener el ID de Threads del usuario.')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=missing_provider_id')
    now_utc = datetime.now(timezone.utc)
    encrypted_token = encrypt_data(access_token) if access_token else None
    threads_name = me_data.get('name') or me_data.get('username', '')
    threads_avatar = me_data.get('threads_profile_picture_url', '')
    new_account_doc = {'user_id': str(user_id), 'provider': 'threads', 'account_id': threads_account_id, 'access_token': encrypted_token, 'refresh_token': 'n/a', 'expires_in': 3600, 'status': 'active', 'timestamp': now_utc.strftime('%Y-%m-%d %H:%M:%S'), 'metadata': {'threads_user_id': threads_account_id, 'name': threads_name, 'avatar': threads_avatar, 'connected_at': now_utc.isoformat()}}
    try:
        await db[Collections.USER_CONNECTED_ACCOUNTS].update_one({'user_id': str(user_id), 'provider': 'threads', 'account_id': threads_account_id}, {'$set': new_account_doc}, upsert=True)
    except Exception as e:
        logger.error(f'Error guardando Threads en vault: {e}', exc_info=True)
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=database_error')
    logger.info(f'Threads conectado exitosamente en bóveda para {email_safe}')
    return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?threads_status=connected')

@router.get('/status')
def status():
    return JSONResponse({'connected': True})

@router.delete('')
def disconnect():
    return JSONResponse({'success': True})
