"""
Salesforce OAuth 2.0
Migrated to Secure OAuth Vault
"""
import os
import jwt
import secrets
import logging
import requests
import urllib.parse
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from app.database import get_current_user, get_db, SECRET_KEY
from app.core.constants import Collections
try:
    from app.core.security import encrypt_data
except ImportError:
    logger = logging.getLogger(__name__)
    logger.warning('Módulo de encriptación no encontrado. Se usará texto plano (MODO DEV).')
    encrypt_data = lambda x: x
logger = logging.getLogger('auth.salesforce')
router = APIRouter()
SF_CLIENT_ID = os.getenv('SALESFORCE_CLIENT_ID')
SF_CLIENT_SECRET = os.getenv('SALESFORCE_CLIENT_SECRET')
SF_REDIRECT_URI = os.getenv('SALESFORCE_REDIRECT_URI')
SF_AUTH_URL = 'https://login.salesforce.com/services/oauth2/authorize'
SF_TOKEN_URL = 'https://login.salesforce.com/services/oauth2/token'
FRONTEND_REDIRECT_URL = os.getenv('FRONTEND_REDIRECT_URL', 'https://hypershifu.com/chat')
SF_SCOPES = ['api', 'refresh_token']

@router.get('/login')
async def login(user: dict=Depends(get_current_user)):
    user_id = str(user.get('_id', user.get('id', '')))
    correo = user.get('correo') or user.get('email', '')
    if not user_id or not correo:
        raise HTTPException(status_code=401, detail='Usuario inválido o sin correo')
    nonce = secrets.token_urlsafe(32)
    state_payload = {'nonce': nonce, 'user_id': user_id, 'correo': correo}
    state = jwt.encode(state_payload, SECRET_KEY, algorithm='HS256')
    params = {'response_type': 'code', 'client_id': SF_CLIENT_ID, 'redirect_uri': SF_REDIRECT_URI, 'scope': ' '.join(SF_SCOPES), 'state': state, 'prompt': 'login consent'}
    auth_url = f'{SF_AUTH_URL}?{urllib.parse.urlencode(params)}'
    return JSONResponse({'url': auth_url})

@router.get('/callback')
async def callback(request: Request, db=Depends(get_db)):
    state_jwt = request.query_params.get('state')
    code = request.query_params.get('code')
    error = request.query_params.get('error')
    error_description = request.query_params.get('error_description', '')
    if error:
        logger.warning(f'Salesforce Auth Error: {error} - {error_description}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=auth_failed')
    user_id, correo = (None, None)
    if state_jwt:
        try:
            payload = jwt.decode(state_jwt, SECRET_KEY, algorithms=['HS256'])
            user_id = payload.get('user_id')
            correo = payload.get('correo')
        except Exception as e:
            logger.warning(f'Invalid state JWT en Salesforce: {e}')
    if not user_id or not correo:
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=session_lost')
    if not code:
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=missing_code')
    email_safe = correo.strip().lower()
    data = {'grant_type': 'authorization_code', 'client_id': SF_CLIENT_ID, 'client_secret': SF_CLIENT_SECRET, 'code': code, 'redirect_uri': SF_REDIRECT_URI}
    try:
        token_resp = requests.post(SF_TOKEN_URL, data=data, timeout=15)
        token_res = token_resp.json()
    except requests.RequestException as e:
        logger.error(f'Salesforce Network Error: {e}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=token_exchange_network_error')
    if 'access_token' not in token_res:
        logger.error(f'Salesforce Token Error: {token_res}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=token_exchange_failed')
    access_token = token_res.get('access_token')
    refresh_token = token_res.get('refresh_token')
    sf_id_url = token_res.get('id', '')
    sf_user_id = sf_id_url.split('/')[-1] if sf_id_url else None
    if not sf_user_id:
        logger.error('Salesforce Error: No se pudo extraer el User ID de la respuesta.')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=missing_provider_id')
    encrypted_token = encrypt_data(access_token) if access_token else None
    encrypted_refresh = encrypt_data(refresh_token) if refresh_token else None
    now_utc = datetime.now(timezone.utc)
    new_account_doc = {'user_id': str(user_id), 'provider': 'salesforce', 'account_id': sf_user_id, 'access_token': encrypted_token, 'refresh_token': encrypted_refresh, 'status': 'active', 'timestamp': now_utc.strftime('%Y-%m-%d %H:%M:%S'), 'metadata': {'salesforce_user_id': sf_user_id, 'instance_url': token_res.get('instance_url'), 'id_url': sf_id_url, 'signature': token_res.get('signature'), 'connected_at': now_utc.isoformat()}}
    try:
        await db[Collections.USER_CONNECTED_ACCOUNTS].update_one({'user_id': str(user_id), 'provider': 'salesforce', 'account_id': sf_user_id}, {'$set': new_account_doc, '$setOnInsert': {'created_at': now_utc}}, upsert=True)
    except Exception as e:
        logger.error(f'Error en base de datos al guardar Salesforce: {e}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=database_error')
    logger.info(f'Salesforce conectado exitosamente en bóveda para {email_safe}')
    return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?salesforce_status=connected')

@router.get('/status')
def status():
    return JSONResponse({'connected': True})

@router.delete('')
def disconnect():
    return JSONResponse({'success': True})


# ── Service Layer ──────────────────────────────────────────────────────────────

