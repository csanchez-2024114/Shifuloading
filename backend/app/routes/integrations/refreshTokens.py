"""
Rutas y lógica de Mantenimiento de Tokens (Refresh)
Integrado con Bóveda Segura (oauth_vault).
- Lectura y desencriptación automática vía get_user_vault_with_fallback.
- Escritura estricta con encriptación (Fernet) al rotar tokens.
- Corrección de Event Loop (await) en operaciones de base de datos.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, model_validator
from typing import Optional, Dict, Any, Tuple
import requests
import os
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import logging
from app.database import get_db, get_user_vault_with_fallback
from app.core.constants import Collections

try:
    from app.core.security import encrypt_data
except ImportError:
    logging.getLogger(__name__).warning(
        "Módulo de encriptación no disponible. Usando texto plano (MODO DEV)."
    )

    def encrypt_data(data: str) -> str:
        return data


load_dotenv()
router = APIRouter()
logger = logging.getLogger("routes.refresh_tokens")
_REQUEST_TIMEOUT = 15


class RefreshTokenRequest(BaseModel):
    userEmail: str = Field(..., description="Email del usuario")
    integrationName: Optional[str] = Field(
        None, description="Nombre de la integración específica a refrescar"
    )

    @model_validator(mode="before")
    def accept_email_aliases(cls, values: dict) -> dict:
        if not isinstance(values, dict):
            return values
        if "userEmail" not in values and "user_email" in values:
            values["userEmail"] = values.get("user_email")
        if "userEmail" not in values and "email" in values:
            values["userEmail"] = values.get("email")
        if "userEmail" not in values and "correo" in values:
            values["userEmail"] = values.get("correo")
        return values


class RefreshTokenResponse(BaseModel):
    success: bool
    refreshedTokens: Optional[Dict[str, str]] = None
    errors: Optional[Dict[str, str]] = None
    message: Optional[str] = None


async def get_refresh_tokens_from_db(user_email: str, db_conn) -> Dict[str, str]:
    """
    Obtiene los refresh tokens desencriptados usando el motor central de lectura.
    """
    integrations = await get_user_vault_with_fallback(user_email, db_conn)
    if not integrations:
        raise ValueError(f"El usuario '{user_email}' no tiene integraciones guardadas.")
    refresh_tokens = {}
    for name, integration in integrations.items():
        if isinstance(integration, dict):
            rt = integration.get("refresh_token")
            if rt and rt != "n/a":
                refresh_tokens[name] = rt
    if not refresh_tokens:
        logger.warning(f"No se encontraron refresh tokens válidos para {user_email}")
    logger.info(
        f"Refresh tokens listos para evaluar en {user_email}: {list(refresh_tokens.keys())}"
    )
    return refresh_tokens


def is_token_expired(timestamp: str, expires_in: int = 1800) -> bool:
    """Check if the token is expired or near expiration (within 5 minutes)."""
    if not timestamp:
        return True
    try:
        token_time = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
        token_time = token_time.replace(tzinfo=timezone.utc)
        expiration_time = token_time + timedelta(seconds=expires_in)
        buffer_time = datetime.now(timezone.utc) + timedelta(minutes=5)
        return expiration_time < buffer_time
    except ValueError:
        logger.warning(f"Formato de timestamp inválido detectado: {timestamp}")
        return True


async def save_access_token_to_db(
    db_conn,
    redis,
    user_email: str,
    integration_name: str,
    access_token: str,
    new_refresh_token: Optional[str] = None,
) -> None:
    """
    [ESCRITURA SEGURA] Encripta y guarda el access token actualizado.
    Aplica Key Mirroring (token == access_token) para retrocompatibilidad.
    """
    try:
        from app.core.db_utils import canonicalize_email

        user_safe = canonicalize_email(user_email)
        now_utc = datetime.now(timezone.utc)
        timestamp_str = now_utc.strftime("%Y-%m-%d %H:%M:%S")
        enc_access = encrypt_data(access_token)
        user_doc, source = await get_user_vault_with_fallback(user_safe, db_conn)
        if source == "none":
            logger.error(
                f"Usuario {user_safe} no encontrado. No se pudo guardar el token V2."
            )
            return
        user_id_str = str(user_doc.get("_id", ""))
        provider_lower = integration_name.lower()
        update_fields = {
            "access_token": enc_access,
            "token": enc_access,
            "timestamp": timestamp_str,
            "status": "active",
            "updated_at": now_utc,
            "metadata.email": user_safe,
            "metadata.name": f"Cuenta de {integration_name}",
        }
        if new_refresh_token:
            update_fields["refresh_token"] = encrypt_data(new_refresh_token)
        result = await db_conn[Collections.USER_CONNECTED_ACCOUNTS].update_one(
            {
                "user_id": user_id_str,
                "provider": provider_lower,
                "account_id": user_safe,
            },
            {"$set": update_fields},
            upsert=True,
        )
        logger.info(
            f"[V2] Token guardado/actualizado exitosamente en '{Collections.USER_CONNECTED_ACCOUNTS}' para {user_safe} ({provider_lower})"
        )
    except Exception as e:
        logger.error(
            f"Error crítico al actualizar token de {integration_name} para {user_email}: {e}"
        )
        raise


def refresh_gmail_token(refresh_token: str) -> str:
    url = "https://oauth2.googleapis.com/token"
    data = {
        "client_id": os.getenv("GMAIL_CLIENT_ID"),
        "client_secret": os.getenv("GMAIL_CLIENT_SECRET"),
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    response = requests.post(url, data=data, timeout=_REQUEST_TIMEOUT)
    response.raise_for_status()
    logger.info(f"Gmail token refresh response: {response.status_code}")
    return response.json()["access_token"]


def refresh_dropbox_token(refresh_token: str) -> str:
    url = "https://api.dropboxapi.com/oauth2/token"
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": os.getenv("DROPBOX_CLIENT_ID"),
        "client_secret": os.getenv("DROPBOX_CLIENT_SECRET"),
    }
    response = requests.post(url, data=data, timeout=_REQUEST_TIMEOUT)
    response.raise_for_status()
    logger.info(f"Dropbox token refresh response: {response.status_code}")
    return response.json()["access_token"]


def refresh_asana_token(refresh_token: str) -> str:
    url = "https://app.asana.com/-/oauth_token"
    data = {
        "grant_type": "refresh_token",
        "client_id": os.getenv("ASANA_CLIENT_ID"),
        "client_secret": os.getenv("ASANA_CLIENT_SECRET"),
        "refresh_token": refresh_token,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    response = requests.post(url, data=data, headers=headers, timeout=_REQUEST_TIMEOUT)
    response.raise_for_status()
    logger.info(f"Asana token refresh response: {response.status_code}")
    access_token = response.json().get("access_token")
    if not access_token:
        raise ValueError("No se encontró 'access_token' en la respuesta.")
    return access_token


def refresh_hubspot_token(refresh_token: str) -> Tuple[str, Optional[str]]:
    url = "https://api.hubapi.com/oauth/v1/token"
    data = {
        "grant_type": "refresh_token",
        "client_id": os.getenv("HUBSPOT_CLIENT_ID"),
        "client_secret": os.getenv("HUBSPOT_CLIENT_SECRET"),
        "refresh_token": refresh_token,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    response = requests.post(url, data=data, headers=headers, timeout=_REQUEST_TIMEOUT)
    response.raise_for_status()
    logger.info(f"HubSpot token refresh response: {response.status_code}")
    response_json = response.json()
    access_token = response_json.get("access_token")
    if not access_token:
        raise ValueError("No se encontró 'access_token' en la respuesta.")
    return (access_token, response_json.get("refresh_token"))


def refresh_outlook_token(refresh_token: str) -> Tuple[str, Optional[str]]:
    url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    data = {
        "client_id": os.getenv("OUTLOOK_CLIENT_ID"),
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
        "scope": "offline_access https://graph.microsoft.com/User.Read https://graph.microsoft.com/Chat.Read https://graph.microsoft.com/Files.Read.All https://graph.microsoft.com/Files.ReadWrite.All https://graph.microsoft.com/Mail.Read https://graph.microsoft.com/Mail.Send https://graph.microsoft.com/TeamsAppInstallation.ReadForChat https://graph.microsoft.com/Team.ReadBasic.All https://graph.microsoft.com/Channel.ReadBasic.All",
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    response = requests.post(url, data=data, headers=headers, timeout=_REQUEST_TIMEOUT)
    response.raise_for_status()
    logger.info(f"Outlook token refresh response: {response.status_code}")
    response_json = response.json()
    access_token = response_json.get("access_token")
    if not access_token:
        raise ValueError("No se encontró 'access_token' en la respuesta.")
    return (access_token, response_json.get("refresh_token"))


def refresh_discord_token(refresh_token: str) -> Tuple[str, Optional[str]]:
    url = "https://discord.com/api/oauth2/token"
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": os.getenv("DISCORD_CLIENT_ID"),
        "client_secret": os.getenv("DISCORD_CLIENT_SECRET"),
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    response = requests.post(url, data=data, headers=headers, timeout=_REQUEST_TIMEOUT)
    response.raise_for_status()
    logger.info(f"Discord token refresh response: {response.status_code}")
    response_json = response.json()
    access_token = response_json.get("access_token")
    if not access_token:
        raise ValueError("No se encontró 'access_token' en la respuesta.")
    return (access_token, response_json.get("refresh_token"))


def refresh_facebook_token(refresh_token: str) -> Tuple[str, Optional[str]]:
    url = "https://graph.facebook.com/v20.0/oauth/access_token"
    data = {
        "grant_type": "fb_exchange_token",
        "fb_exchange_token": refresh_token,
        "client_id": os.getenv("FACEBOOK_CLIENT_ID"),
        "client_secret": os.getenv("FACEBOOK_CLIENT_SECRET"),
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    response = requests.post(url, data=data, headers=headers, timeout=_REQUEST_TIMEOUT)
    response.raise_for_status()
    logger.info(f"Facebook token refresh response: {response.status_code}")
    access_token = response.json().get("access_token")
    if not access_token:
        raise ValueError("No se encontró 'access_token' en la respuesta.")
    return (access_token, None)


def refresh_instagram_token(refresh_token: str) -> Tuple[str, Optional[str]]:
    url = "https://api.instagram.com/oauth/access_token"
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": os.getenv("INSTAGRAM_CLIENT_ID"),
        "client_secret": os.getenv("INSTAGRAM_CLIENT_SECRET"),
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    response = requests.post(url, data=data, headers=headers, timeout=_REQUEST_TIMEOUT)
    response.raise_for_status()
    logger.info(f"Instagram token refresh response: {response.status_code}")
    response_json = response.json()
    access_token = response_json.get("access_token")
    if not access_token:
        raise ValueError("No se encontró 'access_token' en la respuesta.")
    return (access_token, response_json.get("refresh_token"))


def refresh_jira_token(refresh_token: str) -> Tuple[str, Optional[str]]:
    url = "https://auth.atlassian.com/oauth/token"
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": os.getenv("JIRA_CLIENT_ID"),
        "client_secret": os.getenv("JIRA_CLIENT_SECRET"),
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    response = requests.post(url, data=data, headers=headers, timeout=_REQUEST_TIMEOUT)
    response.raise_for_status()
    logger.info(f"Jira token refresh response: {response.status_code}")
    response_json = response.json()
    access_token = response_json.get("access_token")
    if not access_token:
        raise ValueError("No se encontró 'access_token' en la respuesta.")
    return (access_token, response_json.get("refresh_token"))


def refresh_linkedin_token(refresh_token: str) -> Tuple[str, Optional[str]]:
    url = "https://www.linkedin.com/oauth/v2/accessToken"
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": os.getenv("LINKEDIN_CLIENT_ID"),
        "client_secret": os.getenv("LINKEDIN_CLIENT_SECRET"),
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    response = requests.post(url, data=data, headers=headers, timeout=_REQUEST_TIMEOUT)
    response.raise_for_status()
    logger.info(f"LinkedIn token refresh response: {response.status_code}")
    response_json = response.json()
    access_token = response_json.get("access_token")
    if not access_token:
        raise ValueError("No se encontró 'access_token' en la respuesta.")
    return (access_token, response_json.get("refresh_token"))


def refresh_linkedin_sales_token(refresh_token: str) -> Tuple[str, Optional[str]]:
    url = "https://www.linkedin.com/oauth/v2/accessToken"
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": os.getenv("LINKEDIN_SALES_CLIENT_ID"),
        "client_secret": os.getenv("LINKEDIN_SALES_CLIENT_SECRET"),
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    response = requests.post(url, data=data, headers=headers, timeout=_REQUEST_TIMEOUT)
    response.raise_for_status()
    logger.info(f"LinkedIn Sales token refresh response: {response.status_code}")
    response_json = response.json()
    access_token = response_json.get("access_token")
    if not access_token:
        raise ValueError("No se encontró 'access_token' en la respuesta.")
    return (access_token, response_json.get("refresh_token"))


def refresh_monday_token(refresh_token: str) -> Tuple[str, Optional[str]]:
    url = "https://auth.monday.com/oauth2/token"
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": os.getenv("MONDAY_CLIENT_ID"),
        "client_secret": os.getenv("MONDAY_CLIENT_SECRET"),
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    response = requests.post(url, data=data, headers=headers, timeout=_REQUEST_TIMEOUT)
    response.raise_for_status()
    logger.info(f"Monday token refresh response: {response.status_code}")
    response_json = response.json()
    access_token = response_json.get("access_token")
    if not access_token:
        raise ValueError("No se encontró 'access_token' en la respuesta.")
    return (access_token, response_json.get("refresh_token"))


def refresh_salesforce_token(refresh_token: str) -> Tuple[str, Optional[str]]:
    url = "https://login.salesforce.com/services/oauth2/token"
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": os.getenv("SALESFORCE_CLIENT_ID"),
        "client_secret": os.getenv("SALESFORCE_CLIENT_SECRET"),
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    response = requests.post(url, data=data, headers=headers, timeout=_REQUEST_TIMEOUT)
    response.raise_for_status()
    logger.info(f"Salesforce token refresh response: {response.status_code}")
    response_json = response.json()
    access_token = response_json.get("access_token")
    if not access_token:
        raise ValueError("No se encontró 'access_token' en la respuesta.")
    return (access_token, response_json.get("refresh_token"))


def refresh_whatsapp_token(refresh_token: str) -> Tuple[str, Optional[str]]:
    url = "https://graph.facebook.com/v20.0/oauth/access_token"
    data = {
        "grant_type": "fb_exchange_token",
        "fb_exchange_token": refresh_token,
        "client_id": os.getenv("WHATSAPP_CLIENT_ID"),
        "client_secret": os.getenv("WHATSAPP_CLIENT_SECRET"),
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    response = requests.post(url, data=data, headers=headers, timeout=_REQUEST_TIMEOUT)
    response.raise_for_status()
    logger.info(f"WhatsApp token refresh response: {response.status_code}")
    access_token = response.json().get("access_token")
    if not access_token:
        raise ValueError("No se encontró 'access_token' en la respuesta.")
    return (access_token, None)


async def refresh_tokens(
    db_conn,
    redis,
    integrations: Dict[str, str],
    user_email: str,
    integration_name: Optional[str] = None,
) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Itera y refresca los tokens, persistiendo automáticamente las actualizaciones."""
    refreshed_tokens = {}
    errors = {}
    target_integrations = (
        {integration_name: integrations[integration_name]}
        if integration_name
        else integrations
    )
    supported_integrations = [
        "Gmail",
        "Dropbox",
        "Asana",
        "HubSpot",
        "Drive",
        "Outlook",
        "OneDrive",
        "Discord",
        "Facebook",
        "Instagram",
        "Jira",
        "LinkedIn",
        "LinkedIn Sales",
        "Monday",
        "Salesforce",
        "Teams",
        "WhatsApp",
        "Google Docs",
        "Google Sheets",
        "Google Slides",
    ]
    google_integrations = [
        "Gmail",
        "Drive",
        "Google Docs",
        "Google Sheets",
        "Google Slides",
    ]
    microsoft_integrations = ["Outlook", "OneDrive", "Teams"]
    if "Gmail" in integrations and (
        integration_name is None or integration_name in google_integrations
    ):
        try:
            logger.info("Refrescando token para Google APIs usando Gmail refresh_token")
            new_access_token = refresh_gmail_token(integrations["Gmail"])
            for google_service in google_integrations:
                if google_service in integrations:
                    await save_access_token_to_db(
                        db_conn, redis, user_email, google_service, new_access_token
                    )
                    refreshed_tokens[google_service] = new_access_token
            if integration_name in google_integrations:
                return (refreshed_tokens, errors)
        except Exception as e:
            for google_service in google_integrations:
                if google_service in integrations:
                    errors[google_service] = str(e)
            logger.error(f"Error al refrescar token de Google: {e}")
            if integration_name in google_integrations:
                return (refreshed_tokens, errors)
    if "Outlook" in integrations and (
        integration_name is None or integration_name in microsoft_integrations
    ):
        try:
            logger.info(
                "Refrescando token para Microsoft APIs usando Outlook refresh_token"
            )
            new_access_token, new_refresh_token = refresh_outlook_token(
                integrations["Outlook"]
            )
            for ms_service in microsoft_integrations:
                if ms_service in integrations:
                    await save_access_token_to_db(
                        db_conn,
                        redis,
                        user_email,
                        ms_service,
                        new_access_token,
                        new_refresh_token,
                    )
                    refreshed_tokens[ms_service] = new_access_token
            if integration_name in microsoft_integrations:
                return (refreshed_tokens, errors)
        except Exception as e:
            for ms_service in microsoft_integrations:
                if ms_service in integrations:
                    errors[ms_service] = str(e)
            logger.error(f"Error al refrescar token de Microsoft: {e}")
            if integration_name in microsoft_integrations:
                return (refreshed_tokens, errors)
    for name, refresh_token in target_integrations.items():
        if name not in supported_integrations:
            continue
        if name in google_integrations or name in microsoft_integrations:
            continue
        try:
            logger.info(f"Intentando refrescar token para {name}")
            new_access_token = None
            new_refresh_token = None
            if name == "Dropbox":
                new_access_token = refresh_dropbox_token(refresh_token)
            elif name == "Asana":
                new_access_token = refresh_asana_token(refresh_token)
            elif name == "HubSpot":
                new_access_token, new_refresh_token = refresh_hubspot_token(
                    refresh_token
                )
            elif name == "Discord":
                new_access_token, new_refresh_token = refresh_discord_token(
                    refresh_token
                )
            elif name == "Facebook":
                new_access_token, new_refresh_token = refresh_facebook_token(
                    refresh_token
                )
            elif name == "Instagram":
                new_access_token, new_refresh_token = refresh_instagram_token(
                    refresh_token
                )
            elif name == "Jira":
                new_access_token, new_refresh_token = refresh_jira_token(refresh_token)
            elif name == "LinkedIn":
                new_access_token, new_refresh_token = refresh_linkedin_token(
                    refresh_token
                )
            elif name == "LinkedIn Sales":
                new_access_token, new_refresh_token = refresh_linkedin_sales_token(
                    refresh_token
                )
            elif name == "Monday":
                new_access_token, new_refresh_token = refresh_monday_token(
                    refresh_token
                )
            elif name == "Salesforce":
                new_access_token, new_refresh_token = refresh_salesforce_token(
                    refresh_token
                )
            elif name == "WhatsApp":
                new_access_token, new_refresh_token = refresh_whatsapp_token(
                    refresh_token
                )
            if new_access_token:
                await save_access_token_to_db(
                    db_conn,
                    redis,
                    user_email,
                    name,
                    new_access_token,
                    new_refresh_token,
                )
                refreshed_tokens[name] = new_access_token
            else:
                errors[name] = "No se obtuvo nuevo token"
        except Exception as e:
            errors[name] = str(e)
            logger.error(f"Error al refrescar token de {name}: {e}")
    return (refreshed_tokens, errors)


