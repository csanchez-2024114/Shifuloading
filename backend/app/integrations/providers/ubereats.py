"""
Uber Eats OAuth 2.0 Authentication Module — FastAPI Version
Migrated to Secure Async OAuth Vault (Single Source of Truth)
Supports SANDBOX and PRODUCTION environments.
"""
import os
import jwt
import secrets
import logging
import requests
import urllib.parse
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from app.database import get_current_user, get_db, SECRET_KEY
try:
    from app.core.security import encrypt_data
except ImportError:
    logger = logging.getLogger(__name__)
    logger.warning('Módulo de encriptación no encontrado. Se usará texto plano (MODO DEV).')
    encrypt_data = lambda x: x
logger = logging.getLogger('auth.ubereats')
router = APIRouter()
UBER_ENV = os.getenv('UBER_ENV', 'SANDBOX').upper()
if UBER_ENV == 'PRODUCTION':
    UBER_AUTH_URL = 'https://login.uber.com/oauth/v2/authorize'
    UBER_TOKEN_URL = 'https://login.uber.com/oauth/v2/token'
else:
    UBER_AUTH_URL = 'https://sandbox-login.uber.com/oauth/v2/authorize'
    UBER_TOKEN_URL = 'https://sandbox-login.uber.com/oauth/v2/token'
UBER_PROFILE_URL = 'https://api.uber.com/v1.2/me'
FRONTEND_REDIRECT_URL = os.getenv('FRONTEND_REDIRECT_URL', 'https://hypershifu.com/chat')
UBER_SCOPES = 'eats.store eats.order profile'

@router.get('/login')
async def login(user: dict=Depends(get_current_user)):
    """
    Inicia el flujo OAuth. Empaqueta el ID y el Correo del usuario
    en el token JWT para prevenir pérdida de sesión y CSRF.
    """
    user_id = str(user.get('_id', user.get('id', '')))
    correo = user.get('correo') or user.get('email', '')
    if not user_id or not correo:
        logger.warning('Intento de login UberEats sin correo o ID válido.')
        raise HTTPException(status_code=401, detail='Usuario inválido o sin correo')
    client_id = os.getenv('UBEREATS_CLIENT_ID')
    redirect_uri = os.getenv('UBEREATS_REDIRECT_URI')
    if not client_id or not redirect_uri:
        logger.error('Missing Uber Eats env config')
        raise HTTPException(status_code=500, detail='Server configuration error')
    nonce = secrets.token_urlsafe(32)
    state_payload = {'nonce': nonce, 'user_id': user_id, 'correo': correo, 'exp': datetime.now(timezone.utc).timestamp() + 600}
    state = jwt.encode(state_payload, SECRET_KEY, algorithm='HS256')
    params = {'client_id': client_id, 'redirect_uri': redirect_uri, 'state': state, 'scope': UBER_SCOPES, 'response_type': 'code'}
    auth_url = f'{UBER_AUTH_URL}?{urllib.parse.urlencode(params)}'
    return JSONResponse({'url': auth_url})

@router.get('/callback')
async def callback(request: Request, db=Depends(get_db)):
    """
    Recibe el código de Uber Eats, procesa tokens y perfil, y guarda
    todo en una única transacción asíncrona hacia oauth_vault.
    """
    state_jwt = request.query_params.get('state')
    code = request.query_params.get('code')
    error = request.query_params.get('error')
    if error:
        logger.warning(f'Uber Auth Failed: {error}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=auth_failed')
    if not state_jwt or not code:
        logger.warning('Callback de Uber Eats incompleto.')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=missing_parameters')
    user_id, correo = (None, None)
    try:
        payload = jwt.decode(state_jwt, SECRET_KEY, algorithms=['HS256'])
        user_id = payload.get('user_id')
        correo = payload.get('correo')
    except jwt.ExpiredSignatureError:
        logger.warning('State JWT de Uber Eats expirado')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=session_expired')
    except Exception as e:
        logger.warning(f'Invalid state JWT en Uber Eats: {e}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=session_lost')
    if not user_id or not correo:
        logger.warning('Fallo al recuperar identidad del state JWT de Uber Eats.')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=session_lost')
    email_safe = correo.strip().lower()
    data = {'client_id': os.getenv('UBEREATS_CLIENT_ID'), 'client_secret': os.getenv('UBEREATS_CLIENT_SECRET'), 'redirect_uri': os.getenv('UBEREATS_REDIRECT_URI'), 'grant_type': 'authorization_code', 'code': code}
    try:
        token_resp = requests.post(UBER_TOKEN_URL, data=data, timeout=15)
        token_json = token_resp.json()
    except requests.RequestException as e:
        logger.error(f'Uber API Network Error: {e}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=token_exchange_network_error')
    except ValueError:
        logger.error(f'Uber Invalid JSON Response: {token_resp.text}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=token_exchange_invalid_response')
    if 'access_token' not in token_json:
        logger.error(f'Uber Token Error: {token_json}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=token_exchange_failed')
    access_token = token_json.get('access_token')
    refresh_token = token_json.get('refresh_token')
    expires_in = token_json.get('expires_in', 2592000)
    user_data = {}
    try:
        headers = {'Authorization': f'Bearer {access_token}'}
        resp = requests.get(UBER_PROFILE_URL, headers=headers, timeout=10)
        if resp.status_code == 200:
            user_data = resp.json()
        else:
            logger.warning(f'Uber Profile HTTP Error: {resp.status_code}')
    except Exception as profile_err:
        logger.warning(f'No se pudo obtener perfil de Uber: {profile_err}')
    encrypted_token = encrypt_data(access_token) if access_token else None
    encrypted_refresh = encrypt_data(refresh_token) if refresh_token else None
    now = datetime.now(timezone.utc)
    integration_payload = {'token': encrypted_token, 'refresh_token': encrypted_refresh, 'uber_id': user_data.get('driver_id') or user_data.get('uuid', 'unknown_merchant'), 'first_name': user_data.get('first_name', 'Merchant'), 'email': user_data.get('email', ''), 'expires_in': expires_in, 'scope': token_json.get('scope'), 'environment': UBER_ENV, 'timestamp': now.strftime('%Y-%m-%d %H:%M:%S')}
    try:
        await db.oauth_vault.update_one({'correo': email_safe}, {'$set': {'integrations.UberEats': integration_payload, 'updated_at': now}, '$setOnInsert': {'created_at': now, 'user_id': user_id, 'provider': 'server_side_oauth', 'status': 'active'}}, upsert=True)
    except Exception as e:
        logger.error(f'Error guardando UberEats en vault para {email_safe}: {e}', exc_info=True)
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=database_error')
    logger.info(f'UberEats ({UBER_ENV}) conectado en Bóveda para {email_safe}')
    return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?ubereats_status=connected')

@router.get('/status')
def status():
    return JSONResponse({'connected': True})

@router.delete('')
def disconnect():
    return JSONResponse({'success': True})
