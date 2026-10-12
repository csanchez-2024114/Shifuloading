# Cómo funciona Shifu — De la entrada al usuario hasta la respuesta final

Este documento explica en lenguaje simple qué pasa exactamente desde que el usuario manda un mensaje hasta que recibe una respuesta. Está ordenado tal como el sistema lo ejecuta, paso a paso.

---

## Visión general del recorrido

```
Usuario escribe algo
        │
        ▼
1. La petición HTTP llega al servidor y se valida la identidad (JWT)
        │
        ▼
2. intent_analyzer_node  ←  "¿Qué quiere el usuario realmente?"
        │
        ├── Si es ambiguo ──► clarification_responder  ──► guarda en BD ──► responde
        │
        └── Si está claro ──► continúa...
                │
                ▼
3. context_loader_node  ←  "Cargar todo lo que el agente necesita saber"
        │
        ▼
4. agent_node  ←  "El LLM decide qué hacer"
        │
        ├── Quiere usar herramientas ──► tool_executor_node ──► vuelve a agent_node
        │                                       (puede repetirse hasta 25 veces)
        │
        └── Ya terminó ──► continúa...
                │
                ▼
5. markdown_formatter_node  ←  "Embellecer la respuesta"
        │
        ▼
6. memory_saver_node  ←  "Guardar todo en la base de datos"
        │
        ▼
Respuesta al usuario
```

---

## Paso 1 — La petición llega al servidor

El usuario manda un mensaje desde el frontend (web o app). El mensaje incluye:
- Su texto (`user_input`)
- El ID de la conversación (`conversation_id`) para mantener el hilo
- El modelo que quiere usar (opcional; por defecto `gpt-4o-mini`)

El servidor valida que el usuario esté autenticado usando un token JWT. Si no, rechaza la petición. Si sí, extrae el `user_id` y el `user_email` del token y arranca el grafo de LangGraph.

**En streaming:** el servidor abre un canal SSE (Server-Sent Events). El cliente recibe tokens en tiempo real mientras el grafo trabaja. Hay un heartbeat cada 5 segundos para que la conexión no se caiga aunque el agente tarde.

---

## Paso 2 — intent_analyzer_node: ¿Qué quiere el usuario?

Este es el primer nodo que se ejecuta. Su trabajo es entender **la intención real** del mensaje antes de cargar nada más. Usa un LLM rápido (también `gpt-4o-mini`) con temperatura 0 para que sea determinista.

### Qué hace exactamente:

1. **Carga el historial reciente de la conversación** — los últimos 16 mensajes (8 turnos). Esto es clave: si el usuario dijo "sí" o "dale", el clasificador necesita saber a qué está respondiendo.

2. **Clasifica la intención** en una de estas categorías:
   - `crear_workflow` — el usuario quiere automatizar algo nuevo
   - `editar_workflow` — quiere modificar uno existente
   - `ejecutar_workflow` — quiere disparar uno ahora
   - `eliminar_workflow` — quiere borrarlo
   - `consultar_estado` — pregunta sobre workflows o historial
   - `pregunta_capacidad` — "¿puedes hacer X?"
   - `accion_directa` — acción inmediata, no un workflow (ej. "muéstrame mis correos ahora")
   - `aprobar_plan` — el usuario está aprobando una propuesta que Shifu presentó
   - `ajustar_plan` — quiere cambiar algo del plan propuesto
   - `responder_pregunta` — está respondiendo algo que Shifu le preguntó
   - `unclear` — no se puede determinar

3. **Detecta la fase del workflow** (sin LLM — solo con patrones en el historial):
   - `idle` — sin contexto de workflow activo
   - `phase1_collecting` — se está hablando de crear algo pero aún no hay plan
   - `phase1_proposed` — Shifu ya presentó un plan numerado y preguntó "¿Te parece bien?"
   - `phase2_building` — el usuario aprobó y se está construyendo el workflow
   - `phase2_done` — el workflow fue confirmado y activado

4. **Decide si hay ambigüedad**: si la confianza cae por debajo del 60%, activa `needs_clarification = true` y genera una pregunta para el usuario.

5. **Genera una estrategia** para el agente: una instrucción en español que le dice exactamente qué herramienta debe llamar primero y con qué parámetros.

### Qué sale de aquí:

