"""Agente alterno con langgraph-bigtool: el modelo no recibe todas las herramientas, las busca con
`retrieve_tools` en un índice semántico. Se activa con USE_BIGTOOL=1 (agent.py sigue siendo el default).

Diferencias con el agente principal (bigtool no soporta middleware):
- sin HumanInTheLoopMiddleware → el registro NO incluye herramientas con efectos reales;
- sin ToolErrorMiddleware → cada herramienta se envuelve para devolver "Error: ..." en vez de lanzar;
- sin tope de llamadas por esfuerzo → el límite es recursion_limit; el esfuerzo sí ajusta el razonamiento;
- las herramientas no usan argumentos inyectados (ToolRuntime): bigtool @ main llama a la API interna de
  ToolNode con la firma vieja. user_id y el escritor de stream se leen con get_runtime()/get_stream_writer().

Dos stores separados: el InMemoryStore con el índice de herramientas va al grafo (compile(store=...));
el MongoDBStore de recuerdos lo usan save_memory/search_memories por cierre. No chocan.
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
from langgraph.config import get_config, get_stream_writer
from langgraph.errors import GraphBubbleUp
from langgraph.types import interrupt
from langgraph.prebuilt import InjectedStore
from langgraph.runtime import get_runtime
from langgraph.store.base import BaseStore, PutOp
from langgraph.store.memory import InMemoryStore
from langgraph_bigtool import create_agent as create_bigtool_agent
from langgraph_bigtool.utils import convert_positional_only_function_to_tool

from assistant.core import memory
from assistant.core.agent import (OLD_TOOL_NAMES, history_landing, landing_due, landing_note, mark_no_tools,
                             rename_old_tools, system_prompt_text)
from assistant.core.config import Settings
from assistant.core.tool_spec import expand_requirements, get_spec, validate_registry
from assistant.core.tools import (
    ACTUALIZAR_RECUERDO_DOC, BUSCAR_RECUERDOS_DOC, INVESTIGADOR_DOC, calculadora, save_memory_doc,
    check_python_syntax,
    earlier_research, fecha_hora, investigar, investigator_model, make_buscar_web, memory_verifier_for, turn_key,
    web_search, DEEP_RESEARCH_CONFIRM, FOLLOW_UP_MSG, RESEARCH_DECLINED_MSG, research_needs_confirmation,
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
        except GraphBubbleUp:  # interrupt() (confirmación de deep_research): no es un error de la herramienta
            raise
        except Exception as exc:  # noqa: BLE001
            return f"Tool error ({type(exc).__name__}): {exc}. Try another approach."

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
        """Remove accents/diacritics from a text (an accented vowel becomes the plain vowel)."""
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


def _thread_messages(checkpointer) -> tuple[str | None, list]:
    """(thread_id, mensajes) del hilo en curso. Bigtool no inyecta el estado a las herramientas:
    se lee del último checkpoint, que ya incluye el mensaje del usuario de este turno."""
    try:
        thread_id = get_config()["configurable"]["thread_id"]
    except Exception:  # noqa: BLE001 - fuera de un grafo
        return None, []
    if checkpointer is None:
        return thread_id, []
    saved = checkpointer.get_tuple({"configurable": {"thread_id": thread_id}})
    messages = (saved.checkpoint.get("channel_values") or {}).get("messages") if saved else None
    return thread_id, messages or []


def _thread_user_texts(checkpointer) -> tuple[str | None, list[str]]:
    thread_id, messages = _thread_messages(checkpointer)
    return thread_id, memory.user_texts(messages)


def build_registry(model, settings: Settings, memories_store, search_fn: Callable = web_search,
                   checkpointer=None, checker=None, profile=None) -> dict[str, BaseTool]:
    """Registro id -> herramienta. id = nombre de la herramienta (legible en la UI). Las base del núcleo más las
    extra del perfil (el activo si no se pasa)."""
    from assistant.core.profile import active_profile

    profile = profile or active_profile()
    def search_key():
        thread_id, messages = _thread_messages(checkpointer)
        return thread_id, turn_key(thread_id, messages), messages

    buscar_web = make_buscar_web(settings, search_fn, key_fn=search_key)
    inv_model = investigator_model(model, settings)
    verifier = memory_verifier_for(settings, checker)

    @tool("save_memory", description=save_memory_doc(settings.memory_save_policy))
    def guardar_recuerdo(text: str, evidence: str = "") -> str:
        thread_id, messages = _thread_messages(checkpointer)
        return memory.remember(memories_store, _ctx("user_id", "anon"), text, evidence, memory.user_texts(messages),
                               thread_id=thread_id, verifier=verifier, saved_this_turn=memory.turn_saves(messages),
                               max_per_turn=settings.memory_max_per_turn, dedup=settings.memory_dedup,
                               dedup_score=settings.memory_dedup_score)

    @tool("search_memories", description=BUSCAR_RECUERDOS_DOC)
    def buscar_recuerdos(query: str) -> str:
        return memory.recall(memories_store, _ctx("user_id", "anon"), query, settings.memory_min_score)

    @tool("update_memory", description=ACTUALIZAR_RECUERDO_DOC)
    def actualizar_recuerdo(id: str, text: str, evidence: str = "") -> str:  # noqa: A002
        thread_id, texts = _thread_user_texts(checkpointer)
        return memory.revise(memories_store, _ctx("user_id", "anon"), id, text, evidence, texts,
                             thread_id=thread_id, verifier=verifier)

    @tool("deep_research", description=INVESTIGADOR_DOC)
    def investigador_profundo(task: str) -> str:
        thread_id, messages = _thread_messages(checkpointer)
        previous = earlier_research(messages)
        if previous is not None:
            return FOLLOW_UP_MSG.format(previous=previous)
        if research_needs_confirmation(messages):  # bigtool no tiene middleware: misma tarjeta, vía interrupt()
            answer = interrupt({"action_requests": [{"name": "deep_research", "args": {"task": task},
                                                     "description": DEEP_RESEARCH_CONFIRM}],
                                "review_configs": [{"action_name": "deep_research",
                                                    "allowed_decisions": ["approve", "reject"]}]})
            decision = ((answer or {}).get("decisions") or [{}])[0] if isinstance(answer, dict) else {}
            if decision.get("type") != "approve":
                return RESEARCH_DECLINED_MSG
        return investigar(inv_model, settings, search_fn, task, get_stream_writer(),
                          turn_key=turn_key(thread_id, messages))

    tools = [calculadora, fecha_hora, check_python_syntax, buscar_web, guardar_recuerdo, buscar_recuerdos,
             actualizar_recuerdo,
             investigador_profundo, *profile.bigtool_tools(settings)]
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


class RegistroTolerante(dict):
    """bigtool hace tool_registry[id] con los ids de selected_tool_ids guardados en el checkpoint. Un id antiguo
    (herramienta renombrada) se resuelve a la actual; uno que ya no existe da None y PromptedModel lo descarta, en vez
    de un KeyError que rompería el hilo."""

    def __missing__(self, key):
        return self.get(OLD_TOOL_NAMES.get(key))


class PromptedModel:
    """Adaptador mínimo: bigtool no acepta system prompt (issue #7) ni middleware. Antepone el prompt
    dinámico (system.md + fecha + instrucciones de retrieve_tools) y aplica el razonamiento del esfuerzo."""

    def __init__(self, model, cap: int = 0, settings: Settings | None = None, profile=None):
        self.model = model
        self.cap = cap  # TURN_TOKEN_CAP: al 80% (o con un historial más pesado que el tope), sin herramientas
        self.settings = settings  # política de memoria del prompt (MEMORY_SAVE_POLICY)
        self.profile = profile  # prompt y política del perfil; None = el activo

    def bind_tools(self, tools, **kwargs):
        if effort := _ctx("razonamiento"):
            kwargs["reasoning"] = {"effort": effort}
        if max_tokens := _ctx("max_tokens"):  # margen de salida con esfuerzo alto
            kwargs["max_tokens"] = max_tokens
        unicas = {}
        for t in tools:  # sin los ids que ya no existen (None) ni duplicados (id viejo + id nuevo)
            name = getattr(t, "name", None) or getattr(t, "__name__", None)
            if t is not None and name not in unicas:
                unicas[name] = t
        bound = self.model.bind_tools(list(unicas.values()), **kwargs)
        landing = self.model.bind_tools(list(unicas.values()), **{**kwargs, "tool_choice": "none"})

        def prompt(msgs):
            msgs = rename_old_tools(msgs)
            system = system_prompt_text(self.settings, self.profile) + BIGTOOL_PROMPT
            counter = landing_due(self.cap, [SystemMessage(system), *msgs])
            note = f"\n\n{landing_note(counter, self.cap)}" if counter else ""
            return [SystemMessage(system + note), *msgs]

        def route(sent):  # devolver un Runnable hace que RunnableLambda lo invoque con la misma entrada
            if counter := landing_due(self.cap, sent):
                counter.landing = True
                if history_landing(counter, self.cap):  # sin herramientas por el historial: la UI lo avisa
                    get_stream_writer()({"tipo": "sin_herramientas"})
                    return landing | RunnableLambda(mark_no_tools)
                return landing
            return bound

        return RunnableLambda(prompt) | RunnableLambda(route)


def build_bigtool_agent(model, settings: Settings, checkpointer=None, memories_store=None,
                        embeddings=None, search_fn: Callable = web_search, checker=None, profile=None):
    registry = build_registry(model, settings, memories_store, search_fn, checkpointer=checkpointer, checker=checker,
                              profile=profile)
    index = build_tool_index(registry, settings, embeddings)
    builder = create_bigtool_agent(PromptedModel(model, settings.turn_token_cap, settings, profile), RegistroTolerante(registry), limit=RETRIEVE_LIMIT, namespace_prefix=NAMESPACE,
                                   retrieve_tools_function=make_retrieve_tools(registry))
    return builder.compile(checkpointer=checkpointer, store=index)
