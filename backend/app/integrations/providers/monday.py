"""
Monday.com OAuth 2.0 Authentication Module — FastAPI Version
Migrated to Secure OAuth Vault
"""
import os
import jwt
import secrets
import logging
import requests
import urllib.parse
from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from bson import ObjectId
from app.database import get_current_user, get_db, SECRET_KEY
from app.core.constants import Collections
try:
    from app.core.security import encrypt_data
except ImportError:
    logger = logging.getLogger(__name__)
    logger.warning('Módulo de encriptación no encontrado. Se usará texto plano (MODO DEV).')
    encrypt_data = lambda x: x
logger = logging.getLogger('auth.monday')
router = APIRouter()
MONDAY_AUTH_URL = 'https://auth.monday.com/oauth2/authorize'
MONDAY_TOKEN_URL = 'https://auth.monday.com/oauth2/token'
MONDAY_API_URL = 'https://api.monday.com/v2'
FRONTEND_REDIRECT_URL = os.getenv('FRONTEND_REDIRECT_URL', 'https://hypershifu.com/chat')
MONDAY_SCOPES = ['me:read', 'boards:read', 'users:read']

@router.get('/login')
async def login(user: dict=Depends(get_current_user)):
    user_id = str(user.get('_id', user.get('id', '')))
    correo = user.get('correo') or user.get('email', '')
    if not user_id or not correo:
        raise HTTPException(status_code=401, detail='Usuario inválido o sin correo')
    nonce = secrets.token_urlsafe(32)
    state_payload = {'nonce': nonce, 'user_id': user_id, 'correo': correo}
    state = jwt.encode(state_payload, SECRET_KEY, algorithm='HS256')
    client_id = os.getenv('MONDAY_CLIENT_ID')
    redirect_uri = os.getenv('MONDAY_REDIRECT_URI')
    if not client_id or not redirect_uri:
        raise HTTPException(status_code=500, detail='Configuración OAuth de Monday incompleta')
    params = {'client_id': client_id, 'redirect_uri': redirect_uri, 'state': state, 'scope': ' '.join(MONDAY_SCOPES), 'response_type': 'code'}
    auth_url = f'{MONDAY_AUTH_URL}?{urllib.parse.urlencode(params)}'
    return JSONResponse({'url': auth_url})

@router.get('/callback')
async def callback(request: Request, db=Depends(get_db)):
    try:
        state_jwt = request.query_params.get('state')
        code = request.query_params.get('code')
        error = request.query_params.get('error')
        if error:
            logger.warning(f'Monday Auth Error: {error}')
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=auth_failed')
        user_id, correo = (None, None)
        if state_jwt:
            try:
                payload = jwt.decode(state_jwt, SECRET_KEY, algorithms=['HS256'])
                user_id = payload.get('user_id')
                correo = payload.get('correo')
            except Exception as e:
                logger.warning(f'Invalid state JWT en Monday: {e}')
        if not user_id or not correo:
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=session_lost')
        if not code:
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=missing_code')
        email_safe = correo.strip().lower()
        data = {'client_id': os.getenv('MONDAY_CLIENT_ID'), 'client_secret': os.getenv('MONDAY_CLIENT_SECRET'), 'code': code, 'redirect_uri': os.getenv('MONDAY_REDIRECT_URI'), 'grant_type': 'authorization_code'}
        try:
            token_resp = requests.post(MONDAY_TOKEN_URL, data=data, timeout=15)
            token_json = token_resp.json()
        except requests.RequestException as e:
            logger.error(f'Monday Network Error (Token): {e}')
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=token_exchange_network_error')
        if 'access_token' not in token_json:
            logger.error(f'Monday Token Error: {token_json}')
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=token_exchange_failed')
        access_token = token_json['access_token']
        refresh_token = token_json.get('refresh_token')
        me_data = {}
        try:
            query = '{ me { id name email account { id name } } }'
            headers = {'Authorization': access_token, 'API-Version': '2023-10'}
            gql_resp = requests.post(MONDAY_API_URL, json={'query': query}, headers=headers, timeout=15)
            if gql_resp.status_code == 200:
                me_data = gql_resp.json().get('data', {}).get('me', {})
        except requests.RequestException as e:
            logger.warning(f'No se pudo obtener datos GraphQL de Monday: {e}')
        monday_user_id = str(me_data.get('id', ''))
        if not monday_user_id or monday_user_id == 'None':
            logger.error('Monday Error: No se pudo extraer el ID del usuario de GraphQL.')
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=missing_provider_id')
        encrypted_token = encrypt_data(access_token) if access_token else None
        encrypted_refresh = encrypt_data(refresh_token) if refresh_token else None
        now_utc = datetime.now(timezone.utc)
        new_account_doc = {'user_id': str(user_id), 'provider': 'monday', 'account_id': monday_user_id, 'access_token': encrypted_token, 'refresh_token': encrypted_refresh, 'status': 'active', 'timestamp': now_utc.strftime('%Y-%m-%d %H:%M:%S'), 'metadata': {'monday_user_id': monday_user_id, 'email': me_data.get('email'), 'name': me_data.get('name'), 'account_id': me_data.get('account', {}).get('id'), 'account_name': me_data.get('account', {}).get('name'), 'connected_at': now_utc.isoformat()}}
        try:
            await db[Collections.USER_CONNECTED_ACCOUNTS].update_one({'user_id': str(user_id), 'provider': 'monday', 'account_id': monday_user_id}, {'$set': new_account_doc, '$setOnInsert': {'created_at': now_utc}}, upsert=True)
        except Exception as e:
            logger.error(f'Error guardando Monday V2 en DB para {email_safe}: {e}', exc_info=True)
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=database_error')
    except Exception as e:
        logger.error(f'MONDAY CALLBACK ERROR: {e}', exc_info=True)
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=internal_server_error')

@router.get('/status')
def status():
    return JSONResponse({'connected': True})

@router.delete('')
def disconnect():
    return JSONResponse({'success': True})
