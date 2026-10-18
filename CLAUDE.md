# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Agente 0: asistente tipo ChatGPT con LangGraph 1.2 (`create_agent` + middleware), OpenAI `gpt-6-luna` vía Responses API, MongoDB (checkpointer + store), servidor FastAPI con SSE y una interfaz de un solo archivo (`src/assistant/packs/ui/index.html`). Windows, sin Docker. La documentación del proyecto está en español (README.md, CONTRATO.md).

El código está separado en un núcleo reutilizable (`src/assistant/core/`), piezas compartibles (`src/assistant/packs/`) y perfiles por caso de uso (`src/assistant/profiles/`). El perfil se elige con `AGENT_PROFILE`: vacía, carga `default`, que es Agente 0 con el comportamiento de siempre. Cómo crear uno: `docs/CREAR_PERFIL.md`.

Estado de capacidades (qué está probado con el modelo real y qué solo con modelos falsos) e interruptores con su default: `docs/ESTADO.md`. Qué activar en el `.env`: `docs/ACTIVACION.md`. Validaciones reales: `docs/VALIDACION_E2E.md`.

## Comandos

```powershell
uv venv .venv
uv pip install --python .venv -e ".[dev]"                         # o: uv sync --extra dev (versiones exactas de uv.lock)
.venv\Scripts\python -m uvicorn assistant.server:app --host 127.0.0.1 --port 8000   # app en http://localhost:8000
$env:AGENT_PROFILE="generic"; .venv\Scripts\python -m uvicorn assistant.server:app --port 8001   # otro perfil
.venv\Scripts\python -m pytest                                    # suite completa (0 tokens, modelos falsos)
.venv\Scripts\python -m pytest tests/test_chip_honesto.py -q      # un archivo
.venv\Scripts\python -m pytest tests/test_ui_navegador.py -k investigacion -q   # por nombre
.venv\Scripts\python scripts\run_evals.py                        # evals en modo falso (0 tokens); --real solo muestra el costo
```

- pytest **siempre** usa el Mongo local `mongodb://127.0.0.1:27017`, con las bases `assistant_test` (IA) y `app_test` (negocio). Lo fuerza `tests/conftest.py` aunque `.env` apunte a Atlas. Los tests con Mongo se saltan si no responde.
- `tests/test_ui_navegador.py` usa Playwright con Edge o Chrome ya instalados (headless) contra la app real, con un modelo falso controlable (`Controlable`: la palabra del mensaje decide qué herramienta pide). Se salta si no hay navegador.
- `conftest.py` ofrece `FakeChat`, `FakeSearch` y `_settings(**overrides)` para construir agentes sin red.
- No hay linter configurado.
- Dependencias: rangos en `pyproject.toml`, versiones exactas en `uv.lock` (las de `.venv`). Extra `[files]` para `FILES_ENABLED`.
- Evals: `evals/dataset.jsonl` (casos con `gate` quality/security), `scripts/run_evals.py` (falso o real), `scripts/eval_server.py` (servidor medido para el modo real: :8001, base `assistant_ux_tmp_*`, `--app-db` para la base de negocio temporal, tope duro con 429) y `scripts/compare_evals.py`. `tests/test_evals.py` corre todo el modo falso.

## Reglas del usuario (vigentes)

- MongoDB ya está instalado como servicio: solo conectarse. No instalarlo, arrancarlo ni crear scripts que lo levanten.
- No tocar `.env` ni los datos reales en Atlas (base `assistant`). No cambiar la conexión. `scripts/migrate_memories.py` nunca con `--apply` sobre datos reales.
- Sin commits hasta que se pidan; nunca push, ramas nuevas ni `--force`. Mensajes de commit en español. Antes de commitear: suite completa en verde y revisar `git diff --cached` (sin `.env`, claves, URIs con contraseña, `.playwright-mcp/`, `data/`, temporales ni datos de usuarios).
- Todo lo que lee el modelo (prompts, descripciones de herramientas, resultados de herramientas) va en **inglés**; los avisos al usuario y la UI, en **español**. Los comentarios del código están en español.
- Pruebas reales con la API: anunciar tope y estimación antes; usar una instancia aparte (p. ej. puerto 8001, base temporal `assistant_ux_tmp_*`, `TURN_TOKEN_CAP` bajo solo ahí) sin tocar el servidor del 8000; al terminar borrar la base temporal y detener la instancia.
- `langgraph` está fijado `>=1.2.15,<1.3`: el cierre de turno abortado en bigtool usa `CONFIG_KEY_RUNTIME` de `langgraph._internal`. Si se actualiza, vigila `tests/test_cierre_abortado.py`. `langgraph-bigtool` va fijado a un commit de git (PyPI 0.0.3 está roto con 1.x).

