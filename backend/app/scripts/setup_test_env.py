import os
import time
import sys
from dotenv import load_dotenv
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(BASE_DIR)
from app.core.mongo import get_sync_database
load_dotenv()
db = get_sync_database()
print(f' REPARANDO DATOS EN: {db.name}')
try:
    db.create_collection('oauth_vault')
    print(' Colección oauth_vault verificada.')
except Exception:
    pass
db.users.delete_many({'email': 'test_enterprise@shifu.com'})
result = db.users.insert_one({'user_id': 'user_test_001', 'email': 'test_enterprise@shifu.com', 'nombre': 'Usuario de Prueba', 'integrations': {'gmail': {'access_token': 'token_falso_gmail_123', 'refresh_token': 'refresh_falso_gmail', 'scope': 'https://mail.google.com/'}, 'slack': {'access_token': 'token-slack-de-prueba', 'team_id': 'T_FALSO'}}})
print(f' Insertado usuario con ID: {result.inserted_id}')
count = db.users.count_documents({'integrations': {'$exists': True}})
print(f' VERIFICACIÓN: Ahora hay {count} usuario(s) con integraciones listos para migrar.')
