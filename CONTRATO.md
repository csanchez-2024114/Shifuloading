# CONTRATO

Fuente de verdad para todos los subagentes. Si tu código no coincide con esto, este documento manda.
Versiones instaladas en `.venv`: langgraph 1.2.15, langchain 1.4.6, langchain-core 1.6.10, langchain-openai 1.7.2,
langgraph-checkpoint-mongodb 0.5.1, langgraph-store-mongodb 0.4.0, pymongo 4.19, fastapi 0.143, ddgs 9.16.
Python: `.venv\Scripts\python`. Paquete instalado editable (`src/assistant`), importa como `assistant.*`.

**Todo es SÍNCRONO** (MongoDBSaver es sync). Usa `agent.stream(...)` / `agent.invoke(...)`, nunca `astream`.
Sin Docker. El servidor usa la `MONGODB_URI` de `.env` (hoy Atlas; default local `mongodb://127.0.0.1:27017`). pytest usa SIEMPRE el MongoDB local (conftest fuerza la URI). No arranques ni instales Mongo.

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
    max_tokens: int   # 8000 (tope de tokens de salida por llamada, razonamiento incluido; 0 = sin tope)
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
Herramientas con nombre en inglés (antes en español: `agent.OLD_TOOL_NAMES` guarda el mapa), todas `@tool` de `langchain.tools`. Los hilos viejos siguen funcionando: `_nombres_antiguos` reescribe los nombres antiguos del historial antes de cada llamada al modelo, bigtool usa `RegistroTolerante` (ids antiguos → actuales; ids que ya no existen se ignoran) y la UI traduce nombres viejos y nuevos a la misma etiqueta. Lo que lee el modelo va en inglés: descripciones, nombres y descripciones de parámetros y los mensajes que devuelven ("Memory saved.", "No relevant memories for this query.", "Tool error (...)"…). La UI traduce esos mensajes al mostrarlos (`toolOutputLabel` en index.html); `tests/test_idioma.py` falla si se cuela español.
```python
calculator(expression: str) -> str       # evaluación con ast (+ - * / // % **, paréntesis, math.sqrt/sin/cos/log/pi/e...), sin eval
current_datetime(time_zone: str = "local") -> str   # fecha/hora actual ISO + día de la semana; zona IANA opcional (zoneinfo)
save_memory(text: str, runtime: ToolRuntime, evidence="") -> str   # memory.remember → "Memory saved." o "Not saved: ..."
search_memories(query: str, runtime: ToolRuntime) -> str # memory.recall → "- [id <key>] texto" por línea, NO_RELEVANT_MSG o NO_MEMORIES_MSG
update_memory(id: str, text: str, runtime, evidence="") -> str  # memory.revise: solo el user_id del contexto, misma verificación que guardar; previous_text + updated_at
send_simulated_email(recipient: str, subject: str, body: str) -> str  # NO envía nada; ejemplo HITL
check_python_syntax(code: str) -> str    # solo ast.parse (no ejecuta ni importa): SYNTAX_OK_MSG o "SyntaxError at line L, column C: ..."
def web_search(query: str, settings: Settings) -> tuple[str, str]
    # 1) ChatOpenAI(model=settings.llm_model, api_key=..., use_responses_api=True, tags=["nostream"])
    #    .bind_tools([{"type": "web_search"}]).invoke(query) → (resp.text, "openai_web_search")
    #    (si .text vacío, trátalo como fallo)
    # 2) cualquier excepción → logging.warning con el motivo y DDGS().text(query, max_results=5) → (texto formateado
    #    título/url/resumen, "duckduckgo")
def make_buscar_web(settings, search_fn=web_search) -> BaseTool
    # tool "web_search(query: str)": devuelve f"[engine: {engine}]\n{texto}"; si no es la primera web_search de la
    # misma respuesta del modelo, no busca y devuelve ONE_SEARCH_MSG ("Not run: one search per step…")
def make_investigador(model: BaseChatModel, buscar_web_tool: BaseTool) -> BaseTool
    # tool "deep_research(task: str)": subagente = create_agent(model, [buscar_web_tool], system_prompt=<investigar con 3-5 búsquedas y devolver resumen con fuentes>)
    # invoke({"messages":[{"role":"user","content":tarea}]}) → result["messages"][-1].text
def build_tools(model, settings, search_fn=web_search) -> list[BaseTool]
    # [web_search, calculator, current_datetime, check_python_syntax, save_memory, search_memories, update_memory,
    #  deep_research]  (deep_research pide confirmación salvo petición explícita: research_needs_confirmation)
    # + send_simulated_email si settings.enable_hitl_demo
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
    #     HumanInTheLoopMiddleware(interrupt_on={"send_simulated_email": True}),  # patrón HITL listo
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
    #   "tools"/"select_tools" y el middleware HITL (rechazo de la tarjeta) con ToolMessage → tool_end;
    #   clave "__interrupt__" → evento interrupt
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
{"type": "tool_start", "id": "call_1", "name": "web_search", "args": {"query": "..."}}
{"type": "tool_end", "id": "call_1", "name": "web_search", "output": "primeros 500 chars", "status": "success"|"error"|"skipped", "engine": "duckduckgo"|"openai_web_search"|null}
# "skipped": la herramienta NO se ejecutó (output "Not run: …", "Cancelled: …" o rechazo del usuario). La UI no pone "✓"
{"type": "interrupt", "id": "<interrupt id>", "action_requests": [{"name": "send_simulated_email", "args": {...}, "description": "..."}]}
{"type": "effort", "level": "bajo"|"medio"|"alto", "max_calls": 5, "reasoning": "low", "source": "auto"|"regla"|"manual"}
// primero, solo con MODEL_CALL_LIMIT=0. source: "auto" = clasificador, "regla" = mensaje corto sin señales (sin
// clasificador, esfuerzo bajo), "manual" = selector de Ajustes (campo "effort" del body de /chat)
{"type": "progress", "name": "web_search", "args": {"query": "..."}}                     // búsqueda interna del investigador profundo
{"type": "phase", "phase": "verifying"}                                                  // ANSWER_VERIFY empieza a verificar (la UI muestra "verificando…")
{"type": "summarized"}                                                                    // MEMORY_SUMMARIZE: se resumió la conversación vieja
{"type": "verify", "status": "ok", "notes": [], "tokens": 812}                           // ANSWER_VERIFY, solo si el turno usó web_search/investigador
{"type": "verify", "status": "corrected"|"kept_original", "text": "texto final", "original": "respuesta original", "notes": ["..."], "tokens": 950}
{"type": "no_tools"}                                                                    // el historial ya pesa más que TURN_TOKEN_CAP: el turno va sin herramientas (la UI muestra "⚠️ Sin herramientas…")
{"type": "verify", "status": "unverified", "notes": ["No verificada: este mensaje llegó a su tope de tokens (TURN_TOKEN_CAP)"], "tokens": 0}  // el turno ya aterrizó o pasó el tope: no se verifica
// "text"/"original" solo si el texto cambió. kept_original = se descartó la corrección del verificador (p. ej. traía cifras
// que no están en la evidencia); puede venir con citas inventadas quitadas. Reglas de citas en citations.py (en código).
{"type": "error", "message": "texto legible"}
{"type": "done", "thread_id": "abc"}
```
Avisos del sistema al usuario: texto plano, sin marcadores de markdown (la interfaz mostraba los `_` de la cursiva).

