"""
/api/v1/connectors — Custom connector requests (ShifuConnectorModal).

v1 scope (ladder ponytail): persist the request so it's tracked and visible to the team.
Does NOT build the connector via AI — that's a separate, larger feature. No WS status
updates are emitted (no pipeline exists yet to drive them); the frontend shows a fixed
"analyzing" state after submit.

Router is mounted with prefix "/api/v1/connectors" in main.py; paths below are relative
to that.

Endpoints:
  POST /custom-request — Request a custom connector built by Shifu for an unsupported service
"""

import logging
import os
from datetime import datetime, timezone
from email.message import EmailMessage

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.constants import Collections
from app.database import get_current_user
from app.utils.mail import _send_email_message, validate_smtp_config

logger = logging.getLogger(__name__)
router = APIRouter()


def _notify_team_of_custom_connector_request(name: str, description: str, user_email: str) -> None:
    """Best-effort internal notification. Never raises — email delivery is not required
    for the request to be considered successfully persisted."""
    try:
        validate_smtp_config()
        from_email = os.getenv("SMTP_FROM_EMAIL", "")
        to_email = os.getenv("CONTACT_TO_EMAIL") or from_email
        msg = EmailMessage()
        msg["Subject"] = f"🔌 Nueva solicitud de conector personalizado: {name}"
        msg["From"] = f"Shifu Conectores <{from_email}>"
        msg["To"] = to_email
        if user_email:
            msg["Reply-To"] = user_email
        msg.set_content(
            "Se recibió una nueva solicitud de conector personalizado desde el dashboard.\n\n"
            f"🔧 Servicio: {name}\n"
            f"👤 Usuario: {user_email or 'desconocido'}\n\n"
            f"💬 Descripción:\n{description}\n"
        )
        _send_email_message(msg)
    except Exception:
        logger.warning("No se pudo enviar la notificación interna de conector personalizado.", exc_info=True)


class CustomConnectorRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1, max_length=4000)


@router.post("/custom-request", status_code=202)
async def request_custom_connector(
    body: CustomConnectorRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    """
    Persists a request from ShifuConnectorModal to build a custom connector.
    v1: no automated build pipeline — this only records the request and (best-effort)
    notifies the team by email. Status is always "analyzing"; there is no follow-up
    status transition in this version.
    """
    user_id = current_user.get("id", "")
    user_email = current_user.get("email") or current_user.get("correo", "")
    db = request.app.state.db

    doc = {
        "user_id": user_id,
        "name": body.name.strip(),
        "description": body.description.strip(),
        "status": "analyzing",
        "created_at": datetime.now(timezone.utc),
    }
    result = await db[Collections.CUSTOM_CONNECTOR_REQUESTS].insert_one(doc)

    background_tasks.add_task(
        _notify_team_of_custom_connector_request, doc["name"], doc["description"], user_email
    )

    return JSONResponse(
        status_code=202,
        content=jsonable_encoder({"request_id": str(result.inserted_id), "status": "analyzing"}),
    )
