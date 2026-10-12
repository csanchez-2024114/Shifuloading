from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field, model_validator
from typing import Optional, Dict, Any, Literal
from datetime import datetime
from bson import ObjectId
import logging
import string
import random

from app.database import get_db, get_current_user
from app.core.constants import Collections

logger = logging.getLogger(__name__)

# Mounted at /api/v1/rewards — user-facing reward catalog + redemption.
router = APIRouter()
# Mounted at /api/v1/admin — reward/challenge/streak administration.
admin_router = APIRouter()
# Mounted at /api/v1/challenges — user-facing challenge completion.
challenge_router = APIRouter()
# Mounted at /api/v1/reward-streaks — user-facing streak rewards.
streak_router = APIRouter()
# Mounted at /api/v1/me/rewards — own redemption history.
me_router = APIRouter()


class RewardCreate(BaseModel):
    id: str = Field(..., description="ID del admin que crea la recompensa")
    name: str
    description: str
    type: Literal["referral", "challenge", "streak"]
    max_redemptions_per_user: int = 1
    required_referrals: Optional[int] = 0
    active: bool = True
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    challenge_description: Optional[str] = None
    challenge_goal: Optional[str] = None
    challenge_points: Optional[int] = 0

    @model_validator(mode="before")
    def normalize_id_aliases(cls, values: dict) -> dict:
        if not isinstance(values, dict):
            return values
        if "adminId" in values and (not values.get("id")):
            values["id"] = values.get("adminId")
        if "admin_id" in values and (not values.get("id")):
            values["id"] = values.get("admin_id")
        if "userId" in values and (not values.get("id")):
            values["id"] = values.get("userId")
        if "user_id" in values and (not values.get("id")):
            values["id"] = values.get("user_id")
        return values


class RewardUpdate(BaseModel):
    id: str = Field(..., description="ID del admin que actualiza")
    name: Optional[str] = None
    description: Optional[str] = None
    type: Optional[Literal["referral", "challenge", "streak"]] = None
    max_redemptions_per_user: Optional[int] = None
    required_referrals: Optional[int] = None
    active: Optional[bool] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    challenge_description: Optional[str] = None
    challenge_goal: Optional[str] = None
    challenge_points: Optional[int] = None

    @model_validator(mode="before")
    def normalize_id_aliases(cls, values: dict) -> dict:
        if not isinstance(values, dict):
            return values
        if "adminId" in values and (not values.get("id")):
            values["id"] = values.get("adminId")
        if "admin_id" in values and (not values.get("id")):
            values["id"] = values.get("admin_id")
        return values


class ToggleStatusRequest(BaseModel):
    id: str = Field(..., description="ID del admin")

    @model_validator(mode="before")
    def normalize_id_aliases(cls, values: dict) -> dict:
        if not isinstance(values, dict):
            return values
        if "adminId" in values and (not values.get("id")):
            values["id"] = values.get("adminId")
        if "admin_id" in values and (not values.get("id")):
            values["id"] = values.get("admin_id")
        return values


class RedeemRequest(BaseModel):
    id: str = Field(..., description="ID del usuario")
    reward_id: str

    @model_validator(mode="before")
    def normalize_id_aliases(cls, values: dict) -> dict:
        if not isinstance(values, dict):
            return values
        if "userId" in values and (not values.get("id")):
            values["id"] = values.get("userId")
        if "user_id" in values and (not values.get("id")):
            values["id"] = values.get("user_id")
        if "rewardId" in values and (not values.get("reward_id")):
            values["reward_id"] = values.get("rewardId")
        return values


class CompleteChallenge(BaseModel):
    id: str = Field(..., description="ID del usuario")
    evidence: Optional[str] = None

    @model_validator(mode="before")
    def normalize_id_aliases(cls, values: dict) -> dict:
        if not isinstance(values, dict):
            return values
        if "userId" in values and (not values.get("id")):
            values["id"] = values.get("userId")
        if "user_id" in values and (not values.get("id")):
            values["id"] = values.get("user_id")
        return values


class ApproveChallenge(BaseModel):
    id: str = Field(..., description="ID del admin")
    completion_id: str

    @model_validator(mode="before")
    def normalize_id_aliases(cls, values: dict) -> dict:
        if not isinstance(values, dict):
            return values
        if "adminId" in values and (not values.get("id")):
            values["id"] = values.get("adminId")
        if "admin_id" in values and (not values.get("id")):
            values["id"] = values.get("admin_id")
        return values


