# Reglas de construcción de agentes — HyperShifu

> Este documento es la fuente de verdad para crear cualquier agente nuevo que derive
> de `shifu_base_v1`. Léelo completo antes de escribir la primera línea de código.

---

## 1. Arquitectura de carpetas

```
app/
└── agent/
    ├── CONSTRUCTION_RULES.md   ← este archivo
    ├── shared/                 ← utilidades compartidas por TODOS los agentes
    │   ├── nodes/              ← nodos reutilizables (10 nodos base)
    │   ├── memory/             ← sistema de memoria cognitiva
    │   ├── context/            ← bloques de contexto (geo, tiempo, zona horaria)
    │   ├── helpers/            ← loaders de identidad, catálogo, preferencias
    │   ├── tools/providers/    ← bigtools (18 integraciones OAuth)
    │   └── utils/              ← app_resolver, log_utils
    │
    ├── shifu_base_v1/          ← agente base comercial (v1.0)
    │   ├── __init__.py
    │   ├── registry.py         ← punto de entrada único (init + get)
    │   └── graph/
    │       ├── __init__.py
    │       ├── state.py        ← ShifuState, ShifuInputState, ShifuOutputState
    │       ├── builder_standard.py
    │       ├── req_nodes.py    ← req_investigator: máquina de estados multi-turno
    │       └── tavily_subgraph.py
    │
    └── shifu_<nombre>/         ← nuevo agente derivado (sigue esta estructura)
        ├── __init__.py
        ├── registry.py
        └── graph/
            ├── __init__.py
            ├── state.py
            └── builder_<variante>.py
```

**Principios de carpetas:**
- `shared/` es de solo lectura para los agentes — se lee, no se modifica.
- Cada agente tiene su propio paquete Python aislado bajo `app/agent/`.
- Nunca poner código de un agente dentro de `shared/`. Si un nodo es genérico, se
  propone como PR a `shared/nodes/`; si es específico, vive dentro del agente.

---

## 2. Flujo del grafo base

### Pipeline estándar (turno normal)

```
START
  │
  ▼
goal_resolver          (nodo 1 — siempre primero)
  │
  ▼
memory_retriever       (nodo 2 — depende de goal_resolver)
  │
  ▼
semantic_intake        (nodo 3 — intake + routing)
  │
  ├──────────────────┬──────────────────┐
  ▼                  ▼                  ▼
catalog_checker   auth_validator   tavily_subgraph   (paralelos — fan-out)
  │                  │                  │
  └──────────────────┴──────────────────┘
                      │
                      ▼ (fan-in)
               bigtools_inspector
                      │
                      ▼
                  responder
                      │
                      ▼
            response_evaluator
                      │
                      ▼
             memory_updater
                      │
                      ▼
                     END
```

### Pipeline con planificador (turno con apps validadas)

```
bigtools_inspector → workflow_planner → responder → response_evaluator → memory_updater → END
```
`workflow_planner` genera un plan privado de ejecución entre `bigtools_inspector` y `responder`.

### Variante: requirements flow (`req_level ≠ None`)

```
semantic_intake [skip LLM] → req_investigator → responder → response_evaluator → memory_updater → END
```
`semantic_intake` detecta `intent == "create_workflow"` → setea `req_level=1`. En turnos siguientes, `req_level` persiste en el checkpointer de MongoDB y `semantic_intake` devuelve `_EMPTY_RESULT` sin llamar al LLM. El routing prioriza `req_level` por encima de todos los demás checks.

### Variante: turno de cierre (`is_closing = True`)

```
semantic_intake → responder → response_evaluator → memory_updater → END
```
Los tres nodos paralelos se omiten (sin llamadas a API).

### Variante: error en nodo crítico

```
semantic_intake / bigtools_inspector / responder  →  error_handler  →  END
(capturado por _safe_node, escribe agent_error en el estado)
```

### Selección de cuenta pendiente (`account_selection_resolved = True`)

