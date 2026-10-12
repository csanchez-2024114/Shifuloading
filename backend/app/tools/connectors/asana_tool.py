"""
Asana Tool Provider.
Refactorizado para soporte Multicuenta, Desencriptación Segura y Resiliencia.
Integrado con el motor de lectura centralizado de la plataforma con puente asíncrono robusto.
"""

import re
import logging
import requests
import asyncio
import concurrent.futures
from typing import Optional, List, Any, Callable, Dict
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
logger = logging.getLogger("tools.asana")
ASANA_API_BASE = "https://app.asana.com/api/1.0"
_REQUEST_TIMEOUT = 15


class ListProjectsInput(BaseModel):
    workspace_id: str = Field(
        default="",
        description="ID opcional del workspace. Si está vacío, busca en el contexto general.",
    )


class ProjectSummaryInput(BaseModel):
    identifier: str = Field(
        ...,
        alias="identifier",
        description="Nombre exacto o ID numérico del proyecto en Asana.",
    )


class CreateTaskInput(BaseModel):
    request: str = Field(
        ...,
        alias="request",
        description="Instrucción en lenguaje natural. Ej: 'Crea una tarea llamada X en el proyecto Y'.",
    )


class ListTasksInput(BaseModel):
    project_id: str = Field(
        ..., description="ID del proyecto de Asana del cual se listarán las tareas."
    )


class GetUserInfoInput(BaseModel):
    empty: str = Field(
        default="", alias="empty", description="Sin parámetros requeridos. Dejar vacío."
    )


class ListTeamsInput(BaseModel):
    workspace_id: str = Field(
        ..., description="ID del workspace de Asana del cual se listarán los equipos."
    )


class SearchTaskInput(BaseModel):
    task_name: str = Field(
        ...,
        alias="task_name",
        description="Nombre o parte del nombre de la tarea a buscar en Asana.",
    )


class CompletedTasksInput(BaseModel):
    identifier: str = Field(
        ...,
        alias="identifier",
        description="Nombre o ID del proyecto para listar sus tareas completadas.",
    )


class AsanaEventsInput(BaseModel):
    request: str = Field(
        ...,
        alias="request",
        description="Nombre del proyecto o tarea cuyos eventos recientes se quieren consultar.",
    )


class IncompleteTasksInput(BaseModel):
    identifier: str = Field(
        ...,
        alias="identifier",
        description="Nombre o ID del proyecto para listar tareas pendientes (no completadas).",
    )


class ProjectMembersInput(BaseModel):
    identifier: str = Field(
        ...,
        alias="identifier",
        description="Nombre o ID del proyecto para listar sus miembros.",
    )


class AssignTaskInput(BaseModel):
    request: str = Field(
        ...,
        alias="request",
        description="Instrucción para asignar tarea. Ej: 'Asigna la tarea X al usuario Y'.",
    )


class AddTagInput(BaseModel):
    request: str = Field(
        ...,
        alias="request",
        description="Instrucción para agregar etiqueta. Ej: 'Agrega la etiqueta X a la tarea Y'.",
    )


class TasksByTagInput(BaseModel):
    request: str = Field(
        ...,
        alias="request",
        description="Instrucción para listar tareas por etiqueta. Ej: 'Muéstrame las tareas con la etiqueta X'.",
    )


class CreateCommentInput(BaseModel):
    request: str = Field(
        ...,
        alias="request",
        description="Instrucción para crear comentario. Ej: 'Agrega el comentario Y a la tarea X'.",
    )


class UpdateStatusInput(BaseModel):
    request: str = Field(
        ...,
        alias="request",
        description="Instrucción para actualizar estado. Ej: 'Marca la tarea X como completada'.",
    )


class UpdateDescriptionInput(BaseModel):
    request: str = Field(
        ...,
        alias="request",
        description="Instrucción para actualizar descripción. Ej: 'Actualiza la descripción de la tarea X a Y'.",
    )


class DuplicateTaskInput(BaseModel):
    request: str = Field(
        ...,
        alias="request",
        description="Instrucción para duplicar tarea. Ej: 'Duplica la tarea X con el nombre Y'.",
    )


class ListTagsInput(BaseModel):
    empty: str = Field(
        default="", alias="empty", description="Sin parámetros requeridos. Dejar vacío."
    )


class ListUsersInput(BaseModel):
    empty: str = Field(
        default="", alias="empty", description="Sin parámetros requeridos. Dejar vacío."
    )


