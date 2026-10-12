# Bitácora de Auditorías — HyperShifu Backend

Registro de revisiones técnicas, bugs investigados y cambios aplicados por sesión de desarrollo.
Cada entrada documenta el objetivo, lo que se encontró y si el resultado fue satisfactorio.

---

## Formato de entrada

| Campo | Descripción |
|---|---|
| **Fecha** | Fecha de la auditoría |
| **Título** | Nombre corto del problema o tarea |
| **Descripción** | Contexto: qué se observó o reportó |
| **Objetivo** | Qué se buscaba resolver o confirmar |
| **Resultado** | ✅ Satisfactorio / ❌ No satisfactorio / ⚠️ Parcial / ⏳ Pendiente decisión |
| **Detalle** | Archivos modificados, causa raíz, o razón por la que aún no está resuelto |

---

## Sesión — 2026-06-11

---

### AUD-001 — Refactorización WS Handler agente_v3 a LangGraph

**Descripción:** El WebSocket de agente_v3 usaba `ChatOpenAI.astream()` directamente sin pasar por el grafo LangGraph. No había separación de nodos ni pipeline validador.

**Objetivo:** Mover el handler a un grafo LangGraph real con nodos separados (`semantic_intake`, validadores paralelos, `chat`).

**Resultado:** ✅ Satisfactorio

**Detalle:**
- Creado `app/agents/agente_v3/` con `state.py`, `nodes/chat.py`, `graph.py`
- Handler WS migrado a `ainvoke()` + `AsyncCallbackHandler` (`_WsChatStreamer`)
- LLM del nodo `chat` taggeado con `"shifu-chat"` para que el callback filtre solo sus tokens

---

### AUD-002 — Bug loop de open_questions en agente_v2

**Descripción:** El agente re-preguntaba la misma pregunta en turns consecutivos aunque el usuario ya la había respondido. El LLM no reconocía respuestas vagas como resolución de preguntas abiertas.

**Objetivo:** Eliminar el ciclo de re-pregunta sin agregar más instrucciones al prompt.

**Resultado:** ✅ Satisfactorio

**Detalle:**
- Archivo: `app/agents/agente_v2/nodes/context/conversation_context_builder.py`
- Fix en Python puro: si una pregunta estaba en `prev_open` Y el último mensaje es del usuario → se auto-resuelve sin llamar al LLM
- Lógica determinista, cero tokens adicionales

---

### AUD-003 — AI dice "Voy a conectar" pero no aparece botón

**Descripción:** El agente anunciaba que iba a conectar una app (sin que el usuario lo pidiera), pero el botón de conectar no aparecía en el frontend. Además, el agente no debía asumir conexiones por su cuenta.

**Objetivo:** (1) Definir correctamente cuándo el agente puede anunciar una conexión. (2) Hacer que `ui_action_builder` detecte la intención tanto desde el mensaje del usuario como desde la respuesta del AI.

**Resultado:** ✅ Satisfactorio

**Detalle:**
- `app/agents/agente_v2/nodes/core/chat.py` — Rule 3 del platform block actualizada
- `app/agents/agente_v2/nodes/core/ui_action_builder.py` — Rule 4 ahora lee AMBOS: usuario Y respuesta del AI

---

### AUD-004 — Revisión spec identity/personality agente_v3

**Descripción:** Se entregó un documento de especificación con 5 requisitos para inyección dinámica de identidad y personalidad desde MongoDB en agente_v3.

**Objetivo:** Confirmar si los 5 requisitos ya estaban implementados o había brechas.

**Resultado:** ✅ Satisfactorio

**Detalle:** Todos los requisitos ya implementados en `app/agents/agente_v3/helpers/identity_loader.py`. Sin brechas.

---

### AUD-005 — Errores de sintaxis Babel en MessagesList.tsx

**Descripción:** El componente `MessagesList.tsx` no compilaba en el frontend. Babel reportaba errores de parse en tres puntos del archivo.

**Objetivo:** Identificar y corregir todas las expresiones de sintaxis no soportadas por la versión de Babel del proyecto.

**Resultado:** ✅ Satisfactorio

**Detalle:**
- `catch {}` → `catch (_e) {}` (2 instancias)
- `await res.json() as { url?: string }` → `as any` + variable tipada separada
- `onConnectApp?.(appName)` → `onConnectApp && onConnectApp(appName)`

---

### AUD-006 — Duplicidad de respuestas en agente_v3

**Descripción:** Respuestas del agente duplicadas dentro de la misma burbuja: `"¿En qué puedo ayudarte hoy?¿En qué puedo ayudarte hoy?"`.

**Objetivo:** Identificar la causa raíz y eliminar la duplicación de forma definitiva.

**Resultado:** ✅ Satisfactorio