```
semantic_intake → responder → response_evaluator → memory_updater → END
(saltea validators para evitar conflicto de escritura concurrente en fan-in)
```

---

## 3. Reglas de estado (ShifuState)

### Regla 1 — Propiedad exclusiva de campo

Cada campo del estado tiene exactamente un nodo que lo escribe. Dos nodos no pueden
escribir el mismo campo en el mismo super-paso, a menos que ese campo use un reducer.

### Regla 2 — Reducers obligatorios para escritura paralela

Los tres nodos paralelos (catalog_checker, auth_validator, tavily_subgraph) se
ejecutan en el mismo super-paso de LangGraph. Si un campo puede ser escrito por más
de uno, **debe** declararse con `Annotated` y un reducer.

| Patrón de campo | Cuándo usarlo | Ejemplo |
|-----------------|--------------|---------|
| `Annotated[List[dict], _reset_or_add]` | Varios nodos acumulan en lista; `None` limpia | `validation_reports` |
| `Annotated[Optional[Dict], _merge_dicts]` | Varios nodos aportan entradas a un dict | `selected_accounts`, `available_accounts` |
| `Optional[X]` sin Annotated | Solo UN nodo escribe este campo | `catalog_available_apps`, `user_connected_apps` |

### Regla 3 — Reset obligatorio al inicio de turno

`semantic_intake` debe resetear a `None` todos los campos de lista que podrían tener
datos del turno anterior:

```
"validation_reports": None   →  el reducer lo convierte en []
```

Sin este reset, los errores de un turno anterior aparecen en el turno siguiente.

### Regla 4 — Extender, nunca reemplazar

Un agente nuevo puede **agregar** campos a `ShifuState` para sus nodos propios.
Nunca eliminar ni renombrar un campo existente — rompe todos los nodos de `shared/`.

```python
# CORRECTO
class MiAgenteState(ShifuState):
    campo_nuevo: Optional[str] = None

# INCORRECTO — no hagas esto
class MiAgenteState(ShifuState):
    validation_reports = None  # eliminar o redefinir un campo existente
```

### Tabla de campos de ShifuState