class RewardStreakCreate(BaseModel):
    id: str = Field(..., description="ID del admin")
    streak_days: int
    reward_type: str
    reward_value: Any
    description: str

    @model_validator(mode="before")
    def normalize_id_aliases(cls, values: dict) -> dict:
        if not isinstance(values, dict):
            return values
        if "adminId" in values and (not values.get("id")):
            values["id"] = values.get("adminId")
        if "admin_id" in values and (not values.get("id")):
            values["id"] = values.get("admin_id")
        return values


class ApplyRewardStreak(BaseModel):
    reward_id: str

    @model_validator(mode="before")
    def normalize_aliases(cls, values: dict) -> dict:
        if not isinstance(values, dict):
            return values
        if "rewardId" in values and (not values.get("reward_id")):
            values["reward_id"] = values.get("rewardId")
        return values


class DeleteRewardRequest(BaseModel):
    id: str = Field(..., description="ID del admin")

    @model_validator(mode="before")
    def normalize_id_aliases(cls, values: dict) -> dict:
        if not isinstance(values, dict):
            return values
        if "adminId" in values and (not values.get("id")):
            values["id"] = values.get("adminId")
        if "admin_id" in values and (not values.get("id")):
            values["id"] = values.get("admin_id")
        return values


async def verify_admin(user_id: str, db) -> Dict[str, Any]:
    """Verifica que el usuario sea admin"""
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="user_id requerido"
        )
    try:
        user = await db[Collections.USERS].find_one({"_id": ObjectId(user_id)})
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="ID de usuario inválido"
        )
    if not user or user.get("rol") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado, no eres admin",
        )
    return user


def serialize_reward(reward: Dict[str, Any]) -> Dict[str, Any]:
    """Serializa una recompensa para respuesta JSON"""
    if not reward:
        return None
    reward["_id"] = str(reward["_id"])
    if "start_date" in reward and isinstance(reward["start_date"], datetime):
        reward["start_date"] = reward["start_date"].isoformat()
    if "end_date" in reward and isinstance(reward["end_date"], datetime):
        reward["end_date"] = reward["end_date"].isoformat()
    if "created_at" in reward and isinstance(reward["created_at"], datetime):
        reward["created_at"] = reward["created_at"].isoformat()
    if "updated_at" in reward and isinstance(reward["updated_at"], datetime):
        reward["updated_at"] = reward["updated_at"].isoformat()
    return reward


# ── Admin: Rewards ──────────────────────────────────────────────────────
# /api/v1/admin/rewards*

@admin_router.post("/rewards", status_code=status.HTTP_201_CREATED)
async def create_reward(body: RewardCreate, db=Depends(get_db)):
    await verify_admin(body.id, db)
    reward = {
        "name": body.name,
        "description": body.description,
        "type": body.type,
        "max_redemptions_per_user": body.max_redemptions_per_user,
        "required_referrals": body.required_referrals if body.type == "referral" else 0,
        "active": body.active,
        "created_at": datetime.utcnow(),
        "start_date": (
            datetime.fromisoformat(body.start_date)
            if body.start_date
            else datetime.utcnow()
        ),
    }
    if body.end_date:
        reward["end_date"] = datetime.fromisoformat(body.end_date)
    if body.type == "challenge":
        reward["challenge_description"] = body.challenge_description or ""
        reward["challenge_goal"] = body.challenge_goal or ""
        reward["challenge_points"] = body.challenge_points or 0
    result = await db.rewards.insert_one(reward)
    reward["_id"] = result.inserted_id
    return serialize_reward(reward)


@admin_router.get("/rewards")
async def get_admin_rewards(id: str, db=Depends(get_db)):
    """Ver todas las recompensas (solo admin)"""
    await verify_admin(id, db)
    rewards = await db.rewards.find().to_list(length=None)
    return [serialize_reward(r) for r in rewards]


