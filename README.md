# Agente 0

Asistente conversacional autónomo con LangGraph 1.2, el modelo `gpt-6-luna` de OpenAI, memoria en MongoDB local y una interfaz web de un solo HTML con streaming.

- **Agente principal**: un solo agente (`langchain.agents.create_agent`) que razona y usa herramientas en ciclo hasta resolver.
- **Herramientas**: `buscar_web` (web search hospedado de OpenAI, con DuckDuckGo como respaldo automático), `calculadora`, `fecha_hora`, `guardar_recuerdo`, `buscar_recuerdos`, `investigador_profundo` (subagente que hace varias búsquedas y resume).
- **Memoria**: corto plazo con `MongoDBSaver` (por `thread_id`) y largo plazo con `MongoDBStore` (por `user_id`, namespace `("user", user_id, "memories")`).
- **Límites**: `recursion_limit` 100 (red de seguridad), tope de llamadas al modelo por turno, tope de tokens de salida y errores de herramientas devueltos al agente para que pruebe otra vía.
- **Human-in-the-loop**: patrón listo con la herramienta de ejemplo `enviar_email_simulado` (no envía nada). Se activa con `ENABLE_HITL_DEMO=1`: la UI muestra Aprobar/Rechazar.
- **Personalidad**: edita [prompts/system.md](prompts/system.md). No hace falta tocar código ni reiniciar; se lee en cada mensaje.

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
