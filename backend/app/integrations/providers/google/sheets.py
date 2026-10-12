"""
Servicio de Integración: Google Sheets.
Refactorización: Desencriptación segura (Vault-First), unificación de Config y Circuit Breaker.
"""

import os
import logging
from typing import Dict, Any, Optional, Tuple
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google.auth.exceptions import GoogleAuthError, RefreshError
from langchain_core.tools import ToolException
from config import Config
from app.core.mongo import get_sync_database
from app.database import _normalize_integrations
from app.core.constants import Collections
from app.core.db_utils import canonicalize_email, find_user_by_email

load_dotenv()
logger = logging.getLogger(__name__)
_INTEGRATION_KEY = "Google Sheets"
_SHEETS_KEY_ALIASES = (
    "Google Sheets",
    "GoogleSheets",
    "google_sheets",
    "sheets",
    "Sheets",
)


def _get_db():
    """Devuelve la DB canónica desde la conexión global sync."""
    return get_sync_database()


def _get_config_var(var_name: str, fallback_var: str = "") -> str:
    """Extrae variable de Config con fallback doble para evitar AttributeError."""
    val = getattr(Config, var_name, os.getenv(var_name))
    if not val and fallback_var:
        val = getattr(Config, fallback_var, os.getenv(fallback_var, ""))
    return val or ""


def _get_sheets_creds_raw(
    email_safe: str,
) -> Tuple[Optional[Dict[str, Any]], Optional[str], bool]:
    """Ejecuta Vault-First / Legacy-Fallback y devuelve credenciales desencriptadas."""
    db = _get_db()
    is_nested = True
    exact_key = _INTEGRATION_KEY
    vault_doc = db[Collections.OAUTH_VAULT].find_one(
        {"$or": [{"correo": email_safe}, {"email": email_safe}]}
    )
    if vault_doc and vault_doc.get("integrations"):
        integrations = _normalize_integrations(
            vault_doc["integrations"], source="vault", correo=email_safe
        )
    elif vault_doc:
        integrations = _normalize_integrations(
            vault_doc, source="vault", correo=email_safe
        )
        is_nested = False
    else:
        legacy_doc = find_user_by_email(db, email_safe)
        if not legacy_doc:
            integrations = {}
        else:
            integrations = _normalize_integrations(
                legacy_doc.get("integrations", {}), source="legacy", correo=email_safe
            )
    norm = lambda k: k.lower().replace(" ", "_").replace("-", "_")
    for key, value in integrations.items():
        if norm(key) in [norm(alias) for alias in _SHEETS_KEY_ALIASES]:
            if isinstance(value, dict):
                return (value, key, is_nested)
    from app.integrations.providers.google.oauth_shared import get_google_creds_from_v2

    v2 = get_google_creds_from_v2(email_safe, db=db)
    if v2:
        return (v2, "Google", False)
    return (None, None, False)


def refresh_google_sheets_token(
    creds_dict: Dict[str, Any], email_safe: str
) -> Dict[str, Any]:
    """
    Verifica si el token está vencido y lo refresca utilizando la API de Google.
    Aplica patrón Fail-Fast si las credenciales fueron revocadas.
    """
    try:
        token_uri = (
            creds_dict.get("token_uri")
            or _get_config_var("GOOGLE_TOKEN_URI", "SHEETS_TOKEN_URI")
            or "https://oauth2.googleapis.com/token"
        )
        client_id = creds_dict.get("client_id") or _get_config_var(
            "GOOGLE_CLIENT_ID", "SHEETS_CLIENT_ID"
        )
        client_secret = creds_dict.get("client_secret") or _get_config_var(
            "GOOGLE_CLIENT_SECRET", "SHEETS_CLIENT_SECRET"
        )
        scopes = creds_dict.get("scopes") or getattr(
            Config, "SHEETS_SCOPES", ["https://www.googleapis.com/auth/spreadsheets"]
        )
        creds = Credentials(
            token=creds_dict.get("token"),
            refresh_token=creds_dict.get("refresh_token"),
            token_uri=token_uri,
            client_id=client_id,
            client_secret=client_secret,
            scopes=scopes,
        )
        if creds.expired and creds.refresh_token:
            logger.info(
                f"Token de Google Sheets vencido para {email_safe}, solicitando refresh vía google-auth..."
            )
            creds.refresh(Request())
            return {
                "token": creds.token,
                "refresh_token": creds.refresh_token,
                "token_uri": creds.token_uri,
                "client_id": creds.client_id,
                "client_secret": creds.client_secret,
                "scopes": creds.scopes,
            }
        return creds_dict
    except RefreshError as e:
        error_msg = str(e).lower()
        if "invalid_grant" in error_msg or "revoked" in error_msg:
            logger.warning(
                f"Refresh token revocado/expirado para {email_safe} (Sheets)."
            )
            raise ToolException(
                "La sesión de Google ha expirado o el token es inválido. Por favor, reconecta tu cuenta desde el panel de integraciones."
            )
        logger.error(
            f"Error RefreshError al refrescar token de Sheets para {email_safe}: {e}"
        )
        raise ToolException(
            "Error al refrescar la sesión de Google Sheets. Verifica la conexión o reconecta tu cuenta."
        )
    except GoogleAuthError as e:
        logger.error(
            f"Error de autenticación al refrescar token de Sheets para {email_safe}: {e}"
        )
        raise ToolException(
            "Fallo de autenticación con Google. Verifica la red o reconecta tu cuenta."
        )
    except ToolException:
        raise
    except Exception as e:
        logger.error(
            f"Error inesperado al intentar refrescar token de Sheets para {email_safe}.",
            exc_info=True,
        )
        raise ToolException(
            "Error inesperado en el servidor al verificar credenciales de Google Sheets."
        )
        raise ToolException(
            "Error inesperado en el servidor al verificar credenciales de Google Sheets."
        )


