"""
Google OAuth 2.0 — Servicios independientes
Cada servicio tiene su propio /login con scopes acotados.
Un único /callback compartido maneja todos (una sola redirect URI en Google Cloud).

Endpoints:
  GET /auth/google/gmail/login
  GET /auth/google/drive/login
  GET /auth/google/docs/login
  GET /auth/google/sheets/login
  GET /auth/google/slides/login
  GET /auth/google/calendar/login
  GET /auth/google/callback          ← compartido por todos
"""
import os
import jwt
import secrets
import logging
import httpx
import urllib.parse
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from app.database import get_current_user, get_db, SECRET_KEY
from app.core.constants import Collections

try:
    from app.core.security import encrypt_data
except ImportError:
    encrypt_data = lambda x: x  # noqa: E731

logger = logging.getLogger("auth.google")
router = APIRouter()

CLIENT_ID = os.getenv("DRIVE_CLIENT_ID")
CLIENT_SECRET = os.getenv("DRIVE_CLIENT_SECRET")
REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")
FRONTEND_REDIRECT_URL = os.getenv("FRONTEND_REDIRECT_URL", "https://hypershifu.com/chat")

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

# Scopes base siempre incluidos (identifican al usuario)
BASE_SCOPES = ["openid", "email", "profile"]

# Scopes específicos por servicio
SERVICE_SCOPES = {
    "gmail": [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.modify",
    ],
    "drive": [
        "https://www.googleapis.com/auth/drive",
    ],
    "docs": [
        "https://www.googleapis.com/auth/documents",
    ],
    "sheets": [
        "https://www.googleapis.com/auth/spreadsheets",
    ],
    "slides": [
        "https://www.googleapis.com/auth/presentations",
    ],
    "calendar": [
        "https://www.googleapis.com/auth/calendar",
        "https://www.googleapis.com/auth/calendar.events",
    ],
}

# Nombre del provider guardado en BD por servicio
PROVIDER_NAME = {
    "gmail":    "gmail",
    "drive":    "google_drive",
    "docs":     "google_docs",
    "sheets":   "google_sheets",
    "slides":   "google_slides",
    "calendar": "google_calendar",
}


def _build_login_url(user: dict, service: str) -> str:
    """Genera la URL de consentimiento de Google para el servicio indicado."""
    user_id = str(user.get("_id") or user.get("id", ""))
    email = user.get("email") or user.get("correo", "")

    scopes = BASE_SCOPES + SERVICE_SCOPES[service]

    state = jwt.encode(
        {
            "u": user_id,
            "email": email,
            "service": service,
            "nonce": secrets.token_urlsafe(16),
            "exp": datetime.now(timezone.utc).timestamp() + 600,
        },
        SECRET_KEY,
        algorithm="HS256",
    )

    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": " ".join(scopes),
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    }

    return f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"


def _check_config():
    if not CLIENT_ID or not REDIRECT_URI:
        raise HTTPException(status_code=503, detail="Google OAuth no configurado en el servidor")


def _check_user(user: dict):
    user_id = str(user.get("_id") or user.get("id", ""))
    email = user.get("email") or user.get("correo", "")
    if not user_id or not email:
        raise HTTPException(status_code=401, detail="Usuario inválido o sin correo")


# ---------------------------------------------------------------------------
# Login endpoints — uno por servicio
# ---------------------------------------------------------------------------

@router.get("/gmail/login")
async def gmail_login(user: dict = Depends(get_current_user)):
    """Inicia el flujo OAuth solo para Gmail."""
    _check_config()
    _check_user(user)
    return JSONResponse({"url": _build_login_url(user, "gmail")})


@router.get("/drive/login")
async def drive_login(user: dict = Depends(get_current_user)):
    """Inicia el flujo OAuth solo para Google Drive."""
    _check_config()
    _check_user(user)
    return JSONResponse({"url": _build_login_url(user, "drive")})


@router.get("/docs/login")
async def docs_login(user: dict = Depends(get_current_user)):
    """Inicia el flujo OAuth solo para Google Docs."""
    _check_config()
    _check_user(user)
    return JSONResponse({"url": _build_login_url(user, "docs")})


@router.get("/sheets/login")
async def sheets_login(user: dict = Depends(get_current_user)):
    """Inicia el flujo OAuth solo para Google Sheets."""
    _check_config()
    _check_user(user)
    return JSONResponse({"url": _build_login_url(user, "sheets")})


@router.get("/slides/login")
async def slides_login(user: dict = Depends(get_current_user)):
    """Inicia el flujo OAuth solo para Google Slides."""
    _check_config()
    _check_user(user)
    return JSONResponse({"url": _build_login_url(user, "slides")})


