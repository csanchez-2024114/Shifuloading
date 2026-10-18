# REFACTOR_NOTAS: pendientes fuera del alcance del refactor

Este refactor solo reorganiza. Todo lo de aquí abajo es un **cambio de comportamiento** y va en commits o tareas aparte, después de terminar el refactor y con la suite en verde.

## Fase 4, primera tarea: hecha

bigtool ya tiene `read_file` y `search_in_file`, la regla de archivos en `PromptedModel` y la cita literal obligatoria en hilos con adjuntos (`test_archivos_bigtool.py`). Se quitó el bloqueo `FILES_ENABLED`+`USE_BIGTOOL`. Corrección de lo anotado en la Fase 2: bigtool no "recibía las herramientas de archivos sin la regla"; no las recibía en absoluto, porque su registro no parte de `base_tools`.

## Tarea siguiente: que todo lea el perfil pasado a `build_agent`, no solo `AGENT_PROFILE`

Hoy, pasar `profile=` a `build_agent`, `build_tools`, `create_app` o `system_prompt_text` decide el prompt, las herramientas, las aprobaciones, las herramientas-evidencia y los nombres antiguos del middleware. Pero hay piezas que leen siempre el perfil **activo** (`active_profile()`, es decir, `AGENT_PROFILE`), aunque se haya pasado otro:
- **reglas de intención:**
  - la regla de mensaje corto de `elegir_esfuerzo` (`necesita_clasificador`, `core/agent.py:74`; nadie le pasa `intents=`);
  - "continúa" tras un corte (`core/agent.py:228`);
  - el pedido explícito de investigar (`core/tools.py:560`);
  - el encabezado de fuentes en las citas (`core/citations.py:59`);
- **léxico de la memoria:** `core/memory.py:104` (forma neutra y búsqueda por palabras);
- **avisos durante el turno:** las llamadas a `tr(...)` sin perfil en `core/agent.py` (tope de llamadas, corte, no verificada, tope del turno, recursión);
- **tarjeta de `deep_research`:** el predicado `research_needs_confirmation` y `earlier_research`, que usa los nombres antiguos del perfil activo (`core/tools.py:528`);
- **`rename_old_tools`:** su default sin `legacy=` (`core/agent.py:245`).

Con un solo perfil por proceso, el resultado es el mismo. Con dos perfiles en un proceso (o un test que pase `profile=` sin fijar `AGENT_PROFILE`), no. La propuesta es llevar el perfil por el contexto del grafo (`Context`/`runtime`) o por los constructores de los middleware y las herramientas, y probarlo con dos perfiles distintos en el mismo proceso. Es un cambio de comportamiento para el caso multi-perfil, así que va en su propia tarea.

## Seguridad (de la auditoría del 2026-10-17, `docs/AUDITORIA_AGENTE.md`): siguiente fase, sin implementar (después de la tarea anterior)

| # | Hallazgo | Dónde (antes de mover) |
|---|---|---|
| S1 | Con `AUTH_ENABLED=0` (default), `user_id` viene del navegador y `/memories/{user_id}` lee y borra sin control. No se valida `Host` (DNS rebinding: a confirmar) | `server.py:31`, `server.py:216`, `server.py:389-399` |
| S2 | Prompt injection hacia la memoria: el contenido web no se marca como no confiable y, con `MEMORY_VERIFY=0`, un recuerdo sin cita se guarda | `tools.py:268`, `tools.py:341`, `memory.py:320-321` |
| S3 | Exfiltración por enlaces: el filtro de URLs solo corre con `ANSWER_VERIFY=1` | `index.html:427-433`, `agent.py:714-715` |
| S4 | DoS de la calculadora (`((10**10000)**10000)**10000`, `factorial` sin tope) | `tools.py:47`, `tools.py:55-59`, `tools.py:43` |
| S5 | Sin longitud máxima de mensaje ni presupuesto por usuario; la llamada final siempre se permite | `server.py:28-32`, `agent.py:938-963` |
| S6 | `wikipedia_summary`: `language` va directo al host (SSRF/exfiltración), solo bigtool | `extra_tools.py:239-246` |
| S7 | El evento `error` y `Tool error` exponen el texto de la excepción | `agent.py:1076-1078`, `agent.py:573-574` |

