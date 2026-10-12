"""
Mailchimp OAuth 2.0 Authentication Module — FastAPI Version
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
from app.database import get_current_user, get_db, SECRET_KEY
from app.core.constants import Collections
try:
    from app.core.security import encrypt_data
except ImportError:
    logger = logging.getLogger(__name__)
    logger.warning('Módulo de encriptación no encontrado. Se usará texto plano (MODO DEV).')
    encrypt_data = lambda x: x
logger = logging.getLogger('auth.mailchimp')
router = APIRouter()
MAILCHIMP_AUTH_URL = 'https://login.mailchimp.com/oauth2/authorize'
MAILCHIMP_TOKEN_URL = 'https://login.mailchimp.com/oauth2/token'
MAILCHIMP_METADATA_URL = 'https://login.mailchimp.com/oauth2/metadata'
FRONTEND_REDIRECT_URL = os.getenv('FRONTEND_REDIRECT_URL', 'https://hypershifu.com/chat')

@router.get('/login')
async def login(user: dict=Depends(get_current_user)):
    user_id = str(user.get('_id', user.get('id', '')))
    correo = user.get('correo') or user.get('email', '')
    if not user_id or not correo:
        raise HTTPException(status_code=401, detail='Usuario inválido o sin correo')
    nonce = secrets.token_urlsafe(32)
    state_payload = {'nonce': nonce, 'user_id': user_id, 'correo': correo}
    state = jwt.encode(state_payload, SECRET_KEY, algorithm='HS256')
    client_id = os.getenv('MAILCHIMP_CLIENT_ID')
    redirect_uri = os.getenv('MAILCHIMP_REDIRECT_URI')
    if not client_id or not redirect_uri:
        logger.error('Mailchimp credentials missing in environment')
        raise HTTPException(status_code=500, detail='Server misconfiguration')
    params = {'response_type': 'code', 'client_id': client_id, 'redirect_uri': redirect_uri, 'state': state}
    auth_url = f'{MAILCHIMP_AUTH_URL}?{urllib.parse.urlencode(params)}'
    return JSONResponse({'url': auth_url})

@router.get('/callback')
async def callback(request: Request, db=Depends(get_db)):
    state_jwt = request.query_params.get('state')
    code = request.query_params.get('code')
    error = request.query_params.get('error')
    if error:
        logger.warning(f'Mailchimp Auth Error: {error}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=auth_failed')
    user_id, correo = (None, None)
    if state_jwt:
        try:
            payload = jwt.decode(state_jwt, SECRET_KEY, algorithms=['HS256'])
            user_id = payload.get('user_id')
            correo = payload.get('correo')
        except Exception as e:
            logger.warning(f'Invalid state JWT en Mailchimp: {e}')
    if not user_id or not correo:
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=session_lost')
    if not code:
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=missing_code')
    email_safe = correo.strip().lower()
    client_id = os.getenv('MAILCHIMP_CLIENT_ID')
    client_secret = os.getenv('MAILCHIMP_CLIENT_SECRET')
    redirect_uri = os.getenv('MAILCHIMP_REDIRECT_URI')
    data = {'grant_type': 'authorization_code', 'client_id': client_id, 'client_secret': client_secret, 'redirect_uri': redirect_uri, 'code': code}
    try:
        token_resp = requests.post(MAILCHIMP_TOKEN_URL, data=data, timeout=15)
        token_json = token_resp.json()
    except requests.RequestException as e:
        logger.error(f'Mailchimp Network Error (Token): {e}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=token_exchange_network_error')
    if 'access_token' not in token_json:
        logger.error(f'Mailchimp Token Error: {token_json}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=token_exchange_failed')
    access_token = token_json['access_token']
    meta_json = {}
    try:
        meta_headers = {'Authorization': f'OAuth {access_token}'}
        meta_resp = requests.get(MAILCHIMP_METADATA_URL, headers=meta_headers, timeout=10)
        if meta_resp.status_code == 200:
            meta_json = meta_resp.json()
    except requests.RequestException as e:
        logger.warning(f'No se pudo obtener metadata de Mailchimp: {e}')
    login_id = str(meta_json.get('login', {}).get('login_id', ''))
    mailchimp_email = meta_json.get('login', {}).get('email', '')
    if not login_id or login_id == 'None':
        logger.error('Mailchimp Error: No se pudo extraer el login_id de la metadata.')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=missing_provider_id')
    encrypted_token = encrypt_data(access_token) if access_token else None
    now_utc = datetime.now(timezone.utc)
    new_account_doc = {'user_id': str(user_id), 'provider': 'mailchimp', 'account_id': login_id, 'access_token': encrypted_token, 'refresh_token': 'n/a', 'status': 'active', 'timestamp': now_utc.strftime('%Y-%m-%d %H:%M:%S'), 'metadata': {'mailchimp_user_id': login_id, 'email': mailchimp_email, 'dc': meta_json.get('dc'), 'api_endpoint': meta_json.get('api_endpoint'), 'account_name': meta_json.get('accountname', ''), 'connected_at': now_utc.isoformat()}}
    try:
        await db[Collections.USER_CONNECTED_ACCOUNTS].update_one({'user_id': str(user_id), 'provider': 'mailchimp', 'account_id': login_id}, {'$set': new_account_doc, '$setOnInsert': {'created_at': now_utc}}, upsert=True)
    except Exception as e:
        logger.error(f'Error guardando Mailchimp V2 en DB para {email_safe}: {e}', exc_info=True)
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=database_error')
    logger.info(f"Mailchimp conectado exitosamente en bóveda para {email_safe} (DC: {meta_json.get('dc')})")
    return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?mailchimp_status=connected')

@router.get('/status')
def status():
    return JSONResponse({'connected': True})

@router.delete('')
def disconnect():
    return JSONResponse({'success': True})
