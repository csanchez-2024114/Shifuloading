# Nodes — app/agent/shared/nodes/

LangGraph nodes del agente Shifu (shifu_base_v1). Cada función es async y recibe `ShifuState`, retorna un dict parcial que LangGraph mergea al estado global.

---

## Flujo de ejecución

```
START
  │
  ▼
goal_resolver          ← resuelve qué goal activo aplicar a este turno
  │
  ▼
memory_retriever       ← carga y rankea los 5 tipos de memoria del usuario
  │
  ▼
semantic_intake        ← parsea el mensaje: intent, apps, sentiment, schedule...
  │
  ├── [req_level ≠ None] ─────────────────────────────────────────────┐
  │                                                                     │
  ├── [is_closing=True]  ────────────────────────────────────────────┐ │
  │                                                                   │ │
  ├── [account_selection_resolved=True] ──────────────────────────┐  │ │
  │                                                                │  │ │
  └── [default] ─── fan-out paralelo:                             │  │ │
        ├── catalog_checker                                         │  │ │
        ├── auth_validator                                          │  │ │
        └── tavily_subgraph (solo si needs_external_info=True)     │  │ │
              │                                                     │  │ │
              ▼ (fan-in)                                            │  │ │
          bigtools_inspector                                        │  │ │
              │                                                     │  │ │
              ▼                                                     │  │ │
          workflow_planner  ← plan privado de ejecución            │  │ │
              │                                                     │  │ │
              ▼ (todos convergen aquí) ◄────────────────────────── ┘  │ │
          responder  ◄─────────────────────────────────────────────── ┘ │
              ▲                                                           │
              └── req_investigator ◄───────────────────────────────────┘
              │
              ▼
          response_evaluator   ← gate de calidad (hasta 2 reintentos)
              │
              ├── [eval_feedback] ──► responder  (reintento)
              │
              └── [pass / max_retries] ──► memory_updater ──► END

Error en cualquier nodo wrapeado:
  └──► error_handler ──► END
```

### Variante: requirements flow (`req_level ≠ None`)

```
semantic_intake [skip LLM] → req_investigator → responder → response_evaluator → memory_updater → END
```

`req_level` persiste entre turnos vía el checkpointer de MongoDB. `semantic_intake` detecta `intent == "create_workflow"` y setea `req_level=1` para activar el flujo.

---

## Clasificación de nodos

| Nodo | Clasificación | Detalle |
|------|--------------|---------|
| `goal_resolver` | Algoritmo puro | DB fetch + keyword matching Python |
| `memory_retriever` | Algoritmo puro | DB fetch + scoring heurístico Python (sin LLM) |
| `semantic_intake` | Algoritmo puro | 1 LLM call de paso único — no razona en loop |
| `catalog_checker` | Algoritmo puro | DB query + if/else Python |
| `auth_validator` | Algoritmo puro | DB query + lógica de escenarios Python |
| `tavily_subgraph` | **Subgraph** *(no sub-agente)* | `StateGraph` compilado, pero pipeline secuencial fijo de 2 nodos — ver nota abajo |
| `bigtools_inspector` | Algoritmo puro | 1 LLM call de paso único |
| `workflow_planner` | Algoritmo puro | 1 LLM call para plan privado de ejecución |
| `req_investigator` | **Máquina de estados** | 4 sub-funciones despachadas por `req_level`; multi-turno via checkpointer |
| `responder` | Algoritmo puro | Aggregation Python + 1 LLM call de paso único |
| `response_evaluator` | Algoritmo puro | 1 LLM call con structured output |
| `research_curator` | Algoritmo puro | Pipeline fijo de LLM calls — el flujo no cambia dinámicamente |
| `memory_updater` | Algoritmo puro | DB write condicional |
| `error_handler` | Algoritmo puro | Mensaje hardcodeado |

### ¿Hay sub-agentes?

**No hay ningún sub-agente.** Un sub-agente requiere loop de razonamiento autónomo: el nodo recibe un objetivo, decide qué herramienta invocar, observa el resultado, y repite hasta completar. Ningún nodo en este grafo hace eso.

