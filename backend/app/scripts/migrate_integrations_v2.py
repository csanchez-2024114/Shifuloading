import sys
import os
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Any, Tuple
from dotenv import load_dotenv
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger('migration')
try:
    from app.core.security import encrypt_data
    from app.core.mongo import get_sync_database
    from app.core.constants import Collections
except ImportError:
    logger.critical(' Error importando app.core.security')
    sys.exit(1)
db = get_sync_database()

def map_provider_name(name: str) -> str:
    if not name:
        return 'unknown'
    name = name.lower().strip()
    mapping = {'google': 'google', 'gmail': 'google', 'drive': 'google_drive', 'google_drive': 'google_drive', 'slack': 'slack', 'hubspot': 'hubspot', 'salesforce': 'salesforce', 'notion': 'notion', 'twitter': 'twitter', 'dropbox': 'dropbox', 'asana': 'asana', 'outlook': 'outlook', 'onedrive': 'onedrive', 'trello': 'trello', 'jira': 'jira', 'monday': 'monday', 'clickup': 'clickup', 'kick': 'kick', 'discord': 'discord', 'facebook': 'facebook', 'instagram': 'instagram', 'whatsapp': 'whatsapp', 'linkedin': 'linkedin', 'tiktok': 'tiktok', 'teams': 'microsoft_teams'}
    return mapping.get(name, name)

def run_migration():
    logger.info(f" INICIANDO MIGRACIÓN EN: '{db.name}'")
    cols = db.list_collection_names()
    if 'usuarios' in cols:
        target = 'usuarios'
    elif Collections.USERS in cols:
        target = Collections.USERS
    elif 'User' in cols:
        target = 'User'
    else:
        target = Collections.USERS
    logger.info(f" OBJETIVO SELECCIONADO: Colección '{target}'")
    users_col = db[target]
    vault_col = db['oauth_vault']
    cursor = users_col.find({'integrations': {'$exists': True, '$ne': {}}})
    stats = {'ok': 0, 'error': 0, 'skipped': 0, 'processed': 0}
    try:
        for user in cursor:
            stats['processed'] += 1
            user_id = str(user['_id'])
            email = user.get('correo', user.get('email', 'unknown'))
            legacy = user.get('integrations', {})
            items = []
            if isinstance(legacy, dict):
                items = list(legacy.items())
            elif isinstance(legacy, list):
                for x in legacy:
                    if isinstance(x, dict):
                        p = x.get('provider') or x.get('name') or 'unknown'
                        items.append((p, x))
            if not items:
                continue
            for prov_key, data in items:
                if not isinstance(data, dict):
                    continue
                clean_prov = map_provider_name(prov_key)
                token = data.get('access_token') or data.get('token')
                if not token:
                    stats['skipped'] += 1
                    continue
                try:
                    payload = {'access_token': token, 'refresh_token': data.get('refresh_token'), 'team_id': data.get('team_id'), 'cloud_id': data.get('cloud_id'), 'workspace_id': data.get('workspace_id'), 'instance_url': data.get('instance_url'), 'bot_user_id': data.get('bot_user_id'), 'expires_in': data.get('expires_in')}
                    payload = {k: v for k, v in payload.items() if v}
                    encrypted = encrypt_data(json.dumps(payload))
                    sc = data.get('scope') or data.get('scopes') or []
                    if isinstance(sc, str):
                        sc = sc.replace(',', ' ').split()
                    u_name = user.get('nombre') or user.get('name') or ''
                    u_avatar = user.get('img') or user.get('avatar') or ''
                    vault_col.update_one({'user_id': user_id, 'provider': clean_prov}, {'$set': {'user_id': user_id, 'provider': clean_prov, 'status': 'active', 'created_at': datetime.now(timezone.utc), 'updated_at': datetime.now(timezone.utc), 'security': {'encrypted_data': encrypted, 'iv': 'bundled', 'version': 'v2_migration'}, 'metadata': {'email': email, 'name': u_name, 'avatar': u_avatar, 'scopes': sc if isinstance(sc, list) else []}}}, upsert=True)
                    stats['ok'] += 1
                except Exception as e:
                    logger.error(f' Error user {email}: {e}')
                    stats['error'] += 1
    finally:
        cursor.close()
    logger.info('--------------------------------')
    logger.info(f" FINALIZADO. Procesados: {stats['processed']} | OK: {stats['ok']} | Skip: {stats['skipped']}")
if __name__ == '__main__':
    run_migration()
