"""
Facebook OAuth 2.0 Authentication Module (FastAPI Version)
Migrated to Secure OAuth Vault
"""
import os
import jwt
import secrets
import logging
import requests
import urllib.parse
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Request, Depends, HTTPException
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
logger = logging.getLogger('auth.facebook')
FB_API_VERSION = 'v19.0'
FB_AUTH_URL = f'https://www.facebook.com/{FB_API_VERSION}/dialog/oauth'
FB_TOKEN_URL = f'https://graph.facebook.com/{FB_API_VERSION}/oauth/access_token'
FB_ME_URL = f'https://graph.facebook.com/{FB_API_VERSION}/me'
FB_SCOPES = ['public_profile', 'email']
FRONTEND_REDIRECT_URL = os.getenv('FRONTEND_REDIRECT_URL', 'https://hypershifu.com/chat')

@router.get('/login')
async def login(user: dict=Depends(get_current_user)):
    user_id = str(user.get('_id', user.get('id', '')))
    correo = user.get('correo') or user.get('email', '')
    if not user_id or not correo:
        raise HTTPException(status_code=401, detail='Usuario inválido o sin correo')
    nonce = secrets.token_urlsafe(32)
    state_payload = {'nonce': nonce, 'u': user_id, 'email': correo, 'correo': correo, 'exp': datetime.now(timezone.utc).timestamp() + 600}
    state = jwt.encode(state_payload, SECRET_KEY, algorithm='HS256')
    client_id = os.getenv('FACEBOOK_CLIENT_ID')
    redirect_uri = os.getenv('FACEBOOK_REDIRECT_URI')
    if not client_id or not redirect_uri:
        logger.error('Falta configuración de cliente de Facebook')
        raise HTTPException(status_code=500, detail='Server misconfiguration')
    params = {'client_id': client_id, 'redirect_uri': redirect_uri, 'state': state, 'scope': ','.join(FB_SCOPES), 'response_type': 'code', 'auth_type': 'reauthenticate'}
    auth_url = f'{FB_AUTH_URL}?{urllib.parse.urlencode(params)}'
    return JSONResponse({'url': auth_url})

@router.get('/callback')
async def callback(request: Request, db=Depends(get_db)):
    state_jwt = request.query_params.get('state')
    code = request.query_params.get('code')
    error = request.query_params.get('error')
    if error:
        logger.warning(f'Facebook Auth Error: {error}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=auth_failed')
    user_id, correo = (None, None)
    if state_jwt:
        try:
            payload = jwt.decode(state_jwt, SECRET_KEY, algorithms=['HS256'])
            user_id = payload.get('u')
            correo = payload.get('correo') or payload.get('email')
        except Exception as e:
            logger.warning(f'Invalid state JWT en Facebook: {e}')
    if not user_id or not correo:
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=session_lost')
    if not code:
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=missing_code')
    email_safe = correo.strip().lower()
    client_id = os.getenv('FACEBOOK_CLIENT_ID')
    client_secret = os.getenv('FACEBOOK_CLIENT_SECRET')
    redirect_uri = os.getenv('FACEBOOK_REDIRECT_URI')
    try:
        token_resp = requests.get(FB_TOKEN_URL, params={'client_id': client_id, 'client_secret': client_secret, 'redirect_uri': redirect_uri, 'code': code}, timeout=15)
        token_data = token_resp.json()
    except requests.RequestException as e:
        logger.error(f'Facebook Network Error (Short Token): {e}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=token_exchange_network_error')
    if 'access_token' not in token_data:
        logger.error(f'FB Token Error: {token_data}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=token_exchange_failed')
    short_lived_token = token_data['access_token']
    try:
        long_token_resp = requests.get(FB_TOKEN_URL, params={'grant_type': 'fb_exchange_token', 'client_id': client_id, 'client_secret': client_secret, 'fb_exchange_token': short_lived_token}, timeout=15)
        long_token_data = long_token_resp.json()
    except requests.RequestException as e:
        logger.error(f'Facebook Network Error (Long Token): {e}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=token_exchange_network_error')
    final_token = long_token_data.get('access_token', short_lived_token)
    expires_in = long_token_data.get('expires_in', 3600)
    user_data = {}
    try:
        user_resp = requests.get(FB_ME_URL, params={'fields': 'id,name,email,picture', 'access_token': final_token}, timeout=10)
        if user_resp.status_code == 200:
            user_data = user_resp.json()
    except requests.RequestException as e:
        logger.warning(f'No se pudo obtener el perfil de Facebook: {e}')
    fb_account_id = user_data.get('id')
    if not fb_account_id:
        logger.error('Facebook Error: No se pudo obtener el ID de Facebook del usuario.')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=missing_provider_id')
    encrypted_token = encrypt_data(final_token) if final_token else None
    now_utc = datetime.now(timezone.utc)
    new_account_doc = {'user_id': str(user_id), 'provider': 'facebook', 'account_id': fb_account_id, 'access_token': encrypted_token, 'refresh_token': 'n/a', 'expires_in': expires_in, 'status': 'active', 'timestamp': now_utc.strftime('%Y-%m-%d %H:%M:%S'), 'metadata': {'facebook_id': fb_account_id, 'name': user_data.get('name'), 'email': user_data.get('email'), 'picture': user_data.get('picture', {}).get('data', {}).get('url'), 'expires_at': (now_utc + timedelta(seconds=expires_in)).isoformat(), 'connected_at': now_utc.isoformat()}}
    try:
        await db[Collections.USER_CONNECTED_ACCOUNTS].update_one({'user_id': str(user_id), 'provider': 'facebook', 'account_id': fb_account_id}, {'$set': new_account_doc}, upsert=True)
    except Exception as e:
        logger.error(f'Error guardando Facebook en connected_accounts: {e}', exc_info=True)
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=database_error')
    logger.info(f"Facebook de {user_data.get('name')} conectado exitosamente en nuevo esquema.")
    return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?facebook_status=connected')

