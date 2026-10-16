# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Agente 0: asistente tipo ChatGPT con LangGraph 1.2 (`create_agent` + middleware), OpenAI `gpt-6-luna` vía Responses API, MongoDB (checkpointer + store), servidor FastAPI con SSE y una interfaz de un solo archivo (`static/index.html`). Windows, sin Docker. La documentación del proyecto está en español (README.md, CONTRATO.md).

## Comandos

```powershell
uv venv .venv
uv pip install --python .venv -e ".[dev]"
.venv\Scripts\python -m uvicorn assistant.server:app --host 127.0.0.1 --port 8000   # app en http://localhost:8000
.venv\Scripts\python -m pytest                                    # suite completa (0 tokens, modelos falsos)
.venv\Scripts\python -m pytest tests/test_chip_honesto.py -q      # un archivo
.venv\Scripts\python -m pytest tests/test_ui_navegador.py -k investigacion -q   # por nombre
```

- pytest **siempre** usa el Mongo local `mongodb://127.0.0.1:27017`, base `assistant_test` (lo fuerza `tests/conftest.py` aunque `.env` apunte a Atlas). Los tests con Mongo se saltan si no responde.
- `tests/test_ui_navegador.py` usa Playwright con Edge/Chrome ya instalados (headless) contra la app real con un modelo falso controlable (`Controlable`: la palabra del mensaje decide qué herramienta pide). Se salta si no hay navegador.
- `conftest.py` ofrece `FakeChat`, `FakeSearch` y `_settings(**overrides)` para construir agentes sin red.
- No hay linter configurado.

## Reglas del usuario (vigentes)

- MongoDB ya está instalado como servicio: solo conectarse. No instalarlo, arrancarlo ni crear scripts que lo levanten.
- No tocar `.env` ni los datos reales en Atlas (base `assistant`). No cambiar la conexión. `scripts/migrate_memories.py` nunca con `--apply` sobre datos reales.
- Sin commits hasta que se pidan; nunca push, ramas nuevas ni `--force`. Mensajes de commit en español. Antes de commitear: suite completa en verde y revisar `git diff --cached` (sin `.env`, claves, URIs con contraseña, `.playwright-mcp/`, `data/`, temporales ni datos de usuarios).
- Todo lo que lee el modelo (prompts, descripciones de herramientas, resultados de herramientas) va en **inglés**; los avisos al usuario y la UI, en **español**. Los comentarios del código están en español.
- Pruebas reales con la API: anunciar tope y estimación antes; usar una instancia aparte (p. ej. puerto 8001, base temporal `assistant_ux_tmp_*`, `TURN_TOKEN_CAP` bajo solo ahí) sin tocar el servidor del 8000; al terminar borrar la base temporal y detener la instancia.
- `langgraph` está fijado `>=1.2.15,<1.3`: el cierre de turno abortado en bigtool usa `CONFIG_KEY_RUNTIME` de `langgraph._internal`. Si se actualiza, vigila `tests/test_cierre_abortado.py`. `langgraph-bigtool` va fijado a un commit de git (PyPI 0.0.3 está roto con 1.x).

## Arquitectura

Flujo de un mensaje: `static/index.html` → `POST /chat` (o `/resume` tras una tarjeta de aprobación) en `server.py` → `elegir_esfuerzo` (regla o clasificador LLM) → `stream_events` en `agent.py` → eventos SSE (`token`, `tool_start`, `tool_end`, `interrupt`, `verify`, `summarized`, `context`, `effort`, `progress`, `no_tools`, `error`, `done`). **CONTRATO.md es el contrato de esos eventos y endpoints**: actualízalo si cambia su formato.