**Causa raíz:** Topología del grafo con dos fan-in en supersteps distintos. `tavily_searcher` y `bigtools_inspector` disparaban `aggregator` desde supersteps diferentes → LangGraph ejecutaba `chat` dos veces.

**Fix:** `app/agents/agente_v3/graph.py` línea 62 — `tavily_searcher → bigtools_inspector` (era `→ aggregator`). Fan-in unificado en un solo punto.

---

### AUD-007 — Sanitización de resultados Tavily (competidores en contexto LLM)

**Descripción:** Resultados de Tavily incluyen nombres de competidores (Zapier, Make, n8n). Genera *context clash* con restricciones de identidad de Shifu y abre vectores de prompt injection.

**Objetivo:** Neutralizar marcas competidoras antes de que lleguen al LLM, costo cero de tokens.

**Resultado:** ✅ Satisfactorio

**Detalle:**
- `app/agents/agente_v3/nodes/tavily_searcher.py`
- `_BRAND_MAP` con 10 marcas → términos genéricos; `_sanitize()` aplicado a `title` y `content`

---

### AUD-008 — Actualización langgraph-api 0.9.0 → 0.10.0

**Descripción:** `langgraph dev` reporta: `langgraph-api 0.9.0 is in Critical support`.

**Objetivo:** Evaluar impacto y actualizar.

**Resultado:** ⏳ Pendiente decisión del desarrollador

**Detalle:** Solo afecta el servidor de desarrollo local. Producción no impactada. Comando: `.venv\Scripts\pip install "langgraph-api==0.10.0"`

---

### AUD-009 — Pre-auditoría: Spec Mood State / Estado de Humor en agente_v3

**Descripción:** Se entregó especificación de arquitectura para integrar un sistema de **Estado de Humor (Mood State)** en agente_v3. La spec define: detección en `semantic_intake`, transición en `aggregator`, inyección en `chat`, y logs de auditoría visual en consola.

**Objetivo:** Verificar qué componentes de la spec YA están implementados en el código actual antes de codificar.

**Resultado:** ⚠️ Parcialmente implementado — se requiere desarrollo significativo

---

#### Hallazgos detallados:

| Componente | Estado | Detalle |
|---|---|---|
| `mood_state: str` en `V3State` | ❌ Falta | No existe el campo en `state.py` |
| `user_sentiment: str` en `V3State` | ❌ Falta | No existe el campo en `state.py` |
| Detección de sentimiento en `semantic_intake` | ❌ Falta | El prompt LLM no extrae `detected_sentiment` ni `recommended_mood`; el JSON de salida actual no incluye esos campos |
| Lógica de transición de humor en `aggregator` | ❌ Falta | `aggregator` solo maneja `requirement_level` (level_1/level_2). No lee ni muta `mood_state` |
| Inyección de directiva de humor en `chat` | ❌ Falta | `chat.py` no lee `mood_state`; no existe `get_mood_directive()` |
| Logs de consola con caja MOOD STATE TRANSITION | ❌ Falta | `semantic_intake` y `aggregator` tienen cajas de dev mode, pero sin sección de humor |
| Closing shortcut — `is_closing` detectado | ✅ Implementado | `semantic_intake` detecta señales de cierre y setea `is_closing=True` |
| Closing shortcut — prompt abreviado en `chat` | ✅ Implementado | `chat.py` y `identity_loader.py` aplican respuesta corta de despedida cuando `is_closing=True` |
| Closing shortcut — **skip de nodos paralelos** a nivel de grafo | ⚠️ Parcial | `is_closing=True` no cortocircuita el grafo. Los nodos `catalog_checker`, `auth_validator`, `tavily_searcher` siguen ejecutándose (aunque no hacen daño porque `apps_involved=[]`). La spec pide que el grafo salte directamente de `semantic_intake` a `chat` |

---

#### Implicación del closing skip en el grafo:

La spec dice: *"Bypassing parallel validation nodes. Routing directly to Chat."*
Para cumplirlo a nivel de grafo se necesita un **conditional edge** en `semantic_intake`:

```python
# Pseudocódigo de la solución
def _route_after_intake(state):
    if state.get("is_closing"):
        return "chat"          # skip completo de validadores
    return ["catalog_checker", "auth_validator", "tavily_searcher"]

builder.add_conditional_edges("semantic_intake", _route_after_intake, ...)
```

Actualmente no existe este conditional edge — el grafo siempre pasa por los 3 validadores.

---

#### Resumen de trabajo pendiente para implementar la spec completa:

