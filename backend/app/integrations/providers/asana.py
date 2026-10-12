import os
import jwt
import secrets
import logging
import requests
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import RedirectResponse
from app.database import get_current_user, get_db, SECRET_KEY
from app.core.constants import Collections

try:
    from app.core.security import encrypt_data
except ImportError:
    logger = logging.getLogger(__name__)
    logger.warning("Módulo de encriptación no encontrado. Se usará texto plano (MODO DEV).")
    encrypt_data = lambda x: x

logger = logging.getLogger("auth.asana")
router = APIRouter()

ASANA_CLIENT_ID     = os.getenv("ASANA_CLIENT_ID")
ASANA_CLIENT_SECRET = os.getenv("ASANA_CLIENT_SECRET")
ASANA_REDIRECT_URI  = os.getenv("ASANA_REDIRECT_URI")
FRONTEND_REDIRECT_URL = os.getenv("FRONTEND_REDIRECT_URL", "https://hypershifu.com/chat")

ASANA_AUTH_URL  = "https://app.asana.com/-/oauth_authorize"
ASANA_TOKEN_URL = "https://app.asana.com/-/oauth_token"


@router.get("/login")
async def login(user: dict = Depends(get_current_user)):
    user_id = str(user.get("_id", user.get("id", "")))
    correo  = user.get("correo") or user.get("email", "")
    if not user_id or not correo:
        raise HTTPException(status_code=401, detail="Usuario inválido o sin correo")

    nonce = secrets.token_urlsafe(32)
    state = jwt.encode(
        {"nonce": nonce, "user_id": user_id, "correo": correo},
        SECRET_KEY,
        algorithm="HS256",
    )
    auth_url = (
        f"{ASANA_AUTH_URL}"
        f"?client_id={ASANA_CLIENT_ID}"
        f"&redirect_uri={ASANA_REDIRECT_URI}"
        f"&response_type=code"
        f"&state={state}"
    )
    return {"url": auth_url}


@router.get("/callback")
async def callback(request: Request, db=Depends(get_db)):
    try:
        state_jwt = request.query_params.get("state")
        code      = request.query_params.get("code")
        error     = request.query_params.get("error")

        if error:
            logger.warning("Asana Auth Error: %s", error)
            return RedirectResponse(f"{FRONTEND_REDIRECT_URL}?error={error}")

        user_id = correo = None
        if state_jwt:
            try:
                payload = jwt.decode(state_jwt, SECRET_KEY, algorithms=["HS256"])
                user_id = payload.get("user_id")
                correo  = payload.get("correo")
            except Exception as exc:
                logger.error("Error decodificando state JWT: %s", exc)

        if not user_id or not correo:
            return RedirectResponse(f"{FRONTEND_REDIRECT_URL}?error=session_lost")

        token_res = requests.post(
            ASANA_TOKEN_URL,
            data={
                "grant_type":    "authorization_code",
                "client_id":     ASANA_CLIENT_ID,
                "client_secret": ASANA_CLIENT_SECRET,
                "redirect_uri":  ASANA_REDIRECT_URI,
                "code":          code,
            },
        ).json()

        if "error" in token_res or "access_token" not in token_res:
            logger.error("Asana Token Error: %s", token_res)
            return RedirectResponse(f"{FRONTEND_REDIRECT_URL}?error=token_exchange_failed")

        access_token  = token_res.get("access_token")
        refresh_token = token_res.get("refresh_token", "n/a")
        expires_in    = token_res.get("expires_in", 3600)

        # Asana includes user data in the token response under "data"
        asana_user = token_res.get("data", {})
        account_id = str(asana_user.get("gid", ""))
        email      = asana_user.get("email", correo)
        name       = asana_user.get("name", "")

        encrypted_token   = encrypt_data(access_token)  if access_token  else None
        encrypted_refresh = encrypt_data(refresh_token) if refresh_token and refresh_token != "n/a" else "n/a"

        now_utc = datetime.now(timezone.utc)
        doc = {
            "user_id":       str(user_id),
            "provider":      "asana",
            "account_id":    account_id,
            "email":         email.strip().lower(),
            "access_token":  encrypted_token,
            "refresh_token": encrypted_refresh,
            "expires_in":    expires_in,
            "status":        "active",
            "timestamp":     now_utc.strftime("%Y-%m-%d %H:%M:%S"),
            "metadata": {
                "name":         name,
                "asana_gid":    account_id,
                "connected_at": now_utc.isoformat(),
            },
        }

        try:
            await db[Collections.USER_CONNECTED_ACCOUNTS].update_one(
                {"user_id": str(user_id), "provider": "asana", "account_id": account_id},
                {"$set": doc, "$setOnInsert": {"created_at": now_utc}},
                upsert=True,
            )
        except Exception as exc:
            logger.error("Error DB guardando Asana para %s: %s", correo, exc, exc_info=True)
            return RedirectResponse(f"{FRONTEND_REDIRECT_URL}?error=database_error")

        logger.info("✅ Asana conectado para %s (gid=%s)", correo, account_id)
        return RedirectResponse(f"{FRONTEND_REDIRECT_URL}?asana_status=connected")

    except Exception as exc:
        logger.error("ASANA FATAL ERROR: %s", exc, exc_info=True)
        return RedirectResponse(f"{FRONTEND_REDIRECT_URL}?error=internal_server_error")


@router.get("/status")
def status():
    return {"connected": True}


@router.delete("")
def disconnect():
    return {"success": True}


# ── Service Layer ──────────────────────────────────────────────────────────────
import logging
from typing import Dict, Any, Optional
from dotenv import load_dotenv
from app.core.mongo import get_sync_database
from app.core.constants import Collections
from app.core.db_utils import canonicalize_email
load_dotenv()
logger = logging.getLogger(__name__)

def _get_db():
    return get_sync_database()

def get_asana_creds_for_langchain(email: str) -> Dict[str, Any]:
    """
    Recupera las credenciales de Asana del usuario desde la bóveda de seguridad.
    """
    try:
        db = _get_db()
        email_safe = canonicalize_email(email)
        vault_data = db[Collections.OAUTH_VAULT].find_one({'$or': [{'correo': email_safe}, {'email': email_safe}]})
        asana_creds: Optional[Dict[str, Any]] = None
        if vault_data:
            asana_creds = vault_data.get('integrations', {}).get('Asana') or vault_data.get('Asana')
        if asana_creds:
            return {'access_token': asana_creds.get('token'), 'refresh_token': asana_creds.get('refresh_token'), 'expires_in': asana_creds.get('expires_in'), 'timestamp': asana_creds.get('timestamp')}
        logger.warning(f'No se encontraron credenciales de Asana en oauth_vault para el usuario proporcionado.')
        return {'error': 'No encontré credenciales de Asana'}
    except Exception as e:
        logger.exception('Error de conexión o lectura en oauth_vault al consultar Asana')
        return {'error': 'Error interno al consultar las credenciales'}
if __name__ == '__main__':
    import sys
    correo_test = 'steven.undefined@gmail.com'
    creds = get_asana_creds_for_langchain(correo_test)
    print(' Resultado de la búsqueda:')
    if 'error' in creds:
        print(f" Error: {creds['error']}")
    else:
        print('✅ Credenciales encontradas en oauth_vault!')
        print(f'   Access Token: [OCULTO POR SEGURIDAD]')
        print(f'   Refresh Token: [OCULTO POR SEGURIDAD]')
        print(f"   Expires In: {creds.get('expires_in', 'N/A')} segundos")

