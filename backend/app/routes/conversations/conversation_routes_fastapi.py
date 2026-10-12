"""
Conversation Routes V2 - FastAPI rewrite del router Flask original.
Endpoints de historial de chat y mensajes para el frontend.
"""

from datetime import datetime, timezone
from typing import Optional
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, model_validator
from app.models.conversations.conversation_model import ConversationModel, MessageModel
from app.routes.auth.authRoutes import verify_token

router = APIRouter()


class CreateConversationBody(BaseModel):
    title: str = "Nueva conversación"
    model_used: str = "gpt-4o"
    tags: list[str] = []


class CreateMessageBody(BaseModel):
    role: str = "user"
    content: str
    recursos: list = []

    @model_validator(mode="before")
    def normalize_resource_aliases(cls, values: dict) -> dict:
        """Accept English alias `resources` for backward compatibility."""
        if not isinstance(values, dict):
            return values
        if "resources" in values and (not values.get("recursos")):
            values["recursos"] = values.get("resources")
        return values


def _serialize(doc: dict) -> dict:
    """Convierte ObjectIds y datetimes a strings para JSON."""
    doc["id"] = str(doc.pop("_id"))
    for key, val in doc.items():
        if isinstance(val, ObjectId):
            doc[key] = str(val)
        elif isinstance(val, datetime):
            doc[key] = val.isoformat()
    return doc


@router.post("", status_code=201)
async def create_conversation(
    request: Request,
    body: CreateConversationBody,
    payload: dict = Depends(verify_token),
):
    mongo = request.app.state.db
    new_conv = ConversationModel(
        user_id=payload["user_id"],
        title=body.title,
        model_used=body.model_used,
        tags=body.tags,
    )
    res = await mongo.conversations.insert_one(new_conv.model_dump())
    return {
        "success": True,
        "id": str(res.inserted_id),
        "message": "Conversación iniciada",
    }


@router.get("")
async def list_conversations(
    request: Request,
    limit: int = 20,
    payload: dict = Depends(verify_token),
):
    mongo = request.app.state.db
    cursor = (
        mongo.conversations.find({"user_id": payload["user_id"], "is_archived": False})
        .sort("updated_at", -1)
        .limit(limit)
    )
    chats = [_serialize(c) async for c in cursor]
    return {"success": True, "data": chats}


@router.get("/{id}")
async def get_conversation(
    id: str, request: Request, payload: dict = Depends(verify_token)
):
    mongo = request.app.state.db
    if not ObjectId.is_valid(id):
        raise HTTPException(400, "ID de conversación inválido")
    conv = await mongo.conversations.find_one({"_id": ObjectId(id)})
    if not conv:
        raise HTTPException(404, "Conversación no encontrada")
    if str(conv.get("user_id")) != payload["user_id"]:
        raise HTTPException(403, "Prohibido: No eres el dueño")
    return {"success": True, "data": _serialize(conv)}


@router.patch("/{id}")
async def update_conversation(
    id: str,
    request: Request,
    body: dict,
    payload: dict = Depends(verify_token),
):
    mongo = request.app.state.db
    if not ObjectId.is_valid(id):
        raise HTTPException(400, "ID inválido")
    conv = await mongo.conversations.find_one({"_id": ObjectId(id)})
    if not conv:
        raise HTTPException(404, "Conversación no encontrada")
    if str(conv.get("user_id")) != payload["user_id"]:
        raise HTTPException(403, "Prohibido")
    allowed_fields = {"title", "is_pinned", "is_archived", "tags"}
    update_data = {k: v for k, v in body.items() if k in allowed_fields}
    update_data["updated_at"] = datetime.now(timezone.utc)
    await mongo.conversations.update_one(
        {"_id": ObjectId(id)}, {"$set": update_data}
    )
    return {"success": True, "message": "Conversación actualizada"}


@router.delete("/{id}", status_code=204)
async def delete_conversation(
    id: str, request: Request, payload: dict = Depends(verify_token)
):
    mongo = request.app.state.db
    if not ObjectId.is_valid(id):
        raise HTTPException(400, "ID inválido")
    conv = await mongo.conversations.find_one({"_id": ObjectId(id)})
    if not conv:
        raise HTTPException(404, "Conversación no encontrada")
    if str(conv.get("user_id")) != payload["user_id"]:
        raise HTTPException(403, "Prohibido")
    await mongo.conversations.delete_one({"_id": ObjectId(id)})
    await mongo.messages.delete_many({"conversation_id": id})


@router.post("/{id}/messages", status_code=201)
async def create_message(
    id: str,
    request: Request,
    body: CreateMessageBody,
    payload: dict = Depends(verify_token),
):
    mongo = request.app.state.db
    if not ObjectId.is_valid(id):
        raise HTTPException(400, "ID inválido")
    conv = await mongo.conversations.find_one({"_id": ObjectId(id)})
    if not conv:
        raise HTTPException(404, "Conversación no encontrada")
    if str(conv.get("user_id")) != payload["user_id"]:
        raise HTTPException(403, "Prohibido")
    new_msg = MessageModel(
        conversation_id=id,
        role=body.role,
        content=body.content,
        recursos=body.recursos,
    )
    msg_res = await mongo.messages.insert_one(new_msg.model_dump())
    await mongo.conversations.update_one(
        {"_id": ObjectId(id)},
        {
            "$set": {
                "updated_at": datetime.now(timezone.utc),
                "last_message_preview": body.content[:150],
            },
            "$inc": {"message_count": 1},
        },
    )
    return {"success": True, "message_id": str(msg_res.inserted_id)}


@router.get("/{id}/messages")
async def list_messages(
    id: str,
    request: Request,
    limit: int = 50,
    payload: dict = Depends(verify_token),
):
    mongo = request.app.state.db
    if not ObjectId.is_valid(id):
        raise HTTPException(400, "ID inválido")
    conv = await mongo.conversations.find_one({"_id": ObjectId(id)})
    if not conv:
        raise HTTPException(404, "Conversación no encontrada")
    if str(conv.get("user_id")) != payload["user_id"]:
        raise HTTPException(403, "Prohibido")
    cursor = (
        mongo.messages.find({"conversation_id": id})
        .sort("created_at", 1)
        .limit(limit)
    )
    messages = [_serialize(m) async for m in cursor]
    return {"success": True, "data": messages, "total": len(messages)}