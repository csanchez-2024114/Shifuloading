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
from typing import Annotated, Callable

from langchain.embeddings import init_embeddings
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

from assistant.core import memory
from assistant.core.agent import (history_landing, landing_due, landing_note, mark_no_tools, rename_old_tools,
                                  system_prompt_text)
from assistant.core.config import Settings
from assistant.core.files import prompt_addition, thread_has_files
from assistant.core.i18n import tr
from assistant.core.tool_spec import expand_requirements, get_spec, validate_registry
from assistant.core.tools import (
    ACTUALIZAR_RECUERDO_DOC, BUSCAR_RECUERDOS_DOC, INVESTIGADOR_DOC, calculadora, save_memory_doc,
    check_python_syntax,
    earlier_research, fecha_hora, investigar, investigator_model, make_buscar_web, memory_verifier_for, turn_key,
    web_search, FOLLOW_UP_MSG, RESEARCH_DECLINED_MSG, research_needs_confirmation,
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


def _effect(t: BaseTool, profile) -> str:
    """Efecto de la herramienta: el de su ficha @tool_spec o, si no tiene, el de ToolPolicy del perfil."""
    spec = get_spec(t)
    if spec is not None and spec.effect != "read":
        return spec.effect
    policy = profile.tool_policies.get(t.name)
    return policy.effect if policy is not None else "read"


def _con_aprobacion(t: BaseTool, profile) -> BaseTool:
    """Misma herramienta (nombre, descripción, argumentos y ficha), pero antes de correr pide la tarjeta de aprobación
    con interrupt(), igual que deep_research: bigtool no tiene HumanInTheLoopMiddleware."""

    def run(**kwargs):
        answer = interrupt({"action_requests": [{"name": t.name, "args": kwargs,
                                                 "description": tr("tools.effect_confirm", profile, name=t.name)}],
                            "review_configs": [{"action_name": t.name, "allowed_decisions": ["approve", "reject"]}]})
        decision = ((answer or {}).get("decisions") or [{}])[0] if isinstance(answer, dict) else {}
        if decision.get("type") != "approve":
            # mismo prefijo que el rechazo de HumanInTheLoopMiddleware: la UI lo marca como no realizada
            return f"User rejected the tool call: {t.name} was not run."
        return t.invoke(kwargs)

    return StructuredTool.from_function(func=run, name=t.name, description=t.description, args_schema=t.args_schema,
                                        metadata=t.metadata)


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
                               dedup_score=settings.memory_dedup_score,
                               require_quote=settings.memory_require_quote or thread_has_files(messages))

    @tool("search_memories", description=BUSCAR_RECUERDOS_DOC)
    def buscar_recuerdos(query: str) -> str:
        return memory.recall(memories_store, _ctx("user_id", "anon"), query, settings.memory_min_score)

    @tool("update_memory", description=ACTUALIZAR_RECUERDO_DOC)
    def actualizar_recuerdo(id: str, text: str, evidence: str = "") -> str:  # noqa: A002
        thread_id, messages = _thread_messages(checkpointer)
        # con archivos adjuntos en el hilo, solo se guarda lo que el usuario dijo con sus palabras (cita literal)
        return memory.revise(memories_store, _ctx("user_id", "anon"), id, text, evidence, memory.user_texts(messages),
                             thread_id=thread_id, verifier=verifier,
                             require_quote=settings.memory_require_quote or thread_has_files(messages))

    @tool("deep_research", description=INVESTIGADOR_DOC)
    def investigador_profundo(task: str) -> str:
        thread_id, messages = _thread_messages(checkpointer)
        previous = earlier_research(messages)
        if previous is not None:
            return FOLLOW_UP_MSG.format(previous=previous)
        if research_needs_confirmation(messages):  # bigtool no tiene middleware: misma tarjeta, vía interrupt()
            answer = interrupt({"action_requests": [{"name": "deep_research", "args": {"task": task},
                                                     "description": tr("tools.deep_research_confirm")}],
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
    if settings.files_enabled:  # FILES_ENABLED: las mismas lecturas que en el agente normal, del store del agente
        tools += _file_tools(memories_store)
    if settings.effect_approval:  # P3.3: write/send/delete pasan por la tarjeta, con el interrupt() de deep_research
        tools = [_con_aprobacion(t, profile) if _effect(t, profile) != "read" else t for t in tools]
    registry = {t.name: _seguro(t) for t in tools}
    assert len(registry) == len(tools), "nombres de herramientas duplicados en el registro"
    validate_registry(registry)
    return registry


def _file_tools(memories_store) -> list[BaseTool]:
    """read_file y search_in_file para bigtool: sin ToolRuntime, el hilo sale de la config y el usuario del contexto."""
    from assistant.core.files.tools import READ_FILE_DOC, READ_MAX_CHARS, SEARCH_IN_FILE_DOC, read_file_text, search_text

    def ids() -> tuple[str, str | None]:
        try:
            thread_id = get_config()["configurable"]["thread_id"]
        except Exception:  # noqa: BLE001 - fuera de un grafo
            thread_id = None
        return _ctx("user_id", "anon"), thread_id

    @tool("read_file", description=READ_FILE_DOC)
    def read_file(file_id: str = "", page: int = 1, offset: int = 0, max_chars: int = READ_MAX_CHARS) -> str:
        return read_file_text(memories_store, *ids(), file_id, page, offset, max_chars)

    @tool("search_in_file", description=SEARCH_IN_FILE_DOC)
    def search_in_file(query: str, file_id: str = "", k: int = 3) -> str:
        user_id, thread_id = ids()
        return search_text(memories_store, user_id, thread_id, query, file_id, k)

    return [read_file, search_in_file]


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

    def __init__(self, *args, legacy=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.legacy = legacy or {}  # nombres antiguos del perfil: antiguo -> actual

    def __missing__(self, key):
        return self.get(self.legacy.get(key))


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
            msgs = rename_old_tools(msgs, None if self.profile is None else self.profile.legacy_tool_names)
            system = system_prompt_text(self.settings, self.profile)
            if self.settings is not None and self.settings.files_enabled:  # la regla, solo si el hilo tiene adjuntos
                system += prompt_addition(msgs)
            system += BIGTOOL_PROMPT
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
    from assistant.core.profile import active_profile

    profile = profile or active_profile()
    registry = build_registry(model, settings, memories_store, search_fn, checkpointer=checkpointer, checker=checker,
                              profile=profile)
    index = build_tool_index(registry, settings, embeddings)
    builder = create_bigtool_agent(PromptedModel(model, settings.turn_token_cap, settings, profile), RegistroTolerante(registry, legacy=profile.legacy_tool_names), limit=RETRIEVE_LIMIT, namespace_prefix=NAMESPACE,
                                   retrieve_tools_function=make_retrieve_tools(registry))
    return builder.compile(checkpointer=checkpointer, store=index)
