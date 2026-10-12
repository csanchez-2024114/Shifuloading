"""
Dropbox OAuth 2.0 Authentication Module — FastAPI Version (V2 Architecture)
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
CLIENT_ID = os.getenv('DROPBOX_CLIENT_ID')
CLIENT_SECRET = os.getenv('DROPBOX_CLIENT_SECRET')
REDIRECT_URI = os.getenv('DROPBOX_REDIRECT_URI')
DROPBOX_AUTH_URL = 'https://www.dropbox.com/oauth2/authorize'
DROPBOX_TOKEN_URL = 'https://api.dropboxapi.com/oauth2/token'
DROPBOX_USER_INFO = 'https://api.dropboxapi.com/2/users/get_current_account'
FRONTEND_REDIRECT_URL = os.getenv('FRONTEND_REDIRECT_URL', 'https://hypershifu.com/chat')

@router.get('/login')
def login(user_data=Depends(get_current_user)):
    actual_user_id = str(user_data.get('_id')) if isinstance(user_data, dict) else str(user_data)
    correo = user_data.get('correo') or user_data.get('email', '') if isinstance(user_data, dict) else ''
    if not actual_user_id or not correo:
        logger.warning('Intento de login Dropbox sin correo o ID válido.')
        raise HTTPException(status_code=401, detail='Usuario inválido o sin correo')
    state = jwt.encode({'u': actual_user_id, 'email': correo, 'correo': correo, 'exp': datetime.now(timezone.utc).timestamp() + 600}, SECRET_KEY, algorithm='HS256')
    params = {'client_id': CLIENT_ID, 'response_type': 'code', 'redirect_uri': REDIRECT_URI, 'state': state, 'token_access_type': 'offline'}
    auth_url = f'{DROPBOX_AUTH_URL}?{urllib.parse.urlencode(params)}'
    return {'url': auth_url}

@router.get('/callback')
async def callback(request: Request):
    try:
        code = request.query_params.get('code')
        error = request.query_params.get('error')
        error_description = request.query_params.get('error_description')
        state_jwt = request.query_params.get('state')
        if error:
            logger.warning(f'Dropbox Auth Error: {error} - {error_description}')
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error={error}')
        try:
            payload = jwt.decode(state_jwt, SECRET_KEY, algorithms=['HS256'])
            user_id = payload.get('u')
            correo_sistema = payload.get('email')
        except Exception:
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=session_lost')
        if not user_id or not code:
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=session_lost')
        data = {'code': code, 'grant_type': 'authorization_code', 'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET, 'redirect_uri': REDIRECT_URI}
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        token_resp = requests.post(DROPBOX_TOKEN_URL, data=data, headers=headers, timeout=15)
        token_res = token_resp.json()
        if 'access_token' not in token_res:
            logger.error(f'Dropbox Token Error: {token_res}')
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=token_exchange_failed')
        access_token = token_res['access_token']
        refresh_token = token_res.get('refresh_token', '')
        expires_in = token_res.get('expires_in', 14400)
        dropbox_account_id = token_res.get('account_id', 'unknown')
        email = ''
        name = 'unknown'
        try:
            dbx_headers = {'Authorization': f'Bearer {access_token}'}
            user_resp = requests.post(DROPBOX_USER_INFO, headers=dbx_headers, timeout=10)
            if user_resp.status_code == 200:
                user_info = user_resp.json()
                email = user_info.get('email', '')
                name = user_info.get('name', {}).get('display_name', 'unknown')
        except Exception as e:
            logger.warning(f'Error fetching Dropbox userinfo: {e}')
        now_utc = datetime.now(timezone.utc)
        encrypted_access = encrypt_data(access_token)
        encrypted_refresh = encrypt_data(refresh_token) if refresh_token else ''
        new_account_doc = {'user_id': str(user_id), 'provider': 'dropbox', 'account_id': dropbox_account_id, 'access_token': encrypted_access, 'refresh_token': encrypted_refresh, 'expires_in': expires_in, 'status': 'active', 'timestamp': now_utc.strftime('%Y-%m-%d %H:%M:%S'), 'metadata': {'dropbox_id': dropbox_account_id, 'name': name, 'email': email, 'connected_at': now_utc.isoformat()}}
        db = request.app.state.db
        try:
            await db[Collections.USER_CONNECTED_ACCOUNTS].update_one({'user_id': str(user_id), 'provider': 'dropbox', 'account_id': dropbox_account_id}, {'$set': new_account_doc}, upsert=True)
        except Exception as e:
            logger.error(f'Error DB Dropbox: {e}')
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=database_error')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?dropbox_status=connected')
    except Exception as e:
        logger.error(f'DROPBOX ERROR CRÍTICO: {e}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=internal_server_error')

@router.get('/status')
def status():
    return JSONResponse({'connected': True})

@router.delete('')
def disconnect():
    return JSONResponse({'success': True})


# ── Service Layer ──────────────────────────────────────────────────────────────
"""
Dropbox Service - Credenciales OAuth y extracción segura

 Migración a lectura desde oauth_vault (Vault-First / Legacy-Fallback).
