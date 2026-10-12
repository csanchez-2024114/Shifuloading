"""
Google Drive Tool para LangGraph / LangChain
Migración a Bóveda Segura y Resiliencia V2.
- Delega la lectura segura a app.services.drive.
- Inyección de timeout global a level socket para prevenir bloqueos.
- Implementación estricta de ToolException y handle_tool_error=True.
- Migración 100% a StructuredTool con Pydantic para prevenir alucinaciones.
- Salidas estandarizadas a JSON Strings.
"""

import json
from googleapiclient.http import MediaFileUpload
import logging
import socket
from typing import Optional, List, Dict, Any
from langchain_core.tools import StructuredTool, ToolException
from pydantic import BaseModel, Field, ConfigDict
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from app.integrations.providers.google.drive import get_drive_creds_for_langchain
from app.core.db_utils import canonicalize_email

logger = logging.getLogger("tools.google_drive")
_REQUEST_TIMEOUT = 15
socket.setdefaulttimeout(_REQUEST_TIMEOUT)


class ListFilesInput(BaseModel):
    query: str = Field(
        default="",
        alias="consulta",
        description="Filtro opcional para buscar dentro del nombre del archivo. Dejar vacío para listar todo.",
    )


class SearchFileInput(BaseModel):
    name: str = Field(..., alias="name", description="Nombre del archivo a buscar.")
    mime_type: Optional[str] = Field(
        default=None,
        alias="tipo_mime",
        description="MimeType opcional para filtrar (ej. 'application/vnd.google-apps.folder').",
    )
    exact: bool = Field(
        default=False,
        alias="exact",
        description="Si es True, busca coincidencia exacta. Si es False, usa coincidencia parcial.",
    )
    folder_id: Optional[str] = Field(
        default=None,
        alias="folder_id",
        description="ID de la carpeta padre donde buscar.",
    )


class CreateFolderInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    name: str = Field(
        ..., alias="nombre", description="Nombre de la nueva carpeta a crear."
    )
    parent_id: Optional[str] = Field(
        default=None,
        alias="carpeta_id",
        description="ID de la carpeta padre donde se alojará la nueva carpeta.",
    )


class CreateGoogleDocumentInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    name: str = Field(..., alias="nombre", description="Nombre del nuevo documento.")
    parent_id: Optional[str] = Field(
        default=None, alias="carpeta_id", description="ID de la carpeta destino."
    )


class MoveFileInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    file_name: str = Field(
        ...,
        alias="nombre_archivo",
        description="Nombre exacto del archivo que deseas mover.",
    )
    folder_name: str = Field(
        ...,
        alias="nombre_carpeta",
        description="Nombre exacto de la carpeta de destino donde se moverá el archivo.",
    )


class RenameFileInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    file_name: str = Field(
        ...,
        alias="nombre_archivo",
        description="Nombre exacto del archivo original que deseas renombrar.",
    )
    new_name: str = Field(
        ...,
        alias="nuevo_nombre",
        description="El nuevo nombre que se le asignará al archivo.",
    )


class ShareFileInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    file_id: str = Field(
        ..., alias="file_id", description="ID del archivo o carpeta a compartir."
    )
    email: str = Field(
        ...,
        alias="email",
        description="Correo electrónico del usuario con quien se compartirá.",
    )
    role: str = Field(
        default="reader", description="Rol a asignar: 'reader', 'commenter', 'writer'."
    )


class UploadFileInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    local_path: str = Field(
        ..., alias="ruta_local", description="Ruta del archivo local que se va a subir."
    )
    folder_id: Optional[str] = Field(
        default=None,
        alias="carpeta_id",
        description="ID de la carpeta de destino en Drive.",
    )


class DownloadFileInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    file_id: str = Field(
        ..., alias="file_id", description="ID del archivo a descargar."
    )
    destination_path: str = Field(
        ...,
        alias="ruta_destino",
        description="Ruta local donde se guardará el archivo.",
    )


class DeleteFileInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    file_id: str = Field(
        ..., alias="file_id", description="ID del archivo o carpeta a eliminar."
    )
    confirm: bool = Field(
        default=False,
        description="Requiere confirmación explícita para evitar borrados accidentales.",
    )


class ListFilesJsonInput(BaseModel):
    folder_id: str = Field(
        ...,
        alias="carpeta_id",
        description="ID de la carpeta a explorar de forma recursiva.",
    )
    level: int = Field(
        default=0,
        alias="level",
        description="Nivel actual de recursividad. No modificar.",
    )


class ListFilesInFolderInput(BaseModel):
    folder_id: str = Field(
        ..., alias="carpeta_id", description="ID de la carpeta a explorar."
    )


class ListFilesRecursiveInput(BaseModel):
    folder_id: str = Field(
        ..., alias="carpeta_id", description="ID de la carpeta a explorar."
    )
    level: int = Field(
        default=0, alias="level", description="Nivel de exploración. Dejar en 0."
    )
    prefix: str = Field(
        default="", description="Prefijo visual para consola. Dejar vacío."
    )


class ListModifiedFileInput(BaseModel):
    query: str = Field(
        default="", alias="consulta", description="Filtro de búsqueda por nombre."
    )


class GoogleDriveToolProvider:

    def __init__(self, user_email: str | None = None, user_id: str | None = None, account_id: str | None = None):
        email_source = user_email
        canonical = canonicalize_email(email_source) or (email_source or "")
        self.user_email = canonical
        self.user_id = user_id
        self.account_id = account_id or None
        self._service_cache = None

    def _get_service(self) -> Any:
        """
        Punto único de verdad para obtener el servicio de Google Drive autenticado.
        Delega la obtención de credenciales al servicio centralizado, que lee
        de forma segura desde la colección 'user_connected_accounts'.
        """
        if self._service_cache:
            return self._service_cache
        if not self.user_id:
            raise ValueError(
                "No se proporcionó un ID de usuario válido para acceder a Drive."
            )
        credenciales_dict = get_drive_creds_for_langchain(self.user_id, account_id=self.account_id)
        if isinstance(credenciales_dict, dict) and "error" in credenciales_dict:
            logger.error(
                f"[DriveTool] Fallo de credenciales para '{self.user_email}': {credenciales_dict['error']}"
            )
            raise ValueError(
                f"No se puede acceder a Google Drive: {credenciales_dict['error']}"
            )
        campos_requeridos = ["client_id", "client_secret", "refresh_token", "token"]
        faltantes = [c for c in campos_requeridos if not credenciales_dict.get(c)]
        if faltantes:
            logger.error(
                f"[DriveTool] Credenciales incompletas para '{self.user_email}'. Faltan: {faltantes}"
            )
            raise ValueError(
                "Credenciales de Google Drive incompletas. Por favor, reconecta tu cuenta."
            )
        try:
            credentials = Credentials.from_authorized_user_info(credenciales_dict)
            self._service_cache = build(
                "drive", "v3", credentials=credentials, cache_discovery=False
            )
            return self._service_cache
        except Exception as e:
            logger.exception(
                f"[DriveTool] Error crítico construyendo el servicio para '{self.user_email}'."
            )
            raise ValueError(f"Error de autenticación con Google Drive: {str(e)}")

    @staticmethod
    def _escape_quotes(s: str) -> str:
        return s.replace("'", "\\'")

    @staticmethod
    def _serialize_files(items: List[Dict]) -> str:
        payload = [
            {
                "id": f.get("id"),
                "name": f.get("name"),
                "mimeType": f.get("mimeType"),
                "modifiedTime": f.get("modifiedTime"),
                "webViewLink": f.get("webViewLink"),
                "iconLink": f.get("iconLink"),
                "owners": [
                    {
                        "displayName": o.get("displayName"),
                        "emailAddress": o.get("emailAddress"),
                    }
                    for o in f.get("owners") or []
                ],
            }
            for f in items
        ]
        return json.dumps(payload, ensure_ascii=False)

    def list_files_json(self, folder_id: str, level: int = 0) -> str:
        """Lista recursivamente archivos y carpetas. Retorna JSON string."""
        try:
            if level > 3:
                return json.dumps(
                    {
                        "id": folder_id,
                        "name": "Límite de profundidad",
                        "type": "warning",
                        "children": [],
                    },
                    ensure_ascii=False,
                )
            service = self._get_service()
            folder_metadata = (
                service.files()
                .get(
                    fileId=folder_id,
                    fields="id, name, driveId, mimeType, modifiedTime, owners(emailAddress)",
                )
                .execute()
            )
            drive_id = folder_metadata.get("driveId")
            q = f"'{folder_id}' in parents and trashed = false"
            all_items = []
            page_token = None
            while True:
                results = (
                    service.files()
                    .list(
                        q=q,
                        corpora="drive" if drive_id else "allDrives",
                        driveId=drive_id,
                        includeItemsFromAllDrives=True,
                        supportsAllDrives=True,
                        pageSize=100,
                        fields="nextPageToken, files(id, name, mimeType, modifiedTime, owners(emailAddress), size, webViewLink)",
                        orderBy="folder,name",
                        pageToken=page_token,
                    )
                    .execute()
                )
                items = results.get("files", [])
                all_items.extend(items)
                page_token = results.get("nextPageToken")
                if not page_token:
                    break
            carpetas = [
                f
                for f in all_items
                if f["mimeType"] == "application/vnd.google-apps.folder"
            ]
            archivos = [
                f
                for f in all_items
                if f["mimeType"] != "application/vnd.google-apps.folder"
            ]
            nodo = {
                "id": folder_metadata["id"],
                "name": folder_metadata["name"],
                "type": "folder",
                "mimeType": folder_metadata["mimeType"],
                "modifiedTime": folder_metadata.get("modifiedTime"),
                "owner": folder_metadata.get("owners", [{}])[0].get(
                    "emailAddress", "desconocido"
                ),
                "children": [],
            }
            for carpeta in carpetas:
                subcarpeta_raw = json.loads(
                    self.list_files_json(folder_id=carpeta["id"], level=level + 1)
                )
                nodo["children"].append(subcarpeta_raw)
            for archivo in archivos:
                archivo_json = {
                    "id": archivo["id"],
                    "name": archivo["name"],
                    "type": "file",
                    "mimeType": archivo["mimeType"],
                    "modifiedTime": archivo.get("modifiedTime"),
                    "owner": archivo.get("owners", [{}])[0].get(
                        "emailAddress", "desconocido"
                    ),
                    "size": archivo.get("size", "N/A"),
                    "webViewLink": archivo.get("webViewLink"),
                }
                nodo["children"].append(archivo_json)
            return json.dumps(nodo, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[DriveTool] Error en list_files_json: {e}")
            raise ToolException(f"Error explorando el directorio: {str(e)}")

    def list_files_in_folder(self, folder_id: str) -> str:
        """Lista archivos planos dentro de una carpeta específica."""
        try:
            service = self._get_service()
            folder_metadata = (
                service.files()
                .get(fileId=folder_id, fields="id, name, driveId, mimeType")
                .execute()
            )
            drive_id = folder_metadata.get("driveId")
            q = f"'{folder_id}' in parents and trashed = false"
            all_items = []
            page_token = None
            while True:
                results = (
                    service.files()
                    .list(
                        q=q,
                        corpora="drive" if drive_id else "allDrives",
                        driveId=drive_id,
                        includeItemsFromAllDrives=True,
                        supportsAllDrives=True,
                        pageSize=200,
                        fields="nextPageToken, files(id, name, mimeType, modifiedTime, owners(emailAddress))",
                        pageToken=page_token,
                    )
                    .execute()
                )
                all_items.extend(results.get("files", []))
                page_token = results.get("nextPageToken")
                if not page_token:
                    break
            if not all_items:
                return json.dumps(
                    {
                        "mensaje": f"No se encontraron archivos en la carpeta ID {folder_id}."
                    },
                    ensure_ascii=False,
                )
            return self._serialize_files(all_items)
        except Exception as e:
            logger.error(f"[DriveTool] Error en list_files_in_folder: {e}")
            raise ToolException(f"Error accediendo a carpeta de Drive: {str(e)}")

    def list_files_in_folder_recursive(
        self, folder_id: str, level: int = 0, prefix: str = ""
    ) -> str:
        """Lista archivos en formato de árbol visual de consola."""
        try:
            if level > 3:
                return f"{prefix}⚠️ [Límite de exploración alcanzado]"
            service = self._get_service()
            folder_metadata = (
                service.files()
                .get(fileId=folder_id, fields="id, name, driveId, mimeType")
                .execute()
            )
            drive_id = folder_metadata.get("driveId")
            q = f"'{folder_id}' in parents and trashed = false"
            all_items = []
            page_token = None
            while True:
                results = (
                    service.files()
                    .list(
                        q=q,
                        corpora="drive" if drive_id else "allDrives",
                        driveId=drive_id,
                        includeItemsFromAllDrives=True,
                        supportsAllDrives=True,
                        pageSize=100,
                        fields="nextPageToken, files(id, name, mimeType)",
                        orderBy="folder,name",
                        pageToken=page_token,
                    )
                    .execute()
                )
                all_items.extend(results.get("files", []))
                page_token = results.get("nextPageToken")
                if not page_token:
                    break
            if not all_items:
                return ""
            carpetas = [
                f
                for f in all_items
                if f["mimeType"] == "application/vnd.google-apps.folder"
            ]
            archivos = [
                f
                for f in all_items
                if f["mimeType"] != "application/vnd.google-apps.folder"
            ]
            salida = []
            if level == 0:
                salida.append(f"📁 {folder_metadata['name']}/")
            for idx, carpeta in enumerate(carpetas):
                es_ultimo_elemento = idx == len(carpetas) - 1 and len(archivos) == 0
                conector = "└── " if es_ultimo_elemento else "├── "
                extension = "    " if es_ultimo_elemento else "│   "
                salida.append(f"{prefix}{conector}📁 {carpeta['name']}/")
                contenido = self.list_files_in_folder_recursive(
                    carpeta["id"], level + 1, prefix + extension
                )
                if contenido:
                    salida.append(contenido)
            for idx, archivo in enumerate(archivos):
                conector = "└── " if idx == len(archivos) - 1 else "├── "
                salida.append(f"{prefix}{conector}📄 {archivo['name']}")
            return "\n".join(salida)
        except Exception as e:
            raise ToolException(f"Error generando árbol de Drive: {str(e)}")

    def list_modified_file(self, query: str = "") -> str:
        try:
            service = self._get_service()
            q = "trashed = false"
            if query:
                q = f"trashed = false and name contains '{self._escape_quotes(query)}'"
            all_items = []
            page_token = None
            while True:
                results = (
                    service.files()
                    .list(
                        q=q,
                        pageSize=100,
                        fields="nextPageToken, files(id, name, mimeType, modifiedTime, owners(emailAddress))",
                        includeItemsFromAllDrives=True,
                        supportsAllDrives=True,
                        pageToken=page_token,
                    )
                    .execute()
                )
                all_items.extend(results.get("files", []))
                page_token = results.get("nextPageToken")
                if not page_token:
                    break
            if not all_items:
                return json.dumps(
                    {"mensaje": "No se encontraron archivos en Google Drive."},
                    ensure_ascii=False,
                )
            return self._serialize_files(all_items)
        except Exception as e:
            logger.error(f"[DriveTool] Error en list_modified_file: {e}")
            raise ToolException(f"Error filtrando archivos modificados: {str(e)}")

    def list_files(self, query: str = "") -> str:
        try:
            service = self._get_service()
            results = (
                service.files()
                .list(pageSize=100, fields="files(id, name, mimeType)")
                .execute()
            )
            items = results.get("files", [])
            if not items:
                return json.dumps({"mensaje": "No se encontraron archivos."})
            return json.dumps(items, ensure_ascii=False)
        except Exception as e:
            raise ToolException(f"Error listando archivos: {str(e)}")

    def search_file(
        self,
        name: str,
        mime_type: Optional[str] = None,
        exact: bool = False,
        folder_id: Optional[str] = None,
    ) -> str:
        try:
            service = self._get_service()
            partes = ["trashed = false"]
            partes.append(
                f"name = '{self._escape_quotes(name)}'"
                if exact
                else f"name contains '{self._escape_quotes(name)}'"
            )
            if mime_type:
                partes.append(f"mimeType = '{mime_type}'")
            if folder_id:
                partes.append(f"'{folder_id}' in parents")
            results = (
                service.files()
                .list(
                    q=" and ".join(partes),
                    pageSize=1,
                    fields="files(id, name, mimeType, modifiedTime, webViewLink, iconLink, owners(displayName,emailAddress))",
                    orderBy="modifiedTime desc",
                    includeItemsFromAllDrives=True,
                    supportsAllDrives=True,
                )
                .execute()
            )
            items = results.get("files", [])
            if not items:
                return json.dumps(
                    {
                        "mensaje": f"No se encontró ningún archivo con el nombre '{name}'."
                    }
                )
            return self._serialize_files(items)
        except Exception as e:
            raise ToolException(f"Error al buscar en Google Drive: {str(e)}")

    def create_folder(self, name: str, parent_id: str = None) -> str:
        try:
            service = self._get_service()
            file_metadata = {
                "name": name,
                "mimeType": "application/vnd.google-apps.folder",
            }
            if parent_id:
                file_metadata["parents"] = [parent_id]
            result = (
                service.files()
                .create(
                    body=file_metadata,
                    fields="id, name, mimeType, parents, webViewLink",
                )
                .execute()
            )
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            raise ToolException(f"Error al crear carpeta: {str(e)}")

    def create_document(self, name: str, mime_type: str, parent_id: str = None) -> str:
        try:
            service = self._get_service()
            file_metadata = {"name": name, "mimeType": mime_type}
            if parent_id:
                file_metadata["parents"] = [parent_id]
            result = (
                service.files()
                .create(
                    body=file_metadata,
                    fields="id, name, mimeType, parents, webViewLink",
                )
                .execute()
            )
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            raise ToolException(f"Error al crear documento: {str(e)}")

    def create_google_doc(self, name: str, parent_id: str = None) -> str:
        return self.create_document(
            name, "application/vnd.google-apps.document", parent_id
        )

    def create_google_sheet(self, name: str, parent_id: str = None) -> str:
        return self.create_document(
            name, "application/vnd.google-apps.spreadsheet", parent_id
        )

    def create_google_slide(self, name: str, parent_id: str = None) -> str:
        return self.create_document(
            name, "application/vnd.google-apps.presentation", parent_id
        )

    def move_file_by_name(self, file_name: str, folder_name: str) -> str:
        try:
            service = self._get_service()
            file_results = (
                service.files()
                .list(
                    q=f"name contains '{self._escape_quotes(file_name)}' and trashed = false",
                    pageSize=1,
                    fields="files(id, name, parents)",
                )
                .execute()
            )
            if not file_results.get("files"):
                raise ToolException(f"No se encontró archivo '{file_name}'")
            file_id = file_results["files"][0]["id"]
            folder_results = (
                service.files()
                .list(
                    q=f"name contains '{self._escape_quotes(folder_name)}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
                    pageSize=1,
                    fields="files(id, name)",
                )
                .execute()
            )
            if not folder_results.get("files"):
                raise ToolException(f"No se encontró carpeta destino '{folder_name}'")
            folder_id = folder_results["files"][0]["id"]
            previous_parents = ",".join(file_results["files"][0].get("parents", []))
            result = (
                service.files()
                .update(
                    fileId=file_id,
                    addParents=folder_id,
                    removeParents=previous_parents,
                    fields="id, name, mimeType, webViewLink",
                )
                .execute()
            )
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            raise ToolException(f"Error al mover archivo: {str(e)}")

    def rename_file_by_name(self, file_name: str, new_name: str) -> str:
        try:
            service = self._get_service()
            file_results = (
                service.files()
                .list(
                    q=f"name contains '{self._escape_quotes(file_name)}' and trashed = false",
                    pageSize=1,
                    fields="files(id, name)",
                )
                .execute()
            )
            if not file_results.get("files"):
                raise ToolException(f"No se encontró archivo '{file_name}'")
            result = (
                service.files()
                .update(
                    fileId=file_results["files"][0]["id"],
                    body={"name": new_name},
                    fields="id, name, webViewLink",
                )
                .execute()
            )
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            raise ToolException(f"Error al renombrar: {str(e)}")

    def share_file(self, file_id: str, email: str, role: str = "reader") -> str:
        """Comparte un archivo con un usuario y rol específicos."""
        try:
            service = self._get_service()
            permission = {"type": "user", "role": role, "emailAddress": email}
            service.permissions().create(
                fileId=file_id, body=permission, sendNotificationEmail=True
            ).execute()
            return json.dumps(
                {
                    "status": "success",
                    "message": f"Archivo compartido con {email} como {role}.",
                }
            )
        except Exception as e:
            logger.error(f"[DriveTool] Error en share_file: {e}")
            raise ToolException(f"Error al compartir archivo: {str(e)}")

    def upload_file(self, local_path: str, folder_id: Optional[str] = None) -> str:
        """Sube un archivo a Google Drive."""
        try:
            service = self._get_service()
            file_metadata = {"name": local_path.split("/")[-1].split("\\")[-1]}
            if folder_id:
                file_metadata["parents"] = [folder_id]
            media = MediaFileUpload(local_path, resumable=True)
            file = (
                service.files()
                .create(
                    body=file_metadata, media_body=media, fields="id, name, webViewLink"
                )
                .execute()
            )
            return json.dumps({"status": "success", "file": file})
        except Exception as e:
            logger.error(f"[DriveTool] Error en upload_file: {e}")
            raise ToolException(f"Error al subir archivo: {str(e)}")

    def download_file(self, file_id: str, destination_path: str) -> str:
        """Descarga un archivo de Google Drive."""
        try:
            service = self._get_service()
            request = service.files().get_media(fileId=file_id)
            with open(destination_path, "wb") as fh:
                downloader = request
                fh.write(downloader.execute())
            return json.dumps(
                {
                    "status": "success",
                    "message": f"Archivo descargado en {destination_path}.",
                }
            )
        except Exception as e:
            logger.error(f"[DriveTool] Error en download_file: {e}")
            raise ToolException(f"Error al descargar archivo: {str(e)}")

    def delete_file(self, file_id: str, confirm: bool = False) -> str:
        """Elimina un archivo o carpeta."""
        if not confirm:
            raise ToolException(
                "La eliminación requiere confirmación. Usa el parámetro 'confirm=True'."
            )
        try:
            service = self._get_service()
            service.files().delete(fileId=file_id).execute()
            return json.dumps({"status": "deleted", "file_id": file_id})
        except Exception as e:
            logger.error(f"[DriveTool] Error en delete_file: {e}")
            raise ToolException(f"Error al eliminar archivo: {str(e)}")

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

    def get_tool(self) -> StructuredTool:
        return self._make_tool(
            "list_drive_files",
            self.list_files,
            "Lista archivos raíz del usuario autenticado en Drive.",
            ListFilesInput,
        )

    def get_tool_search_one(self) -> StructuredTool:
        return self._make_tool(
            "find_drive_file",
            self.search_file,
            "Busca la existencia y detalles de un archivo en Drive por nombre.",
            SearchFileInput,
        )

    def get_tool_create_folder(self) -> StructuredTool:
        return self._make_tool(
            "create_drive_folder",
            self.create_folder,
            "Crea un directorio o carpeta en Google Drive.",
            CreateFolderInput,
        )

    def get_tool_create_doc(self) -> StructuredTool:
        return self._make_tool(
            "create_drive_doc",
            self.create_google_doc,
            "Crea un documento de texto de Google (Doc) en Drive.",
            CreateGoogleDocumentInput,
        )

    def get_tool_create_sheet(self) -> StructuredTool:
        return self._make_tool(
            "create_drive_sheet",
            self.create_google_sheet,
            "Crea una hoja de cálculo de Google (Sheet) en Drive.",
            CreateGoogleDocumentInput,
        )

    def get_tool_create_slide(self) -> StructuredTool:
        return self._make_tool(
            "create_drive_slide",
            self.create_google_slide,
            "Crea una presentación de Google (Slide) en Drive.",
            CreateGoogleDocumentInput,
        )

    def get_tool_move_file_by_name(self) -> StructuredTool:
        return self._make_tool(
            "move_drive_file",
            self.move_file_by_name,
            "Mueve un archivo a otra carpeta usando el nombre exacto de ambos.",
            MoveFileInput,
        )

    def get_tool_rename_file_by_name(self) -> StructuredTool:
        return self._make_tool(
            "rename_drive_file",
            self.rename_file_by_name,
            "Cambia el nombre de un archivo buscando el original y pasándole el nuevo.",
            RenameFileInput,
        )

    def get_tool_share_file(self) -> StructuredTool:
        return self._make_tool(
            "share_drive_file",
            self.share_file,
            "Comparte un archivo o carpeta con un usuario específico asignándole un rol.",
            ShareFileInput,
        )

    def get_tool_upload_file(self) -> StructuredTool:
        return self._make_tool(
            "upload_drive_file",
            self.upload_file,
            "Sube un archivo desde el sistema local a Google Drive.",
            UploadFileInput,
        )

    def get_tool_download_file(self) -> StructuredTool:
        return self._make_tool(
            "download_drive_file",
            self.download_file,
            "Descarga un archivo desde Google Drive al sistema local.",
            DownloadFileInput,
        )

    def get_tool_delete_file(self) -> StructuredTool:
        return self._make_tool(
            "delete_drive_file",
            self.delete_file,
            "Elimina un archivo o carpeta de Google Drive de forma permanente. Requiere confirmación.",
            DeleteFileInput,
        )


def construir_arbol_drive(credenciales_dict: dict) -> str:
    """
    Construye y devuelve un árbol de carpetas y archivos en formato de texto.
    Se ha blindado con timeouts y protección contra fugas de logs.
    """
    try:
        if isinstance(credenciales_dict, dict) and "error" in credenciales_dict:
            return f"Error de credenciales: {credenciales_dict['error']}"
        campos_requeridos = ["client_id", "client_secret", "refresh_token", "token"]
        if not all((credenciales_dict.get(c) for c in campos_requeridos)):
            return "No se puede acceder a Google Drive: credenciales incompletas."
        credentials = Credentials.from_authorized_user_info(credenciales_dict)
        service = build("drive", "v3", credentials=credentials, cache_discovery=False)
        results = (
            service.files()
            .list(
                q="trashed = false",
                fields="files(id, name, mimeType, parents)",
                pageSize=1000,
                includeItemsFromAllDrives=True,
                supportsAllDrives=True,
            )
            .execute()
        )
        archivos = results.get("files", [])
        if not archivos:
            return "No se encontraron archivos en Google Drive."
        hijos_por_padre = {}
        for archivo in archivos:
            for padre in archivo.get("parents", ["root"]):
                hijos_por_padre.setdefault(padre, []).append(archivo)

        def recorrer_carpeta(parent_id="root", level=0):
            if level > 5:
                return ["  " * level + "- [Límite de profundidad]"]
            items = sorted(
                hijos_por_padre.get(parent_id, []), key=lambda x: x["name"].lower()
            )
            estructura = []
            for item in items:
                estructura.append(
                    f"{'  ' * level}- {item['name']} ({item['mimeType']})"
                )
                if item["mimeType"] == "application/vnd.google-apps.folder":
                    estructura += recorrer_carpeta(item["id"], level + 1)
            return estructura

        return "\n".join(recorrer_carpeta())
    except Exception as e:
        logger.error(f"[DriveTool Helper] Error al construir el árbol: {e}")
        return f"Error al explorar Google Drive: {str(e)}"