**`tavily_subgraph`** es el único caso especial: es un `StateGraph` de LangGraph compilado con `.compile()`, por eso aparece como "subgraph". Pero internamente es un pipeline de exactamente 2 nodos en secuencia fija (`tavily_searcher → research_curator`). Nunca decide qué herramienta usar en base a lo que observa — siempre ejecuta esos dos nodos en ese orden.

El único loop que existe en el grafo completo es `response_evaluator → responder` (reintento de calidad), y es un ciclo explícito con tope de 2 iteraciones, no razonamiento autónomo.

---

## Nodos en orden de ejecución

---

### 1. `goal_resolver_node`
**Archivo:** `goal_resolver.py`

Primer nodo del grafo. Determina qué goal activo del usuario es relevante para el turno actual.

**Lee del estado:**
- `user_id`
- `messages` (busca el último HumanMessage para keyword matching)

**Escribe al estado:**
- `goal_id` — ID del goal activo, o `None` si no hay ninguno

**Lógica:**
1. Carga todos los goals activos del usuario ordenados por fecha (más reciente primero).
2. Si hay solo uno → lo usa directamente.
3. Si hay múltiples → hace keyword matching contra el último mensaje del usuario para el más relevante.
4. Si no hay goals → retorna `goal_id = None` (el resto del grafo funciona igual).

---

### 2. `memory_retriever_node`
**Archivo:** `memory_retriever.py`

Segundo nodo. Recupera los 5 tipos de memoria del usuario en paralelo y los rankea en un string listo para el prompt del responder.

**Lee del estado:**
- `user_id`
- `goal_id`
- `messages` (extrae intent del último HumanMessage)
- `apps_involved`

**Escribe al estado:**
- `raw_memories` — dict con las 5 colecciones de memoria sin procesar
- `ranked_context` — string rankeado por relevancia, para inyectar al prompt del LLM

**Tipos de memoria cargados** (vía `memory_engine.retrieve_memories`):
- `goals` — objetivos activos del usuario
- `semantic` — memoria semántica (hechos persistentes)
- `episodic` — episodios pasados relevantes
- `decisions` — decisiones tomadas por el agente
- `structured` — preferencias estructuradas del usuario

---

### 3. `semantic_intake_node`
**Archivo:** `semantic_intake.py`

El nodo más complejo. Procesa el mensaje del usuario con una sola llamada LLM (gpt-4o-mini) y escribe la mayor parte del estado que usarán los nodos siguientes. Corre ANTES del fan-out paralelo.

**Lee del estado:**
- `messages`, `available_accounts`, `selected_accounts`
- `current_time_utc`, `user_timezone`, `user_location`, `user_country_code`

**Escribe al estado (reset + nueva info cada turno):**
- `structured_prompt` — intent en inglés para el agente
- `apps_involved` — lista de apps detectadas (claves del catálogo)
- `needs_external_info` — bool: ¿requiere búsqueda web?
- `catalog_query_mode` — `"list_available"` | `"list_connected"` | `"validate"` | `"add_account"` | `None`
- `is_closing` — bool: ¿el usuario se está despidiendo?
- `user_sentiment` — `"calm"` | `"polite"` | `"neutral"` | `"confused"` | `"frustrated"` | `"urgent"`
- `mood_state` — recomendación inicial de mood para el responder
- `schedule_context` — cron + human-readable cuando hay expresión de scheduling
- `optimized_search_query` — query SEO limpia para Tavily
- `location_aware` — bool: ¿la query es sensible a ubicación?
- `needs_fact_verification` — bool: ¿los datos son time-sensitive y deben verificarse?
- `account_selection_resolved` — bool: se activa cuando el usuario elige una cuenta de una lista pendiente
- `validation_reports`, `missing_variables` — reseteados a `None` cada turno

**Resolución de apps (2 capas):**
1. **Capa 1** (determinista): normaliza espacios → underscores, aplica alias de sufijos (`"slides"` → `"google_slides"`).
2. **Capa 2** (LLM, solo si quedan apps sin resolver): micro-llamada gpt-4o-mini para resolver referencias ambiguas usando conocimiento general.

