"""
LinkedIn OAuth 2.0 Authentication Module — FastAPI Version (V2 Architecture)
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
from app.database import get_current_user, SECRET_KEY
from app.core.security import encrypt_data
from app.core.constants import Collections
logger = logging.getLogger(__name__)
router = APIRouter()
LINKEDIN_CLIENT_ID = os.getenv('LINKEDIN_CLIENT_ID')
LINKEDIN_CLIENT_SECRET = os.getenv('LINKEDIN_CLIENT_SECRET')
LINKEDIN_REDIRECT_URI = os.getenv('LINKEDIN_REDIRECT_URI')
LINKEDIN_AUTH_URL = 'https://www.linkedin.com/oauth/v2/authorization'
LINKEDIN_TOKEN_URL = 'https://www.linkedin.com/oauth/v2/accessToken'
LINKEDIN_USER_INFO_URL = 'https://api.linkedin.com/v2/userinfo'
FRONTEND_REDIRECT_URL = os.getenv('FRONTEND_REDIRECT_URL', 'https://hypershifu.com/chat')
LINKEDIN_SCOPES = ['openid', 'profile', 'email']

@router.get('/login')
def login(user_data=Depends(get_current_user)):
    actual_user_id = str(user_data.get('_id')) if isinstance(user_data, dict) else str(user_data)
    correo = user_data.get('correo') or user_data.get('email', '') if isinstance(user_data, dict) else ''
    if not actual_user_id or not correo:
        logger.warning('Intento de login LinkedIn sin correo o ID válido.')
        raise HTTPException(status_code=401, detail='Usuario inválido o sin correo')
    state = jwt.encode({'u': actual_user_id, 'email': correo, 'correo': correo, 'exp': datetime.now(timezone.utc).timestamp() + 600}, SECRET_KEY, algorithm='HS256')
    params = {'response_type': 'code', 'client_id': LINKEDIN_CLIENT_ID, 'redirect_uri': LINKEDIN_REDIRECT_URI, 'state': state, 'scope': ' '.join(LINKEDIN_SCOPES), 'prompt': 'select_account'}
    auth_url = f'{LINKEDIN_AUTH_URL}?{urllib.parse.urlencode(params)}'
    return {'url': auth_url}

@router.get('/callback')
async def callback(request: Request):
    try:
        code = request.query_params.get('code')
        error = request.query_params.get('error')
        error_description = request.query_params.get('error_description')
        state_jwt = request.query_params.get('state')
        if error:
            logger.warning(f'LinkedIn Auth Error: {error} - {error_description}')
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error={error}')
        try:
            payload = jwt.decode(state_jwt, SECRET_KEY, algorithms=['HS256'])
            user_id = payload.get('u')
            correo_sistema = payload.get('email')
        except Exception:
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=session_lost')
        if not user_id or not code or (not correo_sistema):
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=session_lost')
        data = {'grant_type': 'authorization_code', 'code': code, 'redirect_uri': LINKEDIN_REDIRECT_URI, 'client_id': LINKEDIN_CLIENT_ID, 'client_secret': LINKEDIN_CLIENT_SECRET}
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        token_resp = requests.post(LINKEDIN_TOKEN_URL, data=data, headers=headers, timeout=15)
        token_res = token_resp.json()
        if 'access_token' not in token_res:
            logger.error(f'LinkedIn Token Error: {token_resp.status_code} - {token_res}')
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=token_exchange_failed')
        access_token = token_res['access_token']
        refresh_token = token_res.get('refresh_token', '')
        expires_in = token_res.get('expires_in', 5184000)
        linkedin_id = 'unknown'
        name = 'unknown'
        email = ''
        picture = ''
        try:
            api_headers = {'Authorization': f'Bearer {access_token}'}
            user_resp = requests.get(LINKEDIN_USER_INFO_URL, headers=api_headers, timeout=10)
            if user_resp.status_code == 200:
                user_info = user_resp.json()
                linkedin_id = user_info.get('sub')
                name = user_info.get('name', 'unknown')
                email = user_info.get('email', '')
                picture = user_info.get('picture', '')
        except Exception as e:
            logger.warning(f'Error fetching LinkedIn userinfo: {e}')
        now_utc = datetime.now(timezone.utc)
        encrypted_access = encrypt_data(access_token)
        encrypted_refresh = encrypt_data(refresh_token) if refresh_token else ''
        new_account_doc = {'user_id': str(user_id), 'provider': 'linkedin', 'account_id': linkedin_id, 'access_token': encrypted_access, 'refresh_token': encrypted_refresh, 'expires_in': expires_in, 'status': 'active', 'timestamp': now_utc.strftime('%Y-%m-%d %H:%M:%S'), 'metadata': {'linkedin_id': linkedin_id, 'name': name, 'email': email, 'picture': picture, 'connected_at': now_utc.isoformat()}}
        db = request.app.state.db
        try:
            await db[Collections.USER_CONNECTED_ACCOUNTS].update_one({'user_id': str(user_id), 'provider': 'linkedin', 'account_id': linkedin_id}, {'$set': new_account_doc}, upsert=True)
        except Exception as e:
            logger.error(f'Error DB guardando LinkedIn para {correo_sistema}: {e}', exc_info=True)
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=database_error')
        logger.info(f"LinkedIn de '{name}' conectado exitosamente en esquema V2.")
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?linkedin_status=connected')
    except Exception as e:
        logger.error(f'LINKEDIN ERROR CRÍTICO: {e}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=internal_server_error')

@router.get('/status')
def status():
    return JSONResponse({'connected': True})

@router.delete('')
def disconnect():
    return JSONResponse({'success': True})
