"""
OneDrive OAuth 2.0 Authentication Module — FastAPI Version (V2 Architecture)
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
from app.core.security import encrypt_data
from app.database import get_db, get_current_user, SECRET_KEY
from app.core.constants import Collections
from app.routes.auth.authRoutes import refresh_token
logger = logging.getLogger(__name__)
router = APIRouter()
ONEDRIVE_CLIENT_ID = os.getenv('ONEDRIVE_CLIENT_ID')
ONEDRIVE_CLIENT_SECRET = os.getenv('ONEDRIVE_CLIENT_SECRET')
ONEDRIVE_REDIRECT_URI = os.getenv('ONEDRIVE_REDIRECT_URI')
AUTH_URL = 'https://login.microsoftonline.com/common/oauth2/v2.0/authorize'
TOKEN_URL = 'https://login.microsoftonline.com/common/oauth2/v2.0/token'
GRAPH_ME_URL = 'https://graph.microsoft.com/v1.0/me'
FRONTEND_REDIRECT_URL = os.getenv('FRONTEND_REDIRECT_URL', 'https://hypershifu.com/chat')
SECRET_KEY = os.getenv('SECRET_KEY')
ONEDRIVE_SCOPES = ['offline_access', 'User.Read', 'Files.Read.All', 'Files.ReadWrite.All']

def get_current_user(request: Request):
    token = request.query_params.get('token')
    if not token:
        auth_header = request.headers.get('Authorization', '')
        if auth_header.lower().startswith('bearer '):
            token = auth_header[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail='Auth required')
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
        return payload
    except Exception as e:
        logger.warning(f'JWT Error: {e}')
        raise HTTPException(status_code=401, detail='Invalid token')

@router.get('/login')
def login(user_payload: dict=Depends(get_current_user)):
    actual_user_id = str(user_payload.get('user_id') or user_payload.get('sub') or user_payload.get('_id', ''))
    correo_sistema = user_payload.get('correo') or user_payload.get('email', '')
    if not actual_user_id or not correo_sistema:
        logger.warning('Intento de login OneDrive sin correo o ID válido.')
        raise HTTPException(status_code=401, detail='Usuario inválido o sin correo')
    state = jwt.encode({'u': actual_user_id, 'email': correo_sistema}, SECRET_KEY, algorithm='HS256')
    params = {'client_id': ONEDRIVE_CLIENT_ID, 'response_type': 'code', 'redirect_uri': ONEDRIVE_REDIRECT_URI, 'response_mode': 'query', 'scope': ' '.join(ONEDRIVE_SCOPES), 'state': state, 'prompt': 'select_account'}
    auth_url = f'{AUTH_URL}?{urllib.parse.urlencode(params)}'
    return {'url': auth_url}

@router.get('/callback')
async def callback(request: Request, db=Depends(get_db)):
    try:
        state_jwt = request.query_params.get('state')
        code = request.query_params.get('code')
        error = request.query_params.get('error')
        if error:
            logger.warning(f'OneDrive Auth Error: {error}')
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error={error}')
        try:
            payload = jwt.decode(state_jwt, SECRET_KEY, algorithms=['HS256'])
            user_id = payload.get('u')
            correo_sistema = payload.get('email') or payload.get('correo')
        except Exception:
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=session_lost')
        if not user_id or not code or (not correo_sistema):
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=session_lost')
        data = {'client_id': ONEDRIVE_CLIENT_ID, 'client_secret': ONEDRIVE_CLIENT_SECRET, 'scope': ' '.join(ONEDRIVE_SCOPES), 'code': code, 'redirect_uri': ONEDRIVE_REDIRECT_URI, 'grant_type': 'authorization_code'}
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        token_resp = requests.post(TOKEN_URL, data=data, headers=headers, timeout=15)
        token_res = token_resp.json()
        if 'access_token' not in token_res:
            logger.error(f'OneDrive Token Error: {token_resp.status_code} - {token_res}')
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=token_exchange_failed')
        access_token = token_res['access_token']
        refresh_token = token_res.get('refresh_token', '')
        ms_id = None
        ms_name = 'unknown'
        ms_email = ''
        try:
            me_resp = requests.get(GRAPH_ME_URL, headers={'Authorization': f'Bearer {access_token}'}, timeout=10)
            if me_resp.status_code == 200:
                me_data = me_resp.json()
                ms_id = me_data.get('id')
                ms_name = me_data.get('displayName', 'unknown')
                ms_email = me_data.get('mail') or me_data.get('userPrincipalName', '')
        except Exception as e:
            logger.warning(f'Error fetching OneDrive /me: {e}')
        if not ms_id or ms_id == 'unknown':
            logger.error('OneDrive Error: No se pudo obtener el ID de Microsoft del usuario.')
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=missing_provider_id')
        now_utc = datetime.now(timezone.utc)
        encrypted_access = encrypt_data(access_token) if access_token else None
        encrypted_refresh = encrypt_data(refresh_token) if refresh_token else ''
        new_account_doc = {'user_id': str(user_id), 'provider': 'onedrive', 'account_id': ms_id, 'access_token': encrypted_access, 'refresh_token': encrypted_refresh, 'expires_in': 3600, 'status': 'active', 'timestamp': now_utc.strftime('%Y-%m-%d %H:%M:%S'), 'metadata': {'microsoft_id': ms_id, 'name': ms_name, 'email': ms_email, 'connected_at': now_utc.isoformat()}}
        try:
            await db[Collections.USER_CONNECTED_ACCOUNTS].update_one({'user_id': str(user_id), 'provider': 'onedrive', 'account_id': ms_id}, {'$set': new_account_doc}, upsert=True)
        except Exception as e:
            logger.error(f'Error DB guardando OneDrive para {correo_sistema}: {e}', exc_info=True)
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=database_error')
        logger.info(f"OneDrive de '{ms_email}' conectado exitosamente en nuevo esquema.")
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?onedrive_status=connected')
    except Exception as e:
        logger.error(f'ONEDRIVE ERROR CRÍTICO: {e}', exc_info=True)
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=internal_server_error')

@router.get('/status')
def status():
    return JSONResponse({'connected': True})

@router.delete('')
def disconnect():
    return JSONResponse({'success': True})
