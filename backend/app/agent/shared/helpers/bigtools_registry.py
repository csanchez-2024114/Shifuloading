"""
Registry of available tools per app — used by bigtools_inspector.

`load_tools_context` is the primary entry point: it queries the MongoDB
collection `app_tools_catalog` first (5-min TTL cache), then falls back to
the static BIGTOOLS_REGISTRY dict below. This means adding a new tool to an
existing app no longer requires a deploy — insert a document in MongoDB and
the agent picks it up within 5 minutes.

Schema for app_tools_catalog:
  { "app": "gmail", "tools": ["listar_correos", "enviar_correo", ...] }
"""

import asyncio
import logging

from cachetools import TTLCache

logger = logging.getLogger(__name__)

_tools_cache: TTLCache = TTLCache(maxsize=50, ttl=300)  # 5-min TTL
_tools_lock = asyncio.Lock()

BIGTOOLS_REGISTRY: dict[str, list[str]] = {
    "gmail": [
        "listar_correos", "buscar_correo", "buscar_correos_por_remitente",
        "listar_correos_por_label", "buscar_correo_por_asunto", "enviar_correo",
        "crear_borrador", "enviar_borrador_por_asunto", "mover_correo_por_asunto",
        "marcar_como_no_leido", "crear_etiqueta", "gmail_reactivo",
    ],
    "drive": [
        "list_drive_files", "find_drive_file", "create_drive_folder",
        "create_drive_doc", "create_drive_sheet", "create_drive_slide",
        "delete_drive_file", "move_drive_file", "rename_drive_file",
    ],
    "sheets": [
        "search_sheets_files", "list_sheet_tabs", "get_sheet_cell",
        "read_sheet_range", "search_sheet_value", "count_sheet_rows",
        "get_sheet_row", "get_sheet_column", "write_sheet_cell",
        "write_sheet_range", "append_sheet_row", "append_sheet_column",
        "create_sheet_tab", "rename_sheet_tab", "clear_sheet_range",
    ],
    "docs": [
        "get_doc_content", "find_doc_by_name", "list_docs_by_names",
        "create_doc", "insert_text_in_doc", "change_doc_title",
        "replace_doc_text", "delete_doc_text_by_content", "insert_table_in_doc",
    ],
    "slides": [
        "get_presentation_content", "find_presentation_by_name",
        "list_presentations", "create_presentation", "insert_text_in_presentation",
        "replace_text_in_presentation", "add_slide", "duplicate_slide",
        "create_table", "share_presentation",
    ],
    "hubspot": [],
    "asana": [],
    "clickup": [],
    "facebook": [],
    "dropbox": [],
}

# El catalogo y los validadores usan google_sheets; este registro usa sheets. Sin traducir, el inspector concluia que
# Sheets "no tiene herramientas" y bloqueaba el turno mientras el contexto de plataforma listaba sus 15 acciones.
LEGACY_KEYS = {"google_drive": "drive", "google_docs": "docs", "google_sheets": "sheets", "google_slides": "slides"}


def registry_tools(app: str) -> list[str]:
    """Acciones del registro estatico para una app, con la clave del catalogo o la antigua."""
    key = (app or "").lower()
    return BIGTOOLS_REGISTRY.get(key) or BIGTOOLS_REGISTRY.get(LEGACY_KEYS.get(key, key), [])


async def load_tools_context(validated_apps: list[str]) -> str:
    """
    Build tools context string for the bigtools_inspector prompt.

    Tries MongoDB `app_tools_catalog` first (5-min TTL), falls back to
    the static BIGTOOLS_REGISTRY above if DB is unavailable or has no doc.
    """
    from app.core.mongo import mongo_manager
    db = mongo_manager.db
    lines = []
    for app in validated_apps:
        app_key = app.lower()
        async with _tools_lock:
            if app_key not in _tools_cache:
                tools = registry_tools(app_key)
                if db is not None:
                    try:
                        doc = await db["app_tools_catalog"].find_one(
                            {"app": {"$in": list({app_key, LEGACY_KEYS.get(app_key, app_key)})}}, {"tools": 1, "_id": 0}
                        )
                        if doc and isinstance(doc.get("tools"), list):
                            tools = doc["tools"]
                    except Exception as exc:
                        logger.warning("[bigtools_registry] DB load failed for %s: %s", app_key, exc)
                _tools_cache[app_key] = tools
            tools = _tools_cache[app_key]
        if tools:
            lines.append(f"  {app}: {', '.join(tools)}")
        else:
            lines.append(f"  {app}: (tools not yet implemented)")
    return "\n".join(lines) if lines else "  (no apps validated)"


def format_tools_context(validated_apps: list[str]) -> str:
    """Sync fallback — static dict only. Kept for backward compatibility."""
    lines = []
    for app in validated_apps:
        tools = registry_tools(app)
        if tools:
            lines.append(f"  {app}: {', '.join(tools)}")
        else:
            lines.append(f"  {app}: (tools not yet implemented)")
    return "\n".join(lines) if lines else "  (no apps validated)"
