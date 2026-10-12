"""
/api/v1/workspaces — Workspace membership, invite codes, and boards.

Creation of a workspace is normally 1:1 (each user gets exactly one, created automatically during
onboarding — see app/routes/onboarding/onboardingRoutes.py:complete_onboarding), but owners can
create additional workspaces up to their plan's `max_workspaces` limit. Membership is N:N: a user
can additionally be invited into other people's workspaces. This router covers joining/managing
membership of that N:N graph plus creating additional workspaces.

Two invite mechanisms, both landing in `workspace_members`:
  1. Join by code (self-serve): POST /join {code} — creates an active member immediately.
  2. Invite by email (admin-initiated): POST /{id}/members/invite {email, role} — creates a
     pending member (status="invited", user_id=None); completed when that email registers or
     logs in (see app/routes/auth/authRoutes.py: _complete_pending_workspace_invites).

The workspace owner is never a row in `workspace_members` — their role is derived from
`workspaces.owner_id`. Endpoints that list/return members synthesize an "owner" entry with a
synthetic id (f"owner_{workspace_id}") so the frontend gets one uniform member list; that
synthetic id is rejected by the role/status/delete endpoints to guard against demoting or
removing the sole owner.

Boards are sub-groups that exist only inside a user's own workspace — no billing/members
of their own, only the owner can create them. `private=True` just hides a board from the
listing for non-owner members; nothing else in the system is board-scoped yet.

Endpoints:
  POST   /                                       — Create an additional workspace (owner, plan-gated)
  GET    /                                       — List workspaces the caller belongs to (own + shared)
  POST   /join                                   — Join a workspace by invite code (self-serve)
  POST   /{workspace_id}/invite-code/regenerate  — Regenerate the caller's own workspace invite code (owner only)
  GET    /{workspace_id}/members                 — List members (owner synthetic entry + workspace_members docs)
  POST   /{workspace_id}/members/invite          — Invite by email + role (owner/admin only)
  PATCH  /{workspace_id}/members/{member_id}/role    — Change a member's role (owner/admin only)
  PATCH  /{workspace_id}/members/{member_id}/status  — Suspend/reactivate a member (owner/admin only)
  DELETE /{workspace_id}/members/{member_id}     — Remove a member (owner/admin only)
  GET    /{workspace_id}/boards                  — List boards (private ones hidden from non-owners)
  POST   /{workspace_id}/boards                  — Create a board (owner only)
  PATCH  /{workspace_id}/boards/{board_id}       — Rename a board (owner only)
  DELETE /{workspace_id}/boards/{board_id}       — Delete a board; workflows become unassigned (owner only)
"""

import logging
import secrets
import string
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field

from app.database import get_current_user
from app.core.constants import Collections
from app.billing.plans import get_plan_rules

logger = logging.getLogger(__name__)
router = APIRouter()

_OWNER_SYNTHETIC_PREFIX = "owner_"
_ROLE_RANK = {"viewer": 0, "member": 1, "admin": 2, "owner": 3}


# ── Pydantic models ──────────────────────────────────────────────────────────


class JoinWorkspaceRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=40)


class InviteMemberRequest(BaseModel):
    email: EmailStr
    role: Literal["admin", "member", "viewer"] = "member"


class UpdateRoleRequest(BaseModel):
    role: Literal["admin", "member", "viewer"]


class UpdateStatusRequest(BaseModel):
    status: Literal["active", "suspended"]


class CreateBoardRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    private: bool = False


class UpdateBoardRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)


class CreateWorkspaceRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)


# ── Shared helpers ───────────────────────────────────────────────────────────


def _iso(value: Any) -> Optional[str]:
    return value.isoformat() if hasattr(value, "isoformat") else None


async def generate_workspace_invite_code(db) -> str:
    """Generates a unique 'SHIFU-XXXXXX' invite code. Shared shape with the one onboarding
    uses when a workspace is first created (app/routes/onboarding/onboardingRoutes.py)."""
    for _ in range(10):
        code = f"SHIFU-{''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))}"
        if not await db[Collections.WORKSPACES].find_one({"invite_code": code}, {"_id": 1}):
            return code
    raise HTTPException(status_code=500, detail="No se pudo generar un código de invitación único.")


