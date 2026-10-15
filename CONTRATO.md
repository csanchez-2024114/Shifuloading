# CONTRATO

Fuente de verdad para todos los subagentes. Si tu código no coincide con esto, este documento manda.
Versiones instaladas en `.venv`: langgraph 1.2.15, langchain 1.4.6, langchain-core 1.6.10, langchain-openai 1.7.2,
langgraph-checkpoint-mongodb 0.5.1, langgraph-store-mongodb 0.4.0, pymongo 4.19, fastapi 0.143, ddgs 9.16.
Python: `.venv\Scripts\python`. Paquete instalado editable (`src/assistant`), importa como `assistant.*`.

**Todo es SÍNCRONO** (MongoDBSaver es sync). Usa `agent.stream(...)` / `agent.invoke(...)`, nunca `astream`.
Sin Docker. MongoDB local en `mongodb://127.0.0.1:27017` ya está corriendo; no lo arranques.

## Archivos y dueños
| Archivo | Dueño |
|---|---|
| `src/assistant/config.py`, `prompts/system.md`, `CONTRATO.md`, `pyproject.toml` | principal (YA EXISTEN, no tocar) |
| `src/assistant/agent.py`, `src/assistant/tools.py` | subagente **agente** |
| `src/assistant/memory.py` | subagente **memoria** |
| `static/index.html` | subagente **frontend** |
| `tests/**` | subagente **tests** |
| `src/assistant/server.py`, `src/assistant/__init__.py`, README, `.env.example` | principal (después) |

Nadie edita archivos ajenos. Si necesitas algo de otro módulo, impórtalo según las firmas de abajo.

## config.py (existe)
```python
ROOT: Path                          # raíz del repo
class ConfigError(Exception)        # mensaje claro para el usuario; server lo imprime sin traceback
@dataclass(frozen=True) class Settings:
    openai_api_key: str; llm_model: str  # default "gpt-6-luna"
    mongodb_uri: str  # default "mongodb://127.0.0.1:27017"
    mongodb_db: str   # default "assistant"
    max_tokens: int   # 4000 (tope de tokens de salida por llamada al modelo)
    recursion_limit: int  # 25
    model_call_limit: int # 15 (llamadas al modelo por turno)
    memory_semantic: bool # False (MongoDB local no tiene Atlas Vector Search)
    enable_hitl_demo: bool # False
    @classmethod from_env() -> Settings
    def require_api_key() -> None   # ConfigError si falta
def read_system_prompt() -> str     # lee prompts/system.md
```

## memory.py (subagente memoria)
```python
STORE_COLLECTION = "memories"
def ping_mongo(uri: str, timeout_ms: int = 2000) -> pymongo.MongoClient
    # MongoClient(uri, serverSelectionTimeoutMS=timeout_ms); client.admin.command("ping")
    # si falla: raise ConfigError(f"No pude conectar a MongoDB en {uri}. Verifica que el servicio esté corriendo")
def verify_model(api_key: str, model: str) -> str
    # openai.OpenAI(api_key=api_key).models.list(); si model está → return model
    # si no: ConfigError(f"El modelo '{model}' no existe para tu cuenta. Modelos 'luna' disponibles: {ids o 'ninguno'}. Ajusta LLM_MODEL en .env")
    # key inválida (openai.AuthenticationError) → ConfigError("OPENAI_API_KEY inválida ...")
    # error de red → ConfigError("No pude contactar la API de OpenAI: ...")
def build_checkpointer(client, db_name: str) -> MongoDBSaver   # MongoDBSaver(client, db_name=db_name)
def build_store(client, db_name: str, semantic: bool = False) -> MongoDBStore
    # MongoDBStore(collection=client[db_name][STORE_COLLECTION]) ; semantic=True solo deja un TODO/log, nunca falla
def memory_namespace(user_id: str) -> tuple[str, str, str]  # ("user", user_id, "memories")
def save_memory(store, user_id: str, text: str) -> str      # key = uuid4 hex; value {"text": text, "created_at": iso}
def search_memories(store, user_id: str, query: str = "", limit: int = 10) -> list[str]
    # store.search(ns, limit=200) SIN query (no hay índice vectorial); filtrado en Python:
    # query vacía → los más recientes; si no, puntúa por palabras de query (minúsculas, sin acentos,
    # ignora palabras <3 letras) contenidas en text; si ninguna coincide devuelve los más recientes.
def startup_checks(settings: Settings) -> pymongo.MongoClient
    # orden: settings.require_api_key(); client = ping_mongo(...); verify_model(...); return client
```

