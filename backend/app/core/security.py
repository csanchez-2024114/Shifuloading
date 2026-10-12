import os
import base64
import logging
from typing import Union
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from dotenv import load_dotenv
logger = logging.getLogger('security.encryption')
load_dotenv()
SECRET_KEY = os.getenv('ENCRYPTION_KEY')
SECRET_SALT = os.getenv('ENCRYPTION_SALT')
if not SECRET_KEY:
    logger.critical(" SECURITY ALERT: Missing 'ENCRYPTION_KEY'. System shutting down.")
    raise ValueError('CRITICAL: Missing ENCRYPTION_KEY env var.')
if not SECRET_SALT:
    logger.warning(" SECURITY WARNING: Missing 'ENCRYPTION_SALT'. Using unsafe fallback. Fix this in production!")
    SECRET_SALT = 'static_fallback_salt_CHANGE_ME_IMMEDIATELY'

def _get_cipher_suite() -> Fernet:
    """
    Inicializa el motor criptográfico Fernet (AES-128-CBC + HMAC-SHA256).
    Garantiza que la clave derivada sea de 32 bytes URL-safe base64.
    """
    try:
        return Fernet(SECRET_KEY)
    except Exception:
        try:
            kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=SECRET_SALT.encode(), iterations=480000)
            key = base64.urlsafe_b64encode(kdf.derive(SECRET_KEY.encode()))
            return Fernet(key)
        except Exception as e:
            logger.critical(f' FATAL: Could not derive encryption key. {str(e)}')
            raise e
_cipher_suite = _get_cipher_suite()

def encrypt_data(data: str) -> str:
    """
    Cifra un string usando Fernet (Symmetric Encryption).
    Garantiza integridad y confidencialidad.
    
    Args:
        data: El texto plano a cifrar (ej. JSON credentials).
    Returns:
        str: El 'token' cifrado en base64 url-safe.
    """
    if not data:
        return ''
    try:
        encrypted_bytes = _cipher_suite.encrypt(data.encode('utf-8'))
        return encrypted_bytes.decode('utf-8')
    except Exception as e:
        logger.error(' Encryption failed for data payload.', exc_info=True)
        raise RuntimeError('Internal encryption error.') from e

def decrypt_data(token: str) -> str:
    """
    Descifra un token Fernet.
    Valida la firma HMAC automáticamente (tamper-proof).

    Args:
        token: El string cifrado.
    Returns:
        str: El texto plano original.
    """
    if not token:
        return ''
    try:
        decrypted_bytes = _cipher_suite.decrypt(token.encode('utf-8'))
        return decrypted_bytes.decode('utf-8')
    except InvalidToken:
        logger.warning(' SECURITY EVENT: Invalid Token detected. Possible tampering or wrong key.')
        raise ValueError('Invalid or corrupted token.')
    except Exception as e:
        logger.error(' Decryption failed due to unexpected error.', exc_info=True)
        raise RuntimeError('Internal decryption error.') from e


# ─────────────────────────────────────────────────────────────────────────────
# Secrets Vault — SEPARATE cipher instance, deliberately not sharing key
# material with the OAuth/integrations vault above (encrypt_data/decrypt_data).
# Blast radius isolation: a compromise of ENCRYPTION_KEY (OAuth tokens) must
# not also expose personal secrets, and vice versa.
# ─────────────────────────────────────────────────────────────────────────────

SECRETS_SECRET_KEY = os.getenv('SECRETS_ENCRYPTION_KEY')
if not SECRETS_SECRET_KEY:
    logger.critical(" SECURITY ALERT: Missing 'SECRETS_ENCRYPTION_KEY'. System shutting down.")
    raise ValueError('CRITICAL: Missing SECRETS_ENCRYPTION_KEY env var.')


def _get_secrets_cipher_suite() -> Fernet:
    """
    Segunda instancia Fernet, derivada de SECRETS_ENCRYPTION_KEY (nunca de
    ENCRYPTION_KEY). Misma mecánica que _get_cipher_suite, clave distinta.
    """
    try:
        return Fernet(SECRETS_SECRET_KEY)
    except Exception:
        try:
            kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=SECRET_SALT.encode(), iterations=480000)
            key = base64.urlsafe_b64encode(kdf.derive(SECRETS_SECRET_KEY.encode()))
            return Fernet(key)
        except Exception as e:
            logger.critical(f' FATAL: Could not derive secrets encryption key. {str(e)}')
            raise e


_secrets_cipher_suite = _get_secrets_cipher_suite()


def encrypt_secret(data: str) -> str:
    """
    Cifra un string usando Fernet con la clave SECRETS_ENCRYPTION_KEY (bóveda de
    secretos personales del usuario — user_secrets). NUNCA usar para tokens
    OAuth/integraciones, esos van por encrypt_data (ENCRYPTION_KEY).
    """
    if not data:
        return ''
    try:
        encrypted_bytes = _secrets_cipher_suite.encrypt(data.encode('utf-8'))
        return encrypted_bytes.decode('utf-8')
    except Exception as e:
        logger.error(' Secrets encryption failed for data payload.', exc_info=True)
        raise RuntimeError('Internal encryption error.') from e


def decrypt_secret(token: str) -> str:
    """
    Descifra un token cifrado con encrypt_secret (SECRETS_ENCRYPTION_KEY).
    """
    if not token:
        return ''
    try:
        decrypted_bytes = _secrets_cipher_suite.decrypt(token.encode('utf-8'))
        return decrypted_bytes.decode('utf-8')
    except InvalidToken:
        logger.warning(' SECURITY EVENT: Invalid Token detected (secrets vault). Possible tampering or wrong key.')
        raise ValueError('Invalid or corrupted token.')
    except Exception as e:
        logger.error(' Secrets decryption failed due to unexpected error.', exc_info=True)
        raise RuntimeError('Internal decryption error.') from e
