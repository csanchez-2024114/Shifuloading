"""
Dropbox Tool Provider V2
Refactorizado:
1. Erradicación de Silent Failures (uso estricto de ToolException).
2. Helper _make_tool para inyección automática de handle_tool_error=True.
"""
import os
import json
import math
import logging
import dropbox
from dropbox import paper
from typing import Optional, List, Dict, Any, Tuple, Callable
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from langchain_core.tools import StructuredTool, ToolException
from app.integrations.providers.dropbox import get_dropbox_creds_for_langchain
from config import Config
from app.core.db_utils import canonicalize_email
load_dotenv()
logger = logging.getLogger(__name__)

class MoveFileInput(BaseModel):
    path: str = Field(..., alias='path', description='Ruta completa del archivo a mover en Dropbox.')
    destination_path: str = Field(..., alias='destination_path', description='Ruta de la carpeta destino en Dropbox.')

class CopyFileInput(BaseModel):
    path: str = Field(..., alias='path', description='Ruta del archivo original en Dropbox.')
    destination_path: str = Field(..., alias='destination_path', description='Ruta de la carpeta donde se guardará la copia.')

class FilePathInput(BaseModel):
    path: str = Field(default='', description='Ruta completa del archivo o carpeta en Dropbox. Deja vacío para la raíz.')

class CreatePaperInput(BaseModel):
    title: str = Field(..., alias='title', description='Título del documento Dropbox Paper a crear.')
    content: str = Field(default='', alias='content', description='Contenido inicial del documento en formato Markdown.')

class DeleteFileInput(BaseModel):
    file_path: str = Field(..., description='Ruta absoluta del archivo o carpeta que se desea eliminar en Dropbox.')

class SearchFolderInput(BaseModel):
    folder_name: str = Field(..., alias='folder_name', description='Nombre o ruta parcial de la carpeta a buscar en Dropbox.')

class SharedLinksInput(BaseModel):
    path: str = Field(..., description='Ruta del archivo o carpeta del que se quieren obtener los links compartidos.')

class FileVersionsInput(BaseModel):
    path: str = Field(..., description='Ruta absoluta del archivo cuyas versiones se quieren consultar.')

class CreateFolderInput(BaseModel):
    folder_name: str = Field(..., alias='folder_name', description="Nombre o ruta de la carpeta a crear en Dropbox. Ej: '/MiCarpeta' o 'ProyectoNuevo'.")

class GetSpaceInput(BaseModel):
    empty: str = Field(default='', alias='empty', description='Sin parámetros requeridos. Dejar vacío.')

