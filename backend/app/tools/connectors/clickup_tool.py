"""
ClickUp Tool para LangGraph / LangChain
Migración a Bóveda Segura, Multicuenta y Resiliencia.
- Implementa el motor de lectura centralizado (get_user_vault_with_fallback).
- Erradicación de fallos silenciosos (uso estricto de ToolException).
- Inyección de handle_tool_error=True vía _make_tool.
- Implementa puente asíncrono robusto para integrarse al event loop de LangGraph.
- Previene bloqueos del Agente propagando excepciones hacia el motor de retry.
"""

import re
import logging
import requests
import asyncio
import concurrent.futures
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple, Any, Callable
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool, ToolException
from app.database import get_user_vault_with_fallback, get_async_database
from app.core.db_utils import canonicalize_email

try:
    from asgiref.sync import async_to_sync
except ImportError:
    async_to_sync = None
load_dotenv()
logger = logging.getLogger("tools.clickup")
CLICKUP_API_BASE = "https://api.clickup.com/api/v2"
_REQUEST_TIMEOUT = 15


class ListSpacesInput(BaseModel):
    filter: str = Field(
        default="",
        alias="filter",
        description="Filtro opcional por nombre. Dejar vacío para listar todos.",
    )


class SearchTasksInput(BaseModel):
    project_name: str = Field(
        ...,
        alias="project_name",
        description="Nombre del proyecto/lista y filtros opcionales en lenguaje natural (ej: urgente, alta prioridad).",
    )


class CreateTaskInput(BaseModel):
    prompt_text: str = Field(
        ...,
        description="Instrucción del usuario. Ej: 'Crea la tarea [X] en la lista [Y]'.",
    )


class ListFoldersInput(BaseModel):
    space_name: str = Field(
        ...,
        alias="space_name",
        description="Nombre del espacio de ClickUp cuyas carpetas se quieren listar.",
    )


class ListListsInput(BaseModel):
    project_name: str = Field(
        ...,
        alias="project_name",
        description="Nombre del proyecto, espacio o carpeta cuyas listas se quieren listar.",
    )


class GetTaskInput(BaseModel):
    task_id: str = Field(..., description="ID único de la tarea en ClickUp.")


class ListMembersInput(BaseModel):
    team_id: str = Field(
        ...,
        description="ID del equipo (team) en ClickUp cuyos miembros se quieren listar.",
    )


class GetDocumentInput(BaseModel):
    doc_id: str = Field(..., description="ID único del documento (workdoc) en ClickUp.")


class ListDocumentsByNameInput(BaseModel):
    project_name: str = Field(
        ...,
        alias="project_name",
        description="Nombre del proyecto, espacio o carpeta para buscar documentos relacionados.",
    )


class CreateListInput(BaseModel):
    prompt_text: str = Field(
        ...,
        description="Instrucción del usuario. Ej: 'Crea una lista llamada X en la carpeta Y'.",
    )


class CreateFolderInput(BaseModel):
    prompt_text: str = Field(
        ...,
        description="Instrucción del usuario. Ej: 'Crea una carpeta llamada X en el espacio Y'.",
    )


class AssignTaskInput(BaseModel):
    task_id: str = Field(
        ..., description="ID único de la tarea a la que se asignará el miembro."
    )
    member_id: str = Field(
        ...,
        description="ID numérico del miembro de ClickUp que se asignará a la tarea.",
    )


class AddCommentInput(BaseModel):
    prompt_text: str = Field(
        ...,
        description="Instrucción. Ej: 'Agrega el comentario listo en la tarea X del proyecto Y'.",
    )


class UpdateDueDateInput(BaseModel):
    prompt_text: str = Field(
        ...,
        description="Instrucción. Ej: 'Cambia la fecha de entrega de la tarea X a 25/12/2025'.",
    )


