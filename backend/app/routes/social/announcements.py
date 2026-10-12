from fastapi import APIRouter, HTTPException, Query, Body, Request
from pydantic import BaseModel, EmailStr, model_validator
from typing import Optional, List
from bson import ObjectId
from datetime import datetime
import validators
import logging
from app.core.constants import Collections
from app.core.db_utils import canonicalize_email

# Mounted at /api/v1/admin — announcement CRUD.
admin_router = APIRouter()
# Mounted at /api/v1/me — own announcement inbox.
me_router = APIRouter()
logger = logging.getLogger(__name__)


class AnnouncementCreate(BaseModel):
    title: str
    description: str
    short_description: Optional[str] = None
    image: Optional[str] = ""
    video: Optional[str] = ""
    active: Optional[bool] = True


class AnnouncementUpdate(BaseModel):
    title: Optional[str]
    description: Optional[str]
    short_description: Optional[str]
    image: Optional[str]
    video: Optional[str]
    active: Optional[bool]


class MarkViewedRequest(BaseModel):
    email: str
    announcement_id: str

    @model_validator(mode="before")
    def accept_spanish_email_alias(cls, values: dict) -> dict:
        if not isinstance(values, dict):
            return values
        if "correo" in values and (not values.get("email")):
            values["email"] = values.get("correo")
        if "announcementId" in values and (not values.get("announcement_id")):
            values["announcement_id"] = values.get("announcementId")
        return values


class MarkAllViewedRequest(BaseModel):
    email: str

    @model_validator(mode="before")
    def accept_spanish_email_alias(cls, values: dict) -> dict:
        if not isinstance(values, dict):
            return values
        if "correo" in values and (not values.get("email")):
            values["email"] = values.get("correo")
        return values


@admin_router.post("/announcements", status_code=201)
async def create_announcement(request: Request, data: AnnouncementCreate):
    mongo = request.app.state.db
    if data.image and (not validators.url(data.image)):
        raise HTTPException(400, "Invalid image URL")
    if data.video and (not validators.url(data.video)):
        raise HTTPException(400, "Invalid video URL")
    announcement_id = ObjectId()
    created_at = datetime.utcnow()
    announcement = {
        "announcement_id": announcement_id,
        "title": data.title.strip(),
        "description": data.description.strip(),
        "short_description": data.short_description or data.description[:100] + "...",
        "image": data.image,
        "video": data.video,
        "active": data.active,
        "created_at": created_at,
    }
    await mongo.announcements.insert_one(announcement)
    await mongo[Collections.USERS].update_many(
        {},
        {
            "$push": {
                "pending_announcements": {
                    "announcement_id": announcement_id,
                    "status": "pending",
                    "created_at": created_at,
                }
            }
        },
    )
    return {
        "message": "Announcement created",
        "announcement": {
            "announcement_id": str(announcement_id),
            "title": announcement["title"],
            "description": announcement["description"],
            "short_description": announcement["short_description"],
            "image": announcement["image"],
            "video": announcement["video"],
            "active": announcement["active"],
            "created_at": created_at.isoformat(),
        },
    }


@admin_router.get("/announcements")
async def list_announcements(request: Request, active: Optional[bool] = Query(None)):
    mongo = request.app.state.db
    query = {}
    if active is not None:
        query["active"] = active
    announcements = await mongo.announcements.find(query).sort("created_at", -1).to_list(100)
    for a in announcements:
        a["announcement_id"] = str(a["announcement_id"])
        a["created_at"] = a["created_at"].isoformat()
    return {"announcements": announcements}


