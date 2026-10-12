# MultiAgente — Análisis Técnico para Investigación

> Documento generado a partir del análisis completo del código en `app/agents/multiAgent/`.  
> Propósito: identificar qué estamos haciendo, qué funciona, y dónde hay oportunidades de mejora investigable.

---

## 1. Técnicas de Agente que Estamos Usando

### 1.1 LangGraph — State Machine Graph
El agente está construido sobre **LangGraph**, una librería de grafos de estado para flujos de conversación con LLMs. El grafo tiene 6 nodos con routing condicional:

```
context_loader → [discovery_summarizer?] → chat → [tool_executor ↔ chat loop] → reflection → memory_saver → END
```

**Nodos clave:**
- `context_loader` — carga 11 bloques de memoria en paralelo antes de cualquier llamada al LLM
- `chat_node` — invoca el LLM principal con el sistema prompt ensamblado
- `tool_executor` — ejecuta todas las tool calls en paralelo; puede regresar a `chat_node`
- `reflection_node` — post-evaluación async del turno (no bloquea la respuesta al usuario)
- `memory_saver` — persiste el turno en DB de forma async

**Términos a investigar:** `LangGraph state machine`, `LangGraph conditional edges`, `LangGraph MessagesState`

---

### 1.2 ReAct Loop (Reasoning + Acting)
El patrón **ReAct** (Yao et al. 2022) está implementado en el loop `chat → tool_executor → chat`. El LLM razona, emite tool calls, recibe resultados, y razona de nuevo. Bounded por **8 rondas máximas** para evitar loops infinitos.

**Términos a investigar:** `ReAct agent pattern`, `tool use loop LLM`, `agentic loop bounded iterations`

---

### 1.3 Reflection / Self-Evaluation
Después de cada turno, un segundo LLM (temperatura 0) evalúa la respuesta del agente en un **fire-and-forget async task**:
- Asigna score de importancia 0–1
- Detecta nuevas preferencias, metas, frustraciones del usuario
- Solo escribe a DB si `importance >= 0.7` (configurable por env var)
- Si detecta fallas, escribe a `agent_self_reflection` con `corrective_lesson`

**Términos a investigar:** `LLM self-reflection pattern`, `agent introspection`, `episodic memory importance scoring`

---

### 1.4 RAG — Retrieval-Augmented Generation
La memoria larga del usuario se divide en chunks semánticos con embeddings. Antes de cada turno, se hace búsqueda por similitud coseno para recuperar los 4 chunks más relevantes e inyectarlos en el sistema prompt.

**Modelo de embeddings:** `text-embedding-3-small` (OpenAI)  
**Scorer híbrido:** `0.45 × semántico + 0.35 × token overlap + 0.15 × marcadores + 0.05 × recencia`

**Términos a investigar:** `RAG conversational agent`, `chunked memory retrieval`, `hybrid semantic keyword scoring`

---

### 1.5 Cognitive Pass — Routing Multi-Señal
Un solo llamado LLM previo al chat (el "cognitive pass") clasifica simultáneamente:
- **Modo** (6 categorías): `conversacion_normal`, `programacion`, `planeacion`, `brainstorming`, `escritura_creativa`, `json_tools`
- **Temperatura derivada** del modo (0.2–1.0)
- **Categoría de contexto**: `self_contained`, `continuation`, `deep_context`
- **Requerimientos de memoria**: qué bloques de contexto inyectar
- **Intent flags**: si necesita web search, si es discovery de proceso
- **Contexto behavioral**: si el usuario saluda, nivel de familiaridad, contexto social

**Términos a investigar:** `multi-signal LLM classification`, `single-pass intent routing`, `cognitive routing agent`

---

### 1.6 Semantic Router — Tool Binding por Embeddings
Antes de pasar las tools al LLM, se calcula similitud coseno entre el mensaje del usuario y las descripciones de cada herramienta. Solo se pasan herramientas al LLM si superan un umbral:
- Umbral normal: **0.38**
- Umbral permisivo (si la diferencia entre top-1 y top-2 es >= 0.05): **0.33**

Esto reduce tokens y costo al evitar function-calling innecesario en consultas simples.

**Términos a investigar:** `semantic router tool selection`, `embedding-based tool gating`, `dynamic tool binding`

---

### 1.7 Process Discovery State Machine
El agente tiene un modo especial para descubrir y estructurar automatizaciones. Es una **máquina de estados de 7 etapas**:

| Etapa | Objetivo |
|---|---|
| `intent_detection` | Clarificar qué quiere lograr el usuario |
| `context_discovery` | Mapear apps involucradas, frecuencia, trigger |
| `tool_exploration` | Dry-run de herramientas para validar factibilidad |
| `structuring` | Construir resumen del flujo completo |
| `refinement` | Edge cases, validaciones |
| `completed` | Confirmar y guardar |

**Términos a investigar:** `conversational process discovery`, `dialog state machine LLM`, `automation discovery agent`

---

### 1.8 Deterministic Intent Gates
Para evitar que el LLM tome decisiones frágiles sobre routing, ciertas intenciones se detectan con **código Python determinístico** (en `intent_gates.py`):
- `is_resume_signal(text)` — frases exactas de reanudación
- `is_crud_intent(text)` — verbos de operación (borrar, modificar, listar)
- `looks_like_discovery_answer(text)` — formas cortas de respuesta (afirmación, hora, email)

**Términos a investigar:** `hybrid symbolic-neural routing`, `deterministic intent gates`, `LLM guard rails`

