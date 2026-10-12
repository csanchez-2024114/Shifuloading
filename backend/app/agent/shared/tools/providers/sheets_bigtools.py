from typing import List, Optional, Type, Any
from dataclasses import dataclass
from pydantic import BaseModel, Field
from app.tools.connectors.google_sheets import GoogleSheetsToolProvider, WriteRangeArgs
from app.core.db_utils import canonicalize_email


@dataclass
class BigTool:
    name: str
    description: str
    tool: Any
    args_schema: Optional[Type[BaseModel]] = None


def get_sheets_bigtools(
    user_id: str, user_email: str, active_accounts: Optional[dict] = None
) -> List[BigTool]:
    """
    Factory que genera todas las BigTools de Google Sheets para un usuario específico.

    Args:
        user_id: ID del usuario para buscar credenciales.
        user_email: Email del usuario (contexto).
        active_accounts: Mapa de `provider -> account_id` para la sesión actual.

    Returns:
        Lista de BigTools configuradas para ese usuario
    """
    account_id = active_accounts.get("google") if active_accounts else None
    provider = GoogleSheetsToolProvider(user_email=user_email, user_id=user_id, account_id=account_id)
    return [
        BigTool(
            name="search_sheets_files",
            description="Search for Google Sheets or Excel files in Drive by name.",
            tool=provider.get_tool_search_sheet(),
        ),
        BigTool(
            name="list_sheet_tabs",
            description="List all sheet tabs inside a Google Sheets file.",
            tool=provider.get_tool_list_sheets(),
        ),
        BigTool(
            name="get_sheet_cell",
            description="Get the exact value of a specific cell in a Google Sheet.",
            tool=provider.get_tool_get_cell(),
        ),
        BigTool(
            name="read_sheet_range",
            description="Read and return data contained in a specific range of a Google Sheet.",
            tool=provider.get_tool_read_range(),
        ),
        BigTool(
            name="search_sheet_value",
            description="Search for a text or numeric value across all cells of a sheet.",
            tool=provider.get_tool_search_value(),
        ),
        BigTool(
            name="count_sheet_rows",
            description="Count the number of rows containing data in a sheet.",
            tool=provider.get_tool_count_rows(),
        ),
        BigTool(
            name="get_sheet_row",
            description="Get all values from a specific row in a sheet.",
            tool=provider.get_tool_get_row(),
        ),
        BigTool(
            name="get_sheet_column",
            description="Get all values from a specific column in a sheet.",
            tool=provider.get_tool_get_column(),
        ),
        BigTool(
            name="get_sheet_occupied_cells",
            description="Return cells that contain data for a given file and sheet.",
            tool=provider.get_tool_get_occupied_cells(),
        ),
        BigTool(
            name="write_sheet_cell",
            description="Write a single value to a specific cell in a sheet.",
            tool=provider.get_tool_write_cell(),
        ),
        BigTool(
            name="write_sheet_range",
            description="Write a 2D matrix of values into a range in a Google Sheet.",
            tool=provider.get_tool_write_range(),
            args_schema=WriteRangeArgs,
        ),
        BigTool(
            name="append_sheet_row",
            description="Append a new row with values to the end of a sheet.",
            tool=provider.get_tool_append_row(),
        ),
        BigTool(
            name="append_sheet_column",
            description="Append a new column with values to the end of a sheet.",
            tool=provider.get_tool_append_column(),
        ),
        BigTool(
            name="create_sheet_tab",
            description="Create a new sheet/tab inside a spreadsheet.",
            tool=provider.get_tool_create_sheet(),
        ),
        BigTool(
            name="rename_sheet_tab",
            description="Rename an existing sheet/tab.",
            tool=provider.get_tool_rename_sheet(),
        ),
        BigTool(
            name="duplicate_sheet_tab",
            description="Duplicate a sheet/tab within the spreadsheet under a new name.",
            tool=provider.get_tool_duplicate_sheet(),
        ),
        BigTool(
            name="clear_sheet_range",
            description="Clear the contents of cells in a given range without deleting rows/columns.",
            tool=provider.get_tool_clear_range(),
        ),
    ]


def get_sheets_tools_by_category(
    user_email: str, category: str = "all"
) -> List[BigTool]:
    """
    Obtiene herramientas de Google Sheets filtradas por categoría.

    Args:
        user_email: Email del usuario
        category: "get" (consulta), "post" (escritura/modificación), "all" (todas)

    Returns:
        Lista de BigTools filtradas
    """
    all_tools = get_sheets_bigtools(user_email)
    if category == "all":
        return all_tools
    category_keywords = {
        "get": ["buscar", "listar", "obtener", "leer", "contar"],
        "post": ["escribir", "agregar", "crear", "renombrar", "duplicar", "limpiar"],
    }
    if category not in category_keywords:
        return all_tools
    keywords = category_keywords[category]
    filtered_tools = []
    for tool in all_tools:
        if any((keyword in tool.name.lower() for keyword in keywords)):
            filtered_tools.append(tool)
    return filtered_tools


def get_data_operation_tools(user_email: str) -> List[BigTool]:
    """
    Obtiene herramientas específicas para operaciones de datos en Google Sheets.
    Incluye: leer, escribir, buscar, contar filas, obtener filas/columnas.
    """
    all_tools = get_sheets_bigtools(user_email)
    data_tools_names = [
        "read_sheet_range",
        "write_sheet_cell",
        "write_sheet_range",
        "search_sheet_value",
        "count_sheet_rows",
        "get_sheet_row",
        "get_sheet_column",
        "get_sheet_occupied_cells",
    ]
    return [tool for tool in all_tools if tool.name in data_tools_names]


def get_sheet_management_tools(user_email: str) -> List[BigTool]:
    """
    Obtiene herramientas específicas para gestión de hojas en Google Sheets.
    Incluye: listar, crear, renombrar, duplicar hojas.
    """
    all_tools = get_sheets_bigtools(user_email)
    sheet_management_names = [
        "list_sheet_tabs",
        "create_sheet_tab",
        "rename_sheet_tab",
        "duplicate_sheet_tab",
    ]
    return [tool for tool in all_tools if tool.name in sheet_management_names]


def get_all_google_sheets_tools(user_email: str) -> List[BigTool]:
    """
    Obtiene todas las herramientas de Google Sheets.
    Esta función mantiene compatibilidad con versiones anteriores.
    """
    return get_sheets_bigtools(user_email)