@admin_router.put("/announcements/{id}")
async def update_announcement(request: Request, id: str, data: AnnouncementUpdate):
    mongo = request.app.state.db
    if not ObjectId.is_valid(id):
        raise HTTPException(400, "Invalid announcement ID")
    update_data = {k: v for k, v in data.dict().items() if v is not None}
    if not update_data:
        raise HTTPException(400, "No valid fields to update")
    if "image" in update_data and update_data["image"] and not validators.url(update_data["image"]):
        raise HTTPException(400, "Invalid image URL")
    if "video" in update_data and update_data["video"] and not validators.url(update_data["video"]):
        raise HTTPException(400, "Invalid video URL")
    result = await mongo.announcements.update_one(
        {"announcement_id": ObjectId(id)}, {"$set": update_data}
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Announcement not found")
    return {"message": "Announcement updated"}


@admin_router.delete("/announcements/{id}")
async def delete_announcement(request: Request, id: str):
    mongo = request.app.state.db
    if not ObjectId.is_valid(id):
        raise HTTPException(400, "Invalid announcement ID")
    result = await mongo.announcements.delete_one({"announcement_id": ObjectId(id)})
    if result.deleted_count == 0:
        raise HTTPException(404, "Announcement not found")
    return {"message": "Announcement deleted"}


@me_router.get("/announcements")
async def get_my_announcements(
    request: Request,
    email: str = Query(...),
    status: Optional[str] = Query(None),
    active: Optional[bool] = Query(None),
):
    mongo = request.app.state.db
    email = canonicalize_email(email)
    user = await mongo[Collections.USERS].find_one({"email": email})
    if not user:
        raise HTTPException(404, "User not found")
    pending = user.get("pending_announcements", [])
    if status:
        pending = [p for p in pending if p.get("status") == status]
    announcement_ids = [p["announcement_id"] for p in pending]
    query = {"announcement_id": {"$in": announcement_ids}}
    if active is not None:
        query["active"] = active
    announcements = await mongo.announcements.find(query).sort("created_at", -1).to_list(100)
    status_map = {str(p["announcement_id"]): p.get("status", "pending") for p in pending}
    for a in announcements:
        a["announcement_id"] = str(a["announcement_id"])
        a["created_at"] = a["created_at"].isoformat()
        a["status"] = status_map.get(str(a["announcement_id"]), "pending")
    return {"announcements": announcements}


@me_router.get("/announcements/pending")
async def get_pending_announcements(request: Request, email: str = Query(...)):
    mongo = request.app.state.db
    email = canonicalize_email(email)
    user = await mongo[Collections.USERS].find_one({"email": email})
    if not user:
        raise HTTPException(404, "User not found")
    pending = user.get("pending_announcements", [])
    pending = [p for p in pending if p.get("status") == "pending"]
    announcement_ids = [p["announcement_id"] for p in pending]
    announcements = await mongo.announcements.find(
        {"announcement_id": {"$in": announcement_ids}}
    ).sort("created_at", -1).to_list(100)
    status_map = {str(p["announcement_id"]): p.get("status", "pending") for p in pending}
    for a in announcements:
        a["announcement_id"] = str(a["announcement_id"])
        a["created_at"] = a["created_at"].isoformat()
        a["status"] = status_map.get(str(a["announcement_id"]), "pending")
    return {"announcements": announcements}


@me_router.post("/announcements/{id}/view")
async def mark_announcement_viewed(request: Request, id: str, data: MarkViewedRequest):
    mongo = request.app.state.db
    email = canonicalize_email(data.email)
    if not ObjectId.is_valid(id):
        raise HTTPException(400, "Invalid announcement ID")
    if data.announcement_id != id:
        raise HTTPException(400, "Announcement ID mismatch")
    user = await mongo[Collections.USERS].find_one({"email": email})
    if not user:
        raise HTTPException(404, "User not found")
    pending = user.get("pending_announcements", [])
    found = False
    for p in pending:
        if str(p["announcement_id"]) == id:
            p["status"] = "viewed"
            p["viewed_at"] = datetime.utcnow()
            found = True
            break
    if not found:
        raise HTTPException(404, "Announcement not found in pending list")
    await mongo[Collections.USERS].update_one(
        {"email": email}, {"$set": {"pending_announcements": pending}}
    )
    return {"message": "Announcement marked as viewed"}


@me_router.post("/announcements/views")
async def mark_all_announcements_viewed(request: Request, data: MarkAllViewedRequest):
    mongo = request.app.state.db
    email = canonicalize_email(data.email)
    user = await mongo[Collections.USERS].find_one({"email": email})
    if not user:
        raise HTTPException(404, "User not found")
    pending = user.get("pending_announcements", [])
    now = datetime.utcnow()
    for p in pending:
        if p.get("status") == "pending":
            p["status"] = "viewed"
            p["viewed_at"] = now
    await mongo[Collections.USERS].update_one(
        {"email": email}, {"$set": {"pending_announcements": pending}}
    )
    return {"message": "All announcements marked as viewed"}