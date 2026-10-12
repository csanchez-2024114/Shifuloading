"""
Servicio de Integración: Google Docs.
Refactorización: Desencriptación segura (Vault-First), unificación de Config y Circuit Breaker.
"""

import os
import logging
import requests
from typing import Dict, Any, Optional, Tuple
from dotenv import load_dotenv
from langchain_core.tools import ToolException
from config import Config
from app.core.mongo import get_sync_database
from app.database import _normalize_integrations
from app.core.constants import Collections
from app.core.db_utils import canonicalize_email, find_user_by_email

load_dotenv()
logger = logging.getLogger(__name__)
_INTEGRATION_KEY = "Google Docs"
_DOCS_KEY_ALIASES = ("Google Docs", "GoogleDocs", "google_docs", "docs", "Docs")


def _get_db():
    """Devuelve la DB canónica desde la conexión global sync."""
    return get_sync_database()


def _get_config_var(var_name: str, fallback_var: str = "") -> str:
    """Extrae variable de Config con fallback doble para evitar AttributeError."""
    val = getattr(Config, var_name, os.getenv(var_name))
    if not val and fallback_var:
        val = getattr(Config, fallback_var, os.getenv(fallback_var, ""))
    return val or ""


def _get_docs_creds_raw(
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
        if norm(key) in [norm(alias) for alias in _DOCS_KEY_ALIASES]:
            if isinstance(value, dict):
                return (value, key, is_nested)
    from app.integrations.providers.google.oauth_shared import get_google_creds_from_v2

    v2 = get_google_creds_from_v2(email_safe, db=db)
    if v2:
        return (v2, "Google", False)
    return (None, None, False)


def get_docs_creds_for_langchain(
    user_id: str, account_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Recupera y valida las credenciales de Google Docs desde oauth_vault.
    Refresca el token de acceso automáticamente si es necesario.
    """
    try:
        from app.integrations.providers.google.oauth_shared import (
            get_google_creds_from_v2,
            refresh_google_token_v2,
        )

        db = _get_db()
        v2 = get_google_creds_from_v2(
            user_id, account_id, provider_hint="google_docs", db=db
        )
        if v2 and v2.get("refresh_token"):
            nuevo_token = refresh_google_token_v2(
                user_id,
                account_id or "",
                v2,
                _get_config_var("GOOGLE_CLIENT_ID", "DOCS_CLIENT_ID"),
                _get_config_var("GOOGLE_CLIENT_SECRET", "DOCS_CLIENT_SECRET"),
                db,
            )
            if nuevo_token:
                v2["token"] = nuevo_token
            return {
                "token": v2.get("token"),
                "refresh_token": v2.get("refresh_token"),
                "token_uri": _get_config_var("GOOGLE_TOKEN_URI", "DOCS_TOKEN_URI")
                or "https://oauth2.googleapis.com/token",
                "client_id": _get_config_var("GOOGLE_CLIENT_ID", "DOCS_CLIENT_ID"),
                "client_secret": _get_config_var(
                    "GOOGLE_CLIENT_SECRET", "DOCS_CLIENT_SECRET"
                ),
                "scopes": getattr(
                    Config,
                    "DOCS_SCOPES",
                    [
                        "https://www.googleapis.com/auth/gmail.modify",
                        "https://www.googleapis.com/auth/drive",
                        "https://www.googleapis.com/auth/documents",
                        "https://www.googleapis.com/auth/spreadsheets",
                        "https://www.googleapis.com/auth/presentations",
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
        docs_creds, exact_key, is_nested = _get_docs_creds_raw(email_safe)
        if not docs_creds or not docs_creds.get("refresh_token"):
            logger.warning(
                f"No se encontraron credenciales de Google Docs para user_id={user_id}."
            )
            raise ToolException(
                "No hay cuenta de Google conectada. Por favor, vincula tu cuenta desde el panel de integraciones."
            )
        nuevo_token = refresh_docs_token(
            email_safe, docs_creds, exact_key or _INTEGRATION_KEY, is_nested
        )
        if nuevo_token:
            docs_creds["token"] = nuevo_token
        return {
            "token": docs_creds.get("token"),
            "refresh_token": docs_creds.get("refresh_token"),
            "token_uri": _get_config_var("GOOGLE_TOKEN_URI", "DOCS_TOKEN_URI")
            or "https://oauth2.googleapis.com/token",
            "client_id": _get_config_var("GOOGLE_CLIENT_ID", "DOCS_CLIENT_ID"),
            "client_secret": _get_config_var(
                "GOOGLE_CLIENT_SECRET", "DOCS_CLIENT_SECRET"
            ),
            "scopes": getattr(
                Config,
                "DOCS_SCOPES",
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
            "Error interno al consultar o refrescar credenciales de Google Docs.",
            exc_info=True,
        )
        raise ToolException(
            "Error interno del servidor al acceder a las credenciales de Google Docs."
        )


def refresh_docs_token(
    email_safe: str, docs_creds: Dict[str, Any], exact_key: str, is_nested: bool = True
) -> Optional[str]:
    """
    Usa el refresh_token para obtener un nuevo access_token y actualiza la ruta exacta en MongoDB.
    """
    try:
        try:
            from app.core.security import encrypt_data
        except ImportError:
            logger.warning(
                "No se pudo importar encrypt_data. Se guardará en texto plano."
            )
            encrypt_data = lambda x: x
        data = {
            "client_id": _get_config_var("GOOGLE_CLIENT_ID", "DOCS_CLIENT_ID"),
            "client_secret": _get_config_var(
                "GOOGLE_CLIENT_SECRET", "DOCS_CLIENT_SECRET"
            ),
            "refresh_token": docs_creds["refresh_token"],
            "grant_type": "refresh_token",
        }
        response = requests.post(
            "https://oauth2.googleapis.com/token", data=data, timeout=10
        )
        if response.status_code == 200:
            nuevo_token = response.json().get("access_token")
            update_path = (
                f"integrations.{exact_key}.token" if is_nested else f"{exact_key}.token"
            )
            db = _get_db()
            db[Collections.OAUTH_VAULT].update_one(
                {"$or": [{"correo": email_safe}, {"email": email_safe}]},
                {"$set": {update_path: encrypt_data(nuevo_token)}},
            )
            logger.info(
                f"Token de Google Docs refrescado y guardado ENCRIPTADO en [{update_path}] para {email_safe}."
            )
            return nuevo_token
        else:
            try:
                error_data = response.json()
            except ValueError:
                error_data = {}
            if error_data.get("error") == "invalid_grant":
                logger.warning(
                    f"Refresh token revocado/expirado para {email_safe} (Docs)."
                )
                raise ToolException(
                    "La sesión de Google ha expirado o el token es inválido. Por favor, reconecta tu cuenta desde el panel de integraciones."
                )
            logger.error(
                f"Error HTTP de Google al refrescar token Docs. Status: {response.status_code}."
            )
            return None
    except ToolException:
        raise
    except requests.Timeout:
        logger.error(
            f"Timeout al intentar conectar con oauth2.googleapis.com para {email_safe} (Docs)."
        )
        raise ToolException(
            "Timeout al contactar a Google. La red está inestable, inténtalo de nuevo en unos momentos."
        )
    except requests.RequestException as e:
        logger.error(f"Falla de red al refrescar token de Docs: {str(e)}")
        raise ToolException(
            "Falla de red al contactar a Google Docs. Verifica la conectividad del servidor."
        )
    except Exception as e:
        logger.error("Error inesperado refrescando el token de Docs.", exc_info=True)
        return None