@router.get('/status')
def status():
    return JSONResponse({'connected': True})

@router.delete('')
def disconnect():
    return JSONResponse({'success': True})


# ── Service Layer ──────────────────────────────────────────────────────────────
"""
Facebook Service - Credenciales OAuth y refresco de tokens

Migrado a lectura desde oauth_vault (Vault-First / Legacy-Fallback).
Escritura exclusiva en oauth_vault con tokens encriptados y sin pérdida de metadatos.
100% síncrono — compatible con LangChain / LangGraph.
Refactorización Enterprise: Single Source of Truth (Config) y Alias Matching.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
import requests
from dotenv import load_dotenv
from config import Config
from app.core.mongo import get_sync_database
from app.database import _normalize_integrations
from app.core.constants import Collections
from app.core.db_utils import canonicalize_email, find_user_by_email
load_dotenv()
try:
    from app.core.security import encrypt_data
except ImportError:
    logging.getLogger(__name__).warning('[facebook_service] Módulo de encriptación no disponible. Usando texto plano (MODO DEV).')

    def encrypt_data(data: str) -> str:
        return data
logger = logging.getLogger('services.facebook')
INTEGRATION_NAME = 'Facebook'
TOKEN_URL = 'https://graph.facebook.com/v12.0/oauth/access_token'
_REQUEST_TIMEOUT = 15
_FB_KEY_ALIASES = ('Facebook', 'facebook', 'FB', 'fb')

def _get_db():
    return get_sync_database()

def _find_facebook_integration(integrations: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Busca las credenciales tolerando variaciones de capitalización.
    Retorna una tupla: (credenciales_encontradas, clave_original_exacta)
    """
    norm = lambda k: k.lower().replace(' ', '_').replace('-', '_')
    for key, value in integrations.items():
        if norm(key) in [norm(alias) for alias in _FB_KEY_ALIASES]:
            if isinstance(value, dict):
                return (value, key)
    return (None, None)

def _persist_to_vault(email: str, token: str, expires_in: int, exact_key: str=INTEGRATION_NAME) -> None:
    """
    Actualiza específicamente el token de Facebook en oauth_vault sin destruir metadatos.
    Migra usuarios legacy creando el documento base si no existe.
    """
    db = _get_db()
    now_utc = datetime.now(timezone.utc)
    timestamp_str = now_utc.strftime('%Y-%m-%d %H:%M:%S')
    enc_token = encrypt_data(token) if token else ''
    user_id = 'unknown'
    legacy_user = find_user_by_email(db, email)
    if legacy_user and legacy_user.get('_id'):
        user_id = str(legacy_user['_id'])
    try:
        result = db[Collections.OAUTH_VAULT].update_one({'$or': [{'correo': email}, {'email': email}]}, {'$set': {f'integrations.{exact_key}.token': enc_token, f'integrations.{exact_key}.expires_in': expires_in, f'integrations.{exact_key}.timestamp': timestamp_str, 'updated_at': now_utc}, '$setOnInsert': {'created_at': now_utc, 'user_id': user_id, 'provider': 'server_side_oauth', 'status': 'active'}}, upsert=True)
        if result.upserted_id:
            logger.info(f"[facebook_service] Nuevo documento creado en oauth_vault para '{email}'.")
        else:
            logger.info(f"[facebook_service] Tokens actualizados en oauth_vault para '{email}'.")
    except Exception as e:
        logger.error(f"[facebook_service] Fallo al escribir en oauth_vault para '{email}': {e}", exc_info=True)
        raise