---

## 2. Qué se Guarda en la Base de Datos

### 2.1 Conversación y Chat
| Colección | Contenido |
|---|---|
| `chat_messages` | Un doc por mensaje: `user_id`, `conversation_id`, `role`, `content`, `created_at` |
| `chat_context` | Un doc por conversación: `summary`, `title`, `message_count`, `updated_at`, `workflow_phase`, `proposed_plan` |

---

### 2.2 Identidad y Preferencias del Usuario
| Colección | Contenido |
|---|---|
| `user_preferences` | Doc dinámico por usuario. Cada preferencia incluye: `{value, confidence (0-1), source (explicit\|implicit\|temporary), updated_at}`. Campos ejemplo: `user_country`, `user_city`, `user_company`, `user_role`, `user_timezone`, `user_language`, `user_email_work`, `user_boss`, `user_name_pref`. También preferencias de cuentas conectadas: `gmail_preferred_account`. **Schema-less**: cualquier key-value puede guardarse. |

---

### 2.3 Memoria de Largo Plazo (Capas)
| Colección | Frecuencia de escritura | Contenido |
|---|---|---|
| `user_daily_diary` | 1 doc por usuario por día | Síntesis LLM de todos los resúmenes de conversación del día |
| `user_global_memory` | Rolling, cada 3 turnos | Síntesis de las últimas N entradas del diario (texto completo) |
| `user_global_memory_chunks` | Cada 3 turnos | Global memory dividida en chunks con embeddings + `source_date_range` |
| `user_summary_context` | Cada turno | Estado cognitivo actual: `current_focus`, `active_topics`, `open_problems`, `recent_decisions`, `project_state`, `turn_count` |
| `user_episodic_memory` | Solo cuando `importance >= 0.7` | Episodios significativos: tipo (`resolved_problem`, `key_decision`, `milestone`, `emotional_moment`, `completed_task`, `new_objective`, `identity_statement`), `topic`, `event`, `importance`, `created_at`, `relative_label` |
| `user_cognitive_profile` | Cada 7+ días O 15+ episodios nuevos | Perfil abstraído: `strategic_direction`, `long_term_goals`, `reasoning_style`, `decision_patterns`, `expertise_areas`, `growth_edges`, `persistent_concerns` |

---

### 2.4 Process Discovery y Automatizaciones
| Colección | Contenido |
|---|---|
| `process_sessions` | Sesión activa/completada: `session_id`, `status` (`in_progress\|waiting_for_oauth\|completed\|abandoned`), `current_stage`, `collected_information`, `conversation_log`, `pending_questions`, `tool_findings`, `validated_sections`, `idle_turns`, `last_interaction_at` |
| `processes` | Proceso documentado: `title`, `goal`, `problem`, `desired_outcome`, `business_context`, `involved_tools`, `actors`, `constraints`, `trigger_description`, `trigger_type`, `frequency`, `steps`, `process_summary`, `workflow_id`, `status (draft\|ready)` |
| `workflows` | Automatización ejecutable: `trigger` (tipo, descripción, frecuencia, schedule, condición), `steps`, `edge_cases`, `notifications`, `status (draft\|ready)` |

---

### 2.5 Observabilidad y Trazas
| Colección | Contenido |
|---|---|
| `agent_reasoning_trace` | Por turno: contexto (output del cognitive pass, suppress_flags, bloques inyectados), chat (modelo, temperatura, router top-3, tool_calls), tool_outcomes, reflection. **No guarda el texto del mensaje** (eso va en `chat_messages`) |
| `agent_self_reflection` | Solo cuando hay fallas detectadas: `self_eval` (quality, confidence, detected_failure, corrective_lesson), `mode`, `raw_eval_output` |
| `user_turn_log` | Debug liviano por turno: `mode`, `context_category`, `temperature`, `suppress_flags`, `integrations_connected`, `workflows_injected` |
| `user_feedback` | Thumbs up/down + comentarios del usuario (señales de calibración) |

---

### 2.6 Catálogo e Integraciones
| Colección | Contenido |
|---|---|
| `catalog_apps` | Apps disponibles en la plataforma: `name`, `nameApi`, `category`, `active`, `visible` |
| `user_connected_accounts` | Integraciones activas del usuario: `user_id`, `provider`, `account_id`, `status: "active"` |

---

## 3. Manejo de Estado del Agente por Situación

### 3.1 Estado Principal (ChatState — LangGraph MessagesState)

| Campo | Tipo | Descripción |
|---|---|---|
| `messages` | list | Historial de mensajes LLM (heredado de MessagesState) |
| `user_id`, `user_email`, `conversation_id`, `name` | str | Identidad del turno |
| `model_name`, `temperature` | str, float | Modelo y temperatura efectiva |
| `cognitive_mode` | dict | Salida completa del cognitive pass |
| `context_loaded` | bool | Flag de que la carga de contexto completó |
| `all_tools` | list | Herramientas disponibles (no serializado, se resetea por turno) |
| `needs_tool_call` | bool | Routing: si va a `tool_executor` o directo a `reflection` |
| `active_process_session` | dict | Doc completo de sesión si `discovery_active=True` |
| `discovery_stage` | str | Etapa actual del discovery |
| `discovery_active` | bool | True solo si este turno es discovery |
| `discovery_just_completed` | bool | True justo después de completar una sesión |
| `force_tools` | bool | Bypass del router semántico (web search o discovery) |
| `raw_history` | list | Historial sin filtrar (para discovery_summarizer) |
| `trace` | dict | Registro estructurado del turno, mutado por todos los nodos |
| `tool_outcomes` | list | `{tool, success, error_text, retry_attempted, fallback_used, ms}` |

