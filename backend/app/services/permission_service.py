"""
Permission Service — capability gates based on user scope.

Scope hierarchy:
  read_only < standard < admin

Derivation:
  - user_platform_role == "admin"     → admin
  - user_plan in (pro, enterprise, …) → standard (full features)
  - all other authenticated users     → standard (current default — no read-only tier yet)

Use require_scope() to gate endpoints or actions. Raises HTTPException(403) on failure.
Logs permission_denied events to the audit log when a gate is triggered.
"""

import logging
from typing import Any

from fastapi import HTTPException

logger = logging.getLogger(__name__)

_SCOPE_LEVELS: dict[str, int] = {
    "read_only": 1,
    "standard":  2,
    "admin":     3,
}

_ADMIN_ROLES = {"admin", "superadmin", "super_admin"}
_PREMIUM_PLANS = {"pro", "enterprise", "premium", "business"}


def _pv(profile: dict, key: str) -> Any:
    """Extract plain value from user_preferences dict format."""
    v = (profile or {}).get(key)
    return (v.get("value") if isinstance(v, dict) else v)


def get_user_scope(user_profile: dict) -> str:
    """Derives the permission scope from user_profile fields."""
    role = str(_pv(user_profile, "user_platform_role") or "").lower()
    if role in _ADMIN_ROLES:
        return "admin"
    plan = str(_pv(user_profile, "user_plan") or "").lower()
    if plan in _PREMIUM_PLANS:
        return "standard"
    return "standard"  # default for all authenticated users today


def require_scope(user_profile: dict, required: str, action: str = "") -> None:
    """
    Raises HTTPException(403) if the user's scope is below required.
    Use this to gate capabilities — it never blocks admins.
    """
    scope = get_user_scope(user_profile)
    if _SCOPE_LEVELS.get(scope, 0) < _SCOPE_LEVELS.get(required, 0):
        logger.warning(
            "[permission] DENIED user_scope=%s required=%s action=%s",
            scope, required, action,
        )
        raise HTTPException(
            status_code=403,
            detail=f"Permission denied: this action requires {required} scope (your scope: {scope}).",
        )


def is_admin(user_profile: dict) -> bool:
    return get_user_scope(user_profile) == "admin"
