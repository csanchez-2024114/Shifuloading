# Shifu V3 — Flujo Completo

Documentación técnica del pipeline completo desde la petición HTTP hasta la respuesta final.
**Última actualización:** 2026-05-20

---

## 1. Endpoints disponibles

### Endpoints del agente

| Endpoint | Comportamiento |
|---|---|
| `POST /v3/agent/shifu/chat` | Espera respuesta completa (JSON) |
| `POST /v3/agent/shifu/chat/stream` | Streaming token a token via SSE |

**Payload de entrada:**
```json
{
  "user_input": "quiero un reporte diario de mis ventas en Sheets",
  "conversation_id": "uuid-de-la-conversacion",
  "model": "gpt-4o-mini"
}
```

**Payload de salida (`/chat`):**
```json
{
  "status": "success",
  "conversation_id": "...",
  "final_answer_md": "Texto de la respuesta (markdown)",
  "final_answer": "Texto de la respuesta (markdown)",
  "reasoning": "Razonamiento interno del agente (opcional)",
  "accion": { "tipo": "connect_integration", "provider": "gmail" },
  "user_choices": null,
  "system_errors": null,
  "intent_analysis": { "intent_type": "crear_workflow", "confidence": 0.87, ... },
  "usage": { "input_tokens": 1200, "output_tokens": 340, "total_tokens": 1540 }
}
```

### Endpoints REST de workflows

| Endpoint | Método | Descripción |
|---|---|---|
| `/v3/agent/shifu/workflows` | GET | Lista todos los workflows del usuario |
| `/v3/agent/shifu/workflows/{id}` | GET | Obtiene un workflow con sus pasos |
| `/v3/agent/shifu/workflows/{id}` | DELETE | Elimina permanentemente (`?confirm=true`) |
| `/v3/agent/shifu/workflows/{id}/run` | POST | Dispara ejecución manual |
| `/v3/agent/shifu/workflows/{id}/runs` | GET | Lista runs de ejecución |
| `/v3/agent/shifu/workflows/{id}/analytics` | GET | Métricas brutas por run |
| `/v3/agent/shifu/workflows/{id}/analytics/cards` | GET | Cards para dashboard frontend |
| `/v3/agent/shifu/workflows/dashboard` | GET | Resumen analítico de todos los workflows |

### Otros endpoints del router

| Endpoint | Método | Descripción |
|---|---|---|
| `/v3/agent/shifu/conversations` | GET | Lista conversaciones del usuario |
| `/v3/agent/shifu/history/{conv_id}` | GET | Mensajes de una conversación |
| `/v3/agent/shifu/preferences` | GET/POST | Preferencias del usuario |

---

## 2. Diagrama general del grafo (LangGraph)

```
HTTP Request (JWT validado)
        │
        ▼
  shifu_graph.ainvoke() / .astream_events()
        │
        ▼
┌───────────────────────────────────────────────────────────────────────┐
│                         GRAFO LANGGRAPH                               │
│                                                                       │
│  START                                                                │
│    │                                                                  │
│    ▼                                                                  │
│  intent_analyzer_node  ← LLM rápido, clasifica ANTES de cargar nada  │
│    │                    También deriva workflow_phase (sin LLM)       │
│    │                                                                  │
│    ├─ needs_clarification=True ──► clarification_responder ─────────┐ │
│    │                               (devuelve UNA pregunta)           │ │
│    │                                                                 ▼ │
│    └─ needs_clarification=False ──► context_loader_node       memory_saver │
│                                       │                              │ │
│                                       ▼                              │ │
│                                  agent_node  ← LLM con tools         │ │
│                                       │                              │ │
│                        ┌─────────────┴──────────────┐               │ │
│                        │ ¿hay tool_calls?            │               │ │
│                       SÍ                            NO               │ │
│                        │                             │               │ │
│                        ▼                             ▼               │ │
│                 tool_executor_node          markdown_formatter_node   │ │
│                        │                             │               │ │
│                        └──────────────┬──────────────┘               │ │
│                                       │                              │ │
│                                  agent_node                          │ │
│                                 (loop hasta                          │ │
│                                  sin tools)                          │ │
│                                       │                              │ │
│                                  markdown_formatter_node             │ │
│                                       │                              │ │
│                                  memory_saver_node ─────────────────►│ │
│                                       │                               │
│                                      END                              │
└───────────────────────────────────────────────────────────────────────┘
        │
        ▼
  Extrae result["messages"][-1].content
  Separa en answer + reasoning (marcador `{}`)
  Devuelve JSONResponse / StreamingResponse (SSE)
```