@router.get("/calendar/login")
async def calendar_login(user: dict = Depends(get_current_user)):
    """Inicia el flujo OAuth solo para Google Calendar."""
    _check_config()
    _check_user(user)
    return JSONResponse({"url": _build_login_url(user, "calendar")})


# ---------------------------------------------------------------------------
# Callback compartido — Google siempre redirige aquí
# ---------------------------------------------------------------------------

@router.get("/callback")
async def callback(request: Request, db=Depends(get_db)):
    """
    Callback compartido para todos los servicios Google.
    El servicio se recupera del state JWT, no de la URL.
    """
    code = request.query_params.get("code")
    state_jwt = request.query_params.get("state")
    error = request.query_params.get("error")

    if error:
        logger.warning("Google Auth denegado: %s", error)
        return RedirectResponse(f"{FRONTEND_REDIRECT_URL}?error={error}")

    if not code or not state_jwt:
        return RedirectResponse(f"{FRONTEND_REDIRECT_URL}?error=missing_parameters")

    # 1. Validar state JWT y extraer servicio
    try:
        payload = jwt.decode(state_jwt, SECRET_KEY, algorithms=["HS256"])
        user_id = payload.get("u")
        system_email = payload.get("email")
        service = payload.get("service")
    except jwt.ExpiredSignatureError:
        logger.warning("Google callback: state JWT expirado")
        return RedirectResponse(f"{FRONTEND_REDIRECT_URL}?error=session_expired")
    except Exception as exc:
        logger.warning("Google callback: state JWT inválido — %s", exc)
        return RedirectResponse(f"{FRONTEND_REDIRECT_URL}?error=session_lost")

    if not user_id or service not in SERVICE_SCOPES:
        return RedirectResponse(f"{FRONTEND_REDIRECT_URL}?error=session_lost")

    # 2. Intercambiar code por tokens
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            token_resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                    "redirect_uri": REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
            )
            token_resp.raise_for_status()
            token_data = token_resp.json()
    except httpx.HTTPStatusError as exc:
        logger.error("Google token exchange error %s: %s", exc.response.status_code, exc.response.text)
        return RedirectResponse(f"{FRONTEND_REDIRECT_URL}?error=token_exchange_failed")
    except Exception as exc:
        logger.error("Google token exchange network error: %s", exc)
        return RedirectResponse(f"{FRONTEND_REDIRECT_URL}?error=token_exchange_network_error")

    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    expires_in = token_data.get("expires_in", 3600)

    if not access_token:
        logger.error("Google no devolvió access_token para servicio=%s: %s", service, token_data)
        return RedirectResponse(f"{FRONTEND_REDIRECT_URL}?error=token_exchange_failed")

    # 3. Obtener email real de Google via userinfo
    google_email = system_email
    google_name = ""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            info_resp = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if info_resp.status_code == 200:
                info = info_resp.json()
                google_email = info.get("email", system_email)
                google_name = info.get("name", "")
    except Exception as exc:
        logger.warning("No se pudo obtener userinfo de Google: %s", exc)

    # 4. Guardar tokens encriptados con provider específico del servicio
    provider = PROVIDER_NAME[service]
    now_utc = datetime.now(timezone.utc)
    doc = {
        "user_id": str(user_id),
        "provider": provider,
        "account_id": google_email,
        "access_token": encrypt_data(access_token),
        "refresh_token": encrypt_data(refresh_token) if refresh_token else "n/a",
        "expires_in": expires_in,
        "status": "active",
        "timestamp": now_utc.strftime("%Y-%m-%d %H:%M:%S"),
        "metadata": {
            "email": google_email,
            "name": google_name,
            "service": service,
            "scopes": BASE_SCOPES + SERVICE_SCOPES[service],
            "connected_at": now_utc.isoformat(),
        },
    }

    try:
        await db[Collections.USER_CONNECTED_ACCOUNTS].update_one(
            {"user_id": str(user_id), "provider": provider, "account_id": google_email},
            {"$set": doc},
            upsert=True,
        )
        logger.info("Google %s guardado para user_id=%s email=%s", service, user_id, google_email)
    except Exception as exc:
        logger.error("Error DB guardando Google %s para %s: %s", service, google_email, exc)
        return RedirectResponse(f"{FRONTEND_REDIRECT_URL}?error=database_error")

    account_encoded = urllib.parse.quote(google_email)
    return RedirectResponse(
        f"{FRONTEND_REDIRECT_URL}?{service}_status=connected&account={account_encoded}"
    )


@router.get("/status")
def status():
    return JSONResponse({"connected": True})


@router.delete("")
def disconnect():
    return JSONResponse({"success": True})
