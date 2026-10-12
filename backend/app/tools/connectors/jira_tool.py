"""
JIRA Tools para LangGraph

ARQUITECTURA:
- User_id se obtiene automáticamente desde Flask/FastAPI session (ContextVars)
- Lazy imports para evitar circular dependencies
- Caché de servicio por request para performance
- Refactorización:
  * Erradicación de fallos silenciosos: _format_error_response ahora lanza ToolException.
  * Respuestas exitosas serializadas en JSON string.
  * Inyección de handle_tool_error=True vía _make_jira_tool.
"""
import json
import logging
import os
from typing import Dict, Any, Optional, List, Callable
from contextvars import ContextVar
from langchain_core.tools import StructuredTool, ToolException
from pydantic import BaseModel, Field, field_validator
from config import Config
from app.core.mongo import get_sync_database
logger = logging.getLogger(__name__)
_jira_user_id_ctx: ContextVar[Optional[str]] = ContextVar('jira_user_id', default=None)
_jira_service_ctx: ContextVar[Any] = ContextVar('jira_service', default=None)

def set_jira_tool_context(user_id: str) -> None:
    """Inyecta contexto de usuario para ejecución de tools en FastAPI."""
    _jira_user_id_ctx.set(str(user_id))
    _jira_service_ctx.set(None)

def clear_jira_tool_context() -> None:
    """Limpia el contexto de ejecución actual."""
    _jira_user_id_ctx.set(None)
    _jira_service_ctx.set(None)

def _get_sync_db():
    return get_sync_database()

class JiraToolError(Exception):
    """Excepción base para errores en JIRA tools"""

    def __init__(self, message: str, error_code: str='jira_tool_error'):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)

class JiraAuthenticationError(JiraToolError):
    """Error cuando el usuario no está autenticado"""

    def __init__(self):
        super().__init__('No estás autenticado. Inicia sesión primero.', error_code='authentication_required')

class JiraNotConnectedError(JiraToolError):
    """Error cuando JIRA no está conectado"""

    def __init__(self):
        super().__init__('JIRA no está conectado. Ve a Configuración → Integraciones → JIRA para conectar tu cuenta.', error_code='jira_not_connected')

class JiraContextError(JiraToolError):
    """Error cuando no hay contexto web válido"""

    def __init__(self):
        super().__init__('Esta operación requiere un contexto web activo.', error_code='invalid_context')

def _get_current_user_id() -> str:
    """
    Obtiene el user_id del contexto actual inyectado por FastAPI.
    """
    user_id = _jira_user_id_ctx.get()
    if not user_id:
        raise JiraAuthenticationError()
    return user_id

def _get_jira_service():
    """
    Obtiene o crea una instancia de JiraService para el usuario actual.
    Implementa caché por request usando contextvars.
    """
    user_id = _get_current_user_id()
    cached_service = _jira_service_ctx.get()
    if cached_service is not None:
        logger.debug(f'[JIRA TOOL] Usando servicio cacheado para user {user_id}')
        return cached_service
    from app.integrations.providers.jira import JiraService, JiraAuthError
    try:
        jira_service = JiraService(user_id=user_id, db=_get_sync_db())
        _jira_service_ctx.set(jira_service)
        logger.info(f'[JIRA TOOL] Servicio inicializado para user {user_id}')
        return jira_service
    except JiraAuthError as e:
        logger.warning(f'[JIRA TOOL] User {user_id} no tiene JIRA conectado')
        raise JiraNotConnectedError() from e

def _format_success_response(message: str, data: Optional[Dict[str, Any]]=None, **kwargs) -> str:
    """
    [FIX] Formatea una respuesta exitosa y la serializa a JSON string.
    """
    response = {'success': True, 'message': message, **kwargs}
    if data:
        response.update(data)
    return json.dumps(response, ensure_ascii=False)

def _handle_error_response(error: Exception, context: str='') -> None:
    """
    [FIX] Lanza una ToolException estricta para que LangGraph la intercepte y active retries.
    """
    if isinstance(error, JiraToolError):
        error_code = error.error_code
        message = error.message
    else:
        error_code = 'unknown_error'
        message = f'Error inesperado: {str(error)}'
    logger.error(f'[JIRA TOOL] {context} - {error_code}: {message}')
    raise ToolException(f'Jira Error [{error_code}]: {message}')

class CreateJiraIssueInput(BaseModel):
    project_key: str = Field(..., alias='clave_proyecto', description='Clave del proyecto JIRA en MAYÚSCULAS (ej: DEV, PROD, BUGS)', min_length=2, max_length=10)
    summary: str = Field(..., alias='resumen', description='Título breve del ticket (5-255 caracteres)', min_length=5, max_length=255)
    description: str = Field('', alias='descripcion', description='Descripción detallada del ticket. Incluye contexto, pasos, etc.')
    issue_type: str = Field('Task', alias='tipo_incidente', description='Tipo de issue: Task, Bug, Story, Epic')
    priority: Optional[str] = Field(None, alias='prioridad', description='Prioridad: Highest, High, Medium, Low, Lowest')

    @field_validator('project_key')
    def validate_project_key(cls, v):
        if not isinstance(v, str) or not v.isupper():
            raise ValueError('project_key debe estar en MAYÚSCULAS')
        return v.strip()

    @field_validator('summary')
    def validate_summary(cls, v):
        if not isinstance(v, str) or not v.strip():
            raise ValueError('summary no puede estar vacío')
        return v.strip()

