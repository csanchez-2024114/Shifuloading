import logging
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field, model_validator
from app.core.limiter import limiter
from app.utils.mail import send_contact_email, validate_smtp_config

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Contact"])


class ContactRequest(BaseModel):
    name: str = Field(
        ..., min_length=2, max_length=120, description="Nombre del remitente"
    )
    email: EmailStr = Field(..., description="Correo electrónico válido")
    message: str = Field(
        ..., min_length=5, max_length=4000, description="Cuerpo del mensaje"
    )

    @model_validator(mode="before")
    def accept_spanish_email_alias(cls, values: dict) -> dict:
        if not isinstance(values, dict):
            return values
        if "correo" in values and (not values.get("email")):
            values["email"] = values.get("correo")
        if "userEmail" in values and (not values.get("email")):
            values["email"] = values.get("userEmail")
        if "user_email" in values and (not values.get("email")):
            values["email"] = values.get("user_email")
        return values


@router.post("/", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("3/minute")
async def contact(
    request: Request, payload: ContactRequest, background_tasks: BackgroundTasks
):
    """
    Recibe mensajes del formulario de contacto y los procesa de forma asíncrona.
    """
    try:
        validate_smtp_config()
    except ValueError as e:
        logger.error(f"Error crítico en SMTP de Contacto: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="El servicio de correo no está configurado temporalmente.",
        )
    background_tasks.add_task(
        send_contact_email, payload.name, payload.email, payload.message
    )
    logger.info(
        f"Formulario de contacto procesado y encolado. Remitente: {payload.email}"
    )
    return {"success": True, "message": "Mensaje encolado correctamente."}