"""
Herramienta de nivel superior para la gestión del conocimiento del usuario.
Permite que Shifu aprenda, actualice y limpie sus propios registros de memoria.

Refactorización:
- Erradicación de fallos silenciosos (uso estricto de ToolException).
- Inyección de handle_tool_error=True vía _make_tool.
- Serialización consistente JSON para outputs.
"""
import json
import logging
from typing import Optional, List, Any, Dict, Callable
from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool, ToolException
from app.services.user_memories_service import UserMemoriesService
from app.core.db_utils import canonicalize_email
logger = logging.getLogger('tools.memories_editor')

class ListMemoriesInput(BaseModel):
    empty: str = Field(default='', alias='empty', description='Sin parámetros requeridos. Dejar vacío.')

class CreateMemoryInput(BaseModel):
    key: str = Field(..., description="Nombre técnico de la preferencia (ej: 'coding_style')")
    value: str = Field(..., description='Valor o descripción de la memoria')
    category: str = Field(..., description="Categoría (ej: 'personal', 'work', 'tech')")
    confidence: float = Field(default=0.9, description='Nivel de certeza de 0.0 a 1.0')

class UpdateMemoryInput(BaseModel):
    key: str = Field(..., description='Clave de la memoria a modificar')
    new_value: str = Field(..., alias='new_value', description='El nuevo contenido de la memoria')

class SearchMemoryInput(BaseModel):
    query: str = Field(..., alias='query', description='Palabra clave para buscar en memorias')

class MemoriesEditorToolProvider:

    def __init__(self, user_email: str | None=None):
        email_source = user_email
        canonical = canonicalize_email(email_source) or (email_source or '')
        self.user_email = canonical
        self.service = UserMemoriesService(self.user_email)

    def _make_tool(self, name: str, func: Callable, description: str, args_schema: type[BaseModel]) -> StructuredTool:
        """Helper Enterprise para inyectar handle_tool_error=True en todas las herramientas."""
        return StructuredTool.from_function(func=func, name=name, description=description, args_schema=args_schema, handle_tool_error=True)

    def list_memories(self, empty: str='') -> str:
        """Lista el conocimiento actual que el agente tiene del usuario."""
        try:
            doc = self.service.get_or_create_memories()
            memories = doc.get('memories', [])
            if not memories:
                return json.dumps({'status': 'empty', 'message': 'Aún no tengo memorias registradas sobre ti.'}, ensure_ascii=False)
            res_list = [{'key': m.get('key'), 'value': m.get('value'), 'category': m.get('category'), 'confidence': m.get('confidence', 0)} for m in memories]
            return json.dumps({'status': 'success', 'memories': res_list}, ensure_ascii=False)
        except Exception as e:
            logger.error(f'[MemoriesTool] Error al listar memorias: {e}')
            raise ToolException(f'Error al leer las memorias de la base de datos: {str(e)}')

    def create_or_update_memory(self, key: str, value: str, category: str, confidence: float=0.9) -> str:
        """Permite al agente aprender algo nuevo."""
        try:
            memoria = {'key': key.strip().lower(), 'value': value.strip(), 'category': category.strip().lower(), 'confidence': confidence, 'update_count': 1}
            doc = self.service.get_or_create_memories()
            if self.service._add_or_update_memory(doc, memoria):
                self.service._save_memories_to_db(doc)
                return json.dumps({'status': 'success', 'message': f"He aprendido que tu '{key}' es '{value}'."}, ensure_ascii=False)
            raise ToolException('No se pudo procesar el guardado de este aprendizaje en la base de datos.')
        except ToolException:
            raise
        except Exception as e:
            logger.error(f'[MemoriesTool] Error al crear/actualizar memoria: {e}')
            raise ToolException(f'Error interno al intentar aprender o actualizar el dato: {str(e)}')

    def search_in_memory(self, query: str) -> str:
        """Busca rápidamente en el baúl de los recuerdos."""
        try:
            doc = self.service.get_or_create_memories()
            found = [m for m in doc.get('memories', []) if query.lower() in m.get('key', '').lower() or query.lower() in m.get('value', '').lower()]
            if not found:
                return json.dumps({'status': 'empty', 'message': f"No encontré nada relacionado con '{query}'."}, ensure_ascii=False)
            res_list = [{'key': f.get('key'), 'value': f.get('value')} for f in found]
            return json.dumps({'status': 'success', 'results': res_list}, ensure_ascii=False)
        except Exception as e:
            logger.error(f'[MemoriesTool] Error al buscar en memoria: {e}')
            raise ToolException(f'Error en la búsqueda dentro del registro de memorias: {str(e)}')

    def get_tool_list_memories(self) -> StructuredTool:
        return self._make_tool(name='list_user_memories', func=self.list_memories, description='Muestra todo lo que el agente sabe del usuario (gustos, reglas, historia).', args_schema=ListMemoriesInput)

    def get_tool_crear_actualizar_memoria(self) -> StructuredTool:
        return self._make_tool(name='create_or_update_memory', func=self.create_or_update_memory, description='Guarda un nuevo dato importante que el usuario haya mencionado.', args_schema=CreateMemoryInput)

    def get_tool_buscar_memoria(self) -> StructuredTool:
        return self._make_tool(name='search_user_memory', func=self.search_in_memory, description='Busca un dato específico en la memoria del agente usando una palabra clave.', args_schema=SearchMemoryInput)

    def get_all_tools(self) -> List[Any]:
        return [self.get_tool_list_memories(), self.get_tool_crear_actualizar_memoria(), self.get_tool_buscar_memoria()]