class GetJiraIssueInput(BaseModel):
    issue_key: str = Field(..., alias='clave_issue', description='Clave del issue (formato: PROYECTO-NÚMERO, ej: DEV-123)', min_length=3)

    @field_validator('issue_key')
    def validate_issue_key(cls, v):
        if not isinstance(v, str) or '-' not in v:
            raise ValueError('issue_key debe tener formato PROYECTO-NÚMERO')
        parts = v.split('-')
        if len(parts) != 2 or not parts[0].isupper() or (not parts[1].isdigit()):
            raise ValueError('Formato inválido. Ejemplo válido: DEV-123')
        return v.strip().upper()

class SearchJiraIssuesInput(BaseModel):
    jql: str = Field(..., alias='consulta_jql', description="Query JQL. Ejemplos: 'project = DEV AND status = Open', 'assignee = currentUser()'")
    max_results: int = Field(50, alias='max_resultados', ge=1, le=100, description='Número máximo de resultados (1-100)')

def create_jira_issue_function(project_key: str, summary: str, description: str='', issue_type: str='Task', priority: Optional[str]=None) -> str:
    try:
        user_id = _get_current_user_id()
        logger.info(f'[JIRA TOOL] create_issue - user: {user_id}, project: {project_key}')
        jira = _get_jira_service()
        ticket = jira.create_ticket(project_key=project_key, summary=summary, description=description, issue_type=issue_type, priority=priority)
        logger.info(f"[JIRA TOOL] Ticket creado: {ticket['key']}")
        return _format_success_response(message=f"Ticket {ticket['key']} creado exitosamente. Puedes verlo en: {ticket['url']}", key=ticket['key'], url=ticket['url'], ticket_id=ticket['id'])
    except (JiraContextError, JiraAuthenticationError, JiraNotConnectedError) as e:
        _handle_error_response(e, 'create_issue')
    except Exception as e:
        _handle_error_response(e, f'create_issue (project: {project_key})')

def get_jira_projects_function() -> str:
    try:
        user_id = _get_current_user_id()
        logger.info(f'[JIRA TOOL] get_projects - user: {user_id}')
        jira = _get_jira_service()
        projects = jira.get_projects()
        logger.info(f'[JIRA TOOL] {len(projects)} proyectos encontrados')
        project_list = ', '.join((f"{p['key']} ({p['name']})" for p in projects))
        return _format_success_response(message=f'📁 Se encontraron {len(projects)} proyectos: {project_list}', projects=projects, count=len(projects))
    except (JiraContextError, JiraAuthenticationError, JiraNotConnectedError) as e:
        _handle_error_response(e, 'get_projects')
    except Exception as e:
        _handle_error_response(e, 'get_projects')

def get_jira_issue_function(issue_key: str) -> str:
    try:
        user_id = _get_current_user_id()
        logger.info(f'[JIRA TOOL] get_issue - user: {user_id}, issue: {issue_key}')
        jira = _get_jira_service()
        issue = jira.get_issue(issue_key)
        logger.info(f'[JIRA TOOL] Issue {issue_key} obtenido')
        return _format_success_response(message=f"📄 Issue {issue_key}: {issue['summary']} (Estado: {issue['status']})", issue=issue)
    except (JiraContextError, JiraAuthenticationError, JiraNotConnectedError) as e:
        _handle_error_response(e, f'get_issue ({issue_key})')
    except Exception as e:
        error_msg = str(e).lower()
        if '404' in error_msg or 'not found' in error_msg:
            raise ToolException(f"El issue '{issue_key}' no existe o no tienes permisos para verlo.")
        _handle_error_response(e, f'get_issue ({issue_key})')