async def get_valid_access_token(
    db, redis, user_email: str, integration_name: str
) -> str:
    """Verifica si el token es válido; de lo contrario, fuerza el refresco."""
    integrations = await get_user_vault_with_fallback(user_email, db)
    if not integrations or integration_name not in integrations:
        raise ValueError(
            f"No se encontró integración {integration_name} para {user_email}"
        )
    integration = integrations[integration_name]
    access_token = integration.get("token")
    timestamp = integration.get("timestamp")
    expires_in = 1800 if integration_name == "HubSpot" else 3600
    if not access_token or is_token_expired(timestamp, expires_in=expires_in):
        logger.info(
            f"Token de {integration_name} expirado o próximo a expirar, forzando refresco"
        )
        all_refresh_tokens = await get_refresh_tokens_from_db(
            user_email=user_email, db_conn=db
        )
        if integration_name not in all_refresh_tokens:
            raise ValueError(f"No se encontró refresh_token para {integration_name}")
        refreshed_tokens, errors = await refresh_tokens(
            db_conn=db,
            redis=redis,
            integrations=all_refresh_tokens,
            user_email=user_email,
            integration_name=integration_name,
        )
        if not refreshed_tokens.get(integration_name):
            raise ValueError(
                f"No se pudo refrescar token para {integration_name}: {errors}"
            )
        access_token = refreshed_tokens[integration_name]
    return access_token


@router.post("/refresh_tokens", response_model=RefreshTokenResponse)
async def refresh_tokens_endpoint(body: RefreshTokenRequest, db=Depends(get_db)):
    try:
        user_email = body.userEmail
        integration_name = body.integrationName
        integrations = await get_refresh_tokens_from_db(
            user_email=user_email, db_conn=db
        )
        if not integrations:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No se encontraron refresh tokens para este usuario",
            )
        refreshed_tokens, errors = await refresh_tokens(
            db_conn=db,
            redis=None,
            integrations=integrations,
            user_email=user_email,
            integration_name=integration_name,
        )
        if errors and (not refreshed_tokens):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Fallaron todas las actualizaciones",
            )
        return RefreshTokenResponse(
            success=True,
            refreshedTokens=refreshed_tokens,
            errors=errors if errors else None,
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al refrescar los tokens: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al refrescar los tokens",
        )


@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "token-refresh",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
