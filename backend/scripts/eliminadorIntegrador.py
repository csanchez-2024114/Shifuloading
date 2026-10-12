from app.core.mongo import get_sync_database
import os
from dotenv import load_dotenv

load_dotenv()
db = client['Prueba']

# Eliminar solo la integración de Drive
result = db.users.update_one(
    {'correo': 'ecalcinap@unsa.edu.pe'},
    {'$unset': {'integrations.Gmail': ''}}
)

print(f'✅ Drive desconectado. Modificados: {result.modified_count} documentos')

# Verificar que se eliminó
user = db.users.find_one({'correo': 'ecalcinap@unsa.edu.pe'})
print('Integraciones actuales:', list(user.get('integrations', {}).keys()))