## tools.py (subagente agente)
Herramientas en español, todas `@tool` de `langchain.tools`, con docstring clara (el modelo la lee).
```python
calculadora(expresion: str) -> str       # evaluación con ast (+ - * / // % **, paréntesis, math.sqrt/sin/cos/log/pi/e...), sin eval
fecha_hora(zona: str = "local") -> str   # fecha/hora actual ISO + día de la semana; zona IANA opcional (zoneinfo)
guardar_recuerdo(texto: str, runtime: ToolRuntime) -> str   # memory.save_memory(runtime.store, runtime.context.user_id, texto)
buscar_recuerdos(consulta: str, runtime: ToolRuntime) -> str # memory.search_memories(...) → lista con viñetas o "Sin recuerdos"
enviar_email_simulado(destinatario: str, asunto: str, cuerpo: str) -> str  # NO envía nada; ejemplo HITL
def web_search(query: str, settings: Settings) -> tuple[str, str]
    # 1) ChatOpenAI(model=settings.llm_model, api_key=..., use_responses_api=True, tags=["nostream"])
    #    .bind_tools([{"type": "web_search"}]).invoke(query) → (resp.text, "openai_web_search")
    #    (si .text vacío, trátalo como fallo)
    # 2) cualquier excepción → logging.warning con el motivo y DDGS().text(query, max_results=5) → (texto formateado
    #    título/url/resumen, "duckduckgo")
def make_buscar_web(settings, search_fn=web_search) -> BaseTool
    # tool "buscar_web(consulta: str)": devuelve f"[motor: {engine}]\n{texto}"
def make_investigador(model: BaseChatModel, buscar_web_tool: BaseTool) -> BaseTool
    # tool "investigador_profundo(tarea: str)": subagente = create_agent(model, [buscar_web_tool], system_prompt=<investigar con 3-5 búsquedas y devolver resumen con fuentes>)
    # invoke({"messages":[{"role":"user","content":tarea}]}) → result["messages"][-1].text
def build_tools(model, settings, search_fn=web_search) -> list[BaseTool]
    # [buscar_web, calculadora, fecha_hora, guardar_recuerdo, buscar_recuerdos, investigador_profundo]
    # + enviar_email_simulado si settings.enable_hitl_demo
```

## agent.py (subagente agente)
```python
@dataclass class Context: user_id: str = "anon"          # context_schema del agente; tools leen runtime.context.user_id
def make_model(settings) -> ChatOpenAI   # ChatOpenAI(model=settings.llm_model, api_key=settings.openai_api_key or None,
    #   use_responses_api=True, max_tokens=settings.max_tokens, streaming=True)
    # OBLIGATORIO use_responses_api=True: gpt-6-luna (docs oficiales) solo hace function calling en Chat Completions
    # con reasoning effort "none"; en Responses API soporta function calling + web_search hospedado.
    # Los tokens llegan como content blocks: usa token.text (no token.content) para extraer texto.
def build_agent(model, tools, settings, checkpointer=None, store=None)
    # create_agent(model, tools, system_prompt=read_system_prompt(), context_schema=Context,
    #   checkpointer=checkpointer, store=store, middleware=[
    #     ModelCallLimitMiddleware(run_limit=settings.model_call_limit, exit_behavior="end"),
    #     ToolErrorMiddleware(on_error=lambda exc, req: f"Error en la herramienta ({type(exc).__name__}): {exc}. Intenta otra cosa."),
    #     HumanInTheLoopMiddleware(interrupt_on={"enviar_email_simulado": True}),  # patrón HITL listo
    #   ])
def run_config(thread_id: str, settings) -> dict  # {"configurable": {"thread_id": thread_id}, "recursion_limit": settings.recursion_limit}
def stream_events(agent, payload, thread_id: str, user_id: str, settings) -> Iterator[dict]
    # payload: {"messages":[{"role":"user","content": "..."}]}  o  langgraph.types.Command(resume=...)
    # agent.stream(payload, config=run_config(...), context=Context(user_id=user_id),
    #              stream_mode=["messages", "updates"], version="v2")
    # chunk v2 = {"type": "messages"|"updates", "ns": tuple, "data": ...}
    # - solo chunks con ns == () (raíz); ignora subagentes/modelos internos
    # - "messages": (token, metadata); si metadata["langgraph_node"] == "model" y token.text → evento token
    # - "updates": dict nodo→update. "model" con AIMessage.tool_calls → tool_start por cada call;
    #   "tools" con ToolMessage → tool_end; clave "__interrupt__" → evento interrupt
    # - excepciones → evento error (mensaje legible) y termina; SIEMPRE cierra con done (si no hubo error)
def get_history(agent, thread_id: str, settings) -> list[dict]
    # agent.get_state(run_config(...)).values.get("messages", []) →
    # Human → {"role":"user","content":text}; AI con texto → {"role":"assistant","content":text};
    # AI con tool_calls → {"role":"tool","name":nombre} por cada call (para mostrar "usó X"); ToolMessage se omite
```

