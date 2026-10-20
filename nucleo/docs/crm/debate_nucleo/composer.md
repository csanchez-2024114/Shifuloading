## 1. Arquitectura destino

**Repositorio base:** `langgraph-alan` como raíz del producto; Shifuloading se integra sin tirar el dominio CRM.

| Pieza | Ubicación destino |
|--------|-------------------|
| Núcleo LangGraph (intocable) | `src/assistant/core/*` (`agent.py`, `server.py`, `memory.py`, middlewares, `files/`, `auth`, `metrics`, `bigtool`) |
| Dominio CRM (puro, sin bucle LLM) | `src/assistant/packs/crm/` — mover/adaptar `operaciones.py`, `estructura.py`, `conceptos.py`, `catalogos/*.json`, `pantalla.py`, `registros.py`, `edicion.py` (lógica), `toma.py`, `sembrar.py`, `diseno.py`, `primer_diseno.py`, `adaptador_lab.py`, `vista.py`, `regional.py`, `marca.py`, `web.py` (búsqueda/enlaces) |
| Sesión, cercos, ganchos, deshacer, pendientes | `src/assistant/packs/crm/sesion/` — `Sesion` / `SesionDiseno`, `puntos.py`, `por_hacer.py`; hoy viven en `agente.py` + `agente_diseno.py` |
| Herramientas expuestas al modelo | `src/assistant/profiles/crm/tools.py` — `@tool` / `tool_spec` que delegan en la sesión; `build_tools` filtra base de Alan (sin `web_search`/`deep_research` salvo que el perfil los quiera) y añade el catálogo CRM |
| Prompt y políticas | `profiles/crm/prompts/system.md` (inglés al modelo), `policies.py` (`ToolPolicy`: `evidence=True` en consultas, `approval` en borrados masivos alineado con `EFFECT_APPROVAL`) |
| Persistencia CRM | `packs/crm/repos/` — interfaz + implementación; evolución de `repositorio.py` |
| Memoria de negocio de la persona | `packs/crm/conversacion.py` — lo que hoy es `memoria.py` (`hechos`, estilo, `por_hacer` en Mongo aparte del doc CRM) |
| Rutas producto | `packs/crm/api/` o montaje en app Carlos: conservar contratos `crmRoutes.py` / `labRoutes.py` |
| UI producto | Sigue en Shifuloading `src/pages/CrmPage.jsx`, `BriefPage.jsx`, `laboratorio/`; no sustituir por `packs/ui/index.html` |
| UI debug / evals | `packs/ui/index.html` o `profiles/crm/static/` solo para pruebas manuales con `AGENT_PROFILE=crm` |

**Adoptar de Alan (sustituye lo nuestro equivalente):** historial del hilo (`MongoDBSaver` + `thread_id`), compactación (`ResumenPorTurno` + `MEMORY_SUMMARIZE`), adjuntos estructurados (`FILES_ENABLED` + GridFS vs parte de `adjuntos.py`), aprobaciones (`HumanInTheLoopMiddleware` + `ToolPolicy`), topes (`LimiteLlamadas`, `LimiteRepeticiones`, `AterrizajeSuave`, `TURN_TOKEN_CAP`), errores de herramienta (`ToolErrorMiddleware`), trazas/métricas/feedback (`TRACE_METADATA`, `TURN_METRICS`), marco de evals (`scripts/run_evals.py`), verificación de URLs sin LLM (`URL_FILTER_ALWAYS`).

**Conservar porque Alan no lo tiene:** documento CRM completo (contactos, tareas, listas, bloques, toma, brief), `operaciones` + versionado optimista, catálogo `conceptos` + cercos de diseño (`agente_diseno._cerco`, ganchos `GANCHOS_PANTALLA`), deshacer selectivo (`puntos.py`), pendientes (`por_hacer.py`), `consultar_datos` con números calculados en código, modo laboratorio (`adaptador_lab`), generación inicial (`generador`, `primer_diseno`), `chat.py` determinista como respaldo, reglas de memoria de negocio (`sanear_memoria`, sin PII), auth/billing/canales/workers de Carlos.

---

## 2. Cercos, ganchos, deshacer, pendientes y verdad → middlewares (sin llamadas extra)

Hoy el bucle está en `agente_diseno.responder` (líneas ~1726–1775): herramientas → `sesion.ejecutar` / `_cerco`; al terminar sin tools → `agente.revisar_respuesta` (hasta `MAX_CORRECCIONES=2`).

**En Alan, sin tocar `core/agent.py`:**

1. **`CrmToolGuard` (`AgentMiddleware.wrap_tool_call`)** — Antes de `handler`, lee `runtime.context` extendido (`CrmContext`: `doc`, `SesionDiseno`, `texto`, `confirmado`, flags toma). Llama la misma lógica que `SesionDiseno.ejecutar` / `_cerco` / `planificar_cerco_masivo` (orden previo al batch de tools). Si el cerco devuelve error, retorna `ToolMessage` sin ejecutar (como `LimiteRepeticiones`). **0 tokens.**

