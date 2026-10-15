"""Agente alterno con langgraph-bigtool: el modelo no recibe todas las herramientas, las busca con
`retrieve_tools` en un índice semántico. Se activa con USE_BIGTOOL=1 (agent.py sigue siendo el default).

Diferencias con el agente principal (bigtool no soporta middleware):
- sin HumanInTheLoopMiddleware → el registro NO incluye herramientas con efectos reales;
- sin ToolErrorMiddleware → cada herramienta se envuelve para devolver "Error: ..." en vez de lanzar;
- sin tope de llamadas por esfuerzo → el límite es recursion_limit; el esfuerzo sí ajusta el razonamiento;
- las herramientas no usan argumentos inyectados (ToolRuntime): bigtool @ main llama a la API interna de
  ToolNode con la firma vieja. user_id y el escritor de stream se leen con get_runtime()/get_stream_writer().

Dos stores separados: el InMemoryStore con el índice de herramientas va al grafo (compile(store=...));
el MongoDBStore de recuerdos lo usan guardar_recuerdo/buscar_recuerdos por cierre. No chocan.
"""
import logging
import math
import re
import types
import unicodedata
import warnings
from typing import Annotated, Callable

from langchain.embeddings import init_embeddings
from langchain_core._api.beta_decorator import LangChainBetaWarning
from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableLambda
from langchain_core.tools import BaseTool, StructuredTool, tool
from langgraph.config import get_stream_writer
from langgraph.prebuilt import InjectedStore
from langgraph.runtime import get_runtime
from langgraph.store.base import BaseStore, PutOp
from langgraph.store.memory import InMemoryStore
from langgraph_bigtool import create_agent as create_bigtool_agent
from langgraph_bigtool.utils import convert_positional_only_function_to_tool

from assistant import memory
from assistant.agent import system_prompt_text
from assistant.apps.crm_demo import crm_tools
from assistant.config import Settings
from assistant.extra_tools import extra_tools
from assistant.tool_spec import expand_requirements, get_spec, validate_registry
from assistant.tools import (
    INVESTIGADOR_DOC, calculadora, fecha_hora, investigar, make_buscar_web, make_subinvestigador, web_search,
)

logger = logging.getLogger(__name__)

NAMESPACE = ("tools",)
RETRIEVE_LIMIT = 3  # herramientas que devuelve cada búsqueda
BIGTOOL_PROMPT = (
    "\n\nYour tools are not loaded up front: there is a registry with many of them (math, text, web, "
    "memory, date, research). For any calculation, current fact, memory lookup or text transformation, "
    "ALWAYS use a tool, even if you think you know the answer: first call retrieve_tools with an English "
    "description of what you need, then call the tool it returns. "
    "Only for conversation (greetings, opinions, small talk) reply directly without retrieve_tools."
)
_EXCLUIR_MATH = {"factorial", "comb", "perm", "prod"}  # ponytail: pueden tardar muchísimo con números enormes


def _ctx(attr: str, default=None):
    try:
        return getattr(get_runtime().context, attr, default)
    except Exception:  # noqa: BLE001 - fuera de un grafo no hay runtime
        return default


def _seguro(t: BaseTool) -> BaseTool:
    """Misma herramienta, pero devuelve 'Error: ...' en vez de lanzar (el agente lo ve e intenta otra cosa)."""

    def run(**kwargs):
        try:
            return t.invoke(kwargs)
        except Exception as exc:  # noqa: BLE001
            return f"Error en la herramienta ({type(exc).__name__}): {exc}. Intenta otra cosa."

    return StructuredTool.from_function(func=run, name=t.name, description=t.description, args_schema=t.args_schema,
                                        metadata=t.metadata)  # conserva la ficha de @tool_spec


def _herramientas_texto() -> list[BaseTool]:
    @tool
    def to_uppercase(text: str) -> str:
        """Convert text to UPPERCASE."""
        return text.upper()

    @tool
    def to_lowercase(text: str) -> str:
        """Convert text to lowercase."""
        return text.lower()

    @tool
    def title_case(text: str) -> str:
        """Capitalize The First Letter Of Each Word."""
        return text.title()

    @tool
    def reverse_text(text: str) -> str:
        """Reverse the characters of a text."""
        return text[::-1]

    @tool
    def count_words(text: str) -> int:
        """Count the words in a text."""
        return len(text.split())

    @tool
    def count_characters(text: str) -> int:
        """Count the characters in a text (including spaces)."""
        return len(text)

    @tool
    def remove_accents(text: str) -> str:
        """Remove accents/diacritics from a text (á -> a)."""
        return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")

    @tool
    def slugify(text: str) -> str:
        """Convert a text to a URL slug (lowercase, hyphens, no accents)."""
        plain = remove_accents.invoke({"text": text}).lower()
        return re.sub(r"[^a-z0-9]+", "-", plain).strip("-")

    @tool
    def is_palindrome(text: str) -> bool:
        """Check whether a text is a palindrome, ignoring spaces, case and accents."""
        plain = re.sub(r"[^a-z0-9]", "", remove_accents.invoke({"text": text}).lower())
        return plain == plain[::-1]

    return [to_uppercase, to_lowercase, title_case, reverse_text, count_words, count_characters,
            remove_accents, slugify, is_palindrome]