Respuesta cortada por MAX_TOKENS: llega como un `token` más al final, con el aviso "⚠️ La respuesta se cortó por el
límite de longitud (MAX_TOKENS). Escribe «continúa» y sigo justo donde me quedé, sin repetir lo anterior." (también
queda en el historial, con `additional_kwargs.cut = true`). No hay evento nuevo.

Tope por mensaje (TURN_TOKEN_CAP): al 80% la siguiente llamada va sin herramientas (aterrizaje suave: respuesta normal,
sin aviso propio). Si el historial del hilo ya pesa más que el tope, todo el mensaje va sin herramientas. El tope frena
las llamadas extra pero siempre permite una respuesta final; esa respuesta no pasa por ANSWER_VERIFY (evento `verify`
con `status: "unverified"`, y en el historial `verify: {"status": "unverified", "notes": [...]}` sin `original`). Solo si se cruza el tope sin aterrizar y el modelo pide más herramientas llega un `token` final con
"⚠️ Detuve este mensaje: superó el tope de N tokens por mensaje (TURN_TOKEN_CAP)…" (N con punto de miles: 45.000)
seguido de `done`. Las herramientas que ya corrían terminan y guardan su resultado; las que no habían empezado quedan
respondidas con "Cancelled: …" en el historial, para que el hilo siga usable. No hay evento nuevo.

