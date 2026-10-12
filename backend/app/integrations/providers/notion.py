import os
import jwt
import secrets
import logging
import requests
import base64
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from bson import ObjectId
from app.database import get_current_user, get_db, SECRET_KEY
from app.core.constants import Collections
try:
    from app.core.security import encrypt_data
except ImportError:
    logger = logging.getLogger(__name__)
    logger.warning('Módulo de encriptación no encontrado. Se usará texto plano (MODO DEV).')
    encrypt_data = lambda x: x
logger = logging.getLogger('auth.notion')
router = APIRouter()
NOTION_CLIENT_ID = os.getenv('NOTION_CLIENT_ID')
NOTION_CLIENT_SECRET = os.getenv('NOTION_CLIENT_SECRET')
NOTION_REDIRECT_URI = os.getenv('NOTION_REDIRECT_URI')
FRONTEND_REDIRECT_URL = os.getenv('FRONTEND_REDIRECT_URL', 'https://hypershifu.com/chat')

@router.get('/login')
async def login(user: dict=Depends(get_current_user)):
    user_id = str(user.get('_id', user.get('id', '')))
    correo = user.get('correo') or user.get('email', '')
    if not user_id or not correo:
        raise HTTPException(status_code=401, detail='Usuario inválido o sin correo')
    nonce = secrets.token_urlsafe(32)
    state = jwt.encode({'nonce': nonce, 'user_id': user_id, 'correo': correo}, SECRET_KEY, algorithm='HS256')
    auth_url = f'https://api.notion.com/v1/oauth/authorize?client_id={NOTION_CLIENT_ID}&response_type=code&owner=user&redirect_uri={NOTION_REDIRECT_URI}&state={state}'
    return {'url': auth_url}

@router.get('/callback')
async def callback(request: Request, db=Depends(get_db)):
    try:
        state_jwt = request.query_params.get('state')
        code = request.query_params.get('code')
        error = request.query_params.get('error')
        if error:
            logger.warning(f'Notion Auth Error: {error}')
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error={error}')
        user_id, correo = (None, None)
        if state_jwt:
            try:
                payload = jwt.decode(state_jwt, SECRET_KEY, algorithms=['HS256'])
                user_id = payload.get('user_id')
                correo = payload.get('correo')
            except Exception as e:
                logger.error(f'Error decodificando state JWT: {e}')
        if not user_id or not correo:
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=session_lost')
        email_safe = correo.strip().lower()
        auth_string = f'{NOTION_CLIENT_ID}:{NOTION_CLIENT_SECRET}'
        encoded_auth = base64.b64encode(auth_string.encode()).decode()
        headers = {'Authorization': f'Basic {encoded_auth}', 'Content-Type': 'application/json'}
        data = {'grant_type': 'authorization_code', 'code': code, 'redirect_uri': NOTION_REDIRECT_URI}
        token_res = requests.post('https://api.notion.com/v1/oauth/token', json=data, headers=headers).json()
        if 'error' in token_res or 'access_token' not in token_res:
            logger.error(f'Notion Token Error: {token_res}')
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=token_exchange_failed')
        access_token = token_res.get('access_token')
        workspace_id = token_res.get('workspace_id')
        encrypted_token = encrypt_data(access_token) if access_token else None
        now_utc = datetime.now(timezone.utc)
        new_account_doc = {'user_id': str(user_id), 'provider': 'notion', 'account_id': workspace_id, 'access_token': encrypted_token, 'refresh_token': 'n/a', 'expires_in': 315360000, 'status': 'active', 'timestamp': now_utc.strftime('%Y-%m-%d %H:%M:%S'), 'metadata': {'workspace_id': workspace_id, 'workspace_name': token_res.get('workspace_name', 'Unknown Workspace'), 'bot_id': token_res.get('bot_id'), 'owner': token_res.get('owner', {}), 'connected_at': now_utc.isoformat()}}
        try:
            await db[Collections.USER_CONNECTED_ACCOUNTS].update_one({'user_id': str(user_id), 'provider': 'notion', 'account_id': workspace_id}, {'$set': new_account_doc, '$setOnInsert': {'created_at': now_utc}}, upsert=True)
        except Exception as e:
            logger.error(f'Error DB guardando Notion V2 para {email_safe}: {e}', exc_info=True)
            return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=database_error')
        logger.info(f"✅ Workspace de Notion '{token_res.get('workspace_name')}' conectado en V2 para {email_safe}")
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?notion_status=connected')
    except Exception as e:
        logger.error(f'NOTION FATAL ERROR: {str(e)}', exc_info=True)
        return RedirectResponse(f'{FRONTEND_REDIRECT_URL}?error=internal_server_error')