class DropboxToolProvider:

    def __init__(self, user_email: str | None=None):
        email_source = user_email
        canonical = canonicalize_email(email_source) or (email_source or '')
        self.user_email = canonical

    def _get_dbx_client(self) -> dropbox.Dropbox:
        """Helper para inicializar el cliente con refresh automático."""
        try:
            creds = get_dropbox_creds_for_langchain(self.user_email)
            if 'error' in creds:
                raise ValueError(f"Error de credenciales Dropbox: {creds['error']}")
            app_key = Config.DROPBOX_CLIENT_ID
            app_secret = Config.DROPBOX_CLIENT_SECRET
            if not app_key or not app_secret:
                raise ValueError('Faltan Config.DROPBOX_CLIENT_ID o Config.DROPBOX_CLIENT_SECRET en la configuración.')
            return dropbox.Dropbox(oauth2_access_token=creds.get('access_token'), oauth2_refresh_token=creds.get('refresh_token'), app_key=app_key, app_secret=app_secret)
        except Exception as e:
            logger.error(f'[Dropbox API] Error autenticando cliente para {self.user_email}: {e}')
            raise ToolException(f'Error de autenticación con Dropbox: {str(e)}')

    def _normalize_path(self, path: str) -> str:
        """Normaliza una ruta de Dropbox."""
        if not path or path in ['/', 'root', 'raíz', '']:
            return ''
        return path if path.startswith('/') else f'/{path}'

    def _make_tool(self, name: str, func: Callable, description: str, args_schema: type[BaseModel]) -> StructuredTool:
        """Helper Enterprise para inyectar handle_tool_error=True en todas las herramientas."""
        return StructuredTool.from_function(func=func, name=name, description=description, args_schema=args_schema, handle_tool_error=True)

    def list_files(self, path: str='') -> str:
        """Lista el contenido de una ruta específica o la raíz."""
        try:
            dbx = self._get_dbx_client()
            target_path = self._normalize_path(path)
            result = dbx.files_list_folder(target_path)
            if not result.entries:
                return f"📭 La ubicación '{target_path or 'Raíz'}' está vacía."
            folders = [f.name + '/' for f in result.entries if isinstance(f, dropbox.files.FolderMetadata)]
            files = [f.name for f in result.entries if isinstance(f, dropbox.files.FileMetadata)]
            response = f"📁 **Contenido en {target_path or 'Raíz'}:**\n"
            if folders:
                response += '\n**Carpetas:**\n' + '\n'.join([f'- 📂 {f}' for f in sorted(folders)])
            if files:
                response += '\n**Archivos:**\n' + '\n'.join([f'- 📄 {f}' for f in sorted(files)])
            return response
        except Exception as e:
            logger.warning(f'[Dropbox API] Error listando archivos: {e}')
            raise ToolException(f"Error al listar archivos en '{path}': {str(e)}")

    def get_file_details(self, path: str) -> str:
        """Obtiene info detallada y un link de descarga temporal."""
        try:
            if not path:
                raise ToolException('Debes proporcionar una ruta válida para obtener detalles.')
            dbx = self._get_dbx_client()
            full_path = self._normalize_path(path)
            metadata = dbx.files_get_metadata(full_path)
            if isinstance(metadata, dropbox.files.FileMetadata):
                link_result = dbx.files_get_temporary_link(full_path)
                return f'📄 **Archivo encontrado:**\n- Nombre: {metadata.name}\n- Tamaño: {self._format_size(metadata.size)}\n- Modificado: {metadata.client_modified}\n- 🔗 Link temporal (6h): {link_result.link}'
            return f"📂 '{path}' es una carpeta, no un archivo."
        except Exception as e:
            logger.warning(f'[Dropbox API] Error obteniendo detalle: {e}')
            raise ToolException(f'Error al obtener detalle del archivo: {str(e)}')

    def get_space(self, empty: str='') -> str:
        """Obtiene el espacio usado y total de la cuenta de Dropbox."""
        try:
            dbx = self._get_dbx_client()
            usage = dbx.users_get_space_usage()
            usado = usage.used
            asignado = usage.allocation.get_individual().allocated if usage.allocation.is_individual() else 0
            porcentaje = round(usado / asignado * 100, 1) if asignado else 0
            return f'💾 **Espacio en Dropbox:**\n- Usado: {self._format_size(usado)}\n- Total: {self._format_size(asignado)}\n- Disponible: {self._format_size(asignado - usado)}\n- Uso: {porcentaje}%'
        except Exception as e:
            logger.warning(f'[Dropbox API] Error obteniendo espacio: {e}')
            raise ToolException(f'Error al obtener espacio de almacenamiento: {str(e)}')

    def search_folder_and_list_files(self, folder_name: str) -> str:
        """Busca una carpeta por nombre y lista los archivos que contiene con links temporales."""
        try:
            dbx = self._get_dbx_client()
            nombre_lower = folder_name.lower()
            resultado_busqueda = dbx.files_search_v2(query=folder_name, options=dropbox.files.SearchOptions(path='', max_results=10, file_categories=[dropbox.files.FileCategory.folder]))
            carpeta_encontrada = None
            for match in resultado_busqueda.matches:
                meta = match.metadata.get_metadata()
                if isinstance(meta, dropbox.files.FolderMetadata) and nombre_lower in meta.name.lower():
                    carpeta_encontrada = meta
                    break
            if not carpeta_encontrada:
                ruta_directa = self._normalize_path(folder_name)
                try:
                    meta = dbx.files_get_metadata(ruta_directa)
                    if isinstance(meta, dropbox.files.FolderMetadata):
                        carpeta_encontrada = meta
                except Exception:
                    pass
            if not carpeta_encontrada:
                return f"📭 No se encontró ninguna carpeta con el nombre '{folder_name}'."
            archivos = dbx.files_list_folder(carpeta_encontrada.path_lower)
            if not archivos.entries:
                return f"📭 La carpeta '{carpeta_encontrada.name}' está vacía."
            result = f"📂 **Archivos en '{carpeta_encontrada.name}':**\n\n"
            for entry in archivos.entries:
                if isinstance(entry, dropbox.files.FileMetadata):
                    try:
                        link = dbx.files_get_temporary_link(entry.path_lower)
                        result += f'- 📄 **{entry.name}** ({self._format_size(entry.size)}) | 🔗 {link.link}\n'
                    except Exception:
                        result += f'- 📄 **{entry.name}** ({self._format_size(entry.size)})\n'
                else:
                    result += f'- 📂 **{entry.name}/**\n'
            return result.strip()
        except Exception as e:
            logger.warning(f'[Dropbox API] Error en search_folder_and_list_files: {e}')
            raise ToolException(f"Error al buscar y listar carpeta '{folder_name}': {str(e)}")

    def get_shared_links(self, path: str) -> str:
        """Obtiene los enlaces compartidos de un archivo o carpeta."""
        try:
            dbx = self._get_dbx_client()
            full_path = self._normalize_path(path)
            links = dbx.sharing_list_shared_links(path=full_path, direct_only=True)
            if not links.links:
                settings = dropbox.sharing.SharedLinkSettings(requested_visibility=dropbox.sharing.RequestedVisibility.public)
                try:
                    link_meta = dbx.sharing_create_shared_link_with_settings(full_path, settings)
                    return f"🔗 **Link compartido para '{path}':**\n{link_meta.url}"
                except dropbox.exceptions.ApiError as e:
                    if 'shared_link_already_exists' in str(e):
                        links = dbx.sharing_list_shared_links(path=full_path)
                    else:
                        raise
            if not links.links:
                return f"📭 No se encontraron links compartidos para '{path}'."
            result = f"🔗 **Links compartidos para '{path}':**\n\n"
            for link in links.links:
                result += f'- {link.url}\n'
            return result.strip()
        except Exception as e:
            logger.warning(f'[Dropbox API] Error en get_shared_links: {e}')
            raise ToolException(f'Error al obtener links compartidos: {str(e)}')

    def get_versions(self, path: str) -> str:
        """Obtiene las últimas versiones de un archivo en Dropbox."""
        try:
            dbx = self._get_dbx_client()
            full_path = self._normalize_path(path)
            result = dbx.files_list_revisions(full_path, limit=10)
            if not result.entries:
                return f"📭 No se encontraron versiones para '{path}'."
            response = f"🕐 **Versiones de '{path}':**\n\n"
            for rev in result.entries:
                response += f'- **Rev:** {rev.rev} | Tamaño: {self._format_size(rev.size)} | Modificado: {rev.client_modified}\n'
            return response.strip()
        except Exception as e:
            logger.warning(f'[Dropbox API] Error en get_versions: {e}')
            raise ToolException(f'Error al obtener versiones del archivo: {str(e)}')

    def create_paper_doc(self, title: str, content: str='') -> str:
        """Crea un documento de Dropbox Paper."""
        try:
            dbx = self._get_dbx_client()
            full_content = f'# {title}\n\n{content}'.encode('utf-8')
            doc = dbx.paper_docs_create(full_content, import_format=paper.ImportFormat.markdown)
            return f"✅ Documento Paper **'{title}'** creado con éxito. ID: {doc.doc_id}"
        except Exception as e:
            logger.warning(f'[Dropbox API] Error creando Paper: {e}')
            raise ToolException(f'Error al crear documento Paper: {str(e)}')

    def create_folder(self, folder_name: str) -> str:
        """Crea una carpeta en Dropbox."""
        try:
            dbx = self._get_dbx_client()
            full_path = self._normalize_path(folder_name)
            result = dbx.files_create_folder_v2(full_path)
            return f"✅ Carpeta **'{result.metadata.name}'** creada en '{result.metadata.path_display}'."
        except dropbox.exceptions.ApiError as e:
            if 'path/conflict' in str(e):
                return f"⚠️ La carpeta '{folder_name}' ya existe en Dropbox."
            logger.warning(f'[Dropbox API] Error creando carpeta: {e}')
            raise ToolException(f'Error en API al crear carpeta: {str(e)}')
        except Exception as e:
            logger.warning(f'[Dropbox API] Error inesperado al crear carpeta: {e}')
            raise ToolException(f'Error inesperado al crear carpeta: {str(e)}')

    def move_file(self, path: str, destination_path: str) -> str:
        """Mueve un archivo a una carpeta destino."""
        try:
            dbx = self._get_dbx_client()
            from_path = self._normalize_path(path)
            name = from_path.split('/')[-1]
            destino_norm = self._normalize_path(destination_path)
            to_path = f'{destino_norm}/{name}'
            result = dbx.files_move_v2(from_path, to_path)
            return f"✅ Archivo **'{name}'** movido a '{result.metadata.path_display}'."
        except Exception as e:
            logger.warning(f'[Dropbox API] Error moviendo archivo: {e}')
            raise ToolException(f"Error al mover el archivo '{path}': {str(e)}")

    def copy_file(self, path: str, destination_path: str) -> str:
        """Copia un archivo a una carpeta destino."""
        try:
            dbx = self._get_dbx_client()
            from_path = self._normalize_path(path)
            name = from_path.split('/')[-1]
            destino_norm = self._normalize_path(destination_path)
            to_path = f'{destino_norm}/{name}'
            result = dbx.files_copy_v2(from_path, to_path)
            return f"✅ Archivo **'{name}'** copiado a '{result.metadata.path_display}'."
        except Exception as e:
            logger.warning(f'[Dropbox API] Error copiando archivo: {e}')
            raise ToolException(f"Error al copiar el archivo '{path}': {str(e)}")

    def delete_element(self, file_path: str) -> str:
        """Borra archivos o carpetas permanentemente."""
        try:
            if not file_path:
                raise ToolException('Debes proporcionar una ruta válida para eliminar.')
            dbx = self._get_dbx_client()
            full_path = self._normalize_path(file_path)
            dbx.files_delete_v2(full_path)
            return f'✅ Se ha eliminado correctamente: {file_path}'
        except Exception as e:
            logger.warning(f'[Dropbox API] Error eliminando elemento: {e}')
            raise ToolException(f"Error al eliminar el elemento '{file_path}': {str(e)}")

    def get_tool_list(self) -> StructuredTool:
        return self._make_tool(name='list_dropbox_files', func=self.list_files, description='Útil para listar todos los archivos y carpetas en Dropbox. Se puede pasar una ruta opcional; sin ruta lista la raíz.', args_schema=FilePathInput)

    def get_tool_get_file(self) -> StructuredTool:
        return self._make_tool(name='get_dropbox_file_details', func=self.get_file_details, description='Útil para obtener la información de un archivo en Dropbox: nombre, tamaño, ruta, fecha de modificación y enlace temporal.', args_schema=FilePathInput)

    def get_tool_get_space(self) -> StructuredTool:
        return self._make_tool(name='get_dropbox_space', func=self.get_space, description='Útil para obtener el espacio usado, disponible y total de la cuenta de Dropbox.', args_schema=GetSpaceInput)

    def get_tool_search_folder_and_list_files(self) -> StructuredTool:
        return self._make_tool(name='search_dropbox_folder_and_list_files', func=self.search_folder_and_list_files, description='Útil para buscar una carpeta en Dropbox por nombre y listar los archivos que contiene con enlaces temporales de descarga.', args_schema=SearchFolderInput)

    def get_tool_get_shared_links(self) -> StructuredTool:
        return self._make_tool(name='get_dropbox_shared_links', func=self.get_shared_links, description='Útil para obtener o crear los enlaces compartidos de un archivo o carpeta en Dropbox dada su ruta.', args_schema=SharedLinksInput)

    def get_tool_get_versions(self) -> StructuredTool:
        return self._make_tool(name='get_dropbox_versions', func=self.get_versions, description='Útil para obtener el historial de versiones de un archivo en Dropbox.', args_schema=FileVersionsInput)

    def get_tool_create_paper_doc(self) -> StructuredTool:
        return self._make_tool(name='create_dropbox_paper_doc', func=self.create_paper_doc, description='Útil para crear un documento en Dropbox Paper con un título y contenido inicial en formato Markdown.', args_schema=CreatePaperInput)

    def get_tool_create_folder(self) -> StructuredTool:
        return self._make_tool(name='create_dropbox_folder', func=self.create_folder, description='Útil para crear una nueva carpeta en Dropbox dado un nombre o ruta.', args_schema=CreateFolderInput)

    def get_tool_move_file(self) -> StructuredTool:
        return self._make_tool(name='move_dropbox_file', func=self.move_file, description='Útil para mover un archivo en Dropbox de su ubicación actual a una carpeta destino.', args_schema=MoveFileInput)

    def get_tool_copy_file(self) -> StructuredTool:
        return self._make_tool(name='copy_dropbox_file', func=self.copy_file, description='Útil para copiar un archivo en Dropbox a una carpeta destino manteniendo el original.', args_schema=CopyFileInput)

    def get_tool_delete_file(self) -> StructuredTool:
        return self._make_tool(name='delete_dropbox_item', func=self.delete_element, description='Útil para eliminar permanentemente un archivo o carpeta en Dropbox. ¡ACCIÓN IRREVERSIBLE!', args_schema=DeleteFileInput)

    def get_all_tools(self) -> List[Any]:
        """Retorna la lista maestra unificada de todas las herramientas."""
        return [self.get_tool_list(), self.get_tool_get_file(), self.get_tool_get_space(), self.get_tool_search_folder_and_list_files(), self.get_tool_get_shared_links(), self.get_tool_get_versions(), self.get_tool_create_paper_doc(), self.get_tool_create_folder(), self.get_tool_move_file(), self.get_tool_copy_file(), self.get_tool_delete_file()]

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        if size_bytes == 0:
            return '0 B'
        size_names = ('B', 'KB', 'MB', 'GB', 'TB')
        i = int(math.floor(math.log(size_bytes, 1024)))
        p = math.pow(1024, i)
        s = round(size_bytes / p, 2)
        return f'{s} {size_names[i]}'

