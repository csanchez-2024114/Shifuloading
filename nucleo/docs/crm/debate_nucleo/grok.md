El traslado deja el núcleo de Alan intacto y monta el CRM como un perfil. El árbol de `langgraph-alan` está en `main`; la rama `origin/feat/agente-codificador` (`ae8832e`) queda como segundo perfil y no entra al turno del CRM. `USE_BIGTOOL` se queda en 0: bigtool no tiene middlewares y `retrieve_tools` sería una llamada de más.

## 1. Arquitectura destino

Repositorio destino: clon de Alan. El producto no arranca con `server.create_app` (eso es la demo de Agente 0: cookie, loopback, `GET /`). Arranca un FastAPI de producto que incluye las rutas de Carlos y un puente del CRM.

| Pieza | Dónde |
|---|---|
| Núcleo (`create_agent`, `stream_events`, `MongoDBSaver`, `MongoDBStore`, cuentas demo, evals de Agente 0) | `src/assistant/core/`. Un solo añadido: `AgentProfile.extra_middleware(settings) -> list`, concatenado al final de la lista de `build_agent`. |
| Dominio del CRM | `src/assistant/packs/crm/`: `edicion.py`, `registros.py`, `toma.py`, `pantalla.py`, `conceptos.py`, `puntos.py`, `por_hacer.py`, `plantillas.py`, `sembrar.py`, `primer_diseno.py`, `diseno.py`, `operaciones.py`, `estructura.py`, `secciones.py`, `valores.py`, `validar.py`, `lienzo.py`, `marca.py`, `regional.py`, `web.py`, `chat.py` (el «sí» pendiente), `automatizaciones.py` (sigue en pausa: no entra al prompt), `vista.py`, `seleccion.py`, `ejemplos.py`, `adjuntos.py` (solo columnas y logo). |
| Caso de uso | `src/assistant/profiles/crm/`: `PROFILE`, `prompts/system.md` (inglés, el contenido de `prompt_sistema`), `tools.py` (`build_tools`), `policies.py` (`ToolPolicy`), `turno.py` (`ContextVar` `TurnoCrm`). |
| UI | La app React de Shifuloading (`src/pages/CrmPage.jsx`, `src/crm/plantillas/*`, `BriefPage.jsx`). `static_dir` del perfil no es `packs/ui/index.html`. |
| Resto de Carlos | Paquete `producto/` (auth, billing, canales, workers). En el árbol desde el día 1; cableado por fases. |
| Codificador | Perfil aparte (`AGENT_PROFILE=coder`: proyectos, sandbox, vista previa). Otro proceso si hace falta. El chat del CRM no lo llama. |

**Se adopta de Alan:** `LimiteLlamadas`, `LimiteRepeticiones`, `AterrizajeSuave`, `AvisoCorte`, `ToolErrorMiddleware`, `FiltroURLs` (`URL_FILTER_ALWAYS=1`), `HumanInTheLoopMiddleware` (reservado; ver fase 4), `tracing.apply` + `TurnRecorder`, `files/` (validar, extraer en subproceso, `read_file` / `search_in_file`, `<untrusted_file_content>`), `MongoDBStore` para recuerdos duraderos con cita (`MEMORY_REQUIRE_QUOTE=1`, `MEMORY_DEDUP=1`). `ResumenPorTurno` entra en la fase 3, con `MEMORY_SUMMARIZE=0` hasta que los bancos de memoria pasen la línea base. `MODEL_CALL_LIMIT=7` (el `MAX_VUELTAS` actual): con eso el clasificador de esfuerzo no corre. `ANSWER_VERIFY=0`.

**Se conserva porque Alan no lo tiene:** el documento `crm_workspaces` (uno por persona, `version`), `crm_puntos` con foto, `crm_logos`, `crm_conversaciones.por_hacer` y el estilo (`sanear_memoria`: tratamiento, tono, hechos, trabajo), la pantalla que calcula `pantalla.describir_pantalla`, el catálogo de `conceptos.py`, la toma y `construir_desde_ficha` (sin modelo), el primer diseño y el brief, las reglas de `chat.py` si el modelo falla, los cercos de `SesionDiseno._cerco`, el deshacer selectivo de `puntos.deshacer`, las rutas CRUD que la pantalla usa sin chat, y el adaptador `adaptador_lab.procesar_chat_lab`. El demo `profiles/default/apps/crm_demo.py` no se reutiliza: es memoria de proceso y datos semilla.

## 2. Cercos, ganchos, deshacer, pendientes, verdad

El estado del turno no va al checkpointer. El puente crea `TurnoCrm` (el doc copiado, puntos, `por_hacer`, cambios, fallos, consultas, avisos) y las herramientas lo leen. Al terminar, una sola escritura.

Middlewares del perfil, 0 llamadas nuevas:

- **`ContextoCrm.wrap_model_call`**. Al system prompt le agrega el JSON de `SesionDiseno.contexto`, `conceptos.bloque_para_prompt`, `por_hacer.bloque` y el aviso de toma. Equivale a reescribir `mensajes[0]` en cada vuelta.
- **`CercoHerramientas.wrap_tool_call`**. Antes de mutar, corre `planificar_cerco_masivo` (mirando los `tool_calls` del `AIMessage` del paso) y `_cerco` (masivo, toma, pestaña abierta, cita-como-tarea, orden que viene de la imagen, tope `MAX_ACCIONES`). Si frena, devuelve `Not run: …` y no toca el doc. Ahí viven también `toma.bloqueo_en_toma` y `error_anotar_sin_piezas`.
- **`TrasDeshacer.wrap_model_call`**. Si la vuelta fue solo `deshacer`, la siguiente llamada ve únicamente herramientas de la categoría deshecha (`CATEGORIA`), una sola vez, y luego `tool_choice="none"`.
- **`GanchosRespuesta.wrap_model_call`**. Si la respuesta no trae herramientas y `revisar_respuesta` / `revisar_pantalla` devuelven aviso (`GANCHOS_PANTALLA`, `afirma_sin_cambios`, `logro_sin_herramienta`, `afirma_sin_respaldo`, `aviso_numero_inventado`, promesa), reinvoca con el aviso, máximo `MAX_CORRECCIONES=2`. Mismo presupuesto que hoy, dentro de las 7.
- **`VerdadRespuesta.after_agent`** (como `FiltroURLs`, 0 tokens). Agotadas las correcciones, si `afirma_sin_respaldo` sigue en pie, sustituye el texto por `respuesta_del_codigo`. Si el turno fue solo deshacer, pone `_respuesta_solo_deshacer`. Añade `verdad_lado_final`, `por_hacer.linea`, `frase_columnas` y `creado_sin_decir`. La pregunta de borrar varias pestañas y el resumen de la ficha (`respuesta_confirmando`) los escribe el código, como ahora. `construir_desde_ficha` ni entra al grafo: el puente lo resuelve antes de `stream_events`.

`ToolPolicy`: `consultar_datos`, `leer_enlace`, `web_search` y las de archivo con `evidence=True` para el filtro de cifras; `quitar_*`, `borrar_registro`, `eliminar_*` con `effect="delete"`. `EFFECT_APPROVAL` se queda en 0 en las fases 1–3: el banco de conceptos espera un «sí» en el mensaje siguiente (`chat.ejecutar_pendiente`), no una tarjeta.

## 3. Datos, async y candado

Dos bases, como Alan. La de IA (`MONGODB_URI`, `MongoDBSaver` + `MongoDBStore`) guarda hilo y recuerdos. La de negocio (la Mongo de Carlos) guarda `crm_workspaces`, `crm_puntos`, `crm_logos`, `crm_conversaciones`.

El grafo es síncrono (`agent.stream`, pymongo). Las herramientas no usan motor. El repositorio del CRM se porta a pymongo síncrono (`guardar_version` igual: `replace_one` con `version`). Las rutas FastAPI siguen `async` y entran al turno con `asyncio.to_thread`. Motor sigue en workers, billing y canales, en otros procesos.

`thread_id = "crm:{user_id}"`: una conversación por persona. El candado en memoria de `server.py` (`busy: set`) aplica a ese hilo y vale con un solo worker de la API. Los workers de Carlos no corren el agente; si tocan el documento, pierde quien no tenga la `version` (409, tres reintentos, igual que `_turno_de_chat`). Varios workers de API exigen pasar ese candado a Mongo (`findOneAndUpdate` con caducidad) antes de escalar. El día 1 hay un worker.

El checkpointer no guarda el CRM. Las herramientas mutan la copia de `TurnoCrm`; el puente escribe una vez al final, con el reintento de versión, el logo antes que el doc, y `puntos_reponer` si hubo deshacer.

## 4. Frontend

Se queda React/Vite. `CrmPage` sigue recibiendo `{respuesta, crm, modo, cambios, vista, pendiente}` por `POST /api/v1/crm/chat`. El puente consume `stream_events` y entrega ese JSON al cerrar. `packs/ui/index.html` no sustituye la pantalla: su contrato es SSE, `thread_id` y tarjetas, sin documento CRM.

El chat del laboratorio no cambia de forma: `POST /api/v1/crm/lab/chat` y el alias `/api/lab/chat` que usan los bancos (`BASE` + `RUTA_CHAT`). Cuerpo `{plantilla, estado, texto, historial, muestra, seleccion, imagen}` y respuesta con `estado`, `respuesta`, `cambios`, `fallos`, `intentos`, `consultas`, `avisos`. `adaptador_lab.py` sigue traduciendo estado de laboratorio y documento.

SSE (`token`, `tool_start`, `tool_end`, `done`) es una fase posterior del panel, y el snapshot `crm` viaja en `done`. Una tarjeta de aprobación, si se enciende `EFFECT_APPROVAL`, la pinta `ChatDiseno` y se reanuda con `POST /api/v1/crm/chat/resume`; el adaptador de bancos traduce esa pausa a la pregunta de «sí» para no romper la medición.