@router.get('/status')
def status():
    """Stub de compatibilidad legacy. El status real viene de /health_check"""
    return {'connected': True}

@router.delete('')
def disconnect():
    """Stub de compatibilidad legacy. El borrado real se hace en /delete_integration"""
    return {'success': True}


# ── Service Layer ──────────────────────────────────────────────────────────────
import base64
import os
import logging
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlencode
from datetime import datetime, timezone
import requests
from config import Config
from app.core.constants import Collections
from app.core.db_utils import canonicalize_email, find_user_by_email
from app.core.security import encrypt_data
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
logger = logging.getLogger(__name__)
_INTEGRATION_KEY = 'notion'

def notion_auth() -> str:
    """Construye la URL de autorización de Notion para redirigir en frontend."""
    notion_auth_url = 'https://api.notion.com/v1/oauth/authorize'
    query_params = {'client_id': Config.NOTION_CLIENT_ID, 'redirect_uri': 'https://neuron-hyper.vercel.app/notion/callback', 'response_type': 'code'}
    return f'{notion_auth_url}?{urlencode(query_params)}'

def notion_callback(mongo, user_email: str, code: Optional[str]=None, error: Optional[str]=None) -> Tuple[Dict[str, Any], int]:
    """
    Intercambia code OAuth por token y guarda la integración en Mongo.
    Migrado para usar oauth_vault y buscar por email.
    Devuelve (payload, status_code) para que lo use cualquier framework.
    """
    db = mongo.db if hasattr(mongo, 'db') else mongo
    email_safe = canonicalize_email(user_email)
    user = find_user_by_email(db, email_safe)
    if not user:
        return ({'error': 'No se encontró el usuario en la base de datos'}, 404)
    if error:
        return ({'error': f'Notion devolvió un error: {error}'}, 400)
    if not code:
        return ({'error': "El parámetro 'code' es obligatorio"}, 400)
    token_url = 'https://api.notion.com/v1/oauth/token'
    token_data = {'grant_type': 'authorization_code', 'code': code, 'redirect_uri': 'https://neuron-hyper.vercel.app/notion/callback'}
    client_credentials = f'{Config.NOTION_CLIENT_ID}:{Config.NOTION_CLIENT_SECRET}'
    encoded_credentials = base64.b64encode(client_credentials.encode()).decode()
    headers = {'Content-Type': 'application/x-www-form-urlencoded', 'Authorization': f'Basic {encoded_credentials}', 'Notion-Version': '2022-06-28'}
    response = requests.post(token_url, data=urlencode(token_data), headers=headers)
    if response.status_code != 200:
        return ({'error': 'Error al obtener el token de Notion', 'details': response.json()}, response.status_code)
    access_token_data = response.json()
    access_token = access_token_data.get('access_token')
    if not access_token:
        return ({'error': 'No se pudo obtener el token de acceso'}, 400)
    now_utc = datetime.now(timezone.utc)
    encrypted_token_data = {'access_token': encrypt_data(access_token_data.get('access_token', '')), 'bot_id': access_token_data.get('bot_id'), 'workspace_name': access_token_data.get('workspace_name'), 'workspace_icon': access_token_data.get('workspace_icon'), 'owner': access_token_data.get('owner'), 'duplicated_template_id': access_token_data.get('duplicated_template_id')}
    db[Collections.OAUTH_VAULT].update_one({'$or': [{'correo': email_safe}, {'email': email_safe}]}, {'$set': {f'integrations.{_INTEGRATION_KEY}': encrypted_token_data, 'updated_at': now_utc, 'email': email_safe}, '$setOnInsert': {'created_at': now_utc, 'user_id': str(user['_id']), 'provider': 'server_side_oauth', 'status': 'active'}}, upsert=True)
    logger.info(f'Integración de Notion guardada en oauth_vault para {email_safe}')
    return ({'message': 'Integración de Notion guardada exitosamente', 'integration': {'workspace_name': access_token_data.get('workspace_name')}}, 200)

