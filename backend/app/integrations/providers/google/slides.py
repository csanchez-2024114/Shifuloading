"""
Google Slides Service - Credenciales OAuth y refresco de tokens

Migración a lectura desde oauth_vault (Vault-First / Legacy-Fallback).
Escritura exclusiva en oauth_vault con tokens encriptados y upsert seguro.
Arquitectura Refactorizada: Patrón Circuit Breaker (Fail-Fast) y Telemetría.
"""

import os
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import requests
from dotenv import load_dotenv
from config import Config
from langchain_core.tools import ToolException
from app.core.mongo import get_sync_database
from app.database import _normalize_integrations
from app.core.constants import Collections
from app.core.db_utils import find_user_by_email, canonicalize_email

load_dotenv()
try:
    from app.core.security import encrypt_data
except ImportError:
    logging.getLogger(__name__).warning(
        "[google_slides_service] Módulo de encriptación no disponible. Usando texto plano (MODO DEV)."
    )

    def encrypt_data(data: str) -> str:
        return data


logger = logging.getLogger("services.google_slides")
_INTEGRATION_KEY = "Google Slides"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_REQUEST_TIMEOUT = 10


def _get_db():
    return get_sync_database()


def _get_config_var(var_name: str, fallback_var: str = "") -> str:
    """
    Extrae variable de Config con fallback doble para evitar AttributeError.
    Útil porque Slides suele compartir el Client ID de Docs/Drive.
    """
    val = getattr(Config, var_name, os.getenv(var_name))
    if not val and fallback_var:
        val = getattr(Config, fallback_var, os.getenv(fallback_var, ""))
    return val or ""


def _get_slides_creds_raw(email_safe: str) -> Optional[Dict[str, Any]]:
    """Ejecuta Vault-First / Legacy-Fallback y devuelve credenciales desencriptadas."""
    db = _get_db()
    vault_doc = db[Collections.OAUTH_VAULT].find_one(
        {"$or": [{"correo": email_safe}, {"email": email_safe}]}
    )
    if vault_doc and vault_doc.get("integrations"):
        integrations = _normalize_integrations(
            vault_doc["integrations"], source="vault", correo=email_safe
        )
    else:
        legacy_doc = find_user_by_email(db, email_safe)
        if not legacy_doc:
            integrations = {}
        else:
            integrations = _normalize_integrations(
                legacy_doc.get("integrations", {}), source="legacy", correo=email_safe
            )
    creds = integrations.get(_INTEGRATION_KEY) or integrations.get("GoogleSlides")
    if creds:
        return creds
    from app.integrations.providers.google.oauth_shared import get_google_creds_from_v2

    return get_google_creds_from_v2(email_safe, db=db)


