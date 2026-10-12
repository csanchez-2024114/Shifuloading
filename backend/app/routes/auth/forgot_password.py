import os
import secrets
import logging
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field, model_validator
from passlib.context import CryptContext
from app.core.limiter import limiter
from app.utils.mail import send_password_reset_email, validate_smtp_config
from app.core.constants import Collections
from app.core.db_utils import canonicalize_email

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Auth"])
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
RESET_TOKEN_TTL_HOURS = 1


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=32)
    new_password: str = Field(..., min_length=8)


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("3/minute")
async def forgot_password(
    request: Request, payload: ForgotPasswordRequest, background_tasks: BackgroundTasks
):
    """
    Recibe un email y, si el usuario existe, envía un enlace de recuperación.
    Siempre responde 202 para evitar enumeración de usuarios.
    """
    try:
        validate_smtp_config()
    except ValueError as e:
        logger.error(f"Configuración SMTP inválida: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="El servicio de correo no está disponible temporalmente.",
        )
    mongo = request.app.state.db
    email_clean = canonicalize_email(payload.email)
    user = await mongo[Collections.OAUTH_VAULT].find_one({"email": email_clean})
    if not user:
        user = await mongo[Collections.USERS].find_one({"email": email_clean})
    if not user:
        return {
            "success": True,
            "message": "Si el correo existe, recibirás instrucciones en breve.",
        }
    reset_token = secrets.token_urlsafe(48)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=RESET_TOKEN_TTL_HOURS)
    await mongo.password_resets.update_one(
        {"email": email_clean, "used": False},
        {
            "$set": {
                "email": email_clean,
                "token": reset_token,
                "expires_at": expires_at,
                "used": False,
                "created_at": datetime.now(timezone.utc),
            }
        },
        upsert=True,
    )
    frontend_url = os.getenv("FRONTEND_URL", "https://hypershifu.com").rstrip("/")
    reset_link = f"{frontend_url}/reset-password?token={reset_token}"
    background_tasks.add_task(send_password_reset_email, email_clean, reset_link)
    logger.info(f"Solicitud de recuperación de contraseña para: {email_clean}")
    return {
        "success": True,
        "message": "Si el correo existe, recibirás instrucciones en breve.",
    }


@router.post("/reset-password", status_code=status.HTTP_200_OK)
@limiter.limit("5/minute")
async def reset_password(request: Request, payload: ResetPasswordRequest):
    """
    Valida el token de recuperación y actualiza la contraseña del usuario.
    """
    mongo = request.app.state.db
    now = datetime.now(timezone.utc)
    reset_doc = await mongo.password_resets.find_one(
        {"token": payload.token, "used": False}
    )
    if not reset_doc:
        raise HTTPException(status_code=400, detail="Token inválido o ya utilizado.")
    expires_at = reset_doc["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if now > expires_at:
        raise HTTPException(
            status_code=400, detail="El enlace de recuperación ha expirado."
        )
    email = reset_doc["email"]
    new_hash = pwd_context.hash(payload.new_password)
    update_token = await mongo[Collections.PASSWORD_RESETS].update_one(
        {"_id": reset_doc["_id"], "used": False},
        {"$set": {"used": True, "used_at": now}},
    )
    if update_token.modified_count == 0:
        raise HTTPException(status_code=400, detail="El token ya fue procesado.")
    result = await mongo[Collections.OAUTH_VAULT].update_one(
        {"email": email}, {"$set": {"password": new_hash}}
    )
    if result.matched_count == 0:
        await mongo[Collections.USERS].update_one(
            {"email": email},
            {"$set": {"password": new_hash}},
        )
    logger.info(f"Contraseña actualizada correctamente para: {email}")
    return {"success": True, "message": "Contraseña actualizada correctamente."}