---

### 3.2 Suppress Flags — Qué Contexto se Inyecta por Situación

El sistema decide dinámicamente qué bloques de contexto suprimir en el system prompt:

| Bloque | Se suprime cuando |
|---|---|
| `global_memory` | `needs_memory_context=False` Y no es consulta de historial |
| `conv_summary` | `needs_conv_summary=False` |
| `temporal_context` | `context_category == "self_contained"` |
| `summary_context` | `context_category == "self_contained"` |
| `cognitive_profile` | `context_category == "self_contained"` |
| `workflow_context` | `needs_workflow_context=False` |

**Resultado:** para preguntas simples y auto-contenidas (ej. "¿cuánto es 2+2?"), el sistema prompt se reduce drásticamente, ahorrando tokens.

---

### 3.3 Transiciones de Estado en Discovery

```
in_progress
    └─► waiting_for_oauth   (usuario necesita conectar una app)
            └─► in_progress  (una vez autenticado)
    └─► completed            (flujo exitoso)
    └─► abandoned            (idle_turns >= 3)
```

El campo `idle_turns` se incrementa cada vez que el agente retoma una sesión pero el usuario no responde a las preguntas de discovery. Al llegar a 3, se abandona automáticamente.

**Ventana de "recién completado":** 5 minutos. Dentro de esa ventana, el agente sabe que acaba de completar una sesión y puede hacer follow-up.

---

## 4. Cómo Estamos Planeando al Agente (Escenarios)

### 4.1 Planificación a Nivel de Turno
En `context_loader`, antes de cualquier LLM call, se ejecutan **11 cargas de memoria en paralelo** (asyncio.gather). El cognitive pass usa toda esa información para "planear" el turno: qué memoria inyectar, qué modo usar, qué herramientas activar.

### 4.2 Discovery como Planificación de Automatizaciones
El proceso de discovery es esencialmente un **planeador conversacional**:
- Cada etapa tiene preguntas específicas que reducen la ambigüedad
- El agente nunca da por hecho valores (frecuencia, cuenta destino, condición)
- El resultado final es un workflow ejecutable en `processes` y `workflows`

### 4.3 Lecciones del Pasado como Plan
La función `get_recent_lessons()` carga errores pasados del agente (`agent_self_reflection`) y los inyecta como "Lessons learned" en el sistema prompt. Esto es una forma de **planificación basada en experiencia previa** — el agente literalmente se dice a sí mismo qué no hacer.

### 4.4 Compactación de Transcript como Planeación de Contexto
Cuando el historial supera 15 líneas, `discovery_summarizer` comprime el transcript con un LLM antes del cognitive pass. La compresión preserva los últimos 3 mensajes intactos y anota los índices originales con `[N|covers:N-M]`.

---

## 5. Tipos de Búsqueda Implementados

### 5.1 Semántica (Vector)
- **Función:** `search_global_memory(query)`
- **Cómo:** cosine similarity sobre embeddings pre-computados en `user_global_memory_chunks`
- **Modelo:** `text-embedding-3-small`
- **Resultado:** top-4 chunks con `source_date_range`
- **Uso:** inyección de memoria larga en sistema prompt

### 5.2 Híbrida (Semántica + Keyword + Marcadores + Recencia)
- **Función:** `_score_messages()`
- **Pesos:** `0.45 semántico + 0.35 token overlap + 0.15 marcadores de importancia + 0.05 recencia`
- **Marcadores de importancia:** ~35 palabras clave en ES+EN (`decided`, `resolved`, `error`, `definitivo`, etc.)
- **Uso:** filtrar el historial de conversación a los 12 mensajes más relevantes para el cognitive pass

### 5.3 Semántica para Tool Selection (Router)
- **Función:** semantic router en `context_loader`
- **Cómo:** cosine similarity entre mensaje del usuario y descripciones de cada herramienta
- **Umbrales:** 0.38 normal, 0.33 permisivo
- **Uso:** decidir qué herramientas pasar al LLM (reducir context y costo)

### 5.4 Web Search (Tiempo Real)
- **Herramienta:** `tavily_search`
- **Activación:** cuando cognitive pass detecta `needs_web_search=True` o `force_tools=True`
- **Fallback inteligente:** si Tavily devuelve vacío → el LLM reformula la query y reintenta → fallback a herramienta complementaria (Wikipedia)
- **Uso:** clima, precios, noticias, tasas de cambio, info actual

### 5.5 Búsqueda en Apps Conectadas
- `search_emails(query)` — búsqueda nativa Gmail
- `search_drive(query)` — búsqueda nativa Google Drive
- `read_sheet_data(sheet_id, range)` — lectura directa Google Sheets
- **Uso:** etapa `tool_exploration` del discovery para validar disponibilidad de datos

### 5.6 Razonamiento LLM (Cognitive Pass)
- No es búsqueda en el sentido clásico, pero el LLM **razona** sobre el mensaje y clasifica 6+ dimensiones simultáneamente
- No usa keywords: usa comprensión semántica completa del contexto + historial
- **Términos a investigar:** `LLM-based intent classification`, `zero-shot routing`, `multi-label classification with LLMs`

---

## 6. Manipulación de Prompts y Razonamiento del Modelo

