import sys
import os
import json
import logging
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from pymongo.errors import PyMongoError
from dotenv import load_dotenv
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S', handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger('AuditSystem')
try:
    from app.core.security import decrypt_data
    from app.core.mongo import get_sync_database, get_sync_client
except ImportError as e:
    logger.critical(f' FATAL: No se pudo importar el módulo de seguridad: {e}')
    sys.exit(1)

@dataclass
class AuditStats:
    total_records: int = 0
    checked: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0

class MigrationAuditor:

    def __init__(self, uri: str):
        self.client = get_sync_client()
        self.db = get_sync_database()
        self.stats = AuditStats()

    def _validate_json_structure(self, data: Dict[str, Any]) -> bool:
        """Valida que el JSON tenga tokens."""
        required_keys = ['access_token', 'token', 'refresh_token', 'api_key']
        has_creds = any((k in data for k in required_keys))
        return has_creds

    def _mask_sensitive_data(self, data: Dict[str, Any]) -> Dict[str, str]:
        """Enmascara datos para logs seguros."""
        masked = {}
        for k, v in data.items():
            if v and isinstance(v, str) and (len(v) > 5):
                masked[k] = f'{v[:4]}...****'
            else:
                masked[k] = str(v)
        return masked

    def audit_record(self, record: Dict[str, Any]) -> bool:
        """Audita un solo registro según el esquema oauth_vault."""
        user_id = record.get('user_id', 'UNKNOWN')
        provider = record.get('provider', 'UNKNOWN')
        try:
            security_obj = record.get('security', {})
            if not security_obj:
                logger.error(f"   [User:{user_id}]  FALLO: No existe objeto 'security'.")
                return False
            encrypted_blob = security_obj.get('encrypted_data')
            if not encrypted_blob:
                logger.error(f"   [User:{user_id}]  FALLO: 'security.encrypted_data' está vacío.")
                return False
            try:
                decrypted_str = decrypt_data(encrypted_blob)
            except Exception as e:
                logger.error(f'   [User:{user_id}]  CRÍTICO: No se pudo desencriptar. {e}')
                return False
            try:
                payload = json.loads(decrypted_str)
            except json.JSONDecodeError:
                logger.error(f'   [User:{user_id}]  FALLO: JSON inválido.')
                return False
            if not self._validate_json_structure(payload):
                logger.warning(f'   [User:{user_id}]  WARNING: JSON válido pero sin credenciales obvias.')
            masked_payload = self._mask_sensitive_data(payload)
            logger.info(f'   [User:{user_id}] ✅ OK | {provider} | Data: {masked_payload}')
            return True
        except Exception as e:
            logger.error(f'   [User:{user_id}]  ERROR: {str(e)}')
            return False

    def run(self, sample_size: int=10):
        try:
            logger.info(f" INICIANDO AUDITORÍA EN BD: '{self.db.name.upper()}'")
            collection = self.db['oauth_vault']
            query = {'status': 'active'}
            total_migrated = collection.count_documents(query)
            self.stats.total_records = total_migrated
            if total_migrated == 0:
                logger.warning(" ALERTA: No se encontraron registros con status='active' en oauth_vault.")
                return False
            logger.info(f' Total Integraciones: {total_migrated}')
            logger.info(f' Auditando muestra de {min(sample_size, total_migrated)}...')
            pipeline = [{'$match': query}, {'$sample': {'size': sample_size}}]
            cursor = collection.aggregate(pipeline)
            logger.info('----------------------------------------------------------------')
            for record in cursor:
                self.stats.checked += 1
                if self.audit_record(record):
                    self.stats.passed += 1
                else:
                    self.stats.failed += 1
            logger.info('----------------------------------------------------------------')
            self._print_summary()
            return self.stats.failed == 0
        except Exception as e:
            logger.critical(f' ERROR SISTÉMICO: {e}')
            return False

    def _print_summary(self):
        print('\n --- RESUMEN DE AUDITORÍA ---')
        print(f'   Base de Datos:  {self.db.name}')
        print(f'   Colección:      oauth_vault')
        print(f'    Aprobados:    {self.stats.passed}')
        print(f'    Fallidos:     {self.stats.failed}')
        score = self.stats.passed / self.stats.checked * 100 if self.stats.checked > 0 else 0
        print(f'   Calidad:        {score:.2f}%')
        print('------------------------------\n')
if __name__ == '__main__':
    uri = os.getenv('MONGO_URI')
    if not uri:
        logger.critical(' ERROR: Falta MONGO_URI.')
        sys.exit(1)
    auditor = MigrationAuditor(uri)
    if auditor.run(sample_size=10):
        logger.info(' AUDITORÍA APROBADA.')
        sys.exit(0)
    else:
        logger.error(' AUDITORÍA FALLIDA.')
        sys.exit(1)