**Short-circuits (sin llamada LLM):**
- `req_level is not None` → retorna `_EMPTY_RESULT` inmediatamente (el turno pertenece al `req_investigator`; el `req_level` persiste en estado desde el turno anterior vía checkpointer)
- Señal de cierre detectada (palabra en `closing_signals` de la personalidad del agente) → `is_closing = True`
- Mensaje trivial social (hola, ok, gracias, bye...) → retorna `_EMPTY_RESULT`

**Detección de `create_workflow`:**
Cuando el LLM retorna `detected_intent == "create_workflow"` y `req_level` es `None`, inyecta `req_level=1` al resultado para activar el flujo de investigación de requerimientos. La lista de intents válidos incluye `create_workflow | workflow | automation | question | exploring | chat | command`.

**Resolución de cuenta multi-account:**
Si `available_accounts` está presente (el usuario tenía cuentas pendientes de elegir), el LLM detecta la selección y escribe `account_selection_resolved = True`, lo que hace que el grafo saltee el fan-out de validación para ese turno.

---

### 4. `catalog_checker_node` *(corre en paralelo)*
**Archivo:** `catalog_checker.py`

Verifica que cada app en `apps_involved` está soportada en la DB de catálogo. Corre en paralelo con `auth_validator` y `tavily_subgraph`.

**Lee del estado:**
- `apps_involved`
- `catalog_query_mode`

**Escribe al estado:**
- `validation_reports` — lista de reportes por app (reducer, safe para paralelo)
- `catalog_available_apps` — lista de apps públicas (solo en modo `list_available`)
- `catalog_apps_grouped` — dict agrupado por categoría (solo en modo `list_available`)

**Estados posibles por app en el catálogo:**

| `active` | `visible` | Estado        | Usable por el agente |
|----------|-----------|---------------|----------------------|
| `True`   | `True`    | Available     | Sí                   |
| `True`   | `False`   | Beta/Internal | Sí                   |
| `False`  | `True`    | Maintenance   | No                   |
| `False`  | `False`   | Archived      | No                   |

**Modos especiales:**
- `list_available` → retorna todas las apps activas + visibles agrupadas por categoría
- Sin apps + sin modo `list_available` → skip

---

### 5. `auth_validator_node` *(corre en paralelo)*
**Archivo:** `auth_validator.py`

Verifica que el usuario tiene una conexión OAuth activa para cada app en `apps_involved`. Maneja escenarios multi-cuenta. Corre en paralelo con `catalog_checker` y `tavily_subgraph`.

**Lee del estado:**
- `apps_involved`, `user_id`, `catalog_query_mode`
- `selected_accounts`, `available_accounts`

**Escribe al estado:**
- `validation_reports` — reportes por app (reducer, safe para paralelo)
- `selected_accounts` — dict `{app: email}` con cuentas auto-seleccionadas
- `available_accounts` — dict `{app: [list_of_accounts]}` cuando hay múltiples cuentas sin resolver
- `user_connected_apps` — dict de todas las apps conectadas (solo en modo `list_connected`)

**Escenarios por app:**

| Caso | Condición | Resultado |
|------|-----------|-----------|
| A | 0 cuentas usables | Error `not_connected` / `expired` / `revoked` |
| B | 1 cuenta usable | Auto-selección → escribe `selected_accounts` |
| C resuelto | Múltiples, ya hay selección válida | OK con la cuenta elegida |
| C pendiente | Múltiples, sin selección | `pending_selection` + escribe `available_accounts` |

**Status de conexión usables:** `"active"` y `"needs_refresh"`. Otros (`"expired"`, `"revoked"`) generan error.

**Modos especiales:**
- `list_connected` → retorna dict de todas las cuentas del usuario agrupadas por provider
- `list_available` → skip (no necesita verificar auth para listar el catálogo)
- `add_account` → genera reporte `add_account` con URL de autorización para cada app

---

### 6. `tavily_subgraph` *(corre en paralelo — nodo especial)*
**Archivo:** `tavily_searcher.py` (envuelto como subgraph con timeout en el builder)