## Ramas y huella

- `refactor/core-profiles` y la primera parte de `feat/seguridad-core` ya están fusionadas en `main` (`cf0b624`, con `--no-ff`); el estado anterior está en el tag `pre-refactor-core-profiles` (`0dce7d4`). `feat/seguridad-core` sigue por delante de `main` (evals, archivos, trazas/métricas/feedback, Fase 4). Los merges los decide el usuario: nunca hagas merge ni push sin que lo pida.
- Un refactor y un cambio de comportamiento nunca van en el mismo commit. Un commit por paso, con la suite en verde.
- **La huella** (`tests/snapshots/perfil_por_defecto.json`):
  - una variable nueva regenera SOLO la sección `config` (`UPDATE_SNAPSHOTS=1 pytest -k huella`) y se declara en `NEW_CONFIG_VARS`; `test_config_solo_cambia_por_las_variables_declaradas` lo fija;
  - un cambio de `packs/ui/index.html` cambia `index_html_sha256`: se propone con el sha nuevo, se aplica con OK del usuario y el commit dice los dos hashes;
  - `test_con_files_enabled_en_0_la_huella_es_la_de_3b9b903` exige que todo lo demás siga igual que en `3b9b903` con los defaults;
  - las constantes siguen fijadas contra `05773c4`: si una cambia de módulo, va a `MOVED_CONSTANTS` con el mismo valor; si cambia un valor, detente y avisa.
- No agregues constantes nuevas en MAYÚSCULAS a los módulos que recorre la huella (`CONST_MODULES`): ponlas en un módulo propio (como `untrusted.py`, `tracing.py`, `metrics.py`, `feedback.py` o `files/`) o en minúscula.
- Todo cambio que vea el modelo va detrás de un interruptor con default 0 (ver `docs/ESTADO.md`).
- `tests/test_dependencias.py` va en modo estricto, con la lista blanca vacía:
  - `core` no importa `packs` ni `profiles`;
  - `packs` no importa `profiles`;
  - un perfil no importa otro (tampoco los de `tests/profiles/`).
- Los `DeprecationWarning` de los alias viejos (15) quedan sin filtro.
- Pendientes y la siguiente fase (seguridad S1–S7): `REFACTOR_NOTAS.md`. El plan, por fases: `REFACTOR_PLAN.md`. La paridad de funcionalidades: `PARIDAD.md`.

## Arquitectura

Flujo de un mensaje:
1. `packs/ui/index.html` → `POST /chat` (o `/resume` tras una tarjeta de aprobación) en `core/server.py`;
2. `elegir_esfuerzo` (regla o clasificador LLM);
3. `stream_events` en `core/agent.py`;
4. eventos SSE: `run` (primero, solo con `TRACE_METADATA`), `token`, `tool_start`, `tool_end`, `interrupt`, `verify`, `summarized`, `context`, `effort`, `progress`, `no_tools`, `error` y `done`.

**CONTRATO.md es el contrato de esos eventos y endpoints**: actualízalo si cambia su formato.

Rutas: las de abajo son relativas a `src/assistant/`. Los nombres viejos (`assistant.agent`, `assistant.server`, `assistant.tools`, `assistant.extra_tools`, `assistant.apps`…) siguen funcionando como alias, con el mismo objeto de módulo (`_compat.py`, un `MetaPathFinder`), y emiten un `DeprecationWarning`.

