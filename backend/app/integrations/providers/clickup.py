"""
ClickUp OAuth 2.0 Authentication Module — FastAPI Version (V2 Architecture)
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
from app.core.constants import Collections
from app.core.security import encrypt_data
logger = logging.getLogger(__name__)
router = APIRouter()
CLIENT_ID = os.getenv('CLICKUP_CLIENT_ID')
CLIENT_SECRET = os.getenv('CLICKUP_CLIENT_SECRET')
REDIRECT_URI = os.getenv('CLICKUP_REDIRECT_URI')
CLICKUP_AUTH_URL = 'https://app.clickup.com/api'
CLICKUP_TOKEN_URL = 'https://api.clickup.com/api/v2/oauth/token'
CLICKUP_USER_INFO = 'https://api.clickup.com/api/v2/user'
FRONTEND_REDIRECT_URL = os.getenv('FRONTEND_REDIRECT_URL', 'https://hypershifu.com/chat')

@router.get('/login')
def login(user_data=Depends(get_current_user)):
    logger.info(f'ClickUp CLIENT_ID: {CLIENT_ID}')
    logger.info(f'ClickUp REDIRECT_URI: {REDIRECT_URI}')
    logger.info(f'ClickUp AUTH_URL: {CLICKUP_AUTH_URL}')
    actual_user_id = str(user_data.get('_id')) if isinstance(user_data, dict) else str(user_data)
    correo = user_data.get('correo') or user_data.get('email', '') if isinstance(user_data, dict) else ''
    if not actual_user_id or not correo:
        logger.warning('Intento de login ClickUp sin correo o ID válido.')
        raise HTTPException(status_code=401, detail='Usuario inválido o sin correo')
    state = jwt.encode({'u': actual_user_id, 'email': correo, 'correo': correo, 'exp': datetime.now(timezone.utc).timestamp() + 600}, SECRET_KEY, algorithm='HS256')
    params = {'client_id': CLIENT_ID, 'redirect_uri': REDIRECT_URI, 'state': state}
    auth_url = f'{CLICKUP_AUTH_URL}?{urllib.parse.urlencode(params)}'
    return {'url': auth_url}

@router.get('/callback')
async def callback(request: Request):
    try:
        code = request.query_params.get('code')
        error = request.query_params.get('error')
        state_jwt = request.query_params.get('state')
        if error:
            logger.warning(f'ClickUp Auth Error: {error}')
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error={error}')
        try:
            payload = jwt.decode(state_jwt, SECRET_KEY, algorithms=['HS256'])
            user_id = payload.get('u')
            correo_sistema = payload.get('email')
        except Exception:
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=session_lost')
        if not user_id or not code:
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=session_lost')
        token_url_with_params = f'{CLICKUP_TOKEN_URL}?client_id={CLIENT_ID}&client_secret={CLIENT_SECRET}&code={code}'
        token_resp = requests.post(token_url_with_params, timeout=15)
        token_res = token_resp.json()
        if 'access_token' not in token_res:
            logger.error(f'ClickUp Token Error: {token_res}')
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=token_exchange_failed')
        access_token = token_res['access_token']
        refresh_token = ''
        expires_in = 0
        clickup_account_id = 'unknown'
        email = ''
        name = 'unknown'
        try:
            headers = {'Authorization': access_token}
            user_resp = requests.get(CLICKUP_USER_INFO, headers=headers, timeout=10)
            if user_resp.status_code == 200:
                user_info = user_resp.json().get('user', {})
                clickup_account_id = str(user_info.get('id', 'unknown'))
                email = user_info.get('email', '')
                name = user_info.get('username', 'unknown')
        except Exception as e:
            logger.warning(f'Error fetching ClickUp userinfo: {e}')
        now_utc = datetime.now(timezone.utc)
        encrypted_access = encrypt_data(access_token)
        new_account_doc = {'user_id': str(user_id), 'provider': 'clickup', 'account_id': clickup_account_id, 'access_token': encrypted_access, 'refresh_token': '', 'expires_in': expires_in, 'status': 'active', 'timestamp': now_utc.strftime('%Y-%m-%d %H:%M:%S'), 'metadata': {'clickup_id': clickup_account_id, 'name': name, 'email': email, 'connected_at': now_utc.isoformat()}}
        db = request.app.state.db
        try:
            await db[Collections.USER_CONNECTED_ACCOUNTS].update_one({'user_id': str(user_id), 'provider': 'clickup', 'account_id': clickup_account_id}, {'$set': new_account_doc}, upsert=True)
        except Exception as e:
            logger.error(f'Error DB ClickUp: {e}')
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=database_error')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?clickup_status=connected')
    except Exception as e:
        logger.error(f'CLICKUP ERROR CRÍTICO: {e}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=internal_server_error')

@router.get('/status')
def status():
    return JSONResponse({'connected': True})

@router.delete('')
def disconnect():
    return JSONResponse({'success': True})


# ── Service Layer ──────────────────────────────────────────────────────────────
import logging
from typing import Dict, Any, Optional
from dotenv import load_dotenv
from app.core.mongo import get_sync_database
from app.core.constants import Collections
from app.core.db_utils import canonicalize_email
load_dotenv()
logger = logging.getLogger(__name__)

def _get_db():
    return get_sync_database()

def get_clickup_creds_for_langchain(email: str) -> Dict[str, Any]:
    """
    Recupera las credenciales de ClickUp almacenadas en MongoDB (colección oauth_vault)
    para el usuario identificado por su correo.
    """
    try:
        db = _get_db()
        email_safe = canonicalize_email(email)
        vault_data = db[Collections.OAUTH_VAULT].find_one({'$or': [{'correo': email_safe}, {'email': email_safe}]})
        clickup_creds: Optional[Dict[str, Any]] = None
        if vault_data:
            clickup_creds = vault_data.get('integrations', {}).get('ClickUp') or vault_data.get('ClickUp')
        if clickup_creds:
            return {'access_token': clickup_creds.get('token'), 'refresh_token': clickup_creds.get('refresh_token'), 'timestamp': clickup_creds.get('timestamp')}
        logger.warning('No se encontraron credenciales de ClickUp en oauth_vault para el usuario proporcionado.')
        return {'error': 'No encontré credenciales de ClickUp'}
    except Exception as e:
        logger.exception('Error de conexión o lectura en oauth_vault al consultar ClickUp')
        return {'error': 'Error interno al consultar las credenciales'}
if __name__ == '__main__':
    import sys
    correo_test = 'ecalcinap@unsa.edu.pe'
    creds = get_clickup_creds_for_langchain(correo_test)
    print(' Resultado de la búsqueda:')
    if 'error' in creds:
        print(f" Error: {creds['error']}")
    else:
        print(' Credenciales encontradas en oauth_vault!')
        print('   Access Token: [OCULTO POR SEGURIDAD]')
        print('   Refresh Token: [OCULTO POR SEGURIDAD]')
        print(f"   Timestamp: {creds.get('timestamp', 'N/A')}")

