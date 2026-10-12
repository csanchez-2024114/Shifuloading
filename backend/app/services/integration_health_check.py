"""
🏥 HEALTH CHECK SERVICE para Integraciones
Verifica el estado y validez de cada integración conectada
"""
import logging
import json
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone, timedelta
import aiohttp
import asyncio
from app.core.security import decrypt_data
from app.core.constants import Collections, ConnectedAccountStatus
logger = logging.getLogger('integration.health')

class IntegrationHealthStatus:
    """Estados posibles de una integración"""
    ACTIVE = 'active'
    EXPIRED = 'expired'
    INVALID = 'invalid'
    NEEDS_REFRESH = 'needs_refresh'
    UNKNOWN = 'unknown'
    DISCONNECTED = 'disconnected'


# Maps live health check result → persistent status in user_connected_accounts.
# UNKNOWN and DISCONNECTED are NOT mapped — transient states must not downgrade the DB record.
# EXPIRED is handled per-record (recoverable=True → needs_refresh, False → expired).
_HEALTH_TO_DB_STATUS = {
    IntegrationHealthStatus.ACTIVE:        ConnectedAccountStatus.ACTIVE,
    IntegrationHealthStatus.NEEDS_REFRESH: ConnectedAccountStatus.NEEDS_REFRESH,
    IntegrationHealthStatus.INVALID:       ConnectedAccountStatus.REVOKED,
}


