"""
Google Slides Tool para LangGraph / LangChain
Migración a Bóveda Segura y Resiliencia V2.
- Implementación de timeout global por socket para prevenir bloqueos.
- Sanitización anti-inyección para Google Drive API.
- Uso estricto de ToolException y handle_tool_error=True.
- Reparado el ValueError: mutually exclusive arguments en build().
- Todas las salidas estandarizadas a JSON Strings.
- Refactorización de Pydantic Schemas para mitigación severa de alucinaciones del LLM.
"""

import json
import logging
import socket
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple, Any, Callable
import dateutil.relativedelta as rd
from pydantic import BaseModel, Field, field_validator, ConfigDict
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from langchain_core.tools import StructuredTool, ToolException
from app.integrations.providers.google.slides import get_slides_creds_for_langchain
from app.integrations.providers.google.drive import get_drive_creds_for_langchain
from app.core.db_utils import canonicalize_email

logger = logging.getLogger("tools.google_slides")
_REQUEST_TIMEOUT = 15
socket.setdefaulttimeout(_REQUEST_TIMEOUT)


class PresentationIdInput(BaseModel):
    presentation_id: str = Field(
        ...,
        alias="id_presentacion",
        description="CRÍTICO: SOLO el ID alfanumérico de la presentación de Google Slides. Prohibido incluir URLs, frases o descripciones aquí.",
    )

    @field_validator("presentation_id", mode="before")
    @classmethod
    def extract_id(cls, v):
        """Previene que el LLM pase URLs completas por error."""
        if isinstance(v, str) and "docs.google.com/presentation" in v:
            parts = v.split("/d/")
            if len(parts) > 1:
                return parts[1].split("/")[0]
            return v.strip()
        return v.strip() if isinstance(v, str) else v


class InsertSlideTextInput(BaseModel):
    presentation_id: str = Field(
        ...,
        alias="id_presentacion",
        description="CRÍTICO: OBLIGATORIO. SOLO el ID alfanumérico de la presentación. ESTÁ ESTRICTAMENTE PROHIBIDO poner el texto a escribir en este campo.",
    )
    slide_id: Optional[str] = Field(
        None,
        alias="id_diapositiva",
        description="ID interno de la diapositiva. Si se omite, usa la primera página por defecto.",
    )
    text: str = Field(
        ...,
        alias="text",
        min_length=1,
        description="OBLIGATORIO. El contenido, párrafo o texto exacto que deseas insertar o escribir. NO puede estar vacío.",
    )
    x: int = Field(
        default=50, description="Posición horizontal X en la diapositiva (puntos)."
    )
    y: int = Field(
        default=50, description="Posición vertical Y en la diapositiva (puntos)."
    )
    width: int = Field(default=300, description="Ancho del cuadro de texto en puntos.")
    height: int = Field(default=100, description="Alto del cuadro de texto en puntos.")

    @field_validator("presentation_id", mode="before")
    @classmethod
    def extract_id(cls, v):
        if isinstance(v, str) and "docs.google.com/presentation" in v:
            parts = v.split("/d/")
            if len(parts) > 1:
                return parts[1].split("/")[0]
            return v.strip()
        return v.strip() if isinstance(v, str) else v


class SearchSlideByNameInput(BaseModel):
    name: str = Field(
        ...,
        alias="name",
        min_length=1,
        description="Nombre exacto o palabra clave de la presentación a buscar en Google Drive.",
    )
    exact: bool = Field(
        default=False,
        description="Si True, requiere coincidencia exacta. Si False, coincidencia parcial.",
    )


class GetSlideListInput(BaseModel):
    names: Optional[str] = Field(
        default=None,
        alias="names",
        description="Nombres de archivos separados por comas. Opcional.",
    )
    owner: Optional[str] = Field(
        default=None,
        alias="owner",
        description="Correo electrónico del propietario a filtrar. Opcional.",
    )
    date: Optional[str] = Field(
        default=None,
        alias="date",
        description="Filtro de fecha (ej. 'hoy', 'ayer', 'este mes'). Opcional.",
    )
    exact: bool = Field(
        default=False, description="Booleano para búsqueda exacta de nombres."
    )