Búsqueda web en dos fases cuando el usuario necesita información externa. Corre en paralelo con los validadores.

**Lee del estado:**
- `needs_external_info`, `optimized_search_query`, `structured_prompt`
- `effort_level`, `location_aware`, `user_location`
- `needs_fact_verification`, `current_time_utc`

**Escribe al estado:**
- `retrieved_research` — texto consolidado con resultados de búsqueda
- `retrieved_sources` — lista de fuentes estructuradas `[{title, url, domain}]`

**Pipeline de 2 fases** (parametrizado por `effort_level`):

| Tier   | Phase 1 depth  | max_results | Phase 2 (extract) URLs | Cap total |
|--------|---------------|-------------|------------------------|-----------|
| `low`  | basic          | 3           | 0                      | 3 KB      |
| `medio`| advanced       | 7           | 3 (basic)              | sin límite|
| `high` | advanced       | 7           | 3 (advanced)           | sin límite|
| `max`  | advanced       | 10          | 5 (advanced)           | sin límite|

**Features adicionales:**
- **Sanitización de competidores**: reemplaza "Zapier", "Make", "n8n", etc. con términos genéricos antes de que lleguen al LLM.
- **Temporal anchor**: inyecta fecha actual en queries de noticias (`needs_fact_verification=True`) para evitar resultados desactualizados.
- **Location appending**: agrega la ciudad del usuario al query cuando `location_aware=True`.
- **Skip automático**: si `needs_external_info=False` o no hay query disponible.

---

### 7. `bigtools_inspector_node` *(fan-in — corre después de los 3 paralelos)*
**Archivo:** `bigtools_inspector.py`

Nodo de fan-in: corre después de que `catalog_checker`, `auth_validator` y `tavily_subgraph` completan. Solo inspecciona apps que pasaron AMBAS validaciones (catalog + auth). Usa LLM para mapear el intent del usuario a herramientas concretas y detectar parámetros faltantes.

**Lee del estado:**
- `validation_reports` (ya consolidados por el reducer)
- `structured_prompt`, `apps_involved`
- `user_timezone`, `user_location`, `user_country_code`
- `messages` (fallback de intent cuando `structured_prompt` es None)
- `config.configurable.inspector_model` (default: `gpt-4o-mini`)

**Escribe al estado:**
- `validation_reports` — agrega 1 reporte con source `"bigtools"` (ok o error)
- `missing_variables` — lista de parámetros críticos que el usuario no proporcionó

**Lógica:**
1. Filtra apps con `catalog.status == "ok"` AND `auth.status == "ok"`.
2. Carga el contexto de herramientas disponibles para esas apps (`BIGTOOLS_REGISTRY`).
3. Llama al LLM con el intent + herramientas → retorna `can_proceed`, `tool_mapping`, `missing_variables`.
4. Si `can_proceed=False` → reporte de error con nota explicativa.
5. Si ninguna app pasó ambas validaciones → skip sin error.

---

### 8. `responder_node`
**Archivo:** `responder.py`

Nodo de convergencia. Consolida todos los outputs del pipeline de validación y genera la respuesta final con streaming. Combina lo que antes eran dos nodos separados (aggregator + chat).

**Lee del estado:** prácticamente todo (`validation_reports`, `missing_variables`, `apps_involved`, `is_closing`, `catalog_query_mode`, `structured_prompt`, `retrieved_research`, `curated_research`, `ranked_context`, `eval_feedback`, `effort_level`, `mood_state`, `user_sentiment`, `model_name`, `messages`, estado de catálogo y cuentas conectadas...)

**Escribe al estado:**
- `messages` — agrega el `AIMessage` con la respuesta generada
- `mood_state` — mood final computado para el turno
- `requirement_level` — `"level_1"` (validación fallida) | `"level_2"` (listo para ejecutar) | `None` (chat puro)

**Paso 1 — Aggregation (Python puro, sin LLM):**
Lee `validation_reports` y determina `requirement_level`:
- `level_1` → hay errores, cuentas pendientes, o `add_account` → construye `error_context` con instrucciones específicas para el LLM
- `level_2` → todas las validaciones pasaron
- `None` → turno puro de chat (sin apps, sin catalog query)

