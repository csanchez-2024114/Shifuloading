"""SOLO desarrollo (se monta con SHIFU_DEV_UI=1): conecta una app con una cuenta falsa para probar
el ciclo agente -> boton -> conectada -> agente retoma, sin credenciales de terceros."""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends

from app.core.constants import Collections
from app.core.security import encrypt_data
from app.database import get_current_user, get_db

router = APIRouter()
_ACCOUNT_ID = "sim@dev"


@router.post("/connect/{app}")
async def simulate_connect(app: str, user: dict = Depends(get_current_user), db: Any = Depends(get_db)):
    user_id = str(user.get("_id") or user.get("id", ""))
    provider = app.lower()
    now = datetime.now(timezone.utc)
    doc = {
        "user_id": user_id, "provider": provider, "account_id": _ACCOUNT_ID,
        "access_token": encrypt_data("simulated-token"), "refresh_token": "n/a",
        "status": "active", "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
        "metadata": {"simulated": True, "connected_at": now.isoformat()},
    }
    await db[Collections.USER_CONNECTED_ACCOUNTS].update_one(
        {"user_id": user_id, "provider": provider, "account_id": _ACCOUNT_ID}, {"$set": doc}, upsert=True
    )
    return {"connected": provider, "account_id": _ACCOUNT_ID}
