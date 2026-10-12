# Tools Directory — Shifu Agent

Directorio completo de todas las herramientas disponibles para el agente Shifu,
organizadas por categoría. Actualizar este archivo cada vez que se agregue, modifique
o elimine una tool del registry.

**Fuente de verdad en código:** [bigTools_registry.py](../app/agents/agent_langGraph/bigTools_registry.py)

---

## Convención de naming — OBLIGATORIO

> **Todas las tools deben estar en inglés:** nombre, descripción y campos del schema.

| Elemento | Correcto | Incorrecto |
|---|---|---|
| Nombre | `list_my_workflows` | `listar_mis_workflows` |
| Descripción | `"Lists all active workflows..."` | `"Lista todos los workflows..."` |
| Campo schema | `spreadsheet_id`, `max_results` | `id_hoja`, `max_resultados` |
| Categoría | usa key de `TOOL_CATALOG` | texto libre |

**Formato de nombres:** `snake_case`, verbo_objeto (ej: `create_workflow`, `list_my_workflows`, `get_doc_content`).

**Estado Gmail:** los 13 tools de Gmail aún tienen nombres en español — pendiente de renombrar cuando se actualice `gmail_bigtools.py`.

---

## Cómo agregar una nueva tool

1. Crear el archivo `app/agents/agent_langGraph/bigtools/<nombre>_bigtools.py`
2. Definir la función `get_<nombre>_bigtools(user_id, user_email, ...) -> List[BigTool]`
3. Cada `BigTool` debe incluir `category=` con una key válida de `TOOL_CATALOG`
4. Nombre, descripción y campos del schema **en inglés** (ver convención arriba)
5. Registrar en `get_all_bigtools()` dentro de `bigTools_registry.py`
6. Actualizar este directorio

---

## Categorías

| Key | Label | Descripción |
|---|---|---|
| `system` | System | Capacidades base de Shifu, siempre disponibles sin OAuth |
| `google` | Google Suite | Gmail, Drive, Docs, Sheets, Slides |
| `productivity` | Productivity & Project Management | ClickUp, Asana, Trello, Monday, Jira, Notion |
| `communication` | Communication & Messaging | Slack, Discord, Teams, Telegram, WhatsApp, Outlook |
| `social` | Social Media | Instagram, Facebook, TikTok, LinkedIn, Twitter/X, Threads |
| `crm` | CRM & Marketing | HubSpot, Salesforce, Brevo, Mailchimp |
| `storage` | File Storage | Dropbox, OneDrive |
| `ecommerce` | E-commerce & Delivery | Uber Eats, Pedidos Ya |
| `workflow` | Workflow Engine | Crear, editar y gestionar automatizaciones |
| `ai` | AI Processing | Summarize, transform, extract, classify, generate |

---

## System

> Siempre disponibles. No requieren OAuth ni integración del usuario.

### `web_search`
- **Descripción:** Búsqueda en internet en tiempo real.
- **Cuándo usar:** Cuando se necesitan datos actuales (precios, noticias, clima, eventos), o para investigar un tema antes de responder.
- **Parámetros requeridos:**
  - `query` *(string)* — Términos de búsqueda.
- **Retorna:** Respuesta sintetizada + links de fuentes.
- **Archivo:** `app/agents/agent_langGraph/tools.py` (TavilySearch)

---

### `get_connected_apps`
- **Descripción:** Lista las integraciones que el usuario tiene conectadas actualmente.
- **Cuándo usar:** Para verificar si una app está conectada antes de intentar usarla, o cuando el usuario pregunta qué apps tiene vinculadas.
- **Parámetros requeridos:** Ninguno (el user context se inyecta vía closure).
- **Retorna:**
  ```json
  {
    "connected_apps": [
      { "provider": "google", "account_id": "user@gmail.com" }
    ],
    "total": 1
  }
  ```
- **Fuente de datos:** Colección MongoDB `user_connected_accounts`
- **Archivo:** `bigTools_registry.py` → `_make_connected_apps_tool()`

---

### `connect_app`
- **Descripción:** Dispara un botón de conexión OAuth en el frontend del usuario.
- **Cuándo usar:** Solo cuando el usuario quiere conectar una app que NO está en su lista de integraciones conectadas.
- **Parámetros requeridos:**
  - `integration` *(string)* — Nombre de la app a conectar. Ej: `"gmail"`, `"google"`, `"slack"`.
- **Retorna:** Payload `{ "accion": "connect_integration", "integration": "...", "login_path": "..." }` que el `tool_executor_node` propaga al frontend.
- **Archivo:** `bigTools_registry.py` → `_make_connect_app_tool()`

---

### `recall_context`
- **Descripción:** Recupera el historial de la conversación actual y la memoria de largo plazo de sesiones anteriores.
- **Cuándo usar:** Cuando el usuario pregunta sobre conversaciones previas ("¿de qué hemos hablado?", "¿qué hicimos antes?", "¿me recuerdas?") o cuando Shifu necesita contexto histórico para responder con precisión.
- **Parámetros requeridos:** Ninguno (user_id, conversation_id y db se inyectan vía closure).
- **Retorna:**
  ```json
  {
    "conversation_summary": "Resumen de la conversación actual",
    "recent_messages": [{ "role": "user", "content": "..." }],
    "long_term_memory": "Memoria acumulada de sesiones anteriores"
  }
  ```