Los tests de caracterización **fijan a propósito** el comportamiento actual de S4 y S7 (`calculadora_caracterizada`, `stream_con_excepcion_da_tipo_y_mensaje_sin_done`). Cuando se arreglen, esos tests se cambian en el mismo commit del arreglo, diciéndolo.

## Defectos y deudas vistos durante la Fase 0

- **`CONTRATO.md` está desactualizado respecto al código** (es previo a este refactor):
  - dice `recursion_limit: 25` y `model_call_limit: 15`; los defaults reales son 100 y 0 (`config.py:96-97`);
  - la firma de `make_investigador` y la pila de `build_agent` que describe no son las actuales.

  La sección de eventos SSE sí coincide con el código. El refactor no cambiará su formato. Se corrige en un commit de docs aparte **después de la Fase 6**, con los valores tomados del código.
- **Concurrencia en un mismo hilo:** `_ACTIVE_TURNS[thread_id]` se pisa con dos `/chat` simultáneos (`agent.py:872`, `agent.py:1015`, `agent.py:1081`).
- **Estado de proceso** (`_ACTIVE_TURNS`, `_PAUSED_SPEND`, `tools._TURNS`): no escala a varios workers.
- **Bigtool:**
  - `effect="write"` (`crm_create_order`) no pide aprobación: `effect` solo se valida (`tool_spec.py:161`). La interfaz de perfil ya trae `ToolPolicy.effect/approval`; **aplicarlo** a herramientas que hoy no piden aprobación sería un cambio de comportamiento.
  - Sin compactación, `ANSWER_VERIFY` ni tope por esfuerzo.
- **Dependencias sin fijar y sin lockfile** (`pyproject.toml:5-21`).
- **La UI depende de los mensajes en inglés del núcleo** (`toolOutputLabel`). Un perfil que cambie esos mensajes rompe las etiquetas. Tarea aparte: etiquetas de la UI por perfil (`labels.json`) y una cáscara de UI genérica.
- **Defaults de configuración por perfil** (Q6): descartado en esta tarea; mejora posterior si hace falta.
- **`check_python_syntax` es candidato a pack** (Q4): en este refactor se queda en `core/tools.py` y fuera de `generic`. Moverlo a `packs/tools/` cuando haya un segundo perfil que lo quiera.

## Anotado en la Fase 3 (interfaz de perfil)

- **`package-data`:** `system.md` e `index.html` viven ahora dentro del paquete (`src/assistant/profiles/default/`). La instalación editable por ruta (la de este proyecto) los encuentra; un *wheel* necesitaría declararlos en `pyproject.toml`. Sin cambio hasta que haga falta.
- **`ToolPolicy.effect` no se aplica todavía:** es metadato (`send` para el email, `read` para `deep_research`). Usarlo para pedir aprobación, por ejemplo en `crm_create_order`, sería un cambio de comportamiento.
- **`AGENT_PROFILE` vive fuera de `Settings`:** la lee `core/profile.py`, así la lista de variables de la huella no cambia. Falta documentarla en README y `.env.example` (Fase 6).
- **Nombres antiguos en español todavía literales en `core/`:** `context.PRUNE_KEEP_TOOLS`, `memory.turn_saves` y `tools.extra_search`. Pasan a la normalización con `profile.legacy_tool_names` en la Fase 4, y ese commit cambiará el valor de `context.PRUNE_KEEP_TOOLS` en la huella.
- **Perfil activo frente a perfil explícito:** `earlier_research` y `research_needs_confirmation` (y la aprobación de `deep_research` que las usa) leen los nombres antiguos del perfil **activo** (`AGENT_PROFILE`), no del que se pasa a `build_agent`. Da igual mientras el perfil explícito sea el activo; revisarlo si un proceso llega a servir dos perfiles.
- **`DeprecationWarning`:** son 15 (eran 13). Los 2 nuevos son los alias `assistant.apps` y `assistant.extra_tools`, que siguen usando `test_tool_spec` y `test_extra_tools`. No hay filtros.

## Anotado en la Fase 4 (textos y reglas)

- **Pendientes de enforcement en bigtool** (se quedan como están, a propósito):
  - `BIGTOOL_PROMPT` sigue como default del núcleo, en inglés y sin campo en el perfil;
  - el `interrupt()` de `deep_research` sigue fijo en `core/extensions/bigtool.py`: no lee `profile.tool_policies` (aprobaciones ni `effect`), solo toma del catálogo el texto de la tarjeta.

  Que bigtool obedezca las políticas del perfil, como hace el agente normal con `HumanInTheLoopMiddleware`, sería un cambio de comportamiento.
