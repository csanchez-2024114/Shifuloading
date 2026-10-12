import os
import json
import datetime
from bson.json_util import dumps
from dotenv import load_dotenv
import sys
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(BASE_DIR)
from app.core.mongo import get_sync_database
current_script_path = os.path.abspath(__file__)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(current_script_path)))
ENV_PATH = os.path.join(BASE_DIR, '.env')
print(f'🔍 Leyendo configuración desde: {ENV_PATH}')
load_dotenv(ENV_PATH)
MONGO_URI = os.getenv('MONGO_URI')
BACKUP_ROOT = 'C:\\hyper reality company - pasantias\\BackupBD'
TIMESTAMP = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
FINAL_BACKUP_PATH = os.path.join(BACKUP_ROOT, f'backup_shifu_{TIMESTAMP}')
if not MONGO_URI:
    print('\n❌ ERROR CRÍTICO: No se encontró MONGO_URI.')
    print('   Verifica que el archivo .env tenga la variable MONGO_URI definida.')
    exit(1)
try:
    safe_uri = MONGO_URI.split('@')[1] if '@' in MONGO_URI else '...'
    print(f'🔌 Conectando a Cluster: ...@{safe_uri}')
    db = get_sync_database()
    print(f"📦 BASE DE DATOS: '{db.name}'")
    if not os.path.exists(BACKUP_ROOT):
        print(f'⚠️ La carpeta {BACKUP_ROOT} no existía. Creándola...')
        os.makedirs(BACKUP_ROOT, exist_ok=True)
    os.makedirs(FINAL_BACKUP_PATH, exist_ok=True)
    print(f'📂 GUARDANDO RESPALDO EN: {FINAL_BACKUP_PATH}')
    print('-' * 50)
    collections = db.list_collection_names()
    print(f'📊 Colecciones encontradas: {len(collections)}')
    for col_name in collections:
        print(f"⬇️  Bajando '{col_name}'...", end=' ', flush=True)
        try:
            cursor = db[col_name].find()
            data = list(cursor)
            safe_col_name = col_name.replace('/', '_').replace('\\', '_')
            file_path = os.path.join(FINAL_BACKUP_PATH, f'{safe_col_name}.json')
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(dumps(data, indent=2, ensure_ascii=False))
            print(f'✅ ({len(data)} docs)')
        except Exception as col_error:
            print(f'❌ Error: {col_error}')
    print('=' * 50)
    print(f'🏆 BACKUP COMPLETADO EXITOSAMENTE')
    print(f'📍 Ve a la carpeta: {FINAL_BACKUP_PATH}')
    print('=' * 50)
except Exception as e:
    print(f'\n❌ ERROR FATAL: {e}')
