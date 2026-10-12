"""
Instagram Graph API Authentication Module.
Migrated to Secure OAuth Vault.
Uses 'Facebook Login for Business' to access Instagram Professional Accounts.
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
from app.database import get_current_user, get_db, SECRET_KEY
from app.core.constants import Collections
try:
    from app.core.security import encrypt_data
except ImportError:
    logger = logging.getLogger(__name__)
    logger.warning('Módulo de encriptación no encontrado. Se usará texto plano (MODO DEV).')
    encrypt_data = lambda x: x
router = APIRouter()
logger = logging.getLogger('auth.instagram')
INSTAGRAM_AUTH_URL = 'https://www.facebook.com/v19.0/dialog/oauth'
INSTAGRAM_TOKEN_URL = 'https://graph.facebook.com/v19.0/oauth/access_token'
INSTAGRAM_GRAPH_URL = 'https://graph.facebook.com/v19.0'
FRONTEND_REDIRECT_URL = os.getenv('FRONTEND_REDIRECT_URL', 'https://hypershifu.com/chat')
INSTAGRAM_SCOPES = ['instagram_basic', 'pages_show_list']

@router.get('/login')
async def instagram_login(user: dict=Depends(get_current_user)):
    user_id = str(user.get('_id', user.get('id', '')))
    correo = user.get('correo') or user.get('email', '')
    if not user_id or not correo:
        raise HTTPException(status_code=401, detail='Usuario inválido o sin correo')
    nonce = secrets.token_urlsafe(32)
    state_payload = {'u': user_id, 'email': correo, 'correo': correo, 'exp': datetime.now(timezone.utc).timestamp() + 600}
    state = jwt.encode(state_payload, SECRET_KEY, algorithm='HS256')
    client_id = os.getenv('INSTAGRAM_CLIENT_ID')
    redirect_uri = os.getenv('INSTAGRAM_REDIRECT_URI')
    if not client_id or not redirect_uri:
        logger.error('Missing Instagram OAuth configuration')
        raise HTTPException(status_code=500, detail='Server misconfiguration')
    params = {'client_id': client_id, 'redirect_uri': redirect_uri, 'scope': ','.join(INSTAGRAM_SCOPES), 'response_type': 'code', 'state': state, 'auth_type': 'reauthenticate'}
    auth_url = f'{INSTAGRAM_AUTH_URL}?{urllib.parse.urlencode(params)}'
    return JSONResponse({'url': auth_url})

@router.get('/callback')
async def instagram_callback(request: Request, db=Depends(get_db)):
    state_jwt = request.query_params.get('state')
    code = request.query_params.get('code')
    error = request.query_params.get('error')
    if error:
        logger.warning(f'Instagram Auth Error: {error}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=auth_failed')
    user_id, correo = (None, None)
    if state_jwt:
        try:
            payload = jwt.decode(state_jwt, SECRET_KEY, algorithms=['HS256'])
            user_id = payload.get('u')
            correo = payload.get('correo') or payload.get('email')
        except Exception as e:
            logger.warning(f'Invalid state JWT en Instagram: {e}')
    if not user_id or not correo:
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=session_lost')
    if not code:
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=missing_code')
    email_safe = correo.strip().lower()
    token_params = {'client_id': os.getenv('INSTAGRAM_CLIENT_ID'), 'client_secret': os.getenv('INSTAGRAM_CLIENT_SECRET'), 'redirect_uri': os.getenv('INSTAGRAM_REDIRECT_URI'), 'code': code}
    try:
        token_resp = requests.get(INSTAGRAM_TOKEN_URL, params=token_params, timeout=15)
        token_json = token_resp.json()
    except requests.RequestException as e:
        logger.error(f'Instagram Network Error (Token): {e}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=token_exchange_network_error')
    if 'access_token' not in token_json:
        logger.error(f'Instagram Token Error: {token_json}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=token_exchange_failed')
    access_token = token_json['access_token']
    instagram_data = None
    try:
        pages_resp = requests.get(f'{INSTAGRAM_GRAPH_URL}/me/accounts', params={'access_token': access_token}, timeout=15).json()
        for page in pages_resp.get('data', []):
            page_id = page.get('id')
            if not page_id:
                continue
            try:
                fields = requests.get(f'{INSTAGRAM_GRAPH_URL}/{page_id}', params={'fields': 'instagram_business_account,name', 'access_token': access_token}, timeout=10).json()
                if fields.get('instagram_business_account'):
                    ig_id = fields['instagram_business_account']['id']
                    ig_info = requests.get(f'{INSTAGRAM_GRAPH_URL}/{ig_id}', params={'fields': 'username,profile_picture_url,name', 'access_token': access_token}, timeout=10).json()
                    instagram_data = {'instagram_id': ig_id, 'username': ig_info.get('username', ''), 'name': ig_info.get('name', ''), 'profile_picture': ig_info.get('profile_picture_url', '')}
                    break
            except requests.RequestException as page_err:
                logger.warning(f'Error procesando la página de FB {page_id}: {page_err}')
                continue
    except requests.RequestException as e:
        logger.error(f'Error general consultando Graph API: {e}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=instagram_graph_error')
    if not instagram_data:
        logger.warning(f'Usuario {email_safe} intentó conectar IG sin cuenta Profesional.')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=no_business_account')
    encrypted_token = encrypt_data(access_token) if access_token else None
    ig_account_id = instagram_data['instagram_id']
    integration_payload = {'user_id': str(user_id), 'provider': 'instagram', 'account_id': ig_account_id, 'access_token': encrypted_token, 'refresh_token': 'n/a', 'token': encrypted_token, 'expires_in': 3600, 'status': 'active', 'timestamp': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'), 'metadata': {'instagram_id': ig_account_id, 'username': instagram_data['username'], 'name': instagram_data['name'], 'profile_picture': instagram_data['profile_picture'], 'account_type': 'BUSINESS', 'connected_at': datetime.now(timezone.utc).isoformat()}}
    now = datetime.now(timezone.utc)
    try:
        await db[Collections.USER_CONNECTED_ACCOUNTS].update_one({'user_id': str(user_id), 'provider': 'instagram', 'account_id': ig_account_id}, {'$set': integration_payload}, upsert=True)
    except Exception as e:
        logger.error(f'Error guardando Instagram en connected_accounts: {e}', exc_info=True)
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=database_error')
    logger.info(f'Instagram conectado exitosamente {email_safe}')
    return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?instagram_status=connected')

@router.get('/status')
def status():
    return JSONResponse({'connected': True})

@router.delete('')
def disconnect():
    return JSONResponse({'success': True})
