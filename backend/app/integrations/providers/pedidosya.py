"""
PedidosYa Authentication Module (Partner API)
Client Credentials Flow (Server-to-Server)
Migrated to Secure OAuth Vault
"""
import os
import logging
import requests
from datetime import datetime, timezone
from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse, RedirectResponse
from app.database import get_current_user, get_db
try:
    from app.core.security import encrypt_data
except ImportError:
    logger = logging.getLogger(__name__)
    logger.warning('Módulo de encriptación no encontrado. Se usará texto plano (MODO DEV).')
    encrypt_data = lambda x: x
logger = logging.getLogger('auth.pedidosya')
router = APIRouter()
PEDIDOSYA_AUTH_URL = os.getenv('PEDIDOSYA_AUTH_URL', 'https://auth-api.pedidosya.com/oauth/token')
CLIENT_ID = os.getenv('PEDIDOSYA_CLIENT_ID')
CLIENT_SECRET = os.getenv('PEDIDOSYA_CLIENT_SECRET')
FRONTEND_REDIRECT_URL = os.getenv('FRONTEND_REDIRECT_URL', 'https://hypershifu.com/chat')

@router.get('/login')
async def login(user: dict=Depends(get_current_user), db=Depends(get_db)):
    try:
        user_id = str(user.get('_id', user.get('id', '')))
        correo = user.get('correo') or user.get('email', '')
        if not user_id or not correo:
            logger.warning('Intento de login en PedidosYa sin usuario o correo válido.')
            return JSONResponse({'url': f'{FRONTEND_REDIRECT_URL}?error=invalid_user'})
        email_safe = correo.strip().lower()
        if not CLIENT_ID or not CLIENT_SECRET:
            logger.error('Faltan credenciales de PedidosYa en el entorno.')
            return JSONResponse({'url': f'{FRONTEND_REDIRECT_URL}?error=pedidosya_missing_credentials'})
        payload = {'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET, 'grant_type': 'client_credentials', 'scope': 'public_api'}
        headers = {'Content-Type': 'application/json'}
        try:
            resp = requests.post(PEDIDOSYA_AUTH_URL, json=payload, headers=headers, timeout=15)
            token_data = resp.json()
        except requests.RequestException as e:
            logger.error(f'Error de red conectando con PedidosYa: {e}')
            return JSONResponse({'url': f'{FRONTEND_REDIRECT_URL}?error=pedidosya_network_error'})
        if resp.status_code != 200 or 'access_token' not in token_data:
            logger.error(f'PedidosYa Auth Error: {token_data}')
            return JSONResponse({'url': f'{FRONTEND_REDIRECT_URL}?error=pedidosya_auth_failed'})
        access_token = token_data.get('access_token')
        encrypted_token = encrypt_data(access_token) if access_token else None
        integration_payload = {'token': encrypted_token, 'refresh_token': 'n/a', 'expires_in': token_data.get('expires_in'), 'token_type': token_data.get('token_type'), 'timestamp': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}
        now = datetime.now(timezone.utc)
        await db.oauth_vault.update_one({'correo': email_safe}, {'$set': {'integrations.PedidosYa': integration_payload, 'updated_at': now}, '$setOnInsert': {'created_at': now, 'user_id': user_id, 'provider': 'server_to_server', 'status': 'active'}}, upsert=True)
        logger.info(f'PedidosYa conectado exitosamente en bóveda para {email_safe}')
        return JSONResponse({'url': f'{FRONTEND_REDIRECT_URL}?pedidosya_status=connected'})
    except Exception as e:
        logger.error(f'ERROR FATAL PEDIDOSYA: {e}', exc_info=True)
        return JSONResponse({'url': f'{FRONTEND_REDIRECT_URL}?error=server_error'})

@router.get('/callback')
async def callback():
    """El flujo S2S no usa este endpoint, pero se mantiene para evitar 404s en flujos legacy."""
    return RedirectResponse(FRONTEND_REDIRECT_URL)

@router.get('/status')
async def status():
    return {'connected': True}

@router.delete('')
async def disconnect():
    return {'success': True}