async def require_workspace_role(workspace_id: str, actor_user_id: str, min_role: str, db) -> Dict[str, Any]:
    """
    Authorizes an action scoped to a workspace. Namespace is separate from the global
    platform role (`users.rol`, see app/routes/social/rewardRoutes.py:verify_admin) — this is
    purely about a user's standing *within one workspace*.

    The owner (workspaces.owner_id) always resolves to role="owner" without needing a
    workspace_members row. Everyone else must have an active workspace_members entry.
    Raises 404 if the workspace doesn't exist, 403 if the actor lacks the role or isn't a
    member at all. Returns {"workspace": doc, "role": str} on success.
    """
    try:
        workspace_oid = ObjectId(workspace_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="workspace_id inválido.")

    workspace = await db[Collections.WORKSPACES].find_one({"_id": workspace_oid})
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace no encontrado.")

    if str(workspace.get("owner_id", "")) == actor_user_id:
        role = "owner"
    else:
        member = await db[Collections.WORKSPACE_MEMBERS].find_one(
            {"workspace_id": workspace_id, "user_id": actor_user_id, "status": "active"}
        )
        if not member:
            raise HTTPException(status_code=403, detail="No sos miembro de este workspace.")
        role = member.get("role", "member")

    if _ROLE_RANK.get(role, -1) < _ROLE_RANK.get(min_role, 99):
        raise HTTPException(status_code=403, detail=f"Esta acción requiere rol '{min_role}' o superior.")

    return {"workspace": workspace, "role": role}


def _display_name(user_doc: Optional[Dict[str, Any]]) -> str:
    if not user_doc:
        return ""
    return f"{user_doc.get('name', '')} {user_doc.get('last_name', '')}".strip()


def _owner_member_dict(workspace: Dict[str, Any], owner_user: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "id": f"{_OWNER_SYNTHETIC_PREFIX}{str(workspace['_id'])}",
        "user_id": str(workspace.get("owner_id", "")),
        "name": _display_name(owner_user) or "Owner",
        "email": (owner_user or {}).get("email", ""),
        "avatar_url": (owner_user or {}).get("img") or (owner_user or {}).get("avatar"),
        "role": "owner",
        "status": "active",
        "invited_by": None,
        "invited_at": None,
        "joined_at": _iso(workspace.get("created_at")),
        "last_active_at": None,
    }


def _member_doc_to_dict(doc: Dict[str, Any]) -> Dict[str, Any]:
    email = doc.get("email", "")
    return {
        "id": str(doc["_id"]),
        "user_id": doc.get("user_id"),
        "name": doc.get("name") or (email.split("@")[0] if email else ""),
        "email": email,
        "avatar_url": doc.get("avatar_url"),
        "role": doc.get("role", "member"),
        "status": doc.get("status", "invited"),
        "invited_by": doc.get("invited_by"),
        "invited_at": _iso(doc.get("invited_at")),
        "joined_at": _iso(doc.get("joined_at")),
        "last_active_at": _iso(doc.get("last_active_at")),
    }


async def _owner_name_for(db, workspace: Dict[str, Any]) -> str:
    owner_user = await db[Collections.USERS].find_one(
        {"_id": workspace.get("owner_id")}, {"name": 1, "last_name": 1, "email": 1}
    )
    return _display_name(owner_user) or (owner_user or {}).get("email", "")


def _require_real_member_id(member_id: str) -> ObjectId:
    if member_id.startswith(_OWNER_SYNTHETIC_PREFIX):
        raise HTTPException(status_code=403, detail="No se puede modificar al dueño del workspace.")
    try:
        return ObjectId(member_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="member_id inválido.")


# ── POST / (create additional workspace) ────────────────────────────────────


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_workspace(
    body: CreateWorkspaceRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Creates an ADDITIONAL workspace owned by the caller — separate from the one
    auto-created at onboarding. Gated by the plan's max_workspaces."""
    db = request.app.state.db
    user_id = current_user.get("id", "")

    user_doc = await db[Collections.USERS].find_one({"_id": ObjectId(user_id)}, {"plan": 1})
    plan = (user_doc or {}).get("plan", "free")
    limit = get_plan_rules(plan).get("max_workspaces", 1)
    if limit != -1:
        owned_count = await db[Collections.WORKSPACES].count_documents({"owner_id": ObjectId(user_id)})
        if owned_count >= limit:
            raise HTTPException(
                status_code=403,
                detail=f"Tu plan permite hasta {limit} workspace(s). Actualiza tu plan para crear mas.",
            )

    invite_code = await generate_workspace_invite_code(db)
    now = datetime.now(timezone.utc)
    doc = {
        "owner_id": ObjectId(user_id),
        "workspace_name": body.name.strip(),
        "invite_code": invite_code,
        "created_at": now,
    }
    res = await db[Collections.WORKSPACES].insert_one(doc)
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=jsonable_encoder({
        "id": str(res.inserted_id), "name": doc["workspace_name"], "role": "owner", "invite_code": invite_code,
    }))


