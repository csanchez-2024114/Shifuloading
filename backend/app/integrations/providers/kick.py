"""
Kick OAuth 2.0 Authentication Module (PKCE Flow) — FastAPI Version
Migrated to Secure Async OAuth Vault
"""
import os
import jwt
import secrets
import logging
import requests
import hashlib
import base64
import urllib.parse
from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from app.database import get_current_user, get_db, SECRET_KEY
from app.core.constants import Collections
try:
    from app.core.security import encrypt_data
except ImportError:
    logger = logging.getLogger(__name__)
    logger.warning('Módulo de encriptación no encontrado. Se usará texto plano (MODO DEV).')
    encrypt_data = lambda x: x
logger = logging.getLogger('auth.kick')
router = APIRouter()
KICK_CLIENT_ID = os.getenv('KICK_CLIENT_ID')
KICK_CLIENT_SECRET = os.getenv('KICK_CLIENT_SECRET')
KICK_REDIRECT_URI = os.getenv('KICK_REDIRECT_URI')
KICK_AUTH_URL = 'https://kick.com/oauth/authorize'
KICK_TOKEN_URL = 'https://id.kick.com/oauth/token'
KICK_API_URL = 'https://api.kick.com/public/v1/users'
FRONTEND_REDIRECT_URL = os.getenv('FRONTEND_REDIRECT_URL', 'https://hypershifu.com/chat')
KICK_SCOPES = ['user:read', 'channel:read', 'streamkey:read']

def generate_code_verifier() -> str:
    return secrets.token_urlsafe(64)

def generate_code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip('=')

@router.get('/login')
async def login(user: dict=Depends(get_current_user)):
    user_id = str(user.get('_id', user.get('id', '')))
    correo = user.get('correo') or user.get('email', '')
    if not user_id or not correo:
        logger.warning(f'Intento de login Kick sin correo o ID válido.')
        raise HTTPException(status_code=401, detail='Usuario inválido o sin correo')
    nonce = secrets.token_urlsafe(32)
    code_verifier = generate_code_verifier()
    code_challenge = generate_code_challenge(code_verifier)
    state_payload = {'nonce': nonce, 'user_id': user_id, 'correo': correo, 'code_verifier': code_verifier, 'exp': datetime.now(timezone.utc).timestamp() + 600}
    state = jwt.encode(state_payload, SECRET_KEY, algorithm='HS256')
    scope_encoded = urllib.parse.quote(' '.join(KICK_SCOPES))
    redirect_encoded = urllib.parse.quote(KICK_REDIRECT_URI, safe='')
    auth_url = f'{KICK_AUTH_URL}?response_type=code&client_id={KICK_CLIENT_ID}&redirect_uri={redirect_encoded}&scope={scope_encoded}&state={state}&code_challenge={code_challenge}&code_challenge_method=S256'
    return JSONResponse({'url': auth_url})

@router.get('/callback')
async def callback(request: Request, db=Depends(get_db)):
    state_jwt = request.query_params.get('state')
    code = request.query_params.get('code')
    error = request.query_params.get('error')
    if error:
        logger.warning(f'Kick Auth Denegado por usuario o API: {error}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error={error}')
    if not state_jwt or not code:
        logger.warning('Callback de Kick incompleto (Falta state o code).')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=missing_parameters')
    user_id, correo, code_verifier = (None, None, None)
    try:
        payload = jwt.decode(state_jwt, SECRET_KEY, algorithms=['HS256'])
        user_id = payload.get('user_id')
        correo = payload.get('correo') or payload.get('email')
        code_verifier = payload.get('code_verifier')
    except jwt.ExpiredSignatureError:
        logger.warning('Kick Auth: JWT State expirado.')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=session_expired')
    except Exception as e:
        logger.warning(f'Kick Auth: Manipulación de JWT o error de firma: {e}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=session_lost')
    if not user_id or not correo or (not code_verifier):
        logger.error('Kick Auth: JWT válido pero payload incompleto.')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=pkce_failed')
    email_safe = correo.strip().lower()
    data = {'grant_type': 'authorization_code', 'client_id': KICK_CLIENT_ID, 'client_secret': KICK_CLIENT_SECRET, 'code': code, 'redirect_uri': KICK_REDIRECT_URI, 'code_verifier': code_verifier, 'prompt': 'consent'}
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    try:
        token_resp = requests.post(KICK_TOKEN_URL, data=data, headers=headers, timeout=15)
        token_res = token_resp.json()
    except requests.RequestException as e:
        logger.error(f'Kick Network Error (Token): {e}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=token_exchange_network_error')
    except ValueError:
        logger.error(f'Kick Invalid JSON Response (Token): {token_resp.text}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=token_exchange_invalid_response')
    if 'access_token' not in token_res:
        logger.error(f'Kick Token Error. HTTP {token_resp.status_code} - Resp: {token_res}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=token_exchange_failed')
    access_token = token_res['access_token']
    refresh_token = token_res.get('refresh_token', '')
    kick_user_id, kick_name, kick_email, kick_avatar = (None, 'unknown', '', '')
    try:
        api_headers = {'Authorization': f'Bearer {access_token}'}
        r = requests.get(KICK_API_URL, headers=api_headers, timeout=10)
        if r.status_code == 200:
            user_info = r.json()
            data_list = user_info.get('data', [])
            if data_list:
                first_user = data_list[0]
                kick_user_id = first_user.get('user_id')
                kick_name = first_user.get('name', 'unknown')
                kick_email = first_user.get('email', '')
                kick_avatar = first_user.get('profile_picture', '')
        else:
            logger.warning(f'Perfil de Kick inaccesible. HTTP {r.status_code}')
    except requests.RequestException as e:
        logger.warning(f'Error de red extrayendo perfil Kick: {e}')
    if not kick_user_id or kick_user_id == 'unknown':
        logger.error('Kick Error: No se pudo obtener el ID de Kick del usuario.')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=missing_provider_id')
    now_utc = datetime.now(timezone.utc)
    encrypted_access = encrypt_data(access_token) if access_token else None
    encrypted_refresh = encrypt_data(refresh_token) if refresh_token else None
    new_account_doc = {'user_id': str(user_id), 'provider': 'kick', 'account_id': kick_user_id, 'access_token': encrypted_access, 'refresh_token': encrypted_refresh, 'expires_in': 3600, 'status': 'active', 'timestamp': now_utc.strftime('%Y-%m-%d %H:%M:%S'), 'metadata': {'kick_id': kick_user_id, 'username': kick_name, 'avatar': kick_avatar, 'email': kick_email, 'connected_at': now_utc.isoformat()}}
    try:
        await db[Collections.USER_CONNECTED_ACCOUNTS].update_one({'user_id': str(user_id), 'provider': 'kick', 'account_id': kick_user_id}, {'$set': new_account_doc}, upsert=True)
    except Exception as e:
        logger.error(f'Error DB guardando Kick en vault para {email_safe}: {e}', exc_info=True)
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=database_error')
    logger.info(f'Kick conectado exitosamente en bóveda para {email_safe}')
    return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?kick_status=connected')

@router.get('/status')
def status():
    return JSONResponse({'connected': True})

@router.delete('')
def disconnect():
    return JSONResponse({'success': True})