**Límites de seguridad:**
- `recursion_limit: 40` — máximo de pasos en el grafo
- `_MAX_TOOL_CALL_ROUNDS: 25` — fuerza salida sin tools si supera este número (13-step workflows necesitan 18+ rondas)
- `_MAX_CONSECUTIVE_TOOL_ERRORS: 2` — si el mismo tool falla 2 veces seguidas, fuerza respuesta final

---

## 3. Nodo: `intent_analyzer_node`

**Archivo:** [app/agents/shifu_v3/nodes.py](../../../agents/shifu_v3/nodes.py)

Corre un LLM ligero (`gpt-4o-mini`, temp=0) **antes** de cargar contexto o tools.
Clasifica la intención, enriquece el mensaje, y deriva la fase del workflow sin LLM.

### Intenciones posibles

| intent_type | Cuándo aplica |
|---|---|
| `crear_workflow` | Usuario quiere automatizar algo nuevo |
| `editar_workflow` | Quiere modificar un flujo existente |
| `ejecutar_workflow` | Quiere correr un flujo ya creado |
| `eliminar_workflow` | Quiere borrar o pausar un flujo |
| `consultar_estado` | Pregunta qué flujos tiene o cómo van |
| `pregunta_capacidad` | "¿Puedes hacer X?" |
| `accion_directa` | Acción inmediata one-shot (NOT workflow): mostrar emails ahora, crear doc ahora |
| `aprobar_plan` | Usuario aprueba la propuesta de Shifu (ESTRICTO: requiere 4 condiciones) |
| `ajustar_plan` | Usuario quiere cambiar algo del plan (cambia el paso 2, agrega notificaciones) |
| `responder_pregunta` | Usuario responde una pregunta directa de Shifu |
| `unclear` | No se puede inferir nada concreto |

### Regla estricta `aprobar_plan` — las 4 deben cumplirse

```
a) El último mensaje de Shifu contiene lista numerada (1. 2. 3. con descripciones)
b) El último mensaje de Shifu termina con pregunta de aprobación ("¿Te parece bien?", etc.)
c) El mensaje actual del usuario es una palabra de aprobación clara:
   sí/si/yes/ok/dale/perfecto/hazlo/crea/adelante/listo/va/genial/claro/de acuerdo/vamos/bueno
d) El mensaje actual NO contiene signo de interrogación
```

### Output al estado

```python
{
  "intent_analysis": {
    "intent_type": "crear_workflow",
    "confidence": 0.82,
    "is_followup": True,
    "conversation_phase": "idle|proposing|building|confirming",
    "entities": { "integration": "gmail", "frequency": "diario", "goal": "..." }
  },
  "enriched_message": "versión técnica del pedido (o None)",
  "agent_strategy": "Llama consultar_herramientas_disponibles para Gmail...",
  "needs_clarification": False,
  "clarification_question": None,
  "workflow_phase": "idle|phase1_collecting|phase1_proposed|phase2_building|phase2_done"
}
```

### `_derive_workflow_phase()` — detector de fase sin LLM

```
Archivo: app/agents/shifu_v3/nodes.py (línea ~1604)

Algoritmo pattern-based (sin LLM, no puede alucinarse):
1. phase2_done:    "confirmado" + "workflow/automatización" en último assistant msg
                   O "¿lo activo" / "programar" en último assistant msg
2. phase2_building: "paso agregado" / "workflow creado" / "workflow_id" en any assistant msg
                    O usuario aprueba (_APPROVAL_TOKENS) + último assistant tiene plan numerado + _PLAN_SIGNALS
3. phase1_proposed: último assistant tiene plan numerado (1. y 2.) + pregunta de aprobación
4. phase1_collecting: cualquier keyword de workflow en cualquier assistant msg
5. idle:           ninguno de los anteriores
```