class ReplaceSlideTextInput(BaseModel):
    presentation_id: str = Field(
        ..., alias="id_presentacion", description="ID alfanumérico de la presentación."
    )
    slide_id: Optional[str] = Field(
        None,
        alias="id_diapositiva",
        description="ID de la diapositiva específica. Si se omite, buscará en toda la presentación.",
    )
    search: str = Field(
        ...,
        alias="search",
        min_length=1,
        description="El texto exacto que quieres buscar dentro de la presentación.",
    )
    replace: str = Field(
        ...,
        alias="replace",
        description="El nuevo texto por el cual lo vas a sustituir. Vacío ('') para borrar.",
    )
    occurrence: int = Field(
        default=0,
        alias="ocurrencia",
        description="0 reemplaza todas las coincidencias. 1 reemplaza solo la primera.",
    )
    match_case: bool = Field(
        default=True,
        description="Si True, diferencia entre mayúsculas y minúsculas en la búsqueda.",
    )


class ChangeSlideTitleInput(BaseModel):
    presentation_id: str = Field(
        ..., alias="id_presentacion", description="ID alfanumérico de la presentación."
    )
    new_title: str = Field(
        ...,
        alias="new_title",
        min_length=1,
        description="El nuevo título o nombre que tendrá el archivo de la presentación.",
    )


class CreateSlideInput(BaseModel):
    title: str = Field(
        ...,
        alias="title",
        min_length=1,
        description="OBLIGATORIO. El nombre o título exacto que tendrá la nueva presentación vacía de Google Slides al crearse.",
    )
    parent_id: Optional[str] = Field(
        default=None,
        alias="carpeta_id",
        description="ID alfanumérico de la carpeta destino de Drive (opcional).",
    )


class AddSlideInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    presentation_id: str = Field(
        ..., alias="id_presentacion", description="ID alfanumérico de la presentación."
    )
    position: Optional[int] = Field(
        default=None,
        description="Índice de posición. Si se omite, se insertará al final de la presentación.",
    )
    layout: str = Field(
        default="BLANK", description="Diseño base (ej. 'BLANK', 'TITLE_AND_BODY')."
    )


class DuplicateSlideInput(BaseModel):
    presentation_id: str = Field(
        ..., alias="id_presentacion", description="ID alfanumérico de la presentación."
    )
    slide_id: str = Field(
        ...,
        alias="id_diapositiva",
        description="ID de la diapositiva específica que se quiere clonar.",
    )
    position: Optional[int] = Field(
        default=None,
        description="Índice donde se colocará la copia. Si se omite, va inmediatamente después.",
    )


class CreateShapeInput(BaseModel):
    presentation_id: str = Field(
        ..., alias="id_presentacion", description="ID alfanumérico de la presentación."
    )
    slide_id: str = Field(
        ..., alias="id_diapositiva", description="ID interno de la diapositiva."
    )
    shape_type: str = Field(
        ...,
        alias="shape_type",
        description="Tipo de figura geométrica (ej. RECTANGLE, ELLIPSE, TRIANGLE).",
    )
    x: int = Field(default=50, description="Posición X.")
    y: int = Field(default=50, description="Posición Y.")
    width: int = Field(default=200, description="Ancho.")
    height: int = Field(default=100, description="Alto.")
    text: Optional[str] = Field(
        default=None, alias="text", description="Texto interno de la figura."
    )


class CreateTableInput(BaseModel):
    presentation_id: str = Field(
        ..., alias="id_presentacion", description="ID alfanumérico de la presentación."
    )
    slide_id: str = Field(
        ..., alias="id_diapositiva", description="ID interno de la diapositiva destino."
    )
    rows: int = Field(
        ..., alias="rows", ge=1, description="Cantidad de filas de la tabla."
    )
    columns: int = Field(
        ..., alias="columns", ge=1, description="Cantidad de columnas de la tabla."
    )
    x: int = Field(default=50, description="Posición X.")
    y: int = Field(default=50, description="Posición Y.")
    width: int = Field(default=400, description="Ancho total.")
    height: int = Field(default=300, description="Alto total.")
    data: Optional[list[list[str]]] = Field(
        default=None,
        alias="data",
        description="Matriz de datos (lista de listas de strings).",
    )

    @field_validator("data", mode="before")
    @classmethod
    def coerce_data_to_str(cls, v: Any) -> Any:
        """Previene errores de validación convirtiendo ints/floats del LLM a str."""
        if v is None:
            return v
        return [[str(cell) for cell in row] for row in v]


class ShareSlideInput(BaseModel):
    presentation_id: str = Field(
        ..., alias="id_presentacion", description="ID de la presentación."
    )
    email: Optional[str] = Field(
        None,
        alias="email",
        description="Correo electrónico del usuario o grupo a invitar.",
    )
    role: str = Field(
        ...,
        alias="role",
        description="Rol otorgado (reader, commenter, writer, owner).",
    )
    scope: str = Field(
        default="user",
        alias="scope",
        description="Alcance del permiso (user, group, domain, anyone).",
    )