- **Siguen en español en `core/`, a propósito:**
  - logs (`logger.*`), docstrings y comentarios (regla del proyecto: comentarios en español; los logs son para quien opera);
  - los errores del cargador de perfiles (decidido: en español);
  - el `"si"`/`"sí"` que acepta `_bool` al leer el entorno;
  - el `ValueError` interno "respuesta vacía del web_search hospedado", que solo dispara el respaldo a DuckDuckGo y va al log.
- **Perfil activo frente a perfil explícito (amplía la nota de la Fase 3):** los textos (`tr`), las reglas de intención y el léxico de memoria se leen del perfil **activo** (`AGENT_PROFILE`), salvo en el servidor y en las tarjetas de aprobación, que usan el perfil que reciben. Revisarlo si un proceso llega a servir dos perfiles.
- **`IntentRules`, `MemoryLexicon` y `TextCatalog` por defecto no asumen idioma:** las reglas no reconocen nada, el léxico no tiene palabras vacías ni temas y el catálogo está vacío (así que `load_profile` exige todas las claves). Un perfil nuevo debe traer su catálogo (por ejemplo `packs/i18n/es.py`), y las reglas y el léxico si los quiere.
- **La huella tiene 136 constantes, no 139.** La cifra 139 de la Fase 0 era de la primera generación, antes de excluir el estado en vivo. Corregido en `PARIDAD.md`.

## Anotado en la Fase 5 (prueba de pivote)

- **Pasos que no estaban en el plan, cada uno en su commit y sin cambio de comportamiento:**
  - la UI pasa a `packs/ui/`, con los mismos bytes;
  - `ToolPolicy.evidence` reemplaza la tupla fija `EVIDENCE_TOOLS`, con el mismo valor para `default`;
  - las reglas de intención pasan a `packs/lang/es_en.py`, porque un perfil no importa otro y `generic` las comparte.
- **Con `USE_BIGTOOL=1`, el registro siempre trae las 8 herramientas base del núcleo**, `check_python_syntax` incluida, así que `generic` en bigtool sí la tiene. Para que el perfil filtre ese registro, `build_tools` o un campo nuevo tendría que aplicarse también a bigtool. Sería un cambio de comportamiento, y se suma a los pendientes de bigtool de la Fase 4.
- **La UI compartida solo conoce las etiquetas de las herramientas del núcleo y de `default`:** una herramienta nueva (`word_count` en `tests/profiles/minimal`) sale con su nombre crudo. Un perfil que quiera etiquetas propias necesita su propio `static_dir`. Una opción futura es que la UI pida las etiquetas al servidor.
- **`generic` repite** su política de memoria `strict` y la regla de economía de búsqueda, en una versión más corta. Las de `default` viven en `profiles/default/policies.py`. Si un tercer perfil las necesita, conviene moverlas a un pack.
- **Los perfiles de `tests/profiles/` se cargan por ruta con puntos** (`profiles.minimal`). Funciona porque pytest pone `tests/` en `sys.path`. `available_profiles()` solo lista los de `assistant.profiles`.

## Anotado en `feat/seguridad-core` (P2–P4 de la auditoría)

- **DDGS se queda como está:** `DDGS()` ya trae un timeout de 5 s (ddgs 9.16). La auditoría proponía `DDGS(timeout=10)`, que lo aflojaría. Fijarlo explícito obligaba a tocar `caracterizacion::formato_de_duckduckgo`, cuyo DDGS falso no acepta argumentos.
- **`Tool error (...)` es candidato a interruptor:** el texto de la excepción le llega al modelo (`core/agent.py:_on_tool_error`, `core/extensions/bigtool.py`). Puede llevar detalles internos (S7), pero el prompt le pide al modelo "leer el error y probar otra vía", así que quitarlo cambia lo que ve. Propuesta: `TOOL_ERROR_DETAIL=1` por defecto; con 0, solo el tipo de excepción.
- **Clientes de OpenAI fuera de `ChatOpenAI`:** `openai.OpenAI` (en `verify_model`, al arrancar) y `OpenAIEmbeddings` (memoria semántica) no llevan `LLM_TIMEOUT_SECONDS`/`LLM_MAX_RETRIES`; usan los defaults de la librería.
- **`tool_spec.EFFECTS` sigue en `("read", "write")`:** la auditoría (P3.3) proponía sumar `"send"` y `"delete"`, pero es una constante que fija la huella y cambiaría la sección `constants`. `EFFECT_APPROVAL` ya trata como "con efecto" todo lo que no sea `"read"`, así que una ficha `@tool_spec` con `send` o `delete` solo necesita que se amplíe la tupla. Va en un commit aparte, que diga que cambia esa constante.
- **`URL_FILTER_ALWAYS` solo cubre el agente normal:** bigtool no tiene middleware, así que el filtro de enlaces de su respuesta final está pendiente.