@admin_router.put("/rewards/{reward_id}")
async def update_reward(reward_id: str, body: RewardUpdate, db=Depends(get_db)):
    """Editar recompensa (solo admin)"""
    await verify_admin(body.id, db)
    try:
        reward_object_id = ObjectId(reward_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="ID de recompensa inválido"
        )
    existing_reward = await db.rewards.find_one({"_id": reward_object_id})
    if not existing_reward:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Recompensa no encontrada"
        )
    if (
        body.type == "referral"
        and existing_reward.get("type") == "challenge"
        and (not body.required_referrals)
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Las recompensas de tipo referido requieren required_referrals",
        )
    if (
        body.type == "challenge"
        and existing_reward.get("type") == "referral"
        and (not body.end_date)
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Las recompensas por desafío requieren fecha de finalización",
        )
    update_fields = {}
    allowed_fields = [
        "name",
        "description",
        "max_redemptions_per_user",
        "required_referrals",
        "active",
        "challenge_description",
        "challenge_goal",
        "challenge_points",
        "type",
    ]
    for field in allowed_fields:
        value = getattr(body, field, None)
        if value is not None:
            update_fields[field] = value
    if body.start_date:
        update_fields["start_date"] = datetime.fromisoformat(body.start_date)
    if body.end_date:
        update_fields["end_date"] = datetime.fromisoformat(body.end_date)
    if not update_fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No hay campos para actualizar",
        )
    await db.rewards.update_one({"_id": reward_object_id}, {"$set": update_fields})
    updated_reward = await db.rewards.find_one({"_id": reward_object_id})
    return serialize_reward(updated_reward)


@admin_router.put("/rewards/{reward_id}/toggle-status")
async def toggle_reward_status(
    reward_id: str, body: ToggleStatusRequest, db=Depends(get_db)
):
    """Activar / desactivar recompensa (solo admin)"""
    await verify_admin(body.id, db)
    try:
        reward_object_id = ObjectId(reward_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="ID de recompensa inválido"
        )
    reward = await db.rewards.find_one({"_id": reward_object_id})
    if not reward:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Recompensa no encontrada"
        )
    new_status = not reward.get("active", True)
    await db.rewards.update_one(
        {"_id": reward_object_id}, {"$set": {"active": new_status}}
    )
    return {
        "message": f"Recompensa {'activada' if new_status else 'desactivada'} correctamente",
        "reward_id": reward_id,
        "active": new_status,
    }


@admin_router.delete("/rewards/{reward_id}")
async def delete_reward(reward_id: str, body: DeleteRewardRequest, db=Depends(get_db)):
    """Eliminar recompensa (solo admin)"""
    await verify_admin(body.id, db)
    try:
        result = await db.rewards.delete_one({"_id": ObjectId(reward_id)})
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="ID de recompensa inválido"
        )
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Recompensa no encontrada"
        )
    return {"message": "Recompensa eliminada correctamente"}


# ── User: Rewards ────────────────────────────────────────────────────────
# /api/v1/rewards*

@router.get("")
async def get_user_rewards(db=Depends(get_db)):
    """Ver recompensas activas (para usuarios)"""
    now = datetime.utcnow()
    rewards = await db.rewards.find(
        {
            "active": True,
            "start_date": {"$lte": now},
            "$or": [
                {"end_date": {"$exists": False}},
                {"end_date": {"$gt": now}},
            ],
        }
    ).to_list(length=None)
    return [serialize_reward(r) for r in rewards]


@router.post("/{reward_id}/redemptions")
async def redeem_reward(reward_id: str, body: RedeemRequest, db=Depends(get_db)):
    """Canjear una recompensa (usuario)"""
    try:
        user_object_id = ObjectId(body.id)
        reward_object_id = ObjectId(reward_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="ID inválido"
        )
    user_doc = await db[Collections.USERS].find_one({"_id": user_object_id})
    if not user_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado"
        )
    reward = await db.rewards.find_one({"_id": reward_object_id})
    if not reward:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Recompensa no encontrada"
        )
    now = datetime.utcnow()
    if not reward.get("active", False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La recompensa no está activa",
        )
    if reward.get("start_date") and reward["start_date"] > now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La recompensa aún no está disponible",
        )
    if reward.get("end_date") and reward["end_date"] <= now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="La recompensa ya expiró"
        )
    max_redemptions = reward.get("max_redemptions_per_user", 1)
    count = await db.reward_redeem.count_documents(
        {"user_id": user_object_id, "reward_id": reward_object_id}
    )
    if count >= max_redemptions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya has canjeado esta recompensa el número máximo de veces",
        )
    redeem_record = {
        "user_id": user_object_id,
        "reward_id": reward_object_id,
        "reward_type": reward.get("type"),
        "reward_name": reward.get("name"),
        "redeemed_at": now,
    }
    await db.reward_redeem.insert_one(redeem_record)
    return {
        "message": "Recompensa canjeada correctamente",
        "reward_name": reward.get("name"),
    }