El nodo devuelve todo esto al estado del grafo:
- `intent_analysis` — tipo de intención, confianza, entidades mencionadas (integración, frecuencia, nombre del workflow)
- `enriched_message` — el mensaje del usuario reformulado resolviendo pronombres y referencias ("eso" → "el workflow de ventas que creamos ayer")
- `agent_strategy` — instrucción directa para el agente
- `workflow_phase` — la fase actual detectada por patrones
- `needs_clarification` — si hay que preguntar antes de continuar

### Bifurcación:

- Si `needs_clarification = true` → va a **clarification_responder**, que formula una pregunta amable, la guarda en la BD y termina el turno
- Si `needs_clarification = false` → continúa al paso 3

---

## Paso 3 — context_loader_node: Cargar todo el contexto

Este nodo es el más "pesado" en datos. Su trabajo es reunir toda la información que el agente necesita para responder bien. Lanza **6 cargas en paralelo** (todas asíncronas al mismo tiempo, no una tras otra):

| Qué carga | Para qué sirve |
|---|---|
| Historial de conversación + resumen | El agente ve lo que ya se habló |
| Preferencias del usuario | Idioma, tono, longitud de respuesta preferida |
| Catálogo de apps disponibles | Sabe qué integraciones existen en el sistema |
| Integraciones conectadas del usuario | Sabe cuáles tiene activadas (Gmail, Sheets, etc.) |
| Entidades conocidas del usuario | IDs reales de archivos, hojas, docs que ya usó antes |
| Memoria global (long-term memory) | Patrones y hechos aprendidos de conversaciones anteriores |
| BigTools (herramientas de workflow) | Las herramientas para crear/editar/ejecutar workflows |

### Verificación de perfil:

Si el usuario está pidiendo crear un workflow por primera vez y **no se saben al menos 2 datos básicos** de él (profesión, área, objetivo, contexto de uso), el nodo pausa la acción y en su lugar le pide al agente que haga **una sola pregunta abierta** para entender quién es el usuario. Esto evita crear workflows genéricos que no le sirven a nadie.

### Construcción del system prompt:

Con todo lo anterior, el nodo construye un **system prompt gigante** (el "manual de instrucciones" del agente para este turno). Incluye 15+ secciones:
- Identidad y personalidad del agente
- Reglas de comportamiento y lo que está prohibido
- La fase actual del workflow y las reglas de la "Phase Guard" (ver más abajo)
- Los recursos conocidos del usuario (IDs de archivos reales)
- El resumen de conversación previa
- El perfil del usuario (nombre, preferencias)
- Las integraciones disponibles y cuáles están conectadas
- Las BigTools disponibles y cómo usarlas
- La estrategia que el intent_analyzer generó para este turno

### Qué sale de aquí:

- `messages` — el historial completo formateado para el LLM, incluyendo el system prompt
- `all_tools` — la lista completa de herramientas que el agente puede usar

---

## Paso 4 — agent_node: El LLM decide qué hacer

Este es el "cerebro" del sistema. Recibe todos los mensajes y todas las herramientas, e invoca al LLM (por defecto `gpt-4o-mini` con temperatura 0.4).

### Qué puede hacer el LLM:

1. **Llamar herramientas** — si necesita datos o ejecutar acciones (buscar emails, crear un workflow, listar archivos, etc.)
2. **Responder directamente** — si ya tiene todo lo que necesita para responder al usuario

### Protecciones contra loops:

- Si el LLM llama herramientas **25 veces en el mismo turno**, se le fuerza a responder en texto sin más herramientas
- Si la **misma herramienta devuelve error 2 veces seguidas**, también se le fuerza a parar y explicar el problema al usuario

### Si llama herramientas:

El grafo va al `tool_executor_node` y luego **regresa a `agent_node`**. Este ciclo se repite hasta que el LLM produce texto sin tool_calls, o hasta que se dispara una de las protecciones.

---

## Paso 4b — tool_executor_node: Ejecutar las herramientas

Cuando el agente decide usar herramientas, este nodo las ejecuta. Para cada herramienta que el LLM pidió:

1. **Busca la función correspondiente** en la lista de herramientas disponibles
2. **La ejecuta** con los argumentos que el LLM proporcionó
3. **Si falla**, activa el sistema de auto-corrección (`_debug_and_retry`):
   - Otro LLM analiza el error y los argumentos originales
   - Intenta corregir los argumentos automáticamente
   - Reintenta la herramienta con los argumentos corregidos
   - Si el reintento también falla → registra un `SYSTEM_ERROR` y le dice al agente que no puede resolver ese problema

