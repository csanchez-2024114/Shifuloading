from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.encoders import jsonable_encoder
from bson import ObjectId
import logging
from app.database import get_current_user, get_db
from app.core.constants import Collections

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/{user_id}")
async def get_user(user_id: str, request: Request):
    mongo = request.app.state.db
    try:
        object_id = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid user ID format")
    user = await mongo[Collections.USERS].find_one({"_id": object_id}, {"password": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user["id"] = str(user.pop("_id"))
    user["name"] = user.get("name", "")
    user["last_name"] = user.get("last_name", "")
    return {"user": jsonable_encoder(user, custom_encoder={ObjectId: str})}


@router.get("/me")
async def get_current_user_info(
    current_user=Depends(get_current_user), mongo=Depends(get_db)
):
    """Retorna la información del usuario autenticado (desde JWT)."""
    try:
        user_id = ObjectId(current_user["id"])
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid user ID in token")
    user = await mongo[Collections.USERS].find_one({"_id": user_id}, {"password": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    subscription = user.get("subscription", {})
    current_plan = user.get("plan", "free")
    if subscription:
        subscription["plan"] = current_plan
    return {
        "id": str(user["_id"]),
        "email": user.get("email", ""),
        "name": user.get("name", ""),
        "last_name": user.get("last_name", ""),
        "plan": current_plan,
        "subscription": subscription,
        "img": user.get("img"),
    }