| Campo | Tipo | Escritor | Annotated | Propósito |
|-------|------|----------|-----------|-----------|
| `messages` | `List` | WS handler + responder | sí (MessagesState) | Historial de mensajes |
| `user_id` | `Optional[str]` | WS handler | no | Identificador del usuario |
| `conversation_id` | `Optional[str]` | WS handler | no | Sesión activa |
| `model_name` | `Optional[str]` | WS handler | no | Modelo LLM seleccionado |
| `effort_level` | `Optional[str]` | WS handler | no | `low/medio/high/max` |
| `current_time_utc` | `Optional[str]` | WS handler | no | ISO 8601, fijado UNA vez por turno |
| `user_timezone` | `Optional[str]` | WS handler | no | IANA (America/Mexico_City) |
| `user_location` | `Optional[str]` | WS handler | no | Ciudad/país legible |
| `user_country_code` | `Optional[str]` | WS handler | no | ISO alpha-2 |
| `user_preferences_context` | `Optional[str]` | WS handler | no | Bloque de prefs cargado por handler |
| `structured_prompt` | `Optional[str]` | semantic_intake | no | Intento normalizado en inglés |
| `apps_involved` | `List[str]` | semantic_intake | no | Claves canónicas de apps |
| `needs_external_info` | `bool` | semantic_intake | no | Activa tavily_subgraph |
| `optimized_search_query` | `Optional[str]` | semantic_intake | no | Query limpia para tavily |
| `catalog_query_mode` | `Optional[Literal]` | semantic_intake | no | `list_available/list_connected/validate/add_account` |
| `is_closing` | `bool` | semantic_intake | no | Turno de cierre (adiós) |
| `user_sentiment` | `Optional[str]` | semantic_intake | no | `calm/polite/neutral/confused/frustrated/urgent` |
| `validation_reports` | `Annotated[List[dict], _reset_or_add]` | catalog_checker + auth_validator | **sí** | Reportes de validación acumulados |
| `available_accounts` | `Annotated[Optional[Dict], _merge_dicts]` | auth_validator | **sí** | Cuentas en espera de selección |
| `selected_accounts` | `Annotated[Optional[Dict], _merge_dicts]` | auth_validator | **sí** | Cuenta elegida por app |
| `catalog_available_apps` | `Optional[List[str]]` | catalog_checker | no | Apps en catálogo (modo list_available) |
| `user_connected_apps` | `Optional[Dict]` | auth_validator | no | Apps conectadas (modo list_connected) |
| `retrieved_research` | `Optional[str]` | tavily_subgraph | no | Texto de investigación para el LLM |
| `retrieved_sources` | `Optional[List[dict]]` | tavily_subgraph | no | Fuentes `{title, url, domain}` para UI |
| `curated_research` | `Optional[str]` | research_curator | no | Hechos comprimidos con conversión TZ |
| `goal_id` | `Optional[str]` | goal_resolver | no | Meta activa del usuario |
| `raw_memories` | `Optional[Dict]` | memory_retriever | no | 5 tipos de memoria sin filtrar |
| `ranked_context` | `Optional[str]` | memory_retriever | no | Contexto ordenado por relevancia |
| `decision_logged` | `bool` | memory_updater | no | Decisión persistida en DB |
| `requirement_level` | `Optional[Literal]` | responder | no | `level_1` (errores) / `level_2` (listo) |
| `mood_state` | `Optional[str]` | responder | no | Directiva de tono calculada |
| `agent_error` | `Optional[Dict]` | _safe_node wrapper | no | `{node, exc, traceback}` si hay excepción |
| `eval_retry_count` | `int` | response_evaluator | no | Contador de reintentos (máx 2) |
| `eval_feedback` | `Optional[str]` | response_evaluator | no | Instrucción de corrección |
| `planning_trace` | `Optional[str]` | workflow_planner | no | Plan privado de ejecución (nunca mostrado al usuario) |
| `req_level` | `Optional[int]` | semantic_intake (→1) + req_investigator (→2,3,5,None) | no | Nivel activo del requirements flow (`None` = inactivo) |
| `req_goal` | `Optional[str]` | req_investigator L2 | no | Objetivo en una línea del workflow a crear |
| `req_apps_scope` | `Optional[List[str]]` | req_investigator L2 | no | Apps necesarias según el plan |
| `req_trigger_type` | `Optional[str]` | req_investigator L2 | no | `webhook\|polling\|schedule\|manual` |
| `req_trigger_event` | `Optional[str]` | req_investigator L2 | no | Evento específico que dispara el workflow |
| `req_plan` | `Optional[dict]` | req_investigator L2 | no | Plan JSON completo: steps, gaps, confidence |
| `req_gaps` | `Optional[List[str]]` | req_investigator L2 | no | Preguntas pendientes de responder por el usuario |
| `req_preflight_passed` | `Optional[bool]` | req_investigator L3 | no | Resultado del check de catálogo + auth |
| `req_preflight_failures` | `Optional[List[str]]` | req_investigator L3 | no | Lista de problemas encontrados en preflight |
| `req_enhancements` | `Optional[List[str]]` | req_investigator L3 | no | Propuestas de mejora generadas al pasar el preflight |
| `req_accepted_enhancements` | `Optional[List[str]]` | req_investigator L5 | no | Mejoras que el usuario aceptó |
| `req_workflow_id` | `Optional[str]` | req_investigator L5 | no | ID del WorkflowModel creado en MongoDB |
| `req_deployed` | `bool` | req_investigator L5 | no | `True` cuando el workflow fue creado exitosamente |

---

## 4. Contrato de nodos

### Firma obligatoria

```python
async def nombre_del_nodo(state: ShifuState) -> dict:
    ...
    return {"campo_propio": valor}
```

