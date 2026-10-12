"""
Onboarding — Módulo independiente de auth y agentes.
Gestiona el ciclo de vida inicial del usuario: perfil → objetivo → caso de uso → workspace.
"""

import logging
import secrets
import string
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from fastapi import APIRouter, Request, Depends, HTTPException, status
from pydantic import BaseModel, Field, HttpUrl
from bson import ObjectId

from app.core.constants import Collections
from app.routes.auth.authRoutes import verify_token

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Pydantic Models ──────────────────────────────────────────────────────────

class AvatarModel(BaseModel):
    avatar_url: str = Field(..., min_length=1)


class GoalModel(BaseModel):
    primary_goal: str = Field(..., min_length=1, max_length=500)
    custom_goal: str = Field(default="", max_length=500)


class UseCaseModel(BaseModel):
    description: str = Field(..., min_length=1, max_length=1000)


# ── Shared helpers ───────────────────────────────────────────────────────────

async def _generate_workspace_invite_code(mongo) -> str:
    """Generates a unique 'SHIFU-XXXXXX' invite code for a new workspace."""
    for _ in range(10):
        code = f"SHIFU-{''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))}"
        if not await mongo[Collections.WORKSPACES].find_one({"invite_code": code}, {"_id": 1}):
            return code
    raise HTTPException(status_code=500, detail="No se pudo generar un código de invitación único.")


async def _advance_step(mongo, user_oid: ObjectId, min_step: int) -> int:
    """Advances current_step to at least min_step. Returns the new step."""
    now = datetime.now(timezone.utc)
    doc = await mongo[Collections.USER_ONBOARDING].find_one_and_update(
        {"user_id": user_oid},
        {
            "$max": {"current_step": min_step},
            "$set": {"updated_at": now},
        },
        upsert=True,
        return_document=True,
    )
    return doc["current_step"] if doc else min_step


# ── Dependency: onboarding must be completed ─────────────────────────────────

async def require_onboarding_completed(
    request: Request,
    payload: Dict[str, Any] = Depends(verify_token),
) -> Dict[str, Any]:
    """Use as Depends() on any endpoint that requires completed onboarding."""
    mongo = request.app.state.db
    user_oid = ObjectId(payload["user_id"])
    doc = await mongo[Collections.USER_ONBOARDING].find_one({"user_id": user_oid})
    if not doc or not doc.get("completed"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Onboarding pendiente. Completa el proceso antes de continuar.",
        )
    return payload


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/status")
async def get_onboarding_status(
    request: Request,
    payload: Dict[str, Any] = Depends(verify_token),
):
    mongo = request.app.state.db
    user_oid = ObjectId(payload["user_id"])
    doc = await mongo[Collections.USER_ONBOARDING].find_one({"user_id": user_oid})
    if not doc:
        return {"current_step": 1, "completed": False}
    return {
        "current_step": doc.get("current_step", 1),
        "completed": doc.get("completed", False),
        "completed_at": doc.get("completed_at"),
    }


@router.post("/avatar")
async def save_avatar(
    request: Request,
    data: AvatarModel,
    payload: Dict[str, Any] = Depends(verify_token),
):
    mongo = request.app.state.db
    user_oid = ObjectId(payload["user_id"])
    now = datetime.now(timezone.utc)

    await mongo[Collections.USER_PROFILES].update_one(
        {"user_id": user_oid},
        {"$set": {"avatar_url": data.avatar_url, "updated_at": now}},
        upsert=True,
    )
    new_step = await _advance_step(mongo, user_oid, min_step=2)
    logger.info("[onboarding] avatar_uploaded user=%s", payload["user_id"])
    return {"success": True, "current_step": new_step}


@router.post("/goal")
async def save_goal(
    request: Request,
    data: GoalModel,
    payload: Dict[str, Any] = Depends(verify_token),
):
    mongo = request.app.state.db
    user_oid = ObjectId(payload["user_id"])
    now = datetime.now(timezone.utc)

    await mongo[Collections.USER_GOALS].update_one(
        {"user_id": user_oid},
        {
            "$set": {
                "primary_goal": data.primary_goal,
                "custom_goal": data.custom_goal,
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    new_step = await _advance_step(mongo, user_oid, min_step=3)
    logger.info("[onboarding] goal_selected user=%s goal=%s", payload["user_id"], data.primary_goal)
    return {"success": True, "current_step": new_step}


@router.post("/use-case")
async def save_use_case(
    request: Request,
    data: UseCaseModel,
    payload: Dict[str, Any] = Depends(verify_token),
):
    mongo = request.app.state.db
    user_oid = ObjectId(payload["user_id"])
    now = datetime.now(timezone.utc)

    await mongo[Collections.USER_USE_CASES].update_one(
        {"user_id": user_oid},
        {
            "$set": {"description": data.description, "updated_at": now},
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    new_step = await _advance_step(mongo, user_oid, min_step=4)
    logger.info("[onboarding] use_case_created user=%s", payload["user_id"])
    return {"success": True, "current_step": new_step}


@router.post("/complete")
async def complete_onboarding(
    request: Request,
    payload: Dict[str, Any] = Depends(verify_token),
):
    mongo = request.app.state.db
    user_oid = ObjectId(payload["user_id"])
    now = datetime.now(timezone.utc)

    onboarding = await mongo[Collections.USER_ONBOARDING].find_one({"user_id": user_oid})
    if not onboarding:
        raise HTTPException(status_code=400, detail="Estado de onboarding no encontrado.")
    if onboarding.get("completed"):
        raise HTTPException(status_code=400, detail="El onboarding ya fue completado.")
    if onboarding.get("current_step", 0) < 4:
        raise HTTPException(
            status_code=400,
            detail=f"Onboarding incompleto. Paso actual: {onboarding.get('current_step', 1)}. Faltan pasos por completar.",
        )

    profile = await mongo[Collections.USER_PROFILES].find_one({"user_id": user_oid})
    if not profile or not profile.get("avatar_url"):
        raise HTTPException(status_code=400, detail="Falta el avatar. Completa el paso de perfil.")

    goals = await mongo[Collections.USER_GOALS].find_one({"user_id": user_oid})
    if not goals:
        raise HTTPException(status_code=400, detail="Falta el objetivo. Completa el paso de motivación.")

    use_case = await mongo[Collections.USER_USE_CASES].find_one({"user_id": user_oid})
    if not use_case:
        raise HTTPException(status_code=400, detail="Falta el caso de uso. Completa ese paso.")

    invite_code = await _generate_workspace_invite_code(mongo)
    workspace_doc = {
        "owner_id": user_oid,
        "workspace_name": "Mi Workspace",
        "invite_code": invite_code,
        "created_at": now,
    }
    res = await mongo[Collections.WORKSPACES].insert_one(workspace_doc)

    await mongo[Collections.USER_ONBOARDING].update_one(
        {"user_id": user_oid},
        {"$set": {"completed": True, "completed_at": now, "current_step": 5, "updated_at": now}},
    )

    logger.info("[onboarding] onboarding_completed user=%s workspace=%s", payload["user_id"], str(res.inserted_id))
    return {"success": True, "workspace_id": str(res.inserted_id)}
