"""
Discord OAuth 2.0 Authentication Module — FastAPI Version (V2 Architecture)
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
from bson import ObjectId
from app.database import get_current_user, SECRET_KEY, get_db
from app.core.security import encrypt_data
from app.core.constants import Collections
logger = logging.getLogger(__name__)
router = APIRouter()
DISCORD_CLIENT_ID = os.getenv('DISCORD_CLIENT_ID')
DISCORD_CLIENT_SECRET = os.getenv('DISCORD_CLIENT_SECRET')
DISCORD_REDIRECT_URI = os.getenv('DISCORD_REDIRECT_URI')
DISCORD_AUTH_URL = 'https://discord.com/api/oauth2/authorize'
DISCORD_TOKEN_URL = 'https://discord.com/api/oauth2/token'
DISCORD_API_URL = 'https://discord.com/api/users/@me'
FRONTEND_REDIRECT_URL = os.getenv('FRONTEND_REDIRECT_URL', 'https://hypershifu.com/chat')
DISCORD_SCOPES = ['identify', 'email', 'guilds']

@router.get('/login')
def login(user_data=Depends(get_current_user)):
    actual_user_id = str(user_data.get('_id')) if isinstance(user_data, dict) else str(user_data)
    correo = user_data.get('correo') or user_data.get('email', '') if isinstance(user_data, dict) else ''
    if not actual_user_id or not correo:
        logger.warning('Intento de login Discord sin correo o ID válido.')
        raise HTTPException(status_code=401, detail='Usuario inválido o sin correo')
    state = jwt.encode({'u': actual_user_id, 'email': correo, 'correo': correo, 'exp': datetime.now(timezone.utc).timestamp() + 600}, SECRET_KEY, algorithm='HS256')
    params = {'client_id': DISCORD_CLIENT_ID, 'redirect_uri': DISCORD_REDIRECT_URI, 'response_type': 'code', 'scope': ' '.join(DISCORD_SCOPES), 'state': state, 'prompt': 'consent'}
    auth_url = f'{DISCORD_AUTH_URL}?{urllib.parse.urlencode(params)}'
    return {'url': auth_url}

@router.get('/callback')
async def callback(request: Request, db=Depends(get_db)):
    try:
        state_jwt = request.query_params.get('state')
        code = request.query_params.get('code')
        error = request.query_params.get('error')
        if error:
            logger.warning(f'Discord Auth Error: {error}')
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error={error}')
        try:
            payload = jwt.decode(state_jwt, SECRET_KEY, algorithms=['HS256'])
            user_id = payload.get('u')
            correo_sistema = payload.get('email') or payload.get('correo')
        except Exception:
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=session_lost')
        if not user_id or not code or (not correo_sistema):
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=session_lost')
        data = {'client_id': DISCORD_CLIENT_ID, 'client_secret': DISCORD_CLIENT_SECRET, 'grant_type': 'authorization_code', 'code': code, 'redirect_uri': DISCORD_REDIRECT_URI}
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        token_resp = requests.post(DISCORD_TOKEN_URL, data=data, headers=headers, timeout=15)
        token_res = token_resp.json()
        if 'access_token' not in token_res:
            logger.error(f'Discord Token Error: {token_resp.status_code} - {token_res}')
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=token_exchange_failed')
        access_token = token_res['access_token']
        refresh_token = token_res.get('refresh_token', '')
        discord_id = None
        username = 'unknown'
        avatar_url = ''
        discord_email = ''
        try:
            api_headers = {'Authorization': f'Bearer {access_token}'}
            user_resp = requests.get(DISCORD_API_URL, headers=api_headers, timeout=10)
            if user_resp.status_code == 200:
                user_info = user_resp.json()
                discord_id = user_info.get('id')
                username = user_info.get('username', 'unknown')
                discord_email = user_info.get('email', '')
                avatar_hash = user_info.get('avatar')
                if avatar_hash:
                    avatar_url = f'https://cdn.discordapp.com/avatars/{discord_id}/{avatar_hash}.png'
        except Exception as e:
            logger.warning(f'Error fetching Discord /@me: {e}')
        if not discord_id or discord_id == 'unknown':
            logger.error('Discord Error: No se pudo obtener el ID de Discord del usuario.')
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=missing_provider_id')
        now_utc = datetime.now(timezone.utc)
        encrypted_access = encrypt_data(access_token) if access_token else None
        encrypted_refresh = encrypt_data(refresh_token) if refresh_token else ''
        new_account_doc = {'user_id': str(user_id), 'provider': 'discord', 'account_id': discord_id, 'access_token': encrypted_access, 'refresh_token': encrypted_refresh, 'expires_in': 3600, 'status': 'active', 'timestamp': now_utc.strftime('%Y-%m-%d %H:%M:%S'), 'metadata': {'discord_id': discord_id, 'username': username, 'avatar': avatar_url, 'email': discord_email, 'connected_at': now_utc.isoformat()}}
        try:
            await db[Collections.USER_CONNECTED_ACCOUNTS].update_one({'user_id': str(user_id), 'provider': 'discord', 'account_id': discord_id}, {'$set': new_account_doc}, upsert=True)
        except Exception as e:
            logger.error(f'Error DB guardando Discord para {correo_sistema}: {e}', exc_info=True)
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=database_error')
        logger.info(f"Discord de '{username}' conectado exitosamente en nuevo esquema.")
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?discord_status=connected')
    except Exception as e:
        logger.error(f'DISCORD ERROR CRÍTICO: {e}', exc_info=True)
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=internal_server_error')

@router.get('/status')
def status():
    return JSONResponse({'connected': True})

@router.delete('')
def disconnect():
    return JSONResponse({'success': True})