# ── GET / (list workspaces I belong to) ──────────────────────────────────────


@router.get("")
async def list_my_workspaces(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Lists the caller's own workspace (created at onboarding) plus every workspace they've
    been added to as a member. Only the owner's own entry includes `invite_code`."""
    db = request.app.state.db
    user_id = current_user.get("id", "")
    user_oid = ObjectId(user_id)

    result: List[Dict[str, Any]] = []

    own = await db[Collections.WORKSPACES].find_one({"owner_id": user_oid})
    if own:
        result.append({
            "id": str(own["_id"]),
            "name": own.get("workspace_name", "Mi Workspace"),
            "role": "owner",
            "invite_code": own.get("invite_code"),
        })

    memberships = await db[Collections.WORKSPACE_MEMBERS].find(
        {"user_id": user_id, "status": "active"}
    ).to_list(length=200)

    for m in memberships:
        try:
            ws_oid = ObjectId(m.get("workspace_id", ""))
        except InvalidId:
            continue
        ws = await db[Collections.WORKSPACES].find_one({"_id": ws_oid})
        if not ws:
            continue
        result.append({
            "id": str(ws["_id"]),
            "name": ws.get("workspace_name", "Workspace"),
            "role": "member",
            "ownerName": await _owner_name_for(db, ws),
        })

    return JSONResponse(content=jsonable_encoder(result))


# ── POST /join ────────────────────────────────────────────────────────────────


@router.post("/join")
async def join_workspace(
    body: JoinWorkspaceRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Self-serve join via invite code — creates an active member immediately, no pending step."""
    db = request.app.state.db
    user_id = current_user.get("id", "")
    email = (current_user.get("email") or "").lower().strip()
    code = body.code.strip().upper()

    workspace = await db[Collections.WORKSPACES].find_one({"invite_code": code})
    if not workspace:
        raise HTTPException(status_code=404, detail="Código de invitación inválido.")
    if str(workspace.get("owner_id", "")) == user_id:
        raise HTTPException(status_code=400, detail="Ya sos el dueño de este workspace.")

    workspace_id = str(workspace["_id"])
    now = datetime.now(timezone.utc)

    existing = await db[Collections.WORKSPACE_MEMBERS].find_one(
        {"workspace_id": workspace_id, "user_id": user_id}
    )
    if existing and existing.get("status") == "suspended":
        raise HTTPException(status_code=403, detail="Tu acceso a este workspace fue suspendido.")
    if not existing:
        await db[Collections.WORKSPACE_MEMBERS].insert_one({
            "workspace_id": workspace_id,
            "user_id": user_id,
            "email": email,
            "role": "member",
            "status": "active",
            "invited_by": None,
            "invited_at": None,
            "joined_at": now,
            "last_active_at": now,
            "created_at": now,
            "updated_at": now,
        })
    elif existing.get("status") != "active":
        await db[Collections.WORKSPACE_MEMBERS].update_one(
            {"_id": existing["_id"]},
            {"$set": {"status": "active", "user_id": user_id, "joined_at": now, "updated_at": now}},
        )

    return JSONResponse(content=jsonable_encoder({
        "id": workspace_id,
        "name": workspace.get("workspace_name", "Workspace"),
        "role": "member",
        "ownerName": await _owner_name_for(db, workspace),
    }))


# ── POST /{workspace_id}/invite-code/regenerate ──────────────────────────────


@router.post("/{workspace_id}/invite-code/regenerate")
async def regenerate_invite_code(
    workspace_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    db = request.app.state.db
    user_id = current_user.get("id", "")
    ctx = await require_workspace_role(workspace_id, user_id, "owner", db)

    new_code = await generate_workspace_invite_code(db)
    await db[Collections.WORKSPACES].update_one(
        {"_id": ctx["workspace"]["_id"]}, {"$set": {"invite_code": new_code}}
    )
    return JSONResponse(content={"invite_code": new_code})


# ── GET /{workspace_id}/members ──────────────────────────────────────────────


@router.get("/{workspace_id}/members")
async def list_members(
    workspace_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    db = request.app.state.db
    user_id = current_user.get("id", "")
    ctx = await require_workspace_role(workspace_id, user_id, "viewer", db)
    workspace = ctx["workspace"]

    owner_user = await db[Collections.USERS].find_one(
        {"_id": workspace.get("owner_id")}, {"name": 1, "last_name": 1, "email": 1, "img": 1, "avatar": 1}
    )
    members = [_owner_member_dict(workspace, owner_user)]

    docs = await db[Collections.WORKSPACE_MEMBERS].find(
        {"workspace_id": workspace_id}
    ).sort("created_at", 1).to_list(length=500)
    members.extend(_member_doc_to_dict(d) for d in docs)

    return JSONResponse(content=jsonable_encoder(members))


# ── POST /{workspace_id}/members/invite ──────────────────────────────────────


@router.post("/{workspace_id}/members/invite", status_code=status.HTTP_201_CREATED)
async def invite_member(
    workspace_id: str,
    body: InviteMemberRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Admin-initiated invite by email. Creates a pending member (user_id=None) — completed
    automatically when that email registers or logs in (see authRoutes.py)."""
    db = request.app.state.db
    user_id = current_user.get("id", "")
    await require_workspace_role(workspace_id, user_id, "admin", db)

    email = body.email.lower().strip()
    dup = await db[Collections.WORKSPACE_MEMBERS].find_one({
        "workspace_id": workspace_id, "email": email, "status": {"$in": ["active", "invited"]},
    })
    if dup:
        raise HTTPException(status_code=400, detail="Este correo ya está registrado en el workspace.")

    now = datetime.now(timezone.utc)
    doc = {
        "workspace_id": workspace_id,
        "user_id": None,
        "email": email,
        "role": body.role,
        "status": "invited",
        "invited_by": user_id,
        "invited_at": now,
        "joined_at": None,
        "last_active_at": None,
        "created_at": now,
        "updated_at": now,
    }
    res = await db[Collections.WORKSPACE_MEMBERS].insert_one(doc)
    doc["_id"] = res.inserted_id

    return JSONResponse(status_code=status.HTTP_201_CREATED, content=jsonable_encoder(_member_doc_to_dict(doc)))


# ── PATCH /{workspace_id}/members/{member_id}/role ──────────────────────────


@router.patch("/{workspace_id}/members/{member_id}/role")
async def update_member_role(
    workspace_id: str,
    member_id: str,
    body: UpdateRoleRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    db = request.app.state.db
    user_id = current_user.get("id", "")
    await require_workspace_role(workspace_id, user_id, "admin", db)
    member_oid = _require_real_member_id(member_id)

    result = await db[Collections.WORKSPACE_MEMBERS].update_one(
        {"_id": member_oid, "workspace_id": workspace_id},
        {"$set": {"role": body.role, "updated_at": datetime.now(timezone.utc)}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Miembro no encontrado.")
    return JSONResponse(content={"status": "updated", "member_id": member_id, "role": body.role})


# ── PATCH /{workspace_id}/members/{member_id}/status ────────────────────────


@router.patch("/{workspace_id}/members/{member_id}/status")
async def update_member_status(
    workspace_id: str,
    member_id: str,
    body: UpdateStatusRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    db = request.app.state.db
    user_id = current_user.get("id", "")
    await require_workspace_role(workspace_id, user_id, "admin", db)
    member_oid = _require_real_member_id(member_id)

    result = await db[Collections.WORKSPACE_MEMBERS].update_one(
        {"_id": member_oid, "workspace_id": workspace_id},
        {"$set": {"status": body.status, "updated_at": datetime.now(timezone.utc)}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Miembro no encontrado.")
    return JSONResponse(content={"status": "updated", "member_id": member_id, "new_status": body.status})


# ── DELETE /{workspace_id}/members/{member_id} ──────────────────────────────


@router.delete("/{workspace_id}/members/{member_id}")
async def remove_member(
    workspace_id: str,
    member_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    db = request.app.state.db
    user_id = current_user.get("id", "")
    await require_workspace_role(workspace_id, user_id, "admin", db)
    member_oid = _require_real_member_id(member_id)

    result = await db[Collections.WORKSPACE_MEMBERS].delete_one(
        {"_id": member_oid, "workspace_id": workspace_id}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Miembro no encontrado.")
    return JSONResponse(content={"status": "removed", "member_id": member_id})


# ── GET /{workspace_id}/boards ───────────────────────────────────────────────


@router.get("/{workspace_id}/boards")
async def list_boards(
    workspace_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    db = request.app.state.db
    user_id = current_user.get("id", "")
    ctx = await require_workspace_role(workspace_id, user_id, "viewer", db)

    query: Dict[str, Any] = {"workspace_id": workspace_id}
    if ctx["role"] != "owner":
        query["private"] = {"$ne": True}

    docs = await db[Collections.BOARDS].find(query).sort("created_at", -1).to_list(length=200)
    result = [{"id": str(d["_id"]), "name": d.get("name", ""), "private": bool(d.get("private", False))} for d in docs]
    return JSONResponse(content=jsonable_encoder(result))


# ── POST /{workspace_id}/boards ────────────────────────────────────────────


@router.post("/{workspace_id}/boards", status_code=status.HTTP_201_CREATED)
async def create_board(
    workspace_id: str,
    body: CreateBoardRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Boards are sub-groups within your own workspace — only the owner creates them
    (not admins), since they have no billing/membership of their own to delegate."""
    db = request.app.state.db
    user_id = current_user.get("id", "")
    await require_workspace_role(workspace_id, user_id, "owner", db)

    now = datetime.now(timezone.utc)
    doc = {
        "workspace_id": workspace_id,
        "name": body.name.strip(),
        "private": body.private,
        "created_by": user_id,
        "created_at": now,
        "updated_at": now,
    }
    res = await db[Collections.BOARDS].insert_one(doc)

    return JSONResponse(status_code=status.HTTP_201_CREATED, content=jsonable_encoder({
        "id": str(res.inserted_id), "name": doc["name"], "private": doc["private"],
    }))


# ── PATCH /{workspace_id}/boards/{board_id} ──────────────────────────────────


@router.patch("/{workspace_id}/boards/{board_id}")
async def update_board(
    workspace_id: str,
    board_id: str,
    body: UpdateBoardRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    db = request.app.state.db
    user_id = current_user.get("id", "")
    await require_workspace_role(workspace_id, user_id, "owner", db)
    try:
        board_oid = ObjectId(board_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="board_id inválido.")

    result = await db[Collections.BOARDS].update_one(
        {"_id": board_oid, "workspace_id": workspace_id},
        {"$set": {"name": body.name.strip(), "updated_at": datetime.now(timezone.utc)}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Board no encontrado.")
    return JSONResponse(content={"id": board_id, "name": body.name.strip()})


# ── DELETE /{workspace_id}/boards/{board_id} ─────────────────────────────────


@router.delete("/{workspace_id}/boards/{board_id}")
async def delete_board(
    workspace_id: str,
    board_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Deletes the board. Workflows inside become unassigned (board_id -> None) —
    they are NOT deleted."""
    db = request.app.state.db
    user_id = current_user.get("id", "")
    await require_workspace_role(workspace_id, user_id, "owner", db)
    try:
        board_oid = ObjectId(board_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="board_id inválido.")

    result = await db[Collections.BOARDS].delete_one({"_id": board_oid, "workspace_id": workspace_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Board no encontrado.")
    await db["workflows"].update_many({"board_id": board_id}, {"$set": {"board_id": None}})
    return JSONResponse(content={"status": "deleted", "board_id": board_id})


# ── POST /{workspace_id}/boards/{board_id}/migrate-unassigned ────────────────


@router.post("/{workspace_id}/boards/{board_id}/migrate-unassigned")
async def migrate_unassigned(
    workspace_id: str,
    board_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Moves all workflows with board_id=None in this workspace to the given board."""
    db = request.app.state.db
    user_id = current_user.get("id", "")
    await require_workspace_role(workspace_id, user_id, "owner", db)
    try:
        board_oid = ObjectId(board_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="board_id inválido.")

    board = await db[Collections.BOARDS].find_one({"_id": board_oid, "workspace_id": workspace_id})
    if not board:
        raise HTTPException(status_code=404, detail="Board no encontrado.")

    result = await db["workflows"].update_many(
        {"workspace_id": workspace_id, "board_id": None},
        {"$set": {"board_id": board_id}},
    )
    return JSONResponse(content={"migrated": result.modified_count})