## 5. El backend de Carlos

Entra al árbol y, por fases, al proceso: auth JWT (`authRoutes`, refresh, `get_current_user`), usuarios, workspaces, Stripe, WhatsApp, Gmail y el resto de conectores, workers (scheduler, recordatorios, workflows), archivos de producto y notificaciones. Delante del chat va el JWT de Carlos. `AUTH_ENABLED` de Alan queda en 0: su `AuthService` (cookie `agente0_session`, CSRF) no reemplaza las cuentas.

Se desconecta del turno, sin borrar archivos: `app/crm/agente.py` (`responder`, el bucle, `Sesion` como motor), el bucle de `agente_diseno._responder`, `app/tools/**` (Jira, HubSpot, el agente viejo), `agent_bus`, `shifu_chat_router` y `bigtools_loader`. Ninguna ruta vuelve a llamar `agente.responder`. Las funciones de dominio que el bucle usaba se quedan en el pack.

`automatizaciones.ejecutar_pendientes` no corre en modo diseño (ya se saca del contexto). Los workers de workflows no invocan al agente del CRM.

## 6. Fases y compuertas

Línea base, antes de mover nada, dos corridas: datos 63/63, citas ≥17/18, deshacer ≥17/18, pestañas ≥22/27, banco2 ≥14/16, conceptos ≥9/14, memoria ≥13/18. Inventario firmado: nombres de herramienta (`edicion`, `toma`, `registros`, `agente`, `agendar`, `deshacer`, `leer_enlace`), campos del lab, colecciones, y cada ruta de `crmRoutes` (CRUD, brief, siguiente-pregunta, importar, logo, puntos, deshacer, historial, memoria) más `lab/chat`.

1. **Puente.** Pack + perfil + los cinco middlewares, herramientas que llaman el Python actual. `MODEL_CALL_LIMIT=7`, `ANSWER_VERIFY=0`, `USE_BIGTOOL=0`, `MEMORY_SUMMARIZE=0`. Ruta de lab compatible el día 1. Compuerta: mismas dos corridas, ningún banco por debajo de la base. Si baja, no hay fase 2.
2. **Persistencia.** Repositorio síncrono, versión, puntos, logos. `POST /api/v1/crm/chat` con el mismo JSON. `backend/test/crm` en verde, sin IA. Bancos otra vez.
3. **Memoria y archivos.** Historial del modelo pasa al checkpointer. Primero se inyectan los mismos 16 mensajes completos (`MAX_HISTORIAL_AL_MODELO`). Luego `MEMORY_SUMMARIZE=1` con `COMPACT_STRUCTURED` y `COMPACT_FIRST_MESSAGE`, y se rehacen memoria y citas. Archivos de Alan debajo; `columnas_fuera` y el logo siguen en el pack. `actualizar_memoria` sigue en segundo plano (estilo y resumen de negocio), una llamada fuera del turno, salida por `sanear_memoria`.
4. **Producto.** React contra el JSON. JWT de Carlos. Rutas de brief, importar y CRUD. SSE opcional. Tarjetas solo si un banco nuevo lo pide.
5. **Apagar el bucle viejo.** `agente_diseno._responder` deja de ser el motor; quedan dominio y cercos. El codificador no se fusiona a este perfil.

Checklist de paridad por fase: cada herramienta, cada rama de `_cerco`, ganchos, deshacer con foto, `por_hacer`, toma, brief, primer diseño, importar, logo, regional, «sí» pendiente, traza (`cambios`, `fallos`, `intentos`, `consultas`, `avisos`) y el fallback a `chat.py`.

## 7. Lo que más me preocupa

El gancho `extra_middleware` es el único toque al núcleo, y hace falta: sin él, el cerco cabe dentro de la herramienta, pero el contexto de pantalla, el filtro tras deshacer y la verdad de la respuesta se quedan fuera de `build_agent`. Lo dejaría explícito y cubierto por el test de caracterización.

No metería las ~50 herramientas en bigtool. El filtro por modo (toma, diseño, datos) ya existe en `SesionDiseno.herramientas` y pasa a `ContextoCrm` sin una llamada de recuperación.

No escribiría el documento con motor desde una herramienta: bloquea el loop o se mezcla con el hilo del grafo. Una escritura síncrona al final del turno.

No cambiaría el texto de la respuesta a «lo que el código cree verdad» en la misma fase en que se cambia el motor. Los bancos comparan frases. Los ganchos que reinvocan se quedan en la fase 1; la sustitución en `after_agent` se mide sola, después.

No levantaría billing, WhatsApp y el agente en el mismo arranque. El código de Carlos entra al árbol en la fase 1 para no perderlo; sus routers siguen apagados hasta la compuerta de la fase 2. El candado en memoria no es un candado de clúster: con un worker basta, y la `version` del documento cubre el resto.