4. **Si la herramienta es `mostrar_opciones`** — en lugar de solo guardar el resultado como texto, extrae la estructura de opciones y la guarda en `user_choices` para que el frontend la muestre como tarjetas interactivas

5. **Limita el tamaño** de cada resultado a 6.000 caracteres para no sobrecargar el contexto del LLM

El resultado de todas las herramientas se agrega al historial de mensajes y el grafo vuelve al `agent_node`.

---

## Paso 5 — markdown_formatter_node: Embellecer la respuesta

Cuando el agente ya terminó de usar herramientas y escribió su respuesta final, este nodo la pasa por un segundo LLM especializado en formateo.

**Solo actúa si la respuesta tiene más de 150 caracteres.** Respuestas cortas las devuelve tal cual.

Qué hace:
- Agrega emojis relevantes con moderación
- Pone en **negrita** términos clave, nombres de workflows y acciones importantes
- Formatea listas con espaciado consistente
- Para propuestas de workflow: asegura que cada paso tenga emoji + nombre en negrita + descripción breve

Lo que **no hace**:
- No cambia el contenido ni el significado
- No agrega frases de cierre como "¿Te puedo ayudar en algo más?"
- No agrega encabezados donde no los había

---

## Paso 6 — memory_saver_node: Guardar todo

El último nodo antes de que el grafo termine. Hace tres cosas en paralelo:

1. **Guarda los mensajes de este turno** en MongoDB — el mensaje del usuario y la respuesta del asistente quedan en la colección `messages` de la conversación

2. **Detecta y guarda preferencias** — analiza si el usuario mencionó algo sobre cómo prefiere que Shifu trabaje (idioma, tono, longitud) y lo guarda en `user_preferences`

3. **Extrae y guarda entidades** (en background, no bloquea) — busca en la respuesta del agente IDs de recursos que el usuario ahora tiene: IDs de Google Sheets, Docs, Slides, Drive, o workflows. Los guarda en `user_entities` para usarlos en futuras conversaciones sin tener que preguntar de nuevo.

---

## La respuesta final al usuario

Una vez que el grafo termina:

- En modo **normal** (`/chat`): la ruta devuelve un JSON con la respuesta final, la acción de UI si hay una (ej. "conectar Gmail"), las opciones de elección si las hay, y metadatos
- En modo **streaming** (`/chat/stream`): la respuesta final se lee desde la base de datos (para asegurar consistencia) y se emite como evento SSE `done`. Después se emite un evento `suggestions` con 3-4 sugerencias de seguimiento generadas por un LLM liviano

---

## Cómo se crean los workflows (el flujo completo)

La creación de un workflow tiene dos fases bien diferenciadas.

### Fase 1 — Entender y proponer

El usuario dice algo como "quiero que me llegue un reporte de ventas cada semana en Sheets".

**Lo que hace el agente:**

1. Llama a `consultar_herramientas_disponibles` para ver qué integraciones tiene el usuario conectadas (¿tiene Google Sheets? ¿Gmail?)
2. Puede llamar a `mostrar_opciones` para que el usuario elija entre alternativas (trigger, frecuencia, formato)
3. Formula un **plan numerado** con cada paso del workflow:
   ```
   Aquí está tu plan:
   1. 📊 Extraer datos de ventas — lee el rango A:F de tu hoja "Ventas 2024"
   2. 📧 Enviar reporte — manda el resumen por Gmail a tu correo
   
   ¿Te parece bien? ¿Lo creamos?
   ```
4. **Espera aprobación.** No hace nada más hasta que el usuario diga que sí.

> **Phase Guard:** El sistema tiene una protección de 3 capas que le prohíbe al agente llamar `crear_workflow` antes de tener la aprobación explícita del usuario. Esto evita que el agente empiece a construir cosas que el usuario no confirmó.

### Fase 2 — Construir

El usuario dice "sí" o "dale". El `intent_analyzer` detecta `aprobar_plan` y la fase pasa a `phase2_building`.

**Lo que hace el agente, en orden:**

1. **`configurar_metadata_workflow`** — guarda el plan como checklist en la base de datos. Esto es el "ancla de memoria" que le permite saber en qué paso quedó si algo falla.

2. **`crear_workflow`** — crea el documento base del workflow en MongoDB con nombre, descripción y frecuencia de ejecución. Devuelve un `workflow_id`.