### 6.1 Arquitectura Modular del Sistema Prompt

El sistema prompt se ensambla dinámicamente en orden, bloque a bloque:

```
[1] Discovery Prompt (si discovery_active)
     ├── BASE_IDENTITY (siempre, ~200 tokens)
     ├── STAGE_GUIDANCE (solo la etapa actual)
     └── POLICIES (condicional: NO_EXECUTE, MULTI_ACCOUNT, TOOL_FINDINGS_AS_HYPOTHESES)
   O Shifu base role (si no es discovery)

[2] User Identity (siempre)
     └── País, ciudad, empresa, rol, timezone, idioma, email, jefe, nombre preferido

[3] Cognitive Profile (si existe Y context_category != "self_contained")
     └── strategic_direction, long_term_goals, reasoning_style, decision_patterns, etc.

[4] Memory Block (con suppress_flags)
     ├── Active Context (summary_context)
     ├── Temporal Context (gap label + diario + episodios recientes)
     ├── Long-Term Memory (resultados de búsqueda semántica)
     └── Integrations (apps conectadas + estado de auth)

[5] Workflows Block (si tiene workflows Y needs_workflow_context=True)

[6] Active Mode (verbosity, reasoning, style, temperature override)
```

### 6.2 Derivación de Temperatura por Modo

| Modo | Temperatura | Lógica |
|---|---|---|
| `conversacion_normal` | 0.7 | Balance creatividad/coherencia |
| `programacion` | 0.3 | Determinismo para código |
| `planeacion` | 0.5 | Estructura + algo de flexibilidad |
| `brainstorming` | 0.9 | Exploración creativa |
| `escritura_creativa` | 1.0 | Máxima creatividad |
| `json_tools` | 0.2 | Salida estructurada estricta |

### 6.3 Inyección de Comportamiento Social
- Si `short_reply=True` → instrucción explícita: `"RESPOND BRIEFLY"`
- Si `ask_followup=False` → instrucción: `"DO NOT ADD A GENERIC FOLLOW-UP"`
- El `social_context` (saludo, familiaridad, energía) informa tono: funcional / amigable / juguetón

### 6.4 Reglas Determinísticas Sacadas del Prompt (intent_gates.py)
Para evitar fragilidad LLM en decisiones de routing:
- `is_resume_signal(text)` — matching exacto de frases de reanudación
- `is_crud_intent(text)` — verbos de operación (delete, modify, list)
- `looks_like_discovery_answer(text, last_question)` — respuestas cortas (afirmación, hora, email, día)

**Por qué importa:** cada regla que se mueve del prompt al código es una regla que ya no puede alucinar el LLM.

### 6.5 Prompt de Discovery Modular (discovery_prompt.py)
- Cada etapa tiene su bloque de guía propio (no se inyectan todas a la vez)
- Políticas opcionales: `NO_EXECUTE`, `MULTI_ACCOUNT`, `TOOL_FINDINGS_AS_HYPOTHESES`
- Incluye ejemplos ES/EN por etapa (estructura few-shot implícita)
- `BASE_IDENTITY` es constante (~200 tokens) y nunca cambia

### 6.6 Lecciones Pasadas como Guía
`get_recent_lessons()` extrae `corrective_lesson` de `agent_self_reflection` y los inyecta en el prompt como "Lessons learned". El modelo recibe instrucciones derivadas de sus propios errores previos.

**Términos a investigar:** `prompt engineering modular systems`, `dynamic prompt injection`, `temperature calibration per task type`, `LLM behavioral steering`, `in-context learning from agent failures`

---

## 7. Qué es Manipulable y Escalable en el Código

### 7.1 Variables de Entorno (Config sin Deploy)

```bash
OPENAI_API_KEY
DIRECT_CHAT_MODEL          # default: gpt-4o-mini → swap a GPT-4o, Claude, Gemini
REFLECTION_MODEL           # default: gpt-4o-mini
REFLECTION_EPISODE_THRESHOLD   # default: 0.7 → ajustar sensibilidad de episodios
TEMP_CLASSIFIER_MODEL      # modelo para cognitive pass
V3_MEMORY_MODEL            # modelo para síntesis de memoria
MEMORY_EMBED_MODEL         # default: text-embedding-3-small
GLOBAL_MEMORY_REFRESH_TURNS    # default: 3 → cada cuántos turnos se refresca memoria global
GLOBAL_MEMORY_DAYS_WINDOW      # default: 14 → ventana de días para memoria global
COGNITIVE_MIN_EPISODES     # default: 15 → episodios mínimos para actualizar perfil cognitivo
COGNITIVE_MIN_DAYS         # default: 7 → días mínimos entre actualizaciones de perfil
```

### 7.2 Umbrales de Router (Calibrables Empíricamente)

```python
# semantic_router.py
THRESHOLD_NORMAL = 0.38       # umbral estándar
THRESHOLD_PERMISSIVE = 0.33   # umbral permisivo con margen
MIN_MARGIN = 0.05             # diferencia mínima top-1 vs top-2
TOP_K = 4                     # chunks recuperados en búsqueda semántica
```

> **AUDIT_INVENTORY:** estos valores no tienen análisis de distribución empírica documentado. Oportunidad de mejora.

### 7.3 Pesos del Scorer Híbrido (Ajustables)

```python
# memory_utils.py
WEIGHT_SEMANTIC = 0.45
WEIGHT_OVERLAP  = 0.35
WEIGHT_MARKERS  = 0.15
WEIGHT_RECENCY  = 0.05
```