def get_credentials(email: str) -> Optional[str]:
    """
    Lee de oauth_vault con fallback a usuarios legacy.
    Devuelve estrictamente el string del token desencriptado.
    """
    if not email:
        logger.warning('[facebook_service] get_credentials called without an email.')
        return None
    email_safe = canonicalize_email(email)
    db = _get_db()
    try:
        fb_creds: Optional[Dict[str, Any]] = None
        exact_key: Optional[str] = None
        integrations = {}
        vault_doc = db[Collections.OAUTH_VAULT].find_one({'$or': [{'correo': email_safe}, {'email': email_safe}]})
        if vault_doc and vault_doc.get('integrations'):
            integrations = _normalize_integrations(vault_doc['integrations'], source='vault', correo=email_safe)
            fb_creds, exact_key = _find_facebook_integration(integrations)
        if not fb_creds:
            legacy_doc = db[Collections.USERS].find_one({'$or': [{'correo': email_safe}, {'email': email_safe}]})
            if legacy_doc:
                integrations = _normalize_integrations(legacy_doc.get('integrations', {}), source='legacy', correo=email_safe)
                fb_creds, exact_key = _find_facebook_integration(integrations)
                if fb_creds:
                    logger.warning(f"[facebook_service] Fallback legacy activo para '{email_safe}'.")
        if not fb_creds:
            return None
        return fb_creds.get('token')
    except Exception as e:
        logger.error(f"[facebook_service] Error de BD al leer credenciales para '{email_safe}': {e}")
        return None

def exchange_code_for_token(authorization_code: str, email: str) -> Optional[Dict[str, Any]]:
    """Procesa el código inicial de Auth y guarda en la bóveda."""
    if not email:
        return None
    email_safe = canonicalize_email(email)
    data = {'code': authorization_code, 'redirect_uri': Config.FRONTEND_REDIRECT_URL, 'client_id': Config.FACEBOOK_CLIENT_ID, 'client_secret': Config.FACEBOOK_CLIENT_SECRET}
    try:
        response = requests.post(TOKEN_URL, data=data, timeout=_REQUEST_TIMEOUT)
        if response.status_code == 200:
            response_data = response.json()
            access_token = response_data.get('access_token', '')
            expires_in = int(response_data.get('expires_in') or 0)
            _persist_to_vault(email_safe, access_token, expires_in)
            return {'token': access_token, 'expires_in': expires_in, 'timestamp': datetime.now()}
        else:
            logger.error(f'[facebook_service] Error oauth: {response.status_code} - {response.text}')
            return None
    except requests.exceptions.RequestException as exc:
        logger.error(f'[facebook_service] Error de red en facebooklog: {exc}')
        return None

def refresh_token(email: str) -> Optional[Dict[str, Any]]:
    """Refresca el Long-Lived token usando el token existente y actualiza la bóveda."""
    if not email:
        return None
    email_safe = canonicalize_email(email)
    current_token = get_credentials(email_safe)
    if not current_token:
        logger.error(f"[facebook_service] No hay token de Facebook para refrescar en '{email_safe}'.")
        return None
    data = {'grant_type': 'fb_exchange_token', 'client_id': Config.FACEBOOK_CLIENT_ID, 'client_secret': Config.FACEBOOK_CLIENT_SECRET, 'fb_exchange_token': current_token}
    try:
        response = requests.post(TOKEN_URL, data=data, timeout=_REQUEST_TIMEOUT)
        if response.status_code == 200:
            response_data = response.json()
            new_access_token = response_data.get('access_token', '')
            new_expires_in = int(response_data.get('expires_in') or 0)
            _persist_to_vault(email_safe, new_access_token, new_expires_in)
            logger.info(f"[facebook_service] Token refrescado exitosamente para '{email_safe}'.")
            return {'token': new_access_token, 'expires_in': new_expires_in, 'timestamp': datetime.now()}
        else:
            logger.error(f'[facebook_service] Error refreshing token: {response.status_code} - {response.text}')
            return None
    except requests.exceptions.RequestException as exc:
        logger.error(f'[facebook_service] Network error in refresh_token: {exc}')
        return None