**Constantes:**
```python
_APPROVAL_TOKENS = frozenset({
    "sí", "si", "yes", "ok", "dale", "perfecto", "hazlo", "crea", "adelante",
    "listo", "va", "genial", "proceed", "go", "go ahead", "claro", "exacto",
    "de acuerdo", "confirmado", "confirma", "bueno", "bien", "vamos", "por favor",
})

_PLAN_SIGNALS = (
    "¿te parece bien", "¿quieres ajustar", "¿lo activo",
    "¿lo creamos", "¿empezamos", "¿procedemos", "¿lo construyo",
)
```

### Routing

```
needs_clarification = True  →  clarification_responder
needs_clarification = False →  context_loader (usa enriched_message como input al agente)
```

---

## 4. Nodo: `context_loader_node`

**Archivo:** [app/agents/shifu_v3/nodes.py](../../../agents/shifu_v3/nodes.py)

Carga todo el contexto del usuario en paralelo (6 operaciones async simultáneas):

```python
asyncio.gather(
  load_context()           ─ historial + resumen de conversación
  load_preferences()       ─ idioma, tono, nivel técnico, industria, profesión
  load_catalog_apps()      ─ todas las integraciones disponibles
  load_user_integrations() ─ cuentas conectadas del usuario (OAuth)
  search_global_memory()   ─ memoria a largo plazo (RAG sobre sesiones previas)
  load_user_entities()     ─ IDs conocidos: Sheets, Docs, Slides, Workflows, Drive
)
```

### Carga de tools

```
get_all_bigtools()     →  lista de BigTool desde el registry
_bigtool_to_lc()       →  convierte a BaseTool de LangChain (wrapper async si sync)
_build_query_tools()   →  tools de consulta + mostrar_opciones + solicitar_conexion_integracion
_build_workflow_tools() → retorna [] (workflow tools vienen de BigTools registry)

Deduplicación: dict keyed by tool.name, last wins
  Priority: query_tools → workflow_tools → lc_bigtools (BigTools override para mismo nombre)
```

### Comprobación de perfil de usuario

Si el usuario tiene menos de 2 campos conocidos de `_USER_PROFILE_FIELDS` **y** intent es `crear_workflow` o `unclear` **y** no hay summary todavía:
- Se inyecta una directiva especial que le pide al agente hacer UNA pregunta abierta sobre quién es el usuario antes de proponer cualquier workflow.

### System prompt construido en `_build_system_prompt`

Secciones en orden:
1. Identidad y personalidad de Shifu
2. Reglas de formato y brevedad (ultra-concise, sin anunciar acciones)
3. Regla MANDATORY: usar `mostrar_opciones` en vez de listas de texto
4. Cómo manejar integraciones no conectadas
5. **⛔ WORKFLOW PHASE GUARD** — compuerta de 3 condiciones obligatorias + fase actual inyectada dinámicamente
6. Workflow TWO-PHASE protocol completo (FASE 1 y FASE 2)
7. Tabla de frecuencias inferibles automáticamente
8. Scheduling (programar_workflow tras confirmar)
9. Bloque CONTINUITY RULE (si hay historial previo)
10. Bloque LONG-TERM MEMORY (si hay memoria global)
11. Bloque KNOWN RESOURCES — IDs reales de entity memory
12. Bloque INTERNAL CONTEXT (resumen de conversación)
13. Perfil del usuario (nombre, nivel técnico, industria)
14. Catálogo de integraciones con ✓ en conectadas
15. Tools activos agrupados por app
16. ⚡ AGENT DIRECTIVE — estrategia concreta para este turno

**Entra al estado:**
```python
{
  "messages": [SystemMessage(system_prompt), ...historial, HumanMessage(enriched_message or user_input)],
  "all_tools": [BaseTool, ...],
}
```

---

## 5. Nodo: `agent_node`

**Archivo:** [app/agents/shifu_v3/nodes.py](../../../agents/shifu_v3/nodes.py)