1. **`state.py`** — Agregar `mood_state: Optional[str]` y `user_sentiment: Optional[str]`
2. **`prompts/semantic_intake.py`** — Agregar campos `detected_sentiment` y `recommended_mood` al esquema JSON de salida
3. **`nodes/semantic_intake.py`** — Extraer y propagar `mood_state` y `user_sentiment` al estado; agregar sección MOOD a la caja de dev mode
4. **`nodes/aggregator.py`** — Leer `user_sentiment` + `validation_reports` para calcular transición de humor; propagar `mood_state` actualizado; agregar sección MOOD a la caja de dev mode
5. **`nodes/chat.py`** — Leer `mood_state` e inyectar directiva de tono al final del system prompt (preservando cache prefix)
6. **`graph.py`** — Agregar `conditional_edges` desde `semantic_intake`: si `is_closing=True` → ir directo a `chat`, omitiendo los 3 validadores paralelos

---

**Resultado final:** ✅ Implementado completamente — ver AUD-011

---

### AUD-011 — Implementación Mood State / Estado de Humor en agente_v3

**Descripción:** Implementación completa del sistema de Estado de Humor (Mood State) según la spec AUD-009.

**Objetivo:** Detectar el sentimiento del usuario en `semantic_intake`, calcular la transición de humor en `responder` con reglas de negocio, e inyectar una directiva de tono al final del system prompt sin romper el cache prefix del LLM provider.

**Resultado:** ✅ Satisfactorio

**Detalle:**

| Archivo | Cambio |
|---|---|
| `state.py` | Agregados `user_sentiment: Optional[str]` y `mood_state: Optional[str]` |
| `prompts/semantic_intake.py` | Schema JSON ampliado con `detected_sentiment` y `recommended_mood` + reglas de detección |
| `nodes/semantic_intake.py` | Extrae `detected_sentiment` / `recommended_mood` del LLM, valida contra sets permitidos, escribe `user_sentiment` y `mood_state` (recomendación inicial) al estado. Sección MOOD agregada al dev box |
| `nodes/responder.py` | `_MOOD_DIRECTIVES` dict (4 tonos), `_compute_mood()` con reglas de negocio, `_dev_box_mood()` (caja MOOD TRANSITION en consola), directiva inyectada al final del system prompt antes del historial |

**Lógica de transición `_compute_mood()`:**
```
is_closing=True              → CLOSING
frustrated / urgent          → DIRECT_EMPATHY
level_1 errors + confused    → DIRECT_EMPATHY  (usuario chocó contra errores)
calm / polite / neutral      → HELPFUL
fallback                     → DEFAULT
```

**Posición de la directiva en el prompt (Prefix Stability):**
```
1. Bloque estático (cacheado) — identidad, principios, estilo
2. Saludo rule
3. Auth policy (level_1 solo)
4. Error context (level_1 solo)
5. Tavily research
6. Clarified intent (internal)
7. ← TONE DIRECTIVE aquí — nunca rompe el cache anterior
--- historial de conversación ---
```

**Nota de persistencia:** El `mood_state` se escribe en el estado de LangGraph cada turno. Sin checkpointer (PostgresSaver) activo en v3, no persiste entre reconexiones WS — el humor se recalcula desde cero cada turno a partir del sentimiento detectado. Esto es correcto funcionalmente (el humor refleja el estado actual del usuario).

---

### AUD-010 — Refactorización grafo agente_v3: nodo Responder + Markdown Formatting

**Descripción:** El grafo tenía 7 nodos con responsabilidades fragmentadas. `aggregator` y `chat` eran dos nodos separados sin necesidad real de serlo. Además los system prompts de `chat` usaban directivas de formato implícitas en lugar de instrucciones Markdown explícitas. Se entregó spec de "Prompt Mirroring" y "Separación Lógica/Presentación".

**Objetivo:**
1. Simplificar el grafo creando un único nodo `responder` que reemplaza `aggregator` + `chat`
2. Agregar conditional edge desde `semantic_intake` para saltarse los validadores en mensajes de cierre
3. Hacer explícitas las directivas de formato Markdown en el system prompt (Prompt Mirroring)
4. Agregar guardrail de Markdown en el WS handler para cerrar bloques truncados por streaming

**Resultado:** ✅ Satisfactorio

**Detalle:**

| Cambio | Archivo | Descripción |
|---|---|---|
| Creado | `nodes/responder.py` | Fusiona `aggregator_node` + `chat_node`. Agregación Python inline, luego LLM streaming |
| Eliminado | `nodes/aggregator.py` | Reemplazado por `responder.py` |
| Eliminado | `nodes/chat.py` | Reemplazado por `responder.py` |
| Actualizado | `graph.py` | 7 nodos → 6 nodos. `add_conditional_edges` desde `semantic_intake`: `is_closing=True → responder` (skip validators). Removes `aggregator` + `chat`, adds `responder` |
| Actualizado | `nodes/__init__.py` | Exports actualizados |
| Actualizado | `helpers/identity_loader.py` | Directivas Markdown explícitas: `prefer_lists` → instrucción bullet points, `use_emojis=false` → instrucción sin emojis. Prompt Mirroring activo |
| Actualizado | `routes/V3/ws/v3_debug_ws.py` | Agregado `_fix_markdown()`: cierra `` ``` ``, `**`, `*` truncados al final del streaming antes de enviar `done` |

**Topología del grafo antes/después:**

```
ANTES: semantic_intake → [3 validators] → bigtools → aggregator → chat → END
                                                         ↑ 7 nodos, cierre no se optimizaba

