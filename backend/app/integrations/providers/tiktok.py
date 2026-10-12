"""
TikTok OAuth 2.0 Authentication Module — FastAPI Version
Migrated to Secure Async OAuth Vault (Single Source of Truth)
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
from app.core.constants import Collections
try:
    from app.core.security import encrypt_data
except ImportError:
    logger = logging.getLogger(__name__)
    logger.warning('Módulo de encriptación no encontrado. Se usará texto plano (MODO DEV).')
    encrypt_data = lambda x: x
logger = logging.getLogger('auth.tiktok')
router = APIRouter()
TIKTOK_CLIENT_KEY = os.getenv('TIKTOK_CLIENT_KEY')
TIKTOK_CLIENT_SECRET = os.getenv('TIKTOK_CLIENT_SECRET')
TIKTOK_REDIRECT_URI = os.getenv('TIKTOK_REDIRECT_URI')
TIKTOK_AUTH_URL = 'https://www.tiktok.com/v2/auth/authorize/'
TIKTOK_TOKEN_URL = 'https://open.tiktokapis.com/v2/oauth/token/'
TIKTOK_USER_INFO_URL = 'https://open.tiktokapis.com/v2/user/info/'
TIKTOK_SCOPES = ['user.info.basic']
FRONTEND_REDIRECT_URL = os.getenv('FRONTEND_REDIRECT_URL', 'https://hypershifu.com/chat')

@router.get('/login')
async def login(user: dict=Depends(get_current_user)):
    """
    Inicia el flujo OAuth. Empaqueta el ID y el Correo del usuario
    en el token JWT para prevenir pérdida de sesión y CSRF.
    """
    user_id = str(user.get('_id', user.get('id', '')))
    correo = user.get('correo') or user.get('email', '')
    if not user_id or not correo:
        logger.warning('Intento de login TikTok sin correo o ID válido.')
        raise HTTPException(status_code=401, detail='Usuario inválido o sin correo')
    if not TIKTOK_CLIENT_KEY or not TIKTOK_REDIRECT_URI:
        logger.error('TikTok credentials missing in environment variables')
        raise HTTPException(status_code=500, detail='Server misconfiguration')
    nonce = secrets.token_urlsafe(32)
    state_payload = {'nonce': nonce, 'user_id': user_id, 'correo': correo, 'exp': datetime.now(timezone.utc).timestamp() + 600}
    state = jwt.encode(state_payload, SECRET_KEY, algorithm='HS256')
    params = {'client_key': TIKTOK_CLIENT_KEY, 'scope': ','.join(TIKTOK_SCOPES), 'response_type': 'code', 'redirect_uri': TIKTOK_REDIRECT_URI, 'state': state}
    auth_url = f'{TIKTOK_AUTH_URL}?{urllib.parse.urlencode(params)}'
    return JSONResponse({'url': auth_url})

@router.get('/callback')
async def callback(request: Request, db=Depends(get_db)):
    """
    Recibe el código de TikTok, procesa tokens y perfil, y guarda
    todo en una única transacción asíncrona hacia oauth_vault.
    """
    state_jwt = request.query_params.get('state')
    code = request.query_params.get('code')
    error = request.query_params.get('error')
    if error:
        logger.warning(f'TikTok Auth Error devuelto por API: {error}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=auth_failed')
    if not state_jwt or not code:
        logger.warning('Callback de TikTok incompleto.')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=missing_parameters')
    user_id, correo = (None, None)
    try:
        payload = jwt.decode(state_jwt, SECRET_KEY, algorithms=['HS256'])
        user_id = payload.get('user_id')
        correo = payload.get('correo')
    except jwt.ExpiredSignatureError:
        logger.warning('State JWT de TikTok expirado')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=session_expired')
    except Exception as e:
        logger.warning(f'Invalid state JWT en TikTok: {e}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=session_lost')
    if not user_id or not correo:
        logger.warning('Fallo al recuperar identidad del state JWT de TikTok.')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=session_lost')
    email_safe = correo.strip().lower()
    data = {'client_key': TIKTOK_CLIENT_KEY, 'client_secret': TIKTOK_CLIENT_SECRET, 'code': code, 'grant_type': 'authorization_code', 'redirect_uri': TIKTOK_REDIRECT_URI}
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    try:
        token_resp = requests.post(TIKTOK_TOKEN_URL, data=data, headers=headers, timeout=15)
        token_res = token_resp.json()
    except requests.RequestException as e:
        logger.error(f'TikTok Network Error (Token): {e}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=token_exchange_network_error')
    except ValueError:
        logger.error(f'TikTok Invalid JSON Response: {token_resp.text}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=token_exchange_invalid_response')
    if 'access_token' not in token_res:
        logger.error(f'TikTok Token Error: {token_resp.status_code} - {token_res}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=token_exchange_failed')
    access_token = token_res['access_token']
    refresh_token = token_res.get('refresh_token')
    expires_in = token_res.get('expires_in', 86400)
    open_id = token_res.get('open_id', '')
    display_name = 'unknown'
    avatar_url = ''
    try:
        user_fields = ['open_id', 'union_id', 'avatar_url', 'display_name']
        user_info_url = f"{TIKTOK_USER_INFO_URL}?fields={','.join(user_fields)}"
        user_resp = requests.get(user_info_url, headers={'Authorization': f'Bearer {access_token}'}, timeout=10)
        if user_resp.status_code == 200:
            tiktok_user = user_resp.json().get('data', {}).get('user', {})
            display_name = tiktok_user.get('display_name', 'unknown')
            avatar_url = tiktok_user.get('avatar_url', '')
        else:
            logger.warning(f'TikTok User Info HTTP Error: {user_resp.status_code}')
    except requests.RequestException as e:
        logger.warning(f'Error fetching TikTok user info: {e}')
    encrypted_token = encrypt_data(access_token) if access_token else None
    encrypted_refresh = encrypt_data(refresh_token) if refresh_token else None
    now_utc = datetime.now(timezone.utc)
    new_account_doc = {'user_id': str(user_id), 'provider': 'tiktok', 'account_id': open_id, 'access_token': encrypted_token, 'refresh_token': encrypted_refresh, 'expires_in': expires_in, 'status': 'active', 'timestamp': now_utc.strftime('%Y-%m-%d %H:%M:%S'), 'metadata': {'tiktok_open_id': open_id, 'name': display_name, 'avatar': avatar_url, 'connected_at': now_utc.isoformat()}}
    try:
        await db[Collections.USER_CONNECTED_ACCOUNTS].update_one({'user_id': str(user_id), 'provider': 'tiktok', 'account_id': open_id}, {'$set': new_account_doc, '$setOnInsert': {'created_at': now_utc}}, upsert=True)
    except Exception as e:
        logger.error(f'Error guardando TikTok en vault unificado para {email_safe}: {e}', exc_info=True)
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=database_error')
    logger.info(f'TikTok conectado exitosamente en bóveda para {email_safe}')
    return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?tiktok_status=connected')

@router.get('/status')
def status():
    return JSONResponse({'connected': True})

@router.delete('')
def disconnect():
    return JSONResponse({'success': True})
