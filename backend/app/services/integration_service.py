import logging
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from app.models.accounts.integration import IntegrationDB, IntegrationPayload, ProviderType
from app.core.security import encrypt_data, decrypt_data
from bson import ObjectId
logger = logging.getLogger('security.audit')

class IntegrationService:
    """
    Service Layer: Maneja la lógica de negocio y criptografía para integraciones.
    Patrón: Secure Proxy.
    """

    @staticmethod
    async def create_integration(db, user_id: str, provider: ProviderType, payload: IntegrationPayload, request_meta: Dict[str, Any]={}) -> IntegrationDB:
        """
        Crea o actualiza una integración aplicando encriptación AES-256 (Military Grade).

        Args:
            db: Instancia de la base de datos Motor (request.app.state.db).
            user_id: ID del usuario propietario.
            provider: Enum del proveedor (ej: ProviderType.GMAIL).
            payload: DTO con los tokens en texto plano (IntegrationPayload).
            request_meta: Metadatos de la petición (IP, UserAgent) para auditoría.

        Returns:
            IntegrationDB: El objeto guardado (con credenciales ya encriptadas).
        """
        try:
            logger.info(f' INTENTO DE VINCULACIÓN: User {user_id} -> Provider {provider.value}')
            sensitive_data = payload.model_dump(mode='json', exclude_none=True)
            payload_str = json.dumps(sensitive_data)
            encrypted_blob = encrypt_data(payload_str)
            current_time = datetime.now(timezone.utc)
            audit_metadata = {'last_ip': request_meta.get('ip', 'unknown'), 'user_agent': request_meta.get('user_agent', 'unknown'), 'updated_by': 'system_service', 'last_handshake': current_time.isoformat()}
            new_integration = IntegrationDB(user_id=user_id, provider=provider, encrypted_credentials=encrypted_blob, is_active=True, status='connected', metadata=audit_metadata, updated_at=current_time, created_at=current_time)
            update_data = new_integration.model_dump(by_alias=True, exclude={'id', 'created_at'})
            result = await db['integrations'].update_one({'user_id': user_id, 'provider': provider.value}, {'$set': update_data, '$setOnInsert': {'created_at': new_integration.created_at}}, upsert=True)
            logger.info(f' VINCULACIÓN EXITOSA: User {user_id} -> {provider.value} | Modified: {result.modified_count}, Upserted: {result.upserted_id}')
            return new_integration
        except Exception as e:
            logger.error(f' CRITICAL ERROR en IntegrationService: {str(e)}', exc_info=True)
            raise RuntimeError('Error interno procesando la integración segura.') from e

    @staticmethod
    async def get_decrypted_credentials(db, user_id: str, provider: str) -> Optional[Dict[str, Any]]:
        """
        Recupera y DESENCRIPTA credenciales Just-In-Time (JIT).

        SECURITY CHECK:
        - Verifica que la integración exista.
        - Verifica que is_active == True (Kill Switch).
        """
        try:
            integration = await db['integrations'].find_one({'user_id': user_id, 'provider': provider}, {'encrypted_credentials': 1, 'is_active': 1, '_id': 0})
            if not integration:
                logger.warning(f' Acceso denegado: Integración no encontrada ({user_id} -> {provider})')
                return None
            if not integration.get('is_active'):
                logger.warning(f' Acceso denegado: Integración DESACTIVADA por seguridad ({user_id} -> {provider})')
                return None
            if 'encrypted_credentials' not in integration:
                logger.error(f' CORRUPCIÓN DE DATOS: Integración sin blob encriptado ({user_id} -> {provider})')
                return None
            decrypted_json = decrypt_data(integration['encrypted_credentials'])
            return json.loads(decrypted_json)
        except Exception as e:
            logger.critical(f' FALLO DE INTEGRIDAD CRÍTICO: No se pudo desencriptar ({user_id} -> {provider}). Posible rotación de claves incorrecta.', exc_info=True)
            return None