class ClickUpToolProvider:

    def __init__(
        self,
        user_email: str | None = None,
        active_accounts: Optional[Dict[str, str]] = None,
    ):
        """
        Inicializa el proveedor con soporte para inyección dinámica de cuentas activas.
        """
        email_source = user_email
        canonical = canonicalize_email(email_source) or (email_source or "")
        self.user_email = canonical
        self.active_accounts = active_accounts or {}
        self.account_id = self.active_accounts.get(
            "clickup"
        ) or self.active_accounts.get("ClickUp")

    def _run_async_safely(self, coro_func: Callable) -> Any:
        """Puente arquitectónico seguro para ejecutar corrutinas en hilos sincrónicos."""
        if async_to_sync:
            return async_to_sync(coro_func)()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                return executor.submit(lambda: asyncio.run(coro_func())).result()
        else:
            return asyncio.run(coro_func())

    def _get_secure_token(self) -> str:
        """
        Obtiene el token desencriptado usando la arquitectura de multicuentas centralizada.
        Utiliza la colección 'user_connected_accounts' para obtener las credenciales.
        """
        if not self.user_email:
            raise ToolException(
                "Error de identidad: correo de usuario ausente para autenticar con ClickUp."
            )

        async def fetch_token():
            db_conn = get_async_database()
            vault = await get_user_vault_with_fallback(
                self.user_email, db_conn, account_id=self.account_id
            )
            clickup_creds = vault.get("clickup") or vault.get("ClickUp")
            if not clickup_creds or not clickup_creds.get("token"):
                raise ToolException(
                    "ClickUp no está conectado o el token es inválido. Por favor, conecta tu cuenta en la configuración."
                )
            return clickup_creds["token"]

        return self._run_async_safely(fetch_token)

    def _get_headers(self) -> Dict[str, str]:
        """Centraliza la autenticación generando headers estándar de manera segura."""
        token = self._get_secure_token()
        return {"Authorization": token, "Content-Type": "application/json"}

    def _make_tool(
        self, name: str, func: Callable, description: str, args_schema: type[BaseModel]
    ) -> StructuredTool:
        """Helper Enterprise para inyectar handle_tool_error=True en todas las herramientas."""
        return StructuredTool.from_function(
            func=func,
            name=name,
            description=description,
            args_schema=args_schema,
            handle_tool_error=True,
        )

    def _get_teams(self, headers: Dict) -> List[Dict]:
        try:
            resp = requests.get(
                f"{CLICKUP_API_BASE}/team", headers=headers, timeout=_REQUEST_TIMEOUT
            )
            resp.raise_for_status()
            return resp.json().get("teams", [])
        except requests.exceptions.RequestException as e:
            logger.error(f"[ClickUp API] Error en _get_teams: {e}")
            raise ToolException(f"Error de conexión con ClickUp (Teams): {str(e)}")

    def _get_spaces(self, team_id: str, headers: Dict) -> List[Dict]:
        try:
            resp = requests.get(
                f"{CLICKUP_API_BASE}/team/{team_id}/space",
                headers=headers,
                timeout=_REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json().get("spaces", [])
        except requests.exceptions.RequestException as e:
            logger.error(f"[ClickUp API] Error en _get_spaces: {e}")
            raise ToolException(f"Error de conexión con ClickUp (Spaces): {str(e)}")

    def _get_folders(self, space_id: str, headers: Dict) -> List[Dict]:
        try:
            resp = requests.get(
                f"{CLICKUP_API_BASE}/space/{space_id}/folder",
                headers=headers,
                timeout=_REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json().get("folders", [])
        except requests.exceptions.RequestException as e:
            logger.error(f"[ClickUp API] Error en _get_folders: {e}")
            raise ToolException(f"Error de conexión con ClickUp (Folders): {str(e)}")

    def _get_lists_in_folder(self, folder_id: str, headers: Dict) -> List[Dict]:
        try:
            resp = requests.get(
                f"{CLICKUP_API_BASE}/folder/{folder_id}/list",
                headers=headers,
                timeout=_REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json().get("lists", [])
        except requests.exceptions.RequestException as e:
            logger.error(f"[ClickUp API] Error en _get_lists_in_folder: {e}")
            raise ToolException(f"Error de conexión con ClickUp (Lists): {str(e)}")

    def _get_folderless_lists(self, space_id: str, headers: Dict) -> List[Dict]:
        try:
            resp = requests.get(
                f"{CLICKUP_API_BASE}/space/{space_id}/list",
                headers=headers,
                timeout=_REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json().get("lists", [])
        except requests.exceptions.RequestException as e:
            logger.error(f"[ClickUp API] Error en _get_folderless_lists: {e}")
            raise ToolException(
                f"Error de conexión con ClickUp (Folderless Lists): {str(e)}"
            )

    def _get_tasks_in_list(self, list_id: str, headers: Dict) -> List[Dict]:
        try:
            resp = requests.get(
                f"{CLICKUP_API_BASE}/list/{list_id}/task?include_closed=true",
                headers=headers,
                timeout=_REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json().get("tasks", [])
        except requests.exceptions.RequestException as e:
            logger.error(f"[ClickUp API] Error en _get_tasks_in_list: {e}")
            raise ToolException(f"Error de conexión con ClickUp (Tasks): {str(e)}")

    def _find_list_by_name(self, nombre: str, headers: Dict) -> Optional[Dict]:
        teams = self._get_teams(headers)
        nombre_lower = nombre.lower()
        for team in teams:
            for space in self._get_spaces(team["id"], headers):
                for folder in self._get_folders(space["id"], headers):
                    for lst in self._get_lists_in_folder(folder["id"], headers):
                        if nombre_lower in lst["name"].lower():
                            return lst
                for lst in self._get_folderless_lists(space["id"], headers):
                    if nombre_lower in lst["name"].lower():
                        return lst
        return None

    def _find_space_by_name(self, nombre: str, headers: Dict) -> Optional[Dict]:
        teams = self._get_teams(headers)
        nombre_lower = nombre.lower()
        for team in teams:
            for space in self._get_spaces(team["id"], headers):
                if nombre_lower in space["name"].lower():
                    return {**space, "team_id": team["id"]}
        return None

    def _find_folder_by_name(self, nombre: str, headers: Dict) -> Optional[Dict]:
        teams = self._get_teams(headers)
        nombre_lower = nombre.lower()
        for team in teams:
            for space in self._get_spaces(team["id"], headers):
                for folder in self._get_folders(space["id"], headers):
                    if nombre_lower in folder["name"].lower():
                        return folder
        return None

    def _parse_fecha(self, texto_fecha: str) -> Optional[int]:
        texto = texto_fecha.strip().lower()
        hoy = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        if texto in ["hoy", "today"]:
            dt = hoy
        elif texto in ["mañana", "manana", "tomorrow"]:
            dt = hoy + timedelta(days=1)
        elif texto == "pasado mañana":
            dt = hoy + timedelta(days=2)
        else:
            for fmt in ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"]:
                try:
                    dt = datetime.strptime(texto_fecha.strip(), fmt)
                    break
                except ValueError:
                    continue
            else:
                return None
        return int(dt.timestamp() * 1000)

    def list_spaces(self, filter: str = "") -> str:
        try:
            headers = self._get_headers()
            teams = self._get_teams(headers)
            if not teams:
                return "📭 No se encontraron equipos en esta cuenta de ClickUp."
            result = "📋 **Estructura de ClickUp:**\n"
            for team in teams:
                result += f"\n👥 Equipo: **{team['name']}**\n"
                for s in self._get_spaces(team["id"], headers):
                    result += f"  🗂️ {s['name']} (ID: {s['id']})\n"
            return result.strip()
        except ToolException:
            raise
        except Exception as e:
            logger.error(f"[ClickUp API] Error en list_spaces: {e}")
            raise ToolException(f"Error interno al listar espacios: {str(e)}")

    def list_folders(self, space_name: str) -> str:
        try:
            headers = self._get_headers()
            space = self._find_space_by_name(space_name, headers)
            if not space:
                raise ToolException(f"No se encontró el espacio '{space_name}'.")
            folders = self._get_folders(space["id"], headers)
            if not folders:
                return f"📭 El espacio '{space_name}' no tiene carpetas."
            result = f"📂 **Carpetas en '{space_name}':**\n\n"
            for f in folders:
                result += f"- **{f['name']}** (ID: {f['id']})\n"
            return result.strip()
        except ToolException:
            raise
        except Exception as e:
            logger.error(f"[ClickUp API] Error en list_folders: {e}")
            raise ToolException(f"Error interno al listar carpetas: {str(e)}")

    def list_lists(self, project_name: str) -> str:
        try:
            headers = self._get_headers()
            todas_listas: List[str] = []
            space = self._find_space_by_name(project_name, headers)
            if space:
                for folder in self._get_folders(space["id"], headers):
                    for lst in self._get_lists_in_folder(folder["id"], headers):
                        todas_listas.append(
                            f"- **{lst['name']}** (Carpeta: {folder['name']}, ID: {lst['id']})"
                        )
                for lst in self._get_folderless_lists(space["id"], headers):
                    todas_listas.append(
                        f"- **{lst['name']}** (Sin carpeta, ID: {lst['id']})"
                    )
            if not todas_listas:
                folder = self._find_folder_by_name(project_name, headers)
                if folder:
                    for lst in self._get_lists_in_folder(folder["id"], headers):
                        todas_listas.append(f"- **{lst['name']}** (ID: {lst['id']})")
            if not todas_listas:
                return f"📭 No se encontraron listas en '{project_name}'."
            result = f"📋 **Listas en '{project_name}':**\n\n"
            result += "\n".join(todas_listas)
            return result.strip()
        except ToolException:
            raise
        except Exception as e:
            logger.error(f"[ClickUp API] Error en list_lists: {e}")
            raise ToolException(f"Error interno al listar listas: {str(e)}")

    def list_tasks_by_name(self, project_name: str) -> str:
        try:
            headers = self._get_headers()
            nombre_lower = project_name.lower()
            lista = self._find_list_by_name(project_name, headers)
            if not lista:
                space = self._find_space_by_name(project_name, headers)
                if space:
                    folders = self._get_folders(space["id"], headers)
                    if folders:
                        listas = self._get_lists_in_folder(folders[0]["id"], headers)
                        lista = listas[0] if listas else None
                    if not lista:
                        listas_sin_carpeta = self._get_folderless_lists(
                            space["id"], headers
                        )
                        lista = listas_sin_carpeta[0] if listas_sin_carpeta else None
            if not lista:
                raise ToolException(
                    f"No se encontraron listas o proyectos relacionados con '{project_name}'."
                )
            tareas = self._get_tasks_in_list(lista["id"], headers)
            if not tareas:
                return f"📭 No hay tareas en '{lista['name']}'."
            if "urgente" in nombre_lower:
                tareas = [t for t in tareas if t.get("priority", {}).get("id") == "1"]
            elif "alta" in nombre_lower or "high" in nombre_lower:
                tareas = [t for t in tareas if t.get("priority", {}).get("id") == "2"]
            result = f"📋 **Tareas en '{lista['name']}':**\n\n"
            for t in tareas:
                status = t.get("status", {}).get("status", "N/A")
                prioridad = (
                    t.get("priority", {}).get("priority", "normal")
                    if t.get("priority")
                    else "normal"
                )
                asignados = (
                    ", ".join([a["username"] for a in t.get("assignees", [])])
                    or "Sin asignar"
                )
                result += f"🔹 **{t['name']}** | Estado: {status} | Prioridad: {prioridad} | Asignado: {asignados}\n"
            return result.strip()
        except ToolException:
            raise
        except Exception as e:
            logger.error(f"[ClickUp API] Error en list_tasks_by_name: {e}")
            raise ToolException(f"Error al procesar la búsqueda de tareas: {str(e)}")

    def get_task(self, task_id: str) -> str:
        try:
            headers = self._get_headers()
            response = requests.get(
                f"{CLICKUP_API_BASE}/task/{task_id}",
                headers=headers,
                timeout=_REQUEST_TIMEOUT,
            )
            if response.status_code != 200:
                raise ToolException(
                    f"Error al obtener tarea en ClickUp: {response.text}"
                )
            t = response.json()
            asignados = (
                ", ".join([a["username"] for a in t.get("assignees", [])])
                or "Sin asignar"
            )
            status = t.get("status", {}).get("status", "N/A")
            prioridad = (
                t.get("priority", {}).get("priority", "normal")
                if t.get("priority")
                else "normal"
            )
            due_date = (
                datetime.fromtimestamp(int(t["due_date"]) / 1000).strftime("%Y-%m-%d")
                if t.get("due_date")
                else "N/A"
            )
            return f"📌 **{t.get('name')}** (ID: {task_id})\n- Estado: {status}\n- Prioridad: {prioridad}\n- Asignados: {asignados}\n- Fecha de entrega: {due_date}\n- Descripción: {t.get('description', 'Sin descripción')[:300]}"
        except ToolException:
            raise
        except Exception as e:
            logger.error(f"[ClickUp API] Error en get_task: {e}")
            raise ToolException(f"Error interno al obtener tarea: {str(e)}")

    def list_members(self, team_id: str) -> str:
        try:
            headers = self._get_headers()
            response = requests.get(
                f"{CLICKUP_API_BASE}/team/{team_id}/member",
                headers=headers,
                timeout=_REQUEST_TIMEOUT,
            )
            if response.status_code != 200:
                raise ToolException(
                    f"Error al listar miembros del equipo en ClickUp: {response.text}"
                )
            members = response.json().get("members", [])
            if not members:
                return f"📭 No se encontraron miembros en el equipo '{team_id}'."
            result = f"👥 **Miembros del equipo {team_id}:**\n\n"
            for m in members:
                user = m.get("user", m)
                result += f"- **{user.get('username', 'N/A')}** | {user.get('email', 'N/A')} (ID: {user.get('id', 'N/A')})\n"
            return result.strip()
        except ToolException:
            raise
        except Exception as e:
            logger.error(f"[ClickUp API] Error en list_members: {e}")
            raise ToolException(f"Error interno al listar miembros: {str(e)}")

    def get_document(self, doc_id: str) -> str:
        try:
            headers = self._get_headers()
            teams = self._get_teams(headers)
            if not teams:
                raise ToolException("No se encontraron equipos en ClickUp.")
            workspace_id = teams[0]["id"]
            response = requests.get(
                f"{CLICKUP_API_BASE}/workspaces/{workspace_id}/docs/{doc_id}",
                headers=headers,
                timeout=_REQUEST_TIMEOUT,
            )
            if response.status_code != 200:
                raise ToolException(
                    f"Error al obtener documento en ClickUp: {response.text}"
                )
            doc = response.json()
            return f"📄 **{doc.get('name', 'Sin título')}** (ID: {doc_id})\n- Creado: {doc.get('date_created', 'N/A')}\n- Actualizado: {doc.get('date_updated', 'N/A')}\n- Visibilidad: {doc.get('visibility', 'N/A')}"
        except ToolException:
            raise
        except Exception as e:
            logger.error(f"[ClickUp API] Error en get_document: {e}")
            raise ToolException(f"Error interno al obtener documento: {str(e)}")

    def list_documents_by_name(self, project_name: str) -> str:
        try:
            headers = self._get_headers()
            teams = self._get_teams(headers)
            if not teams:
                raise ToolException("No se encontraron equipos en ClickUp.")
            workspace_id = teams[0]["id"]
            response = requests.get(
                f"{CLICKUP_API_BASE}/workspaces/{workspace_id}/docs",
                headers=headers,
                timeout=_REQUEST_TIMEOUT,
            )
            if response.status_code != 200:
                raise ToolException(
                    f"Error al listar documentos en ClickUp: {response.text}"
                )
            docs = response.json().get("docs", [])
            if project_name.strip():
                docs = [
                    d for d in docs if project_name.lower() in d.get("name", "").lower()
                ]
            if not docs:
                return f"📭 No se encontraron documentos relacionados con '{project_name}'."
            result = f"📄 **Documentos en ClickUp ('{project_name}'):**\n\n"
            for d in docs:
                result += (
                    f"- **{d.get('name', 'Sin título')}** (ID: {d.get('id', 'N/A')})\n"
                )
            return result.strip()
        except ToolException:
            raise
        except Exception as e:
            logger.error(f"[ClickUp API] Error en list_documents_by_name: {e}")
            raise ToolException(f"Error interno al listar documentos: {str(e)}")

    def create_task(self, prompt_text: str) -> str:
        try:
            headers = self._get_headers()
            match = re.search(
                "tarea\\s+['\\\"]?(.+?)['\\\"]?\\s+en\\s+(?:el proyecto|la lista|el espacio)?\\s*['\\\"]?(.+?)['\\\"]?$",
                prompt_text,
                re.I,
            )
            if not match:
                raise ToolException(
                    "Formato no reconocido. Ejemplo requerido: 'Crea la tarea [X] en la lista [Y]'"
                )
            nombre_task, nombre_destino = (
                match.group(1).strip(),
                match.group(2).strip(),
            )
            lista = self._find_list_by_name(nombre_destino, headers)
            if not lista:
                raise ToolException(
                    f"No se encontró la lista '{nombre_destino}'. Verifica el nombre."
                )
            payload = {
                "name": nombre_task,
                "description": "Creado por Shifu AI",
                "priority": 3,
            }
            resp = requests.post(
                f"{CLICKUP_API_BASE}/list/{lista['id']}/task",
                headers=headers,
                json=payload,
                timeout=_REQUEST_TIMEOUT,
            )
            if resp.status_code in [200, 201]:
                return f"✅ Tarea '{nombre_task}' creada con éxito en la lista '{lista['name']}'."
            logger.warning(f"[ClickUp API] Error al crear tarea: {resp.text}")
            raise ToolException(
                f"Error al intentar crear la tarea en ClickUp: {resp.text}"
            )
        except ToolException:
            raise
        except Exception as e:
            logger.error(f"[ClickUp API] Excepción al crear tarea: {e}")
            raise ToolException(
                f"Error interno procesando la creación de tarea: {str(e)}"
            )

    def create_list(self, prompt_text: str) -> str:
        try:
            headers = self._get_headers()
            match = re.search(
                "lista\\s+['\\\"]?(.+?)['\\\"]?\\s+en\\s+(?:la carpeta|el espacio)?\\s*['\\\"]?(.+?)['\\\"]?$",
                prompt_text,
                re.I,
            )
            if not match:
                raise ToolException(
                    "Formato no reconocido. Ejemplo requerido: 'Crea una lista llamada X en la carpeta Y'"
                )
            nombre_lista, nombre_destino = (
                match.group(1).strip(),
                match.group(2).strip(),
            )
            folder = self._find_folder_by_name(nombre_destino, headers)
            if folder:
                url = f"{CLICKUP_API_BASE}/folder/{folder['id']}/list"
            else:
                space = self._find_space_by_name(nombre_destino, headers)
                if not space:
                    raise ToolException(
                        f"No se encontró la carpeta o espacio '{nombre_destino}'."
                    )
                url = f"{CLICKUP_API_BASE}/space/{space['id']}/list"
            resp = requests.post(
                url,
                headers=headers,
                json={"name": nombre_lista},
                timeout=_REQUEST_TIMEOUT,
            )
            if resp.status_code in [200, 201]:
                return (
                    f"✅ Lista '{nombre_lista}' creada con éxito en '{nombre_destino}'."
                )
            raise ToolException(f"Error de ClickUp al crear lista: {resp.text}")
        except ToolException:
            raise
        except Exception as e:
            logger.error(f"[ClickUp API] Error en create_list: {e}")
            raise ToolException(f"Error interno al crear lista: {str(e)}")

    def create_folder(self, prompt_text: str) -> str:
        try:
            headers = self._get_headers()
            match = re.search(
                "carpeta\\s+['\\\"]?(.+?)['\\\"]?\\s+en\\s+(?:el espacio|el proyecto)?\\s*['\\\"]?(.+?)['\\\"]?$",
                prompt_text,
                re.I,
            )
            if not match:
                raise ToolException(
                    "Formato no reconocido. Ejemplo requerido: 'Crea una carpeta llamada X en el espacio Y'"
                )
            nombre_carpeta, space_name = (
                match.group(1).strip(),
                match.group(2).strip(),
            )
            space = self._find_space_by_name(space_name, headers)
            if not space:
                raise ToolException(f"No se encontró el espacio '{space_name}'.")
            resp = requests.post(
                f"{CLICKUP_API_BASE}/space/{space['id']}/folder",
                headers=headers,
                json={"name": nombre_carpeta},
                timeout=_REQUEST_TIMEOUT,
            )
            if resp.status_code in [200, 201]:
                return f"✅ Carpeta '{nombre_carpeta}' creada con éxito en el espacio '{space_name}'."
            raise ToolException(f"Error de ClickUp al crear carpeta: {resp.text}")
        except ToolException:
            raise
        except Exception as e:
            logger.error(f"[ClickUp API] Error en create_folder: {e}")
            raise ToolException(f"Error interno al crear carpeta: {str(e)}")

    def assign_task(self, task_id: str, member_id: str) -> str:
        try:
            headers = self._get_headers()
            resp = requests.post(
                f"{CLICKUP_API_BASE}/task/{task_id}/member",
                headers=headers,
                json={"assignee": int(member_id)},
                timeout=_REQUEST_TIMEOUT,
            )
            if resp.status_code in [200, 201]:
                return f"✅ Miembro (ID: {member_id}) asignado a la tarea (ID: {task_id}) con éxito."
            raise ToolException(f"Error de ClickUp al asignar tarea: {resp.text}")
        except ToolException:
            raise
        except Exception as e:
            logger.error(f"[ClickUp API] Error en assign_task: {e}")
            raise ToolException(f"Error interno al asignar tarea: {str(e)}")

    def add_comment(self, prompt_text: str) -> str:
        try:
            headers = self._get_headers()
            match = re.search(
                "comentario\\s+['\\\"]?(.+?)['\\\"]?\\s+(?:en|a)\\s+(?:la tarea\\s+)?['\\\"]?(.+?)['\\\"]?(?:\\s+del proyecto|\\s+en)?\\s*['\\\"]?(.+?)?['\\\"]?$",
                prompt_text,
                re.I,
            )
            if not match:
                raise ToolException(
                    "Formato no reconocido. Ejemplo requerido: 'Agrega el comentario X en la tarea Y del proyecto Z'"
                )
            comentario = match.group(1).strip()
            nombre_tarea = match.group(2).strip()
            project_name = match.group(3).strip() if match.group(3) else ""
            busqueda = project_name if project_name else nombre_tarea
            lista = self._find_list_by_name(busqueda, headers)
            if lista:
                tareas = self._get_tasks_in_list(lista["id"], headers)
                task = next(
                    (t for t in tareas if nombre_tarea.lower() in t["name"].lower()),
                    None,
                )
            else:
                task = None
            if not task:
                raise ToolException(f"No se encontró la tarea '{nombre_tarea}'.")
            resp = requests.post(
                f"{CLICKUP_API_BASE}/task/{task['id']}/comment",
                headers=headers,
                json={"comment_text": comentario, "notify_all": False},
                timeout=_REQUEST_TIMEOUT,
            )
            if resp.status_code in [200, 201]:
                return f"✅ Comentario agregado a la tarea '{task['name']}'."
            raise ToolException(f"Error de ClickUp al agregar comentario: {resp.text}")
        except ToolException:
            raise
        except Exception as e:
            logger.error(f"[ClickUp API] Error en add_comment: {e}")
            raise ToolException(f"Error interno al agregar comentario: {str(e)}")

    def update_due_date(self, prompt_text: str) -> str:
        try:
            headers = self._get_headers()
            match = re.search(
                "(?:tarea|de)\\s+['\\\"]?(.+?)['\\\"]?\\s+a\\s+['\\\"]?(.+?)['\\\"]?$",
                prompt_text,
                re.I,
            )
            if not match:
                raise ToolException(
                    "Formato no reconocido. Ejemplo requerido: 'Cambia la fecha de entrega de la tarea X a 25/12/2025'"
                )
            nombre_tarea, texto_fecha = (match.group(1).strip(), match.group(2).strip())
            due_date_ms = self._parse_fecha(texto_fecha)
            if not due_date_ms:
                raise ToolException(
                    f"No se pudo interpretar la fecha '{texto_fecha}'. Usa formatos: dd/mm/yyyy, hoy, mañana."
                )
            teams = self._get_teams(headers)
            tarea_encontrada = None
            for team in teams:
                for space in self._get_spaces(team["id"], headers):
                    for folder in self._get_folders(space["id"], headers):
                        for lst in self._get_lists_in_folder(folder["id"], headers):
                            for t in self._get_tasks_in_list(lst["id"], headers):
                                if nombre_tarea.lower() in t["name"].lower():
                                    tarea_encontrada = t
                                    break
                            if tarea_encontrada:
                                break
                        if tarea_encontrada:
                            break
                    if tarea_encontrada:
                        break
                if tarea_encontrada:
                    break
            if not tarea_encontrada:
                raise ToolException(f"No se encontró la tarea '{nombre_tarea}'.")
            resp = requests.put(
                f"{CLICKUP_API_BASE}/task/{tarea_encontrada['id']}",
                headers=headers,
                json={"due_date": due_date_ms},
                timeout=_REQUEST_TIMEOUT,
            )
            if resp.status_code == 200:
                fecha_fmt = datetime.fromtimestamp(due_date_ms / 1000).strftime(
                    "%d/%m/%Y"
                )
                return f"✅ Fecha de entrega de '{tarea_encontrada['name']}' actualizada a {fecha_fmt}."
            raise ToolException(f"Error de ClickUp al actualizar fecha: {resp.text}")
        except ToolException:
            raise
        except Exception as e:
            logger.error(f"[ClickUp API] Error en update_due_date: {e}")
            raise ToolException(f"Error interno al actualizar fecha: {str(e)}")

    def get_tool_list_spaces(self) -> StructuredTool:
        return self._make_tool(
            func=self.list_spaces,
            name="list_clickup_spaces",
            description="Muestra todos los espacios y equipos de ClickUp.",
            args_schema=ListSpacesInput,
        )

    def get_tool_list_folders(self) -> StructuredTool:
        return self._make_tool(
            func=self.list_folders,
            name="list_clickup_folders",
            description="Lista carpetas dentro de un espacio de ClickUp.",
            args_schema=ListFoldersInput,
        )

    def get_tool_list_lists(self) -> StructuredTool:
        return self._make_tool(
            func=self.list_lists,
            name="list_clickup_lists",
            description="Lista listas de un proyecto o espacio en ClickUp.",
            args_schema=ListListsInput,
        )

    def get_tool_list_tasks(self) -> StructuredTool:
        return self._make_tool(
            func=self.list_tasks_by_name,
            name="list_clickup_tasks",
            description="Lista tareas en ClickUp según nombre del proyecto.",
            args_schema=SearchTasksInput,
        )

    def get_tool_get_task(self) -> StructuredTool:
        return self._make_tool(
            func=self.get_task,
            name="get_clickup_task",
            description="Obtiene detalles de una tarea específica de ClickUp dado su ID.",
            args_schema=GetTaskInput,
        )

    def get_tool_list_members(self) -> StructuredTool:
        return self._make_tool(
            func=self.list_members,
            name="list_clickup_members",
            description="Lista los miembros de un equipo en ClickUp dado su ID.",
            args_schema=ListMembersInput,
        )

    def get_tool_get_document(self) -> StructuredTool:
        return self._make_tool(
            func=self.get_document,
            name="get_clickup_document",
            description="Obtiene los detalles de un documento (workdoc) en ClickUp.",
            args_schema=GetDocumentInput,
        )

    def get_tool_list_documents_by_name(self) -> StructuredTool:
        return self._make_tool(
            func=self.list_documents_by_name,
            name="search_clickup_documents_by_name",
            description="Busca documentos en ClickUp relacionados con un proyecto.",
            args_schema=ListDocumentsByNameInput,
        )

    def get_tool_create_task(self) -> StructuredTool:
        return self._make_tool(
            func=self.create_task,
            name="create_clickup_task",
            description="Crea una nueva tarea en ClickUp usando lenguaje natural.",
            args_schema=CreateTaskInput,
        )

    def get_tool_create_list(self) -> StructuredTool:
        return self._make_tool(
            func=self.create_list,
            name="create_clickup_list",
            description="Crea una nueva lista en ClickUp.",
            args_schema=CreateListInput,
        )

    def get_tool_create_folder(self) -> StructuredTool:
        return self._make_tool(
            func=self.create_folder,
            name="create_clickup_folder",
            description="Crea una nueva carpeta en ClickUp.",
            args_schema=CreateFolderInput,
        )

    def get_tool_assign_task(self) -> StructuredTool:
        return self._make_tool(
            func=self.assign_task,
            name="assign_clickup_task",
            description="Asigna un miembro a una tarea en ClickUp.",
            args_schema=AssignTaskInput,
        )

    def get_tool_add_comment(self) -> StructuredTool:
        return self._make_tool(
            func=self.add_comment,
            name="add_comment_clickup",
            description="Agrega un comentario a una tarea de ClickUp.",
            args_schema=AddCommentInput,
        )

    def get_tool_update_due_date(self) -> StructuredTool:
        return self._make_tool(
            func=self.update_due_date,
            name="update_clickup_due_date",
            description="Actualiza la fecha de entrega de una tarea en ClickUp.",
            args_schema=UpdateDueDateInput,
        )

    def get_tool_search_tasks(self) -> StructuredTool:
        return self.get_tool_list_tasks()

    def get_all_tools(self) -> List[Any]:
        return [
            self.get_tool_list_spaces(),
            self.get_tool_list_folders(),
            self.get_tool_list_lists(),
            self.get_tool_list_tasks(),
            self.get_tool_get_task(),
            self.get_tool_list_members(),
            self.get_tool_get_document(),
            self.get_tool_list_documents_by_name(),
            self.get_tool_create_task(),
            self.get_tool_create_list(),
            self.get_tool_create_folder(),
            self.get_tool_assign_task(),
            self.get_tool_add_comment(),
            self.get_tool_update_due_date(),
        ]