2. **`CrmPostTool` (`after_tool` o dentro del tool)** — `puntos.anotar`, `por_hacer` al superar `MAX_ACCIONES`, `traza.paso_herramienta`. **0 tokens.**

3. **`CrmTruthGuard` (`wrap_model_call` / `after_model`)** — Si la última `AIMessage` no tiene `tool_calls`, ejecuta `revisar_respuesta` + `verdad_lado_final` / respuesta sustituta (`_deshacer_sustituto`, `GANCHOS_PANTALLA`). Si hay aviso: inyecta `HumanMessage` de corrección y **salta a otra vuelta de modelo** (igual que hoy). Si el código debe escribir la respuesta final (solo deshacer): **reemplaza el contenido del `AIMessage` y termina el turno** — **0 tokens** extra. Presupuesto: `MODEL_CALL_LIMIT=3` fijo (sin clasificador de esfuerzo), `ANSWER_VERIFY=0`, alineado con 2–3 llamadas totales.

4. **`CrmDynamicTools` (`wrap_model_call`)** — Equivalente a filtrar herramientas tras deshacer (`tras_deshacer`, `solo_responder`): última llamada con `tool_choice` acotado vía política del perfil, no regex en prompt.

5. **Pendientes** — `por_hacer` persiste en `crm_conversaciones` (como `memoria.py`); se inyecta en `dynamic_prompt` del perfil (`ph.bloque`) junto con `pantalla.describir_pantalla` y `conceptos.bloque_para_prompt`. **0 tokens.**

6. **Aprobaciones** — Borrados masivos que hoy devuelven `ERROR_MASIVO_*` pueden mapearse a `ToolPolicy(approval=True)` + flujo `/resume` de Alan, o mantener `pendiente` JSON en React (paridad con `chat.py`) hasta fase posterior; el cerco sigue siendo la fuente de verdad.

---

## 3. Datos: Motor async vs pymongo sync, checkpointer, candado

- **Documento CRM (`crm_workspaces`):** Mantener el modelo y `operaciones` puros. Implementación recomendada: **capa sync pymongo** usada solo desde herramientas del agente (mismo patrón que `core/appdata/mongo.py`), invocada con `asyncio.to_thread` desde rutas FastAPI async de Carlos **o** rutas sync montadas en el servidor de Alan. Evitar dos semánticas de versionado: una sola implementación en `packs/crm/repos/mongo.py`.

- **Historial de chat:** **Alan manda** — `thread_id = f"crm:{user_id}"` (un hilo por persona). Dejar de duplicar los 16 mensajes en prompt manual; `ResumenPorTurno` sustituye ventana/resumen rodante de `memoria.py` para el modelo. **Conservar** en `crm_conversaciones`: `memoria` (hechos/estilo), `por_hacer`, metadatos; no el array `mensajes` completo si el checkpointer ya lo guarda (migración gradual).

- **Async vs sync:** El **agente es sync** (`agent.stream`/`invoke`, CONTRATO). El **monolito Carlos** puede seguir async en el resto; solo el path `/chat` encola el turno sync. No mezclar `motor` async dentro de tools LangGraph.

- **Candado por hilo (`server.py` `busy` + 409):** Compatible con **un worker** uvicorn en el servicio que ejecuta el agente. Si el deploy de Carlos usa varios workers, **mover el candado a Mongo** (lease por `thread_id`) antes de producción, o dedicar un solo worker/replica al chat CRM. Misma regla para no corromper `crm_workspaces` con dos turnos concurrentes del mismo usuario.

---

## 4. Frontend: React vs HTML de Alan

- **Producto:** Sin cambio de stack. `POST /api/v1/crm/chat` (y variantes lab) mantienen JSON `{ doc, respuesta, vista?, pendiente?, modo, cambios?, consultas?, … }`.

- **Adaptador interno:** Handler que (1) carga CRM + contexto, (2) arma `payload` LangGraph, (3) **`agent.invoke`** en sync (v1 sin streaming) o consume SSE y reconstruye `respuesta`, (4) persiste doc + `por_hacer`, (5) devuelve `vista_crm`.

- **Bancos día 1:** `BASE` + `RUTA_CHAT` (p. ej. `/api/lab/chat` o `/api/v1/crm/lab/chat`) debe seguir respondiendo la forma de `adaptador_lab.procesar_chat_lab`; el motor detrás pasa de `agente_diseno.responder` al perfil `crm`.

- **SSE `/chat` + `/resume`:** Para la UI React, fase 2 opcional: streaming de tokens; tarjetas HITL → componente de confirmación que llame `/resume` o reenvíe `pendiente` legacy.

- **`packs/ui/index.html`:** Solo desarrollo, regresión manual y evals; no es la UI de FREEPOL/Shifu.