def _herramientas_math() -> list[BaseTool]:
    out = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", LangChainBetaWarning)  # la utilidad de bigtool está marcada beta
        for name in dir(math):
            fn = getattr(math, name)
            if name in _EXCLUIR_MATH or not isinstance(fn, types.BuiltinFunctionType):
                continue
            if t := convert_positional_only_function_to_tool(fn):
                out.append(t)
    return out


def build_registry(model, settings: Settings, memories_store, search_fn: Callable = web_search) -> dict[str, BaseTool]:
    """Registro id -> herramienta. id = nombre de la herramienta (legible en la UI)."""
    buscar_web = make_buscar_web(settings, search_fn)
    sub = make_subinvestigador(model, buscar_web)

    @tool
    def guardar_recuerdo(texto: str) -> str:
        """Saves a stable fact about the user to long-term memory (name, likes, preferences, work
        context). Write it as a complete, self-contained sentence in the user's language."""
        memory.save_memory(memories_store, _ctx("user_id", "anon"), texto)
        return "Recuerdo guardado."

    @tool
    def buscar_recuerdos(consulta: str) -> str:
        """Searches long-term memory for what is known about the user (name, likes, preferences).
        Pass topic keywords in the language the memories were saved in, or an empty string for the
        most recent ones."""
        found = memory.search_memories(memories_store, _ctx("user_id", "anon"), consulta)
        return "\n".join(f"- {t}" for t in found) if found else "Sin recuerdos"

    @tool(description=INVESTIGADOR_DOC)
    def investigador_profundo(tarea: str) -> str:
        return investigar(sub, tarea, get_stream_writer())

    tools = [calculadora, fecha_hora, buscar_web, guardar_recuerdo, buscar_recuerdos, investigador_profundo,
             *extra_tools()]
    if settings.bigtool_demo_tools:
        tools += _herramientas_math() + _herramientas_texto() + crm_tools()
    registry = {t.name: _seguro(t) for t in tools}
    assert len(registry) == len(tools), "nombres de herramientas duplicados en el registro"
    validate_registry(registry)
    return registry


def _index_document(t: BaseTool) -> str:
    spec = get_spec(t)
    return spec.document(t) if spec else f"{t.name}: {t.description}"


def make_retrieve_tools(registry: dict[str, BaseTool]) -> Callable:
    """retrieve_tools de bigtool + las pre-funciones declaradas en `requires` de cada herramienta encontrada."""

    def retrieve_tools(query: str, *, store: Annotated[BaseStore, InjectedStore]) -> list[str]:
        """Retrieve a tool to use, given a search query."""
        found = [r.key for r in store.search(NAMESPACE, query=query, limit=RETRIEVE_LIMIT)]
        return expand_requirements(found, registry)

    return retrieve_tools


def build_tool_index(registry: dict[str, BaseTool], settings: Settings, embeddings=None) -> InMemoryStore:
    """Índice semántico en memoria (no MongoDB: en local no hay búsqueda vectorial). Se rellena al arrancar."""
    emb = embeddings or init_embeddings(f"openai:{settings.embedding_model}", api_key=settings.openai_api_key or None)
    dims = len(emb.embed_query("dims"))
    store = InMemoryStore(index={"embed": emb, "dims": dims, "fields": ["description"]})
    store.batch([PutOp(NAMESPACE, k, {"description": _index_document(t)}) for k, t in registry.items()])
    logger.info("Índice de herramientas: %d herramientas (%s, %d dims)", len(registry), settings.embedding_model, dims)
    return store


class PromptedModel:
    """Adaptador mínimo: bigtool no acepta system prompt (issue #7) ni middleware. Antepone el prompt
    dinámico (system.md + fecha + instrucciones de retrieve_tools) y aplica el razonamiento del esfuerzo."""

    def __init__(self, model):
        self.model = model

    def bind_tools(self, tools, **kwargs):
        if effort := _ctx("razonamiento"):
            kwargs["reasoning"] = {"effort": effort}
        bound = self.model.bind_tools(tools, **kwargs)
        return RunnableLambda(lambda msgs: [SystemMessage(system_prompt_text() + BIGTOOL_PROMPT), *msgs]) | bound


def build_bigtool_agent(model, settings: Settings, checkpointer=None, memories_store=None,
                        embeddings=None, search_fn: Callable = web_search):
    registry = build_registry(model, settings, memories_store, search_fn)
    index = build_tool_index(registry, settings, embeddings)
    builder = create_bigtool_agent(PromptedModel(model), registry, limit=RETRIEVE_LIMIT, namespace_prefix=NAMESPACE,
                                   retrieve_tools_function=make_retrieve_tools(registry))
    return builder.compile(checkpointer=checkpointer, store=index)