# ── Me: Rewards ──────────────────────────────────────────────────────────
# /api/v1/me/rewards/redemptions

@me_router.get("/redemptions")
async def get_my_redemptions(
    current_user: dict = Depends(get_current_user), db=Depends(get_db)
):
    """Obtener historial de recompensas canjeadas por el usuario autenticado"""
    user_object_id = ObjectId(current_user.get("id", ""))
    redeems = await db.reward_redeem.find(
        {"user_id": user_object_id}
    ).sort("redeemed_at", -1).to_list(length=None)
    history = [
        {
            "reward_id": str(redeem["reward_id"]),
            "reward_name": redeem.get("reward_name", ""),
            "reward_type": redeem.get("reward_type", ""),
            "redeemed_at": redeem["redeemed_at"].isoformat(),
            "referrals_used": redeem.get("referrals_used", 0),
        }
        for redeem in redeems
    ]
    return {"user_id": str(user_object_id), "redeem_history": history}


# ── Challenges ───────────────────────────────────────────────────────────
# /api/v1/challenges/{id}/completions

@challenge_router.post("/{challenge_id}/completions")
async def complete_challenge(
    challenge_id: str, body: CompleteChallenge, db=Depends(get_db)
):
    """Marcar un desafío como completado por un usuario"""
    try:
        user_id = ObjectId(body.id)
        challenge_object_id = ObjectId(challenge_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="ID inválido"
        )
    user = await db[Collections.USERS].find_one({"_id": user_id})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado"
        )
    reward = await db.rewards.find_one({"_id": challenge_object_id, "type": "challenge"})
    if not reward:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Desafío no encontrado"
        )
    now = datetime.utcnow()
    if not reward.get("active", True):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este desafío no está activo",
        )
    if reward.get("end_date") and reward["end_date"] < now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Este desafío ha expirado"
        )
    if await db.challenge_completions.find_one(
        {"user_id": user_id, "challenge_id": challenge_object_id}
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya has completado este desafío anteriormente",
        )
    completion = {
        "user_id": user_id,
        "challenge_id": challenge_object_id,
        "challenge_name": reward["name"],
        "completed_at": now,
        "evidence": body.evidence or "",
        "approved": False,
    }
    result = await db.challenge_completions.insert_one(completion)
    return {
        "message": "Desafío completado y enviado para aprobación",
        "completion_id": str(result.inserted_id),
    }


@admin_router.post("/challenges/{completion_id}/approve")
async def approve_challenge(completion_id: str, body: ApproveChallenge, db=Depends(get_db)):
    """Aprobar la finalización de un desafío (admin)"""
    await verify_admin(body.id, db)
    try:
        completion = await db.challenge_completions.find_one({"_id": ObjectId(completion_id)})
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ID de finalización inválido",
        )
    if not completion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Registro de finalización no encontrado",
        )
    await db.challenge_completions.update_one(
        {"_id": ObjectId(completion_id)},
        {"$set": {"approved": True, "approved_at": datetime.utcnow()}},
    )
    challenge = await db.rewards.find_one({"_id": completion["challenge_id"]})
    redeem_record = {
        "user_id": completion["user_id"],
        "reward_id": completion["challenge_id"],
        "reward_type": "challenge",
        "reward_name": challenge["name"],
        "redeemed_at": datetime.utcnow(),
        "challenge_completion_id": completion["_id"],
    }
    await db.reward_redeem.insert_one(redeem_record)
    return {
        "message": "Desafío aprobado y recompensa otorgada",
        "user_id": str(completion["user_id"]),
        "challenge_id": str(completion["challenge_id"]),
        "challenge_name": completion["challenge_name"],
    }


