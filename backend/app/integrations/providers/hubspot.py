"""HubSpot OAuth routes - FastAPI native implementation."""
import logging
import os
import secrets
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple
import jwt
import requests
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from app.database import get_current_user, get_db
from app.core.constants import Collections
from config import Config
try:
    from app.core.security import encrypt_data
except ImportError:
    logger = logging.getLogger(__name__)
    logger.warning('Módulo de encriptación no encontrado. Se usará texto plano (MODO DEV).')
    encrypt_data = lambda x: x
logger = logging.getLogger('auth.hubspot')
router = APIRouter()
hubspot_auth_bp = router
HSPOT_AUTH_URL = 'https://app.hubspot.com/oauth/authorize'
HSPOT_TOKEN_URL = 'https://api.hubapi.com/oauth/v1/token'
HSPOT_TOKEN_INFO_URL = 'https://api.hubapi.com/oauth/v1/access-tokens/'
HSPOT_SCOPES = ['crm.objects.line_items.read', 'crm.objects.carts.write', 'crm.schemas.deals.read', 'crm.objects.line_items.write', 'crm.objects.carts.read', 'crm.objects.orders.write', 'oauth', 'crm.objects.owners.read', 'crm.objects.orders.read', 'crm.objects.invoices.read', 'crm.objects.leads.read', 'crm.objects.leads.write', 'crm.objects.users.read', 'tickets', 'crm.objects.contacts.write', 'crm.objects.users.write', 'crm.objects.appointments.read', 'crm.objects.appointments.write', 'crm.objects.companies.write', 'crm.objects.companies.read', 'crm.objects.deals.read', 'crm.objects.deals.write', 'crm.objects.quotes.write', 'crm.objects.contacts.read', 'crm.objects.quotes.read']
FRONTEND_REDIRECT_URL = os.getenv('FRONTEND_REDIRECT_URL', 'https://hypershifu.com/chat')

def _redirect_uri() -> str:
    return os.getenv('HUBSPOT_REDIRECT_URI') or os.getenv('FACEBOOK_REDIRECT_URI', '')

def _state_token(user_id: str, correo: str) -> str:
    payload = {'nonce': secrets.token_urlsafe(16), 'user_id': str(user_id), 'correo': correo, 'iat': int(datetime.now(timezone.utc).timestamp())}
    return jwt.encode(payload, Config.SECRET_KEY, algorithm='HS256')

def _decode_state(state_jwt: str) -> Tuple[Optional[str], Optional[str]]:
    try:
        payload = jwt.decode(state_jwt, Config.SECRET_KEY, algorithms=['HS256'])
        return (payload.get('user_id'), payload.get('correo'))
    except Exception as exc:
        logger.warning('State JWT inválido en callback HubSpot: %s', exc)
        return (None, None)

@router.get('/login')
async def login(user=Depends(get_current_user)):
    user_id = str(user.get('_id', user.get('id', '')))
    correo = user.get('correo') or user.get('email', '')
    if not user_id or not correo:
        raise HTTPException(status_code=401, detail='Usuario inválido o sin correo')
    client_id = os.getenv('HUBSPOT_CLIENT_ID')
    client_secret = os.getenv('HUBSPOT_CLIENT_SECRET')
    redirect_uri = _redirect_uri()
    if not client_id or not client_secret or (not redirect_uri):
        raise HTTPException(status_code=500, detail='Configuración OAuth de HubSpot incompleta')
    params = {'client_id': client_id, 'redirect_uri': redirect_uri, 'scope': ' '.join(HSPOT_SCOPES), 'response_type': 'code', 'state': _state_token(user_id, correo)}
    auth_url = requests.Request('GET', HSPOT_AUTH_URL, params=params).prepare().url
    return {'url': auth_url}