def search_jira_issues_function(jql: str, max_results: int=50) -> str:
    try:
        user_id = _get_current_user_id()
        logger.info(f'[JIRA TOOL] search_issues - user: {user_id}, JQL: {jql}')
        jira = _get_jira_service()
        issues = jira.search_issues(jql=jql, max_results=max_results)
        logger.info(f'[JIRA TOOL] {len(issues)} issues encontrados')
        simplified = []
        for issue in issues:
            fields = issue.get('fields', {})
            simplified.append({'key': issue.get('key'), 'summary': fields.get('summary'), 'status': fields.get('status', {}).get('name'), 'assignee': fields.get('assignee', {}).get('displayName', 'Sin asignar')})
        if simplified:
            issue_list = '\n'.join((f"  • {i['key']}: {i['summary']} [{i['status']}]" for i in simplified[:5]))
            if len(simplified) > 5:
                issue_list += f'\n  ... y {len(simplified) - 5} más'
        else:
            issue_list = 'No se encontraron issues.'
        return _format_success_response(message=f'🔍 Se encontraron {len(simplified)} issues:\n{issue_list}', issues=simplified, count=len(simplified))
    except (JiraContextError, JiraAuthenticationError, JiraNotConnectedError) as e:
        _handle_error_response(e, f'search_issues (JQL: {jql})')
    except Exception as e:
        error_msg = str(e).lower()
        if 'jql' in error_msg or 'syntax' in error_msg:
            raise ToolException(f'Error en la sintaxis de JQL. Corrige tu consulta: {str(e)}')
        _handle_error_response(e, f'search_issues (JQL: {jql})')

def health_check_jira_function() -> str:
    try:
        user_id = _get_current_user_id()
        logger.info(f'[JIRA TOOL] health_check - user: {user_id}')
        jira = _get_jira_service()
        health = jira.health_check()
        logger.info(f'[JIRA TOOL] Health check OK')
        return _format_success_response(message=f"Integración JIRA operativa. {health['projects_count']} proyectos accesibles. Token expira en {health['token_expires_in_minutes']:.1f} minutos.", status=health['status'], cloud_id=health['cloud_id'], projects_count=health['projects_count'], token_expires_in_minutes=health['token_expires_in_minutes'])
    except (JiraContextError, JiraAuthenticationError, JiraNotConnectedError) as e:
        _handle_error_response(e, 'health_check')
    except Exception as e:
        _handle_error_response(e, 'health_check')

def _make_jira_tool(name: str, func: Callable, description: str, args_schema: Optional[type]=None) -> StructuredTool:
    """Helper Enterprise para inyectar handle_tool_error=True."""
    kwargs = {'name': name, 'func': func, 'description': description, 'handle_tool_error': True, 'return_direct': False}
    if args_schema:
        kwargs['args_schema'] = args_schema
    return StructuredTool.from_function(**kwargs)
create_jira_issue_tool = _make_jira_tool(name='create_jira_issue', func=create_jira_issue_function, description="Crea un nuevo ticket/issue en JIRA para el usuario autenticado. Usa este tool cuando el usuario pida crear un ticket, bug, tarea o story. El user_id se obtiene automáticamente de la sesión. Ejemplos de uso: 'crea un bug en DEV sobre el login', 'nueva tarea en PROD para el despliegue'.", args_schema=CreateJiraIssueInput)
get_jira_projects_tool = _make_jira_tool(name='get_jira_projects', func=get_jira_projects_function, description='Obtiene la lista de proyectos JIRA disponibles para el usuario. Usa este tool cuando: (1) el usuario pregunte qué proyectos tiene, (2) necesites verificar project_keys válidos antes de crear un ticket, (3) el usuario pida crear un ticket sin especificar el proyecto.')
get_jira_issue_tool = _make_jira_tool(name='get_jira_issue', func=get_jira_issue_function, description="Obtiene información detallada de un issue específico por su clave. Usa este tool cuando el usuario pregunte por un ticket específico (ej: '¿qué dice DEV-123?'). Retorna: summary, status, assignee, priority, fechas.", args_schema=GetJiraIssueInput)
search_jira_issues_tool = _make_jira_tool(name='search_jira_issues', func=search_jira_issues_function, description="Busca issues en JIRA usando JQL (JIRA Query Language). Usa este tool para búsquedas complejas. Ejemplos de JQL útiles: 'project = DEV AND status = Open' (bugs abiertos en DEV), 'assignee = currentUser() AND status != Done' (mis tareas pendientes), 'priority = High AND created >= -7d' (prioridad alta última semana). Retorna lista de issues con key, summary, status, assignee.", args_schema=SearchJiraIssuesInput)
health_check_jira_tool = _make_jira_tool(name='health_check_jira', func=health_check_jira_function, description='Verifica el estado de la integración JIRA del usuario. Usa este tool cuando el usuario reporte problemas con JIRA o quiera saber si su conexión está activa. Retorna: estado, proyectos disponibles, tiempo de expiración del token.')
jira_tools = [create_jira_issue_tool, get_jira_projects_tool, get_jira_issue_tool, search_jira_issues_tool, health_check_jira_tool]

def get_jira_tools_for_agent() -> List[StructuredTool]:
    """Retorna todas las tools de JIRA listas para inyectar en LangGraph."""
    return jira_tools
JIRA_TOOL_METADATA = {'version': '3.1.0', 'architecture': 'session_based_auth_with_fail_safe', 'tools_count': len(jira_tools), 'tools': [tool.name for tool in jira_tools], 'features': ['Auto user_id injection from Flask session', 'Request-scoped service caching', 'Custom exception hierarchy', 'LLM-friendly error messages (ToolException)', 'JQL search support with auto-retry triggers']}

