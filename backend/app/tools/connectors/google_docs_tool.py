"""
Google Docs Tool para LangGraph / LangChain
Migración a Bóveda Segura y Resiliencia V2.
Refactorizado: Reverse DOM Mutation para tablas, schemas estrictos (Anti-Hallucination),
prevención de Timeouts nativos y salidas JSON estandarizadas.
"""

import json
import logging
import socket
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Any
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from langchain_core.tools import StructuredTool, ToolException
from pydantic import BaseModel, Field, field_validator, ConfigDict
from app.integrations.providers.google.docs import get_docs_creds_for_langchain
from app.integrations.providers.google.drive import get_drive_creds_for_langchain
from app.core.db_utils import canonicalize_email

logger = logging.getLogger("tools.google_docs")
_REQUEST_TIMEOUT = 15
socket.setdefaulttimeout(_REQUEST_TIMEOUT)


class DocumentNamesInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    nombres: str = Field(
        ...,
        alias="names",
        description="Nombres de los documentos separados por comas. (Herramienta deprecada, pero schema requerido para validación).",
    )


class DocIdInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    doc_id: str = Field(
        ...,
        alias="id_documento",
        description="CRÍTICO: SOLO el ID alfanumérico del documento de Google Docs (ej. '1cXz6aHhKaFqz...'). Prohibido incluir URLs, frases o descripciones aquí.",
    )

    @field_validator("doc_id", mode="before")
    @classmethod
    def extract_id(cls, v):
        """Previene que el LLM pase URLs completas por error."""
        if isinstance(v, str) and "docs.google.com" in v:
            parts = v.split("/d/")
            if len(parts) > 1:
                return parts[1].split("/")[0]
            return v.strip()
        return v.strip() if isinstance(v, str) else v


class InsertTextInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    doc_id: str = Field(
        ...,
        alias="id_documento",
        description="CRÍTICO: OBLIGATORIO. SOLO el ID alfanumérico del documento de Google Docs. ESTÁ ESTRICTAMENTE PROHIBIDO poner el texto o contenido a escribir en este campo.",
    )
    text: str = Field(
        ...,
        alias="text",
        description="OBLIGATORIO. El contenido, párrafo o texto exacto que deseas insertar o escribir dentro del documento. NO puede estar vacío.",
    )
    index: int = Field(
        default=1,
        description="Índice de posición de inserción (1 = inicio del documento).",
    )

    @field_validator("doc_id", mode="before")
    @classmethod
    def extract_id(cls, v):
        if isinstance(v, str) and "docs.google.com" in v:
            parts = v.split("/d/")
            if len(parts) > 1:
                return parts[1].split("/")[0]
            return v.strip()
        return v.strip() if isinstance(v, str) else v


class ReplaceTextInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    doc_id: str = Field(
        ..., alias="id_documento", description="ID alfanumérico del documento."
    )
    buscar: str = Field(
        ...,
        alias="search",
        description="Texto exacto que quieres buscar dentro del documento.",
    )
    reemplazar: str = Field(
        ...,
        alias="replace",
        description="El nuevo texto por el cual lo vas a sustituir.",
    )
    occurrence: int = Field(
        default=0,
        alias="ocurrencia",
        description="0 reemplaza todas las coincidencias. 1 reemplaza solo la primera.",
    )


class InsertTableInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    doc_id: str = Field(
        ..., alias="id_documento", description="ID alfanumérico del documento."
    )
    rows: int = Field(..., ge=1, description="Número total de filas (mínimo 1).")
    columns: int = Field(..., ge=1, description="Número total de columnas (mínimo 1).")


class FillTableInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    doc_id: str = Field(
        ..., alias="id_documento", description="ID alfanumérico del documento."
    )
    data: List[List[str]] = Field(
        ...,
        alias="data",
        description="Matriz de datos a insertar en la tabla. Formato: Lista de listas de strings.",
    )


class ChangeTitleInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    doc_id: str = Field(
        ..., alias="id_documento", description="ID alfanumérico del documento."
    )
    new_title: str = Field(
        ...,
        alias="new_title",
        min_length=1,
        description="El nuevo título o nombre que tendrá el archivo del documento.",
    )


class DeleteTextByContentInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    doc_id: str = Field(
        ..., alias="id_documento", description="ID alfanumérico del documento."
    )
    content: str = Field(
        ...,
        alias="content",
        min_length=1,
        description="El texto exacto que deseas buscar y eliminar del documento.",
    )
    occurrence: int = Field(
        default=0,
        alias="ocurrencia",
        description="0 elimina todas las coincidencias. 1 elimina solo la primera.",
    )


class SearchDocumentArgs(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    name: str = Field(
        ...,
        alias="name",
        min_length=1,
        description="Nombre exacto o palabra clave del título del documento que deseas buscar en Drive.",
    )


class SearchDocumentsByAuthorArgs(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    author: str = Field(
        ...,
        alias="author",
        description="Dirección de email del propietario o colaborador del documento.",
    )


class SearchDocumentsByDateArgs(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    date_range: str = Field(
        ...,
        alias="date_range",
        description="Rango de fecha. Opciones válidas: 'hoy', 'ayer', 'esta semana', 'el mes pasado'.",
    )


class FormatTextInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    doc_id: str = Field(
        ..., alias="id_documento", description="ID alfanumérico del documento."
    )
    text_to_format: str = Field(
        ...,
        alias="texto_a_formatear",
        description="El texto exacto al que se le aplicará el formato.",
    )
    style: str = Field(
        ...,
        description="Estilo a aplicar: 'bold', 'italic', 'underline', 'heading_1', 'heading_2'.",
    )


class AddCommentInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    doc_id: str = Field(
        ..., alias="id_documento", description="ID alfanumérico del documento."
    )
    comment_text: str = Field(
        ...,
        alias="texto_comentario",
        description="El contenido del comentario a agregar.",
    )
    anchor_text: str = Field(
        ...,
        alias="texto_ancla",
        description="El texto en el documento al que se anclará el comentario.",
    )


class CreateDocumentArgs(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    title: str = Field(
        ...,
        alias="title",
        min_length=1,
        description="OBLIGATORIO. El nombre o título exacto que tendrá el nuevo documento de Google Docs al ser creado.",
    )


class GoogleDocsToolProvider:

    def __init__(self, user_email: str | None = None, user_id: str | None = None, account_id: str | None = None):
        email_source = user_email
        canonical = canonicalize_email(email_source) or (email_source or "")
        self.user_email = canonical
        self.user_id = user_id
        self.account_id = account_id or None
        self._docs_service_cache = None
        self._drive_service_cache = None

    def _get_docs_service(self):
        if self._docs_service_cache:
            return self._docs_service_cache
        creds = get_docs_creds_for_langchain(self.user_id, account_id=self.account_id)
        if not creds or "error" in creds:
            raise ToolException(
                f"Credenciales Docs inválidas: {creds.get('error', 'Desconocidas')}"
            )
        self._docs_service_cache = build(
            "docs",
            "v1",
            credentials=Credentials.from_authorized_user_info(creds),
            cache_discovery=False,
        )
        return self._docs_service_cache

    def _get_drive_service(self):
        if self._drive_service_cache:
            return self._drive_service_cache
        creds = get_drive_creds_for_langchain(self.user_id, account_id=self.account_id)
        if not creds or "error" in creds:
            raise ToolException(
                f"Credenciales Drive inválidas: {creds.get('error', 'Desconocidas')}"
            )
        self._drive_service_cache = build(
            "drive",
            "v3",
            credentials=Credentials.from_authorized_user_info(creds),
            cache_discovery=False,
        )
        return self._drive_service_cache

    def _sanitize_query(self, query: str) -> str:
        return query.replace("\\", "\\\\").replace("'", "\\'")

    def _handle_error(self, operation: str, e: Exception) -> None:
        logger.error(f"[Google Docs Tool] Fallo en {operation}: {str(e)}")
        if isinstance(e, HttpError):
            if e.resp.status in [401, 403]:
                raise ToolException(
                    "Error 403/401: Permisos insuficientes o scope incorrecto para Google Docs API."
                )
            if e.resp.status == 404:
                raise ToolException(
                    "Error 404: Documento no encontrado o no tienes acceso. Verifica el ID."
                )
            if e.resp.status == 400:
                raise ToolException(
                    f"Error 400: Parámetros inválidos enviados a Google ({e._get_reason()})."
                )
        raise ToolException(f"Fallo en la operación '{operation}': {str(e)}")

    def get_full_content(self, doc_id: str) -> str:
        try:
            docs_service = self._get_docs_service()
            drive_service = self._get_drive_service()
            doc = docs_service.documents().get(documentId=doc_id).execute()
            meta = (
                drive_service.files()
                .get(fileId=doc_id, fields="name, webViewLink, owners")
                .execute()
            )
            content = []
            for elem in doc.get("body", {}).get("content", []):
                if "paragraph" in elem:
                    for el in elem["paragraph"].get("elements", []):
                        if "textRun" in el:
                            content.append(el["textRun"].get("content", ""))
            return json.dumps(
                {
                    "nombre": meta.get("name"),
                    "propietario": meta.get("owners", [{}])[0].get("emailAddress"),
                    "link": meta.get("webViewLink"),
                    "contenido": "".join(content).strip(),
                },
                ensure_ascii=False,
            )
        except Exception as e:
            self._handle_error("obtener_contenido_completo", e)

    def search_document_by_name(self, name: str) -> str:
        try:
            drive_service = self._get_drive_service()
            safe_name = self._sanitize_query(name)
            results = (
                drive_service.files()
                .list(
                    q=f"name contains '{safe_name}' and mimeType='application/vnd.google-apps.document' and trashed=false",
                    fields="files(id)",
                    pageSize=1,
                )
                .execute()
            )
            files = results.get("files", [])
            if not files:
                raise ToolException(f"No se encontró documento con el nombre: {name}")
            return self.get_full_content(files[0]["id"])
        except Exception as e:
            self._handle_error("buscar_documento_por_nombre", e)

    def get_document_info(self, doc_id: str) -> str:
        try:
            drive_service = self._get_drive_service()
            meta = (
                drive_service.files()
                .get(
                    fileId=doc_id,
                    fields="name, owners, createdTime, modifiedTime, webViewLink",
                )
                .execute()
            )
            return json.dumps(
                {
                    "nombre": meta.get("name"),
                    "propietarios": [
                        o.get("emailAddress") for o in meta.get("owners", [])
                    ],
                    "creado": meta.get("createdTime"),
                    "modificado": meta.get("modifiedTime"),
                    "link": meta.get("webViewLink"),
                },
                ensure_ascii=False,
            )
        except Exception as e:
            self._handle_error("obtener_info_documento", e)

    def search_documents_by_author(self, author: str) -> str:
        try:
            drive_service = self._get_drive_service()
            safe_author = self._sanitize_query(author)
            results = (
                drive_service.files()
                .list(
                    q=f"'{safe_author}' in owners and mimeType='application/vnd.google-apps.document' and trashed=false",
                    fields="files(id, name, webViewLink, modifiedTime)",
                    pageSize=10,
                )
                .execute()
            )
            return json.dumps(results.get("files", []), ensure_ascii=False)
        except Exception as e:
            self._handle_error("buscar_documentos_por_autor", e)

    def search_documents_by_date(self, date_range: str) -> str:
        try:
            drive_service = self._get_drive_service()
            fecha_inicio = self._parse_fecha(date_range)
            query = "mimeType='application/vnd.google-apps.document' and trashed=false"
            if fecha_inicio:
                query += f" and modifiedTime >= '{fecha_inicio}T00:00:00'"
            results = (
                drive_service.files()
                .list(
                    q=query,
                    fields="files(id, name, webViewLink, modifiedTime)",
                    orderBy="modifiedTime desc",
                    pageSize=15,
                )
                .execute()
            )
            return json.dumps(results.get("files", []), ensure_ascii=False)
        except Exception as e:
            self._handle_error("buscar_documentos_por_fecha", e)

    def get_document_comments(self, doc_id: str) -> str:
        try:
            drive_service = self._get_drive_service()
            comments = (
                drive_service.comments()
                .list(
                    fileId=doc_id,
                    fields="comments(id,author,content,createdTime,resolved)",
                )
                .execute()
            )
            return json.dumps(comments.get("comments", []), ensure_ascii=False)
        except Exception as e:
            self._handle_error("obtener_comentarios_documento", e)

    def insert_text(self, doc_id: str, text: str, index: int = 1) -> str:
        if not text or not text.strip():
            raise ToolException(
                "El texto provisto está vacío. Se requiere contenido válido."
            )
        try:
            service = self._get_docs_service()
            requests_body = [
                {"insertText": {"location": {"index": index}, "text": text}}
            ]
            service.documents().batchUpdate(
                documentId=doc_id, body={"requests": requests_body}
            ).execute()
            return json.dumps(
                {
                    "status": "success",
                    "message": f"Texto insertado correctamente en el documento.",
                },
                ensure_ascii=False,
            )
        except Exception as e:
            self._handle_error("insertar_texto", e)

    def replace_text(
        self, doc_id: str, buscar: str, reemplazar: str, occurrence: int = 0
    ) -> str:
        if not buscar:
            raise ToolException("El parámetro 'buscar' no puede estar vacío.")
        try:
            service = self._get_docs_service()
            requests_body = [
                {
                    "replaceAllText": {
                        "containsText": {"text": buscar, "matchCase": True},
                        "replaceText": reemplazar,
                    }
                }
            ]
            service.documents().batchUpdate(
                documentId=doc_id, body={"requests": requests_body}
            ).execute()
            return json.dumps(
                {"status": "success", "message": "Reemplazo completado."},
                ensure_ascii=False,
            )
        except Exception as e:
            self._handle_error("reemplazar_texto", e)

    def format_text(self, doc_id: str, text_to_format: str, style: str) -> str:
        """Aplica formato (negrita, cursiva, etc.) a un texto específico."""
        try:
            service = self._get_docs_service()
            doc = service.documents().get(documentId=doc_id).execute()
            content = doc.get("body", {}).get("content", [])
            requests = []
            for elem in content:
                if "paragraph" in elem:
                    for el in elem["paragraph"].get("elements", []):
                        if "textRun" in el and text_to_format in el["textRun"].get(
                            "content", ""
                        ):
                            start_index = el["startIndex"] + el["textRun"][
                                "content"
                            ].find(text_to_format)
                            end_index = start_index + len(text_to_format)
                            range_update = {
                                "range": {
                                    "startIndex": start_index,
                                    "endIndex": end_index,
                                }
                            }
                            if style == "bold":
                                requests.append(
                                    {
                                        "updateTextStyle": {
                                            **range_update,
                                            "textStyle": {"bold": True},
                                            "fields": "bold",
                                        }
                                    }
                                )
                            elif style == "italic":
                                requests.append(
                                    {
                                        "updateTextStyle": {
                                            **range_update,
                                            "textStyle": {"italic": True},
                                            "fields": "italic",
                                        }
                                    }
                                )
                            elif style == "underline":
                                requests.append(
                                    {
                                        "updateTextStyle": {
                                            **range_update,
                                            "textStyle": {"underline": True},
                                            "fields": "underline",
                                        }
                                    }
                                )
                            elif style.startswith("heading_"):
                                heading_level = style.split("_")[1]
                                requests.append(
                                    {
                                        "updateParagraphStyle": {
                                            **range_update,
                                            "paragraphStyle": {
                                                "namedStyleType": f"HEADING_{heading_level}"
                                            },
                                            "fields": "namedStyleType",
                                        }
                                    }
                                )
            if not requests:
                raise ToolException(
                    f"No se encontró el texto '{text_to_format}' para formatear."
                )
            service.documents().batchUpdate(
                documentId=doc_id, body={"requests": requests}
            ).execute()
            return json.dumps(
                {"status": "success", "message": f"Formato '{style}' aplicado."}
            )
        except Exception as e:
            self._handle_error("formatear_texto", e)

    def add_comment(self, doc_id: str, comment_text: str, anchor_text: str) -> str:
        """Agrega un comentario a una porción de texto."""
        try:
            drive_service = self._get_drive_service()
            doc = self._get_docs_service().documents().get(documentId=doc_id).execute()
            content = doc.get("body", {}).get("content", [])
            anchor_range = None
            for elem in content:
                if "paragraph" in elem:
                    for el in elem["paragraph"].get("elements", []):
                        if "textRun" in el and anchor_text in el["textRun"].get(
                            "content", ""
                        ):
                            start_index = el["startIndex"] + el["textRun"][
                                "content"
                            ].find(anchor_text)
                            end_index = start_index + len(anchor_text)
                            anchor_range = {"start": start_index, "end": end_index}
                            break
                    if anchor_range:
                        break
            if not anchor_range:
                raise ToolException(f"No se encontró el texto ancla '{anchor_text}'.")

            comment = {
                "content": comment_text,
                "anchor": json.dumps(
                    {"type": "TEXT", "resolved": False, "text_range": anchor_range}
                ),
            }
            result = (
                drive_service.comments()
                .create(fileId=doc_id, body=comment, fields="id,content")
                .execute()
            )
            return json.dumps(
                {
                    "status": "success",
                    "comment_id": result.get("id"),
                    "content": result.get("content"),
                }
            )
        except Exception as e:
            self._handle_error("agregar_comentario", e)

    def fill_table(self, doc_id: str, data: List[List[str]]) -> str:
        """
        [FIX] Aplica Reverse DOM Mutation para evitar el desplazamiento
        de índices al escribir en múltiples celdas de una tabla en Google Docs.
        """
        try:
            service = self._get_docs_service()
            document = service.documents().get(documentId=doc_id).execute()
            tabla = next(
                (
                    el["table"]
                    for el in document.get("body", {}).get("content", [])
                    if "table" in el
                ),
                None,
            )
            if not tabla:
                raise ToolException(
                    "No se encontró ninguna tabla en el documento principal."
                )
            celdas_a_modificar = []
            for i, fila in enumerate(data):
                if i >= tabla["rows"]:
                    break
                for j, valor in enumerate(fila):
                    if j >= tabla["columns"]:
                        break
                    cell = tabla["tableRows"][i]["tableCells"][j]
                    celdas_a_modificar.append(
                        {
                            "start": cell["startIndex"],
                            "end": cell["endIndex"],
                            "valor": str(valor),
                        }
                    )
            celdas_a_modificar.sort(key=lambda x: x["start"], reverse=True)
            requests_body = []
            for celda in celdas_a_modificar:
                start = celda["start"]
                end = celda["end"]
                valor = celda["valor"]
                if end - start > 1:
                    requests_body.append(
                        {
                            "deleteContentRange": {
                                "range": {"startIndex": start + 1, "endIndex": end - 1}
                            }
                        }
                    )
                requests_body.append(
                    {"insertText": {"location": {"index": start + 1}, "text": valor}}
                )
            if requests_body:
                service.documents().batchUpdate(
                    documentId=doc_id, body={"requests": requests_body}
                ).execute()
            return json.dumps(
                {"status": "success", "message": "Tabla llenada con éxito."},
                ensure_ascii=False,
            )
        except Exception as e:
            self._handle_error("llenar_tabla", e)

    def insert_table(self, doc_id: str, rows: int, columns: int) -> str:
        try:
            service = self._get_docs_service()
            doc = service.documents().get(documentId=doc_id).execute()
            content = doc.get("body", {}).get("content", [])
            if not content:
                end_index = 1
            else:
                end_index = content[-1]["endIndex"] - 1
            requests_body = [
                {
                    "insertTable": {
                        "rows": rows,
                        "columns": columns,
                        "location": {"index": end_index},
                    }
                }
            ]
            service.documents().batchUpdate(
                documentId=doc_id, body={"requests": requests_body}
            ).execute()
            return json.dumps(
                {
                    "status": "success",
                    "message": f"Tabla de {rows}x{columns} insertada.",
                },
                ensure_ascii=False,
            )
        except Exception as e:
            self._handle_error("insertar_tabla", e)

    def create_document(self, title: str) -> str:
        try:
            docs_service = self._get_docs_service()
            doc = (
                docs_service.documents().create(body={"title": title.strip()}).execute()
            )
            doc_id = doc["documentId"]
            return json.dumps(
                {
                    "doc_id": doc_id,
                    "titulo": title,
                    "link": f"https://docs.google.com/document/d/{doc_id}/edit",
                    "status": "creado",
                },
                ensure_ascii=False,
            )
        except Exception as e:
            self._handle_error("crear_documento", e)

    def change_title(self, doc_id: str, new_title: str) -> str:
        try:
            drive_service = self._get_drive_service()
            drive_service.files().update(
                fileId=doc_id, body={"name": new_title.strip()}
            ).execute()
            return json.dumps(
                {
                    "status": "success",
                    "message": f"Título cambiado a '{new_title}'.",
                },
                ensure_ascii=False,
            )
        except Exception as e:
            self._handle_error("cambiar_titulo", e)

    def delete_text_by_content(
        self, doc_id: str, content: str, occurrence: int = 0
    ) -> str:
        return self.replace_text(doc_id, content, "", occurrence)

    def _parse_fecha(self, rango: str) -> Optional[str]:
        hoy = datetime.now(timezone.utc).date()
        rango = rango.lower().strip()
        if rango == "hoy":
            return hoy.isoformat()
        if rango == "ayer":
            return (hoy - timedelta(days=1)).isoformat()
        if "semana" in rango:
            return (hoy - timedelta(days=hoy.weekday())).isoformat()
        if "mes" in rango:
            return (hoy.replace(day=1) - timedelta(days=1)).replace(day=1).isoformat()
        return None

    def get_document_lists(self, nombres: str) -> str:
        raise ToolException(
            "Esta herramienta está deprecada por ineficiencia de red. Usa buscar_documentos_por_nombre individualmente."
        )

    def get_document_with_suggestions(self, doc_id: str) -> str:
        raise ToolException(
            "Lectura de sugerencias no soportada en la versión actual de la API v1 robusta."
        )

    def _make_tool(
        self, name: str, func, desc: str, schema: Any = None
    ) -> StructuredTool:
        return StructuredTool.from_function(
            name=name,
            func=func,
            description=desc,
            args_schema=schema,
            handle_tool_error=True,
        )

    def get_tool_get_content(self) -> StructuredTool:
        return self._make_tool(
            "get_doc_content",
            self.get_full_content,
            "Obtiene el contenido completo de un documento de Google Docs por su ID. SOLO pasa el ID.",
            DocIdInput,
        )

    def get_tool_search_document_by_name(self) -> StructuredTool:
        return self._make_tool(
            "find_doc_by_name",
            self.search_document_by_name,
            "Busca un documento de Google Docs por nombre exacto o aproximado en Drive.",
            SearchDocumentArgs,
        )

    def get_tool_get_document_lists(self) -> StructuredTool:
        return self._make_tool(
            "list_docs_by_names",
            self.get_document_lists,
            "Recupera múltiples documentos por nombres separados por comas.",
            DocumentNamesInput,
        )

    def get_tool_get_document_info(self) -> StructuredTool:
        return self._make_tool(
            "get_doc_info",
            self.get_document_info,
            "Obtiene metadatos de un documento: propietarios, fechas, link.",
            DocIdInput,
        )

    def get_tool_get_document_with_suggestions(self) -> StructuredTool:
        return self._make_tool(
            "get_doc_with_suggestions",
            self.get_document_with_suggestions,
            "Recupera un documento incluyendo sugerencias de edición.",
            DocIdInput,
        )

    def get_tool_get_document_comments(self) -> StructuredTool:
        return self._make_tool(
            "get_doc_comments",
            self.get_document_comments,
            "Recupera los comentarios de un documento de Google Docs.",
            DocIdInput,
        )

    def get_tool_search_documents_by_author(self) -> StructuredTool:
        return self._make_tool(
            "find_docs_by_author",
            self.search_documents_by_author,
            "Busca documentos de Google Docs por autor (email).",
            SearchDocumentsByAuthorArgs,
        )

    def get_tool_search_documents_by_date(self) -> StructuredTool:
        return self._make_tool(
            "find_docs_by_date_range",
            self.search_documents_by_date,
            "Busca documentos por rango de fecha.",
            SearchDocumentsByDateArgs,
        )

    def get_tool_create_doc(self) -> StructuredTool:
        return self._make_tool(
            "create_doc",
            self.create_document,
            "Crea un nuevo documento en Google Docs vacío. Para escribirle dentro, debes usar luego 'insert_text_in_doc'.",
            CreateDocumentArgs,
        )

    def get_tool_insert_text(self) -> StructuredTool:
        return self._make_tool(
            "insert_text_in_doc",
            self.insert_text,
            "Escribe o inserta texto dentro de un documento EXISTENTE de Google Docs usando su ID.",
            InsertTextInput,
        )

    def get_tool_change_title(self) -> StructuredTool:
        return self._make_tool(
            "change_doc_title",
            self.change_title,
            "Cambia el título o nombre de un archivo de Google Docs.",
            ChangeTitleInput,
        )

    def get_tool_replace_text(self) -> StructuredTool:
        return self._make_tool(
            "replace_doc_text",
            self.replace_text,
            "Busca y reemplaza texto específico dentro de un documento de Google Docs.",
            ReplaceTextInput,
        )

    def get_tool_format_text(self) -> StructuredTool:
        return self._make_tool(
            "format_doc_text",
            self.format_text,
            "Aplica estilos de formato (negrita, cursiva, encabezado) a un texto específico en un documento.",
            FormatTextInput,
        )

    def get_tool_add_comment(self) -> StructuredTool:
        return self._make_tool(
            "add_doc_comment",
            self.add_comment,
            "Agrega un comentario a una porción de texto (ancla) en un documento.",
            AddCommentInput,
        )

    def get_tool_delete_text_by_content(self) -> StructuredTool:
        return self._make_tool(
            "delete_doc_text_by_content",
            self.delete_text_by_content,
            "Elimina un bloque de texto de un documento buscándolo por su contenido exacto.",
            DeleteTextByContentInput,
        )

    def get_tool_insert_table(self) -> StructuredTool:
        return self._make_tool(
            "insert_table_in_doc",
            self.insert_table,
            "Inserta una tabla vacía en un documento de Google Docs al final del mismo.",
            InsertTableInput,
        )

    def get_tool_fill_table(self) -> StructuredTool:
        return self._make_tool(
            "fill_table_in_doc",
            self.fill_table,
            "Llena una tabla existente en un documento con una matriz de datos (lista de listas).",
            FillTableInput,
        )

    def get_all_tools(self) -> List[Any]:
        return [
            self.get_tool_obtener_contenido(),
            self.get_tool_buscar_documento_por_nombre(),
            self.get_tool_obtener_info_documento(),
            self.get_tool_obtener_comentarios_documento(),
            self.get_tool_buscar_documentos_por_autor(),
            self.get_tool_buscar_documentos_por_fecha(),
            self.get_tool_crear_doc(),
            self.get_tool_insertar_texto(),
            self.get_tool_cambiar_titulo(),
            self.get_tool_reemplazar_texto(),
            self.get_tool_format_text(),
            self.get_tool_add_comment(),
            self.get_tool_eliminar_texto_por_contenido(),
            self.get_tool_insertar_tabla(),
            self.get_tool_llenar_tabla(),
            self.get_tool_obtener_listas_documentos(),
            self.get_tool_obtener_documento_con_sugerencias(),
        ]


if __name__ == "__main__":
    logger.info("Modulo GoogleDocsToolProvider inicializado.")