> **AUDIT_INVENTORY:** los marcadores de importancia (keywords) solapan con el score semántico. Posible sesgo acumulado.

### 7.4 Límites de Seguridad (Bounds)

```python
MAX_TOOL_ROUNDS = 8          # máximo de rondas tool call antes de forzar respuesta
MAX_TOOL_RESULT_CHARS = 6000 # truncado de resultado de tool
MAX_RAW_MESSAGES = 30        # mensajes cargados sin filtrar
MAX_COGNITIVE_MESSAGES = 12  # mensajes para cognitive pass
MAX_COGNITIVE_TOKENS = 420   # output máximo del cognitive pass
MAX_COMPACTION_TOKENS = 500  # output máximo de compactación de transcript
MAX_EMBED_CHUNK_CHARS = 8000 # tamaño máximo de chunk para embedding
MAX_FEEDBACK_DOCS = 50       # docs de feedback para extracción de señales
```

### 7.5 Registro de Tools (Extensible sin Cambio de Código)

```python
get_all_bigtools()  # carga herramientas desde registro externo
```

Agregar una nueva herramienta al registro la expone automáticamente al semantic router y al LLM. No requiere modificar el grafo.

### 7.6 Sistema de Preferencias Schema-Less
`user_preferences` no tiene schema fijo. Cualquier key-value con `{value, confidence, source, updated_at}` puede persistirse. Permite añadir nuevas preferencias sin migraciones de DB.

### 7.7 Bloques de Prompt Modulares (Plug-and-Play)
Cada bloque del sistema prompt es una función/string independiente. Se pueden:
- Agregar nuevos bloques sin refactorizar el ensamblado
- Cambiar el orden de inyección
- A/B testear bloques por usuario o por modo

### 7.8 Políticas de Discovery (Condicionales)
Las políticas `NO_EXECUTE`, `MULTI_ACCOUNT`, `TOOL_FINDINGS_AS_HYPOTHESES` son strings que se inyectan o no dependiendo de la etapa. Se pueden agregar nuevas políticas sin modificar la lógica del grafo.

### 7.9 Async Task Pool (Escalable en I/O)
`context_loader` usa `asyncio.gather()` para 11 cargas en paralelo. `memory_saver` usa `asyncio.create_task()` + tracking set para escrituras background. El patrón escala horizontalmente sin cambios estructurales.

### 7.10 Observabilidad (Lista para Análisis)
`agent_reasoning_trace` captura por turno: cognitive pass output, router top-3, tool_calls, tool_outcomes, y reflection. Es la fuente de verdad para:
- Calibración de umbrales del router
- Detección de drift en importance scoring
- Análisis de qué herramientas se usan más y cuándo fallan
- A/B testing de cambios de prompt

---

## 8. Nodos del Grafo — Qué Hace Cada Uno

El grafo tiene **6 nodos** conectados por edges condicionales. El flujo principal es:

```
START
  └─► context_loader
        ├─► [discovery_summarizer]   ← solo si discovery_active=True
        │         └─► chat
        └─► chat
              ├─► tool_executor ──► chat   (loop, max 8 rondas)
              └─► reflection
                    └─► memory_saver
                          └─► END
```

---

### Nodo 1: `context_loader_node`
**Archivo:** [nodes/context_loader.py](app/agents/multiAgent/nodes/context_loader.py)  
**Posición en grafo:** Primer nodo, siempre se ejecuta.

**Qué hace:**
Es el nodo más complejo del sistema. Actúa como el "cerebro de preparación" antes de cualquier llamada al LLM principal. Su trabajo es ensamblar todo el contexto necesario para que el agente pueda responder de forma coherente y personalizada.

**Fases internas:**

**Fase 0 — Pre-carga (3 llamadas paralelas):**
- Carga el catálogo de apps disponibles (`catalog_apps`)
- Carga las integraciones activas del usuario (`user_connected_accounts`)
- Carga la sesión de discovery activa (`process_sessions`) — necesaria para que el cognitive pass sepa si hay una sesión pendiente antes de clasificar el intent

**Fase A — 12 operaciones en paralelo (`asyncio.gather`):**
1. `load_context` — resumen de la conversación actual (`chat_context`)
2. `load_preferences` — preferencias del usuario (`user_preferences`)
3. `get_structured_memory` — memoria global estructurada en JSON por secciones
4. `load_user_workflows` — workflows activos del usuario
5. `_cognitive_pass` — llamada LLM que clasifica modo, temperatura, memoria necesaria, intents (web search, discovery), contexto social — todo en un solo JSON
6. `get_recent_episodes` — últimos 5 episodios de `user_episodic_memory`
7. `get_last_interaction` — gap desde la última sesión (label: "hace 2 días", etc.)
8. `get_last_diary_entry` — última entrada del diario diario
9. `get_summary_context` — estado cognitivo activo del usuario (`user_summary_context`)
10. `get_cognitive_profile` — perfil cognitivo de largo plazo (`user_cognitive_profile`)
11. `get_recent_lessons` — lecciones correctivas de errores pasados (`agent_self_reflection`)
12. `get_calibration_signal` — señal de feedback negativo reciente (`user_feedback`)

**Compactación de transcript (dentro del cognitive pass):**
- Si el historial supera 15 líneas, lo compacta con un LLM antes de enviarlo al cognitive pass
- Preserva índices originales con anotación `[N|covers:N-M]`
- Mantiene los últimos 3 mensajes intactos

