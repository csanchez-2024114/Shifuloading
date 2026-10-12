"""
Twitter (X) OAuth 2.0 PKCE — FastAPI Version
Migrated to Secure OAuth Vault
"""
import os
import jwt
import secrets
import logging
import requests
import base64
import hashlib
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
logger = logging.getLogger('auth.twitter')
router = APIRouter()
TWITTER_AUTH_URL = 'https://twitter.com/i/oauth2/authorize'
TWITTER_TOKEN_URL = 'https://api.twitter.com/2/oauth2/token'
TWITTER_USER_URL = 'https://api.twitter.com/2/users/me'
TWITTER_SCOPES = ['tweet.read', 'users.read', 'offline.access']
FRONTEND_REDIRECT_URL = os.getenv('FRONTEND_REDIRECT_URL', 'https://hypershifu.com/chat')

def generate_code_verifier():
    return secrets.token_urlsafe(96)

def generate_code_challenge(code_verifier):
    digest = hashlib.sha256(code_verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip('=')

@router.get('/login')
async def login(user: dict=Depends(get_current_user)):
    user_id = str(user.get('_id', user.get('id', '')))
    correo = user.get('correo') or user.get('email', '')
    if not user_id or not correo:
        raise HTTPException(status_code=401, detail='Usuario inválido o sin correo')
    nonce = secrets.token_urlsafe(32)
    code_verifier = generate_code_verifier()
    code_challenge = generate_code_challenge(code_verifier)
    state_payload = {'nonce': nonce, 'u': user_id, 'email': correo, 'correo': correo, 'code_verifier': code_verifier, 'exp': datetime.now(timezone.utc).timestamp() + 600}
    state = jwt.encode(state_payload, SECRET_KEY, algorithm='HS256')
    params = {'response_type': 'code', 'client_id': os.getenv('TWITTER_CLIENT_ID'), 'redirect_uri': os.getenv('TWITTER_REDIRECT_URI'), 'scope': ' '.join(TWITTER_SCOPES), 'state': state, 'code_challenge': code_challenge, 'code_challenge_method': 'S256', 'prompt': 'consent'}
    auth_url = f'{TWITTER_AUTH_URL}?{urllib.parse.urlencode(params)}'
    return JSONResponse({'url': auth_url})

@router.get('/callback')
async def callback(request: Request, db=Depends(get_db)):
    code = request.query_params.get('code')
    state = request.query_params.get('state')
    error = request.query_params.get('error')
    if error:
        logger.warning(f'Twitter Auth Failed: {error}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error={error}')
    user_id, correo, code_verifier = (None, None, None)
    if state:
        try:
            payload = jwt.decode(state, SECRET_KEY, algorithms=['HS256'])
            user_id = payload.get('u')
            correo = payload.get('correo') or payload.get('email')
            code_verifier = payload.get('code_verifier')
        except Exception as e:
            logger.warning(f'Invalid state JWT en Twitter: {e}')
    if not user_id or not correo or (not code_verifier):
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=session_lost')
    email_safe = correo.strip().lower()
    client_id = os.getenv('TWITTER_CLIENT_ID')
    client_secret = os.getenv('TWITTER_CLIENT_SECRET')
    redirect_uri = os.getenv('TWITTER_REDIRECT_URI')
    credentials = f'{client_id}:{client_secret}'
    encoded_credentials = base64.b64encode(credentials.encode()).decode()
    headers = {'Authorization': f'Basic {encoded_credentials}', 'Content-Type': 'application/x-www-form-urlencoded'}
    data = {'grant_type': 'authorization_code', 'code': code, 'redirect_uri': redirect_uri, 'code_verifier': code_verifier}
    try:
        token_resp = requests.post(TWITTER_TOKEN_URL, headers=headers, data=data, timeout=15)
        token_res = token_resp.json()
    except requests.RequestException as e:
        logger.error(f'Twitter Network Error: {e}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=token_exchange_network_error')
    if 'access_token' not in token_res:
        logger.error(f'Twitter Token Error: {token_res}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=token_exchange_failed')
    access_token = token_res['access_token']
    refresh_token = token_res.get('refresh_token', '')
    twitter_user_data = {}
    try:
        user_resp = requests.get(TWITTER_USER_URL, headers={'Authorization': f'Bearer {access_token}'}, params={'user.fields': 'id,name,username,profile_image_url'}, timeout=10)
        if user_resp.status_code == 200:
            twitter_user_data = user_resp.json().get('data', {})
        else:
            logger.error(f'Error fetching Twitter /me: {user_resp.status_code} - {user_resp.text}')
    except requests.RequestException as e:
        logger.error(f'Twitter Profile Network Error: {e}')
    twitter_account_id = twitter_user_data.get('id')
    if not twitter_account_id:
        logger.error('Twitter Error: No se pudo obtener el ID de Twitter del usuario.')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=missing_provider_id')
    encrypted_access = encrypt_data(access_token) if access_token else None
    encrypted_refresh = encrypt_data(refresh_token) if refresh_token else None
    now_utc = datetime.now(timezone.utc)
    new_account_doc = {'user_id': str(user_id), 'provider': 'twitter', 'account_id': twitter_account_id, 'access_token': encrypted_access, 'refresh_token': encrypted_refresh, 'expires_in': 3600, 'status': 'active', 'timestamp': now_utc.strftime('%Y-%m-%d %H:%M:%S'), 'metadata': {'twitter_id': twitter_account_id, 'name': twitter_user_data.get('name'), 'username': twitter_user_data.get('username'), 'avatar': twitter_user_data.get('profile_image_url'), 'expires_at': (now_utc + timedelta(seconds=3600)).isoformat(), 'connected_at': now_utc.isoformat()}}
    try:
        await db[Collections.USER_CONNECTED_ACCOUNTS].update_one({'user_id': str(user_id), 'provider': 'twitter', 'account_id': twitter_account_id}, {'$set': new_account_doc}, upsert=True)
    except Exception as e:
        logger.error(f'Error guardando Twitter en connected_accounts: {e}', exc_info=True)
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=database_error')
    logger.info(f'Twitter conectado en bóveda para {email_safe}')
    return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?twitter_status=connected')

@router.get('/status')
def status():
    return JSONResponse({'connected': True})

@router.delete('')
def disconnect():
    return JSONResponse({'success': True})