@admin_router.get("/challenges/pending")
async def list_pending_challenges(id: str, db=Depends(get_db)):
    """Listar desafíos pendientes de aprobación (admin)"""
    await verify_admin(id, db)
    pending = await db.challenge_completions.find({"approved": False}).to_list(length=None)
    result = []
    for p in pending:
        user = await db[Collections.USERS].find_one({"_id": p["user_id"]})
        user_info = {"nombre": "Desconocido", "apellido": "", "correo": ""}
        if user:
            user_info = {
                "nombre": user.get("nombre", ""),
                "apellido": user.get("apellido", ""),
                "correo": user.get("correo", ""),
            }
        challenge = await db.rewards.find_one({"_id": p["challenge_id"]})
        challenge_info = {"name": "Desconocido", "description": ""}
        if challenge:
            challenge_info = {
                "name": challenge.get("name", ""),
                "description": challenge.get("description", ""),
                "challenge_description": challenge.get("challenge_description", ""),
            }
        result.append(
            {
                "completion_id": str(p["_id"]),
                "user_id": str(p["user_id"]),
                "user": user_info,
                "challenge_id": str(p["challenge_id"]),
                "challenge": challenge_info,
                "completed_at": p["completed_at"].isoformat(),
                "evidence": p.get("evidence", ""),
            }
        )
    return result


# ── Reward Streaks: Admin ───────────────────────────────────────────────
# /api/v1/admin/reward-streaks

@admin_router.post("/reward-streaks", status_code=status.HTTP_201_CREATED)
async def create_update_reward_streak(body: RewardStreakCreate, db=Depends(get_db)):
    """Crear o actualizar una recompensa por racha (admin)"""
    await verify_admin(body.id, db)
    existing_reward = await db.rewards.find_one({"streak_days": body.streak_days})
    reward_data = {
        "streak_days": body.streak_days,
        "type": "streak",
        "reward_type": body.reward_type,
        "reward_value": body.reward_value,
        "description": body.description,
        "updated_at": datetime.utcnow(),
    }
    if existing_reward:
        await db.rewards.update_one({"_id": existing_reward["_id"]}, {"$set": reward_data})
        return {
            "message": "Recompensa actualizada con éxito",
            "reward_id": str(existing_reward["_id"]),
        }
    reward_data["created_at"] = datetime.utcnow()
    result = await db.rewards.insert_one(reward_data)
    return {
        "message": "Recompensa creada con éxito",
        "reward_id": str(result.inserted_id),
    }


@admin_router.get("/reward-streaks")
async def list_admin_reward_streaks(id: str, db=Depends(get_db)):
    """Listar todas las recompensas por racha (admin)"""
    await verify_admin(id, db)
    rewards = await db.rewards.find({"type": "streak"}).to_list(length=None)
    for reward in rewards:
        reward["_id"] = str(reward["_id"])
        if "created_at" in reward:
            reward["created_at"] = reward["created_at"].isoformat()
        if "updated_at" in reward:
            reward["updated_at"] = reward["updated_at"].isoformat()
    return {"rewards": rewards}


# ── Reward Streaks: User ────────────────────────────────────────────────
# /api/v1/reward-streaks*

@streak_router.get("")
async def list_reward_streaks(db=Depends(get_db)):
    """Listar todas las recompensas por racha (usuario)"""
    rewards = await db.rewards.find({"type": "streak"}).to_list(length=None)
    for reward in rewards:
        reward["_id"] = str(reward["_id"])
        if "created_at" in reward:
            reward["created_at"] = reward["created_at"].isoformat()
        if "updated_at" in reward:
            reward["updated_at"] = reward["updated_at"].isoformat()
    return {"rewards": rewards}