**Intent gates determinísticos (post cognitive pass):**
- `is_crud_intent` → fuerza `process_discovery_intent=False`
- `is_resume_signal` → fuerza `process_discovery_intent=True`
- `looks_like_discovery_answer` → fuerza `process_discovery_intent=True`

**Fase B — Carga de memoria global (estrategia dependiente del cognitive pass):**
- Si `needs_history_context=True` → carga narrativa completa (el usuario pregunta qué hemos hablado)
- Si `needs_memory_context=True` → búsqueda semántica top-4 chunks en `user_global_memory_chunks`
- Si `needs_memory_context=False` → no carga memoria global (suprime el bloque)

**Construcción del sistema prompt (exactamente 3 SystemMessages):**
1. **Identity block:** identidad de Shifu + políticas condicionales por modo + nombre del usuario + lecciones aprendidas + señal de calibración
2. **Memory/context block:** perfil de identidad + contexto cognitivo activo + contexto temporal + memoria global (semántica o narrativa) + integraciones + resumen de conversación + workflows. Cada sección con suppress_flags individuales.
3. **Active mode block:** modo, temperatura, verbosity, reasoning, style + reglas de comportamiento social (short_reply, ask_followup, energy, playful/functional) + fecha/hora actual en zona horaria del usuario

**Filtrado de historial:**
- Historial > 6 mensajes: scorer híbrido (semántico 0.45 + overlap 0.35 + marcadores 0.15 + recencia 0.05)
- Selecciona top-12 mensajes más relevantes + siempre los últimos 2

**Qué escribe al estado:**
- `messages` — 3 SystemMessages + historial filtrado
- `temperature` — derivada del modo
- `cognitive_mode` — output completo del cognitive pass
- `all_tools` — herramientas convertidas de BigTool a LangChain BaseTool (sin workflow tools)
- `force_tools` — True si web search detectado
- `active_process_session`, `discovery_active`, `discovery_stage`
- `raw_history` — historial sin filtrar (para discovery_summarizer)
- `trace` — primer bloque del reasoning trace (context section)

---

### Nodo 2: `discovery_summarizer_node`
**Archivo:** [nodes/discovery_summarizer.py](app/agents/multiAgent/nodes/discovery_summarizer.py)  
**Posición en grafo:** Condicional — solo cuando `discovery_active=True`.

**Qué hace:**
Compacta el historial completo de conversación en un bloque de progreso estructurado (`## Discovery progress`) para que el LLM de chat tenga contexto preciso del discovery sin necesitar leer 20-30 mensajes crudos.

**Lógica de presupuesto dinámico:**
Calcula un `density_score` combinando:
- Ratio de campos llenados en `collected_information` (peso 0.6)
- Profundidad de conversación: `min(num_mensajes / 20, 1.0)` (peso 0.4)

| Density score | Budget | max_tokens | chars/msg |
|---|---|---|---|
| < 0.25 | LOW | 150 | 150 |
| 0.25–0.55 | MEDIUM | 300 | 220 |
| ≥ 0.55 | HIGH | 500 | 300 |

**Formato de output:**
```
## Discovery progress
**Goal:** <qué quiere automatizar el usuario>
**Confirmed:** <hechos explícitamente confirmados>
**Last user answer:** <última respuesta sustantiva>
**Pending:** <qué falta resolver>
**Ambiguities:** <qué está poco claro>
```

**Inserción en mensajes:**
Lo inserta como SystemMessage justo después de todos los bloques de sistema (discovery prompt + memory blocks), antes de los últimos 4 mensajes de conversación. El LLM de chat ve exactamente: `[system msgs] [progress summary] [últimos msgs] [mensaje del usuario]`.

**No-op cuando:** historial tiene ≤ 6 mensajes (la slice de los últimos 4 ya es suficiente).

---

### Nodo 3: `chat_node`
**Archivo:** [nodes/chat.py](app/agents/multiAgent/nodes/chat.py)  
**Posición en grafo:** Nodo central — llama al LLM principal. Puede ser llamado múltiples veces en el mismo turno (loop con tool_executor).

**Qué hace:**
Es el único nodo que llama al LLM de chat (gpt-4o-mini por defecto). Su responsabilidad es decidir si pasa herramientas o no, llamar al modelo, y detectar si la respuesta contiene tool calls.

**Semantic Router (antes de la llamada LLM):**
1. Extrae el último texto del usuario
2. Calcula cosine similarity entre ese texto y las descripciones de cada herramienta (via embeddings `text-embedding-3-small`)
3. Decide si pasar tools al LLM:
   - `score >= 0.38` → bind tools (umbral normal)
   - `score >= 0.33` AND `margen top1 - top2 >= 0.05` → bind tools (umbral permisivo)
   - Cualquier otra cosa → LLM sin tools (respuesta plain text directa)
4. Si `force_tools=True` (web search detectado) → bypass del router, siempre bind tools

**Protección de loop (tool round limit):**
- Cuenta cuántos `AIMessage` con `tool_calls` hay en el historial
- Si `tool_rounds >= 8` → inyecta un `HumanMessage` de sistema forzando respuesta en lenguaje natural y llama al LLM sin tools

**Llamada al LLM:**
```python
ChatOpenAI(
    model=model_name,
    temperature=temperature,   # derivada del cognitive pass
    presence_penalty=0.3,      # reduce repetición de frases
    frequency_penalty=0.2,     # reduce repetición de tokens
)
```