---

## 5. Resto del backend de Carlos (auth, billing, canales…)

- **Entra en el mismo deploy o proceso:** Auth JWT/sesión actual (`get_current_user`), rate limits (`limiter`), billing, workers, canales, Telegram, etc. — **sin reescribir** en el núcleo Alan.

- **No entra en `langgraph-alan` core:** Lógica de negocio HyperShifu fuera del perfil CRM.

- **Puente:** Tras auth, `user_id` → `Context.user_id` + propiedad del `thread_id`; las rutas CRM **no** aceptan `user_id` del cliente. Opcional: mapear usuarios Carlos a `appdata` de Alan solo si se activa `AUTH_ENABLED` en la UI de Alan; en producto basta el auth de Carlos.

- **Billing / workers:** Siguen tocando Mongo y colas como hoy; el agente solo escribe CRM vía herramientas.

- **Automatizaciones (`automatizaciones.py`):** Permanecen en pausa; se ejecutan en `repositorio.obtener` como ahora, fuera del grafo.

---

## 6. Fases, compuertas de medición, paridad

| Fase | Entregable | Compuerta (misma medición, mismos bancos) |
|------|------------|-------------------------------------------|
| **F0** | Checklist paridad: herramientas (`edicion`+datos+toma+deshacer), campos de respuesta lab, rutas, env (`CRM_DISENO`, `CRM_LAB_ADAPTER`) | Inventario firmado |
| **F1** | Repo Alan + `profiles/crm` vacío + `labRoutes` montado; motor fake o passthrough | Bancos corren (aunque fallen); contrato HTTP OK |
| **F2** | `packs/crm` dominio + repos; tests unitarios de `operaciones`/`adaptador_lab` migrados | `pytest` dominio verde |
| **F3** | Tools + `CrmToolGuard` + persistencia doc; **sin** `revisar_respuesta` aún | `banco_datos` ≥ línea base 63/63 |
| **F4** | `CrmTruthGuard` + deshacer/puntos + ganchos | `banco_deshacer` 17–18/18, `banco_pestanas` ≥22/27 |
| **F5** | Toma, conceptos, memoria híbrida, citas | bancos homónimos + `banco_memoria` 13–18/18 |
| **F6** | `crmRoutes` producción, brief, logo, import; desconectar `agente_diseno` legacy | `backend/test/crm` + smoke E2E |
| **F7** | Streaming UI, HITL unificado, candado Mongo multi-worker | Carga y concurrencia |

**Checklist paridad (extracto):** todas las funciones en `SesionDiseno.herramientas`, `consultas` en respuesta, `puntos` con foto, `por_hacer` entre turnos, `pendiente` borrados, selección de pestaña, adjuntos/CSV, `traza` opcional, 2–3 llamadas modelo (`MODEL_CALL_LIMIT=3`, clasificador off).

**Riesgos:** regresión silenciosa al cambiar memoria (16 mensajes → checkpointer); clasificador de esfuerzo (+1 llamada) si no se fija `MODEL_CALL_LIMIT`; pérdida de cercos si se reimplementan en prompt; tamaño del catálogo de tools (evaluar `USE_BIGTOOL=1` + índice semántico); 18k tests que asumen bucle async LangChain directo.

---

## 7. Lo que más preocupa y qué haría distinto

**Preocupación principal:** **Dos runtimes** (bucle manual async en `agente_diseno` vs grafo sync de Alan) con **estado de sesión rico** (`doc` mutado, `deshecho`, `cambios`, `consultas`). Si las tools son funciones sin contexto compartido, se rompen cercos y deshacer. Exige **`CrmContext` inmutable en config + sesión por turno en middleware**, no variables globales.

**Segunda:** **Concurrencia** (versionado CRM + candado in-process + varios workers).

**Tercera:** **Presupuesto de llamadas** — las correcciones de `revisar_respuesta` *son* llamadas al modelo; hay que contarlas dentro del tope 3 y priorizar cercos en código sobre “auto-corrección” del modelo.

**Haría distinto:** (1) **No fusionar monolitos en un solo PR** — servicio Alan embebido detrás de `responder_lab` hasta que los bancos verdes lo validen. (2) **Un solo paquete `packs/crm/sesion`** con tests copiados de `agente_diseno` antes de borrar el bucle viejo. (3) **`MODEL_CALL_LIMIT=3` y documentar** que `EFFORT`/clasificador quedan prohibidos en CRM. (4) **No activar `ANSWER_VERIFY`** (duplica verificación que ya hace `revisar_respuesta` orientado a dominio). (5) Estudiar **rama `feat/agente-codificador`** solo para patrones `tool_spec`/sandbox, no para mezclar codificador con CRM en el mismo perfil.

---

*Nota: estoy en modo Ask; esto es plan y análisis únicamente, sin cambios en el código.*