class IntegrationHealthChecker:
    """
    Verifica el estado de cada integración con su proveedor externo.
    
    ESTRATEGIA:
    - Gmail/Google: Valida con Google API
    - Slack: Valida con Slack API
    - HubSpot: Valida con HubSpot API
    - Otros: Verifica tiempo de expiración
    """
    PROVIDER_TIMEOUTS = {'gmail': 10, 'drive': 10, 'google_docs': 10, 'google_sheets': 10, 'google_slides': 10, 'slack': 8, 'hubspot': 8, 'notion': 8, 'mailchimp': 8, 'jira': 10, 'salesforce': 10, 'teams': 10, 'discord': 8, 'asana': 8, 'monday': 8, 'clickup': 8, 'dropbox': 8, 'onedrive': 10, 'outlook': 10, 'linkedin': 8, 'facebook': 8, 'whatsapp': 10}
    SHORT_EXPIRY_PROVIDERS = {'gmail', 'drive', 'google_docs', 'google_sheets', 'google_slides', 'teams', 'outlook', 'onedrive', 'salesforce', 'jira'}

    @staticmethod
    async def check_gmail_health(credentials: Dict[str, Any], timeout: int=10) -> Dict[str, Any]:
        """
        ✅ Verifica estado de Gmail usando Google TokenInfo Endpoint
        
        GET https://www.googleapis.com/oauth2/v1/tokeninfo?access_token=TOKEN
        """
        try:
            access_token = credentials.get('access_token')
            if not access_token:
                return {'status': IntegrationHealthStatus.INVALID, 'reason': 'access_token ausente', 'checked_at': datetime.now(timezone.utc).isoformat(), 'is_recoverable': False}
            async with aiohttp.ClientSession() as session:
                url = 'https://www.googleapis.com/oauth2/v1/tokeninfo'
                async with session.get(url, params={'access_token': access_token}, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
                    if response.status == 200:
                        data = await response.json()
                        expires_in = data.get('expires_in', 0)
                        if expires_in > 300:
                            return {'status': IntegrationHealthStatus.ACTIVE, 'expires_in': expires_in, 'scope': data.get('scope', ''), 'checked_at': datetime.now(timezone.utc).isoformat(), 'is_recoverable': False}
                        else:
                            return {'status': IntegrationHealthStatus.NEEDS_REFRESH, 'expires_in': expires_in, 'checked_at': datetime.now(timezone.utc).isoformat(), 'is_recoverable': bool(credentials.get('refresh_token'))}
                    elif response.status == 400:
                        return {'status': IntegrationHealthStatus.EXPIRED, 'reason': 'Token expirado o inválido', 'checked_at': datetime.now(timezone.utc).isoformat(), 'is_recoverable': bool(credentials.get('refresh_token'))}
                    else:
                        return {'status': IntegrationHealthStatus.UNKNOWN, 'reason': f'Google API respondió con {response.status}', 'checked_at': datetime.now(timezone.utc).isoformat(), 'is_recoverable': True}
        except asyncio.TimeoutError:
            return {'status': IntegrationHealthStatus.UNKNOWN, 'reason': 'Timeout al conectar con Google', 'checked_at': datetime.now(timezone.utc).isoformat(), 'is_recoverable': True}
        except Exception as e:
            logger.error(f'Error checking Gmail health: {str(e)}')
            return {'status': IntegrationHealthStatus.UNKNOWN, 'reason': f'Error: {str(e)}', 'checked_at': datetime.now(timezone.utc).isoformat(), 'is_recoverable': True}

    @staticmethod
    async def check_slack_health(credentials: Dict[str, Any], timeout: int=8) -> Dict[str, Any]:
        """
        ✅ Verifica estado de Slack usando auth.test
        
        GET https://slack.com/api/auth.test
        header: Authorization: Bearer TOKEN
        """
        try:
            access_token = credentials.get('access_token')
            if not access_token:
                return {'status': IntegrationHealthStatus.INVALID, 'reason': 'access_token ausente', 'checked_at': datetime.now(timezone.utc).isoformat(), 'is_recoverable': False}
            async with aiohttp.ClientSession() as session:
                headers = {'Authorization': f'Bearer {access_token}'}
                async with session.get('https://slack.com/api/auth.test', headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get('ok'):
                            return {'status': IntegrationHealthStatus.ACTIVE, 'org_id': data.get('org_id'), 'user_id': data.get('user_id'), 'team_id': data.get('team_id'), 'checked_at': datetime.now(timezone.utc).isoformat(), 'is_recoverable': False}
                        else:
                            return {'status': IntegrationHealthStatus.EXPIRED, 'reason': data.get('error', 'Token inválido'), 'checked_at': datetime.now(timezone.utc).isoformat(), 'is_recoverable': False}
                    else:
                        return {'status': IntegrationHealthStatus.UNKNOWN, 'reason': f'Slack API respondió con {response.status}', 'checked_at': datetime.now(timezone.utc).isoformat(), 'is_recoverable': True}
        except asyncio.TimeoutError:
            return {'status': IntegrationHealthStatus.UNKNOWN, 'reason': 'Timeout al conectar con Slack', 'checked_at': datetime.now(timezone.utc).isoformat(), 'is_recoverable': True}
        except Exception as e:
            logger.error(f'Error checking Slack health: {str(e)}')
            return {'status': IntegrationHealthStatus.UNKNOWN, 'reason': f'Error: {str(e)}', 'checked_at': datetime.now(timezone.utc).isoformat(), 'is_recoverable': True}

    @staticmethod
    async def check_hubspot_health(credentials: Dict[str, Any], timeout: int=8) -> Dict[str, Any]:
        """
        ✅ Verifica estado de HubSpot usando CRM API
        
        GET https://api.hubapi.com/crm/v3/objects/contacts
        header: Authorization: Bearer TOKEN
        """
        try:
            access_token = credentials.get('access_token')
            if not access_token:
                return {'status': IntegrationHealthStatus.INVALID, 'reason': 'access_token ausente', 'checked_at': datetime.now(timezone.utc).isoformat(), 'is_recoverable': False}
            async with aiohttp.ClientSession() as session:
                headers = {'Authorization': f'Bearer {access_token}'}
                async with session.get('https://api.hubapi.com/crm/v3/objects/contacts?limit=1', headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
                    if response.status == 200:
                        return {'status': IntegrationHealthStatus.ACTIVE, 'checked_at': datetime.now(timezone.utc).isoformat(), 'is_recoverable': False}
                    elif response.status == 401:
                        return {'status': IntegrationHealthStatus.EXPIRED, 'reason': 'Token no autorizado', 'checked_at': datetime.now(timezone.utc).isoformat(), 'is_recoverable': False}
                    else:
                        return {'status': IntegrationHealthStatus.UNKNOWN, 'reason': f'HubSpot API respondió con {response.status}', 'checked_at': datetime.now(timezone.utc).isoformat(), 'is_recoverable': True}
        except asyncio.TimeoutError:
            return {'status': IntegrationHealthStatus.UNKNOWN, 'reason': 'Timeout al conectar con HubSpot', 'checked_at': datetime.now(timezone.utc).isoformat(), 'is_recoverable': True}
        except Exception as e:
            logger.error(f'Error checking HubSpot health: {str(e)}')
            return {'status': IntegrationHealthStatus.UNKNOWN, 'reason': f'Error: {str(e)}', 'checked_at': datetime.now(timezone.utc).isoformat(), 'is_recoverable': True}

    @staticmethod
    async def check_generic_expiry(credentials: Dict[str, Any]) -> Dict[str, Any]:
        """
        ⏰ Para proveedores donde no hay endpoint de validación,
        verificamos la fecha de expiración local
        """
        expires_in = credentials.get('expires_in')
        timestamp = credentials.get('timestamp')
        if not timestamp:
            return {'status': IntegrationHealthStatus.UNKNOWN, 'reason': 'Sin timestamp de creación', 'is_recoverable': bool(credentials.get('refresh_token'))}
        try:
            created_at = datetime.fromisoformat(timestamp)
            now = datetime.now(timezone.utc)
            if not created_at.tzinfo:
                created_at = created_at.replace(tzinfo=timezone.utc)
            elapsed = (now - created_at).total_seconds()
            if expires_in:
                remaining = expires_in - elapsed
                if remaining > 300:
                    return {'status': IntegrationHealthStatus.ACTIVE, 'expires_in': int(remaining), 'checked_at': datetime.now(timezone.utc).isoformat()}
                elif remaining > 0:
                    return {'status': IntegrationHealthStatus.NEEDS_REFRESH, 'expires_in': int(remaining), 'checked_at': datetime.now(timezone.utc).isoformat(), 'is_recoverable': bool(credentials.get('refresh_token'))}
                else:
                    return {'status': IntegrationHealthStatus.EXPIRED, 'reason': 'Token expirado (tiempo local)', 'checked_at': datetime.now(timezone.utc).isoformat(), 'is_recoverable': bool(credentials.get('refresh_token'))}
            else:
                return {'status': IntegrationHealthStatus.ACTIVE, 'message': 'Sin expiración conocida', 'checked_at': datetime.now(timezone.utc).isoformat()}
        except Exception as e:
            logger.error(f'Error checking generic expiry: {str(e)}')
            return {'status': IntegrationHealthStatus.UNKNOWN, 'reason': f'Error al verificar: {str(e)}', 'is_recoverable': True}

    @staticmethod
    async def check_integration_health(provider: str, credentials: Dict[str, Any]) -> Dict[str, Any]:
        """
        🏥 Punto de entrada: Verifica el estado de una integración
        
        Delega a verificadores específicos según el proveedor
        """
        provider_lower = provider.lower()
        if provider_lower in {'gmail', 'drive', 'google_docs', 'google_sheets', 'google_slides'}:
            timeout = IntegrationHealthChecker.PROVIDER_TIMEOUTS.get(provider_lower, 10)
            return await IntegrationHealthChecker.check_gmail_health(credentials, timeout)
        elif provider_lower == 'slack':
            timeout = IntegrationHealthChecker.PROVIDER_TIMEOUTS.get('slack', 8)
            return await IntegrationHealthChecker.check_slack_health(credentials, timeout)
        elif provider_lower == 'hubspot':
            timeout = IntegrationHealthChecker.PROVIDER_TIMEOUTS.get('hubspot', 8)
            return await IntegrationHealthChecker.check_hubspot_health(credentials, timeout)
        else:
            return await IntegrationHealthChecker.check_generic_expiry(credentials)

async def get_all_integrations_health(db, user_id: str) -> Dict[str, Any]:
    """
    📊 Obtiene el estado de TODAS las integraciones del usuario
    
    Returns:
    {
        "user_id": "...",
        "total_integrations": 5,
        "active_count": 3,
        "expired_count": 1,
        "needs_refresh_count": 1,
        "integrations": {
            "gmail": {...},
            "slack": {...},
            ...
        },
        "summary": {
            "all_healthy": false,
            "requires_action": true,
            "checked_at": "..."
        }
    }
    """
    try:
        cursor = db.oauth_vault.find({'user_id': user_id})
        integrations_list = await cursor.to_list(length=500)
        if not integrations_list:
            return {'user_id': user_id, 'total_integrations': 0, 'integrations': {}, 'summary': {'all_healthy': True, 'requires_action': False, 'checked_at': datetime.now(timezone.utc).isoformat(), 'message': 'Sin integraciones'}}
        integrations_health = {}
        status_counts = {'active': 0, 'expired': 0, 'invalid': 0, 'needs_refresh': 0, 'unknown': 0, 'disconnected': 0}
        tasks = []
        for doc in integrations_list:
            provider = doc.get('provider')
            if not provider:
                continue
            try:
                encrypted_data = doc.get('security', {}).get('encrypted_data')
                if not encrypted_data:
                    integrations_health[provider] = {'status': IntegrationHealthStatus.UNKNOWN, 'reason': 'Credenciales no encontradas', 'is_active': doc.get('status') == 'active'}
                    continue
                credentials_json = decrypt_data(encrypted_data)
                credentials = json.loads(credentials_json)
                health = await IntegrationHealthChecker.check_integration_health(provider, credentials)
                integrations_health[provider] = {'id': str(doc.get('_id')), 'provider': provider, 'is_active': doc.get('status') == 'active', 'created_at': doc.get('created_at'), 'last_checked': doc.get('last_checked'), **health}
                status = health.get('status', IntegrationHealthStatus.UNKNOWN)
                if status in status_counts:
                    status_counts[status] += 1
            except Exception as e:
                logger.error(f'Error checking health for {provider}: {str(e)}')
                integrations_health[provider] = {'status': IntegrationHealthStatus.UNKNOWN, 'reason': f'Error en verificación: {str(e)}', 'is_active': doc.get('status') == 'active'}
                status_counts['unknown'] += 1
        now = datetime.now(timezone.utc)
        for integration in integrations_list:
            provider = integration.get('provider')
            if provider not in integrations_health:
                continue
            await db.oauth_vault.update_one({'_id': integration.get('_id')}, {'$set': {'last_checked': now}})
            # Persist health status to user_connected_accounts so auth_validator can use it
            h = integrations_health[provider]
            h_status = h.get('status', IntegrationHealthStatus.UNKNOWN)
            if h_status == IntegrationHealthStatus.EXPIRED:
                new_db_status = (
                    ConnectedAccountStatus.NEEDS_REFRESH if h.get('is_recoverable')
                    else ConnectedAccountStatus.EXPIRED
                )
            else:
                new_db_status = _HEALTH_TO_DB_STATUS.get(h_status)  # None for UNKNOWN/DISCONNECTED
            if new_db_status:
                await db[Collections.USER_CONNECTED_ACCOUNTS].update_many(
                    {'user_id': user_id, 'provider': provider},
                    {'$set': {'status': new_db_status, 'last_health_check': now}},
                )
        total = len(integrations_health)
        healthy = status_counts['active']
        requires_action = status_counts['expired'] + status_counts['needs_refresh']
        return {'user_id': user_id, 'total_integrations': total, 'status_counts': status_counts, 'integrations': integrations_health, 'summary': {'all_healthy': requires_action == 0 and total > 0, 'requires_action': requires_action > 0, 'healthy_count': healthy, 'problematic_count': requires_action, 'checked_at': now.isoformat(), 'message': _generate_summary_message(status_counts, total)}}
    except Exception as e:
        logger.error(f'Error getting health for user {user_id}: {str(e)}')
        return {'user_id': user_id, 'error': str(e), 'integrations': {}, 'summary': {'all_healthy': False, 'requires_action': True, 'checked_at': datetime.now(timezone.utc).isoformat()}}

def _generate_summary_message(status_counts: Dict[str, int], total: int) -> str:
    """Genera mensaje legible del resumen"""
    active = status_counts['active']
    expired = status_counts['expired']
    needs_refresh = status_counts['needs_refresh']
    if total == 0:
        return 'Sin integraciones'
    if expired == 0 and needs_refresh == 0:
        return f'✅ Todas las {total} integraciones están activas'
    messages = []
    if active > 0:
        messages.append(f"✅ {active} activa{('s' if active > 1 else '')}")
    if expired > 0:
        messages.append(f"❌ {expired} expirada{('s' if expired > 1 else '')}")
    if needs_refresh > 0:
        messages.append(f'🔄 {needs_refresh} necesita refresh')
    return ' | '.join(messages)
