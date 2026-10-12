"""
Servicio de Integración: Gmail.
Refactorización V3: Lectura directa desde `user_connected_accounts` (modelo multicuenta).
"""

import os
import logging
import requests
from typing import Dict, Any, Optional, Tuple
from dotenv import load_dotenv
from langchain_core.tools import ToolException
from config import Config
from app.core.mongo import get_sync_database
from app.core.constants import Collections
from app.core.db_utils import canonicalize_email, find_user_by_email
from app.integrations.providers.google.oauth_shared import get_google_creds_from_v2

load_dotenv()
logger = logging.getLogger(__name__)
_INTEGRATION_KEY = "Gmail"
_GMAIL_KEY_ALIASES = ("Gmail", "google_mail", "gmail", "Google Mail")


def _get_db():
    """Devuelve la DB canónica desde la conexión global sync."""
    return get_sync_database()


def _get_config_var(var_name: str, fallback_var: str = "") -> str:
    """Extrae variable de Config con fallback doble para evitar AttributeError."""
    val = getattr(Config, var_name, os.getenv(var_name))
    if not val and fallback_var:
        val = getattr(Config, fallback_var, os.getenv(fallback_var, ""))
    return val or ""


def _get_gmail_creds_raw(
    user_id: str, account_id: Optional[str] = None
) -> Tuple[Optional[Dict[str, Any]], Optional[str], bool]:
    """Obtiene credenciales de `user_connected_accounts`."""
    db = _get_db()
    v2 = get_google_creds_from_v2(user_id, account_id, provider_hint="gmail", db=db)
    if v2:
        return (v2, "Google", False)
    return (None, None, False)


def get_gmail_creds_for_langchain(
    user_id: str, account_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Recupera credenciales de Gmail desencriptadas (EN canonical).
    Refresca si es necesario y guarda el nuevo token encriptado en MongoDB.
    """
    try:
        gmail_creds, _, _ = _get_gmail_creds_raw(user_id, account_id)
        if not gmail_creds or not gmail_creds.get("refresh_token"):
            # Este es el warning que estás viendo.
            logger.warning(
                f"No se encontraron credenciales de Gmail para user_id={user_id}, account_id={account_id}."
            )
            raise ToolException(
                # Este es el error que se propaga y ves en el log del executor.
                "No hay cuenta de Gmail conectada. Por favor, vincula tu cuenta desde el panel de integraciones."
            )
        nuevo_token = refresh_gmail_token(
            user_id,
            account_id or "",
            gmail_creds,
        )
        if nuevo_token:
            gmail_creds["token"] = nuevo_token
        return {
            "token": gmail_creds.get("token"),
            "refresh_token": gmail_creds.get("refresh_token"),
            "token_uri": _get_config_var("GOOGLE_TOKEN_URI", "GMAIL_TOKEN_URI")
            or "https://oauth2.googleapis.com/token",
            "client_id": _get_config_var("GOOGLE_CLIENT_ID", "GMAIL_CLIENT_ID"),
            "client_secret": _get_config_var(
                "GOOGLE_CLIENT_SECRET", "GMAIL_CLIENT_SECRET"
            ),
            "scopes": getattr(
                Config,
                "GMAIL_SCOPES",
                [
                    "https://www.googleapis.com/auth/gmail.modify",
                    "https://www.googleapis.com/auth/drive",
                    "https://www.googleapis.com/auth/documents",
                    "https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/presentations",
                ],
            ),
        }
    except ToolException:
        raise
    except Exception as e:
        logger.error(
            "Error interno al consultar o refrescar credenciales de Gmail.",
            exc_info=True,
        )
        raise ToolException(
            "Error interno del servidor al acceder a las credenciales de Gmail."
        )


def refresh_gmail_token(
    user_id: str, account_id: str, gmail_creds: Dict[str, Any]
) -> Optional[str]:
    """Usa el refresh_token para obtener un nuevo access_token y lo actualiza encriptado. (EN canonical)"""
    try:
        try:
            from app.core.security import encrypt_data
        except ImportError:
            logger.warning(
                "No se pudo importar encrypt_data. Se guardará en texto plano."
            )
            encrypt_data = lambda x: x
        data = {
            "client_id": _get_config_var("GOOGLE_CLIENT_ID", "GMAIL_CLIENT_ID"),
            "client_secret": _get_config_var(
                "GOOGLE_CLIENT_SECRET", "GMAIL_CLIENT_SECRET"
            ),
            "refresh_token": gmail_creds["refresh_token"],
            "grant_type": "refresh_token",
        }
        response = requests.post(
            "https://oauth2.googleapis.com/token", data=data, timeout=10
        )
        if response.status_code == 200:
            nuevo_token = response.json().get("access_token")
            db = _get_db()
            db[Collections.USER_CONNECTED_ACCOUNTS].update_one(
                {"user_id": user_id, "account_id": account_id, "provider": "google"},
                {"$set": {"access_token": encrypt_data(nuevo_token)}},
            )
            logger.info(
                f"Token de Gmail refrescado y guardado para user_id={user_id}, account_id={account_id}."
            )
            return nuevo_token
        else:
            try:
                error_data = response.json()
            except ValueError:
                error_data = {}
            if error_data.get("error") == "invalid_grant":
                logger.warning(
                    f"Refresh token revocado/expirado para user_id={user_id}, account_id={account_id} (Gmail)."
                )
                raise ToolException(
                    "La sesión de Gmail ha expirado o el token es inválido. Por favor, reconecta tu cuenta desde el panel de integraciones."
                )
            logger.error(
                f"Error HTTP de Google al refrescar token Gmail. Status: {response.status_code}. Details: {response.text}"
            )
            return None
    except ToolException:
        raise
    except requests.Timeout:
        logger.error(
            f"Timeout al intentar conectar con oauth2.googleapis.com para user_id={user_id} (Gmail)."
        )
        raise ToolException(
            "Timeout al contactar a Google. La red está inestable, inténtalo de nuevo en unos momentos."
        )
    except requests.RequestException as e:
        logger.error(f"Falla de red al refrescar el token de Gmail: {str(e)}")
        raise ToolException(
            "Falla de red al contactar a Google. Verifica la conectividad del servidor."
        )
    except Exception as e:
        logger.error("Error inesperado refrescando el token de Gmail.", exc_info=True)
        return None

