from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, model_validator
import logging
from app.database import get_db
from app.core.constants import Collections
from app.core.db_utils import canonicalize_email

logger = logging.getLogger("gmail.disable_webhook")
router = APIRouter()


class DisableWebhookRequest(BaseModel):
    user_email: EmailStr

    @model_validator(mode="before")
    def accept_email_aliases(cls, values: dict) -> dict:
        if not isinstance(values, dict):
            return values
        # accept camelCase, snake_case and spanish aliases
        if "userEmail" in values and (not values.get("user_email")):
            values["user_email"] = values.get("userEmail")
        if "email" in values and (not values.get("user_email")):
            values["user_email"] = values.get("email")
        if "correo" in values and (not values.get("user_email")):
            values["user_email"] = values.get("correo")
        return values


@router.delete("/watch")
async def disable_gmail_watch(payload: DisableWebhookRequest, db=Depends(get_db)):
    try:
        email_safe = canonicalize_email(payload.user_email)
        logger.info(f"Desactivando webhook para: {email_safe}")
        result_vault = await db[Collections.OAUTH_VAULT].update_one(
            {"$or": [{"correo": email_safe}, {"email": email_safe}]},
            {"$set": {"integrations.Gmail.webhook_langchain_gmail": False}},
        )
        result_legacy = await db[Collections.USERS].update_one(
            {"$or": [{"correo": email_safe}, {"email": email_safe}]},
            {"$set": {"integrations.Gmail.webhook_langchain_gmail": False}},
        )
        if result_vault.matched_count == 0 and result_legacy.matched_count == 0:
            raise HTTPException(
                status_code=404,
                detail="Usuario no encontrado en los registros de integración",
            )
        modificados = result_vault.modified_count + result_legacy.modified_count
        return {
            "status": "ok",
            "message": (
                "Webhook desactivado" if modificados > 0 else "Ya estaba desactivado"
            ),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al desactivar webhook: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error al desactivar webhook")


def setup_disable_gmail_watch(app, mongo, cache, refresh_functions):
    """Stub de compatibilidad legacy para Flask."""
    logger.debug("setup_disable_gmail_watch invocado (modo compatibilidad)")
    return {"disable_gmail_watch": None}