def refresh_slides_token(email: str, slides_creds: Dict[str, Any]) -> Optional[str]:
    """
    Usa el refresh_token para obtener un nuevo access_token y lo persiste
    encriptado en oauth_vault aplicando UPSERT para migrar usuarios legacy.
    Aplica patrón Fail-Fast si las credenciales fueron revocadas.
    """
    email_safe = canonicalize_email(email)
    refresh_token = slides_creds.get("refresh_token")
    if not refresh_token:
        logger.error(
            f"[google_slides_service] refresh_token ausente para '{email_safe}'."
        )
        return None
    data = {
        "client_id": _get_config_var("GOOGLE_CLIENT_ID", "DOCS_CLIENT_ID"),
        "client_secret": _get_config_var("GOOGLE_CLIENT_SECRET", "DOCS_CLIENT_SECRET"),
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    try:
        response = requests.post(_GOOGLE_TOKEN_URL, data=data, timeout=_REQUEST_TIMEOUT)
        if response.status_code == 200:
            nuevo_token: str = response.json().get("access_token", "")
            if not nuevo_token:
                logger.error(
                    f"[google_slides_service] Google no devolvió access_token para '{email_safe}'."
                )
                return None
            db = _get_db()
            now_utc = datetime.now(timezone.utc)
            timestamp_str = now_utc.strftime("%Y-%m-%d %H:%M:%S")
            user_id = "unknown"
            legacy_user = find_user_by_email(db, email_safe)
            if legacy_user and legacy_user.get("_id"):
                user_id = str(legacy_user["_id"])
            db[Collections.OAUTH_VAULT].update_one(
                {"$or": [{"correo": email_safe}, {"email": email_safe}]},
                {
                    "$set": {
                        f"integrations.{_INTEGRATION_KEY}.token": encrypt_data(
                            nuevo_token
                        ),
                        f"integrations.{_INTEGRATION_KEY}.timestamp": timestamp_str,
                        "updated_at": now_utc,
                        "correo": email_safe,
                        "email": email_safe,
                    },
                    "$setOnInsert": {
                        "created_at": now_utc,
                        "user_id": user_id,
                        "provider": "server_side_oauth",
                        "status": "active",
                    },
                },
                upsert=True,
            )
            logger.info(
                f"[google_slides_service] Token refrescado y persistido en bóveda para '{email_safe}'."
            )
            return nuevo_token
        else:
            try:
                error_data = response.json()
            except ValueError:
                error_data = {}
            if error_data.get("error") == "invalid_grant":
                logger.warning(
                    f"[google_slides_service] Refresh token revocado/expirado para '{email_safe}'."
                )
                raise ToolException(
                    "La sesión de Google ha expirado o el token es inválido. Por favor, reconecta tu cuenta desde el panel de integraciones."
                )
            logger.error(
                f"[google_slides_service] Error HTTP {response.status_code} al refrescar token para '{email_safe}': {response.text}"
            )
            return None
    except ToolException:
        raise
    except requests.Timeout:
        logger.error(
            f"[google_slides_service] Timeout al intentar conectar con Google para '{email_safe}'."
        )
        raise ToolException(
            "Timeout al contactar a Google Slides. La red está inestable, inténtalo en unos momentos."
        )
    except requests.RequestException as exc:
        logger.error(
            f"[google_slides_service] Error de red al refrescar token para '{email_safe}': {exc}"
        )
        raise ToolException(
            "Falla de red al contactar a Google Slides. Verifica la conectividad del servidor."
        )
    except Exception as e:
        logger.error(
            f"[google_slides_service] Fallo inesperado procesando token para '{email_safe}': {e}",
            exc_info=True,
        )
        return None


def get_slides_creds_for_langchain(
    user_id: str, account_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Obtiene credenciales de Google Slides, refresca token proactivamente,
    y devuelve diccionario compatible con LangChain.
    """
    if not user_id:
        raise ToolException(
            "ID de usuario inválido o no proporcionado al servicio de Google Slides."
        )
    try:
        from app.integrations.providers.google.oauth_shared import (
            get_google_creds_from_v2,
            refresh_google_token_v2,
        )

        db = _get_db()
        v2 = get_google_creds_from_v2(
            user_id, account_id, provider_hint="google_slides", db=db
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
            token = v2.get("token")
            if not token:
                raise ToolException(
                    "Credenciales incompletas: No se pudo obtener el token de acceso válido de Google."
                )
            return {
                "token": token,
                "refresh_token": v2.get("refresh_token"),
                "token_uri": _get_config_var("GOOGLE_TOKEN_URI", "DOCS_TOKEN_URI")
                or "https://oauth2.googleapis.com/token",
                "client_id": _get_config_var("GOOGLE_CLIENT_ID", "DOCS_CLIENT_ID"),
                "client_secret": _get_config_var(
                    "GOOGLE_CLIENT_SECRET", "DOCS_CLIENT_SECRET"
                ),
                "scopes": getattr(
                    Config,
                    "SLIDES_SCOPES",
                    [
                        "https://www.googleapis.com/auth/presentations",
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
        slides_creds = _get_slides_creds_raw(email_safe)
        if not slides_creds or not slides_creds.get("refresh_token"):
            raise ToolException(
                "No hay cuenta de Google conectada. Por favor, vincula tu cuenta desde el panel de integraciones."
            )
        nuevo_token = refresh_slides_token(email_safe, slides_creds)
        if nuevo_token:
            slides_creds["token"] = nuevo_token
        token = slides_creds.get("token")
        if not token:
            raise ToolException(
                "Credenciales incompletas: No se pudo obtener el token de acceso válido de Google."
            )
        return {
            "token": token,
            "refresh_token": slides_creds.get("refresh_token"),
            "token_uri": _get_config_var("GOOGLE_TOKEN_URI", "DOCS_TOKEN_URI")
            or "https://oauth2.googleapis.com/token",
            "client_id": _get_config_var("GOOGLE_CLIENT_ID", "DOCS_CLIENT_ID"),
            "client_secret": _get_config_var(
                "GOOGLE_CLIENT_SECRET", "DOCS_CLIENT_SECRET"
            ),
            "scopes": getattr(
                Config,
                "SLIDES_SCOPES",
                [
                    "https://www.googleapis.com/auth/presentations",
                    "https://www.googleapis.com/auth/drive.file",
                ],
            ),
        }
    except ToolException:
        raise
    except Exception as e:
        logger.error(
            f"[google_slides_service] Error interno al obtener credenciales para user_id={user_id}: {e}",
            exc_info=True,
        )
        raise ToolException(
            "Error interno del servidor al acceder a las credenciales de Google Slides."
        )

