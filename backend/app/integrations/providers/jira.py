"""
JIRA OAuth 2.0
Migrated to Secure OAuth Vault
"""
import os
import jwt
import secrets
import logging
import requests
import urllib.parse
from datetime import datetime, timezone
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
logger = logging.getLogger('auth.jira')
router = APIRouter()
ATLASSIAN_AUTH_URL = 'https://auth.atlassian.com/authorize'
ATLASSIAN_TOKEN_URL = 'https://auth.atlassian.com/oauth/token'
ATLASSIAN_RESOURCES_URL = 'https://api.atlassian.com/oauth/token/accessible-resources'
FRONTEND_REDIRECT_URL = os.getenv('FRONTEND_REDIRECT_URL', 'https://hypershifu.com/chat')
JIRA_CLIENT_ID = os.getenv('JIRA_CLIENT_ID')
JIRA_CLIENT_SECRET = os.getenv('JIRA_CLIENT_SECRET')
JIRA_REDIRECT_URI = os.getenv('JIRA_REDIRECT_URI')
JIRA_SCOPES = ['read:jira-work', 'write:jira-work', 'read:jira-user', 'offline_access']

@router.get('/login')
async def login(user: dict=Depends(get_current_user)):
    """Inicia el flujo OAuth y firma el estado con el ID y Correo del usuario."""
    user_id = str(user.get('_id', user.get('id', '')))
    correo = user.get('correo') or user.get('email', '')
    if not user_id or not correo:
        raise HTTPException(status_code=401, detail='Usuario inválido o sin correo')
    nonce = secrets.token_urlsafe(32)
    state_payload = {'nonce': nonce, 'user_id': user_id, 'correo': correo}
    state = jwt.encode(state_payload, SECRET_KEY, algorithm='HS256')
    params = {'audience': 'api.atlassian.com', 'client_id': JIRA_CLIENT_ID, 'scope': ' '.join(JIRA_SCOPES), 'redirect_uri': JIRA_REDIRECT_URI, 'state': state, 'response_type': 'code', 'prompt': 'consent'}
    auth_url = f'{ATLASSIAN_AUTH_URL}?{urllib.parse.urlencode(params)}'
    return JSONResponse({'url': auth_url})

@router.get('/callback')
async def callback(request: Request, db=Depends(get_db)):
    state_jwt = request.query_params.get('state')
    code = request.query_params.get('code')
    error = request.query_params.get('error')
    if error:
        logger.warning(f'Jira Auth Error: {error}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=auth_failed')
    user_id, correo = (None, None)
    if state_jwt:
        try:
            state_payload = jwt.decode(state_jwt, SECRET_KEY, algorithms=['HS256'])
            user_id = state_payload.get('user_id')
            correo = state_payload.get('correo') or state_payload.get('email')
        except Exception:
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=session_lost')
    if not user_id or not correo:
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=session_lost')
    email_safe = correo.strip().lower()
    if not code:
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=missing_code')
    try:
        token_resp = requests.post(ATLASSIAN_TOKEN_URL, json={'grant_type': 'authorization_code', 'client_id': JIRA_CLIENT_ID, 'client_secret': JIRA_CLIENT_SECRET, 'code': code, 'redirect_uri': JIRA_REDIRECT_URI}, timeout=15)
        token_res = token_resp.json()
    except requests.RequestException as e:
        logger.error(f'Jira Token Network Error: {e}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=token_exchange_network_error')
    if 'access_token' not in token_res:
        logger.error(f'Jira Token Error: {token_res}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=token_exchange_failed')
    access_token = token_res['access_token']
    refresh_token = token_res.get('refresh_token')
    expires_in = token_res.get('expires_in', 3600)
    try:
        resources_resp = requests.get(ATLASSIAN_RESOURCES_URL, headers={'Authorization': f'Bearer {access_token}', 'Accept': 'application/json'}, timeout=15)
        resources = resources_resp.json()
    except requests.RequestException as e:
        logger.error(f'Jira Resources Network Error: {e}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=jira_resources_failed')
    if not resources or not isinstance(resources, list):
        logger.error(f'Jira Resources Empty or Invalid: {resources}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=no_jira_sites_found')
    cloud_id = resources[0].get('id')
    site_name = resources[0].get('name', 'Jira Workspace')
    avatar_url = resources[0].get('avatarUrl', '')
    if not cloud_id:
        logger.error('Jira Error: No se pudo obtener el Cloud ID del Workspace.')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=missing_provider_id')
    now_utc = datetime.now(timezone.utc)
    encrypted_token = encrypt_data(access_token) if access_token else None
    encrypted_refresh = encrypt_data(refresh_token) if refresh_token else None
    new_account_doc = {'user_id': str(user_id), 'provider': 'jira', 'account_id': cloud_id, 'access_token': encrypted_token, 'refresh_token': encrypted_refresh, 'expires_in': expires_in, 'status': 'active', 'timestamp': now_utc.strftime('%Y-%m-%d %H:%M:%S'), 'metadata': {'cloud_id': cloud_id, 'site_name': site_name, 'avatar_url': avatar_url, 'connected_at': now_utc.isoformat()}}
    try:
        await db[Collections.USER_CONNECTED_ACCOUNTS].update_one({'user_id': str(user_id), 'provider': 'jira', 'account_id': cloud_id}, {'$set': new_account_doc}, upsert=True)
    except Exception as e:
        logger.error(f'Error guardando Jira en vault: {e}')
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=database_error')
    logger.info(f'Jira conectado exitosamente en Bóveda para {email_safe} (Site: {site_name})')
    return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?jira_status=connected')

