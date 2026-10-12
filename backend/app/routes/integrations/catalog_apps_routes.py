from fastapi import APIRouter, Request, HTTPException, Query
import logging
from typing import List, Optional
from app.services.catalog_apps import (
    get_all,
    create_app,
    update_app,
    deactivate_app,
    get_by_names,
)
from app.agent.shared.utils.login_paths import get_login_path, get_auth_type

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/apps")
async def get_catalog_apps_list(request: Request, names: Optional[List[str]] = Query(None)):
    try:
        mongo = request.app.state.db
        if names:
            items = await get_by_names(names, mongo)
        else:
            items = await get_all(mongo)
        for item in items:
            # Normalize to canonical form: lowercase + spaces → underscores
            # Matches how the agent (semantic_intake / catalog_checker) treats nameApi.
            raw = (item.get("nameApi") or "").lower().replace(" ", "_")
            item["nameApi"] = raw
            item["loginPath"] = get_login_path(raw)
            item["authType"] = get_auth_type(raw)
        return {"apps": items}
    except Exception:
        logger.exception("Error list_catalog_apps")
        raise HTTPException(500, "Error fetching catalog apps")


@router.post("/apps", status_code=201)
async def add_new_catalog_app(request: Request, data: dict):
    try:
        db = request.app.state.db
        created = await create_app(data, db)
        return {"created": created}
    except ValueError as ve:
        logger.warning(f"create_catalog_app validation: {ve}")
        raise HTTPException(400, str(ve))
    except Exception:
        logger.exception("Error creating app")
        raise HTTPException(500, "Error creating app")


@router.put("/apps/{app_id}")
async def modify_catalog_app(app_id: str, request: Request, data: dict):
    try:
        db = request.app.state.db
        updated = await update_app(app_id, data, db)
        if not updated:
            raise HTTPException(404, "Not found")
        return {"updated": updated}
    except ValueError as ve:
        logger.warning(f"update_catalog_app validation: {ve}")
        raise HTTPException(400, str(ve))
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error update_catalog_app")
        raise HTTPException(500, "Error updating app")


@router.patch("/apps/{app_id}")
async def patch_catalog_app(app_id: str, request: Request, data: dict):
    try:
        db = request.app.state.db
        # Support deactivation via body: {"active": false}
        if "active" in data and data["active"] is False:
            updated = await deactivate_app(app_id, db)
            if not updated:
                raise HTTPException(404, "Not found")
            return {"updated": updated}
        # Otherwise delegate to generic update
        updated = await update_app(app_id, data, db)
        if not updated:
            raise HTTPException(404, "Not found")
        return {"updated": updated}
    except ValueError as ve:
        logger.warning(f"patch_catalog_app validation: {ve}")
        raise HTTPException(400, str(ve))
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error patch_catalog_app")
        raise HTTPException(500, "Error patching app")