from app.core.mongo import get_sync_database
import os
from dotenv import load_dotenv

load_dotenv()
db = get_sync_database()

def eliminar_integraciones(correo, integraciones_especificas=None):
    """
    Elimina integraciones de un usuario
    
    Args:
        correo (str): Correo del usuario
        integraciones_especificas (list): Lista de integraciones a eliminar.
                                         Si es None, elimina todas.
    """
    if integraciones_especificas:
        # Eliminar integraciones específicas
        unset_dict = {f'integrations.{integracion}': '' for integracion in integraciones_especificas}
        result = db.users.update_one(
            {'correo': correo},
            {'$unset': unset_dict}
        )
        print(f'✅ Integraciones específicas eliminadas. Modificados: {result.modified_count} documentos')
    else:
        # Eliminar TODAS las integraciones
        result = db.users.update_one(
            {'correo': correo},
            {'$unset': {'integrations': ''}}
        )
        print(f'✅ Todas las integraciones eliminadas. Modificados: {result.modified_count} documentos')
    
    # Verificar resultado
    user = db.users.find_one({'correo': correo})
    if user and 'integrations' in user:
        print('Integraciones restantes:', list(user.get('integrations', {}).keys()))
    else:
        print('✅ No quedan integraciones en el usuario')

# Ejemplos de uso:
# 1. Eliminar TODAS las integraciones
eliminar_integraciones('ecalcinap@unsa.edu.pe')

# 2. Eliminar integraciones específicas
# eliminar_integraciones('ecalcinap@unsa.edu.pe', ['Gmail', 'Drive', 'Dropbox'])

# 3. Eliminar solo una integración
# eliminar_integraciones('ecalcinap@unsa.edu.pe', ['Gmail'])