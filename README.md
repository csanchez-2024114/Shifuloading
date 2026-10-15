# Agente 0

Asistente conversacional autónomo con LangGraph 1.2, el modelo `gpt-6-luna` de OpenAI, memoria en MongoDB (local o Atlas, según `MONGODB_URI`) y una interfaz web de un solo HTML con streaming.

- **Agente principal**: un solo agente (`langchain.agents.create_agent`) que razona y usa herramientas en ciclo hasta resolver.
- **Herramientas**: `buscar_web` (web search hospedado de OpenAI, con DuckDuckGo como respaldo automático), `calculadora`, `fecha_hora`, `guardar_recuerdo`, `buscar_recuerdos`, `actualizar_recuerdo`, `investigador_profundo` (subagente que hace varias búsquedas y resume).
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
| `MONGODB_URI` | `mongodb://127.0.0.1:27017` | MongoDB que usa **el servidor** (historial y recuerdos). Puede ser local o Atlas (`mongodb+srv://…`); el servidor usa siempre la que esté en `.env`. Los tests no la usan (ver Correr) |
| `MONGODB_DB` | `assistant` | base de datos |
| `MAX_TOKENS` | `0` | tope de tokens de salida por llamada (incluye razonamiento interno); `0` = sin tope |
| `RECURSION_LIMIT` | `100` | pasos máximos del grafo por turno (cada ronda modelo→herramienta usa ~5 pasos por los middlewares; el tope real por turno es `MODEL_CALL_LIMIT`) |
| `MODEL_CALL_LIMIT` | `0` | `0` = **automático**: una llamada rápida clasifica cada mensaje (bajo/medio/alto) y fija el tope de llamadas al modelo (5/15/40) y el razonamiento de Luna (low/medium/high); `>0` = tope fijo |
| `MEMORY_SEMANTIC` | `0` | `1` = búsqueda semántica de recuerdos con Atlas Vector Search y embeddings `text-embedding-3-small`; con MongoDB local se ignora (log de aviso) y usa búsqueda por palabras |
| `MEMORY_MIN_SCORE` | `0.68` | puntuación mínima (0–1) para que un recuerdo cuente como relevante en la búsqueda semántica; calibrado, ver "MongoDB Atlas" |
| `ENABLE_HITL_DEMO` | `0` | activa la herramienta de ejemplo con aprobación humana |

### MongoDB Atlas (opcional)

Pon en `.env` la URI `mongodb+srv://usuario:password@cluster0.xxxxx.mongodb.net/` (Atlas → Connect → Drivers) y `MEMORY_SEMANTIC=1`. Al arrancar se crea solo el índice vectorial `vector_index` en la colección `memories` (puede tardar hasta un minuto la primera vez). Tu IP debe estar en Network Access.

**Umbral de relevancia (`MEMORY_MIN_SCORE`, default `0.68`).** La búsqueda vectorial siempre devuelve "el más parecido", aunque no tenga nada que ver. Por eso se descartan los resultados con puntuación menor al umbral, y `buscar_recuerdos` responde "No hay recuerdos relevantes para esto" en vez del menos malo.
- **Escala:** Atlas con coseno puntúa entre 0 y 1, calculado como (1 + coseno)/2.
- **No se aplica a:** la búsqueda vacía (los más recientes), el panel 🧠 ni la búsqueda por palabras del Mongo local.
- **Cómo se eligió el 0.68:** se midió con `text-embedding-3-small` sobre 10 recuerdos de ejemplo, 14 consultas relevantes y 14 irrelevantes. Con 0.68 acertó 23 de 28. Los dos grupos se solapan, así que ningún valor separa perfecto:
  - quedan fuera dos relevantes, "ciudad donde vive" (0.673) y "pasatiempos" (0.617);
  - pasan tres irrelevantes cercanas: "nombre de mi gato" encuentra al perro (0.730), "fecha de nacimiento del usuario" el cumpleaños de la hermana (0.719) y "religión del usuario" el nombre (0.712).
  - Para esos casos, el prompt le pide al agente no deducir datos de recuerdos parecidos.
- **Si lo cambias:** más alto da más "no tengo ese dato"; más bajo deja pasar más recuerdos sin relación.

**Recuerdos guardados antes de activar la semántica.** No tienen embedding y no aparecen en la búsqueda semántica, aunque sí en el panel 🧠. Para indexarlos usa el script de migración, que lee `MONGODB_URI` y `MONGODB_DB` de `.env`:

