"""
Shared Google OAuth V2 helper.

Provides fallback credential lookup from user_connected_accounts when
oauth_vault doesn't have the credentials (new OAuth integration system).

All Google Suite services (Gmail, Drive, Docs, Sheets, Slides) share
provider="google" in user_connected_accounts.
"""

import logging
import requests
from typing import Optional, Dict, Any

from app.core.constants import Collections

logger = logging.getLogger(__name__)


def get_google_creds_from_v2(
    user_id: str,
    account_id: Optional[str] = None,
    provider_hint: Optional[str] = None,
    db: Optional[Any] = None,
) -> Optional[Dict[str, Any]]:
    """
    Looks up Google OAuth credentials from user_connected_accounts (V2 system).
    Returns decrypted creds dict {"token": ..., "refresh_token": ...} or None.

    Used as fallback when oauth_vault / legacy users collection don't have creds.
    Tokens stored by add_integration are encrypted with Fernet and keyed by user_id.
    """
    from app.core.security import decrypt_data
    from app.core.db_utils import find_user_by_email
    from app.core.mongo import get_sync_database

    if db is None:
        db = get_sync_database()

    if not user_id:
        logger.warning("[GoogleOAuthV2] Called without user_id.")
        return None

    all_providers = [
        "google",
        "gmail",
        "google_drive",
        "google_docs",
        "google_sheets",
        "google_slides",
        "google_calendar",
    ]

    def _query(providers):
        base = {"user_id": user_id, "provider": {"$in": providers}}
        if account_id:
            base["account_id"] = account_id
        active = {"$and": [base, {"$or": [{"status": "active"}, {"is_active": True}]}]}
        doc = db[Collections.USER_CONNECTED_ACCOUNTS].find_one(active)
        if not doc:
            doc = db[Collections.USER_CONNECTED_ACCOUNTS].find_one(base)
        return doc

    v2_doc = None

    # Phase 1: try the hinted provider specifically (exact match, no Gmail fallback).
    # This prevents using Gmail tokens (gmail scope only) for Drive/Sheets/Docs/Slides.
    if provider_hint:
        v2_doc = _query([provider_hint])
        # Also try the generic "google" provider as a secondary preferred option
        if not v2_doc:
            v2_doc = _query(["google"])

    # Phase 2: fall back to the full provider list
    if not v2_doc:
        v2_doc = _query(all_providers)

    if not v2_doc:
        logger.warning(
            f"[GoogleOAuthV2] No active Google account found for user_id={user_id}, account_id={account_id}, provider_hint={provider_hint}"
        )
        return None

    try:
        raw_token = decrypt_data(v2_doc.get("access_token") or "") or ""
        raw_refresh = decrypt_data(v2_doc.get("refresh_token") or "") or ""
        if raw_refresh:
            logger.info(
                f"[GoogleOAuthV2] V2 creds found for user_id={user_id} account_id={v2_doc.get('account_id')}"
            )
            return {"token": raw_token, "refresh_token": raw_refresh}
    except Exception as exc:
        logger.warning(
            f"[GoogleOAuthV2] decrypt error for account_id={account_id}: {exc}"
        )

    return None


def refresh_google_token_v2(
    user_id: str,
    account_id: str,
    creds: Dict[str, Any],
    client_id: str,
    client_secret: str,
    db=None,
) -> Optional[str]:
    """
    Refreshes a Google OAuth token for a V2 user and persists the new token
    in user_connected_accounts. Returns the new access_token or None on failure.
    """
    from langchain_core.tools import ToolException
    from app.core.mongo import get_sync_database

    if db is None:
        db = get_sync_database()
    try:
        from app.core.security import encrypt_data
    except ImportError:
        encrypt_data = lambda x: x

    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": creds.get("refresh_token", ""),
        "grant_type": "refresh_token",
    }
    try:
        response = requests.post(
            "https://oauth2.googleapis.com/token", data=data, timeout=10
        )
        if response.status_code == 200:
            nuevo_token = response.json().get("access_token")
            db[Collections.USER_CONNECTED_ACCOUNTS].update_one(
                {
                    "user_id": user_id,
                    "provider": {
                        "$in": [
                            "google",
                            "gmail",
                            "google_drive",
                            "google_docs",
                            "google_sheets",
                            "google_slides",
                        ]
                    },
                },
                {"$set": {"access_token": encrypt_data(nuevo_token)}},
            )
            logger.info(f"[GoogleOAuthV2] Token refrescado para user_id={user_id}.")
            return nuevo_token
        else:
            try:
                error_data = response.json()
            except ValueError:
                error_data = {}
            if error_data.get("error") == "invalid_grant":
                raise ToolException(
                    "La sesión de Google ha expirado o el token es inválido. Por favor, reconecta tu cuenta desde el panel de integraciones."
                )
            logger.error(
                f"[GoogleOAuthV2] HTTP {response.status_code} al refrescar token para user_id={user_id}."
            )
            return None
    except ToolException:
        raise
    except Exception as e:
        logger.error(
            f"[GoogleOAuthV2] Error inesperado al refrescar token para user_id={user_id}: {e}",
            exc_info=True,
        )
        return None