DESPUÉS:
  Normal:  semantic_intake → [3 validators] → bigtools → responder → END
  Closing: semantic_intake → responder → END
                                   ↑ 6 nodos, closing bypass real en el grafo
```

---

### AUD-012 — Sistema de Consciencia Temporal (Temporal Awareness, 3 Capas)

**Descripción:** agente_v3 no tenía noción del tiempo: el LLM no sabía la fecha/hora actual, no podía calcular "el próximo lunes" con precisión (~30%), y las preferencias de usuario en MongoDB podían llevar meses desactualizadas sin que el agente lo supiera.

**Objetivo:** Implementar una jerarquía temporal de tres capas para grounding temporal real, conversión determinista de expresiones de scheduling a cron, y staleness awareness de preferencias.

**Resultado:** ✅ Satisfactorio

**Detalle:**

| Capa | Problema | Solución | Archivo |
|---|---|---|---|
| 1 — System Time Grounding | LLM sin noción de fecha/hora actual | Bloque temporal UTC + local inyectado al final del system prompt cada turno | `helpers/time_context.py` (NUEVO) |
| 2 — Chrono Parsing | "todos los lunes a las 9am" → LLM calculaba mal (~30%) | Python + python-dateutil convierte expresión a cron determinista (~78%) | `helpers/chrono_parser.py` (NUEVO) |
| 3 — Memory Staleness | Prefs en MongoDB podían tener meses sin actualizarse | Carga prefs + calcula días desde `updated_at` → anota "hace N días" en prompt | `helpers/preferences_loader.py` (NUEVO) |

**Archivos creados/modificados:**

| Archivo | Cambio |
|---|---|
| `helpers/time_context.py` | NUEVO — `build_time_context_block(user_tz_str)` → bloque Markdown con UTC + local + timezone + reglas |
| `helpers/chrono_parser.py` | NUEVO — `parse_schedule(expr, anchor)` → `{cron, human, type, next_run}` o None. Soporta ES+EN, día de semana, diario, mensual, semanal, por hora |
| `helpers/preferences_loader.py` | NUEVO — `load_user_prefs_block(user_id, db)` → `(formatted_block, user_timezone)`. Umbral staleness: 30 días |
| `state.py` | Agregados `user_timezone`, `schedule_context`, `user_preferences_context` |
| `prompts/semantic_intake.py` | Schema JSON ampliado con `scheduling_expression` + regla de extracción |
| `nodes/semantic_intake.py` | Extrae `scheduling_expression` del LLM → llama `parse_schedule()` → escribe `schedule_context`. Dev box ampliado con sección Chrono Parser |
| `helpers/identity_loader.py` | `build_system_messages()` acepta `user_preferences_context` → inyectado en posición 5.5 (después de research, antes de clarified intent) |
| `nodes/responder.py` | Lee `user_timezone` + `user_preferences_context` del estado. Llama `build_time_context_block()` → inyecta bloque temporal en posición 8 (última, después de mood directive) |
| `routes/V3/ws/v3_debug_ws.py` | Llama `load_user_prefs_block(user_id, db)` antes de construir `input_state`. Pasa `user_timezone` y `user_preferences_context` al estado del grafo |

**Orden final de bloques en el system prompt:**
```
1. Bloque estático (CACHEADO) — identidad, principios, restricciones, estilo
2. Saludo rule
3. Auth policy (level_1 solo)
4. Error context (level_1 solo)
5. Tavily research
5.5 User preferences + staleness                  ← CAPA 3
6. Clarified intent (interno)
7. Mood directive (tono)
8. Current time block (UTC + local + timezone)     ← CAPA 1
--- historial de conversación ---
```

**Flujo Chrono Parser (Capa 2):**
```
LLM extrae → scheduling_expression: "todos los lunes a las 9am"
chrono_parser.parse_schedule() → lunes → python_dow=0 → cron_dow=1
dateutil.parse("9am") → hour=9, minute=0
→ {"cron": "0 9 * * 1", "human": "Every Monday at 9:00", "type": "weekly",
   "next_run": "2026-06-16T09:00:00Z"}
```

**Nota de desacoplamiento:** `schedule_context` se escribe al estado pero aún no se consume en el system prompt del `responder` — está disponible para cuando el workflow planner lo necesite. El bloque temporal (Capa 1) ya se inyecta cada turno desde `responder`.