Invoca el LLM principal con todos los tools enlazados.

```python
llm = ChatOpenAI(model=model_name, temperature=0.4)  # V3_CHAT_TEMP env var
llm_with_tools = llm.bind_tools(all_tools)
response = await llm_with_tools.ainvoke(messages)
```

**Modelos permitidos:** `gpt-4o-mini` (default), `gpt-4.1-nano`

**Forzado de salida (anti-loop):**
- Si `tool_rounds >= 25` → inyecta SystemMessage "Límite de operaciones alcanzado. Responde AHORA."
- Si mismo tool falló `>= 2` veces consecutivas → inyecta SystemMessage con el nombre del tool y qué necesita del usuario

**Output:** `AIMessage` con o sin `tool_calls`.

---

## 6. Nodo: `tool_executor_node`

**Archivo:** [app/agents/shifu_v3/nodes.py](../../../agents/shifu_v3/nodes.py)

Ejecuta todos los `tool_calls` del último `AIMessage` en paralelo.

```python
results = await asyncio.gather(*[_run_one(tc) for tc in tool_calls])
```

### Auto-debug y retry con LLM

Si un tool retorna error **y** tiene `args_schema` **y** NO es un state error:
1. Llama a un LLM (mismo `model_name`) con el error + schema + args originales
2. Si el LLM puede corregir los args → reintenta el tool con los args corregidos
3. Si el retry también falla → devuelve un `SYSTEM_ERROR` estructurado
4. State errors (no active draft, not found, not connected) → pasa directamente al agente

**State error patterns** (no se reintentan):
`no active draft`, `create a workflow first`, `not found`, `already active`, `not connected`, etc.

### Captura de payloads especiales

Escanea los resultados y captura en el estado:
- `accion` si algún tool retorna `{"accion": "connect_integration", ...}` → frontend abre modal OAuth
- `user_choices` si algún tool retorna `{"tipo": "user_choices", ...}` → frontend renderiza ChoicesCard
- `system_errors` si algún tool retorna `{"error": "SYSTEM_ERROR", ...}` → lista acumulada

**Límite de resultado:** 6,000 caracteres por tool (trunca con mensaje)

---

## 7. Nodo: `markdown_formatter_node`

**Archivo:** [app/agents/shifu_v3/nodes.py](../../../agents/shifu_v3/nodes.py)

Post-procesador ligero: reformatea la respuesta final del agente en markdown pulido.

```python
# Solo actúa sobre respuestas >= 150 caracteres
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2)
formatted = await llm.ainvoke([system_prompt, raw_response])
# Retorna AIMessage con MISMO id que el mensaje raw → add_messages lo reemplaza in-place
```

**Reglas del formatter:**
- Preserva todo el contenido y significado — nunca añade ni quita información
- Agrega emojis con moderación (refuerzan significado, nunca decorativos)
- Bold en términos clave, nombres de workflows, acciones importantes
- Formatos de lista con espaciado consistente
- Respuestas cortas (< 150 chars): las retorna exactamente como están
- Nunca añade frases de cierre tipo "¿Te puedo ayudar en algo más?"

---

## 8. Nodo: `memory_saver_node`

**Archivo:** [app/agents/shifu_v3/nodes.py](../../../agents/shifu_v3/nodes.py)

Persiste la conversación y actualiza memoria. Parte síncrona y parte en background:

```
Síncrono (bloquea antes de responder):
  save_message(user_input, "user")
  save_message(assistant_response, "assistant")
  refresh_summary()   ← actualiza resumen de conversación

Background (no bloquea la respuesta — asyncio.create_task):
  detect_and_save_preferences()  ← extrae preferencias implícitas del turno
  extract_and_save_entities()    ← extrae IDs (Sheets, Docs, Slides, Drive, Workflows) de ToolMessages
  update_daily_diary()           ← agrega al diario de memoria long-term
```

---

## 9. Tools disponibles para el agente

### Tools de consulta (siempre disponibles — `_build_query_tools`)