```powershell
.venv\Scripts\python scripts\migrate_memories.py           # dry-run: cuántos recuerdos, de cuántos usuarios y costo estimado; no escribe
.venv\Scripts\python scripts\migrate_memories.py --apply   # indexa
```

- **Qué cambia:** solo agrega `embedding` y `namespace_prefix` a los recuerdos que no tienen vector; no modifica ningún otro campo ni fecha.
- **Se puede repetir:** una segunda ejecución no hace nada.
- **Costo:** unos 12 tokens de embeddings por recuerdo.
- **Otra base:** se elige con `--db`.

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

### Memoria larga y control de alucinaciones (opcional, todo desactivado por defecto)

| Variable | Default | Uso |
|---|---|---|
| `MEMORY_SUMMARIZE` | `0` | `1` = cuando la conversación pasa `SUMMARY_TRIGGER_TOKENS`, los mensajes viejos se reemplazan por un resumen (`SummarizationMiddleware` de LangChain) |
| `SUMMARY_TRIGGER_TOKENS` | `12000` | umbral en tokens aproximados de la conversación (sin contar el system prompt) |
| `SUMMARY_KEEP_MESSAGES` | `20` | últimos mensajes que se conservan sin resumir |
| `MEMORY_VERIFY` | `0` | `1` = antes de guardar un recuerdo, una llamada barata comprueba que el usuario lo dijo; si no, no se guarda y el agente lo avisa |
| `ANSWER_VERIFY` | `0` | `1` = si el turno usó `buscar_web` o `investigador_profundo`, una llamada barata contrasta la respuesta con lo recuperado y la corrige si hace falta |

Siempre activo, sin costo extra de llamadas:
- **Prompt anti-alucinación** ([prompts/system.md](prompts/system.md)):
  - separa lo que viene de herramientas, de recuerdos y del conocimiento propio;
  - dice "no lo sé" antes que inventar;
  - no afirma datos de actualidad sin buscar;
  - cita `[título](url)` solo con URLs de los resultados;
  - si un recuerdo contradice lo que dices ahora, pregunta;
  - responde siempre en el idioma del usuario.
- **Recuerdos con procedencia:** cada recuerdo guarda `text`, `created_at`, `thread_id` de origen, `evidence` (tu frase textual) y `confidence`:
  - `verified`: lo confirmó `MEMORY_VERIFY`;
  - `quoted`: la cita aparece literal en lo que escribiste;
  - `unverified`: sin evidencia.
  
  Si la cita que propone el modelo no aparece literal en tus mensajes, `evidence` queda vacío. Los recuerdos guardados antes de este cambio siguen funcionando: se muestran como `unverified`, sin evidencia.
- **Actualizar recuerdos:** `buscar_recuerdos` muestra el id de cada recuerdo y `actualizar_recuerdo(id, texto, evidencia)` reemplaza uno existente cuando confirmas un cambio (p. ej. café de olla → té verde), en vez de dejar dos contradictorios. Pasa por la misma verificación que guardar (`MEMORY_VERIFY`), solo toca recuerdos de tu `user_id` (un id ajeno se rechaza con el mismo mensaje que uno inexistente) y guarda el valor anterior en `previous_text` y la fecha en `updated_at` para auditar o deshacer. El agente no puede borrar recuerdos: borrar es solo desde la interfaz.
- **Gestión de recuerdos:** el botón 🧠 de la interfaz lista los recuerdos del ID de usuario actual, con fecha, confianza, evidencia y, si se actualizó, el valor anterior, y permite borrarlos. API: `GET /memories/{user_id}` y `DELETE /memories/{user_id}/{key}`.

Detalles:
- **Qué toma el resumen:** pide conservar literal nombres, cifras, fechas, decisiones y preferencias, y fusionar el resumen anterior. Se desactivó el recorte previo de la librería (`trim_tokens_to_summarize`), que con su valor por defecto descartaba el resumen anterior en el segundo resumen. El texto del resumen no llega a la UI como tokens; se ve el aviso "🗜️ Conversación anterior resumida".
- **Qué cuenta como evidencia:** la verificación de recuerdos solo usa mensajes que escribió el usuario. **Nunca usa el resumen**, que es texto generado por el modelo.
- **Citas revisadas en código** ([citations.py](src/assistant/citations.py)), no solo con el prompt del verificador. Dos URLs son la misma si coinciden dominio y ruta: no cuentan `?utm_source=openai` y otros parámetros, `www.`, el fragmento ni la barra final. Reglas:
  - una cita respaldada nunca se pierde: si la corrección la quita, se vuelve a poner en una línea "Fuentes:" al final;
  - una cita cuya URL no está en lo que devolvió la búsqueda se quita (queda su texto);
  - una corrección que trae cifras que no están ni en la respuesta ni en la evidencia se descarta y se conserva el original, con un aviso;
  - si el verificador "corrige" sin cambiar nada, no se marca como corrección.