3. **`agregar_paso_workflow`** (una llamada por cada paso) — agrega cada paso uno a uno. Cada paso tiene:
   - Un tipo (`gmail_send`, `sheets_read`, `http_request`, etc.)
   - Su configuración específica (a quién mandar, qué leer, qué URL llamar)
   - El número de orden dentro del workflow

4. **`confirmar_workflow`** — activa el workflow. A partir de este momento el workflow está vivo y se ejecutará según su frecuencia configurada.

### Cómo queda guardado en la base de datos

El workflow vive en la colección `workflows` de MongoDB. Tiene esta estructura lógica:

```
workflow
  ├── _id (ObjectId)
  ├── user_id
  ├── nombre: "Reporte semanal de ventas"
  ├── descripcion
  ├── frecuencia: "weekly"
  ├── status: "active" | "draft" | "paused"
  ├── created_at / updated_at
  └── pasos: [
        { orden: 1, tipo: "sheets_read", config: { spreadsheet_id: "...", range: "A:F" } },
        { orden: 2, tipo: "gmail_send",  config: { to: "me@...", subject: "Reporte" } }
      ]
```

Los IDs de los recursos reales (el `spreadsheet_id`, el `doc_id`, etc.) se guardan también en `user_entities` para que en futuras conversaciones el agente los recuerde sin tener que preguntar otra vez.

---

## Qué son las "entidades" y por qué importan

Las entidades son recursos concretos que el usuario ya usa: una hoja de cálculo específica, un documento, una carpeta de Drive, un workflow creado. Cada vez que el agente menciona o usa un recurso real, el `memory_saver` lo extrae y lo guarda en la colección `user_entities`.

**Ejemplo práctico:** La primera vez que el usuario dice "usa mi hoja de ventas", el agente le pide el ID. Lo usa, lo guarda. La próxima semana, si el usuario dice "actualiza el reporte de ventas", el agente ya sabe qué hoja es sin preguntar.

---

## Las herramientas disponibles

El agente tiene acceso a dos categorías de herramientas:

### Herramientas de consulta (siempre disponibles)
- `consultar_herramientas_disponibles` — qué apps están conectadas
- `buscar_workflows_existentes` — lista los workflows del usuario
- `mostrar_opciones` — presenta tarjetas de elección al usuario (en lugar de lista de texto)
- `solicitar_conexion_integracion` — pide al usuario que conecte una app

### Herramientas de workflow (BigTools)
- `configurar_metadata_workflow` — ancla el plan en memoria
- `crear_workflow` — crea el documento base
- `agregar_paso_workflow` — agrega un paso al workflow en construcción
- `reemplazar_paso_workflow` — reemplaza un paso existente
- `confirmar_workflow` — activa el workflow
- `listar_mis_workflows` — lista con detalles
- `obtener_workflow` — detalle de uno específico
- `eliminar_workflow` — borra permanentemente

---

## Resumen visual del flujo completo

```
Usuario: "quiero un reporte semanal de ventas"
        │
        ▼
intent_analyzer: crear_workflow, confidence=0.91, phase=idle
        │
        ▼
context_loader: carga historial + preferencias + entidades + tools
        │
        ▼
agent: llama consultar_herramientas_disponibles
        │
tool_executor: ejecuta → {"sheets": true, "gmail": true}
        │
        ▼
agent: llama mostrar_opciones (¿qué hoja usar?)
        │
tool_executor: → user_choices emitido al frontend como tarjetas
        │
        ▼
agent: propone plan numerado de 2 pasos + pregunta "¿Te parece bien?"
        │
markdown_formatter: embellece la respuesta con emojis y formato
        │
memory_saver: guarda el turno en MongoDB
        │
        ▼
Usuario: "sí, dale"
        │
        ▼
intent_analyzer: aprobar_plan, workflow_phase=phase2_building
        │
context_loader
        │
agent: llama configurar_metadata_workflow
      → llama crear_workflow
      → llama agregar_paso_workflow (paso 1)
      → llama agregar_paso_workflow (paso 2)
      → llama confirmar_workflow
        │
agent: "¡Tu workflow está listo! Se ejecutará cada lunes a las 8am."
        │
markdown_formatter → memory_saver → extrae IDs → guarda en user_entities
        │
        ▼
Usuario recibe respuesta + 3 sugerencias de seguimiento
```