## Eventos SSE (formato exacto)
Cada evento: `data: <json>\n\n` (sin línea `event:`; el tipo va en el JSON). Un objeto JSON por evento:
```json
{"type": "token", "text": "Hola"}
{"type": "tool_start", "id": "call_1", "name": "buscar_web", "args": {"consulta": "..."}}
{"type": "tool_end", "id": "call_1", "name": "buscar_web", "output": "primeros 500 chars", "status": "success"|"error", "engine": "duckduckgo"|"openai_web_search"|null}
{"type": "interrupt", "id": "<interrupt id>", "action_requests": [{"name": "enviar_email_simulado", "args": {...}, "description": "..."}]}
{"type": "effort", "level": "bajo"|"medio"|"alto", "max_calls": 5, "reasoning": "low"}   // primero, solo en modo automático
{"type": "progress", "name": "buscar_web", "args": {"consulta": "..."}}                  // búsqueda interna del investigador profundo
{"type": "error", "message": "texto legible"}
{"type": "done", "thread_id": "abc"}
```
`engine` en tool_end: se extrae de la primera línea `[motor: X]` del output (null si no aplica).

## Endpoints (server.py, principal)
| Método | Ruta | Body / respuesta |
|---|---|---|
| GET | `/` | sirve `static/index.html` |
| POST | `/chat` | body `{"message": str, "thread_id": str, "user_id": str}` → `text/event-stream` con los eventos de arriba |
| POST | `/resume` | body `{"thread_id": str, "user_id": str, "decisions": [{"type": "approve"} \| {"type": "reject", "message": str}]}` → mismo stream SSE. Internamente `Command(resume={"decisions": decisions})` |
| GET | `/history/{thread_id}` | `{"thread_id": str, "messages": [{"role":"user"\|"assistant","content":str} \| {"role":"tool","name":str}]}` (vacío si no existe) |
| GET | `/health` | `{"ok": true, "model": str}` |

`server.create_app(agent=None) -> FastAPI`: si recibe `agent`, NO hace chequeos de arranque (para tests).
`server.app` se crea perezosamente (al pedirlo uvicorn); ahí corren `memory.startup_checks` y un `ConfigError` se imprime sin traceback y sale con código 1.

## Tests
- Sin gastar tokens: LLM falso (`langchain_core.language_models.fake_chat_models.GenericFakeChatModel` u otro;
  `create_agent` llama `model.bind_tools`, así que subclasea y haz que `bind_tools` devuelva `self`).
- Tests con MongoDB real: base `assistant_test` SIEMPRE (nunca `assistant`), fixture de sesión que hace
  `client.drop_database("assistant_test")` al final; se saltan (`pytest.skip`) si `ping_mongo` falla.
- web search se inyecta con `search_fn` falso; nunca llamar a OpenAI ni DuckDuckGo.
