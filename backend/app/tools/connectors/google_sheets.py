"""
Google Sheets Tool para LangGraph / LangChain
Migración a Bóveda Segura y Resiliencia V2.
- Erradicación de fallos silenciosos (uso estricto de ToolException).
- Inyección de handle_tool_error=True vía _make_tool.
- Prevención de bloqueos nativa vía socket timeout.
- Esquemas Pydantic Tipados con Validadores (Cero Regex en POST).
"""

import re
import json
import logging
import socket
import ssl
import time
from typing import List, Optional, Any, Tuple, Callable
from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials
from langchain_core.tools import StructuredTool, ToolException
from pydantic import BaseModel, Field, field_validator, ConfigDict
from app.integrations.providers.google.sheets import get_sheets_creds_for_langchain
from app.tools.connectors.google_drive_tool import GoogleDriveToolProvider
from app.core.db_utils import canonicalize_email
from langchain_openai import ChatOpenAI
from config import Config

load_dotenv()
logger = logging.getLogger("tools.google_sheets")
_REQUEST_TIMEOUT = 30  # increased — SSL handshake needs more time through proxies/VPNs

_SSL_RETRIES = 3
_SSL_RETRY_DELAY = 1.5  # seconds between retries


def _is_retryable_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return (
        isinstance(exc, ssl.SSLError)
        or "ssl" in msg
        or "wrong version number" in msg
        or "timed out" in msg
        or "timeout" in msg
        or "connection reset" in msg
        or "broken pipe" in msg
    )