| Tool | Descripción |
|---|---|
| `listar_mis_workflows` | Lista todos los workflows del usuario con sus estados |
| `ver_borrador_workflow` | Muestra el workflow draft activo de esta conversación |
| `consultar_herramientas_disponibles` | Retorna names exactos de tools disponibles, agrupados por integración. Con `app='gmail'` devuelve schema completo con `required_config` |
| `solicitar_conexion_integracion` | Emite un evento de frontend para abrir modal OAuth. Solo cuando la app definitivamente NO está conectada |
| `mostrar_opciones` | Renderiza un card interactivo de elección en el UI. OBLIGATORIO en vez de listas de texto |

#### Tool `mostrar_opciones`

```python
async def _mostrar_opciones(
    question: str,           # La pregunta a mostrar
    options: List[str],      # Máximo 8 opciones
    allow_other: bool = True,    # Mostrar input libre "Otra cosa"
    multi_select: bool = False,  # Permitir múltiples selecciones
    step: int = 1,           # Para wizards multi-paso
    total_steps: int = 1,
) -> str:
    return json.dumps({
        "tipo": "user_choices",
        "question": ...,
        "options": options[:8],
        ...
    })
```

El resultado llega al frontend via SSE como evento `user_choices`.

### Tools de workflow (`_build_workflow_tools` + BigTools registry)

| Tool | Descripción |
|---|---|
| `crear_workflow` | Crea un nuevo draft workflow en esta conversación |
| `agregar_paso_workflow` | Agrega un paso al draft activo |
| `ver_borrador_workflow` | Ver el draft actual |
| `confirmar_workflow` | Activa el draft workflow |
| `pausar_workflow` / `reactivar_workflow` | Pausa/reactiva un workflow activo |
| `editar_workflow` | Carga un workflow existente como nuevo draft |
| `eliminar_paso_workflow` | Elimina un paso por orden |
| `reemplazar_paso_workflow` | Reemplaza un paso del draft |
| `eliminar_workflow` | Elimina permanentemente un workflow |
| `fijar_frecuencia_workflow` | Establece la frecuencia de ejecución |
| `configurar_metadata_workflow` | Guarda el plan de fases como checklist interno |
| `programar_workflow` | Programa ejecución automática (interval o once) |
| `listar_programaciones_workflow` | Lista todas las programaciones activas |
| `pausar_programacion` / `reanudar_programacion` / `eliminar_programacion` | Gestión de schedules |

---

## 10. Workflow Phase Guard (Sistema de fases)

El sistema implementa una **compuerta de tres capas** para evitar que Shifu cree el workflow antes de terminar la recolección de información.

### Capas de protección

**Capa 1 — `_derive_workflow_phase()`** (pattern-based, sin LLM):
- Escanea historial de mensajes buscando señales concretas
- Retorna: `idle | phase1_collecting | phase1_proposed | phase2_building | phase2_done`
- Se inyecta en el estado como `workflow_phase`

**Capa 2 — PHASE GUARD en system prompt**:
- Sección dedicada con 3 condiciones obligatorias (ALL THREE must be true)
- Lista explícita de 6 violaciones que NUNCA activan Phase 2
- Muestra la fase actual: `### Current workflow phase: **{workflow_phase}**`

**Capa 3 — Intent analyzer tightened**:
- `aprobar_plan` requiere 4 condiciones estrictas
- Si alguna falla → asigna `ajustar_plan`, `responder_pregunta`, o `unclear`

### Secuencia válida de entrada a Phase 2

```
Turno N:   Shifu → presenta plan numerado → termina con "¿Te parece bien?"
Turno N+1: User  → "sí" / "dale" / "hazlo" / "perfecto" / similar
Turno N+1: Shifu → PRIMERA ACCIÓN = crear_workflow (sin texto previo)
```

---

## 11. BigTools Registry

**Archivo:** [app/agents/agent_langGraph/bigTools_registry.py](../../../agents/agent_langGraph/bigTools_registry.py)

```python
get_all_bigtools(
  user_id, user_email, db,
  active_accounts,      # {"gmail": "account_id", ...}
  allowed_providers,    # {"gmail", "google_sheets", ...}
  conversation_id
) → List[BigTool]
```