def get_sheets_creds_for_langchain(
    user_id: str, account_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Recupera credenciales de Google Sheets desencriptadas.
    Refresca si es necesario y guarda el nuevo token encriptado en MongoDB.
    """
    try:
        from app.integrations.providers.google.oauth_shared import (
            get_google_creds_from_v2,
            refresh_google_token_v2,
        )

        db = _get_db()
        v2 = get_google_creds_from_v2(
            user_id, account_id, provider_hint="google_sheets", db=db
        )
        if v2 and v2.get("refresh_token"):
            nuevo_token = refresh_google_token_v2(
                user_id,
                account_id or "",
                v2,
                _get_config_var("GOOGLE_CLIENT_ID", "SHEETS_CLIENT_ID"),
                _get_config_var("GOOGLE_CLIENT_SECRET", "SHEETS_CLIENT_SECRET"),
                db,
            )
            if nuevo_token:
                v2["token"] = nuevo_token
            return {
                "token": v2.get("token"),
                "refresh_token": v2.get("refresh_token"),
                "token_uri": _get_config_var("GOOGLE_TOKEN_URI", "SHEETS_TOKEN_URI")
                or "https://oauth2.googleapis.com/token",
                "client_id": _get_config_var("GOOGLE_CLIENT_ID", "SHEETS_CLIENT_ID"),
                "client_secret": _get_config_var(
                    "GOOGLE_CLIENT_SECRET", "SHEETS_CLIENT_SECRET"
                ),
                "scopes": getattr(
                    Config,
                    "SHEETS_SCOPES",
                    [
                        "https://www.googleapis.com/auth/spreadsheets",
                        "https://www.googleapis.com/auth/drive.file",
                    ],
                ),
            }

        # Legacy fallback: look up email by user_id, then search oauth_vault
        try:
            from bson.objectid import ObjectId

            user = db[Collections.USERS].find_one({"_id": ObjectId(user_id)})
            email_safe = canonicalize_email(user.get("email") if user else "")
        except Exception:
            email_safe = ""
        if not email_safe:
            raise ToolException(
                "No hay cuenta de Google conectada. Por favor, vincula tu cuenta desde el panel de integraciones."
            )
        sheets_creds, exact_key, is_nested = _get_sheets_creds_raw(email_safe)
        if not sheets_creds or not sheets_creds.get("refresh_token"):
            logger.warning(
                f"No se encontraron credenciales de Google Sheets para user_id={user_id}."
            )
            raise ToolException(
                "No hay cuenta de Google conectada. Por favor, vincula tu cuenta desde el panel de integraciones."
            )
        creds_dict = {
            "token": sheets_creds.get("token"),
            "refresh_token": sheets_creds.get("refresh_token"),
            "token_uri": _get_config_var("GOOGLE_TOKEN_URI", "SHEETS_TOKEN_URI"),
            "client_id": _get_config_var("GOOGLE_CLIENT_ID", "SHEETS_CLIENT_ID"),
            "client_secret": _get_config_var(
                "GOOGLE_CLIENT_SECRET", "SHEETS_CLIENT_SECRET"
            ),
            "scopes": getattr(
                Config,
                "SHEETS_SCOPES",
                [
                    "https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive.file",
                ],
            ),
        }
        nuevos_creds = refresh_google_sheets_token(creds_dict, email_safe)
        if nuevos_creds.get("token") and nuevos_creds["token"] != creds_dict.get(
            "token"
        ):
            update_path = (
                f"integrations.{exact_key or _INTEGRATION_KEY}.token"
                if is_nested
                else f"{exact_key or _INTEGRATION_KEY}.token"
            )
            try:
                from app.core.security import encrypt_data
            except ImportError:
                logger.warning(
                    "No se pudo importar encrypt_data. El token se guardará en texto plano."
                )
                encrypt_data = lambda x: x
            db[Collections.OAUTH_VAULT].update_one(
                {"$or": [{"correo": email_safe}, {"email": email_safe}]},
                {"$set": {update_path: encrypt_data(nuevos_creds["token"])}},
            )
            logger.info(
                f"Token de Google Sheets actualizado en [{update_path}] para {email_safe}."
            )
        return nuevos_creds
    except ToolException:
        raise
    except Exception as e:
        logger.error(
            "Error interno al consultar o refrescar credenciales de Google Sheets",
            exc_info=True,
        )
        raise ToolException(
            "Error interno del servidor al acceder a las credenciales de Google Sheets."
        )

