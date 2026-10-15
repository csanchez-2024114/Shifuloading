# Agente 0

Asistente conversacional autónomo con LangGraph 1.2, el modelo `gpt-6-luna` de OpenAI, memoria en MongoDB local y una interfaz web de un solo HTML con streaming.

- **Agente principal**: un solo agente (`langchain.agents.create_agent`) que razona y usa herramientas en ciclo hasta resolver.
- **Herramientas**: `buscar_web` (web search hospedado de OpenAI, con DuckDuckGo como respaldo automático), `calculadora`, `fecha_hora`, `guardar_recuerdo`, `buscar_recuerdos`, `investigador_profundo` (subagente que hace varias búsquedas y resume).
- **Memoria**: corto plazo con `MongoDBSaver` (por `thread_id`) y largo plazo con `MongoDBStore` (por `user_id`, namespace `("user", user_id, "memories")`).
- **Límites**: `recursion_limit` 100 (red de seguridad), tope de llamadas al modelo por turno, tope de tokens de salida y errores de herramientas devueltos al agente para que pruebe otra vía.
- **Human-in-the-loop**: patrón listo con la herramienta de ejemplo `enviar_email_simulado` (no envía nada). Se activa con `ENABLE_HITL_DEMO=1`: la UI muestra Aprobar/Rechazar.
- **Personalidad**: edita [prompts/system.md](prompts/system.md). No hace falta tocar código ni reiniciar; se lee en cada mensaje. Los prompts internos y las descripciones de herramientas están en inglés; el agente responde en el idioma del usuario.

## Instalación