- **`agent.py`**: `build_agent` arma `create_agent` con una pila de middleware. Los más relevantes:
  - `LimiteLlamadas`, `LimiteRepeticiones` y `AterrizajeSuave`: el turno tiene un tope de tokens (`TURN_TOKEN_CAP`), contado por el callback `TurnTokens`. Al 80% se fuerza `tool_choice="none"`. El aborto real solo ocurre en una frontera de paso (`_step_kind`) y `_close_aborted_turn` deja el hilo consistente.
  - `HumanInTheLoopMiddleware`: confirmación de `deep_research` (predicado `research_needs_confirmation`) y del email simulado. Su rechazo genera un `ToolMessage` desde el nodo del middleware, no desde `tools`.
  - `AvisoCorte` y `_continue_cut`: respuestas cortadas por `max_tokens`.
  - `ResumenPorTurno`: compactación sobre `SummarizationMiddleware` (`MEMORY_SUMMARIZE`; disparo por % de `CONTEXT_WINDOW_TOKENS` o, si está definida, `SUMMARY_TRIGGER_TOKENS`). Una por turno, registro en `compaction_log`, capa estructurada (`COMPACT_STRUCTURED`). `compact_thread` es la compactación manual.
  - `AnswerVerifier`: `ANSWER_VERIFY`. Solo usa como evidencia las herramientas que de verdad corrieron (`is_evidence`).

  `_update_events` traduce los updates del grafo a eventos SSE. `get_history` reconstruye el historial para la UI. Las herramientas que no se ejecutaron (prefijos `NOT_RUN_PREFIXES`) se reportan con `status: "skipped"` y la UI nunca les pone "✓".
- **`context.py`**: medidor de contexto por hilo (`MedidorContexto`, estado `context_stats`/`compaction_log`, `context_in_use`: uso real de la última respuesta o estimación) y poda de resultados viejos de herramientas (`PodaHerramientas`, `COMPACT_PRUNE_TOOLS`). Endpoint `GET /threads/{id}/context`.
- **`tools.py`**:
  - Las herramientas del agente: `web_search` (OpenAI hospedado con respaldo DuckDuckGo, una búsqueda por respuesta del modelo, presupuesto compartido por mensaje), `calculator`, `current_datetime`, `check_python_syntax` (solo `ast.parse`), las de memoria y `deep_research`.
  - `deep_research` es un subagente investigador con sus propios topes que reutiliza investigaciones previas del hilo.
  - Los textos al modelo son constantes en inglés (`*_MSG`, `*_DOC`).
- **`memory.py`**: política de guardado (`MEMORY_SAVE_POLICY`, `MEMORY_POLICIES`, va al final del prompt del sistema; ningún recuerdo se inyecta en el prompt) y recuerdos largos en `MongoDBStore`, namespace `("user", user_id, "memories")`, con procedencia (`evidence`, `confidence`, `thread_id`) y verificación opcional (`MEMORY_VERIFY`).
- **`bigtool_agent.py`** (`USE_BIGTOOL=1`): agente alterno con langgraph-bigtool.
  - El modelo solo ve `retrieve_tools`, que busca en un índice semántico (`InMemoryStore` con embeddings) del registro: herramientas base + `extra_tools.py` + apps.
  - No soporta middleware, así que replica a mano lo esencial:
    - `PromptedModel`: prompt y aterrizaje suave;
    - `interrupt()` dentro de `deep_research`;
    - `_seguro`, que re-lanza `GraphBubbleUp`.

  Cualquier cambio de comportamiento del agente normal suele necesitar su equivalente aquí.
- **`tool_spec.py`** + `apps/`: decorador `@tool_spec` para herramientas de apps en bigtool. Genera la descripción corta para el modelo y el documento rico que se indexa, y resuelve pre-requisitos (`requires`/`auto`). Guía en `docs/PLANTILLA_HERRAMIENTA.md`; ejemplo en `apps/crm_demo.py`.
- **`config.py`**: `Settings` desde variables de entorno. Todas las mejoras opcionales van detrás de un interruptor con default seguro (ver la tabla en README.md).
- **`prompts/system.md`**: prompt del sistema en inglés. Se lee en cada mensaje, así que los cambios no requieren reiniciar.
- **`static/index.html`**: toda la UI, sin build.
  - Etiquetas de herramientas en `TOOL_LABELS`, `TOOL_DONE` y `NOT_RUN`; `OLD_TOOL_NAMES` traduce los nombres antiguos (en español) de hilos viejos.
  - Los chips se agrupan por herramienta (`AssistantBubble.group`/`paint`).