**Paso 2 — Mood computation:**
Prioridad: `is_closing` > sentiment `frustrated/urgent` > `level_1 + confused` > `calm/polite/neutral` > fallback `DEFAULT`

| Mood | Cuándo se activa |
|------|-----------------|
| `CLOSING` | El usuario se despide |
| `DIRECT_EMPATHY` | Usuario frustrado/urgente, o level_1 + confundido |
| `HELPFUL` | Sentimiento positivo/neutro |
| `DEFAULT` | Fallback general |

**Paso 3 — Generación LLM (streaming):**
Construye el prompt en capas en este orden (para maximizar cache de provider):
1. Bloque estático: identidad + principios + restricciones + estilo (CACHEADO)
2. Regla de saludo (primer turno vs. turno N+1)
3. Auth policy (solo en level_1)
4. Error context (errores de validación)
5. Research externo (Tavily curado o raw)
6. Intent clarificado / **REQUIREMENTS FLOW directive** (ver nota abajo)
7. Contexto de memoria (ranked_context)
8. Feedback de self-correction (eval_feedback, solo en reintentos)
9. Anti-looping rule (evita frases repetidas de cierre)
10. Mood directive
11. Effort directive (salvo en DIRECT_EMPATHY)
12. Research grounding directive + citation rules (si hay research)
13. Bloque de tiempo actual (siempre mutable, siempre al final)
14. Catalog/connected listing (cuando aplica)
15. `messages` del historial de conversación

**REQUIREMENTS FLOW directive (cuando `req_level is not None`):**
En lugar de inyectar `structured_prompt` como `"[Clarified user intent — internal use only]"`, el responder inyecta:
```
REQUIREMENTS FLOW — CRITICAL INSTRUCTION: Your ONLY task is to deliver the following
content to the user in a natural, conversational tone. Do NOT add analysis about app
availability, catalog checks, or alternative suggestions. Do NOT modify the questions
or proposals listed. Just present them clearly:
<structured_prompt from req_investigator>
```
Esto asegura que el responder relay el contenido de `req_investigator` sin añadir análisis propios ni interferir con el flujo de requerimientos.

---

### 9. `response_evaluator_node`
**Archivo:** `response_evaluator.py`

Gate de calidad después del responder. Evalúa la última respuesta del agente en 3 criterios. Si falla, inyecta feedback y el grafo vuelve al responder (hasta 2 reintentos). Si pasa, libera el flujo hacia `memory_updater`.

**Lee del estado:**
- `messages` (busca el último AIMessage)
- `eval_retry_count`, `structured_prompt`
- `apps_involved`, `curated_research`, `retrieved_research`, `catalog_query_mode`
- `current_time_utc`, `user_timezone`
- `config.configurable.eval_model` (default: `gpt-4o-mini`)

**Escribe al estado:**
- `eval_feedback` — string con corrección específica si falló, `None` si pasó
- `eval_retry_count` — incrementado en cada fallo

**3 criterios de evaluación:**
1. Sin alucinaciones (claims consistentes con el contexto de la conversación)
2. Responde la pregunta real (coincide con `structured_prompt`)
3. Formato apropiado (sin JSON crudo, sin Markdown roto)

**Short-circuits:**
- `eval_retry_count >= 2` → fuerza pass (evita loops infinitos)
- Turno puro de chat (sin apps, sin research, sin catalog) → skip (nada verificable)

---

### 10. `research_curator_node`
**Archivo:** `research_curator.py`

Pipeline de post-procesamiento de research. Transforma el texto crudo de Tavily en una representación compacta que preserva TODOS los hechos únicos relevantes. Sin compresión con pérdida: clasifica y actúa, no resume.

**Lee del estado:**
- `retrieved_research`, `effort_level`
- `optimized_search_query`, `structured_prompt`
- `needs_fact_verification`
- `user_timezone`, `user_location`, `user_country_code`

**Escribe al estado:**
- `curated_research` — research procesado y enriquecido con timezone

**Pipeline de 8 fases:**