### Perfiles y packs

- **`core/profile.py`**: `AgentProfile`, con estos campos:
  - prompt, `static_dir` y `display_name`;
  - `build_tools(model, settings, base)` y `bigtool_tools(settings)`;
  - `tool_policies: {nombre: ToolPolicy(effect, approval, description_key, evidence)}`;
  - `memory_policies` (con `"strict"` obligatoria) y `search_economy_rule`;
  - `legacy_tool_names`;
  - `texts` (`TextCatalog`), `intents` (`IntentRules`) y `lexicon` (`MemoryLexicon`).

  `load_profile` lo importa por nombre (`assistant.profiles.<x>` o una ruta con puntos), lo guarda en caché y lo valida. Los errores salen en español: perfil inexistente (con la lista de los disponibles), sin `PROFILE`, sin `"strict"` o con claves de `REQUIRED_TEXTS` que faltan.
- **El perfil por parámetro:** `build_agent`, `build_bigtool_agent`, `build_tools`, `create_app` y `system_prompt_text` aceptan `profile=`; con `None`, usan el perfil activo, que se resuelve al usar y nunca al importar. **Dentro de un turno manda el perfil del agente:** `stream_events` lo fija con `profile_scope` (un `ContextVar`) y `current_profile()` lo devuelve a `tr()`, las reglas de intención, el léxico de la memoria, los nombres antiguos y la tarjeta de `deep_research`. Fuera del turno, el servidor pasa al clasificador de esfuerzo las intenciones del perfil del agente. Lo prueba `tests/test_dos_perfiles.py`.
- **`core/i18n.py`**: `REQUIRED_TEXTS`, `FILE_TEXTS` (claves que se exigen solo con `FILES_ENABLED=1`) y `tr(key, profile=None, **values)`. Los textos al usuario no viven en el núcleo: salen del catálogo del perfil. Claves opcionales con texto de respaldo en el código: `http.thread_busy`, `startup.metrics_need_app_db`, `startup.feedback_needs_trace`.
- **`profiles/default/`**: Agente 0. Sus piezas:
  - `prompts/system.md`: prompt en inglés; se relee en cada mensaje, así que no hace falta reiniciar;
  - `tools.py`: base + `send_simulated_email` con `ENABLE_HITL_DEMO`; extras de bigtool;
  - `policies.py`: `TOOL_POLICIES` (email y `deep_research` con aprobación; `web_search`/`deep_research` como evidencia), `OLD_TOOL_NAMES`, `MEMORY_POLICIES` y `SEARCH_ECONOMY_RULE`;
  - `apps/crm_demo.py`.
- **`profiles/generic/`**: prueba de pivote con 7 herramientas base, sin `check_python_syntax` ni email (filtra `base` por nombre, así que tampoco recibe `read_file`/`search_in_file`). `tests/profiles/minimal/` es un perfil externo de prueba.
- **`packs/`**: lo compartible entre perfiles.
  - `i18n/es.py`: textos al usuario, `TEXTS`;
  - `lang/es_en.py`: `INTENTS` (continuar, señales del clasificador, investigar, encabezado de fuentes) y `LEXICON` (memoria por palabras);
  - `tools/utilities.py`: 31 utilidades de bigtool;
  - `tools/demo.py`: demos de math y texto;
  - `ui/index.html`: la UI, con `STATIC_DIR`.

### Núcleo (`core/`)

