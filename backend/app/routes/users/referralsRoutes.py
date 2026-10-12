from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.database import get_db
from app.core.constants import Collections

router = APIRouter(tags=["Referrals"])


class ReferralClaimModel(BaseModel):
    referral_code: str = Field(..., min_length=1)
    new_user_id: str = Field(..., min_length=1)


@router.get("/codes/{code}")
async def verify_code(code: str, mongo=Depends(get_db)):
    """Verifica si un código de referido existe y es válido."""
    referrer = await mongo[Collections.USERS].find_one({"code_referrals_uniq": code.upper()})
    if not referrer:
        return {"valid": False, "message": "Código no encontrado"}
    return {
        "valid": True,
        "referrer_name": f"{referrer.get('nombre')} {referrer.get('apellido', '')}".strip(),
        "referrer_id": str(referrer["_id"]),
    }


@router.post("/claim")
async def claim_referral_code(body: ReferralClaimModel, mongo=Depends(get_db)):
    """
    Canjea un código de referido para un usuario ya registrado.

    Reusa la misma validación de `GET /codes/{code}` (busca por
    `code_referrals_uniq`) y persiste el vínculo en la colección `referrals`
    con el mismo shape que ya consume `GET /api/v1/me/referrals`
    (`app/routes/me/me.py::list_my_referrals`): `{referrer_id, referred_id,
    date_registered}` + `$inc count_referrals` en el doc del referente. No
    existe hoy ninguna lógica de bonus/créditos en el flujo de registro
    (`authRoutes.py::register_user` genera un código PROPIO para el nuevo
    usuario, pero nunca consume uno ajeno) — este endpoint es, por ahora,
    el único punto donde un código de referido se "canjea" de verdad.
    """
    code = body.referral_code.strip().upper()
    referrer = await mongo[Collections.USERS].find_one({"code_referrals_uniq": code})
    if not referrer:
        return {"success": False, "reason": "Código no encontrado"}

    try:
        new_user_oid = ObjectId(body.new_user_id)
    except InvalidId:
        return {"success": False, "reason": "new_user_id inválido"}

    new_user = await mongo[Collections.USERS].find_one({"_id": new_user_oid})
    if not new_user:
        return {"success": False, "reason": "Usuario no encontrado"}

    if referrer["_id"] == new_user_oid:
        return {"success": False, "reason": "No podés canjear tu propio código de referido"}

    if new_user.get("referred_by") or await mongo.referrals.find_one({"referred_id": str(new_user_oid)}):
        return {"success": False, "reason": "Este usuario ya canjeó un código de referido"}

    now = datetime.now(timezone.utc)
    await mongo.referrals.insert_one({
        "referrer_id": str(referrer["_id"]),
        "referred_id": str(new_user_oid),
        "referral_code": code,
        "date_registered": now,
    })
    await mongo[Collections.USERS].update_one(
        {"_id": referrer["_id"]},
        {"$inc": {"count_referrals": 1}},
    )
    await mongo[Collections.USERS].update_one(
        {"_id": new_user_oid},
        {"$set": {"referred_by": str(referrer["_id"])}},
    )

    return {
        "success": True,
        "bonus_applied": "referral_registered",
        "referrer_id": str(referrer["_id"]),
    }