| Fase | Descripción |
|------|-------------|
| A | Segmentación adaptativa según `effort_level` y tamaño del research |
| B | Extracción paralela: cada chunk → bullets de información (LLM) |
| C | Dedup determinista: hash exacto + near-similarity (sin LLM, threshold 0.85) |
| D | Clasificación batch (LLM): `keep` / `merge` / `conflict` por cada bullet |
| E | Aplicar grupos: construir lista refinada |
| E.5 | Ranking por relevancia (LLM, solo si `needs_fact_verification=True`) |
| F | Resolución de conflictos vía Tavily (solo cuando hay bullets en conflicto) |
| G | Verificación de hechos cruzando con nueva búsqueda Tavily (condicional) |
| H | Enriquecimiento temporal: convierte horarios UTC al timezone del usuario (Python puro) |

**Parámetros por effort tier:**

| Tier   | target_chunk | max_batches | ext_tokens |
|--------|-------------|-------------|------------|
| `low`  | 0 (pass-through) | 0      | 0          |
| `medio`| 10,000      | 8           | 800        |
| `high` | 10,000      | 12          | 1,000      |
| `max`  | 12,000      | 15          | 1,200      |

---

### 11. `memory_updater_node`
**Archivo:** `memory_updater.py`

Último nodo antes de END. Persiste un registro de decisión solo cuando el turno completó un workflow real. Evita ruido: turnos conversacionales, errores, y mensajes de cierre no se guardan.

**Lee del estado:**
- `requirement_level` — debe ser `"level_2"` para guardar
- `ranked_context` — debe estar presente
- `user_id`, `conversation_id`, `goal_id`, `apps_involved`
- `messages` (busca el último AIMessage como texto de decisión)

**Escribe al estado:**
- `decision_logged` — `True` si se persistió, `False` si se saltó

**Condición de guardado:** `requirement_level == "level_2"` AND `ranked_context` presente AND `user_id` presente. Los tres deben cumplirse.

---

### 12. `error_handler_node`
**Archivo:** `error_handler.py`

Nodo de recuperación de errores. Atrapa cualquier excepción que escape de un nodo wrapeado con `_safe_node` en el builder.

**Lee del estado:**
- `agent_error` — dict con `{node, exc, traceback}` inyectado por `_safe_node`

**Escribe al estado:**
- `messages` — agrega un AIMessage con un mensaje amigable en español

**Propósito:** garantiza que el cliente WebSocket nunca reciba un stack trace crudo. Loguea el error completo y retorna un mensaje genérico de "algo salió mal".

---

### 13. `workflow_planner_node`
**Archivo:** `workflow_planner.py`

Nodo deliberativo que corre entre `bigtools_inspector` y `responder`. Genera un plan de ejecución privado (nunca mostrado al usuario) basado en el tool mapping validado. Separa el razonamiento estructural de la síntesis de lenguaje natural que hace el `responder`.

**Lee del estado:**
- `apps_involved` — para decidir si hay algo que planear
- `validation_reports` — extrae el `tool_mapping` del reporte `bigtools` con `status="ok"`
- `structured_prompt` — intent del usuario en inglés
- `missing_variables` — parámetros que faltan para ejecutar
- `curated_research` — contexto externo adicional (primeros 600 chars)

**Escribe al estado:**
- `planning_trace` — texto plano con el plan paso a paso, o `None` si se saltó

**Skip conditions (retorna `{"planning_trace": None}`):**
- `apps_involved` vacío → turno de chat puro, nada que planear
- Sin reporte `bigtools` con `status="ok"` → la validación falló, el `responder` maneja el error

**Modelo:** `gpt-4o-mini`, `temperature=0` — razonamiento determinístico, sin creatividad.

**Output format (texto plano, una línea por paso):**
```
Step 1: [gmail] watch_inbox — listen for new emails with subject 'Factura'
Step 2: [google_sheets] append_row — write sender, subject, date to Sheet
RECOMMENDATION: Confirm which Gmail account to use (test@hypershifu.com assumed).
```

---

### 14. `req_investigator_node`
**Archivo:** `app/agent/shifu_base_v1/graph/req_nodes.py`