@router.get('/callback')
async def callback(request: Request, code: Optional[str]=None, state: Optional[str]=None, db=Depends(get_db)):
    user_id, correo = _decode_state(state) if state else (None, None)
    if not user_id or not correo:
        logger.warning('Fallo al recuperar identidad. Sesión perdida.')
        return RedirectResponse(url=f'{FRONTEND_REDIRECT_URL}?error=session_lost')
    if not code:
        return RedirectResponse(url=f'{FRONTEND_REDIRECT_URL}?error=missing_code')
    email_safe = correo.strip().lower()
    client_id = os.getenv('HUBSPOT_CLIENT_ID')
    client_secret = os.getenv('HUBSPOT_CLIENT_SECRET')
    redirect_uri = _redirect_uri()
    if not client_id or not client_secret or (not redirect_uri):
        return RedirectResponse(url=f'{FRONTEND_REDIRECT_URL}?error=config_error')
    try:
        token_response = requests.post(HSPOT_TOKEN_URL, data={'grant_type': 'authorization_code', 'client_id': client_id, 'client_secret': client_secret, 'redirect_uri': redirect_uri, 'code': code}, headers={'Content-Type': 'application/x-www-form-urlencoded'}, timeout=30)
        token_data = token_response.json()
        access_token = token_data.get('access_token')
        if not access_token:
            logger.error('HubSpot token exchange falló: %s', token_data)
            return RedirectResponse(url=f'{FRONTEND_REDIRECT_URL}?error=token_exchange_failed')
        refresh_token = token_data.get('refresh_token')
        expires_in = int(token_data.get('expires_in', 0) or 0)
        token_info = {}
        try:
            info_response = requests.get(f'{HSPOT_TOKEN_INFO_URL}{access_token}', timeout=20)
            if info_response.ok:
                token_info = info_response.json()
        except Exception as info_exc:
            logger.warning('No se pudo obtener token info de HubSpot: %s', info_exc)
        hub_id = str(token_info.get('hub_id'))
        user_email_hubspot = token_info.get('user', '')
        if not hub_id or hub_id == 'None':
            logger.error('HubSpot Error: No se pudo obtener el hub_id del token.')
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=missing_provider_id')
        encrypted_token = encrypt_data(access_token) if access_token else None
        encrypted_refresh = encrypt_data(refresh_token) if refresh_token else None
        now_utc = datetime.now(timezone.utc)
        new_account_doc = {'user_id': str(user_id), 'provider': 'hubspot', 'account_id': hub_id, 'access_token': encrypted_token, 'refresh_token': encrypted_refresh, 'expires_in': expires_in, 'status': 'active', 'timestamp': now_utc.strftime('%Y-%m-%d %H:%M:%S'), 'metadata': {'hub_id': hub_id, 'email': user_email_hubspot, 'scope': token_data.get('scope', ''), 'connected_at': now_utc.isoformat()}}
        try:
            await db[Collections.USER_CONNECTED_ACCOUNTS].update_one({'user_id': str(user_id), 'provider': 'hubspot', 'account_id': hub_id}, {'$set': new_account_doc, '$setOnInsert': {'created_at': now_utc}}, upsert=True)
        except Exception as e:
            logger.error(f'Error DB guardando HubSpot V2 para {email_safe}: {e}', exc_info=True)
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=database_error')
        logger.info(f'HubSpot conectado exitosamente en bóveda para {email_safe}')
        return RedirectResponse(url=f'{FRONTEND_REDIRECT_URL}?hubspot_status=connected')
    except Exception as exc:
        logger.error('Error fatal en callback HubSpot: %s', exc, exc_info=True)
        return RedirectResponse(url=f'{FRONTEND_REDIRECT_URL}?error=internal_server_error')