**Flujo interno:**
1. Carga tools estáticos: `suma`, `concat`, `tavily`, `wikipedia`
2. Por cada integración SaaS soportada:
   ```
   importlib.import_module("app.agents.agent_langGraph.bigtools.{service}_bigtools")
   → get_{service}_bigtools(user_email, user_id, db, active_accounts)
   ```
3. Aísla excepciones por integración — si Gmail falla, las demás siguen cargando

**Integraciones soportadas:**
`gmail · drive · docs · sheets · slides · dropbox · onedrive · clickup · asana · trello · monday · jira · instagram · slack · notion · hubspot · brevo · mailchimp · facebook · linkedin · twitter · telegram · whatsapp · outlook`

**Estructura `BigTool`:**
```python
@dataclass
class BigTool:
    name: str                          # "listar_correos"
    description: str                   # descripción en lenguaje natural
    tool: Callable                     # sync o async
    args_schema: Type[BaseModel]       # Pydantic schema de los args
```

---

## 12. Variante Streaming (SSE)

**Archivo:** [app/routes/V3/agent/shifu.py](shifu.py)

### Arquitectura de streaming

El endpoint usa un patrón **producer/consumer con cola async** para manejar herramientas lentas sin romper la conexión:
- `_run_graph()` corre `astream_events` en un background task, pone eventos en una `asyncio.Queue`
- `_watch_disconnect()` detecta desconexiones del cliente cada 2s, pone un sentinel en la cola
- El loop principal procesa la cola con `wait_for(timeout=5s)` — emite `: keep-alive\n\n` si no hay eventos

### Eventos SSE emitidos

| Evento | Payload | Cuándo |
|---|---|---|
| `: keep-alive` | (comentario SSE) | Cada 5 s de silencio (herramientas lentas) |
| `token` | `{"type": "token", "text": "...", "node": "..."}` | Cada chunk de texto del LLM en nodo `agent` |
| `reasoning_commit` | `{"type": "reasoning_commit", "text": "..."}` | LLM produjo texto + tool_calls en el mismo mensaje |
| `tool_start` | `{"type": "tool_start", "tool": "listar_correos"}` | Inicio de cada tool call |
| `intent_plan` | `{"type": "intent_plan", "intent_type": "...", "confidence": ..., ...}` | Al terminar `intent_analyzer_node` |
| `user_choices` | `{"type": "user_choices", "question": "...", "options": [...], ...}` | Cuando `mostrar_opciones` se llama |
| `suggestions` | `{"type": "suggestions", "items": ["...", "..."]}` | Al final, después de `done` |
| `done` | `{"type": "done", "text": "...", "reasoning": ..., "accion": ..., "user_choices": ..., "system_errors": ...}` | Respuesta final |
| `error` | `{"type": "error", "message": "..."}` | Si el grafo falla |

Solo se streamean tokens del nodo `agent` (se filtra `memory_saver` y otros nodos).

### Texto final: DB vs stream

El campo `text` del evento `done` usa la respuesta guardada por `memory_saver` en MongoDB (más limpia), con fallback al texto acumulado del stream. El campo `text_source` indica cuál fue usado (`"db"` o `"stream"`).

### Suggestion generator

Después de cada turno exitoso, se llama `_generate_suggestions()` con timeout de 6s:
- Modelo: `gpt-4o-mini` (override por env `V3_SUGGESTIONS_MODEL`)
- Genera 3-4 prompts de seguimiento cortos en español
- Se emite como evento `suggestions` antes del evento `done`
- Completamente non-blocking — no afecta la respuesta principal

---

## 13. Entity Memory Service

**Archivo:** [app/services/entity_memory_service.py](../../../services/entity_memory_service.py)

Persiste IDs concretos de recursos que retornan las herramientas (Sheets, Docs, Slides, Drive, Workflows) para que Shifu los use en sesiones futuras sin alucinarlos.

**Colección MongoDB:** `user_entities` (un doc por usuario)