- **Las correcciones se ven:** si `ANSWER_VERIFY` corrige una respuesta, la interfaz muestra la versión corregida con un aviso y un botón "ver original". El original queda guardado en el historial, así que también se ve al recargar.

**Costo aproximado** (gpt-6-luna; medido en la prueba real descrita abajo):

| Mejora | Cuándo cuesta | Costo medido |
|---|---|---|
| Prompt anti-alucinación | cada llamada al modelo | +~340 tokens de entrada (el system prompt pasó de ~250 a ~580) |
| `MEMORY_SUMMARIZE` | cada vez que se pasa el umbral | 1 llamada; entrada ≈ lo que se resume, salida ~700 tokens. Con conversaciones largas ahorra, porque deja de reenviar la historia completa en cada llamada |
| `MEMORY_VERIFY` | cada recuerdo que se guarda | 1 llamada de ~200 de entrada + ~30 de salida |
| `ANSWER_VERIFY` | solo turnos con búsqueda web o investigador | 1 llamada de ~360 de entrada + ~5 de salida si todo está bien (la búsqueda misma cuesta ~7k); si corrige, se suma la salida de la respuesta corregida. Con DuckDuckGo o el investigador la evidencia es más larga (tope ~3k tokens) |

**Limitaciones (honestas):**
- Las alucinaciones **se reducen, no se eliminan**. El prompt y las verificaciones las hacen menos probables, pero el modelo y el verificador también pueden equivocarse. `ANSWER_VERIFY` solo revisa los turnos con búsqueda web y solo contra lo recuperado.
- **El resumen puede deformar contenido:** puede omitir o cambiar un detalle. Por eso los hechos clave del usuario se guardan aparte como recuerdos (`guardar_recuerdo`), que no dependen del resumen.
- Con `MEMORY_SUMMARIZE=1`, al recargar un hilo resumido solo se ven el aviso de resumen y los mensajes conservados: los viejos ya no están en el estado de la conversación.
- `MEMORY_VERIFY` puede rechazar algo que sí dijiste con otras palabras. En ese caso el agente te avisa y puedes repetirlo explícitamente.
- **No hay autenticación:** el `user_id` es texto libre, y quien escriba tu ID en la interfaz ve y borra tus recuerdos. La app está pensada para uso local.

**Con `USE_BIGTOOL=1`:**
- Sí aplican los recuerdos con procedencia, `actualizar_recuerdo`, `MEMORY_VERIFY` y el prompt.
- **`MEMORY_SUMMARIZE` y `ANSWER_VERIFY` no aplican**, porque langgraph-bigtool no soporta middleware.
- Propuesta para implementarlo a mano (no hecha):
  1. Construir el grafo de bigtool sin compilar (`create_bigtool_agent(...)` devuelve un `StateGraph`).
  2. Agregar un nodo `summarize` antes de `agent`. Ese nodo cuenta tokens con `count_tokens_approximately` y, si se pasa del umbral, llama al modelo con el mismo `SUMMARY_PROMPT` y devuelve `RemoveMessage(REMOVE_ALL_MESSAGES)` + el resumen + los últimos N mensajes, sin separar una llamada a herramienta de su respuesta.
  3. Para `ANSWER_VERIFY`, un nodo final antes de `END` con la lógica de `AnswerVerifier.after_agent`.
  
  Una alternativa sin persistir nada es recortar en `PromptedModel` con `trim_messages`, pero así se pierde lo viejo en vez de resumirlo.

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

Tests (sin gastar tokens). **pytest siempre usa tu MongoDB local** (`mongodb://127.0.0.1:27017`, base `assistant_test`), aunque `.env` apunte a Atlas: `tests/conftest.py` fuerza esa URI. Borran la base al final y se saltan si el Mongo local no responde:

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