@streak_router.post("/redemptions", status_code=status.HTTP_201_CREATED)
async def apply_user_reward_streak(
    body: ApplyRewardStreak,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Aplicar una recompensa por racha al usuario autenticado"""
    if not body.reward_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ID de recompensa no proporcionado",
        )
    try:
        user_object_id = ObjectId(current_user.get("id", ""))
        user_doc = await db[Collections.USERS].find_one({"_id": user_object_id})
        if not user_doc:
            raise HTTPException(404, "Usuario no encontrado")

        reward = await db.rewards.find_one({"_id": ObjectId(body.reward_id)})
        if not reward:
            raise HTTPException(404, "Recompensa no encontrada")

        if user_doc.get("login_streak", 0) < reward["streak_days"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes la racha suficiente para esta recompensa",
            )

        existing_applied = await db.reward_redeem_streak.find_one(
            {
                "user_id": user_object_id,
                "reward_id": ObjectId(body.reward_id),
                "status": "active",
            }
        )
        if existing_applied:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ya tienes esta recompensa activa",
            )

        applied_reward = {
            "user_id": user_object_id,
            "reward_id": ObjectId(body.reward_id),
            "streak_days": reward["streak_days"],
            "reward_type": reward["reward_type"],
            "reward_value": reward["reward_value"],
            "description": reward["description"],
            "applied_at": datetime.utcnow(),
            "status": "active",
        }
        result = await db.reward_redeem_streak.insert_one(applied_reward)
        if reward["reward_type"] == "discount":
            discount_code = "".join(
                random.choices(string.ascii_uppercase + string.digits, k=8)
            )
            await db.reward_redeem_streak.update_one(
                {"_id": result.inserted_id}, {"$set": {"discount_code": discount_code}}
            )
            return {
                "message": "Recompensa aplicada con éxito",
                "reward_id": str(result.inserted_id),
                "discount_code": discount_code,
            }
        return {
            "message": "Recompensa aplicada con éxito",
            "reward_id": str(result.inserted_id),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al aplicar recompensa: {e}", exc_info=True)
        raise HTTPException(500, "Error interno del servidor")


@streak_router.get("/redemptions")
async def list_reward_streak_redemptions(
    status_filter: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Listar las recompensas por racha aplicadas al usuario autenticado"""
    try:
        user_object_id = ObjectId(current_user.get("id", ""))
        query = {"user_id": user_object_id}
        if status_filter:
            query["status"] = status_filter
        reward_redeem_streak = await db.reward_redeem_streak.find(query).sort(
            "applied_at", -1
        ).to_list(length=None)
        formatted_rewards = []
        for reward in reward_redeem_streak:
            formatted_reward = {
                "id": str(reward["_id"]),
                "reward_id": str(reward["reward_id"]),
                "streak_days": reward["streak_days"],
                "reward_type": reward["reward_type"],
                "reward_value": reward["reward_value"],
                "description": reward["description"],
                "applied_at": reward["applied_at"].strftime("%Y-%m-%d %H:%M:%S"),
                "status": reward["status"],
            }
            if "discount_code" in reward:
                formatted_reward["discount_code"] = reward["discount_code"]
            if "expires_at" in reward:
                formatted_reward["expires_at"] = reward["expires_at"].strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            formatted_rewards.append(formatted_reward)
        return {
            "user_id": str(user_object_id),
            "reward_streak_redemptions": formatted_rewards,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al listar recompensas: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor",
        )


# ── Admin Stats ──────────────────────────────────────────────────────────
# /api/v1/admin/streak-stats

@admin_router.get("/streak-stats")
async def get_streak_stats(id: str, db=Depends(get_db)):
    """Obtener estadísticas de rachas de usuarios (admin)"""
    await verify_admin(id, db)
    try:
        top_streaks = await db[Collections.USERS].find(
            {}, {"_id": 1, "nombre": 1, "apellido": 1, "login_streak": 1}
        ).sort("login_streak", -1).limit(10).to_list(length=None)
        formatted_streaks = []
        for user in top_streaks:
            formatted_streaks.append(
                {
                    "user_id": str(user["_id"]),
                    "name": f"{user.get('nombre', '')} {user.get('apellido', '')}".strip(),
                    "streak": user.get("login_streak", 0),
                }
            )
        total_users = await db[Collections.USERS].count_documents({})
        users_with_streak = await db[Collections.USERS].count_documents(
            {"login_streak": {"$gt": 0}}
        )
        streak_distribution = []
        ranges = [(1, 3), (4, 7), (8, 14), (15, 30), (31, 1000000)]
        for start, end in ranges:
            count = await db[Collections.USERS].count_documents(
                {"login_streak": {"$gte": start, "$lte": end}}
            )
            streak_distribution.append(
                {
                    "range": f"{start}-{(end if end != 1000000 else '+')}",
                    "count": count,
                    "percentage": (
                        round(count / total_users * 100, 2) if total_users > 0 else 0
                    ),
                }
            )
        return {
            "total_users": total_users,
            "users_with_streak": users_with_streak,
            "streak_percentage": (
                round(users_with_streak / total_users * 100, 2) if total_users > 0 else 0
            ),
            "top_streaks": formatted_streaks,
            "streak_distribution": streak_distribution,
        }
    except Exception as e:
        logger.error(f"Error al obtener estadísticas: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor",
        )
