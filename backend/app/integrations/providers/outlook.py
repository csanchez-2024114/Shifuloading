"""
Outlook OAuth 2.0 Authentication Module — FastAPI Version (V2 Architecture)
"""
import os
import jwt
import logging
import requests
import urllib.parse
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from app.database import get_current_user, SECRET_KEY
from app.core.security import encrypt_data
from app.core.constants import Collections
logger = logging.getLogger(__name__)
router = APIRouter()
CLIENT_ID = os.getenv('OUTLOOK_CLIENT_ID')
CLIENT_SECRET = os.getenv('OUTLOOK_CLIENT_SECRET')
REDIRECT_URI = os.getenv('OUTLOOK_REDIRECT_URI')
MICROSOFT_AUTH_URL = 'https://login.microsoftonline.com/common/oauth2/v2.0/authorize'
MICROSOFT_TOKEN_URL = 'https://login.microsoftonline.com/common/oauth2/v2.0/token'
MICROSOFT_USER_INFO = 'https://graph.microsoft.com/v1.0/me'
FRONTEND_REDIRECT_URL = os.getenv('FRONTEND_REDIRECT_URL', 'https://hypershifu.com/chat')
OUTLOOK_SCOPES = ['offline_access', 'User.Read', 'Mail.ReadWrite', 'Mail.Send']

@router.get('/login')
def login(user_data=Depends(get_current_user)):
    actual_user_id = str(user_data.get('_id')) if isinstance(user_data, dict) else str(user_data)
    correo = user_data.get('correo') or user_data.get('email', '') if isinstance(user_data, dict) else ''
    if not actual_user_id or not correo:
        logger.warning('Intento de login Outlook sin correo o ID válido.')
        raise HTTPException(status_code=401, detail='Usuario inválido o sin correo')
    state = jwt.encode({'u': actual_user_id, 'email': correo, 'correo': correo, 'exp': datetime.now(timezone.utc).timestamp() + 600}, SECRET_KEY, algorithm='HS256')
    params = {'client_id': CLIENT_ID, 'response_type': 'code', 'redirect_uri': REDIRECT_URI, 'response_mode': 'query', 'scope': ' '.join(OUTLOOK_SCOPES), 'state': state, 'prompt': 'select_account'}
    auth_url = f'{MICROSOFT_AUTH_URL}?{urllib.parse.urlencode(params)}'
    return {'url': auth_url}

@router.get('/callback')
async def callback(request: Request):
    try:
        code = request.query_params.get('code')
        error = request.query_params.get('error')
        error_description = request.query_params.get('error_description')
        state_jwt = request.query_params.get('state')
        if error:
            logger.warning(f'Outlook Auth Error: {error} - {error_description}')
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error={error}')
        try:
            payload = jwt.decode(state_jwt, SECRET_KEY, algorithms=['HS256'])
            user_id = payload.get('u')
            correo_sistema = payload.get('email')
        except Exception:
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=session_lost')
        if not user_id or not code:
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=session_lost')
        data = {'client_id': CLIENT_ID, 'scope': ' '.join(OUTLOOK_SCOPES), 'code': code, 'redirect_uri': REDIRECT_URI, 'grant_type': 'authorization_code', 'client_secret': CLIENT_SECRET}
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        token_resp = requests.post(MICROSOFT_TOKEN_URL, data=data, headers=headers, timeout=15)
        token_res = token_resp.json()
        if 'access_token' not in token_res:
            logger.error(f'Outlook Token Error: {token_res}')
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=token_exchange_failed')
        access_token = token_res['access_token']
        refresh_token = token_res.get('refresh_token', '')
        expires_in = token_res.get('expires_in', 3600)
        outlook_account_id = 'unknown'
        email = ''
        name = 'unknown'
        try:
            graph_headers = {'Authorization': f'Bearer {access_token}'}
            user_resp = requests.get(MICROSOFT_USER_INFO, headers=graph_headers, timeout=10)
            if user_resp.status_code == 200:
                user_info = user_resp.json()
                outlook_account_id = user_info.get('id')
                email = user_info.get('mail') or user_info.get('userPrincipalName', '')
                name = user_info.get('displayName', 'unknown')
        except Exception as e:
            logger.warning(f'Error fetching Outlook userinfo: {e}')
        now_utc = datetime.now(timezone.utc)
        encrypted_access = encrypt_data(access_token)
        encrypted_refresh = encrypt_data(refresh_token) if refresh_token else ''
        new_account_doc = {'user_id': str(user_id), 'provider': 'outlook', 'account_id': outlook_account_id, 'access_token': encrypted_access, 'refresh_token': encrypted_refresh, 'expires_in': expires_in, 'status': 'active', 'timestamp': now_utc.strftime('%Y-%m-%d %H:%M:%S'), 'metadata': {'outlook_id': outlook_account_id, 'name': name, 'email': email, 'connected_at': now_utc.isoformat()}}
        db = request.app.state.db
        try:
            await db[Collections.USER_CONNECTED_ACCOUNTS].update_one({'user_id': str(user_id), 'provider': 'outlook', 'account_id': outlook_account_id}, {'$set': new_account_doc}, upsert=True)
        except Exception as e:
            logger.error(f'Error DB Outlook: {e}')
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=database_error')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?outlook_status=connected')
    except Exception as e:
        logger.error(f'OUTLOOK ERROR CRÍTICO: {e}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=internal_server_error')

@router.get('/status')
def status():
    return JSONResponse({'connected': True})

@router.delete('')
def disconnect():
    return JSONResponse({'success': True})


# ── Service Layer ──────────────────────────────────────────────────────────────