- **Archivo:** `system_tools.py` → `make_recall_context_tool()`

---

### `inspect_tool`
- **Descripción:** Inspecciona cualquier tool disponible para revelar su interfaz exacta.
- **Cuándo usar:** Antes de usar una tool desconocida, o antes de agregar un paso a un workflow.
- **Parámetros requeridos:**
  - `tool_name` *(string)* — Nombre exacto de la tool, o uno de los valores especiales:
    - `"list"` → nombres de todas las tools disponibles
    - `"categories"` → todas las categorías con sus tools y conteos
    - `"category:<key>"` → todas las tools de una categoría (ej: `"category:system"`)
- **Retorna:**
  ```json
  {
    "name": "web_search",
    "category": "system",
    "description": "...",
    "required_params": [{ "name": "query", "type": "string", "description": "..." }],
    "optional_params": [],
    "returns": "..."
  }
  ```
- **Archivo:** `bigTools_registry.py` → `_make_inspector()`

---

## Google Suite

> Requieren OAuth con `provider: "google"`. Un solo token cubre Gmail, Drive, Docs, Sheets y Slides.
> Se activan automáticamente cuando el usuario tiene `"google"` en sus cuentas conectadas.

### Estado actual: ✅ Activo

| Tool | Descripción | Archivo |
|---|---|---|
| ✅ Gmail (13 tools) | `listar_correos`, `buscar_correo`, `enviar_correo`, `crear_borrador`, `mover_correo_por_asunto`, y más | `bigtools/gmail_bigtools.py` |
| ✅ Drive | Listar, buscar, subir, descargar archivos y carpetas | `bigtools/drive_bigtools.py` |
| ✅ Docs | Crear, leer, editar documentos de Google | `bigtools/docs_bigtools.py` |
| ✅ Sheets | Leer, escribir, crear hojas de cálculo | `bigtools/sheets_bigtools.py` |
| ✅ Slides | Crear y editar presentaciones | `bigtools/slides_bigtools.py` |

---

## Productivity & Project Management

> Requieren OAuth individual por proveedor.

| Tool | Descripción | Provider | Archivo |
|---|---|---|---|
| *(por agregar)* | ClickUp — tareas, proyectos, espacios | `clickup` | `bigtools/clickup_bigtools.py` |
| *(por agregar)* | Asana — tareas, proyectos, comentarios | `asana` | `bigtools/asana_bigtools.py` |
| *(por agregar)* | Trello — tableros, listas, tarjetas | `trello` | `bigtools/trello_bigtools.py` |
| *(por agregar)* | Monday — tableros, grupos, items | `monday` | `bigtools/monday_bigtools.py` |
| *(por agregar)* | Jira — issues, sprints, proyectos | `jira` | `bigtools/jira_bigtools.py` |
| *(por agregar)* | Notion — páginas, bases de datos | `notion` | `bigtools/notion_bigtools.py` |

---

## Communication & Messaging

| Tool | Descripción | Provider | Archivo |
|---|---|---|---|
| *(por agregar)* | Slack — mensajes, canales, usuarios | `slack` | `bigtools/slack_bigtools.py` |
| *(por agregar)* | Discord — mensajes, servidores | `discord` | `bigtools/discord_bigtools.py` |
| *(por agregar)* | Microsoft Teams — mensajes, reuniones | `teams` | `bigtools/teams_bigtools.py` |
| *(por agregar)* | Telegram — mensajes, bots | `telegram` | `bigtools/telegram_bigtools.py` |
| *(por agregar)* | WhatsApp Business — mensajes | `whatsapp` | `bigtools/whatsapp_bigtools.py` |
| *(por agregar)* | Outlook — correo, calendario | `outlook` | `bigtools/outlook_bigtools.py` |

---

## Social Media

| Tool | Descripción | Provider | Archivo |
|---|---|---|---|
| *(por agregar)* | Instagram — posts, stories, DMs | `instagram` | `bigtools/instagram_bigtools.py` |
| *(por agregar)* | Facebook — posts, páginas | `facebook` | `bigtools/facebook_bigtools.py` |
| *(por agregar)* | TikTok — videos, analytics | `tiktok` | `bigtools/tiktok_bigtools.py` |
| *(por agregar)* | LinkedIn — posts, conexiones | `linkedin` | `bigtools/linkedin_bigtools.py` |
| *(por agregar)* | Twitter/X — tweets, DMs | `twitter` | `bigtools/twitter_bigtools.py` |
| *(por agregar)* | Threads — posts, replies | `threads` | `bigtools/threads_bigtools.py` |

---

## CRM & Marketing