class GetSlideIdsInput(BaseModel):
    presentation_id: str = Field(
        ...,
        alias="id_presentacion",
        description="ID alfanumérico de la presentación para recuperar los IDs de sus páginas.",
    )


class GoogleSlidesToolProvider:

    def __init__(self, user_email: str | None = None, user_id: str | None = None, account_id: str | None = None):
        email_source = user_email
        canonical = canonicalize_email(email_source) or (email_source or "")
        self.user_email = canonical
        self.user_id = user_id
        self.account_id = account_id or None
        self._slides_service_cache = None
        self._drive_service_cache = None

    def _get_slides_service(self):
        if self._slides_service_cache:
            return self._slides_service_cache
        creds_dict = get_slides_creds_for_langchain(self.user_id, account_id=self.account_id)
        if not creds_dict or "error" in creds_dict:
            raise ToolException(
                f"Credenciales Slides inválidas: {creds_dict.get('error', 'Desconocidas')}"
            )
        self._slides_service_cache = build(
            "slides",
            "v1",
            credentials=Credentials.from_authorized_user_info(creds_dict),
            cache_discovery=False,
        )
        return self._slides_service_cache

    def _get_drive_service(self):
        if self._drive_service_cache:
            return self._drive_service_cache
        creds_dict = get_drive_creds_for_langchain(self.user_id, account_id=self.account_id)
        if not creds_dict or "error" in creds_dict:
            raise ToolException(
                f"Credenciales Drive inválidas: {creds_dict.get('error', 'Desconocidas')}"
            )
        self._drive_service_cache = build(
            "drive",
            "v3",
            credentials=Credentials.from_authorized_user_info(creds_dict),
            cache_discovery=False,
        )
        return self._drive_service_cache

    def _sanitize_query(self, query: str) -> str:
        """Escapa caracteres para evitar inyección en Drive API."""
        return query.replace("\\", "\\\\").replace("'", "\\'")

    def _handle_error(self, operation: str, e: Exception) -> None:
        """Propaga errores estandarizados hacia LangGraph mediante ToolException."""
        logger.error(f"[Google Slides Tool] Fallo en {operation}: {str(e)}")
        if isinstance(e, HttpError):
            if e.resp.status in [401, 403]:
                raise ToolException(
                    "Error 403/401: Permisos insuficientes o scope incorrecto."
                )
            if e.resp.status == 404:
                raise ToolException(
                    "Error 404: Presentación no encontrada o sin acceso. Verifica el ID."
                )
            if e.resp.status == 400:
                raise ToolException(
                    f"Error 400: Parámetros inválidos enviados a Google ({e._get_reason()})."
                )
        raise ToolException(f"Fallo en la operación '{operation}': {str(e)}")

    def _parse_fecha(self, rango: str) -> Tuple[Optional[str], Optional[str]]:
        hoy = datetime.now(timezone.utc).date()
        rango = rango.lower().strip()
        if rango == "hoy":
            return (hoy.isoformat(), hoy.isoformat())
        if rango == "ayer":
            ayer = hoy - timedelta(days=1)
            return (ayer.isoformat(), ayer.isoformat())
        if rango in ["esta semana", "semana actual"]:
            return ((hoy - timedelta(days=hoy.weekday())).isoformat(), hoy.isoformat())
        if rango in ["la semana pasada"]:
            end = hoy - timedelta(days=hoy.weekday() + 1)
            return ((end - timedelta(days=6)).isoformat(), end.isoformat())
        if rango in ["este mes"]:
            return (hoy.replace(day=1).isoformat(), hoy.isoformat())
        if rango in ["el mes pasado"]:
            start = hoy.replace(day=1) - rd.relativedelta.relativedelta(months=1)
            end = start.replace(day=1) + rd.relativedelta.relativedelta(
                months=1, days=-1
            )
            return (start.isoformat(), end.isoformat())
        if "," in rango:
            fechas = [f.strip() for f in rango.split(",")]
            if len(fechas) == 2:
                return (fechas[0], fechas[1])
        return (rango, None)

    def get_presentation_content(self, presentation_id: str) -> str:
        try:
            service = self._get_slides_service()
            presentation = (
                service.presentations().get(presentationId=presentation_id).execute()
            )
            text_content = []
            for slide in presentation.get("slides", []):
                for element in slide.get("pageElements", []):
                    shape = element.get("shape")
                    if shape and "text" in shape and ("textElements" in shape["text"]):
                        for te in shape["text"]["textElements"]:
                            if "textRun" in te:
                                text_content.append(te["textRun"].get("content", ""))
            final_content = "".join(text_content).strip()
            return json.dumps(
                {"status": "success", "content": final_content}, ensure_ascii=False
            )
        except Exception as e:
            self._handle_error("get_presentation_content", e)

    def find_presentation_by_name(self, nombre: str, exacto: bool = False) -> str:
        try:
            drive_service = self._get_drive_service()
            nombre_seguro = self._sanitize_query(nombre)
            query = f"mimeType='application/vnd.google-apps.presentation' and name"
            query += f"='{nombre_seguro}'" if exacto else f" contains '{nombre_seguro}'"
            results = (
                drive_service.files()
                .list(
                    q=query,
                    fields="files(id, name, webViewLink, createdTime, owners(displayName,emailAddress))",
                    pageSize=5,
                )
                .execute()
            )
            archivos = results.get("files", [])
            if not archivos:
                raise ToolException(
                    f"No se encontró presentación con nombre '{nombre}'"
                )
            slide_file = archivos[0]
            contenido_json = json.loads(self.get_presentation_content(slide_file["id"]))
            return json.dumps(
                {
                    "status": "success",
                    "id": slide_file["id"],
                    "nombre": slide_file["name"],
                    "link": slide_file["webViewLink"],
                    "fecha_creacion": slide_file.get("createdTime"),
                    "propietario": slide_file.get("owners", [{}])[0].get(
                        "displayName", "Desconocido"
                    ),
                    "contenido": contenido_json.get("content", ""),
                },
                ensure_ascii=False,
            )
        except ToolException:
            raise
        except Exception as e:
            self._handle_error("find_presentation_by_name", e)

    def list_presentations(
        self,
        nombres: Optional[str] = None,
        propietario: Optional[str] = None,
        fecha: Optional[str] = None,
        exacto: bool = False,
    ) -> str:
        try:
            drive_service = self._get_drive_service()
            query = "mimeType='application/vnd.google-apps.presentation'"
            if nombres:
                nombres_lista = [
                    self._sanitize_query(n.strip())
                    for n in nombres.split(",")
                    if n.strip()
                ]
                if nombres_lista:
                    op = "=" if exacto else " contains "
                    query += (
                        " and ("
                        + " or ".join([f"name{op}'{n}'" for n in nombres_lista])
                        + ")"
                    )
            if propietario:
                query += f" and '{self._sanitize_query(propietario)}' in owners"
            if fecha:
                start_date, end_date = self._parse_fecha(fecha)
                if start_date:
                    query += f" and modifiedTime >= '{start_date}T00:00:00Z'"
                if end_date:
                    query += f" and modifiedTime <= '{end_date}T23:59:59Z'"
            results = (
                drive_service.files()
                .list(
                    q=query,
                    fields="files(id, name, createdTime, modifiedTime, owners, webViewLink)",
                    orderBy="modifiedTime desc",
                )
                .execute()
            )
            files = results.get("files", [])
            if not files:
                return json.dumps(
                    {
                        "status": "error",
                        "mensaje": "No se encontraron presentaciones con los filtros dados",
                    },
                    ensure_ascii=False,
                )
            detalle = [
                {
                    "id": f.get("id"),
                    "nombre": f.get("name"),
                    "creado": f.get("createdTime"),
                    "modificado": f.get("modifiedTime"),
                    "propietarios": [
                        o.get("emailAddress") for o in f.get("owners", [])
                    ],
                    "link": f.get("webViewLink"),
                }
                for f in files
            ]
            return json.dumps(
                {"status": "success", "resultados": detalle}, ensure_ascii=False
            )
        except Exception as e:
            self._handle_error("list_presentations", e)

    def get_presentation_info(self, nombre: str, exacto: bool = False) -> str:
        try:
            drive_service = self._get_drive_service()
            nombre_seguro = self._sanitize_query(nombre)
            query = f"mimeType='application/vnd.google-apps.presentation' and name"
            query += f"='{nombre_seguro}'" if exacto else f" contains '{nombre_seguro}'"
            results = (
                drive_service.files()
                .list(
                    q=query,
                    fields="files(id, name, createdTime, modifiedTime, owners, lastModifyingUser, webViewLink)",
                    pageSize=1,
                )
                .execute()
            )
            files = results.get("files", [])
            if not files:
                raise ToolException(f"No se encontró presentación '{nombre}'")
            file_info = files[0]
            presentation_id = file_info["id"]
            service = self._get_slides_service()
            presentation = (
                service.presentations().get(presentationId=presentation_id).execute()
            )
            return json.dumps(
                {
                    "status": "success",
                    "id": file_info.get("id"),
                    "nombre": file_info.get("name"),
                    "enlace": file_info.get("webViewLink"),
                    "fecha_creacion": file_info.get("createdTime"),
                    "ultima_modificacion": file_info.get("modifiedTime"),
                    "propietarios": [
                        o.get("emailAddress") for o in file_info.get("owners", [])
                    ],
                    "ultimo_editor": file_info.get("lastModifyingUser", {}).get(
                        "emailAddress"
                    ),
                    "total_diapos": len(presentation.get("slides", [])),
                },
                ensure_ascii=False,
            )
        except ToolException:
            raise
        except Exception as e:
            self._handle_error("get_presentation_info", e)

    def get_presentation_comments(self, nombre: str, exacto: bool = False) -> str:
        try:
            drive_service = self._get_drive_service()
            nombre_seguro = self._sanitize_query(nombre)
            query = f"mimeType='application/vnd.google-apps.presentation' and name"
            query += f"='{nombre_seguro}'" if exacto else f" contains '{nombre_seguro}'"
            results = (
                drive_service.files()
                .list(q=query, fields="files(id, name, webViewLink)", pageSize=1)
                .execute()
            )
            archivos = results.get("files", [])
            if not archivos:
                raise ToolException(f"No se encontró presentación '{nombre}'")
            slide_file = archivos[0]
            comments_result = (
                drive_service.comments()
                .list(
                    fileId=slide_file["id"],
                    fields="comments(author,content,createdTime,resolved,quotedFileContent)",
                )
                .execute()
            )
            comentarios_extraidos = [
                {
                    "autor": c.get("author", {}).get("displayName", "Desconocido"),
                    "contenido": c.get("content", ""),
                    "fecha": c.get("createdTime"),
                    "resuelto": c.get("resolved", False),
                    "texto_comentado": c.get("quotedFileContent", {}).get(
                        "value", "No especificado"
                    ),
                }
                for c in comments_result.get("comments", [])
            ]
            return json.dumps(
                {
                    "status": "success",
                    "id": slide_file["id"],
                    "nombre": slide_file.get("name"),
                    "enlace": slide_file.get("webViewLink"),
                    "comentarios": comentarios_extraidos,
                },
                ensure_ascii=False,
            )
        except ToolException:
            raise
        except Exception as e:
            self._handle_error("get_presentation_comments", e)

    def get_presentation_slide_ids(self, presentation_id: str) -> str:
        try:
            service = self._get_slides_service()
            presentation = (
                service.presentations().get(presentationId=presentation_id).execute()
            )
            slides_info = [
                {"index": idx, "slide_id": slide.get("objectId")}
                for idx, slide in enumerate(presentation.get("slides", []), start=1)
            ]
            return json.dumps(
                {"status": "success", "slides": slides_info}, ensure_ascii=False
            )
        except Exception as e:
            self._handle_error("get_presentation_slide_ids", e)

    def insert_text_in_presentation(
        self,
        presentation_id: str,
        slide_id: Optional[str] = None,
        text: str = "",
        x: int = 50,
        y: int = 50,
        width: int = 300,
        height: int = 100,
    ) -> str:
        if not text.strip():
            raise ToolException(
                "El texto provisto está vacío. Genera contenido primero."
            )
        try:
            service = self._get_slides_service()
            if not slide_id:
                presentation = (
                    service.presentations()
                    .get(presentationId=presentation_id)
                    .execute()
                )
                slides = presentation.get("slides", [])
                if not slides:
                    raise ToolException("La presentación no tiene diapositivas")
                slide_id = slides[0].get("objectId")
            object_id = f"TextBox_{slide_id}_{x}_{y}"
            requests = [
                {
                    "createShape": {
                        "objectId": object_id,
                        "shapeType": "TEXT_BOX",
                        "elementProperties": {
                            "pageObjectId": slide_id,
                            "size": {
                                "height": {"magnitude": height, "unit": "PT"},
                                "width": {"magnitude": width, "unit": "PT"},
                            },
                            "transform": {
                                "scaleX": 1,
                                "scaleY": 1,
                                "translateX": x,
                                "translateY": y,
                                "unit": "PT",
                            },
                        },
                    }
                },
                {
                    "insertText": {
                        "objectId": object_id,
                        "insertionIndex": 0,
                        "text": text,
                    }
                },
            ]
            service.presentations().batchUpdate(
                presentationId=presentation_id, body={"requests": requests}
            ).execute()
            return json.dumps(
                {
                    "status": "success",
                    "mensaje": "Texto insertado correctamente",
                    "slide_id_usado": slide_id,
                },
                ensure_ascii=False,
            )
        except ToolException:
            raise
        except Exception as e:
            self._handle_error("insert_text_in_presentation", e)

    def replace_text_in_presentation(
        self,
        presentation_id: str,
        slide_id: Optional[str] = None,
        search: str = "",
        replace: str = "",
        occurrence: int = 0,
        match_case: bool = True,
    ) -> str:
        if not search:
            raise ToolException("El parámetro 'search' está vacío.")
        try:
            service = self._get_slides_service()
            presentation = (
                service.presentations().get(presentationId=presentation_id).execute()
            )
            slides = presentation.get("slides", [])
            index_map = []
            for s in slides:
                if slide_id and s.get("objectId") != slide_id:
                    continue
                for element in s.get("pageElements", []):
                    shape = element.get("shape")
                    if shape and "text" in shape:
                        for te in shape["text"].get("textElements", []):
                            if "textRun" in te:
                                text = te["textRun"].get("content", "")
                                search_text = text if match_case else text.lower()
                                target = search if match_case else search.lower()
                                pos = search_text.find(target)
                                while pos != -1:
                                    index_map.append(
                                        {
                                            "objectId": element["objectId"],
                                            "start": pos,
                                            "end": pos + len(search),
                                        }
                                    )
                                    pos = search_text.find(target, pos + 1)
            if not index_map:
                raise ToolException(
                    f"No se encontró '{search}' en la diapositiva/presentación"
                )
            requests = []
            target_matches = (
                index_map
                if occurrence == 0
                else [index_map[occurrence - 1]] if occurrence <= len(index_map) else []
            )
            if not target_matches:
                raise ToolException(
                    f"No existe la ocurrencia {occurrence} de '{search}'"
                )
            for match in target_matches:
                requests.append(
                    {
                        "deleteText": {
                            "objectId": match["objectId"],
                            "textRange": {
                                "type": "FIXED_RANGE",
                                "startIndex": match["start"],
                                "endIndex": match["end"],
                            },
                        }
                    }
                )
                requests.append(
                    {
                        "insertText": {
                            "objectId": match["objectId"],
                            "insertionIndex": match["start"],
                            "text": replace,
                        }
                    }
                )
            service.presentations().batchUpdate(
                presentationId=presentation_id, body={"requests": requests}
            ).execute()
            return json.dumps(
                {"status": "success", "mensaje": "Reemplazo completado"},
                ensure_ascii=False,
            )
        except ToolException:
            raise
        except Exception as e:
            self._handle_error("replace_text_in_presentation", e)

    def change_presentation_title(self, presentation_id: str, new_title: str) -> str:
        try:
            drive_service = self._get_drive_service()
            updated_file = (
                drive_service.files()
                .update(
                    fileId=presentation_id,
                    body={"name": new_title.strip()},
                    fields="id, name, webViewLink",
                )
                .execute()
            )
            return json.dumps(
                {
                    "status": "success",
                    "mensaje": "Título cambiado",
                    "nuevo_titulo": updated_file.get("name"),
                },
                ensure_ascii=False,
            )
        except Exception as e:
            self._handle_error("change_presentation_title", e)

    def create_presentation(self, title: str, parent_id: Optional[str] = None) -> str:
        try:
            drive_service = self._get_drive_service()
            file_metadata = {
                "name": title.strip(),
                "mimeType": "application/vnd.google-apps.presentation",
            }
            if parent_id:
                file_metadata["parents"] = [parent_id]
            presentation = (
                drive_service.files()
                .create(body=file_metadata, fields="id, name, webViewLink")
                .execute()
            )
            return json.dumps(
                {
                    "status": "success",
                    "mensaje": "Presentación creada",
                    "id": presentation.get("id"),
                    "link": presentation.get("webViewLink"),
                },
                ensure_ascii=False,
            )
        except Exception as e:
            self._handle_error("create_presentation", e)

    def add_slide(
        self,
        presentation_id: str,
        position: Optional[int] = None,
        layout: str = "BLANK",
    ) -> str:
        try:
            service = self._get_slides_service()
            request = {
                "createSlide": {"slideLayoutReference": {"predefinedLayout": layout}}
            }
            if position is not None:
                request["createSlide"]["insertionIndex"] = position
            service.presentations().batchUpdate(
                presentationId=presentation_id, body={"requests": [request]}
            ).execute()
            return json.dumps(
                {"status": "success", "mensaje": "Diapositiva agregada"},
                ensure_ascii=False,
            )
        except Exception as e:
            self._handle_error("add_slide", e)

    def duplicate_slide(
        self, presentation_id: str, slide_id: str, position: Optional[int] = None
    ) -> str:
        try:
            service = self._get_slides_service()
            request = {"duplicateObject": {"objectId": slide_id}}
            if position is not None:
                request["duplicateObject"]["insertionIndex"] = position
            service.presentations().batchUpdate(
                presentationId=presentation_id, body={"requests": [request]}
            ).execute()
            return json.dumps(
                {
                    "status": "success",
                    "mensaje": "Diapositiva duplicada",
                    "original_slide": slide_id,
                },
                ensure_ascii=False,
            )
        except Exception as e:
            self._handle_error("duplicate_slide", e)

    def create_shape(
        self,
        presentation_id: str,
        slide_id: str,
        shape_type: str,
        x: int = 50,
        y: int = 50,
        width: int = 200,
        height: int = 100,
        text: Optional[str] = None,
    ) -> str:
        try:
            service = self._get_slides_service()
            object_id = f"Shape_{slide_id}_{x}_{y}"
            requests = [
                {
                    "createShape": {
                        "objectId": object_id,
                        "shapeType": shape_type,
                        "elementProperties": {
                            "pageObjectId": slide_id,
                            "size": {
                                "width": {"magnitude": width, "unit": "PT"},
                                "height": {"magnitude": height, "unit": "PT"},
                            },
                            "transform": {
                                "scaleX": 1,
                                "scaleY": 1,
                                "translateX": x,
                                "translateY": y,
                                "unit": "PT",
                            },
                        },
                    }
                }
            ]
            if text:
                requests.append(
                    {
                        "insertText": {
                            "objectId": object_id,
                            "insertionIndex": 0,
                            "text": text,
                        }
                    }
                )
            service.presentations().batchUpdate(
                presentationId=presentation_id, body={"requests": requests}
            ).execute()
            return json.dumps(
                {
                    "status": "success",
                    "mensaje": "Figura creada",
                    "tipo": shape_type,
                    "texto_insertado": text,
                },
                ensure_ascii=False,
            )
        except Exception as e:
            self._handle_error("create_shape", e)

    def create_table(
        self,
        presentation_id: str,
        slide_id: str,
        rows: int,
        columns: int,
        x: int = 50,
        y: int = 50,
        width: int = 400,
        height: int = 300,
        data: Optional[list[list[str]]] = None,
    ) -> str:
        try:
            service = self._get_slides_service()
            object_id = f"Table_{slide_id}_{x}_{y}"
            requests = [
                {
                    "createTable": {
                        "objectId": object_id,
                        "rows": rows,
                        "columns": columns,
                        "elementProperties": {
                            "pageObjectId": slide_id,
                            "size": {
                                "width": {"magnitude": width, "unit": "PT"},
                                "height": {"magnitude": height, "unit": "PT"},
                            },
                            "transform": {
                                "scaleX": 1,
                                "scaleY": 1,
                                "translateX": x,
                                "translateY": y,
                                "unit": "PT",
                            },
                        },
                    }
                }
            ]
            if data:
                for i, row in enumerate(data):
                    for j, cell_text in enumerate(row):
                        if cell_text:
                            requests.append(
                                {
                                    "insertText": {
                                        "objectId": object_id,
                                        "cellLocation": {
                                            "rowIndex": i,
                                            "columnIndex": j,
                                        },
                                        "insertionIndex": 0,
                                        "text": str(cell_text),
                                    }
                                }
                            )
            service.presentations().batchUpdate(
                presentationId=presentation_id, body={"requests": requests}
            ).execute()
            return json.dumps(
                {
                    "status": "success",
                    "mensaje": f"Tabla {rows}x{columns} creada y poblada",
                },
                ensure_ascii=False,
            )
        except Exception as e:
            self._handle_error("create_table", e)

    def share_presentation(
        self,
        presentation_id: str,
        role: str,
        scope: str = "user",
        email: Optional[str] = None,
    ) -> str:
        try:
            drive_service = self._get_drive_service()
            permiso = {"role": role, "type": scope}
            if scope in ["user", "group"] and email:
                permiso["emailAddress"] = email
            elif scope == "domain" and email:
                permiso["domain"] = email
            drive_service.permissions().create(
                fileId=presentation_id, body=permiso, fields="id"
            ).execute()
            return json.dumps(
                {
                    "status": "success",
                    "mensaje": "Permisos actualizados",
                    "rol": role,
                    "compartido_con": email,
                },
                ensure_ascii=False,
            )
        except Exception as e:
            self._handle_error("share_presentation", e)

    def _make_tool(
        self, name: str, func: Callable, desc: str, schema: Any = None
    ) -> StructuredTool:
        """Helper para registrar herramientas de forma estandarizada y segura para LangGraph."""
        return StructuredTool.from_function(
            name=name,
            func=func,
            description=desc,
            args_schema=schema,
            handle_tool_error=True,
        )

    def get_tool_obtener_contenido(self) -> StructuredTool:
        return self._make_tool(
            "get_presentation_content",
            self.get_presentation_content,
            "Obtiene el texto completo de una presentación. SOLO pasa el ID alfanumérico.",
            PresentationIdInput,
        )

    def get_tool_obtener_slide_por_nombre(self) -> StructuredTool:
        return self._make_tool(
            "find_presentation_by_name",
            self.find_presentation_by_name,
            "Busca una presentación en Drive por nombre y devuelve su contenido.",
            SearchSlideByNameInput,
        )

    def get_tool_obtener_lista_slides(self) -> StructuredTool:
        return self._make_tool(
            "list_presentations",
            self.list_presentations,
            "Filtra presentaciones por nombre, propietario o fecha.",
            GetSlideListInput,
        )

    def get_tool_obtener_info_slide(self) -> StructuredTool:
        return self._make_tool(
            "get_presentation_info",
            self.get_presentation_info,
            "Metadatos detallados de una presentación.",
            SearchSlideByNameInput,
        )

    def get_tool_obtener_comentarios_slide(self) -> StructuredTool:
        return self._make_tool(
            "get_presentation_comments",
            self.get_presentation_comments,
            "Recupera comentarios de la presentación.",
            SearchSlideByNameInput,
        )

    def get_tool_obtener_ids_slides(self) -> StructuredTool:
        return self._make_tool(
            "get_presentation_slide_ids",
            self.get_presentation_slide_ids,
            "Obtiene los IDs internos de las páginas/diapositivas de la presentación.",
            GetSlideIdsInput,
        )

    def get_tool_insertar_texto(self) -> StructuredTool:
        return self._make_tool(
            "insert_text_in_presentation",
            self.insert_text_in_presentation,
            "Inserta un bloque de texto en una diapositiva EXISTENTE de Google Slides.",
            InsertSlideTextInput,
        )

    def get_tool_reemplazar_texto(self) -> StructuredTool:
        return self._make_tool(
            "replace_text_in_presentation",
            self.replace_text_in_presentation,
            "Busca y reemplaza texto en la presentación.",
            ReplaceSlideTextInput,
        )

    def get_tool_cambiar_titulo(self) -> StructuredTool:
        return self._make_tool(
            "change_presentation_title",
            self.change_presentation_title,
            "Cambia el nombre del archivo de la presentación en Drive.",
            ChangeSlideTitleInput,
        )

    def get_tool_crear_slide(self) -> StructuredTool:
        return self._make_tool(
            "create_presentation",
            self.create_presentation,
            "Crea un archivo nuevo y vacío de Google Slides. Devuelve el ID generado.",
            CreateSlideInput,
        )

    def get_tool_agregar_diapositiva(self) -> StructuredTool:
        return self._make_tool(
            "add_slide",
            self.add_slide,
            "Añade una página/diapositiva nueva al archivo.",
            AddSlideInput,
        )

    def get_tool_duplicar_diapositiva(self) -> StructuredTool:
        return self._make_tool(
            "duplicate_slide",
            self.duplicate_slide,
            "Duplica una diapositiva existente.",
            DuplicateSlideInput,
        )

    def get_tool_crear_figura(self) -> StructuredTool:
        return self._make_tool(
            "create_shape",
            self.create_shape,
            "Dibuja una figura geométrica.",
            CreateShapeInput,
        )

    def get_tool_crear_tabla(self) -> StructuredTool:
        return self._make_tool(
            "create_table",
            self.create_table,
            "Inserta una tabla de datos.",
            CreateTableInput,
        )

    def get_tool_compartir_slide(self) -> StructuredTool:
        return self._make_tool(
            "share_presentation",
            self.share_presentation,
            "Modifica permisos de acceso a la presentación.",
            ShareSlideInput,
        )

    def get_all_tools(self) -> List[Any]:
        return [
            self.get_tool_obtener_contenido(),
            self.get_tool_obtener_slide_por_nombre(),
            self.get_tool_obtener_lista_slides(),
            self.get_tool_obtener_info_slide(),
            self.get_tool_obtener_comentarios_slide(),
            self.get_tool_obtener_ids_slides(),
            self.get_tool_insertar_texto(),
            self.get_tool_reemplazar_texto(),
            self.get_tool_cambiar_titulo(),
            self.get_tool_crear_slide(),
            self.get_tool_agregar_diapositiva(),
            self.get_tool_duplicar_diapositiva(),
            self.get_tool_crear_figura(),
            self.get_tool_crear_tabla(),
            self.get_tool_compartir_slide(),
        ]