Confirmación de deep_research: evento `interrupt` con `action_requests: [{"name": "deep_research", "args": {"task": …},
"description": "Esto tardará unos 1-2 minutos y consume bastante más; ¿sigo?"}]`. Se reanuda con `/resume` y
`decisions: [{"type": "approve"}]` o `[{"type": "reject", "message": "The user declined this action. …"}]` (el mensaje
de rechazo lo lee el modelo: en inglés). No se pide si el mensaje del usuario pide investigar.

Interfaz: "Nueva conversación" nunca se deshabilita. Con un turno en curso, el clic queda en cola (borde discontinuo,
"Nueva al terminar…"; un segundo clic cancela) y se ejecuta al terminar; con una aprobación pendiente se ejecuta al
momento. El id del hilo actual se muestra siempre bajo el selector (`#threadid`).

Keep-alive: durante silencios de `SSE_PING_SECONDS` (15 s por defecto) el servidor envía la línea de comentario SSE
`: ping` seguida de una línea vacía. No es un evento (no tiene `data:`); los clientes deben ignorar las líneas que
empiezan con `:`.
`engine` en tool_end: se extrae de la primera línea `[engine: X]` del output (null si no aplica).

## Endpoints (server.py, principal)
| Método | Ruta | Body / respuesta |
|---|---|---|
| GET | `/` | sirve `static/index.html` |
| POST | `/chat` | body `{"message": str, "thread_id": str, "user_id": str, "effort"?: "bajo"\|"medio"\|"alto"\|null}` → `text/event-stream` con los eventos de arriba. `effort` (selector de la UI) manda sobre el clasificador; null o ausente = automático |
| POST | `/resume` | body `{"thread_id": str, "user_id": str, "decisions": [{"type": "approve"} \| {"type": "reject", "message": str}]}` → mismo stream SSE. Internamente `Command(resume={"decisions": decisions})` |
| GET | `/history/{thread_id}` | `{"thread_id": str, "messages": [{"role":"user"\|"assistant","content":str,"original"?:str,"verify"?:{"status":str,"notes":[str]},"no_tools"?:true} \| {"role":"tool","name":str,"status"?:"skipped"\|"error"} \| {"role":"summary"}]}` (vacío si no existe; `original` = respuesta antes de ANSWER_VERIFY; `verify.status` "unverified" = no se verificó por el tope, sin `original`; `no_tools` = respondió sin herramientas porque el historial superaba el tope; `status` solo si la herramienta no se ejecutó o falló) |
| GET | `/memories/{user_id}` | `{"user_id": str, "memories": [{"key","text","created_at","thread_id","evidence","confidence","previous_text","updated_at"}]}` (más recientes primero; 503 sin store) |
| DELETE | `/memories/{user_id}/{key}` | `{"deleted": key}`; 404 si no existe en el namespace de ese usuario |
| GET | `/health` | `{"ok": true, "model": str}` |

`server.create_app(agent=None) -> FastAPI`: si recibe `agent`, NO hace chequeos de arranque (para tests).
`server.app` se crea perezosamente (al pedirlo uvicorn); ahí corren `memory.startup_checks` y un `ConfigError` se imprime sin traceback y sale con código 1.

## Tests
- Sin gastar tokens: LLM falso (`langchain_core.language_models.fake_chat_models.GenericFakeChatModel` u otro;
  `create_agent` llama `model.bind_tools`, así que subclasea y haz que `bind_tools` devuelva `self`).
- Tests con MongoDB real: base `assistant_test` SIEMPRE (nunca `assistant`), fixture de sesión que hace
  `client.drop_database("assistant_test")` al final; se saltan (`pytest.skip`) si `ping_mongo` falla.
- web search se inyecta con `search_fn` falso; nunca llamar a OpenAI ni DuckDuckGo.