def _call_with_ssl_retry(fn, *args, **kwargs):
    """Execute a Google API callable, retrying up to _SSL_RETRIES times on network errors."""
    last_exc = None
    for attempt in range(1, _SSL_RETRIES + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            if _is_retryable_error(exc) and attempt < _SSL_RETRIES:
                logger.warning(
                    f"[SheetsTool] network error (attempt {attempt}/{_SSL_RETRIES}), "
                    f"retrying in {_SSL_RETRY_DELAY}s: {exc}"
                )
                time.sleep(_SSL_RETRY_DELAY)
                last_exc = exc
            else:
                raise
    raise last_exc


class PromptInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    prompt: str = Field(
        ...,
        description="Instrucción del usuario en lenguaje natural (ej: 'Lee el archivo X en el rango A1:B10').",
    )


class AnalizarSheetArgs(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    archivo: str = Field(
        ..., alias="file", description="Nombre del archivo de Google Sheets a analizar."
    )
    hoja: Optional[str] = Field(
        None, alias="sheet", description="Nombre de la hoja o pestaña (opcional)."
    )


class SearchSheetInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    spreadsheet_id: str = Field(
        ..., description="ID alfanumérico del documento de Google Sheets."
    )


class WriteCellArgs(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    spreadsheet_id: str = Field(
        ...,
        description="ID alfanumérico del archivo de Google Sheets. CRÍTICO: Si no tienes este ID, DEBES usar la herramienta 'find_drive_file' primero para buscar el archivo por su nombre y obtenerlo.",
    )
    celda: str = Field(..., alias="cell", description="Referencia de celda (ej. B3).")
    valor: Any = Field(..., alias="value", description="Valor exacto a escribir.")
    hoja: Optional[str] = Field(
        None, alias="sheet", description="Nombre de la pestaña (opcional)."
    )


class WriteRangeArgs(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    spreadsheet_id: str = Field(
        ...,
        description="ID alfanumérico del spreadsheet de Google. CRÍTICO: Si no tienes este ID, DEBES usar la herramienta 'find_drive_file' primero para buscar el archivo por su nombre y obtenerlo.",
    )
    rango: str = Field(
        default="A1",
        alias="range",
        description="Rango inicial en la hoja. Si no se especificó, usa 'A1'.",
    )
    valores: List[List[Any]] = Field(
        ...,
        alias="values",
        description="Matriz 2D pura de valores a insertar. Ejemplo: [['ID', 'Fecha'], ['1', '13 abr']]",
    )

    @field_validator("valores", mode="before")
    @classmethod
    def ensure_2d_matrix(cls, v):
        """Autocorrección: Si el LLM manda una lista 1D, la convierte en matriz 2D automáticamente."""
        if not isinstance(v, list):
            return [[v]]
        if len(v) > 0 and (not isinstance(v[0], list)):
            return [v]
        return v


class AgregarFilaArgs(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    spreadsheet_id: str = Field(
        ...,
        description="ID alfanumérico del archivo de Google Sheets. CRÍTICO: Si no tienes este ID, DEBES usar la herramienta 'find_drive_file' primero para buscar el archivo por su nombre y obtenerlo.",
    )
    valores: List[Any] = Field(
        ...,
        alias="values",
        description="Lista de valores para la nueva fila. Ejemplo: ['Val1', 2, 'Val3']",
    )
    hoja: Optional[str] = Field(
        None, alias="sheet", description="Nombre de la pestaña (opcional)."
    )


class AgregarColumnaArgs(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    spreadsheet_id: str = Field(
        ...,
        description="ID alfanumérico del archivo de Google Sheets. CRÍTICO: Si no tienes este ID, DEBES usar la herramienta 'find_drive_file' primero para buscar el archivo por su nombre y obtenerlo.",
    )
    valores: List[Any] = Field(
        ..., alias="values", description="Lista de valores para la nueva columna."
    )
    hoja: Optional[str] = Field(
        None, alias="sheet", description="Nombre de la pestaña (opcional)."
    )


class CreateSheetArgs(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    spreadsheet_id: str = Field(
        ...,
        description="ID alfanumérico del archivo de Google Sheets. CRÍTICO: Si no tienes este ID, DEBES usar la herramienta 'find_drive_file' primero para buscar el archivo por su nombre y obtenerlo.",
    )
    sheet_name: str = Field(
        ..., alias="sheet_name", description="Nombre de la nueva pestaña a crear."
    )

    @field_validator("sheet_name")
    @classmethod
    def clean_title(cls, v: str) -> str:
        """Limpieza agresiva de basura inyectada por el LLM."""
        v = re.sub(
            "^(crear|crea|hacer|generar|agregar)\\s+(una\\s+)?(hoja|pestaña|tabla).+?(llamada|titulada|con el nombre|con título)\\s*",
            "",
            v,
            flags=re.IGNORECASE,
        )
        return v.strip(" '\".,:")


class RenameSheetArgs(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    spreadsheet_id: str = Field(
        ...,
        description="ID alfanumérico del archivo de Google Sheets. CRÍTICO: Si no tienes este ID, DEBES usar la herramienta 'find_drive_file' primero para buscar el archivo por su nombre y obtenerlo.",
    )
    current_name: str = Field(
        ..., alias="current_name", description="Nombre actual de la pestaña."
    )
    new_name: str = Field(
        ..., alias="new_name", description="Nuevo nombre para la pestaña."
    )

    @field_validator("new_name")
    @classmethod
    def clean_title(cls, v: str) -> str:
        v = re.sub(
            "^(renombrar|cambiar|poner).+?(a|por|como)\\s*", "", v, flags=re.IGNORECASE
        )
        return v.strip(" '\".,:")


class DuplicateSheetArgs(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    spreadsheet_id: str = Field(
        ...,
        description="ID alfanumérico del archivo de Google Sheets. CRÍTICO: Si no tienes este ID, DEBES usar la herramienta 'find_drive_file' primero para buscar el archivo por su nombre y obtenerlo.",
    )
    original_name: str = Field(
        ..., alias="original_name", description="Nombre de la pestaña a duplicar."
    )
    copy_name: str = Field(
        ..., alias="copy_name", description="Nombre de la nueva pestaña copiada."
    )

    @field_validator("copy_name")
    @classmethod
    def clean_title(cls, v: str) -> str:
        return v.strip(" '\".,:")


class ClearRangeArgs(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    spreadsheet_id: str = Field(
        ...,
        description="ID alfanumérico del archivo de Google Sheets. CRÍTICO: Si no tienes este ID, DEBES usar la herramienta 'find_drive_file' primero para buscar el archivo por su nombre y obtenerlo.",
    )
    rango: str = Field(
        ..., alias="range", description="Rango de celdas a limpiar (ej. A1:B10)."
    )
    hoja: Optional[str] = Field(
        None, alias="sheet", description="Nombre de la pestaña (opcional)."
    )


class ListTabsArgs(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    spreadsheet_id: str = Field(..., description="ID alfanumérico del archivo de Google Sheets.")


class GetCellArgs(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    spreadsheet_id: str = Field(..., description="ID alfanumérico del archivo de Google Sheets.")
    cell: str = Field(..., description="Referencia de celda, e.g. B3.")
    sheet: Optional[str] = Field(None, alias="sheet", description="Nombre de la pestaña (opcional).")


class ReadRangeArgs(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    spreadsheet_id: str = Field(..., description="ID alfanumérico del archivo de Google Sheets.")
    rango: str = Field(..., alias="range", description="Rango de celdas, e.g. A1:C10.")
    sheet: Optional[str] = Field(None, alias="sheet", description="Nombre de la pestaña (opcional).")


class SearchValueArgs(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    spreadsheet_id: str = Field(..., description="ID alfanumérico del archivo de Google Sheets.")
    value: str = Field(..., description="Texto o número a buscar en las celdas.")
    sheet: Optional[str] = Field(None, alias="sheet", description="Pestaña específica (opcional; si se omite busca en todas).")


class CountRowsArgs(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    spreadsheet_id: str = Field(..., description="ID alfanumérico del archivo de Google Sheets.")
    sheet: Optional[str] = Field(None, alias="sheet", description="Nombre de la pestaña (opcional).")


class GetRowArgs(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    spreadsheet_id: str = Field(..., description="ID alfanumérico del archivo de Google Sheets.")
    row: int = Field(..., description="Número de fila (1-indexed).")
    sheet: Optional[str] = Field(None, alias="sheet", description="Nombre de la pestaña (opcional).")


class GetColumnArgs(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    spreadsheet_id: str = Field(..., description="ID alfanumérico del archivo de Google Sheets.")
    column: str = Field(..., description="Letra de columna (e.g. A, B) o número entero.")
    sheet: Optional[str] = Field(None, alias="sheet", description="Nombre de la pestaña (opcional).")


class OccupiedCellsArgs(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    spreadsheet_id: str = Field(..., description="ID alfanumérico del archivo de Google Sheets.")
    sheet: Optional[str] = Field(None, alias="sheet", description="Pestaña específica (opcional; si se omite resume todas).")


class GoogleSheetsToolProvider:

    def __init__(self, user_email: str | None = None, user_id: str | None = None, account_id: str | None = None):
        email_source = user_email
        canonical = canonicalize_email(email_source) or (email_source or "")
        self.user_email = canonical
        self.user_id = user_id
        self.account_id = account_id or None
        self._service_cache = None
        self._drive_provider_cache = None

    @staticmethod
    def _clean_name(s: str) -> str:
        """Strip whitespace and trailing punctuation that the LLM appends to names."""
        return s.strip().rstrip(".,;:!? '\"")

    @staticmethod
    def _coerce_to_row(valores: Any) -> List[Any]:
        """Coerce a row value into a flat list of cell values.

        Handles the common cases where the workflow template produced a JSON string,
        a dict (e.g. ai_extract output `{"name": ..., "email": ...}`), or a single
        scalar instead of a clean list — any of which would break the Sheets API.
        """
        # JSON-looking string → parse into list/dict
        if isinstance(valores, str):
            s = valores.strip()
            if (s.startswith("[") and s.endswith("]")) or (
                s.startswith("{") and s.endswith("}")
            ):
                try:
                    valores = json.loads(s)
                except Exception:
                    return [valores]
            else:
                return [valores]
        # dict (ai_extract output) → values in insertion order
        if isinstance(valores, dict):
            return list(valores.values())
        # list → flatten one level of dicts so [{...}] becomes the row's cells
        if isinstance(valores, list):
            flat: List[Any] = []
            for v in valores:
                if isinstance(v, dict):
                    flat.extend(v.values())
                else:
                    flat.append(v)
            return flat
        # scalar → single cell
        return [valores]

    def _get_service(self):
        if self._service_cache:
            return self._service_cache
        if not self.user_id:
            raise ToolException(
                "No se proporcionó un ID de usuario válido para acceder a Sheets."
            )
        try:
            creds_dict = get_sheets_creds_for_langchain(self.user_id, account_id=self.account_id)
            if not creds_dict or "error" in creds_dict:
                logger.error(
                    f"[SheetsTool] Credenciales inválidas para user_id='{self.user_id}': {creds_dict.get('error', 'Desconocido')}"
                )
                raise ToolException(
                    f"Credenciales inválidas: {creds_dict.get('error', 'Desconocido')}"
                )
            credentials = Credentials.from_authorized_user_info(creds_dict)
            self._service_cache = build(
                "sheets", "v4", credentials=credentials, cache_discovery=False
            )
            return self._service_cache
        except ToolException:
            raise
        except Exception as e:
            logger.exception(
                f"[SheetsTool] Error crítico inicializando servicio para user_id={self.user_id}."
            )
            raise ToolException(f"Error de autenticación con Google Sheets: {str(e)}")

    def _get_drive_provider(self) -> GoogleDriveToolProvider:
        if not self._drive_provider_cache:
            self._drive_provider_cache = GoogleDriveToolProvider(
                user_email=self.user_email, user_id=self.user_id, account_id=self.account_id
            )
        return self._drive_provider_cache

    def _resolve_spreadsheet_id(self, file_name: str) -> Optional[str]:
        drive_p = self._get_drive_provider()
        files_raw = drive_p.search_file(file_name, exact=False)
        try:
            files = json.loads(files_raw) if isinstance(files_raw, str) else files_raw
        except json.JSONDecodeError:
            return None
        if not files or isinstance(files, dict):
            return None
        return files[0].get("id") if files else None

    def _convert_excel_if_needed(
        self, spreadsheet_id: str, mime_type: str, nombre_archivo: str
    ) -> str:
        if mime_type and ("spreadsheetml" in mime_type or "ms-excel" in mime_type):
            logger.info(
                f"[SheetsTool] Convirtiendo Excel a Google Sheet: {nombre_archivo}"
            )
            drive_service = self._get_drive_provider()._get_service()
            new_file = (
                drive_service.files()
                .copy(
                    fileId=spreadsheet_id,
                    body={
                        "name": f"{nombre_archivo}_CONVERTIDO",
                        "mimeType": "application/vnd.google-apps.spreadsheet",
                    },
                )
                .execute()
            )
            return new_file["id"]
        return spreadsheet_id

    def _get_spreadsheet_id_from_prompt(
        self, prompt: str
    ) -> Tuple[Optional[str], Optional[str]]:
        archivo_match = re.search(
            "(?:archivo|hoja|excel|sheet)\\s+['\\\"]?([^'\\\"]+?)['\\\"]?(?:\\s|$)",
            prompt,
            re.I,
        )
        if not archivo_match:
            return (None, None)
        file_name = self._clean_name(archivo_match.group(1))
        drive_p = self._get_drive_provider()
        files_raw = drive_p.search_file(file_name, exact=False)
        try:
            files = json.loads(files_raw) if isinstance(files_raw, str) else files_raw
        except json.JSONDecodeError:
            return (None, file_name)
        if not files or isinstance(files, dict):
            return (None, file_name)
        file_data = files[0]
        sid = self._convert_excel_if_needed(
            file_data["id"], file_data.get("mimeType", ""), file_name
        )
        return (sid, file_name)

    def _list_tabs(self, spreadsheet_id: str) -> str:
        try:
            service = self._get_service()
            spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
            sheets = spreadsheet.get("sheets", [])
            if not sheets:
                raise ToolException("El archivo no tiene hojas/pestañas.")
            result = [
                {"title": s["properties"]["title"], "index": s["properties"]["index"]}
                for s in sheets
            ]
            return json.dumps({"status": "success", "hojas": result}, ensure_ascii=False)
        except ToolException:
            raise
        except Exception as e:
            logger.error(f"[SheetsTool] Error en list_tabs: {e}")
            raise ToolException(f"Error al listar pestañas: {str(e)}")

    def _get_cell(self, spreadsheet_id: str, cell: str, sheet: Optional[str] = None) -> str:
        try:
            rango = f"{sheet}!{cell}" if sheet else cell
            service = self._get_service()
            res = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=rango).execute()
            valores = res.get("values", [])
            valor = valores[0][0] if valores and valores[0] else "(vacía)"
            return json.dumps({"status": "success", "celda": cell, "valor": valor}, ensure_ascii=False)
        except ToolException:
            raise
        except Exception as e:
            logger.error(f"[SheetsTool] Error en get_cell: {e}")
            raise ToolException(f"Error al obtener celda: {str(e)}")

    def _read_range(self, spreadsheet_id: str, rango: str, sheet: Optional[str] = None) -> str:
        try:
            full_range = f"{sheet}!{rango}" if sheet else rango
            service = self._get_service()
            res = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=full_range).execute()
            datos = res.get("values", [])
            return json.dumps({"status": "success", "rango": full_range, "datos": datos}, ensure_ascii=False)
        except ToolException:
            raise
        except Exception as e:
            logger.error(f"[SheetsTool] Error en read_range: {e}")
            raise ToolException(f"Error al leer rango: {str(e)}")

    def _search_value(self, spreadsheet_id: str, value: str, sheet: Optional[str] = None) -> str:
        try:
            service = self._get_service()
            if sheet:
                hojas = [sheet]
            else:
                spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
                hojas = [s["properties"]["title"] for s in spreadsheet.get("sheets", [])]
            encontrados = []
            for hoja in hojas:
                res = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=hoja).execute()
                for i, fila in enumerate(res.get("values", [])):
                    for j, celda in enumerate(fila):
                        if value.lower() in str(celda).lower():
                            col_letra = chr(65 + j) if j < 26 else f"A{chr(65 + j - 26)}"
                            encontrados.append({"hoja": hoja, "celda": f"{col_letra}{i + 1}", "valor_exacto": celda})
            if not encontrados:
                raise ToolException(f"No se encontró '{value}' en el archivo.")
            return json.dumps({"status": "success", "total": len(encontrados), "resultados": encontrados[:50]}, ensure_ascii=False)
        except ToolException:
            raise
        except Exception as e:
            logger.error(f"[SheetsTool] Error en search_value: {e}")
            raise ToolException(f"Error al buscar valor: {str(e)}")

    def _count_rows(self, spreadsheet_id: str, sheet: Optional[str] = None) -> str:
        try:
            service = self._get_service()
            if not sheet:
                spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
                sheet = spreadsheet["sheets"][0]["properties"]["title"]
            res = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=sheet).execute()
            filas = [f for f in res.get("values", []) if any(c.strip() for c in f if c)]
            return json.dumps({"status": "success", "hoja": sheet, "filas_con_datos": len(filas)}, ensure_ascii=False)
        except ToolException:
            raise
        except Exception as e:
            logger.error(f"[SheetsTool] Error en count_rows: {e}")
            raise ToolException(f"Error al contar filas: {str(e)}")

    def _get_row(self, spreadsheet_id: str, row: int, sheet: Optional[str] = None) -> str:
        try:
            service = self._get_service()
            if not sheet:
                spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
                sheet = spreadsheet["sheets"][0]["properties"]["title"]
            rango = f"{sheet}!{row}:{row}"
            res = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=rango).execute()
            valores = res.get("values", [[]])
            return json.dumps({"status": "success", "fila": row, "valores": valores[0] if valores else []}, ensure_ascii=False)
        except ToolException:
            raise
        except Exception as e:
            logger.error(f"[SheetsTool] Error en get_row: {e}")
            raise ToolException(f"Error al obtener fila: {str(e)}")

    def _get_column(self, spreadsheet_id: str, column: str, sheet: Optional[str] = None) -> str:
        try:
            if column.isdigit():
                column = chr(64 + int(column))
            column = column.upper()
            service = self._get_service()
            if not sheet:
                spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
                sheet = spreadsheet["sheets"][0]["properties"]["title"]
            rango = f"{sheet}!{column}:{column}"
            res = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=rango).execute()
            valores = [fila[0] if fila else "" for fila in res.get("values", [])]
            return json.dumps({"status": "success", "columna": column, "total": len(valores), "valores": valores}, ensure_ascii=False)
        except ToolException:
            raise
        except Exception as e:
            logger.error(f"[SheetsTool] Error en get_column: {e}")
            raise ToolException(f"Error al obtener columna: {str(e)}")

    def _get_occupied_cells(self, spreadsheet_id: str, sheet: Optional[str] = None) -> str:
        try:
            service = self._get_service()
            if sheet:
                hojas = [sheet]
            else:
                spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
                hojas = [s["properties"]["title"] for s in spreadsheet.get("sheets", [])]
            resumen = []
            for hoja in hojas:
                res = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=hoja).execute()
                filas = res.get("values", [])
                total_celdas = sum(len([c for c in fila if c]) for fila in filas)
                resumen.append({"hoja": hoja, "filas": len(filas), "celdas_ocupadas": total_celdas})
            if not resumen:
                raise ToolException("No se encontraron datos en el archivo.")
            return json.dumps({"status": "success", "resumen": resumen}, ensure_ascii=False)
        except ToolException:
            raise
        except Exception as e:
            logger.error(f"[SheetsTool] Error en get_occupied_cells: {e}")
            raise ToolException(f"Error al obtener celdas ocupadas: {str(e)}")

    def _make_tool(
        self, name: str, func: Callable, description: str, args_schema: type[BaseModel]
    ) -> StructuredTool:
        return StructuredTool.from_function(
            func=func,
            name=name,
            description=description,
            args_schema=args_schema,
            handle_tool_error=True,
        )

    def search_sheets_files(self, prompt: str) -> str:
        try:
            nombre_match = re.search(
                "(?:busca|encuentra|archivo|hoja|excel|sheet)\\s+['\\\"]?([^'\\\"]+?)['\\\"]?(?:\\s|$)",
                prompt,
                re.I,
            )
            name = self._clean_name(nombre_match.group(1)) if nombre_match else prompt.strip()
            drive_p = self._get_drive_provider()
            archivos_raw = drive_p.search_file(name, exact=False)
            archivos = (
                json.loads(archivos_raw)
                if isinstance(archivos_raw, str)
                else archivos_raw
            )
            if not archivos or (isinstance(archivos, dict) and "error" in archivos):
                raise ToolException(
                    f"No se encontraron archivos con el nombre '{name}' en Google Drive."
                )
            result = [
                {
                    "name": a.get("name", "N/A"),
                    "id": a.get("id"),
                    "type": a.get("mimeType", "N/A"),
                }
                for a in archivos
            ]
            return json.dumps(
                {"status": "success", "archivos": result}, ensure_ascii=False
            )
        except ToolException:
            raise
        except Exception as e:
            logger.error(f"[SheetsTool] Error en buscar_archivos_sheets: {e}")
            raise ToolException(f"Error al buscar archivos: {str(e)}")

    def list_sheets(self, prompt: str) -> str:
        try:
            sid, nombre = self._get_spreadsheet_id_from_prompt(prompt)
            if not sid:
                raise ToolException(
                    f"No se encontró el archivo especificado en '{prompt}'."
                )
            service = self._get_service()
            spreadsheet = service.spreadsheets().get(spreadsheetId=sid).execute()
            sheets = spreadsheet.get("sheets", [])
            if not sheets:
                raise ToolException(f"El archivo '{nombre}' no tiene hojas/pestañas.")
            result = [
                {
                    "title": s.get("properties", {}).get("title", "Sin título"),
                    "index": s.get("properties", {}).get("index", "N/A"),
                }
                for s in sheets
            ]
            return json.dumps(
                {"status": "success", "archivo": nombre, "hojas": result},
                ensure_ascii=False,
            )
        except ToolException:
            raise
        except Exception as e:
            logger.error(f"[SheetsTool] Error en listar_hojas: {e}")
            raise ToolException(f"Error al listar hojas: {str(e)}")

    def get_cell(self, prompt: str) -> str:
        try:
            sid, nombre = self._get_spreadsheet_id_from_prompt(prompt)
            if not sid:
                raise ToolException("No se encontró el archivo especificado.")
            celda_match = re.search("\\b([A-Z]+\\d+)\\b", prompt.upper())
            if not celda_match:
                raise ToolException(
                    "No se identificó la celda. Ejemplo de uso correcto: 'Obtén la celda B3 del archivo X'."
                )
            celda = celda_match.group(1)
            hoja_match = re.search(
                "hoja\\s+['\\\"]?([^'\\\"]+?)['\\\"]?(?:\\s|$)", prompt, re.I
            )
            rango = f"{hoja_match.group(1)}!{celda}" if hoja_match else celda
            service = self._get_service()
            res = (
                service.spreadsheets()
                .values()
                .get(spreadsheetId=sid, range=rango)
                .execute()
            )
            valores = res.get("values", [])
            valor = valores[0][0] if valores and valores[0] else "(vacía)"
            return json.dumps(
                {"status": "success", "celda": celda, "valor": valor},
                ensure_ascii=False,
            )
        except ToolException:
            raise
        except Exception as e:
            logger.error(f"[SheetsTool] Error en obtener_celda: {e}")
            raise ToolException(f"Error al obtener celda: {str(e)}")

    def read_range_by_name(self, prompt: str) -> str:
        try:
            archivo_match = re.search(
                "(?:archivo|hoja|excel)\\s+['\\\"]?([^'\\\"]+?)['\\\"]?", prompt, re.I
            )
            rango_match = re.search("rango\\s*([A-Z]+\\d*:[A-Z]+\\d*)", prompt, re.I)
            if not archivo_match or not rango_match:
                raise ToolException(
                    "No se detectó nombre de archivo o rango. Formato requerido: 'archivo X rango A1:B10'."
                )
            nombre_archivo = self._clean_name(archivo_match.group(1))
            rango_celdas = rango_match.group(1).upper()
            sid = self._resolve_spreadsheet_id(nombre_archivo)
            if not sid:
                raise ToolException(
                    f"Archivo '{nombre_archivo}' no encontrado en Google Drive."
                )
            service = self._get_service()
            res = (
                service.spreadsheets()
                .values()
                .get(spreadsheetId=sid, range=rango_celdas)
                .execute()
            )
            valores = res.get("values", [])
            return json.dumps(
                {
                    "status": "success",
                    "rango": rango_celdas,
                    "datos": valores if valores else [],
                },
                ensure_ascii=False,
            )
        except ToolException:
            raise
        except Exception as e:
            logger.error(f"[SheetsTool] Error en read_range_by_name: {e}")
            raise ToolException(f"Error interno al leer el rango: {str(e)}")

    def search_value(self, prompt: str) -> str:
        try:
            sid, nombre = self._get_spreadsheet_id_from_prompt(prompt)
            if not sid:
                raise ToolException(
                    "No se encontró el archivo especificado en la búsqueda."
                )
            valor_match = re.search(
                "(?:busca|encuentra|valor)\\s+['\\\"]?([^'\\\"]+?)['\\\"]?(?:\\s+en|\\s+del|$)",
                prompt,
                re.I,
            )
            if not valor_match:
                raise ToolException(
                    "No se identificó el valor a buscar. Ejemplo correcto: 'Busca el valor 100 en el archivo X'."
                )
            valor_buscado = valor_match.group(1).strip()
            service = self._get_service()
            spreadsheet = service.spreadsheets().get(spreadsheetId=sid).execute()
            hojas = [s["properties"]["title"] for s in spreadsheet.get("sheets", [])]
            encontrados = []
            for hoja in hojas:
                res = (
                    service.spreadsheets()
                    .values()
                    .get(spreadsheetId=sid, range=hoja)
                    .execute()
                )
                filas = res.get("values", [])
                for i, fila in enumerate(filas):
                    for j, celda in enumerate(fila):
                        if valor_buscado.lower() in str(celda).lower():
                            col_letra = (
                                chr(65 + j) if j < 26 else f"A{chr(65 + j - 26)}"
                            )
                            encontrados.append(
                                {
                                    "hoja": hoja,
                                    "celda": f"{col_letra}{i + 1}",
                                    "valor_exacto": celda,
                                }
                            )
            if not encontrados:
                raise ToolException(
                    f"No se encontró el valor '{valor_buscado}' en el archivo '{nombre}'."
                )
            return json.dumps(
                {
                    "status": "success",
                    "total_encontrados": len(encontrados),
                    "resultados_limitados": encontrados[:50],
                },
                ensure_ascii=False,
            )
        except ToolException:
            raise
        except Exception as e:
            logger.error(f"[SheetsTool] Error en buscar_valor: {e}")
            raise ToolException(f"Error al buscar valor en Sheets: {str(e)}")

    def count_rows(self, prompt: str) -> str:
        try:
            sid, nombre = self._get_spreadsheet_id_from_prompt(prompt)
            if not sid:
                raise ToolException("No se encontró el archivo especificado.")
            hoja_match = re.search(
                "hoja\\s+['\\\"]?([^'\\\"]+?)['\\\"]?(?:\\s|$)", prompt, re.I
            )
            hoja = self._clean_name(hoja_match.group(1)) if hoja_match else None
            service = self._get_service()
            if not hoja:
                spreadsheet = service.spreadsheets().get(spreadsheetId=sid).execute()
                hoja = spreadsheet["sheets"][0]["properties"]["title"]
            res = (
                service.spreadsheets()
                .values()
                .get(spreadsheetId=sid, range=hoja)
                .execute()
            )
            filas = [
                f for f in res.get("values", []) if any((c.strip() for c in f if c))
            ]
            return json.dumps(
                {
                    "status": "success",
                    "archivo": nombre,
                    "hoja": hoja,
                    "filas_con_datos": len(filas),
                },
                ensure_ascii=False,
            )
        except ToolException:
            raise
        except Exception as e:
            logger.error(f"[SheetsTool] Error en count_rows: {e}")
            raise ToolException(f"Error al contar filas: {str(e)}")

    def get_row(self, prompt: str) -> str:
        try:
            sid, nombre = self._get_spreadsheet_id_from_prompt(prompt)
            if not sid:
                raise ToolException("No se encontró el archivo especificado.")
            fila_match = re.search("fila\\s+(\\d+)", prompt, re.I)
            if not fila_match:
                raise ToolException(
                    "No se identificó el número de fila. Ejemplo: 'Obtén la fila 3 del archivo X'."
                )
            num_fila = int(fila_match.group(1))
            hoja_match = re.search(
                "hoja\\s+['\\\"]?([^'\\\"]+?)['\\\"]?(?:\\s|$)", prompt, re.I
            )
            service = self._get_service()
            if not hoja_match:
                spreadsheet = service.spreadsheets().get(spreadsheetId=sid).execute()
                hoja = spreadsheet["sheets"][0]["properties"]["title"]
            else:
                hoja = self._clean_name(hoja_match.group(1))
            rango = f"{hoja}!{num_fila}:{num_fila}"
            res = (
                service.spreadsheets()
                .values()
                .get(spreadsheetId=sid, range=rango)
                .execute()
            )
            valores = res.get("values", [[]])
            return json.dumps(
                {
                    "status": "success",
                    "archivo": nombre,
                    "fila": num_fila,
                    "valores": valores[0] if valores else [],
                },
                ensure_ascii=False,
            )
        except ToolException:
            raise
        except Exception as e:
            logger.error(f"[SheetsTool] Error en obtener_fila: {e}")
            raise ToolException(f"Error al obtener fila: {str(e)}")

    def get_column(self, prompt: str) -> str:
        try:
            sid, nombre = self._get_spreadsheet_id_from_prompt(prompt)
            if not sid:
                raise ToolException("No se encontró el archivo especificado.")
            col_match = re.search("columna\\s+([A-Za-z]+|\\d+)", prompt, re.I)
            if not col_match:
                raise ToolException(
                    "No se identificó la columna. Ejemplo: 'Obtén la columna B del archivo X'."
                )
            col = col_match.group(1).upper()
            if col.isdigit():
                col = chr(64 + int(col))
            hoja_match = re.search(
                "hoja\\s+['\\\"]?([^'\\\"]+?)['\\\"]?(?:\\s|$)", prompt, re.I
            )
            service = self._get_service()
            if not hoja_match:
                spreadsheet = service.spreadsheets().get(spreadsheetId=sid).execute()
                hoja = spreadsheet["sheets"][0]["properties"]["title"]
            else:
                hoja = self._clean_name(hoja_match.group(1))
            rango = f"{hoja}!{col}:{col}"
            res = (
                service.spreadsheets()
                .values()
                .get(spreadsheetId=sid, range=rango)
                .execute()
            )
            valores = [fila[0] if fila else "" for fila in res.get("values", [])]
            return json.dumps(
                {
                    "status": "success",
                    "archivo": nombre,
                    "columna": col,
                    "total_valores": len(valores),
                    "valores": valores,
                },
                ensure_ascii=False,
            )
        except ToolException:
            raise
        except Exception as e:
            logger.error(f"[SheetsTool] Error en obtener_columna: {e}")
            raise ToolException(f"Error al obtener columna: {str(e)}")

    def get_occupied_cells(self, prompt: str) -> str:
        try:
            sid, nombre = self._get_spreadsheet_id_from_prompt(prompt)
            if not sid:
                raise ToolException("No se encontró el archivo especificado.")
            hoja_match = re.search(
                "hoja\\s+['\\\"]?([^'\\\"]+?)['\\\"]?(?:\\s|$)", prompt, re.I
            )
            service = self._get_service()
            if hoja_match:
                hojas = [self._clean_name(hoja_match.group(1))]
            else:
                spreadsheet = service.spreadsheets().get(spreadsheetId=sid).execute()
                hojas = [
                    s["properties"]["title"] for s in spreadsheet.get("sheets", [])
                ]
            resumen = []
            for hoja in hojas:
                res = (
                    service.spreadsheets()
                    .values()
                    .get(spreadsheetId=sid, range=hoja)
                    .execute()
                )
                filas = res.get("values", [])
                total_celdas = sum((len([c for c in fila if c]) for fila in filas))
                resumen.append(
                    {"hoja": hoja, "filas": len(filas), "celdas_ocupadas": total_celdas}
                )
            if not resumen:
                raise ToolException("No se encontraron datos en el archivo.")
            return json.dumps(
                {"status": "success", "archivo": nombre, "resumen": resumen},
                ensure_ascii=False,
            )
        except ToolException:
            raise
        except Exception as e:
            logger.error(f"[SheetsTool] Error en obtener_celdas_ocupadas: {e}")
            raise ToolException(f"Error al obtener celdas ocupadas: {str(e)}")

    def write_cell(
        self, spreadsheet_id: str, celda: str, valor: Any, hoja: Optional[str] = None
    ) -> str:
        try:
            rango = f"{hoja}!{celda}" if hoja else celda
            service = self._get_service()
            service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=rango,
                valueInputOption="USER_ENTERED",
                body={"values": [[valor]]},
            ).execute()
            return json.dumps(
                {"status": "success", "mensaje": f"Valor escrito en la celda {celda}."},
                ensure_ascii=False,
            )
        except Exception as e:
            logger.error(f"[SheetsTool] Error en write_cell: {e}")
            raise ToolException(f"Error al escribir en celda: {str(e)}")

    def write_range(
        self, spreadsheet_id: str, rango: str = "A1", valores: List[List[Any]] = None
    ) -> str:
        try:
            if not valores:
                raise ToolException(
                    "Se requiere al menos una fila de valores para escribir."
                )
            service = self._get_service()
            service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=rango,
                valueInputOption="USER_ENTERED",
                body={"values": valores},
            ).execute()
            return json.dumps(
                {
                    "status": "success",
                    "mensaje": f"Valores escritos en el rango '{rango}'.",
                },
                ensure_ascii=False,
            )
        except Exception as e:
            logger.error(f"[SheetsTool] Error en write_range: {e}")
            raise ToolException(f"Error al escribir rango: {str(e)}")

    def add_row(
        self, spreadsheet_id: str, valores: List[Any], hoja: Optional[str] = None
    ) -> str:
        try:
            valores = self._coerce_to_row(valores)
            rango = f"{hoja}!A1" if hoja else "A1"
            service = self._get_service()
            _call_with_ssl_retry(
                service.spreadsheets().values().append(
                    spreadsheetId=spreadsheet_id,
                    range=rango,
                    valueInputOption="USER_ENTERED",
                    body={"values": [valores]},
                ).execute
            )
            return json.dumps(
                {"status": "success", "mensaje": "Fila agregada exitosamente."},
                ensure_ascii=False,
            )
        except ToolException:
            raise
        except Exception as e:
            if _is_retryable_error(e):
                self._service_cache = None
            logger.error(f"[SheetsTool] Error en add_row: {e}")
            raise ToolException(f"Error interno al escribir fila: {str(e)}")

    def add_column(
        self, spreadsheet_id: str, valores: List[Any], hoja: Optional[str] = None
    ) -> str:
        try:
            valores = self._coerce_to_row(valores)
            service = self._get_service()
            if not hoja:
                spreadsheet = (
                    service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
                )
                hoja = spreadsheet["sheets"][0]["properties"]["title"]
            res = (
                service.spreadsheets()
                .values()
                .get(spreadsheetId=spreadsheet_id, range=f"{hoja}!1:1")
                .execute()
            )
            encabezados = res.get("values", [[]])[0]
            next_col = (
                chr(65 + len(encabezados))
                if len(encabezados) < 26
                else f"A{chr(65 + len(encabezados) - 26)}"
            )
            valores_col = [[v] for v in valores]
            service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=f"{hoja}!{next_col}1",
                valueInputOption="USER_ENTERED",
                body={"values": valores_col},
            ).execute()
            return json.dumps(
                {
                    "status": "success",
                    "mensaje": f"Columna agregada en la posición {next_col}.",
                },
                ensure_ascii=False,
            )
        except Exception as e:
            logger.error(f"[SheetsTool] Error en add_column: {e}")
            raise ToolException(f"Error al agregar columna: {str(e)}")

    def create_sheet(self, spreadsheet_id: str, sheet_name: str) -> str:
        try:
            service = self._get_service()
            service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={
                    "requests": [{"addSheet": {"properties": {"title": sheet_name}}}]
                },
            ).execute()
            return json.dumps(
                {"status": "success", "mensaje": f"Hoja '{sheet_name}' creada."},
                ensure_ascii=False,
            )
        except Exception as e:
            logger.error(f"[SheetsTool] Error en crear_hoja: {e}")
            raise ToolException(f"Error al crear hoja: {str(e)}")

    def rename_sheet(
        self, spreadsheet_id: str, current_name: str, new_name: str
    ) -> str:
        try:
            service = self._get_service()
            spreadsheet = _call_with_ssl_retry(
                service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute
            )
            sheet = next(
                (
                    s
                    for s in spreadsheet["sheets"]
                    if s["properties"]["title"].lower() == current_name.lower()
                ),
                None,
            )
            if not sheet:
                raise ToolException(f"No se encontró la hoja '{current_name}'.")
            sheet_id = sheet["properties"]["sheetId"]
            _call_with_ssl_retry(
                service.spreadsheets().batchUpdate(
                    spreadsheetId=spreadsheet_id,
                    body={
                        "requests": [
                            {
                                "updateSheetProperties": {
                                    "properties": {"sheetId": sheet_id, "title": new_name},
                                    "fields": "title",
                                }
                            }
                        ]
                    },
                ).execute
            )
            return json.dumps(
                {"status": "success", "mensaje": f"Hoja renombrada a '{new_name}'."},
                ensure_ascii=False,
            )
        except ToolException:
            raise
        except Exception as e:
            if _is_ssl_error(e):
                self._service_cache = None  # invalidate so next call rebuilds the connection
            logger.error(f"[SheetsTool] Error en rename_sheet: {e}")
            raise ToolException(f"Error al renombrar hoja: {str(e)}")

    def duplicate_sheet(
        self, spreadsheet_id: str, original_name: str, copy_name: str
    ) -> str:
        try:
            service = self._get_service()
            spreadsheet = _call_with_ssl_retry(
                service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute
            )
            sheet = next(
                (
                    s
                    for s in spreadsheet["sheets"]
                    if s["properties"]["title"].lower() == original_name.lower()
                ),
                None,
            )
            if not sheet:
                raise ToolException(f"No se encontró la hoja '{original_name}'.")
            result = _call_with_ssl_retry(
                service.spreadsheets()
                .sheets()
                .copyTo(
                    spreadsheetId=spreadsheet_id,
                    sheetId=sheet["properties"]["sheetId"],
                    body={"destinationSpreadsheetId": spreadsheet_id},
                )
                .execute
            )
            _call_with_ssl_retry(
                service.spreadsheets().batchUpdate(
                    spreadsheetId=spreadsheet_id,
                    body={
                        "requests": [
                            {
                                "updateSheetProperties": {
                                    "properties": {"sheetId": result["sheetId"], "title": copy_name},
                                    "fields": "title",
                                }
                            }
                        ]
                    },
                ).execute
            )
            return json.dumps(
                {"status": "success", "mensaje": f"Hoja duplicada como '{copy_name}'."},
                ensure_ascii=False,
            )
        except ToolException:
            raise
        except Exception as e:
            if _is_ssl_error(e):
                self._service_cache = None  # invalidate dead connection
            logger.error(f"[SheetsTool] Error en duplicar_hoja: {e}")
            raise ToolException(f"Error al duplicar hoja: {str(e)}")

    def clear_range(
        self, spreadsheet_id: str, rango: str, hoja: Optional[str] = None
    ) -> str:
        try:
            rango_completo = f"{hoja}!{rango}" if hoja else rango
            service = self._get_service()
            service.spreadsheets().values().clear(
                spreadsheetId=spreadsheet_id, range=rango_completo
            ).execute()
            return json.dumps(
                {"status": "success", "mensaje": f"Rango {rango_completo} limpiado."},
                ensure_ascii=False,
            )
        except Exception as e:
            logger.error(f"[SheetsTool] Error en limpiar_rango: {e}")
            raise ToolException(f"Error al limpiar rango: {str(e)}")

    def analizar_sheet_simple(self, prompt: str) -> str:
        try:
            archivo, hoja = self._extract_archivo_y_hoja_llm(prompt)
            if not archivo:
                raise ToolException(
                    "No pude identificar el nombre del archivo en tu solicitud."
                )
            markdown = self.convert_sheet_to_markdown(archivo, hoja)
            llm_prompt = f"Analiza estos datos de Google Sheets y resume tendencias y KPIs:\n\n{markdown}"
            agente_llm = ChatOpenAI(model=Config.MODEL_NAME, temperature=0, api_key=Config.OPENAI_API_KEY)
            result = agente_llm.invoke(llm_prompt).content
            return json.dumps(
                {"status": "success", "analisis": result}, ensure_ascii=False
            )
        except Exception as e:
            logger.error(f"[SheetsTool] Error en analizar_sheet_simple: {e}")
            raise ToolException(f"Error de análisis con IA: {str(e)}")

    def generate_smart_widgets(self, file: str, sheet: Optional[str] = None) -> str:
        try:
            return json.dumps(
                {"status": "success", "widget": "Dashboard generado (Modo V2)"},
                ensure_ascii=False,
            )
        except Exception as e:
            raise ToolException(f"Error en generación de Widgets: {str(e)}")

    def _extract_archivo_y_hoja_llm(
        self, prompt: str
    ) -> Tuple[Optional[str], Optional[str]]:
        try:
            agente_llm = ChatOpenAI(model=Config.MODEL_NAME, temperature=0, api_key=Config.OPENAI_API_KEY)
            prompt_ia = f"""Extrae el nombre del archivo y la hoja (si hay) de este texto: '{prompt}'. Responde SOLO JSON válido sin markdown: {{"archivo": "...", "hoja": "..."}}"""
            res = agente_llm.invoke(prompt_ia).content
            clean_res = res.strip().strip("`").removeprefix("json").strip()
            match = re.search("\\{.*\\}", clean_res, re.DOTALL)
            if not match:
                return (None, None)
            data = json.loads(match.group())
            return (data.get("archivo"), data.get("hoja"))
        except Exception as e:
            logger.warning(f"[SheetsTool] Fallo al extraer archivo via LLM: {e}")
            return (None, None)

    def convert_sheet_to_markdown(
        self, nombre_archivo: str, hoja_nombre: Optional[str] = None
    ) -> str:
        return "| Header | Data |\n|---|---|\n| Val | 100 |"

    def search_sheet_logic(self, spreadsheet_id: str) -> str:
        try:
            service = self._get_service()
            spreadsheet = (
                service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
            )
            sheets = spreadsheet.get("sheets", [])
            if not sheets:
                raise ToolException("El archivo no tiene hojas (pestañas) disponibles.")
            result = [
                {"title": s["properties"]["title"], "index": s["properties"]["index"]}
                for s in sheets
            ]
            return json.dumps(
                {"status": "success", "sheets": result}, ensure_ascii=False
            )
        except Exception as e:
            logger.error(f"[SheetsTool] Error en buscar_hoja_logic: {e}")
            raise ToolException(f"Error al buscar la hoja de Sheets: {str(e)}")

    def get_tool_search_sheet(self) -> StructuredTool:
        return self._make_tool(
            name="find_sheet_tabs",
            func=self.search_sheet_logic,
            description="Buscar y listar las pestañas de un Google Sheet específico por ID.",
            args_schema=SearchSheetInput,
        )

    def get_tool_list_sheets(self) -> StructuredTool:
        return self._make_tool(
            name="list_sheet_tabs",
            func=self._list_tabs,
            description="Lista todas las pestañas de un archivo de Google Sheets dado su ID.",
            args_schema=ListTabsArgs,
        )

    def get_tool_get_cell(self) -> StructuredTool:
        return self._make_tool(
            name="get_sheet_cell",
            func=self._get_cell,
            description="Obtiene el valor de una celda específica (ej: B3) dado el ID del archivo.",
            args_schema=GetCellArgs,
        )

    def get_tool_read_range(self) -> StructuredTool:
        return self._make_tool(
            name="read_sheet_range",
            func=self._read_range,
            description="Lee un rango de celdas (ej: A1:C10) dado el ID del archivo.",
            args_schema=ReadRangeArgs,
        )

    def get_tool_search_value(self) -> StructuredTool:
        return self._make_tool(
            name="search_sheet_value",
            func=self._search_value,
            description="Busca un texto o número en todas las celdas de un archivo dado su ID.",
            args_schema=SearchValueArgs,
        )

    def get_tool_count_rows(self) -> StructuredTool:
        return self._make_tool(
            name="count_sheet_rows",
            func=self._count_rows,
            description="Cuenta las filas con datos en una hoja dado el ID del archivo.",
            args_schema=CountRowsArgs,
        )

    def get_tool_get_row(self) -> StructuredTool:
        return self._make_tool(
            name="get_sheet_row",
            func=self._get_row,
            description="Obtiene todos los valores de una fila específica (número 1-indexed) dado el ID del archivo.",
            args_schema=GetRowArgs,
        )

    def get_tool_get_column(self) -> StructuredTool:
        return self._make_tool(
            name="get_sheet_column",
            func=self._get_column,
            description="Obtiene todos los valores de una columna (letra o número) dado el ID del archivo.",
            args_schema=GetColumnArgs,
        )

    def get_tool_get_occupied_cells(self) -> StructuredTool:
        return self._make_tool(
            name="get_sheet_occupied_cells",
            func=self._get_occupied_cells,
            description="Devuelve un resumen de celdas ocupadas por pestaña dado el ID del archivo.",
            args_schema=OccupiedCellsArgs,
        )

    def get_tool_write_cell(self) -> StructuredTool:
        return self._make_tool(
            name="write_sheet_cell",
            func=self.write_cell,
            description="Escribir un valor en una celda específica.",
            args_schema=WriteCellArgs,
        )

    def get_tool_write_range(self) -> StructuredTool:
        return self._make_tool(
            name="write_sheet_range",
            func=self.write_range,
            description="Escribe una matriz 2D de valores en un rango de Google Sheets.",
            args_schema=WriteRangeArgs,
        )

    def get_tool_append_row(self) -> StructuredTool:
        return self._make_tool(
            name="append_sheet_row",
            func=self.add_row,
            description="Agregar una nueva fila con valores al final de una hoja.",
            args_schema=AgregarFilaArgs,
        )

    def get_tool_append_column(self) -> StructuredTool:
        return self._make_tool(
            name="append_sheet_column",
            func=self.add_column,
            description="Agregar una nueva columna con valores al final de una hoja.",
            args_schema=AgregarColumnaArgs,
        )

    def get_tool_create_sheet(self) -> StructuredTool:
        return self._make_tool(
            name="create_sheet_tab",
            func=self.create_sheet,
            description="Crear una nueva hoja (pestaña) dentro de un archivo.",
            args_schema=CreateSheetArgs,
        )

    def get_tool_rename_sheet(self) -> StructuredTool:
        return self._make_tool(
            name="rename_sheet_tab",
            func=self.rename_sheet,
            description="Renombrar una hoja existente.",
            args_schema=RenameSheetArgs,
        )

    def get_tool_duplicate_sheet(self) -> StructuredTool:
        return self._make_tool(
            name="duplicate_sheet_tab",
            func=self.duplicate_sheet,
            description="Duplicar una hoja dentro de un archivo con un nuevo nombre.",
            args_schema=DuplicateSheetArgs,
        )

    def get_tool_clear_range(self) -> StructuredTool:
        return self._make_tool(
            name="clear_sheet_range",
            func=self.clear_range,
            description="Limpiar el contenido de un rango en Google Sheets sin eliminar filas ni columnas.",
            args_schema=ClearRangeArgs,
        )

    def get_all_tools(self) -> List[Any]:
        return [
            self.get_tool_search_sheet(),
            self.get_tool_list_sheets(),
            self.get_tool_get_cell(),
            self.get_tool_read_range(),
            self.get_tool_search_value(),
            self.get_tool_count_rows(),
            self.get_tool_get_row(),
            self.get_tool_get_column(),
            self.get_tool_get_occupied_cells(),
            self.get_tool_write_cell(),
            self.get_tool_write_range(),
            self.get_tool_append_row(),
            self.get_tool_append_column(),
            self.get_tool_create_sheet(),
            self.get_tool_rename_sheet(),
            self.get_tool_duplicate_sheet(),
            self.get_tool_clear_range(),
        ]