```python
# Flujo de escritura (en memory_saver_node, background):
await extract_and_save_entities(user_id, state["messages"], db)
# ↑ Escanea ToolMessages buscando: spreadsheet_id, document_id, presentation_id, workflow_id, file_id
# ↑ También detecta objetos Drive: {"id": "...", "name": "...", "mimeType": "..."}

# Flujo de lectura (en context_loader_node):
entities = await load_user_entities(user_id, db)
block = format_entities_for_prompt(entities)
# ↑ Inyecta en system prompt como "## 📁 Recursos conocidos del usuario (IDs reales)"
```

**Tipos de entidades:**
`google_sheet · google_doc · google_slides · drive_folder · drive_file · workflow`

Máximo 20 entidades por tipo, ordenadas por `last_seen_at` desc.

---

## 14. Estado del grafo (`ShifuState`)

**Archivo:** [app/agents/shifu_v3/state.py](../../../agents/shifu_v3/state.py)

```python
class ShifuState(TypedDict, total=False):
    # ── Input (set by the route handler)
    user_input: str
    user_id: str
    user_email: str
    name: str
    conversation_id: str
    model_name: str

    # ── Messages (accumulated via add_messages — handles deduplication)
    messages: Annotated[list[AnyMessage], add_messages]

    # ── Tools built by context_loader (no checkpointer — not serialized)
    all_tools: list[Any]

    # ── UI action emitted by tool_executor (e.g. connect_integration modal)
    accion: Optional[dict]

    # ── Interactive choice card emitted by mostrar_opciones tool
    user_choices: Optional[dict]

    # ── System errors collected across all tool_executor rounds
    system_errors: Optional[list[dict]]

    # ── Intent analysis (set by intent_analyzer_node)
    intent_analysis: Optional[dict]
    enriched_message: Optional[str]
    agent_strategy: Optional[str]
    needs_clarification: Optional[bool]
    clarification_question: Optional[str]

    # ── Workflow phase tracker (set by intent_analyzer_node)
    # Values: "idle" | "phase1_collecting" | "phase1_proposed" | "phase2_building" | "phase2_done"
    workflow_phase: Optional[str]
```

---

## 15. Lógica de creación de Workflows (2 fases)

### FASE 1 — Entender y proponer

```
1. [Opcional] Si perfil incompleto → preguntar UNA vez sobre quién es el usuario
2. llamar mostrar_opciones si necesita elegir entre opciones (tipo de automatización, app, frecuencia)
3. consultar_herramientas_disponibles() por cada integración
4. Para cada campo required_config, clasificar:
     ✅ known-now       → ya se sabe el valor
     🔄 runtime-output  → lo genera otro paso (usar {{step_N.field}} en Phase 2)
     🔍 needs-lookup    → requiere tool de búsqueda en Phase 2
     ❓ needs-user      → debe preguntarle al usuario (solo si NO se puede inferir)
5. Proponer plan en 3-6 pasos con:
     - Nombre creativo del workflow (ej. "Radar de Leads", "Motor de Ventas")
     - INTRO de 2-3 oraciones describiendo qué problema resuelve
     - Cada paso: N. [emoji] **Nombre** — descripción de valor para el negocio
     - Frecuencia mencionada naturalmente
     - Una mejora proactiva sugerida
     - Terminar con: "¿Te parece bien o quieres ajustar algo?"
6. NUNCA llamar crear_workflow en esta fase
```

### FASE 2 — Construir (solo si el usuario aprueba)

```
1. crear_workflow(nombre_descriptivo)              ← SIN texto previo, ir directo al tool call
2. fijar_frecuencia_workflow(id, frecuencia_inferida)
3. configurar_metadata_workflow(id, plan_steps)    ← MEMORY ANCHOR: guarda el checklist del plan
4. [Para cada paso que necesita lookup] → llamar find/search tool primero
5. agregar_paso_workflow(id, orden=N, config={campos_completos})
   ⛔ config: {} = workflow roto — TODOS los required_config deben tener valor
   ⛔ usar {{step_N.field}} para runtime-outputs
   ⛔ agregar_paso EXACTAMENTE UNA VEZ por número de orden
6. ver_borrador_workflow(id)                       ← verificar: sin duplicados, completitud
   - Si hay duplicados: eliminar_paso_workflow
   - Si faltan pasos: agregar los que faltan
7. Presentar workflow en 2-4 líneas en lenguaje humano
8. "¿Lo activo tal como está o quieres cambiar algo?"
9. confirmar_workflow(id)                          ← si aprueba
10. [Opcional] programar_workflow(id, schedule_type, every_seconds)
```