**Qué escribe al estado:**
- `messages` — agrega el AIMessage de respuesta
- `needs_tool_call` — True si la respuesta tiene tool_calls (driving el routing condicional)
- `trace.chat` — modelo, temperatura usada, tool_rounds, router_top3, tools_bound, tool_calls (solo hashes de args)

---

### Nodo 4: `tool_executor_node`
**Archivo:** [nodes/tool_executor.py](app/agents/multiAgent/nodes/tool_executor.py)  
**Posición en grafo:** Condicional — solo cuando `needs_tool_call=True`. Regresa a `chat_node` formando un loop.

**Qué hace:**
Ejecuta todas las tool calls del último AIMessage en paralelo y devuelve los `ToolMessage` con los resultados.

**Ejecución paralela:**
```python
pairs = await asyncio.gather(*[_run_one(tc) for tc in tool_calls])
```
Cada tool se ejecuta de forma independiente y concurrente.

**Flujo por cada tool call:**

**Happy path:**
1. Busca la herramienta en `tool_map` por nombre
2. Llama `tool.ainvoke(tc["args"])`
3. Trunca el resultado a 6,000 caracteres si es muy largo
4. Devuelve `ToolMessage(content=result, tool_call_id=tc["id"])`

**Fallback de búsqueda vacía (Tavily / Wikipedia):**
Si el resultado de búsqueda está vacío:
1. LLM reformula la query (modelo ligero, max 80 tokens)
2. Reintenta la misma herramienta con la nueva query
3. Si sigue vacío → intenta la herramienta complementaria (`tavily ↔ wikipedia`)
4. Si todo falla → devuelve mensaje de error claro

**Auto-retry en errores de argumentos:**
Si la tool devuelve un error que no es de estado (not_found, unauthorized, etc.):
1. LLM analiza el error y los args originales
2. Produce args corregidos (JSON, max 300 tokens)
3. Reintenta una vez con los args corregidos
4. Si `unfixable=true` en la respuesta → devuelve error legible sin reintentar

**No reintenta errores de estado:** `not_found`, `not_connected`, `unauthorized`, `already_active`, etc. — son problemas de contexto, no de argumentos.

**Qué escribe al estado:**
- `messages` — agrega los ToolMessages
- `tool_outcomes` — lista de `{tool, success, error_text, retry_attempted, fallback_used, ms}` por cada ejecución
- `trace.tool_outcomes` — mismos outcomes acumulados en el reasoning trace

---

### Nodo 5: `reflection_node`
**Archivo:** [nodes/reflection.py](app/agents/multiAgent/nodes/reflection.py)  
**Posición en grafo:** Después de `chat_node` cuando la respuesta es texto plano (no tool calls). Antes de `memory_saver`.

**Qué hace:**
Evalúa el turno completo usando un segundo LLM (temperatura 0) en un **fire-and-forget async task**. No bloquea la respuesta al usuario — se lanza como `asyncio.create_task()` y el nodo retorna `{}` inmediatamente.

**Llamada LLM:**
- Modelo: `REFLECTION_MODEL` (default: gpt-4o-mini)
- Temperatura: 0 (máximo determinismo)
- Max tokens: 400
- Input: modo cognitivo + contexto de discovery (si aplica) + tool outcomes + texto del usuario + texto del AI

**Output JSON evaluado:**

| Campo | Descripción |
|---|---|
| `importance_score` | 0.0–1.0 — qué tan memorable es este turno |
| `importance_reason` | Explicación breve del score |
| `new_preferences` | Preferencias detectadas `{key: {value, confidence, source}}` |
| `new_goal` | Nuevo objetivo o proyecto detectado |
| `frustration` | Fricción o problema expresado por el usuario |
| `episode` | Episodio a guardar si importance >= umbral |
| `discovery_update` | Avance de etapa + nuevos findings (solo en discovery) |
| `self_eval` | Auto-evaluación de la respuesta del agente |

**Escrituras a DB:**
1. `user_preferences` — nuevas preferencias con confianza y fuente
2. `user_episodic_memory` — solo si `importance >= EPISODE_THRESHOLD` (default 0.7) y `episode.save=true`
3. `user_preferences` — objetivo detectado (`objetivo_detectado`) con conf 0.85
4. `user_preferences` — última frustración (`ultima_frustracion`) con conf 0.75
5. `agent_self_reflection` — solo si `detected_failure != "none"` → guarda la lección correctiva

**Si está en discovery mode (`discovery_active=True`):**
- Extrae `discovery_update` del JSON
- Actualiza `collected_information`, `tool_findings`, `validated_sections`, `pending_questions`, `ambiguities` en la sesión
- Si `stage_advance` avanza a `"validation"` → crea documento `workflows`
- Si `stage_advance == "completed"` → crea documento `processes`, marca workflow como ready, completa la sesión
- Si `stage_advance == "abandoned"` → abandona la sesión

**Self-eval (metacognición):**
Detecta 6 tipos de fallas:
- `tool_misuse` — la tool falló pero el AI dijo que tuvo éxito
- `identity_drift` — el AI no se identificó como Shifu
- `contradiction` — el AI contradijo un hecho conocido del usuario
- `lost_intent` — el AI respondió algo diferente a lo que se preguntó
- `hallucination` — el AI afirmó algo que no estaba en los datos
- `json_parse_fallback` — el JSON de reflexión fue inválido

Si detecta falla → escribe lección correctiva en `agent_self_reflection` → en el próximo turno esa lección se inyecta en el system prompt vía `get_recent_lessons`.