@router.get('/status')
def status():
    return JSONResponse({'connected': True})

@router.delete('')
def disconnect():
    return JSONResponse({'success': True})


# ── Service Layer ──────────────────────────────────────────────────────────────
"""
JIRA Service - Lógica de negocio para Atlassian JIRA API v3

Migrado a lectura desde oauth_vault con fallback a usuarios legacy.
Tokens refrescados se persisten encriptados exclusivamente en oauth_vault.
Refactorización Enterprise: Single Source of Truth (Config) y Prevención de Corrupción MongoDB.
"""
import logging
import requests
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Tuple
from bson import ObjectId
from bson.errors import InvalidId
from config import Config
from app.core.mongo import get_sync_database
from app.database import _normalize_integrations
from app.core.constants import Collections
from app.core.db_utils import find_user_by_email, canonicalize_email
try:
    from app.core.security import encrypt_data
except ImportError:
    logging.getLogger(__name__).warning('[jira_service] Módulo de encriptación no disponible. Usando texto plano (MODO DEV).')

    def encrypt_data(data: str) -> str:
        return data
logger = logging.getLogger('services.jira')
_JIRA_KEY_ALIASES = ('Jira', 'jira', 'Atlassian Jira', 'atlassian_jira')

def _find_jira_integration(integrations: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Busca las credenciales tolerando variaciones de capitalización.
    Retorna una tupla: (credenciales_encontradas, clave_original_exacta)
    """
    norm = lambda k: k.lower().replace(' ', '_').replace('-', '_')
    for key, value in integrations.items():
        if norm(key) in [norm(alias) for alias in _JIRA_KEY_ALIASES]:
            if isinstance(value, dict):
                return (value, key)
    return (None, None)

class JiraServiceError(Exception):
    """Excepción base para errores del servicio JIRA"""
    pass

class JiraAuthError(JiraServiceError):
    """Error de autenticación (token inválido o expirado)"""
    pass

class JiraAPIError(JiraServiceError):
    """Error en la respuesta de JIRA API"""
    pass

class JiraService:
    """
    Servicio para interactuar con Atlassian JIRA API v3.

    Lee credenciales desde oauth_vault (con fallback a usuarios legacy).
    Persiste tokens refrescados encriptados exclusivamente en oauth_vault.
    """
    BASE_URL = 'https://api.atlassian.com'
    TOKEN_REFRESH_MARGIN = timedelta(minutes=5)
    REQUEST_TIMEOUT = 30

    def __init__(self, user_id: str, db=None):
        """Inicializa el servicio JIRA para un usuario específico."""
        self.user_id: str = str(user_id)
        self.db = db if db is not None else get_sync_database()
        self.email: str = ''
        self.access_token: str = ''
        self.refresh_token: str = ''
        self.cloud_id: str = ''
        self.expires_at: datetime = datetime.utcnow()
        self.exact_integration_key: str = 'Jira'
        self._load_credentials()
        logger.info(f'[jira_service] JiraService inicializado para user_id={self.user_id} correo={self.email}')

    def _load_credentials(self) -> None:
        """Carga credenciales JIRA con el patrón Vault-First / Legacy-Fallback."""
        try:
            user_oid = ObjectId(self.user_id)
        except (InvalidId, TypeError) as exc:
            raise JiraAuthError(f'user_id inválido: {self.user_id}') from exc
        user = self.db[Collections.USERS].find_one({'_id': user_oid})
        if not user:
            raise JiraAuthError(f'Usuario no encontrado: {self.user_id}')
        email_raw: str = user.get('email', '')
        if not email_raw:
            raise JiraAuthError(f'El usuario {self.user_id} no tiene email registrado. No es posible localizar sus integraciones en la bóveda.')
        self.email = canonicalize_email(email_raw)
        vault_doc = self.db[Collections.OAUTH_VAULT].find_one({'email': self.email})
        jira_config: Optional[Dict[str, Any]] = None
        exact_key: Optional[str] = None
        if vault_doc and vault_doc.get('integrations'):
            integrations: Dict[str, Any] = _normalize_integrations(vault_doc['integrations'], source='vault', correo=self.email)
            jira_config, exact_key = _find_jira_integration(integrations)
            if jira_config:
                logger.debug(f"[jira_service] Credenciales leídas desde oauth_vault para '{self.email}'.")
        if not jira_config:
            raw_integrations: Dict[str, Any] = user.get('integrations', {})
            integrations = _normalize_integrations(raw_integrations, source='legacy', correo=self.email)
            jira_config, exact_key = _find_jira_integration(integrations)
            if jira_config:
                logger.warning(f"[jira_service] Fallback a colección legacy 'usuarios' para '{self.email}'.")
        if not jira_config or not exact_key:
            raise JiraAuthError(f"JIRA no está conectado para '{self.email}'.")
        self.exact_integration_key = exact_key
        required = ['token', 'refresh_token', 'cloud_id']
        missing = [f for f in required if not jira_config.get(f)]
        if missing:
            raise JiraAuthError(f"Configuración de Jira incompleta para '{self.email}'. Faltan: {missing}")
        self.access_token = jira_config['token']
        self.refresh_token = jira_config['refresh_token']
        self.cloud_id = jira_config['cloud_id']
        self.expires_at = self._resolve_expires_at(jira_config)

    @staticmethod
    def _resolve_expires_at(jira_config: Dict[str, Any]) -> datetime:
        """Calcula expires_at adaptándose al esquema Vault o Legacy."""
        raw_expires = jira_config.get('expires_at')
        if raw_expires:
            if isinstance(raw_expires, datetime):
                return raw_expires.replace(tzinfo=None)
            if isinstance(raw_expires, str):
                try:
                    from dateutil import parser as dateutil_parser
                    return dateutil_parser.parse(raw_expires).replace(tzinfo=None)
                except (ValueError, ImportError):
                    pass
        timestamp_str: Optional[str] = jira_config.get('timestamp')
        expires_in = jira_config.get('expires_in')
        if timestamp_str and expires_in is not None:
            try:
                ts = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                return ts + timedelta(seconds=int(expires_in))
            except (ValueError, TypeError):
                pass
        return datetime.utcnow() + timedelta(hours=1)

    def _ensure_valid_token(self) -> None:
        """Verifica que el token sea válido y lo refresca proactivamente."""
        if isinstance(self.expires_at, str):
            from dateutil import parser as dateutil_parser
            self.expires_at = dateutil_parser.parse(self.expires_at).replace(tzinfo=None)
        expires_naive = self.expires_at.replace(tzinfo=None)
        now = datetime.utcnow()
        if expires_naive <= now + self.TOKEN_REFRESH_MARGIN:
            logger.info(f"[jira_service] Token próximo a expirar para '{self.email}', refrescando...")
            self._refresh_token()
        else:
            remaining = (expires_naive - now).total_seconds() / 60
            logger.debug(f'[jira_service] Token válido. Expira en {remaining:.1f} min.')

    def _refresh_token(self) -> None:
        """
        Refresca el access token y lo persiste ENCRIPTADO en oauth_vault.
        Aplica UPSERT para migrar automáticamente a usuarios legacy.
        """
        client_id = Config.JIRA_CLIENT_ID
        client_secret = Config.JIRA_CLIENT_SECRET
        if not client_id or not client_secret:
            raise JiraAuthError('Config.JIRA_CLIENT_ID o Config.JIRA_CLIENT_SECRET no configurados.')
        try:
            response = requests.post(f'{self.BASE_URL}/oauth/token', json={'grant_type': 'refresh_token', 'client_id': client_id, 'client_secret': client_secret, 'refresh_token': self.refresh_token}, headers={'Content-Type': 'application/json'}, timeout=self.REQUEST_TIMEOUT)
            response.raise_for_status()
            data: Dict[str, Any] = response.json()
        except requests.exceptions.RequestException as exc:
            logger.error(f"[jira_service] Error de red al refrescar token para '{self.email}': {exc}")
            raise JiraAuthError(f'Falló el refresh de token Jira: {exc}') from exc
        new_access_token: str = data['access_token']
        new_refresh_token: str = data.get('refresh_token', self.refresh_token)
        new_expires_in: int = int(data.get('expires_in', 3600))
        now_utc = datetime.now(timezone.utc)
        timestamp_str = now_utc.strftime('%Y-%m-%d %H:%M:%S')
        encrypted_token = encrypt_data(new_access_token)
        encrypted_refresh = encrypt_data(new_refresh_token)
        try:
            self.db[Collections.OAUTH_VAULT].update_one({'email': self.email}, {'$set': {f'integrations.{self.exact_integration_key}.token': encrypted_token, f'integrations.{self.exact_integration_key}.refresh_token': encrypted_refresh, f'integrations.{self.exact_integration_key}.expires_in': new_expires_in, f'integrations.{self.exact_integration_key}.cloud_id': self.cloud_id, f'integrations.{self.exact_integration_key}.timestamp': timestamp_str, 'updated_at': now_utc}, '$setOnInsert': {'user_id': self.user_id, 'created_at': now_utc, 'status': 'active'}}, upsert=True)
            logger.info(f"[jira_service] Token Jira refrescado y migrado a oauth_vault para '{self.email}'.")
        except Exception:
            logger.exception(f"[jira_service] Error al escribir en oauth_vault para '{self.email}'.")
        self.access_token = new_access_token
        self.refresh_token = new_refresh_token
        self.expires_at = datetime.utcnow() + timedelta(seconds=new_expires_in)

    def _make_request(self, method: str, endpoint: str, json_data: Optional[Dict]=None, params: Optional[Dict]=None) -> Dict:
        """Realiza request HTTP a JIRA API con auto-refresh proactivo."""
        self._ensure_valid_token()
        url = f'{self.BASE_URL}/ex/jira/{self.cloud_id}{endpoint}'
        headers = {'Authorization': f'Bearer {self.access_token}', 'Accept': 'application/json', 'Content-Type': 'application/json'}
        try:
            response = requests.request(method=method, url=url, headers=headers, json=json_data, params=params, timeout=self.REQUEST_TIMEOUT)
            if response.status_code == 401:
                logger.warning(f"[jira_service] 401 recibido para '{self.email}'. Forzando refresh...")
                self._refresh_token()
                headers['Authorization'] = f'Bearer {self.access_token}'
                response = requests.request(method=method, url=url, headers=headers, json=json_data, params=params, timeout=self.REQUEST_TIMEOUT)
            response.raise_for_status()
            return response.json() if response.content else {}
        except requests.exceptions.HTTPError:
            error_msg = f'JIRA API Error [{response.status_code}]: {response.text}'
            logger.error(f'[jira_service] {error_msg}')
            raise JiraAPIError(error_msg)
        except requests.exceptions.RequestException as exc:
            error_msg = f'Request Error: {exc}'
            logger.error(f'[jira_service] {error_msg}')
            raise JiraAPIError(error_msg)

    def create_ticket(self, project_key: str, summary: str, description: str, issue_type: str='Task', priority: Optional[str]=None) -> Dict[str, Any]:
        """Crea un nuevo ticket/issue en JIRA."""
        payload: Dict[str, Any] = {'fields': {'project': {'key': project_key}, 'summary': summary, 'description': {'type': 'doc', 'version': 1, 'content': [{'type': 'paragraph', 'content': [{'type': 'text', 'text': description}]}]}, 'issuetype': {'name': issue_type}}}
        if priority:
            payload['fields']['priority'] = {'name': priority}
        response = self._make_request('POST', '/rest/api/3/issue', json_data=payload)
        issue_key = response.get('key')
        issue_url = response.get('self', '').split('/rest')[0] + f'/browse/{issue_key}'
        return {'id': response.get('id'), 'key': issue_key, 'url': issue_url}

    def get_projects(self) -> List[Dict[str, Any]]:
        """Obtiene todos los proyectos accesibles."""
        projects = self._make_request('GET', '/rest/api/3/project')
        return [{'id': p['id'], 'key': p['key'], 'name': p['name']} for p in projects]

    def get_issue(self, issue_key: str) -> Dict[str, Any]:
        """Obtiene información de un issue específico."""
        response = self._make_request('GET', f'/rest/api/3/issue/{issue_key}')
        fields = response.get('fields', {})
        return {'id': response.get('id'), 'key': response.get('key'), 'summary': fields.get('summary'), 'status': fields.get('status', {}).get('name'), 'assignee': fields.get('assignee', {}).get('displayName'), 'priority': fields.get('priority', {}).get('name'), 'created': fields.get('created')}

    def search_issues(self, jql: str, max_results: int=50) -> List[Dict[str, Any]]:
        """Busca issues usando JQL."""
        response = self._make_request('GET', '/rest/api/3/search', params={'jql': jql, 'maxResults': max_results, 'fields': 'summary,status,assignee,priority,created,issuetype'})
        return response.get('issues', [])

    def health_check(self) -> Dict[str, Any]:
        """Verifica que la conexión es válida."""
        projects = self.get_projects()
        expires_in_min = (self.expires_at.replace(tzinfo=None) - datetime.utcnow()).total_seconds() / 60
        return {'status': 'healthy', 'cloud_id': self.cloud_id, 'projects_count': len(projects), 'token_expires_in_minutes': round(expires_in_min, 2)}

