from fastapi import APIRouter, Depends, HTTPException
from typing import List, Any
import logging
from app.models.accounts.connected_account import ConnectedAccountResponse
from app.database import get_db, get_current_user, _normalize_integrations
from app.core.constants import Collections

logger = logging.getLogger("api.accounts")
router = APIRouter(tags=["Connected Accounts"])


@router.get("/", response_model=List[ConnectedAccountResponse])
async def fetch_connected_accounts_for_user(
    current_user=Depends(get_current_user), db: Any = Depends(get_db)
):
    user_id_str = str(current_user["_id"])
    cursor = db[Collections.USER_CONNECTED_ACCOUNTS].find({"user_id": user_id_str})
    accounts = await cursor.to_list(length=100)
    for acc in accounts:
        acc["_id"] = str(acc["_id"])  # ConnectedAccountResponse.id tiene alias "_id" y exige str: con el ObjectId crudo respondia 500
    return accounts


@router.delete("/{provider}/{account_id}")
async def remove_connected_account(
    provider: str,
    account_id: str,
    user: dict = Depends(get_current_user),
    db: Any = Depends(get_db),
):
    user_id_str = str(user.get("_id") or user.get("id", ""))
    if not user_id_str:
        raise HTTPException(status_code=401, detail="Usuario no autenticado")
    provider_lower = provider.lower()
    result = await db[Collections.USER_CONNECTED_ACCOUNTS].delete_one(
        {"user_id": user_id_str, "provider": provider_lower, "account_id": account_id}
    )
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=404, detail="No se encontró la cuenta para desconectar"
        )
    logger.info(f"Cuenta {account_id} de {provider_lower} eliminada correctamente.")
    return {"message": "Cuenta desconectada exitosamente"}
