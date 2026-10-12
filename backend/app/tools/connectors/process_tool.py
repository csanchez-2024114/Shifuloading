"""
Process Tool Provider V2.
Refactorizado:
1. Erradicación de Silent Failures (uso estricto de ToolException).
2. Helper _make_tool para inyección automática de handle_tool_error=True.
3. Migración a StructuredTool y serialización JSON de respuestas.
4. Inyección de descripciones semánticas para correcta interpretación del LLM.
"""
import json
from datetime import datetime
from typing import Optional, List, Dict, Any, Callable
from bson import ObjectId
from bson.errors import InvalidId


def _json_default(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, ObjectId):
        return str(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
from langchain_openai import ChatOpenAI
from langchain_core.tools import StructuredTool, ToolException
from pydantic import BaseModel, Field
from config import Config
from app.services.mongo_process_manager import MongoProcessManager
from app.core.db_utils import canonicalize_email

class ViewProcessInput(BaseModel):
    process_id: str = Field(..., description='ID hexadecimal de MongoDB del proceso o el Nombre del proceso')

class ModifyStepInput(BaseModel):
    process_name: str = Field(..., alias='process_name', description='Nombre técnico (ej: train_process_...')
    step_number: int = Field(..., description='Número de paso a modificar (base 1)')
    new_tool_input: Dict[str, Any] = Field(..., alias='new_tool_input', description='Nuevo JSON de entrada para el paso')

class ExecuteProcessInput(BaseModel):
    process_name: str = Field(..., alias='process_name', description='Nombre del proceso a re-ejecutar')
    from_step: Optional[int] = Field(default=None, alias='from_step', description='Paso desde el cual re-ejecutar (opcional)')

class RecoverAndModifyProcessInput(BaseModel):
    process_id: str = Field(..., description='ID del proceso guardado a modificar')
    new_input: str = Field(..., description='Nueva instrucción o corrección del usuario')

class DeleteProcessByIdInput(BaseModel):
    process_id: str = Field(..., description='ID del proceso a eliminar permanentemente')

class ListProcessesInput(BaseModel):
    empty: str = Field(default='', alias='empty', description='Sin parámetros requeridos. Dejar vacío.')

class ProcessToolProvider:

    def __init__(self, user_email: str | None = None, user_id: str | None = None):
        email_source = user_email
        canonical = canonicalize_email(email_source) or (email_source or '')
        self.user_email = canonical
        self.user_id = user_id or ""
        self.manager = MongoProcessManager()
        self._llm = None

    def _ownership_filter(self) -> dict:
        """Returns a MongoDB filter that matches docs owned by this user (email OR user_id)."""
        conditions: list = []
        if self.user_email:
            conditions.append({"user_email": self.user_email})
            conditions.append({"correo_usuario": self.user_email})
        if self.user_id:
            conditions.append({"user_id": self.user_id})
        return {"$or": conditions} if conditions else {}

    @property
    def llm(self):
        if not self._llm:
            self._llm = ChatOpenAI(model=Config.MODEL_NAME, temperature=0, api_key=Config.OPENAI_API_KEY)
        return self._llm

    def _make_tool(self, name: str, func: Callable, description: str, args_schema: type[BaseModel]) -> StructuredTool:
        """Helper Enterprise para inyectar handle_tool_error=True en todas las herramientas."""
        return StructuredTool.from_function(func=func, name=name, description=description, args_schema=args_schema, handle_tool_error=True)

    def list_processes(self, empty: str='') -> str:
        """Devuelve un resumen de todos los procesos del usuario."""
        try:
            procesos = self.manager.load_all_by_user(self.user_email, self.user_id)
            if not procesos:
                return json.dumps({'status': 'empty', 'message': 'No tienes procesos guardados.'})

            # Batch-fetch all linked workflow docs to avoid N+1 queries
            workflow_ids = [
                ObjectId(p['workflow_id'])
                for p in procesos
                if p.get('workflow_id')
            ]
            workflows_by_id: dict = {}
            if workflow_ids:
                for wf in self.manager.db['workflows'].find({'_id': {'$in': workflow_ids}}):
                    workflows_by_id[str(wf['_id'])] = wf

            res = []
            for p in procesos:
                name = p.get('nombre_processo') or p.get('nombre_proceso') or p.get('nombre') or p.get('title') or 'Sin nombre'
                desc = p.get('descripcion') or p.get('goal') or p.get('process_summary') or ''
                status = p.get('status', '')
                steps = p.get('steps', [])

                entry = {
                    'id': str(p['_id']),
                    'nombre': name,
                    'descripcion': desc,
                    'status': status,
                    'created_at': p.get('created_at'),
                }

                # Enrich with workflow details when available
                wf_id = p.get('workflow_id')
                wf = workflows_by_id.get(str(wf_id)) if wf_id else None
                if wf:
                    trig = wf.get('trigger') or {}
                    schedule = trig.get('schedule') or {}
                    entry['trigger'] = trig.get('description') or p.get('trigger_description') or ''
                    entry['condicion'] = trig.get('condition') or ''
                    entry['frecuencia'] = schedule.get('human_readable') or trig.get('frequency') or ''
                    entry['total_pasos'] = len(wf.get('steps') or [])
                    entry['workflow_status'] = wf.get('status', '')
                elif p.get('trigger_description'):
                    entry['trigger'] = p.get('trigger_description')
                    if steps:
                        entry['total_pasos'] = len(steps)

                res.append(entry)
            return json.dumps(res, ensure_ascii=False, default=_json_default)
        except Exception as e:
            raise ToolException(f'Error al listar procesos: {str(e)}')

    def view_process(self, process_id: str) -> str:
        """Obtiene toda la traza de ejecución de un proceso específico (por ID o Nombre)."""
        ownership = self._ownership_filter()
        try:
            query = {'_id': ObjectId(process_id), **ownership}
        except InvalidId:
            query = {'$and': [{'$or': [{'nombre_proceso': process_id}, {'title': process_id}]}, ownership]} if ownership else {'nombre_proceso': process_id}
        try:
            process = self.manager.collection.find_one(query)
            if not process:
                raise ToolException(f"Proceso '{process_id}' no encontrado.")
            process['_id'] = str(process['_id'])
            if process.get('user_id'):
                process['user_id'] = str(process['user_id'])
            return json.dumps(process, ensure_ascii=False, default=_json_default)
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error interno al buscar el proceso: {str(e)}')

    def recover_process(self, process_name: str) -> str:
        """Re-ejecuta un proceso (Legacy / Dummy para no romper firmas)."""
        raise ToolException("Esta función está en desuso. Utiliza la herramienta 'recuperar_y_modificar_proceso'.")

    def modify_step(self, process_name: str, step_number: int, new_tool_input: Dict[str, Any]) -> str:
        """Modifica un paso (Legacy / Dummy para no romper firmas)."""
        raise ToolException("Modificación parcial no soportada. Utiliza la herramienta 'recuperar_y_modificar_proceso'.")

    def recover_and_modify_process_langgraph(self, process_id: str, new_input: str) -> str:
        raise ToolException("Esta funcionalidad ha sido reemplazada por el sistema de workflows de Shifu. Usa el agente para crear o modificar workflows.")

    def delete_process_by_id(self, process_id: str) -> str:
        """Elimina el registro de un proceso en MongoDB."""
        try:
            ownership = self._ownership_filter()
            res = self.manager.collection.delete_one({'_id': ObjectId(process_id), **ownership})
            if res.deleted_count > 0:
                res_dict = {'status': 'ok', 'mensaje': f"Proceso con id '{process_id}' eliminado correctamente"}
                return json.dumps(res_dict, ensure_ascii=False, default=_json_default)
            raise ToolException('Proceso no encontrado o no pertenece a tu usuario.')
        except InvalidId:
            raise ToolException('El ID proporcionado no es un identificador válido de MongoDB.')
        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f'Error al intentar eliminar el proceso: {str(e)}')

    def get_tool_list_processes(self) -> StructuredTool:
        return self._make_tool(
            name='listar_procesos',
            func=self.list_processes,
            description=(
                'Lista todos los procesos y automatizaciones guardados del usuario en la base de datos. '
                'Usar cuando el usuario pregunte: "qué procesos tengo", "mis automatizaciones", '
                '"procesos activos o completados", "muéstrame mis procesos configurados". '
                'Devuelve una lista JSON donde cada elemento tiene un campo "id" con el MongoDB ObjectId del proceso. '
                'SIEMPRE usa ese campo "id" exacto (ej: "6a14dc8119f66c283a813b49") al llamar delete_process_by_id o ver_proceso. '
                'NUNCA uses números secuenciales (1, 2, 3) como IDs — solo el valor del campo "id". '
                'NO usar para listar programaciones o schedules de ejecución.'
            ),
            args_schema=ListProcessesInput,
        )

    def get_tool_view_process(self) -> StructuredTool:
        return self._make_tool(
            name='ver_proceso',
            func=self.view_process,
            description='Obtiene el detalle completo, pasos y resultados de un proceso o automatización guardada, por su ID o nombre.',
            args_schema=ViewProcessInput,
        )

    def get_tool_recover_process(self) -> StructuredTool:
        return self._make_tool(name='recover_process', func=self.recover_process, description='Esta herramienta está en desuso. No la utilices.', args_schema=ExecuteProcessInput)

    def get_tool_modify_step(self) -> StructuredTool:
        return self._make_tool(name='modify_process_step', func=self.modify_step, description='Esta herramienta está en desuso. No la utilices.', args_schema=ModifyStepInput)

    def get_tool_recover_and_modify_process_langgraph(self) -> StructuredTool:
        return self._make_tool(name='recover_and_modify_process', func=self.recover_and_modify_process_langgraph, description='Útil para retomar un proceso que ya se ejecutó en el pasado y volver a correrlo sumándole una nueva instrucción o corrección.', args_schema=RecoverAndModifyProcessInput)

    def get_all_tools(self) -> list:
        return [
            self.get_tool_list_processes(),
            self.get_tool_view_process(),
            self.get_tool_recover_and_modify_process_langgraph(),
            self.get_tool_delete_process_by_id(),
        ]

    def get_tool_delete_process_by_id(self) -> StructuredTool:
        return self._make_tool(
            name='delete_process_by_id',
            func=self.delete_process_by_id,
            description=(
                'Elimina permanentemente un proceso guardado de la base de datos. '
                'El process_id debe ser el MongoDB ObjectId exacto del proceso (campo "id" de listar_procesos), '
                'por ejemplo "6a14dc8119f66c283a813b49". '
                'Si el usuario quiere eliminar varios, llama esta herramienta una vez por proceso con su ID real. '
                'NUNCA uses números como 1, 2, 3 — solo el ObjectId hexadecimal de 24 caracteres.'
            ),
            args_schema=DeleteProcessByIdInput,
        )