**Patch del trace:**
Una vez que termina la reflexión (async), parchea el doc de `agent_reasoning_trace` ya insertado por `memory_saver` con el resumen de lo que escribió.

---

### Nodo 6: `memory_saver_node`
**Archivo:** [nodes/memory_saver.py](app/agents/multiAgent/nodes/memory_saver.py)  
**Posición en grafo:** Último nodo antes de END. Siempre se ejecuta.

**Qué hace:**
Persiste el turno completo a todas las capas de memoria. Tiene escrituras **síncronas** (deben completarse antes de retornar) y **asíncronas** (background tasks que no bloquean).

**Escrituras síncronas (await — bloquean):**

1. **`save_message`** → `chat_messages`
   - Guarda la respuesta del AI (el mensaje del usuario ya fue guardado por el WebSocket antes de que corriera el grafo)

2. **`refresh_summary`** → `chat_context`
   - Regenera el resumen semántico de la conversación actual con un LLM
   - El diario diario depende de que esto esté fresco

3. **`last_temporal_block`** → `chat_context`
   - Persiste el bloque temporal del turno actual para que el endpoint REST `/memory-snapshot` pueda devolverlo sin esperar el WebSocket

4. **`user_turn_log`** → inserción directa
   - Log ligero de debug por turno: modo, categoría, temperatura, suppress_flags, workflows inyectados, integraciones conectadas, secciones de memoria usadas

**Escrituras asíncronas (background tasks — no bloquean):**

5. **`update_daily_diary`** → `user_daily_diary`
   - Sintetiza el resumen de la conversación de hoy en el diario diario
   - Dentro de esta función: si `turn_count % GLOBAL_MEMORY_REFRESH_TURNS == 0` → también actualiza `user_global_memory` y `user_global_memory_chunks` (re-embeds)

6. **`update_summary_context`** → `user_summary_context`
   - Reescribe el estado cognitivo activo del usuario con los últimos 6 mensajes como input
   - Campos: `current_focus`, `active_topics`, `open_problems`, `recent_decisions`, `project_state`

7. **`update_cognitive_profile`** → `user_cognitive_profile`
   - Solo se ejecuta si se cumplen ambas condiciones: `>= 15 episodios` Y `>= 7 días` desde la última actualización
   - Abstrae el perfil cognitivo del usuario a partir de todos los episodios acumulados

8. **`record_trace`** → `agent_reasoning_trace`
   - Inserta el reasoning trace del turno (sin el texto del mensaje/respuesta)
   - La reflexión parchea este doc después con su resumen vía `update_one(turn_id=...)`

**Anti-GC de tasks:**
Todas las background tasks se registran en un `set` a nivel de módulo (`_background_tasks`) para que el event loop no las elimine por garbage collection antes de que terminen.

---

### Resumen Visual de Responsabilidades

| Nodo | Llama LLM | Lee DB | Escribe DB | Es async |
|---|---|---|---|---|
| `context_loader` | Sí (cognitive pass + compactación) | Sí (11+ sources) | No | Sí (gather) |
| `discovery_summarizer` | Sí (resumen de discovery) | No | No | Sí |
| `chat` | Sí (LLM principal) | No | No | Sí |
| `tool_executor` | Sí (retry + reformulación) | No | No | Sí (gather por tool) |
| `reflection` | Sí (evaluador) | No | Sí (prefs, episodios, self-eval, discovery) | Fire-and-forget |
| `memory_saver` | No | No | Sí (messages, context, diary, summary, trace) | Sync + background |

---

## 9. Áreas con AUDIT_INVENTORY — Lo que el Código Mismo Marcó para Mejorar

| Tipo | Descripción |
|---|---|
| **INVESTIGATE** | Umbral del router (0.38/0.33/0.05) — sin análisis de distribución empírica |
| **INVESTIGATE** | Pesos del scorer híbrido (0.45/0.35/0.15/0.05) — sin sensitivity analysis |
| **INVESTIGATE** | Umbrales de densidad en discovery_summarizer (0.25 MEDIUM, 0.55 HIGH) — fórmula no documentada |
| **REPLACE** | `_IMPORTANCE_MARKERS` — keyword boost (0.15) solapa con score semántico (0.45), posible sesgo |
| **EXTRACT** | Resume signals, CRUD intent, Discovery answer — detectados por LLM en prompt, ya moviendo a intent_gates.py |
| **DEAD CODE** | `conversation_dynamics` en state.py — definido, nunca poblado ni leído |
| **UNDERUTILIZED** | `user_episodic_memory` — se escribe pero solo se lee para temporal_context; no se usa para routing ni weighting |

---

## 9. Términos para Investigar (Resumen Rápido)

```
LangGraph state machine
ReAct agent pattern
LLM self-reflection / introspection
Episodic memory importance scoring
RAG conversational agent
Chunked memory retrieval
Hybrid semantic-keyword scoring
Multi-signal LLM classification
Single-pass intent routing
Semantic router tool selection
Embedding-based tool gating
Dynamic tool binding
Conversational process discovery
Dialog state machine LLM
Hybrid symbolic-neural routing
Deterministic intent gates
LLM guard rails
Modular prompt engineering
Dynamic prompt injection
Temperature calibration per task type
LLM behavioral steering
In-context learning from agent failures
Agentic loop bounded iterations
Cognitive profile abstraction LLM
Schema-less preference store
Async parallel context loading
```
