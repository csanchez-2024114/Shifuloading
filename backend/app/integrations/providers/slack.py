"""
Slack OAuth 2.0 Authentication Module
Migrated to Secure Async OAuth Vault
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
from app.database import get_current_user, get_db, SECRET_KEY
from app.core.constants import Collections
try:
    from app.core.security import encrypt_data
except ImportError:
    logger = logging.getLogger(__name__)
    logger.warning('Módulo de encriptación no encontrado. Se usará texto plano (MODO DEV).')
    encrypt_data = lambda x: x
logger = logging.getLogger('auth.slack')
router = APIRouter()
SLACK_CLIENT_ID = os.getenv('SLACK_CLIENT_ID')
SLACK_CLIENT_SECRET = os.getenv('SLACK_CLIENT_SECRET')
SLACK_REDIRECT_URI = os.getenv('SLACK_REDIRECT_URI')
SLACK_AUTH_URL = 'https://slack.com/oauth/v2/authorize'
SLACK_TOKEN_URL = 'https://slack.com/api/oauth.v2.access'
FRONTEND_REDIRECT_URL = os.getenv('FRONTEND_REDIRECT_URL', 'https://hypershifu.com/chat')
SLACK_SCOPES = ['channels:read', 'chat:write', 'users:read']

@router.get('/login')
async def login(user: dict=Depends(get_current_user)):
    """
    Inicia el flujo OAuth. Empaqueta el ID y el Correo del usuario
    en el token JWT para poder recuperarlo de forma segura.
    """
    user_id = str(user.get('_id', user.get('id', '')))
    correo = user.get('correo') or user.get('email', '')
    if not user_id or not correo:
        logger.warning('Intento de login Slack sin correo o ID válido.')
        raise HTTPException(status_code=401, detail='Usuario inválido o sin correo')
    nonce = secrets.token_urlsafe(32)
    state_payload = {'nonce': nonce, 'u': user_id, 'email': correo, 'correo': correo, 'exp': datetime.now(timezone.utc).timestamp() + 600}
    state = jwt.encode(state_payload, SECRET_KEY, algorithm='HS256')
    params = {'client_id': SLACK_CLIENT_ID, 'scope': ','.join(SLACK_SCOPES), 'redirect_uri': SLACK_REDIRECT_URI, 'state': state, 'prompt': 'consent'}
    auth_url = f'{SLACK_AUTH_URL}?{urllib.parse.urlencode(params)}'
    return JSONResponse({'url': auth_url})

@router.get('/callback')
async def callback(request: Request, db=Depends(get_db)):
    """
    Recibe el código de Slack, solicita el Token y lo guarda ENCRIPTADO
    directamente en la Bóveda Segura asíncrona (oauth_vault).
    """
    state_jwt = request.query_params.get('state')
    code = request.query_params.get('code')
    error = request.query_params.get('error')
    if error:
        logger.warning(f'Slack Auth Denegado por usuario o API: {error}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error={error}')
    if not state_jwt or not code:
        logger.warning('Callback de Slack incompleto (Falta state o code).')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=missing_parameters')
    user_id, correo = (None, None)
    try:
        payload = jwt.decode(state_jwt, SECRET_KEY, algorithms=['HS256'])
        user_id = payload.get('u')
        correo = payload.get('correo') or payload.get('email')
    except jwt.ExpiredSignatureError:
        logger.warning('Slack Auth: JWT State expirado.')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=session_expired')
    except Exception as e:
        logger.warning(f'Slack Auth: Manipulación de JWT o error de firma: {e}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=session_lost')
    if not user_id or not correo:
        logger.warning('Fallo al recuperar identidad del state JWT. Sesión perdida.')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=session_lost')
    email_safe = correo.strip().lower()
    data = {'client_id': SLACK_CLIENT_ID, 'client_secret': SLACK_CLIENT_SECRET, 'code': code, 'redirect_uri': SLACK_REDIRECT_URI}
    try:
        token_resp = requests.post(SLACK_TOKEN_URL, data=data, timeout=15)
        token_res = token_resp.json()
    except requests.RequestException as e:
        logger.error(f'Slack Network Error (Token): {e}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=token_exchange_network_error')
    except ValueError:
        logger.error(f'Slack Invalid JSON Response: {token_resp.text}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=token_exchange_invalid_response')
    if not token_res.get('ok'):
        logger.error(f'Slack Token Exchange Error: {token_res}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=token_exchange_failed')
    slack_team_id = token_res.get('team', {}).get('id')
    if not slack_team_id:
        logger.error('Slack Error: No se pudo obtener el ID del Workspace (Team ID).')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=missing_provider_id')
    now_utc = datetime.now(timezone.utc)
    access_token = token_res.get('access_token')
    team_name = token_res.get('team', {}).get('name', 'Unknown Workspace')
    encrypted_token = encrypt_data(access_token) if access_token else None
    slack_payload = {'user_id': str(user_id), 'provider': 'slack', 'account_id': slack_team_id, 'access_token': encrypted_token, 'refresh_token': 'n/a', 'expires_in': 3600, 'status': 'active', 'timestamp': now_utc.strftime('%Y-%m-%d %H:%M:%S'), 'metadata': {'team_id': slack_team_id, 'team_name': team_name, 'bot_user_id': token_res.get('bot_user_id', ''), 'connected_at': now_utc.isoformat()}}
    try:
        await db[Collections.USER_CONNECTED_ACCOUNTS].update_one({'user_id': str(user_id), 'provider': 'slack', 'account_id': slack_team_id}, {'$set': slack_payload}, upsert=True)
    except Exception as e:
        logger.error(f'Error DB guardando Slack en user_connected_accounts para {email_safe}: {e}', exc_info=True)
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=database_error')
    logger.info(f"Guardando integración Slack '{slack_payload.get('team_name')}' en Bóveda para {email_safe}")
    return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?slack_status=connected')

@router.get('/status')
def status():
    """Endpoint simplificado. El status real lo maneja health_check."""
    return JSONResponse({'connected': True})

@router.delete('')
def disconnect():
    """Endpoint simplificado. El disconnect real lo maneja delete_integration."""
    return JSONResponse({'success': True})