Requisitos: Python 3.11+, [uv](https://docs.astral.sh/uv/) y MongoDB corriendo como servicio local.

```powershell
uv venv .venv
uv pip install --python .venv -e ".[dev]"
copy .env.example .env   # y pon tu OPENAI_API_KEY
```

## Variables de entorno (`.env`)

| Variable | Default | Uso |
|---|---|---|
| `OPENAI_API_KEY` | (obligatoria) | clave de OpenAI |
| `LLM_MODEL` | `gpt-6-luna` | ID del modelo; se valida al arrancar con `models.list()` |
| `MONGODB_URI` | `mongodb://127.0.0.1:27017` | MongoDB local |
| `MONGODB_DB` | `assistant` | base de datos |
| `MAX_TOKENS` | `0` | tope de tokens de salida por llamada (incluye razonamiento interno); `0` = sin tope |
| `RECURSION_LIMIT` | `100` | pasos máximos del grafo por turno (cada ronda modelo→herramienta usa ~5 pasos por los middlewares; el tope real por turno es `MODEL_CALL_LIMIT`) |
| `MODEL_CALL_LIMIT` | `0` | `0` = **automático**: una llamada rápida clasifica cada mensaje (bajo/medio/alto) y fija el tope de llamadas al modelo (5/15/40) y el razonamiento de Luna (low/medium/high); `>0` = tope fijo |
| `MEMORY_SEMANTIC` | `0` | `1` = búsqueda semántica de recuerdos con Atlas Vector Search y embeddings `text-embedding-3-small`; con MongoDB local se ignora (log de aviso) y usa búsqueda por palabras |
| `ENABLE_HITL_DEMO` | `0` | activa la herramienta de ejemplo con aprobación humana |

### MongoDB Atlas (opcional)

Pon en `.env` la URI `mongodb+srv://usuario:password@cluster0.xxxxx.mongodb.net/` (Atlas → Connect → Drivers) y `MEMORY_SEMANTIC=1`. Al arrancar se crea solo el índice vectorial `vector_index` en la colección `memories` (puede tardar hasta un minuto la primera vez). Tu IP debe estar en Network Access. Los recuerdos guardados antes de activar la semántica no tienen embedding y no aparecen en búsquedas semánticas.

### Muchas herramientas con langgraph-bigtool (opcional, desactivado por defecto)

| Variable | Default | Uso |
|---|---|---|
| `USE_BIGTOOL` | `0` | `1` = usa el agente alterno de [`bigtool_agent.py`](src/assistant/bigtool_agent.py) en vez de `agent.py` |
| `BIGTOOL_DEMO_TOOLS` | `0` | `1` = agrega ~58 herramientas inofensivas de demostración (funciones de `math` y de texto); 95 en total |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | modelo de embeddings de OpenAI para el índice de herramientas |

Con [langgraph-bigtool](https://github.com/langchain-ai/langgraph-bigtool) el modelo no recibe todas las herramientas: solo ve `retrieve_tools`, la llama con una descripción de lo que necesita y recibe las 3 más parecidas de un índice semántico. **Conviene a partir de unas decenas de herramientas**; con las 6–7 actuales no aporta y suma una llamada extra.

Con bigtool el registro incluye siempre las 6 herramientas del agente más **31 herramientas extra** ([`extra_tools.py`](src/assistant/extra_tools.py)), todas sin efectos reales:

| Grupo | Herramientas |
|---|---|
| Conversiones | `convert_units` (longitud, masa, volumen, velocidad, área, datos, temperatura), `convert_currency` (tipo de cambio del BCE de hoy), `convert_timezone` |
| Fechas | `days_between_dates`, `add_days_to_date`, `day_of_week`, `age_from_birthdate`, `business_days_between` |
| Finanzas | `loan_payment`, `compound_interest`, `percentage_change`, `add_sales_tax` (IVA 16%), `split_bill` |
| Datos y salud | `describe_numbers`, `linear_regression`, `body_mass_index` |
| Mundo (solo lectura) | `geocode_place`, `distance_between_places`, `weather_forecast`, `wikipedia_summary` |
| Texto y utilidades | `word_frequency`, `extract_emails_and_urls`, `generate_password`, `generate_uuid`, `hash_text`, `base64_encode`, `base64_decode`, `format_json`, `validate_curp` |
| Azar | `roll_dice`, `random_choice` |

Las de "mundo" consultan APIs públicas sin clave (Open-Meteo, Frankfurter, Wikipedia): el nombre del lugar o tema que preguntes se envía a esos servicios. `generate_password` es para pruebas: la contraseña queda en el historial de la conversación.

Medido con tiktoken (solo los esquemas de herramientas por llamada al modelo):

| | Herramientas que ve el modelo | Tokens de esquemas por llamada |
|---|---|---|
| Agente normal | 7 | ~760 |
| Las 37 del registro sin bigtool (hipotético) | 37 | ~3,300 |
| Las 95 con demo sin bigtool (hipotético) | 95 | ~7,300 |
| Bigtool, antes de buscar | 1 (`retrieve_tools`) | ~60 (+80 de instrucciones) |
| Bigtool, tras encontrar 3 | 4 | ~240 |

Detalles:
- **Índice:** `InMemoryStore` con embeddings, no MongoDB (en local no hay búsqueda vectorial). Se crea al arrancar: ~1.1k tokens de embeddings con 37 herramientas, ~2.5k con 95, ~2 s.
- **Dos stores separados:** el índice de herramientas va al grafo; los recuerdos siguen en MongoDB y las herramientas de memoria los usan directamente. El historial sigue en `MongoDBSaver`.
- **Instalación desde git:** la versión de PyPI (0.0.3) no funciona con LangGraph 1.x; `pyproject.toml` fija el commit de `main` que lo corrige.
- **Limitaciones** (bigtool no soporta el middleware de LangChain):
  - sin aprobación humana, por eso el registro no incluye herramientas con efectos reales;
  - sin tope de llamadas por esfuerzo, el límite es `RECURSION_LIMIT` (el esfuerzo sí ajusta el razonamiento);
  - no hay herramientas siempre visibles: hasta la calculadora se busca primero.
- **Para agregar herramientas de una app:** usa la plantilla `@tool_spec` (guía en [docs/PLANTILLA_HERRAMIENTA.md](docs/PLANTILLA_HERRAMIENTA.md), ejemplo en [apps/crm_demo.py](src/assistant/apps/crm_demo.py)). Así se indexa una descripción rica y se declaran las pre-funciones (`requires`, con alternativas, y `auto` para encadenar solo). Súmalas a `build_registry` en `bigtool_agent.py`, sin argumentos inyectados (`ToolRuntime`); el usuario se lee con `get_runtime().context`.
- **CRM de ejemplo:** con `BIGTOOL_DEMO_TOOLS=1` se carga un CRM simulado en memoria (clientes y pedidos) para probar las pre-funciones, por ejemplo "crea un pedido de 2 monitores para ana@example.com".

### Observabilidad con LangSmith (opcional, desactivada por defecto)

| Variable | Default | Uso |
|---|---|---|
| `LANGSMITH_TRACING` | `false` | `true` activa el envío de trazas |
| `LANGSMITH_API_KEY` | (vacía) | tu clave de LangSmith (smith.langchain.com → Settings → API Keys) |
| `LANGSMITH_PROJECT` | `agente-0` | proyecto donde se agrupan las trazas (si no se define, LangSmith usa `default`) |
| `LANGSMITH_ENDPOINT` | (US) | solo cuentas EU: `https://eu.api.smith.langchain.com`, sin `/` al final |

No requiere código: `config.py` carga `.env` en el entorno y LangChain/LangGraph activan el tracer solos. Reinicia el servidor después de cambiarlas.

> **Importante:** con `LANGSMITH_TRACING=true`, cada conversación se **envía a la nube de LangSmith**: tus mensajes, las respuestas, los argumentos y resultados de las herramientas (búsquedas, cálculos) y los recuerdos guardados o consultados. No lo actives con datos que no quieras compartir con ese servicio.

Cada mensaje genera **una sola traza** con el agente principal y, anidado dentro de la herramienta `investigador_profundo`, el subagente investigador con su modelo y sus `buscar_web`. Esto funciona porque LangChain propaga el contexto de trazado con `contextvars` (automático en Python 3.11+). La clasificación de esfuerzo corre antes del agente y aparece como una traza aparte, pequeña.

## Correr

```powershell
.venv\Scripts\activate
uvicorn assistant.server:app --reload --host 127.0.0.1 --port 8000
```

Abre http://localhost:8000. Usa el mismo `user_id` en distintas conversaciones para que recuerde tus datos. Al recargar con el mismo `thread_id` recupera la conversación.

Tests (sin gastar tokens; los de MongoDB usan la base `assistant_test`, la borran al final y se saltan si Mongo no responde):

```powershell
.venv\Scripts\python -m pytest
```

## Si algo falla

- **"No pude conectar a MongoDB en …"**: el servicio no está corriendo o la URI es otra. En Windows: `Get-Service MongoDB` / `Start-Service MongoDB` (como administrador), o revisa `MONGODB_URI`.
- **"Falta OPENAI_API_KEY"**: crea `.env` en la raíz (copia `.env.example`) con tu clave.
- **"OPENAI_API_KEY inválida"**: la clave está mal o revocada.
- **"El modelo 'X' no existe para tu cuenta"**: el mensaje lista los modelos "luna" disponibles; ajusta `LLM_MODEL`.
- **Puerto 8000 ocupado**: `netstat -ano | findstr :8000` para ver el proceso, o corre con `--port 8001`.
- **La búsqueda web dice `[motor: duckduckgo]`**: el web search hospedado de OpenAI falló y se usó el respaldo; el log del servidor muestra el motivo.
