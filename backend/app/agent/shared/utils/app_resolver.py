"""
app_resolver — canonical app key resolution for agente_v3.

Resolves short app names (e.g. "sheets") to canonical catalog nameApi keys
(e.g. "google_sheets") by building a suffix alias map from the live catalog.

Used by catalog_checker and auth_validator as a second normalization layer,
independent of semantic_intake, to guard against edge cases where apps_involved
was written without going through semantic_intake's Capa-1 normalization.
"""

import logging

from app.agent.shared.helpers.catalog_cache import get_catalog_apps

logger = logging.getLogger(__name__)


async def resolve_app_key(app: str) -> str:
    """
    Return the canonical nameApi key for `app`.

    - Already canonical (e.g. "google_sheets"): returned unchanged.
    - Known suffix (e.g. "sheets" → "google_sheets"): resolved via alias map.
    - Unrecognized: returned unchanged — let the caller handle not_found.
    """
    catalog_apps = await get_catalog_apps()
    catalog_set  = set(catalog_apps)

    if app in catalog_set:
        return app

    alias_map = {
        key.split("_")[-1]: key
        for key in catalog_set if "_" in key
    }
    resolved = alias_map.get(app, app)
    if resolved != app:
        logger.debug("[app_resolver] '%s' → '%s'", app, resolved)
    return resolved