## De la validación E2E con el modelo real (`docs/VALIDACION_E2E.md`, línea base del 2026-10-17)

- **Costo tras rechazar la tarjeta de `deep_research`** (observación 1): tras el rechazo, el modelo hizo una `web_search` y escribió un informe largo: 24k tokens en la reanudación, 3 veces lo estimado. Es correcto y honesto, porque el prompt dice "If they decline, answer without it" y no prohíbe buscar. Si se quiere un rechazo barato, habría que decirlo en el prompt o en el resultado del rechazo (por ejemplo, "answer briefly from your own knowledge; do not search"). Es un cambio de comportamiento, así que necesita su interruptor o tu decisión.
- **El 413 de `MAX_MESSAGE_CHARS` se ve con el JSON crudo** (observación 3): la UI muestra el texto de la respuesta tal cual: `⚠️ Error del servidor (413): {"detail":"El mensaje es demasiado largo…"}`. Mejoraría si la UI leyera `detail` en los errores HTTP de `/chat` y `/resume`. Tocar `packs/ui/index.html` cambia el sha256 de la huella, así que va en un commit propio, que lo diga.
- **La tarjeta aprobada sigue diciendo "✓ Investigando…"** (observación 4): cuando la investigación ya terminó y el informe está debajo, la tarjeta conserva el texto de la decisión, que se lee como si siguiera en curso. Habría que cambiarlo a algo como "✓ Aprobada" al llegar `done`. Es un cambio de la UI, con la misma nota sobre la huella.

## Anotado en la Fase 2 de `feat/seguridad-core` (análisis de archivos, `FILES_ENABLED`)

- ~~**bigtool recibe las herramientas de archivos sin la regla del prompt de archivos**~~ (resuelto en la Fase 4; en realidad no las recibía). `base_tools` agrega `read_file` y `search_in_file` con el interruptor, y el registro de bigtool parte de `base_tools`. Pero `PromptedModel` no añade `FILE_UNTRUSTED_RULE` cuando el hilo tiene adjuntos, como sí hace el `dynamic_prompt` del agente normal. La salida va envuelta en `<untrusted_file_content>` igual y la memoria exige cita literal en hilos con adjuntos; lo que falta es la regla. Sin arreglar.
- **`generic` no recibe las herramientas de archivos aunque `FILES_ENABLED=1`**: su `build_tools` filtra `base` por la lista `TOOLS`, que no las incluye. Las rutas de subida sí existen, así que el usuario puede adjuntar un archivo que el modelo no puede leer (las imágenes sí llegan). Documentado en `docs/CREAR_PERFIL.md`. Sin arreglar.
- **La memoria semántica y `put(index=False)`**: `langgraph-store-mongodb` lanza `IndexError` con `put(..., index=False)` en un store con índice vectorial. Se evitó guardando los archivos en un store sin índice (colección `file_store`). Si se actualiza la librería, conviene revisar si se corrigió.

## Anotado en la prueba real de la Fase 3 (2026-10-18)

- **Un mensaje enviado mientras carga el historial desaparece de la pantalla.** Con `?thread=<id>` en la URL, `initLocal` llama a `loadHistory` (asíncrono). Si el usuario envía antes de que responda `/history`, y el servidor leyó el historial antes de guardar el turno, la respuesta vacía llama a `showEmpty()` y borra la burbuja en vivo. El turno se procesa y se guarda, pero el usuario no lo ve y lo reenvía (pasó en la prueba real: 2 528 tokens de más). Reproducido con modelo falso retrasando `get_history`. Arreglo propuesto (cosmético, sin aplicar): que `send()` invalide la carga pendiente (`state.loadSeq++`) y quite el "Cargando conversación…".