# ── Service Layer ──────────────────────────────────────────────────────────────
"""
HubSpot Service - Credenciales OAuth y refresco de tokens

Migrado a lectura desde oauth_vault (Vault-First / Legacy-Fallback).
Escritura exclusiva en oauth_vault con tokens encriptados y sin pérdida de metadatos.
100% síncrono — compatible con LangChain / LangGraph.
Refactorización: Single Source of Truth (Config) y Prevención de Corrupción MongoDB.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
import requests
from config import Config
from app.core.mongo import get_sync_database
from app.database import _normalize_integrations
from app.core.constants import Collections
from app.core.db_utils import find_user_by_email, canonicalize_email
try:
    from app.core.security import encrypt_data
except ImportError:
    logging.getLogger(__name__).warning('[hubspot_service] Módulo de encriptación no disponible. Usando texto plano (MODO DEV).')

    def encrypt_data(data: str) -> str:
        return data
logger = logging.getLogger('services.hubspot')
INTEGRATION_NAME = 'HubSpot'
TOKEN_URL = 'https://api.hubapi.com/oauth/v1/token'
_REQUEST_TIMEOUT = 15
_HUBSPOT_KEY_ALIASES = ('HubSpot', 'hubspot', 'Hubspot')

def _get_db():
    return get_sync_database()

def _find_hubspot_integration(integrations: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Busca las credenciales tolerando variaciones de capitalización.
    Retorna una tupla: (credenciales_encontradas, clave_original_exacta)
    """
    norm = lambda k: k.lower().replace(' ', '_').replace('-', '_')
    for key, value in integrations.items():
        if norm(key) in [norm(alias) for alias in _HUBSPOT_KEY_ALIASES]:
            if isinstance(value, dict):
                return (value, key)
    return (None, None)

def getbearertoken(authorization_code: str) -> Optional[Dict[str, Any]]:
    """Intercambia un authorization_code por access_token + refresh_token."""
    data = {'grant_type': 'authorization_code', 'code': authorization_code, 'redirect_uri': Config.FRONTEND_REDIRECT_URL, 'client_id': Config.HUBSPOT_CLIENT_ID, 'client_secret': Config.HUBSPOT_CLIENT_SECRET}
    try:
        response = requests.post(TOKEN_URL, data=data, timeout=_REQUEST_TIMEOUT)
        if response.status_code == 200:
            return response.json()
        logger.warning(f'[hubspot_service] getbearertoken falló [{response.status_code}]: {response.text}')
    except requests.exceptions.RequestException as exc:
        logger.error(f'[hubspot_service] Error de red en getbearertoken: {exc}')
    return None

def getrefreshbearertoken(refreshtoken: str) -> Optional[Dict[str, Any]]:
    """Refresca el access_token usando el refresh_token."""
    data = {'grant_type': 'refresh_token', 'redirect_uri': Config.FRONTEND_REDIRECT_URL, 'client_id': Config.HUBSPOT_CLIENT_ID, 'client_secret': Config.HUBSPOT_CLIENT_SECRET, 'refresh_token': refreshtoken}
    try:
        response = requests.post(TOKEN_URL, data=data, timeout=_REQUEST_TIMEOUT)
        if response.status_code == 200:
            return response.json()
        logger.warning(f'[hubspot_service] getrefreshbearertoken falló [{response.status_code}]: {response.text}')
    except requests.exceptions.RequestException as exc:
        logger.error(f'[hubspot_service] Error de red en getrefreshbearertoken: {exc}')
    return None

def _persist_to_vault(email: str, token: str, refresh_token: str, expires_in: int, exact_key: str=INTEGRATION_NAME) -> None:
    """
    Actualiza específicamente los tokens en oauth_vault sin destruir metadatos.
    Migra usuarios legacy creando el documento base si no existe.
    """
    db = _get_db()
    now_utc = datetime.now(timezone.utc)
    timestamp_str = now_utc.strftime('%Y-%m-%d %H:%M:%S')
    enc_token = encrypt_data(token) if token else ''
    enc_refresh = encrypt_data(refresh_token) if refresh_token else ''
    email_safe = canonicalize_email(email)
    user_id = 'unknown'
    legacy_user = find_user_by_email(db, email_safe)
    if legacy_user and legacy_user.get('_id'):
        user_id = str(legacy_user['_id'])
    try:
        result = db[Collections.OAUTH_VAULT].update_one({'$or': [{'correo': email_safe}, {'email': email_safe}]}, {'$set': {f'integrations.{exact_key}.token': enc_token, f'integrations.{exact_key}.refresh_token': enc_refresh, f'integrations.{exact_key}.expires_in': expires_in, f'integrations.{exact_key}.timestamp': timestamp_str, 'updated_at': now_utc, 'correo': email_safe, 'email': email_safe}, '$setOnInsert': {'created_at': now_utc, 'user_id': user_id, 'provider': 'server_side_oauth', 'status': 'active'}}, upsert=True)
        if result.upserted_id:
            logger.info(f"[hubspot_service] Nuevo documento creado en oauth_vault para '{email_safe}'.")
        else:
            logger.info(f"[hubspot_service] Tokens actualizados en oauth_vault para '{email_safe}'.")
    except Exception as e:
        logger.error(f"[hubspot_service] Fallo al escribir en oauth_vault para '{email}': {e}", exc_info=True)
        raise