- Implementa desencriptación estricta vía _normalize_integrations.
- Elimina fugas de credenciales en logs/stdout.
"""
import logging
from typing import Dict, Any, Optional
from dotenv import load_dotenv
from app.core.mongo import get_sync_database
from app.database import _normalize_integrations
from app.core.constants import Collections
from app.core.db_utils import canonicalize_email
load_dotenv()
logger = logging.getLogger('services.dropbox')
_INTEGRATION_KEY = 'Dropbox'

def _get_db():
    return get_sync_database()

def _get_dropbox_creds_raw(email_safe: str) -> Optional[Dict[str, Any]]:
    """
    Ejecuta el patrón Vault-First / Legacy-Fallback y devuelve el sub-dict
    de Dropbox ya normalizado y desencriptado.
    """
    db = _get_db()
    vault_doc = db[Collections.OAUTH_VAULT].find_one({'$or': [{'correo': email_safe}, {'email': email_safe}]})
    if vault_doc and vault_doc.get('integrations'):
        integrations = _normalize_integrations(vault_doc['integrations'], source='vault', correo=email_safe)
        logger.info(f"[dropbox_service] Credenciales leídas desde oauth_vault para '{email_safe}'.")
    else:
        legacy_doc = db[Collections.USERS].find_one({'$or': [{'correo': email_safe}, {'email': email_safe}]})
        if not legacy_doc:
            logger.warning(f"[dropbox_service] Usuario '{email_safe}' no encontrado en BD.")
            return None
        integrations = _normalize_integrations(legacy_doc.get('integrations', {}), source='legacy', correo=email_safe)
        logger.warning(f"[dropbox_service] Fallback legacy activo para '{email_safe}'.")
    return integrations.get(_INTEGRATION_KEY) or integrations.get('dropbox')

def get_dropbox_creds_for_langchain(email: str) -> Dict[str, Any]:
    """
    Obtiene, desencripta y formatea las credenciales de Dropbox para el agente.
    Maneja variaciones en la estructura de datos legacy vs nueva.
    """
    if not email:
        logger.warning('[dropbox_service] Función llamada sin correo válido.')
        return {'error': 'Correo inválido'}
    email_safe = canonicalize_email(email)
    try:
        dropbox_creds = _get_dropbox_creds_raw(email_safe)
        if not dropbox_creds:
            logger.warning(f'[dropbox_service] ❌ No se encontraron credenciales de Dropbox para {email_safe}')
            return {'error': 'No encontré credenciales de Dropbox'}
        token_data = dropbox_creds.get('token')
        if isinstance(token_data, dict):
            access_token = token_data.get('access_token')
            refresh_token = token_data.get('refresh_token') or dropbox_creds.get('refresh_token')
            expires_in = token_data.get('expires_in') or dropbox_creds.get('expires_in')
            account_id = token_data.get('account_id') or dropbox_creds.get('account_id')
        else:
            access_token = token_data
            refresh_token = dropbox_creds.get('refresh_token')
            expires_in = dropbox_creds.get('expires_in')
            account_id = dropbox_creds.get('account_id')
        if not access_token:
            return {'error': 'Credenciales incompletas: access_token ausente.'}
        return {'access_token': access_token, 'refresh_token': refresh_token, 'expires_in': expires_in, 'account_id': account_id}
    except Exception as e:
        logger.error(f'[dropbox_service] Error crítico al obtener credenciales para {email_safe}: {str(e)}', exc_info=True)
        return {'error': f'Error interno al acceder a la base de datos.'}
if __name__ == '__main__':
    logger.info('Modulo Dropbox Service inicializado correctamente. (Tests removidos por seguridad)')

