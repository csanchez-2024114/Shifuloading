"""
Microsoft Teams OAuth 2.0 Authentication Module — FastAPI Version (V2 Architecture)
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
from app.core.constants import Collections
logger = logging.getLogger(__name__)
router = APIRouter()
TEAMS_CLIENT_ID = os.getenv('TEAMS_CLIENT_ID')
TEAMS_CLIENT_SECRET = os.getenv('TEAMS_CLIENT_SECRET')
TEAMS_REDIRECT_URI = os.getenv('TEAMS_REDIRECT_URI')
AUTH_URL = 'https://login.microsoftonline.com/common/oauth2/v2.0/authorize'
TOKEN_URL = 'https://login.microsoftonline.com/common/oauth2/v2.0/token'
GRAPH_ME_URL = 'https://graph.microsoft.com/v1.0/me'
FRONTEND_REDIRECT_URL = os.getenv('FRONTEND_REDIRECT_URL', 'https://hypershifu.com/chat')
SECRET_KEY = os.getenv('SECRET_KEY')
TEAMS_SCOPES = ['offline_access', 'User.Read', 'ChatMessage.Read', 'Channel.ReadBasic.All', 'Team.ReadBasic.All']

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
        logger.warning('Intento de login Teams sin correo o ID válido.')
        raise HTTPException(status_code=401, detail='Usuario inválido o sin correo')
    state = jwt.encode({'u': actual_user_id, 'email': correo_sistema, 'correo': correo_sistema, 'exp': datetime.now(timezone.utc).timestamp() + 600}, SECRET_KEY, algorithm='HS256')
    params = {'client_id': TEAMS_CLIENT_ID, 'response_type': 'code', 'redirect_uri': TEAMS_REDIRECT_URI, 'response_mode': 'query', 'scope': ' '.join(TEAMS_SCOPES), 'state': state, 'prompt': 'select_account'}
    auth_url = f'{AUTH_URL}?{urllib.parse.urlencode(params)}'
    return {'url': auth_url}

@router.get('/callback')
async def callback(request: Request):
    try:
        state_jwt = request.query_params.get('state')
        code = request.query_params.get('code')
        error = request.query_params.get('error')
        if error:
            logger.warning(f'Teams Auth Error: {error}')
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error={error}')
        try:
            payload = jwt.decode(state_jwt, SECRET_KEY, algorithms=['HS256'])
            user_id = payload.get('u')
        except Exception:
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=session_lost')
        if not user_id or not code:
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=session_lost')
        data = {'client_id': TEAMS_CLIENT_ID, 'client_secret': TEAMS_CLIENT_SECRET, 'scope': ' '.join(TEAMS_SCOPES), 'code': code, 'redirect_uri': TEAMS_REDIRECT_URI, 'grant_type': 'authorization_code'}
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        token_resp = requests.post(TOKEN_URL, data=data, headers=headers, timeout=15)
        token_res = token_resp.json()
        if 'access_token' not in token_res:
            logger.error(f'Teams Token Error: {token_resp.status_code} - {token_res}')
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
            logger.warning(f'Error fetching Teams /me: {e}')
        if not ms_id:
            logger.error('Teams Error: No se pudo obtener el ID de Microsoft del usuario.')
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=missing_provider_id')
        now_utc = datetime.now(timezone.utc)
        encrypted_access = encrypt_data(access_token)
        encrypted_refresh = encrypt_data(refresh_token) if refresh_token else ''
        new_account_doc = {'user_id': str(user_id), 'provider': 'teams', 'account_id': ms_id, 'access_token': encrypted_access, 'refresh_token': encrypted_refresh, 'expires_in': 3600, 'timestamp': now_utc.strftime('%Y-%m-%d %H:%M:%S'), 'status': 'active', 'metadata': {'microsoft_id': ms_id, 'name': ms_name, 'email': ms_email, 'connected_at': now_utc.isoformat()}}
        connected_accounts_col = request.app.state.db[Collections.USER_CONNECTED_ACCOUNTS]
        await connected_accounts_col.update_one({'user_id': str(user_id), 'provider': 'teams', 'account_id': ms_id}, {'$set': new_account_doc}, upsert=True)
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?teams_status=connected')
    except Exception as e:
        logger.error(f'TEAMS ERROR CRÍTICO: {e}', exc_info=True)
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=internal_server_error')

@router.get('/status')
def status():
    return JSONResponse({'connected': True})

@router.delete('')
def disconnect():
    return JSONResponse({'success': True})


# ── Service Layer ──────────────────────────────────────────────────────────────
"""
Microsoft Teams Service - Credenciales OAuth y llamadas a la API
Refactorizado: Single Source of Truth (Config), Timeouts y Logging Enterprise.
"""
import logging
import requests
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
from config import Config
from app.core.mongo import get_sync_database
from app.core.constants import Collections
from app.core.db_utils import find_user_by_email, canonicalize_email
logger = logging.getLogger('services.teams')
GRAPH_API_URL = 'https://graph.microsoft.com/v1.0'
TOKEN_URL = 'https://login.microsoftonline.com/common/oauth2/v2.0/token'
_REQUEST_TIMEOUT = 15

def _get_db():
    """Obtiene la base de datos síncrona."""
    return get_sync_database()

def get_teams_headers(email: str) -> Dict[str, str]:
    """
    Obtiene los headers de autorización válidos para un usuario.
    Si el token ha expirado, intenta refrescarlo automáticamente.
    """
    db = _get_db()
    email_safe = canonicalize_email(email)
    user_data = db[Collections.OAUTH_VAULT].find_one({'$or': [{'correo': email_safe}, {'email': email_safe}]})
    collection_to_update = Collections.OAUTH_VAULT
    if not user_data or 'integrations' not in user_data or 'teams' not in user_data['integrations']:
        user_data = find_user_by_email(db, email_safe)
        collection_to_update = Collections.USERS
    if not user_data or 'integrations' not in user_data or 'teams' not in user_data['integrations']:
        logger.warning(f"[teams_service] Usuario '{email_safe}' no conectado a Microsoft Teams.")
        raise Exception('Usuario no conectado a Microsoft Teams')
    teams_data = user_data['integrations']['teams']
    access_token = teams_data.get('access_token')
    expires_at = teams_data.get('expires_at')
    refresh_token = teams_data.get('refresh_token')
    now_utc = datetime.now(timezone.utc)
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if not expires_at or now_utc >= expires_at - timedelta(minutes=5):
        logger.info(f'[teams_service] Token expirado o próximo a expirar para {email_safe}. Refrescando...')
        new_tokens = refresh_access_token(refresh_token)
        if new_tokens and 'access_token' in new_tokens:
            access_token = new_tokens['access_token']
            expires_in = new_tokens.get('expires_in', 3600)
            new_expiry = now_utc + timedelta(seconds=expires_in)
            update_data = {'integrations.teams.access_token': access_token, 'integrations.teams.expires_at': new_expiry, 'updated_at': now_utc}
            if 'refresh_token' in new_tokens:
                update_data['integrations.teams.refresh_token'] = new_tokens['refresh_token']
            db[collection_to_update].update_one({'$or': [{'correo': email_safe}, {'email': email_safe}]}, {'$set': update_data})
            logger.info(f'[teams_service] Token refrescado y guardado exitosamente para {email_safe}.')
        else:
            logger.error(f'[teams_service] Fallo crítico al refrescar token para {email_safe}.')
            raise Exception('No se pudo refrescar el token de Teams. Requiere re-autenticación.')
    return {'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'}

def refresh_access_token(refresh_token: str) -> Optional[Dict[str, Any]]:
    """Solicita un nuevo Access Token usando el Refresh Token"""
    if not refresh_token:
        logger.error('[teams_service] Intento de refresco sin refresh_token.')
        return None
    data = {'client_id': Config.TEAMS_CLIENT_ID, 'client_secret': Config.TEAMS_CLIENT_SECRET, 'grant_type': 'refresh_token', 'refresh_token': refresh_token, 'scope': 'User.Read Chat.Read offline_access'}
    try:
        response = requests.post(TOKEN_URL, data=data, timeout=_REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except requests.Timeout:
        logger.error('[teams_service] Timeout al conectar con Microsoft Graph.')
        return None
    except Exception as e:
        logger.error(f'[teams_service] Falló el refresh token: {e}')
        return None

def get_user_profile(email: str) -> Dict[str, Any]:
    """Obtiene el perfil del usuario de Microsoft"""
    try:
        headers = get_teams_headers(email)
        response = requests.get(f'{GRAPH_API_URL}/me', headers=headers, timeout=_REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f'[teams_service] Error al obtener perfil: {e}')
        return {'error': str(e)}

def get_recent_chats(email: str) -> Dict[str, Any]:
    """Obtiene los chats recientes del usuario"""
    try:
        headers = get_teams_headers(email)
        url = f'{GRAPH_API_URL}/me/chats?$expand=lastMessagePreview&$top=10'
        response = requests.get(url, headers=headers, timeout=_REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f'[teams_service] Error al obtener chats: {e}')
        return {'error': str(e)}

def get_joined_teams(email: str) -> Dict[str, Any]:
    """Obtiene los equipos (Teams) a los que pertenece el usuario"""
    try:
        headers = get_teams_headers(email)
        url = f'{GRAPH_API_URL}/me/joinedTeams'
        response = requests.get(url, headers=headers, timeout=_REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f'[teams_service] Error al obtener joined teams: {e}')
        return {'error': str(e)}