def _get_hubspot_creds_and_key(email_safe: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """Helper interno para recuperar credenciales y su llave exacta para evitar duplicidad."""
    db = _get_db()
    try:
        hubspot_creds: Optional[Dict[str, Any]] = None
        exact_key: Optional[str] = None
        integrations = {}
        vault_doc = db[Collections.OAUTH_VAULT].find_one({'$or': [{'correo': email_safe}, {'email': email_safe}]})
        if vault_doc and vault_doc.get('integrations'):
            integrations = _normalize_integrations(vault_doc['integrations'], source='vault', correo=email_safe)
            hubspot_creds, exact_key = _find_hubspot_integration(integrations)
        if not hubspot_creds:
            legacy_doc = find_user_by_email(db, email_safe)
            if legacy_doc:
                integrations = _normalize_integrations(legacy_doc.get('integrations', {}), source='legacy', correo=email_safe)
                hubspot_creds, exact_key = _find_hubspot_integration(integrations)
                if hubspot_creds:
                    logger.warning(f"[hubspot_service] Fallback legacy activo para '{email_safe}'.")
        return (hubspot_creds, exact_key or INTEGRATION_NAME)
    except Exception as e:
        logger.error(f"[hubspot_service] Error de BD al leer credenciales para '{email_safe}': {e}")
        return (None, INTEGRATION_NAME)

def get_credentials(email: str) -> Optional[Dict[str, Any]]:
    """
    Lee de oauth_vault con fallback a usuarios legacy. Retorna desencriptado.
    """
    if not email:
        logger.warning('[hubspot_service] get_credentials called without an email.')
        return None
    creds, _ = _get_hubspot_creds_and_key(canonicalize_email(email))
    return creds

def create_credentials(authorization_code: str, email: str) -> Optional[Dict[str, Any]]:
    """Procesa el código inicial de Auth y guarda en la bóveda."""
    if not email:
        return None
    email_safe = canonicalize_email(email)
    credentials = getbearertoken(authorization_code=authorization_code)
    if not credentials:
        logger.error(f"[hubspot_service] Falló el intercambio de auth_code para '{email_safe}'.")
        return None
    access_token = credentials.get('access_token', '')
    refresh_token = credentials.get('refresh_token', '')
    expires_in = int(credentials.get('expires_in') or 0)
    _persist_to_vault(email_safe, access_token, refresh_token, expires_in, exact_key=INTEGRATION_NAME)
    return {'token': access_token, 'refresh_token': refresh_token, 'expires_in': expires_in, 'timestamp': datetime.now()}

def refresh_token(email: str) -> Optional[Dict[str, Any]]:
    """Refresca el token usando la credencial existente y actualiza la bóveda."""
    if not email:
        return None
    email_safe = canonicalize_email(email)
    current_creds, exact_key = _get_hubspot_creds_and_key(email_safe)
    if not current_creds or not current_creds.get('refresh_token'):
        logger.error(f"[hubspot_service] No hay refresh_token disponible para '{email_safe}'.")
        return None
    refresh_token = current_creds['refresh_token']
    response_data = getrefreshbearertoken(refresh_token)
    if not response_data:
        logger.error(f"[hubspot_service] La API rechazó el refresh para '{email_safe}'.")
        return None
    new_access_token = response_data.get('access_token', '')
    new_refresh_token = response_data.get('refresh_token', refresh_token)
    new_expires_in = int(response_data.get('expires_in') or 0)
    _persist_to_vault(email_safe, new_access_token, new_refresh_token, new_expires_in, exact_key=exact_key)
    logger.info(f"[hubspot_service] Token refrescado exitosamente para '{email_safe}'.")
    return {'token': new_access_token, 'refresh_token': new_refresh_token, 'expires_in': new_expires_in, 'timestamp': datetime.now()}