- **`agent.py`**: `build_agent` arma `create_agent` con una pila de middleware. Los más relevantes:
  - `LimiteLlamadas`, `LimiteRepeticiones` y `AterrizajeSuave`: el turno tiene un tope de tokens (`TURN_TOKEN_CAP`), contado por el callback `TurnTokens`. Al 80% se fuerza `tool_choice="none"`. El aborto real solo ocurre en una frontera de paso (`_step_kind`) y `_close_aborted_turn` deja el hilo consistente.
  - `HumanInTheLoopMiddleware`: las aprobaciones del perfil (`ToolPolicy.approval`). En el perfil default son `deep_research` (predicado `research_needs_confirmation`) y el email simulado. Su rechazo genera un `ToolMessage` desde el nodo del middleware, no desde `tools`.
  - `AvisoCorte` y `_continue_cut`: respuestas cortadas por `max_tokens`.
  - `ResumenPorTurno`: compactación sobre `SummarizationMiddleware`:
    - se activa con `MEMORY_SUMMARIZE` y se dispara por % de `CONTEXT_WINDOW_TOKENS` o, si está definida, por `SUMMARY_TRIGGER_TOKENS`;
    - una por turno, con registro en `compaction_log` y capa estructurada (`COMPACT_STRUCTURED`);
    - con `COMPACT_FIRST_MESSAGE`, cita el primer mensaje del usuario: la línea `FIRST USER MESSAGE …` la pone el código, se arrastra en `first_user_message` y se quita de lo que ve el resumidor; con ella, el encabezado es `SOURCED_SUMMARY_HEADER`;
    - `compact_thread` es la compactación manual.
  - `AnswerVerifier`: `ANSWER_VERIFY`. Solo usa como evidencia las herramientas marcadas `evidence=True` en el perfil (`evidence_tools`) que de verdad corrieron (`is_evidence`).

  `_update_events` traduce los updates del grafo a eventos SSE. `get_history` reconstruye el historial para la UI. Las herramientas que no se ejecutaron (prefijos `NOT_RUN_PREFIXES`) se reportan con `status: "skipped"` y la UI nunca les pone "✓".
- **`context.py`**: medidor de contexto por hilo (`MedidorContexto`, estado `context_stats`/`compaction_log`, `context_in_use`: uso real de la última respuesta o estimación) y poda de resultados viejos de herramientas (`PodaHerramientas`, `COMPACT_PRUNE_TOOLS`; `prune_keep_tools()` deja las de memoria con sus nombres antiguos). Endpoint `GET /threads/{id}/context`.
- **`tools.py`**:
  - Las 8 herramientas base, en `base_tools`: `web_search` (OpenAI hospedado con respaldo DuckDuckGo, una búsqueda por respuesta del modelo, presupuesto compartido por mensaje), `calculator`, `current_datetime`, `check_python_syntax` (solo `ast.parse`), las 3 de memoria y `deep_research`. `build_tools` pasa la base al perfil.
  - `deep_research` es un subagente investigador con sus propios topes que reutiliza investigaciones previas del hilo. `research_approval()` da su aprobación.
  - Los textos al modelo son constantes en inglés (`*_MSG`, `*_DOC`) y se quedan en el núcleo: la UI los traduce por prefijo.