Toda función de nodo es:
- `async` — nunca bloqueante
- Recibe el estado completo como argumento único
- Devuelve un `dict` con **solo los campos que este nodo escribe**
- Nunca devuelve el estado completo, nunca modifica el objeto `state` directamente

### Las 5 reglas de implementación de nodos

| # | Regla | Por qué |
|---|-------|---------|
| 1 | `state.get("campo")` siempre con default (`or []`, `or {}`, `or ""`) | Todos los campos son `Optional`, pueden ser `None` |
| 2 | Devolver solo campos propios en el `dict` | LangGraph hace merge; devolver el estado completo causa conflictos |
| 3 | Nunca `await asyncio.sleep()` o bloqueos en el event loop | Bloquea todos los nodos paralelos del mismo super-paso |
| 4 | Loguear con `logger.info()` al inicio y al final del nodo | Trazabilidad en LangSmith y logs locales |
| 5 | No capturar excepciones que quieras que lleguen a `_safe_node` | Si el nodo está envuelto, deja que el wrapper las maneje |

### Cuándo usar `_safe_node`

Envolver en `_safe_node` cuando el nodo hace alguna de estas operaciones:
- Llamada a API externa (OpenAI, integraciones OAuth, Tavily)
- Consulta a MongoDB (puede timeout o perder conexión)
- Operación que puede lanzar una excepción no controlada que pararía el grafo

```python
# En builder_<variante>.py
from app.agent.shifu_base_v1.graph.builder_standard import _safe_node

graph.add_node("mi_nodo", _safe_node(mi_nodo_fn, "mi_nodo"))
```

Nodos que NO necesitan `_safe_node`: lógica pura de Python sin I/O externo.

---

## 5. Utilidades compartidas — qué reusar

**Regla:** Nunca reimplementar lo que ya existe en `shared/`. Si lo necesitas, importa.
Si no existe, créalo en `shared/` para que lo hereden los próximos agentes.

| Función | Módulo | Uso |
|---------|--------|-----|
| `get_agent_identity()` | `shared/helpers/identity_loader.py` | Carga self_identity, principios, restricciones (cache 10 min) |
| `get_agent_personality()` | `shared/helpers/identity_loader.py` | Tono, saludo, política de auth (cache 10 min) |
| `build_system_messages()` | `shared/helpers/identity_loader.py` | Lista ordenada de `SystemMessage` lista para el LLM |
| `get_catalog_apps()` | `shared/helpers/catalog_cache.py` | Apps activas del catálogo (cache TTL, no leer Mongo directo) |
| `resolve_app_key()` | `shared/utils/app_resolver.py` | Normaliza nombre de app → clave canónica (`"sheets"` → `"google_sheets"`) |
| `build_geo_block()` | `shared/context/geo_context.py` | Bloque de contexto geográfico del usuario |
| `get_language_hint()` | `shared/context/geo_context.py` | Sugerencia de idioma/registro por país |
| `build_time_context_block()` | `shared/context/time_context.py` | Bloque UTC + hora local (**siempre el ÚLTIMO system message**) |
| `retrieve_memories()` | `shared/memory/memory_engine.py` | 5 tipos de memoria: goals, semantic, episodic, decisions, structured |
| `rank_memories()` | `shared/helpers/context_ranker.py` | Filtra y ordena memorias por relevancia → string para el responder |
| `load_user_prefs_block()` | `shared/helpers/preferences_loader.py` | Preferencias del usuario como bloque de texto |
| `parse_schedule()` | `shared/helpers/chrono_parser.py` | Resuelve expresión cron → próxima ejecución |

---

## 6. Reglas del builder (grafo)

### Reglas de routing

```
agent_error presente              →  route a error_handler → END                (prioridad 0)
req_level ≠ None                  →  route a req_investigator (skip fan-out)    (prioridad 1)
is_closing = True                 →  route directo a responder (skip fan-out)   (prioridad 2)
account_selection_resolved = True →  route directo a responder (skip fan-out)   (prioridad 3)
default                           →  fan-out: [catalog_checker, auth_validator, tavily_subgraph]
```