class AsanaToolProvider:

    def __init__(
        self,
        user_email: str | None = None,
        active_accounts: Optional[Dict[str, str]] = None,
    ):
        """
        Inicializa el proveedor con soporte para inyección dinámica de cuentas activas.
        """
        self.user_email = canonicalize_email(user_email) or (user_email or "")
        self.active_accounts = active_accounts or {}
        self.account_id = self.active_accounts.get("asana") or self.active_accounts.get(
            "Asana"
        )

    def _run_async_safely(self, coro_func: Callable) -> Any:
        """
        Puente arquitectónico ultra-seguro para ejecutar corrutinas dentro de hilos (workers) sincrónicos.
        Previene el colapso 'RuntimeError: This event loop is already running'.
        """
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
        Utiliza la colección 'user_connected_accounts' para obtener las credenciales de forma segura.
        """
        if not self.user_email:
            raise ToolException("Error de identidad: user_email ausente.")

        async def fetch_token():
            db_conn = get_async_database()
            vault = await get_user_vault_with_fallback(
                self.user_email, db_conn, account_id=self.account_id
            )
            asana_creds = vault.get("asana") or vault.get("Asana")
            if not asana_creds or not asana_creds.get("token"):
                raise ToolException(
                    "La cuenta de Asana no está conectada o el token es inválido. Por favor, conecta tu cuenta en la configuración."
                )
            return asana_creds["token"]

        return self._run_async_safely(fetch_token)

    def _get_headers(self) -> dict:
        """Helper para construir headers HTTP estandarizados de manera segura."""
        token = self._get_secure_token()
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def _make_tool(
        self, func: Callable, name: str, description: str, args_schema: type[BaseModel]
    ) -> StructuredTool:
        """Inyecta handle_tool_error=True para garantizar resiliencia en el Grafo ante caídas de la API externa."""
        return StructuredTool.from_function(
            func=func,
            name=name,
            description=description,
            args_schema=args_schema,
            handle_tool_error=True,
        )

    def _resolver_proyecto_id(self, identifier: str, headers: dict) -> Optional[str]:
        if identifier.isdigit():
            return identifier
        try:
            resp = requests.get(
                f"{ASANA_API_BASE}/projects", headers=headers, timeout=_REQUEST_TIMEOUT
            )
            resp.raise_for_status()
            proj_list = resp.json().get("data", [])
            target = next(
                (p for p in proj_list if identifier.lower() in p["name"].lower()), None
            )
            return target["gid"] if target else None
        except requests.exceptions.RequestException as e:
            logger.error(f"[Asana API] Error resolviendo ID de proyecto: {e}")
            return None

    def _resolver_tarea_id(self, task_name: str, headers: dict) -> Optional[str]:
        try:
            resp = requests.get(
                f"{ASANA_API_BASE}/projects", headers=headers, timeout=_REQUEST_TIMEOUT
            )
            resp.raise_for_status()
            proj_list = resp.json().get("data", [])
            for proj in proj_list:
                t_resp = requests.get(
                    f"{ASANA_API_BASE}/projects/{proj['gid']}/tasks?opt_fields=name,gid",
                    headers=headers,
                    timeout=_REQUEST_TIMEOUT,
                )
                if t_resp.status_code == 200:
                    tareas = t_resp.json().get("data", [])
                    for tarea in tareas:
                        if task_name.lower() in tarea["name"].lower():
                            return tarea["gid"]
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"[Asana API] Error resolviendo ID de tarea: {e}")
            return None

    def _get_workspace_id(self, headers: dict) -> Optional[str]:
        try:
            resp = requests.get(
                f"{ASANA_API_BASE}/users/me?opt_fields=workspaces",
                headers=headers,
                timeout=_REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            workspaces = resp.json().get("data", {}).get("workspaces", [])
            return workspaces[0]["gid"] if workspaces else None
        except requests.exceptions.RequestException as e:
            logger.error(f"[Asana API] Error obteniendo Workspace ID: {e}")
            return None

    def list_projects(self, workspace_id: str = "") -> str:
        try:
            headers = self._get_headers()
            url = f"{ASANA_API_BASE}/projects?opt_fields=name,notes,archived,created_at,owner.name"
            response = requests.get(url, headers=headers, timeout=_REQUEST_TIMEOUT)
            response.raise_for_status()
            projects = response.json().get("data", [])
            if not projects:
                return "📭 No hay proyectos en esta cuenta de Asana."
            result = "📋 **Proyectos en Asana:**\n\n"
            for proj in projects:
                status = "✅ Activo" if not proj.get("archived") else "⚪ Archivado"
                notes = proj.get("notes", "Sin descripción")
                short_notes = f"{notes[:100]}..." if len(notes) > 100 else notes
                result += f"📁 **{proj.get('name')}**\n👤 Dueño: {proj.get('owner', {}).get('name', 'N/A')}\n📌 Estado: {status} | ID: {proj.get('gid')}\n📝 {short_notes}\n{'─' * 30}\n"
            return result.strip()
        except ToolException:
            raise
        except Exception as e:
            logger.error(
                f"[Asana API] Error interno en list_projects: {e}", exc_info=True
            )
            raise ToolException(f"Error al listar proyectos: {str(e)}")

    def list_tasks(self, project_id: str) -> str:
        try:
            headers = self._get_headers()
            url = f"{ASANA_API_BASE}/projects/{project_id}/tasks?opt_fields=name,completed,due_on,assignee.name"
            response = requests.get(url, headers=headers, timeout=_REQUEST_TIMEOUT)
            response.raise_for_status()
            tareas = response.json().get("data", [])
            if not tareas:
                return f"📭 El proyecto '{project_id}' no tiene tareas."
            result = f"📋 **Tareas del proyecto {project_id}:**\n\n"
            for t in tareas:
                status = "✅" if t.get("completed") else "🔲"
                asignado = (
                    t.get("assignee", {}).get("name", "Sin asignar")
                    if t.get("assignee")
                    else "Sin asignar"
                )
                result += f"{status} **{t['name']}** | Vence: {t.get('due_on', 'N/A')} | Asignado: {asignado}\n"
            return result.strip()
        except ToolException:
            raise
        except Exception as e:
            logger.error(f"[Asana API] Error en list_tasks: {e}")
            raise ToolException(f"Error al listar tareas: {str(e)}")

    def get_user_info(self, empty: str = "") -> str:
        try:
            headers = self._get_headers()
            response = requests.get(
                f"{ASANA_API_BASE}/users/me?opt_fields=name,email,workspaces",
                headers=headers,
                timeout=_REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json().get("data", {})
            workspaces = ", ".join([w["name"] for w in data.get("workspaces", [])])
            return f"👤 **Información del usuario:**\n- Nombre: {data.get('name', 'N/A')}\n- Correo: {data.get('email', 'N/A')}\n- Workspaces: {workspaces or 'N/A'}"
        except ToolException:
            raise
        except Exception as e:
            logger.error(f"[Asana API] Error en get_user_info: {e}")
            raise ToolException(f"Error al obtener info de usuario: {str(e)}")

    def list_teams(self, workspace_id: str) -> str:
        try:
            headers = self._get_headers()
            response = requests.get(
                f"{ASANA_API_BASE}/workspaces/{workspace_id}/teams?opt_fields=name,description",
                headers=headers,
                timeout=_REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            teams = response.json().get("data", [])
            if not teams:
                return "📭 No se encontraron equipos en este workspace."
            result = "👥 **Equipos en Asana:**\n\n"
            for team in teams:
                result += f"- **{team['name']}** (ID: {team['gid']})\n"
            return result.strip()
        except ToolException:
            raise
        except Exception as e:
            logger.error(f"[Asana API] Error en list_teams: {e}")
            raise ToolException(f"Error al listar equipos: {str(e)}")

    def get_task_detail_by_name(self, task_name: str) -> str:
        try:
            headers = self._get_headers()
            task_id = self._resolver_tarea_id(task_name, headers)
            if not task_id:
                raise ToolException(
                    f"No se encontró ninguna tarea con el nombre '{task_name}'."
                )
            response = requests.get(
                f"{ASANA_API_BASE}/tasks/{task_id}?opt_fields=name,notes,completed,due_on,assignee.name,tags.name,memberships.project.name",
                headers=headers,
                timeout=_REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            t = response.json().get("data", {})
            assignee = (
                t.get("assignee", {}).get("name", "Sin asignar")
                if t.get("assignee")
                else "Sin asignar"
            )
            tags = (
                ", ".join([tag["name"] for tag in t.get("tags", [])]) or "Sin etiquetas"
            )
            project = (
                t.get("memberships", [{}])[0].get("project", {}).get("name", "N/A")
                if t.get("memberships")
                else "N/A"
            )
            return f"📌 **{t.get('name')}**\n- Estado: {('✅ Completada' if t.get('completed') else '🔲 Pendiente')}\n- Asignado a: {assignee}\n- Vence: {t.get('due_on', 'N/A')}\n- Proyecto: {project}\n- Etiquetas: {tags}\n- Descripción: {t.get('notes', 'Sin descripción')[:200]}"
        except ToolException:
            raise
        except Exception as e:
            logger.error(f"[Asana API] Error en get_task_detail_by_name: {e}")
            raise ToolException(f"Error al obtener detalle: {str(e)}")

    def list_task_comments_by_name(self, task_name: str) -> str:
        try:
            headers = self._get_headers()
            task_id = self._resolver_tarea_id(task_name, headers)
            if not task_id:
                raise ToolException(
                    f"No se encontró ninguna tarea con el nombre '{task_name}'."
                )
            response = requests.get(
                f"{ASANA_API_BASE}/tasks/{task_id}/stories?opt_fields=text,created_at,created_by.name,type",
                headers=headers,
                timeout=_REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            stories = [
                s for s in response.json().get("data", []) if s.get("type") == "comment"
            ]
            if not stories:
                return f"💬 La tarea '{task_name}' no tiene comentarios."
            result = f"💬 **Comentarios de '{task_name}':**\n\n"
            for s in stories:
                autor = s.get("created_by", {}).get("name", "Desconocido")
                result += f"👤 **{autor}** ({s.get('created_at', '')[:10]}):\n{s.get('text', '')}\n---\n"
            return result.strip()
        except ToolException:
            raise
        except Exception as e:
            logger.error(f"[Asana API] Error en list_task_comments_by_name: {e}")
            raise ToolException(f"Error al listar comentarios: {str(e)}")

    def get_project_summary(self, identifier: str) -> str:
        try:
            headers = self._get_headers()
            project_id = self._resolver_proyecto_id(identifier, headers)
            if not project_id:
                raise ToolException(f"Proyecto '{identifier}' no encontrado.")
            tareas_resp = requests.get(
                f"{ASANA_API_BASE}/projects/{project_id}/tasks?opt_fields=completed,name",
                headers=headers,
                timeout=_REQUEST_TIMEOUT,
            )
            tareas_resp.raise_for_status()
            tareas = tareas_resp.json().get("data", [])
            if not tareas:
                return f"📭 El proyecto '{identifier}' no tiene tareas asignadas."
            total = len(tareas)
            completas = sum((1 for t in tareas if t.get("completed")))
            progreso = round(completas / total * 100, 1) if total > 0 else 0
            return f"📊 **Resumen: {identifier}**\n✅ Tareas Completas: {completas} / {total}\n📈 Progreso Real: {progreso}%\n{'─' * 20}"
        except ToolException:
            raise
        except Exception as e:
            logger.error(f"[Asana API] Error obteniendo resumen: {e}")
            raise ToolException(f"Error al obtener resumen: {str(e)}")

    def list_users(self, empty: str = "") -> str:
        try:
            headers = self._get_headers()
            ws_id = self._get_workspace_id(headers)
            if not ws_id:
                raise ToolException("No se encontraron workspaces activos.")
            response = requests.get(
                f"{ASANA_API_BASE}/workspaces/{ws_id}/users?opt_fields=name,email",
                headers=headers,
                timeout=_REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            users = response.json().get("data", [])
            if not users:
                return "📭 No se encontraron usuarios."
            result = "👥 **Usuarios del workspace:**\n\n"
            for u in users:
                result += f"- **{u.get('name', 'N/A')}** | {u.get('email', 'N/A')} (ID: {u.get('gid')})\n"
            return result.strip()
        except ToolException:
            raise
        except Exception as e:
            logger.error(f"[Asana API] Error en list_users: {e}")
            raise ToolException(f"Error al listar usuarios: {str(e)}")

    def list_tags(self, empty: str = "") -> str:
        try:
            headers = self._get_headers()
            ws_id = self._get_workspace_id(headers)
            if not ws_id:
                raise ToolException("No se encontraron workspaces activos.")
            response = requests.get(
                f"{ASANA_API_BASE}/workspaces/{ws_id}/tags?opt_fields=name,color,notes",
                headers=headers,
                timeout=_REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            tags = response.json().get("data", [])
            if not tags:
                return "📭 No hay etiquetas en este workspace."
            result = "🏷️ **Etiquetas en Asana:**\n\n"
            for tag in tags:
                result += f"- **{tag.get('name')}** | Color: {tag.get('color', 'N/A')} | ID: {tag.get('gid')}\n"
            return result.strip()
        except ToolException:
            raise
        except Exception as e:
            logger.error(f"[Asana API] Error en list_tags: {e}")
            raise ToolException(f"Error al listar etiquetas: {str(e)}")

    def list_completed_tasks(self, identifier: str) -> str:
        try:
            headers = self._get_headers()
            project_id = self._resolver_proyecto_id(identifier, headers)
            if not project_id:
                raise ToolException(f"Proyecto '{identifier}' no encontrado.")
            response = requests.get(
                f"{ASANA_API_BASE}/projects/{project_id}/tasks?opt_fields=name,completed,due_on,assignee.name",
                headers=headers,
                timeout=_REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            tareas = [t for t in response.json().get("data", []) if t.get("completed")]
            if not tareas:
                return f"📭 No hay tareas completadas en '{identifier}'."
            result = f"✅ **Tareas completadas en '{identifier}':**\n\n"
            for t in tareas:
                result += f"✅ {t['name']} | Vence: {t.get('due_on', 'N/A')}\n"
            return result.strip()
        except ToolException:
            raise
        except Exception as e:
            logger.error(f"[Asana API] Error en list_completed_tasks: {e}")
            raise ToolException(f"Error al buscar tareas completadas: {str(e)}")

    def list_events(self, request: str) -> str:
        try:
            headers = self._get_headers()
            project_id = self._resolver_proyecto_id(request, headers)
            if not project_id:
                task_id = self._resolver_tarea_id(request, headers)
                if not task_id:
                    raise ToolException(
                        f"No se encontró un proyecto o tarea con el nombre '{request}'."
                    )
                resource_id = task_id
            else:
                resource_id = project_id
            response = requests.get(
                f"{ASANA_API_BASE}/events?resource={resource_id}",
                headers=headers,
                timeout=_REQUEST_TIMEOUT,
            )
            if response.status_code == 412:
                return f"ℹ️ El recurso '{request}' existe en Asana. Para recibir eventos en tiempo real configura un webhook de Asana. El endpoint de eventos requiere un sync token inicial."
            response.raise_for_status()
            events = response.json().get("data", [])
            if not events:
                return f"📭 No se encontraron eventos recientes para '{request}'."
            result = f"📅 **Eventos de '{request}':**\n\n"
            for ev in events[:20]:
                result += f"- Tipo: {ev.get('type')} | Acción: {ev.get('action')} | Recurso: {ev.get('resource', {}).get('name', 'N/A')}\n"
            return result.strip()
        except ToolException:
            raise
        except Exception as e:
            logger.error(f"[Asana API] Error en list_events: {e}")
            raise ToolException(f"Error al listar eventos: {str(e)}")

    def list_incomplete_tasks(self, identifier: str) -> str:
        try:
            headers = self._get_headers()
            project_id = self._resolver_proyecto_id(identifier, headers)
            if not project_id:
                raise ToolException(f"Proyecto '{identifier}' no encontrado.")
            response = requests.get(
                f"{ASANA_API_BASE}/projects/{project_id}/tasks?opt_fields=name,completed,due_on,assignee.name",
                headers=headers,
                timeout=_REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            tareas = [
                t for t in response.json().get("data", []) if not t.get("completed")
            ]
            if not tareas:
                return f"✅ ¡Todas las tareas de '{identifier}' están completadas!"
            result = f"🔲 **Tareas pendientes en '{identifier}':**\n\n"
            for t in tareas:
                asignado = (
                    t.get("assignee", {}).get("name", "Sin asignar")
                    if t.get("assignee")
                    else "Sin asignar"
                )
                result += (
                    f"🔲 {t['name']} | Vence: {t.get('due_on', 'N/A')} | {asignado}\n"
                )
            return result.strip()
        except ToolException:
            raise
        except Exception as e:
            logger.error(f"[Asana API] Error en list_incomplete_tasks: {e}")
            raise ToolException(f"Error al buscar tareas pendientes: {str(e)}")

    def list_project_members(self, identifier: str) -> str:
        try:
            headers = self._get_headers()
            project_id = self._resolver_proyecto_id(identifier, headers)
            if not project_id:
                raise ToolException(f"Proyecto '{identifier}' no encontrado.")
            response = requests.get(
                f"{ASANA_API_BASE}/projects/{project_id}/project_memberships?opt_fields=user.name,user.email,access_level",
                headers=headers,
                timeout=_REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            members = response.json().get("data", [])
            if not members:
                return f"📭 No hay miembros en el proyecto '{identifier}'."
            result = f"👥 **Miembros del proyecto '{identifier}':**\n\n"
            for m in members:
                user = m.get("user", {})
                result += f"- **{user.get('name', 'N/A')}** | {user.get('email', 'N/A')} | Acceso: {m.get('access_level', 'N/A')}\n"
            return result.strip()
        except ToolException:
            raise
        except Exception as e:
            logger.error(f"[Asana API] Error en list_project_members: {e}")
            raise ToolException(f"Error al listar miembros: {str(e)}")

    def list_tasks_by_tag(self, request: str) -> str:
        try:
            headers = self._get_headers()
            ws_id = self._get_workspace_id(headers)
            if not ws_id:
                raise ToolException("No se encontró workspace.")
            tags_resp = requests.get(
                f"{ASANA_API_BASE}/workspaces/{ws_id}/tags?opt_fields=name",
                headers=headers,
                timeout=_REQUEST_TIMEOUT,
            )
            tags_resp.raise_for_status()
            tags = tags_resp.json().get("data", [])
            tag = next((t for t in tags if request.lower() in t["name"].lower()), None)
            if not tag:
                raise ToolException(f"No se encontró la etiqueta '{request}'.")
            tareas_resp = requests.get(
                f"{ASANA_API_BASE}/tags/{tag['gid']}/tasks?opt_fields=name,completed,assignee.name",
                headers=headers,
                timeout=_REQUEST_TIMEOUT,
            )
            tareas_resp.raise_for_status()
            tareas = tareas_resp.json().get("data", [])
            if not tareas:
                return f"📭 No hay tareas con la etiqueta '{tag['name']}'."
            result = f"🏷️ **Tareas con etiqueta '{tag['name']}':**\n\n"
            for t in tareas:
                status = "✅" if t.get("completed") else "🔲"
                result += f"{status} {t['name']}\n"
            return result.strip()
        except ToolException:
            raise
        except Exception as e:
            logger.error(f"[Asana API] Error en list_tasks_by_tag: {e}")
            raise ToolException(f"Error al listar tareas por etiqueta: {str(e)}")

    def create_task_asana(self, request: str) -> str:
        try:
            headers = self._get_headers()
            nombre_match = re.search("llamada\\s+(.+?)(?:\\s+en|$)", request, re.I)
            task_name = (
                nombre_match.group(1).strip() if nombre_match else "Nueva Tarea Shifu"
            )
            ws_id = self._get_workspace_id(headers)
            if not ws_id:
                raise ToolException("No tienes workspaces configurados en Asana.")
            payload = {"data": {"name": task_name, "workspace": ws_id}}
            resp = requests.post(
                f"{ASANA_API_BASE}/tasks",
                headers=headers,
                json=payload,
                timeout=_REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            return f"✅ Tarea '{task_name}' creada con éxito."
        except ToolException:
            raise
        except requests.exceptions.RequestException as e:
            logger.warning(
                f"[Asana API] Error al crear tarea: {(e.response.text if getattr(e, 'response', None) else str(e))}"
            )
            raise ToolException(f"Error de Asana al crear tarea: {str(e)}")
        except Exception as e:
            logger.error(f"[Asana API] Error interno creando tarea: {e}")
            raise ToolException(f"Error interno al crear tarea: {str(e)}")

    def assign_task_to_user_by_name(self, request: str) -> str:
        try:
            headers = self._get_headers()
            tarea_match = re.search(
                "tarea\\s+['\\\"]?(.+?)['\\\"]?\\s+a(?:l usuario)?\\s+(.+?)$",
                request,
                re.I,
            )
            if not tarea_match:
                raise ToolException(
                    "Formato no reconocido. Ejemplo correcto: 'Asigna la tarea X al usuario Y'."
                )
            task_name = tarea_match.group(1).strip()
            nombre_usuario = tarea_match.group(2).strip()
            task_id = self._resolver_tarea_id(task_name, headers)
            if not task_id:
                raise ToolException(f"No se encontró la tarea '{task_name}'.")
            ws_id = self._get_workspace_id(headers)
            users_resp = requests.get(
                f"{ASANA_API_BASE}/workspaces/{ws_id}/users?opt_fields=name,gid",
                headers=headers,
                timeout=_REQUEST_TIMEOUT,
            )
            users_resp.raise_for_status()
            users = users_resp.json().get("data", [])
            user = next(
                (u for u in users if nombre_usuario.lower() in u["name"].lower()), None
            )
            if not user:
                raise ToolException(
                    f"No se encontró el usuario '{nombre_usuario}' en tu workspace."
                )
            resp = requests.put(
                f"{ASANA_API_BASE}/tasks/{task_id}",
                headers=headers,
                json={"data": {"assignee": user["gid"]}},
                timeout=_REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            return f"✅ Tarea '{task_name}' asignada a '{user['name']}' con éxito."
        except ToolException:
            raise
        except requests.exceptions.RequestException as e:
            raise ToolException(f"Error de Asana al asignar tarea: {str(e)}")
        except Exception as e:
            logger.error(f"[Asana API] Error en assign_task_to_user_by_name: {e}")
            raise ToolException(f"Error interno al asignar tarea: {str(e)}")

    def add_tag_to_task_by_name(self, request: str) -> str:
        try:
            headers = self._get_headers()
            match = re.search(
                "etiqueta\\s+['\\\"]?(.+?)['\\\"]?\\s+a\\s+(?:la tarea\\s+)?['\\\"]?(.+?)['\\\"]?$",
                request,
                re.I,
            )
            if not match:
                raise ToolException(
                    "Formato no reconocido. Ejemplo correcto: 'Agrega la etiqueta X a la tarea Y'."
                )
            nombre_etiqueta = match.group(1).strip()
            task_name = match.group(2).strip()
            task_id = self._resolver_tarea_id(task_name, headers)
            if not task_id:
                raise ToolException(f"No se encontró la tarea '{task_name}'.")
            ws_id = self._get_workspace_id(headers)
            tags_resp = requests.get(
                f"{ASANA_API_BASE}/workspaces/{ws_id}/tags?opt_fields=name",
                headers=headers,
                timeout=_REQUEST_TIMEOUT,
            )
            tags_resp.raise_for_status()
            tags = tags_resp.json().get("data", [])
            tag = next(
                (t for t in tags if nombre_etiqueta.lower() in t["name"].lower()), None
            )
            if not tag:
                new_tag_resp = requests.post(
                    f"{ASANA_API_BASE}/tags",
                    headers=headers,
                    json={"data": {"name": nombre_etiqueta, "workspace": ws_id}},
                    timeout=_REQUEST_TIMEOUT,
                )
                new_tag_resp.raise_for_status()
                tag_id = new_tag_resp.json().get("data", {}).get("gid")
            else:
                tag_id = tag["gid"]
            resp = requests.post(
                f"{ASANA_API_BASE}/tasks/{task_id}/addTag",
                headers=headers,
                json={"data": {"tag": tag_id}},
                timeout=_REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            return f"✅ Etiqueta '{nombre_etiqueta}' agregada a la tarea '{task_name}'."
        except ToolException:
            raise
        except requests.exceptions.RequestException as e:
            raise ToolException(f"Error de Asana al agregar etiqueta: {str(e)}")
        except Exception as e:
            logger.error(f"[Asana API] Error en add_tag_to_task_by_name: {e}")
            raise ToolException(f"Error interno al agregar etiqueta: {str(e)}")

    def create_task_comment(self, request: str) -> str:
        try:
            headers = self._get_headers()
            match = re.search(
                "(?:tarea|a)\\s+['\\\"]?(.+?)['\\\"]?\\s+(?:que diga|el comentario|con el texto|:)\\s+['\\\"]?(.+?)['\\\"]?$",
                request,
                re.I,
            )
            if not match:
                raise ToolException(
                    "Formato no reconocido. Ejemplo correcto: 'Agrega el comentario Y a la tarea X'."
                )
            task_name = match.group(1).strip()
            comentario = match.group(2).strip()
            task_id = self._resolver_tarea_id(task_name, headers)
            if not task_id:
                raise ToolException(f"No se encontró la tarea '{task_name}'.")
            resp = requests.post(
                f"{ASANA_API_BASE}/tasks/{task_id}/stories",
                headers=headers,
                json={"data": {"text": comentario}},
                timeout=_REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            return f"✅ Comentario agregado a la tarea '{task_name}'."
        except ToolException:
            raise
        except requests.exceptions.RequestException as e:
            raise ToolException(f"Error de Asana al agregar comentario: {str(e)}")
        except Exception as e:
            logger.error(f"[Asana API] Error en create_task_comment: {e}")
            raise ToolException(f"Error interno al crear comentario: {str(e)}")

    def update_task_status_by_name(self, request: str) -> str:
        try:
            headers = self._get_headers()
            nombre_match = re.search(
                "tarea\\s+['\\\"]?(.+?)['\\\"]?(?:\\s+como|\\s+a\\s+|$)", request, re.I
            )
            if not nombre_match:
                raise ToolException(
                    "No se identificó el nombre de la tarea en la request."
                )
            task_name = nombre_match.group(1).strip()
            completada = any(
                (
                    w in request.lower()
                    for w in [
                        "completada",
                        "completado",
                        "hecha",
                        "hecho",
                        "finalizada",
                        "terminada",
                    ]
                )
            )
            task_id = self._resolver_tarea_id(task_name, headers)
            if not task_id:
                raise ToolException(f"No se encontró la tarea '{task_name}'.")
            resp = requests.put(
                f"{ASANA_API_BASE}/tasks/{task_id}",
                headers=headers,
                json={"data": {"completed": completada}},
                timeout=_REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            estado_str = "completada ✅" if completada else "pendiente 🔲"
            return f"✅ Tarea '{task_name}' marcada como {estado_str}."
        except ToolException:
            raise
        except requests.exceptions.RequestException as e:
            raise ToolException(f"Error de Asana al actualizar estado: {str(e)}")
        except Exception as e:
            logger.error(f"[Asana API] Error en update_task_status_by_name: {e}")
            raise ToolException(f"Error interno al actualizar estado: {str(e)}")

    def update_task_description_by_name(self, request: str) -> str:
        try:
            headers = self._get_headers()
            match = re.search(
                "tarea\\s+['\\\"]?(.+?)['\\\"]?\\s+(?:a|con|:)\\s+['\\\"]?(.+)['\\\"]?$",
                request,
                re.I,
            )
            if not match:
                raise ToolException(
                    "Formato no reconocido. Ejemplo correcto: 'Actualiza la descripción de la tarea X a Y'."
                )
            task_name = match.group(1).strip()
            nueva_desc = match.group(2).strip()
            task_id = self._resolver_tarea_id(task_name, headers)
            if not task_id:
                raise ToolException(f"No se encontró la tarea '{task_name}'.")
            resp = requests.put(
                f"{ASANA_API_BASE}/tasks/{task_id}",
                headers=headers,
                json={"data": {"notes": nueva_desc}},
                timeout=_REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            return f"✅ Descripción de la tarea '{task_name}' actualizada con éxito."
        except ToolException:
            raise
        except requests.exceptions.RequestException as e:
            raise ToolException(f"Error de Asana al actualizar descripción: {str(e)}")
        except Exception as e:
            logger.error(f"[Asana API] Error en update_task_description_by_name: {e}")
            raise ToolException(f"Error interno al actualizar descripción: {str(e)}")

    def duplicate_task_by_name(self, request: str) -> str:
        try:
            headers = self._get_headers()
            match = re.search(
                "tarea\\s+['\\\"]?(.+?)['\\\"]?\\s+(?:como|con el nombre)\\s+['\\\"]?(.+?)['\\\"]?$",
                request,
                re.I,
            )
            if not match:
                raise ToolException(
                    "Formato no reconocido. Ejemplo correcto: 'Duplica la tarea X como Y'."
                )
            nombre_original = match.group(1).strip()
            nombre_copia = match.group(2).strip()
            task_id = self._resolver_tarea_id(nombre_original, headers)
            if not task_id:
                raise ToolException(f"No se encontró la tarea '{nombre_original}'.")
            resp = requests.post(
                f"{ASANA_API_BASE}/tasks/{task_id}/duplicate",
                headers=headers,
                json={
                    "data": {
                        "name": nombre_copia,
                        "include": [
                            "notes",
                            "assignee",
                            "subtasks",
                            "attachments",
                            "tags",
                            "dates",
                        ],
                    }
                },
                timeout=_REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            return f"✅ Tarea '{nombre_original}' duplicada como '{nombre_copia}'."
        except ToolException:
            raise
        except requests.exceptions.RequestException as e:
            raise ToolException(f"Error de Asana al duplicar tarea: {str(e)}")
        except Exception as e:
            logger.error(f"[Asana API] Error en duplicate_task_by_name: {e}")
            raise ToolException(f"Error interno al duplicar tarea: {str(e)}")

    def get_tool_list_projects(self) -> StructuredTool:
        return self._make_tool(
            func=self.list_projects,
            name="list_asana_projects",
            description="Útil para obtener la lista completa de proyectos en Asana.",
            args_schema=ListProjectsInput,
        )

    def get_tool_list_tasks(self) -> StructuredTool:
        return self._make_tool(
            func=self.list_tasks,
            name="list_asana_tasks",
            description="Útil para listar todas las tareas de un proyecto específico.",
            args_schema=ListTasksInput,
        )

    def get_tool_get_user_info(self) -> StructuredTool:
        return self._make_tool(
            func=self.get_user_info,
            name="get_asana_user_info",
            description="Obtiene la información del usuario autenticado.",
            args_schema=GetUserInfoInput,
        )

    def get_tool_list_teams(self) -> StructuredTool:
        return self._make_tool(
            func=self.list_teams,
            name="list_asana_teams",
            description="Lista los equipos dentro de un workspace.",
            args_schema=ListTeamsInput,
        )

    def get_tool_get_task_detail_by_name(self) -> StructuredTool:
        return self._make_tool(
            func=self.get_task_detail_by_name,
            name="get_asana_task_details_by_name",
            description="Busca una tarea por nombre y muestra sus detalles.",
            args_schema=SearchTaskInput,
        )

    def get_tool_list_task_comments_by_name(self) -> StructuredTool:
        return self._make_tool(
            func=self.list_task_comments_by_name,
            name="list_asana_task_comments_by_name",
            description="Lista todos los comentarios de una tarea.",
            args_schema=SearchTaskInput,
        )

    def get_tool_get_project_summary(self) -> StructuredTool:
        return self._make_tool(
            func=self.get_project_summary,
            name="get_asana_project_summary",
            description="Muestra métricas de avance de un proyecto.",
            args_schema=ProjectSummaryInput,
        )

    def get_tool_list_users(self) -> StructuredTool:
        return self._make_tool(
            func=self.list_users,
            name="list_asana_users",
            description="Lista todos los miembros del workspace.",
            args_schema=ListUsersInput,
        )

    def get_tool_list_tags(self) -> StructuredTool:
        return self._make_tool(
            func=self.list_tags,
            name="list_asana_tags",
            description="Lista todas las etiquetas disponibles en el workspace.",
            args_schema=ListTagsInput,
        )

    def get_tool_list_completed_tasks(self) -> StructuredTool:
        return self._make_tool(
            func=self.list_completed_tasks,
            name="list_asana_completed_tasks",
            description="Lista las tareas completadas de un proyecto.",
            args_schema=CompletedTasksInput,
        )

    def get_tool_list_events(self) -> StructuredTool:
        return self._make_tool(
            func=self.list_events,
            name="list_asana_events",
            description="Muestra eventos recientes de un proyecto o tarea.",
            args_schema=AsanaEventsInput,
        )

    def get_tool_list_incomplete_tasks(self) -> StructuredTool:
        return self._make_tool(
            func=self.list_incomplete_tasks,
            name="list_asana_pending_tasks",
            description="Lista tareas pendientes de un proyecto.",
            args_schema=IncompleteTasksInput,
        )

    def get_tool_list_project_members(self) -> StructuredTool:
        return self._make_tool(
            func=self.list_project_members,
            name="list_asana_project_members",
            description="Muestra miembros de un proyecto.",
            args_schema=ProjectMembersInput,
        )

    def get_tool_list_tasks_by_tag(self) -> StructuredTool:
        return self._make_tool(
            func=self.list_tasks_by_tag,
            name="list_asana_tasks_by_tag",
            description="Lista tareas filtradas por etiqueta.",
            args_schema=TasksByTagInput,
        )

    def get_tool_create_task_asana(self) -> StructuredTool:
        return self._make_tool(
            func=self.create_task_asana,
            name="create_asana_task",
            description="Crea una tarea usando lenguaje natural.",
            args_schema=CreateTaskInput,
        )

    def get_tool_assign_task_to_user_by_name(self) -> StructuredTool:
        return self._make_tool(
            func=self.assign_task_to_user_by_name,
            name="assign_asana_task_to_user_by_name",
            description="Asigna una tarea a un usuario por nombre.",
            args_schema=AssignTaskInput,
        )

    def get_tool_add_tag_to_task_by_name(self) -> StructuredTool:
        return self._make_tool(
            func=self.add_tag_to_task_by_name,
            name="add_tag_to_asana_task_by_name",
            description="Agrega una etiqueta a una tarea.",
            args_schema=AddTagInput,
        )

    def get_tool_create_task_comment(self) -> StructuredTool:
        return self._make_tool(
            func=self.create_task_comment,
            name="create_asana_task_comment",
            description="Agrega un comentario a una tarea.",
            args_schema=CreateCommentInput,
        )

    def get_tool_update_task_status_by_name(self) -> StructuredTool:
        return self._make_tool(
            func=self.update_task_status_by_name,
            name="update_asana_task_status_by_name",
            description="Marca una tarea como completada o pendiente.",
            args_schema=UpdateStatusInput,
        )

    def get_tool_update_task_description_by_name(self) -> StructuredTool:
        return self._make_tool(
            func=self.update_task_description_by_name,
            name="update_asana_task_description_by_name",
            description="Actualiza la descripción de una tarea.",
            args_schema=UpdateDescriptionInput,
        )

    def get_tool_duplicate_task_by_name(self) -> StructuredTool:
        return self._make_tool(
            func=self.duplicate_task_by_name,
            name="duplicate_asana_task_by_name",
            description="Duplica una tarea existente.",
            args_schema=DuplicateTaskInput,
        )

    def get_all_tools(self) -> List[Any]:
        return [
            self.get_tool_list_projects(),
            self.get_tool_list_tasks(),
            self.get_tool_get_user_info(),
            self.get_tool_list_teams(),
            self.get_tool_get_task_detail_by_name(),
            self.get_tool_list_task_comments_by_name(),
            self.get_tool_get_project_summary(),
            self.get_tool_list_users(),
            self.get_tool_list_tags(),
            self.get_tool_list_completed_tasks(),
            self.get_tool_list_events(),
            self.get_tool_list_incomplete_tasks(),
            self.get_tool_list_project_members(),
            self.get_tool_list_tasks_by_tag(),
            self.get_tool_create_task_asana(),
            self.get_tool_assign_task_to_user_by_name(),
            self.get_tool_add_tag_to_task_by_name(),
            self.get_tool_create_task_comment(),
            self.get_tool_update_task_status_by_name(),
            self.get_tool_update_task_description_by_name(),
            self.get_tool_duplicate_task_by_name(),
        ]


if __name__ == "__main__":
    logger.info("Modulo AsanaToolProvider inicializado correctamente.")