- **`memory.py`**: política de guardado (`MEMORY_SAVE_POLICY`; el texto sale de `memory_policies` del perfil y va al final del prompt del sistema; ningún recuerdo se inyecta en el prompt) y recuerdos largos en `MongoDBStore`, namespace `("user", user_id, "memories")`, con procedencia (`evidence`, `confidence`, `thread_id`) y verificación opcional (`MEMORY_VERIFY`). La búsqueda por palabras usa el `lexicon` del perfil.
- **`files/`** (`FILES_ENABLED=1`): `validate.py` (tipo por contenido, macros, zip bomb, nombres), `extract.py` (subproceso `python -I` con topes y timeout), `store.py` (lo extraído en el store del agente, por usuario e hilo; con un store vectorial, en la colección `file_store` sin índice por un `IndexError` de langgraph-store-mongodb) y `tools.py` (`read_file`/`search_in_file`, salida siempre en `<untrusted_file_content>`). Un mensaje con adjuntos lleva la ficha en `additional_kwargs["attachments"]`; en un hilo con adjuntos el prompt suma `FILE_UNTRUSTED_RULE` y la memoria exige cita literal. Rutas en `server.py` (`_install_file_routes`).
- **`tracing.py`** (`TRACE_METADATA`): `run_id`, `run_name`, metadatos y tags del turno; evento SSE `run`. **`metrics.py`** (`TURN_METRICS`): `TurnRecorder` arma la fila del turno a partir de sus eventos (`stream_events(..., observer=)`; sin observer, los eventos son los mismos) y `summarize` para `/metrics/summary`. **`feedback.py`** (`FEEDBACK_ENABLED`): `create_feedback` en LangSmith en segundo plano. Las filas van a los repos `turn_metrics` y `feedback` de `appdata` (índices y TTL en la primera escritura).
- **Candado por hilo** (`server.py`, siempre activo): `/chat` y `/resume` responden 409 si el hilo ya tiene un turno; se suelta cuando el iterador del turno se cierra (`_held`). Vive en memoria: **vale solo con un worker de uvicorn**; para varios, hay que moverlo a Mongo.
- **`extensions/bigtool.py`** (`USE_BIGTOOL=1`): agente alterno con langgraph-bigtool.
  - El modelo solo ve `retrieve_tools`, que busca en un índice semántico (`InMemoryStore` con embeddings) del registro: las 8 herramientas base más `profile.bigtool_tools(settings)`. En el perfil default, esas extras son las utilidades, las demos y las apps.
  - No soporta middleware, así que replica a mano lo esencial:
    - `PromptedModel`: prompt y aterrizaje suave;
    - `interrupt()` dentro de `deep_research`: no lee `tool_policies` (está pendiente);
    - con `FILES_ENABLED=1`, su propio `read_file`/`search_in_file` (`_file_tools`), la regla de archivos en `PromptedModel` y la cita literal en su memoria;
    - `_seguro(t, hidden)`: con `TOOL_ERROR_DETAIL_HIDDEN=1`, solo el tipo de excepción;
    - `_seguro`, que re-lanza `GraphBubbleUp`.

  Cualquier cambio de comportamiento del agente normal suele necesitar su equivalente aquí.
- **`tool_spec.py`** + `profiles/default/apps/`: decorador `@tool_spec` para herramientas de apps en bigtool. Genera la descripción corta para el modelo y el documento rico que se indexa, y resuelve pre-requisitos (`requires`/`auto`). Guía en `docs/PLANTILLA_HERRAMIENTA.md`; ejemplo en `profiles/default/apps/crm_demo.py`.
- **Cuentas (`AUTH_ENABLED=1`)**:
  - `auth.py`: argon2id, sesiones con hash en la base, CSRF derivado del token y bloqueo por intentos;
  - `appdata/`: repositorios de la base de negocio (`repos.py` interfaces, `mongo.py`, `memory.py` para tests);
  - `ai_data.py`: borrado de hilos y memoria en la base de la IA;
  - en `server.py`, `_user`/`_changing`/`_owned`: el user_id sale de la sesión y un hilo ajeno da 404;
  - hay dos bases, que nunca pueden ser la misma (`memory.app_startup`); la de la IA no guarda correos ni contraseñas;
  - `scripts/assign_legacy_data.py` asigna datos anteriores (dry-run por defecto).
- **`config.py`**: `Settings` desde variables de entorno. `AGENT_PROFILE` no está en `Settings`: la lee `core/profile.py`. Todas las mejoras opcionales van detrás de un interruptor con default seguro (ver la tabla en README.md; la combinación validada está en "Configuración recomendada"). Los números se leen con `_num`: una variable vacía vale su default. `ROOT` solo sirve para encontrar `.env`.
- **`server.py`**: `app` perezoso (importar no conecta) y `create_app(..., profile=None)`. Sirve `profile.static_dir / "index.html"`.
- **`packs/ui/index.html`**: toda la UI, sin build.
  - Etiquetas de herramientas en `TOOL_LABELS`, `TOOL_DONE` y `NOT_RUN`; `OLD_TOOL_NAMES` traduce los nombres antiguos (en español) de hilos viejos. Las herramientas nuevas de un perfil salen con su nombre crudo.
  - Los chips se agrupan por herramienta (`AssistantBubble.group`/`paint`).