**Importante:** `req_level` debe chequearse ANTES de `is_closing` y `account_selection_resolved`. Si el usuario dice "adiós" mientras hay un `req_level` activo, el flujo de requirements tiene precedencia sobre el cierre.

### Reglas del fan-out / fan-in

Los nodos paralelos comparten un super-paso de `apply_writes` en LangGraph.
Durante ese super-paso, si dos nodos escriben el mismo campo sin reducer → **crash**.

Checklist antes de agregar un nodo al fan-out:
- [ ] ¿Qué campos escribe este nodo?
- [ ] ¿Alguno de esos campos también lo escribe otro nodo paralelo?
- [ ] Si sí → ¿tiene reducer `Annotated`?
- [ ] Si no → error garantizado en producción

### Timeout en subgrafos opcionales

Cualquier subgrafo opcional (investigación, tool call externo) debe tener un timeout
que degrade gracefully:

```
asyncio.wait_for(subgrafo.ainvoke(...), timeout=45.0)
```

Si el timeout salta → devolver campos vacíos, no lanzar excepción.

### `_safe_node` — qué captura

Captura cualquier excepción que no sea `GraphInterrupt` o `NodeInterrupt` (que son
control flow de LangGraph y deben propagarse). Al capturar, escribe `agent_error`
y el grafo continúa hacia `error_handler` en lugar de crashear.

---

## 7. Orden de system messages (cache efficiency)

El prefijo estático del prompt (identidad, principios, estilo) es cacheado por
OpenAI. Agregar contenido mutable (tiempo, datos del turno) al inicio del prompt
invalida el cache y multiplica el costo de inferencia.

**Orden correcto (de inicio a fin del prompt):**

| # | Bloque | Frecuencia de cambio |
|---|--------|---------------------|
| 1 | Identidad + principios + restricciones | Nunca (cache permanente) |
| 2 | Estilo de respuesta | Nunca |
| 3 | Saludo (si es primer turno) | Por turno, solo si aplica |
| 4 | Política de autenticación (level_1) | Condicional |
| 5 | Contexto de error / cuenta pendiente | Condicional |
| 6 | Investigación externa (tavily) | Por turno, si aplica |
| 7 | Preferencias del usuario | Por usuario |
| 8 | Intento clarificado (structured_prompt) | Por turno |
| 9 | Contexto de memoria rankeado | Por turno |
| 10 | Feedback de evaluador (retry) | Solo en retry |
| 11 | Regla anti-loop | Por turno |
| 12 | Directiva de mood | Por turno |
| 13 | Directiva de effort | Por turno |
| 14 | **Contexto de tiempo (build_time_context_block)** | **Siempre — OBLIGATORIO ÚLTIMO** |

> **Regla de oro:** `build_time_context_block()` va SIEMPRE AL ÚLTIMO.
> La hora cambia cada turno y destruiría el cache del prefijo estático si va antes.

---

## 8. Registry pattern

Cada agente tiene un `registry.py` con dos funciones públicas:

```python
# registry.py de un nuevo agente
_graphs: dict = {}

def init_X_graphs(checkpointer=None) -> None:
    """Compila y cachea el grafo. Llamado UNA vez en el lifespan de FastAPI."""
    graph = build_graph()  # tu builder
    compiled = graph.compile(checkpointer=checkpointer)
    _graphs["standard"] = compiled

def get_X_graph(tier: str = "standard"):
    """Devuelve el grafo compilado. Llamado en cada request."""
    return _graphs[tier]
```

Registro en `main.py` (sección lifespan):

```python
from app.agent.mi_agente.registry import init_X_graphs, get_X_graph

# Dentro de lifespan(), después de MongoDBSaver:
init_X_graphs(checkpointer=checkpointer)
app.state.mi_agente_graph = get_X_graph()
```