Máquina de estados multi-turno para guiar al usuario a través de 6 niveles de investigación de requerimientos antes de crear un workflow. Despachado exclusivamente cuando `req_level` está presente en el estado (seteado por `semantic_intake` al detectar `intent == "create_workflow"`).

El estado persiste entre turnos vía el checkpointer de MongoDB — no se usa `interrupt()`.

**Lee del estado:**
- `req_level` — determina qué sub-función ejecutar
- `req_plan`, `req_goal`, `req_apps_scope`, `req_trigger_type`, `req_trigger_event`
- `req_enhancements` — propuestas del nivel anterior
- `apps_involved`, `user_id`, `conversation_id`, `user_email`
- `messages` — para extraer respuestas del usuario

**Escribe al estado:**
- `req_level` — avanza al siguiente nivel (o `None` al completar)
- `req_plan` — plan estructurado JSON extraído en L2
- `req_goal`, `req_apps_scope`, `req_trigger_type`, `req_trigger_event` — extraídos en L2
- `req_gaps` — preguntas pendientes de responder
- `req_preflight_passed`, `req_preflight_failures` — resultado del check en L3
- `req_enhancements` — propuestas de mejora (L3 pasa → L5)
- `req_accepted_enhancements` — selecciones del usuario (L5)
- `req_workflow_id` — ID del workflow creado en MongoDB (L5)
- `req_deployed` — `True` cuando el workflow fue creado exitosamente
- `structured_prompt` — contenido para que el `responder` entregue al usuario

**Niveles de la máquina de estados:**

| `req_level` | Sub-función | Qué hace | Siguiente nivel |
|-------------|-------------|----------|----------------|
| `1` | `_ask_understanding` | LLM genera 3-4 preguntas sobre objetivo, trigger, apps, resultado | `2` |
| `2` | `_plan_and_ask_gaps` | LLM 1: extrae `req_plan` en JSON. LLM 2: genera preguntas de gaps (cuentas, frecuencia, errores) | `3` |
| `3` | `_run_preflight` | Check catálogo + check auth OAuth. Pasa → propuestas mejoras → L5. Falla → preguntas correctivas → loop L3 | `5` ó `3` (loop) |
| `5` | `_deploy` | Parsea enhancements aceptados, llama `create_workflow()` + `add_step_to_workflow()` + `set_workflow_frequency()` en MongoDB | `None` (fin) |

**Nota sobre `_run_preflight` (L3):**
- Check de catálogo: normaliza app names a `lowercase_underscore` antes de comparar con `get_catalog_apps()`. Si el catálogo está vacío (entorno dev), omite ambos checks.
- Check de auth: consulta `user_connected_accounts` en MongoDB; solo apps que pasaron el check de catálogo son verificadas. Status usables: `"active"` y `"needs_refresh"`.

**Integración con `responder`:**
`req_investigator` escribe en `structured_prompt`. El `responder` detecta `req_level is not None` y usa la directiva `REQUIREMENTS FLOW` para relayar el contenido fielmente al usuario (sin análisis propio ni checks de disponibilidad).

**LLM:** `gpt-4o-mini`, `temperature=0`, `max_tokens=800`, con retry 3 intentos.

---

## Patrones comunes

### `validation_reports` reducer
`catalog_checker`, `auth_validator`, y `bigtools_inspector` escriben al mismo campo `validation_reports`. Es seguro porque LangGraph usa un reducer de tipo `list` que concatena — nunca sobreescribe. Todos los nodos paralelos retornan una lista, no un valor escalar.

### `_safe_node` wrapper
El builder envuelve `semantic_intake`, `bigtools_inspector`, y `responder` en `_safe_node(fn, name)`. Si el nodo lanza una excepción, `_safe_node` captura el error, escribe `agent_error` al estado, y devuelve el control al grafo que enruta a `error_handler`.

### DEV_MODE
Todos los nodos imprimen cajas de debug ASCII cuando `SHIFUDEV_MODE=true` en el `.env`. Esto incluye outputs intermedios, decisiones de routing, y métricas de cada fase.