### Tipos de paso avanzados

```
AI steps (app: 'ai'):  ai_summarize, ai_transform, ai_extract, ai_classify,
                       ai_generate, ai_filter, ai_decide
Foreach loops:         type: 'foreach', source: '{{step_N}}'
Condition branches:    type: 'condition', config: {field, operator, value, on_false}
Retry:                 max_retries: 2, retry_delay: 1.0
Deduplication:         config: {after: '{{state.last_run_at}}'}
```

### Inferencia automática de frecuencia

| Intención del workflow | frequency_type | every_seconds |
|---|---|---|
| Monitor precios / alertas en tiempo real | realtime | 300 |
| Check inbox / feeds | every_15m | 900 |
| Procesamiento de correo / lead capture | hourly | 3600 |
| Sync periódico | every_4h | 14400 |
| Reporte diario / backup | daily | 86400 |
| Resumen semanal | weekly | 604800 |
| Facturación mensual | monthly | 2592000 |
| Ejecución única | once | 0 |

---

## 16. Variables de entorno relevantes

| Variable | Default | Descripción |
|---|---|---|
| `V3_CHAT_MODEL` | `gpt-4o-mini` | Modelo del agente principal |
| `V3_CHAT_TEMP` | `0.4` | Temperatura del LLM principal |
| `INTENT_CLASSIFIER_MODEL` | `gpt-4o-mini` | Modelo del clasificador de intención |
| `INTENT_CONFIDENCE_THRESHOLD` | `0.60` | Umbral mínimo de confianza para no pedir clarificación |
| `V3_SUGGESTIONS_MODEL` | `gpt-4o-mini` | Modelo para generar sugerencias de seguimiento |
| `REDIS_URL` | — | Redis para pub/sub de eventos del workflow executor |

---

## 17. Persistencia (MongoDB)

| Colección | Qué guarda |
|---|---|
| `chat_messages` | Mensajes user/assistant por conversación |
| `conversations` | Metadata de conversaciones (resumen, etc.) |
| `preferences` | Preferencias del usuario (idioma, tono, perfil, profesión) |
| `integrations` | Cuentas OAuth conectadas |
| `workflows` | Definiciones de workflows (pasos, frecuencia, metadata, status) |
| `workflow_runs` | Registros de ejecución |
| `workflow_analytics` | Métricas y performance por run |
| `long_term_memory` | Diario diario + síntesis global por usuario |
| `user_entities` | IDs de recursos conocidos (Sheets, Docs, Slides, Drive, Workflows) |
| `scheduled_tasks` | Programaciones de workflows (interval / once) |

---

## 18. Frontend — Eventos SSE y componentes UI

**Componentes relacionados en el frontend:**

| Componente | Evento SSE | Descripción |
|---|---|---|
| `ChoicesCard` | `user_choices` | Card interactivo con opciones numeradas, multi-select, input libre "Otra cosa", botón "Omitir", paginación step/total_steps |
| `SuggestionsRow` | `suggestions` | Chips de sugerencias en pills violetas; al hacer click envía el texto como mensaje del usuario |
| `IntentPlanBlock` | `intent_plan` | Bloque de análisis de intención (intent_type, confidence, agent_strategy) mostrado antes de la respuesta |
| Tool label badges | `tool_start` | Etiqueta del nombre de la herramienta siendo ejecutada |

**Forma de `user_choices` payload:**
```typescript
{
  type: "user_choices",
  question: string,
  options: string[],      // max 8
  allow_other: boolean,
  multi_select: boolean,
  step: number,
  total_steps: number,
}
```

**Forma de `suggestions` payload:**
```typescript
{
  type: "suggestions",
  items: string[],        // 3-4 prompts cortos en español
}
```