### Colecciones MongoDB del checkpointer

Cada agente necesita sus propias colecciones para no mezclar estado de conversaciones
de distintos agentes:

| Agente | checkpoint_collection_name | writes_collection_name |
|--------|---------------------------|----------------------|
| shifu_base_v1 | `shifu_checkpoints` | `shifu_checkpoint_writes` |
| shifu_v2 | `shifu_v2_checkpoints` | `shifu_v2_checkpoint_writes` |
| shifu_ecommerce | `shifu_ecom_checkpoints` | `shifu_ecom_checkpoint_writes` |

Nunca compartir colecciones de checkpoint entre agentes distintos.

---

## 9. Checklist — nuevo agente listo para PR

Antes de abrir un PR con un agente nuevo, verificar cada punto:

### Estructura
- [ ] Paquete en `app/agent/<nombre>/` con `__init__.py`, `graph/`, `registry.py`
- [ ] `graph/state.py` extiende `ShifuState` (no la reemplaza ni elimina campos)
- [ ] `graph/builder_<variante>.py` sigue el patrón de la sección 6

### Estado
- [ ] Campos con escritura paralela usan `Annotated` + reducer
- [ ] Campos de escritor único usan `Optional[X]` sin `Annotated`
- [ ] `semantic_intake` (o el nodo equivalente) resetea `validation_reports=None`

### Nodos
- [ ] Todos los nodos son `async def nombre(state: ShifuState) -> dict`
- [ ] Ningún nodo devuelve el estado completo
- [ ] Todos los accesos al estado usan `.get()` con default
- [ ] Nodos con I/O externo están envueltos en `_safe_node`

### Sistema de prompts
- [ ] `build_time_context_block()` es el ÚLTIMO bloque en todos los system messages
- [ ] Contenido estático (identidad, principios) precede a contenido dinámico

### Registry y lifespan
- [ ] `registry.py` expone `init_X_graphs()` y `get_X_graph()`
- [ ] `main.py` llama `init_X_graphs(checkpointer=checkpointer)` en lifespan
- [ ] `main.py` asigna `app.state.<nombre>_graph = get_X_graph()`
- [ ] Checkpointer usa colecciones MongoDB propias (no comparte con otros agentes)

### Tests
- [ ] Directorio `test/<nombre>/` con al menos 1 test de turno feliz
- [ ] Test de turno de cierre (`is_closing=True`)
- [ ] Test de error (`agent_error` se propaga correctamente)

---

## Decisiones de arquitectura — por qué son así

| Decisión | Razón |
|----------|-------|
| `semantic_intake` resetea `validation_reports=None` | Sin reset, los errores del turno anterior contaminan el siguiente |
| Fan-out paralelo requiere reducers | LangGraph aplica `apply_writes` en un único super-paso; dos escrituras sin reducer causan crash |
| `time_context` SIEMPRE al final | La hora cambia cada turno; si va antes del contenido estático, invalida el cache de OpenAI |
| Cierre (`is_closing`) saltea validators | Un turno de cierre no necesita validar apps; elimina 3 llamadas a API innecesarias |
| `account_selection_resolved` va directo a responder | Evita que `auth_validator` escriba `selected_accounts` concurrentemente con el dato ya resuelto |
| `tavily_subgraph` tiene timeout de 45s | La investigación es opcional; un timeout nunca debe crashear la respuesta |
| `_safe_node` en 3 nodos clave | `semantic_intake`, `bigtools_inspector`, `responder` son los más expuestos a excepciones de API |
| Identidad y personalidad con cache de 10 min | Permite editar en MongoDB sin reiniciar el servidor; el cache evita leer en cada turno |
| Colecciones MongoDB propias por agente | Mezclar checkpoints de agentes distintos causa colisiones de `thread_id` |
| Registry con `_graphs` dict en módulo | Una sola instancia compilada; no recompilar en cada request (costoso) |