| Tool | Descripción | Provider | Archivo |
|---|---|---|---|
| *(por agregar)* | HubSpot — contactos, deals, emails | `hubspot` | `bigtools/hubspot_bigtools.py` |
| *(por agregar)* | Salesforce — leads, oportunidades | `salesforce` | `bigtools/salesforce_bigtools.py` |
| *(por agregar)* | Brevo — campañas, contactos | `brevo` | `bigtools/brevo_bigtools.py` |
| *(por agregar)* | Mailchimp — listas, campañas | `mailchimp` | `bigtools/mailchimp_bigtools.py` |

---

## File Storage

| Tool | Descripción | Provider | Archivo |
|---|---|---|---|
| *(por agregar)* | Dropbox — archivos, carpetas | `dropbox` | `bigtools/dropBox_bigtools.py` |
| *(por agregar)* | OneDrive — archivos, carpetas | `onedrive` | `bigtools/onedrive_bigtools.py` |

---

## E-commerce & Delivery

| Tool | Descripción | Provider | Archivo |
|---|---|---|---|
| *(por agregar)* | Uber Eats — pedidos, menú | `ubereats` | `bigtools/ubereats_bigtools.py` |
| *(por agregar)* | Pedidos Ya — pedidos, restaurante | `pedidosya` | `bigtools/pedidosya_bigtools.py` |

---

## Workflow Engine

> Herramientas internas del motor de automatización. No requieren OAuth.

| Tool | Descripción | Archivo |
|---|---|---|
| *(por activar)* | `crear_workflow` — crea un nuevo workflow | `bigtools/workflow_bigtools.py` |
| *(por activar)* | `agregar_paso_workflow` — agrega un paso | `bigtools/workflow_bigtools.py` |
| *(por activar)* | `reemplazar_paso_workflow` — reemplaza un paso | `bigtools/workflow_bigtools.py` |
| *(por activar)* | `eliminar_paso_workflow` — elimina un paso | `bigtools/workflow_bigtools.py` |
| *(por activar)* | `editar_workflow` — carga workflow para editar | `bigtools/workflow_bigtools.py` |
| *(por activar)* | `confirmar_workflow` — confirma y activa | `bigtools/workflow_bigtools.py` |
| *(por activar)* | `cancelar_workflow` — descarta el borrador | `bigtools/workflow_bigtools.py` |
| *(por activar)* | `listar_mis_workflows` — lista workflows del usuario | `bigtools/workflow_bigtools.py` |
| *(por activar)* | `ver_borrador_workflow` — muestra el borrador actual | `bigtools/workflow_bigtools.py` |
| *(por activar)* | `pausar_workflow` — pausa ejecución | `bigtools/workflow_bigtools.py` |
| *(por activar)* | `reactivar_workflow` — reactiva workflow pausado | `bigtools/workflow_bigtools.py` |
| *(por activar)* | `eliminar_workflow` — borra un workflow | `bigtools/workflow_bigtools.py` |
| *(por activar)* | `fijar_frecuencia_workflow` — define cuándo corre | `bigtools/scheduler_bigtools.py` |
| *(por activar)* | `listar_historial_ejecuciones` — logs de ejecución | `bigtools/scheduleProcessTool_bigtools.py` |

---

## AI Processing

> Siempre disponibles. No requieren OAuth. Se usan como pasos intermedios en workflows.

| Tool | Input principal | Output | Archivo |
|---|---|---|---|
| *(por activar)* | `ai_summarize` — resume texto | `text` | texto resumido | `bigtools/ai_bigtools.py` |
| *(por activar)* | `ai_transform` — transforma/traduce texto | `text`, `instruction` | texto transformado | `bigtools/ai_bigtools.py` |
| *(por activar)* | `ai_extract` — extrae campos a JSON | `text`, `fields` | JSON con campos | `bigtools/ai_bigtools.py` |
| *(por activar)* | `ai_classify` — clasifica en categorías | `text`, `categories` | categoría elegida | `bigtools/ai_bigtools.py` |
| *(por activar)* | `ai_generate` — genera contenido nuevo | `instruction` | texto generado | `bigtools/ai_bigtools.py` |
| *(por activar)* | `ai_filter` — filtra un array JSON | `items`, `criteria` | array filtrado | `bigtools/ai_bigtools.py` |
| *(por activar)* | `ai_decide` — toma una decisión booleana | `context`, `question` | `{answer: bool, reason}` | `bigtools/ai_bigtools.py` |

---

## Notas de implementación

### Convención de categorías en BigTool

```python
BigTool(
    name="mi_tool",
    description="...",
    tool=mi_funcion,
    args_schema=MiSchema,
    category="google",  # ← siempre incluir, usar key de TOOL_CATALOG
)
```

### Consultar el índice desde el agente

```
inspect_tool("categories")           # ver todas las categorías activas
inspect_tool("category:system")      # ver tools de sistema
inspect_tool("web_search")           # ver schema completo de una tool
```

### Estado de activación

| Estado | Significado |
|---|---|
| ✅ Activo | Tool registrada y disponible para el agente |
| *(por activar)* | Tool existe en el código pero no está en `get_all_bigtools()` |
| *(por agregar)* | Tool planeada pero aún no implementada |
