# Estado del núcleo (2026-10-18)

Qué capacidades existen, con qué interruptor, y qué evidencia tiene cada una. Hay dos niveles:
- **Real:** probado con el modelo real (`gpt-6-luna`), siempre en `:8001` con bases temporales borradas al terminar.
- **Falsos:** cubierto solo por la suite con modelos falsos (0 tokens).

La suite tiene 548 tests y corre siempre. Detalle de las pruebas reales en [VALIDACION_E2E.md](VALIDACION_E2E.md); qué activar en tu `.env`, en [ACTIVACION.md](ACTIVACION.md).

Ramas: `main` (`cf0b624`) tiene el refactor y la primera parte de la seguridad (S1–S5 y la validación E2E). `feat/seguridad-core` va por delante con todo lo de la Fase 1 en adelante (evals, archivos, trazas/métricas/feedback, Fase 4), sin fusionar.

## Capacidades de la lista base

| Capacidad | Existe | Interruptor (default) | Probado con el modelo real | Solo con modelos falsos |
|---|---|---|---|---|
| **Memoria** larga por usuario, con procedencia y política de guardado | sí | siempre; `MEMORY_SEMANTIC`, `MEMORY_VERIFY`, `MEMORY_DEDUP` (0) | guardar y recuperar (línea base y evals); semántica, verificación y dedup validadas el 2026-10-16 | — |
| Memoria: solo con cita literal del usuario | sí | `MEMORY_REQUIRE_QUOTE` (0); forzada en hilos con adjuntos | 4 de 4 datos guardados con cita; lo de la web no se guardó (segunda tanda; evals) | **el rechazo en código**: en real lo frenó antes la política del prompt |
| **Búsqueda web** (OpenAI hospedada, respaldo DuckDuckGo) y `deep_research` | sí | siempre | línea base, segunda tanda y evals (`web-*`, `inv-*`) | — |
| **Aprobaciones** (tarjeta de `deep_research` y email de demo) | sí | `ENABLE_HITL_DEMO` (0) para el email | investigación aprobada y rechazada (línea base, evals) | email de demo |
| Aprobación por efecto (`write`/`send`/`delete`) | sí | `EFFECT_APPROVAL` (0) | — | **todo**: con el perfil default no cambia nada (solo actuaría en bigtool con el CRM de demo) |
| **Verificación de enlaces**: filtro de URLs sin respaldo | sí | `URL_FILTER_ALWAYS` (0) | escenario 2 y `url-*` de las evals, incluido el enlace entre comillas invertidas tras la corrección | el filtro de la URL pegada a `(` |
| Verificación con LLM (`ANSWER_VERIFY`) | sí | `ANSWER_VERIFY` (0) | no en estas tandas | sus reglas de citas en código |
| Contenido externo como no confiable | sí | `UNTRUSTED_WRAP` (0); siempre para archivos | escenarios 2, 3 y 5 (segunda tanda); archivos trampa (evals y UI) | el bloqueo de una inyección web real (la trampa web solo existe en modo falso) |
| **Costos**: tope por mensaje, aterrizaje suave, presupuesto de búsquedas | sí | `TURN_TOKEN_CAP` (150000) y los de esfuerzo | tope de 15k con búsqueda que no cabe (línea base, evals); corte de investigación con tope 60k (primera corrida de evals) | — |
| Tope de tiempo por mensaje | sí | `TURN_MAX_SECONDS` (0) | con 6 s no llegó a cortar | **el corte**, el aviso y el hilo usable después |
| **Trazas**: `run_id` y metadatos por turno, evento `run` | sí | `TRACE_METADATA` (0) | `run_id` del evento = fila de métricas = feedback (prueba corta de la Fase 3) | **LangSmith**: metadatos de la traza y su recepción |
| **Métricas** por turno, sin contenido de mensajes | sí | `TURN_METRICS` (0); necesita base de negocio | fila revisada campo por campo, sin el texto del mensaje ni de la respuesta | estados `cap`, `time_cap`, `recursion`, `error`, `disconnected` |
| **Feedback** 👍/👎 | sí | `FEEDBACK_ENABLED` (0); exige los dos anteriores | un 👍 y un 👎 por la UI: una sola fila con `score` -1 | **`create_feedback` en LangSmith** |
| **Archivos**: subida validada, extracción aislada, lectura por fragmentos | sí | `FILES_ENABLED` (0) | evals 6/6 (CSV, PDF, imagen, CSV y PDF trampa, tipo falso) y 3 mensajes por la UI | con bigtool; el timeout del extractor; macros y zip bombs |
| **Evals** repetibles | sí | — | corrida completa (411 697 tokens) y repetición de fallas (125 665) | modo falso entero en la suite |
| **Perfiles** (núcleo + packs + perfiles) | sí | `AGENT_PROFILE` (`default`) | perfil `default` | `generic`, perfiles externos y dos perfiles en el mismo proceso |
| Cuentas, sesiones, dos bases | sí | `AUTH_ENABLED` (0) | no en estas tandas | todo |
| Seguridad de red (hosts, loopback, largo del mensaje) | sí | `TRUSTED_HOSTS`, `MAX_MESSAGE_CHARS` (50000) | 413 por largo (línea base, evals) | hosts y loopback |
| Candado por hilo (409) | sí | siempre; **un worker de uvicorn** | — | concurrencia con modelo lento |
| Errores de herramientas sin detalle | sí | `TOOL_ERROR_DETAIL_HIDDEN` (0) | — | todo |
| bigtool (muchas herramientas) | sí | `USE_BIGTOOL` (0), `BIGTOOL_DEMO_TOOLS` (0) | no en estas tandas | todo, incluido con archivos |
| Compactación del contexto | sí | `MEMORY_SUMMARIZE` y `COMPACT_*` (0) | validada el 2026-10-16 (con `COMPACT_STRUCTURED` y `COMPACT_FIRST_MESSAGE`) | `COMPACT_PRUNE_TOOLS` (no ahorró en real) |

## Solo con modelos falsos (los que pediste vigilar)

- **LangSmith:** los metadatos de la traza (`run_id`, `run_name`, `metadata`, `tags`) y `create_feedback`. En todas las pruebas reales `LANGSMITH_TRACING=false`.
- **`TURN_MAX_SECONDS`:** con 6 s el plazo venció durante la respuesta final, que se deja terminar, y no hubo corte. El corte limpio solo lo cubre `test_seguridad::turn_max_seconds_*`.
- **`EFFECT_APPROVAL`:** no se corrió en real; con el perfil por defecto no cambia nada.
- **Rechazo en código de `MEMORY_REQUIRE_QUOTE`:** en real el modelo nunca llegó a llamar a `save_memory` con evidencia falsa, porque lo frenó la política del prompt. El rechazo lo cubren `test_seguridad` y los tests de inyección desde archivos.
- **Además:** la combinación `FILES_ENABLED` + `USE_BIGTOOL`, el candado por hilo, `TOOL_ERROR_DETAIL_HIDDEN`, el perfil del turno con dos perfiles y el filtro de la URL pegada a `(`.

## Interruptores y su default

Todos los booleanos están en `0` por defecto. Sin ellos, la huella es idéntica a la del perfil por defecto.

| Interruptor | Default | Qué hace |
|---|---|---|
| `UNTRUSTED_WRAP` | 0 | resultados web entre `<untrusted_web_content>` + regla en el prompt |
| `MEMORY_REQUIRE_QUOTE` | 0 | la memoria solo guarda con cita literal del usuario |
| `URL_FILTER_ALWAYS` | 0 | quita enlaces sin respaldo de la respuesta final |
| `TURN_MAX_SECONDS` | 0 | tope de tiempo por mensaje |
| `EFFECT_APPROVAL` | 0 | tarjeta para herramientas con efecto |
| `FILES_ENABLED` | 0 | archivos (con `FILE_MAX_BYTES` 10000000, `FILE_MAX_PER_MESSAGE` 5, `FILE_MAX_PAGES` 50, `FILE_MAX_CHARS` 200000, `FILE_EXTRACT_TIMEOUT` 20, `FILE_IMAGE_MAX_PX` 1568) |
| `TRACE_METADATA` | 0 | `run_id` y metadatos por turno, evento `run` |
| `TURN_METRICS` | 0 | métricas por turno (con `METRICS_TTL_DAYS` 90) |
| `FEEDBACK_ENABLED` | 0 | 👍/👎 y `POST /feedback` |
| `TOOL_ERROR_DETAIL_HIDDEN` | 0 | errores de herramientas sin detalle para el modelo |
| `ANSWER_VERIFY` | 0 | verificación de la respuesta con LLM |
| `MEMORY_SEMANTIC`, `MEMORY_VERIFY`, `MEMORY_DEDUP`, `MEMORY_SEARCH_ECONOMY` | 0 | capas de memoria |
| `MEMORY_SUMMARIZE`, `COMPACT_STRUCTURED`, `COMPACT_FIRST_MESSAGE`, `COMPACT_PRUNE_TOOLS` | 0 | compactación del contexto |
| `USE_BIGTOOL`, `BIGTOOL_DEMO_TOOLS` | 0 | agente con langgraph-bigtool y sus demos |
| `ENABLE_HITL_DEMO` | 0 | email simulado con aprobación |
| `AUTH_ENABLED` | 0 | cuentas y base de negocio |

Valores no booleanos que importan: `TURN_TOKEN_CAP` 150000, `MAX_MESSAGE_CHARS` 50000, `MODEL_CALL_LIMIT` 0 (esfuerzo automático), `TRUSTED_HOSTS` `localhost,127.0.0.1`, `AGENT_PROFILE` vacía (= `default`). La tabla completa está en el README.

## Pendiente

- **Etiquetas de herramientas por perfil** (`labels.json` + `GET /profile/labels`): diseño en `REFACTOR_NOTAS.md`.
- **Candado por hilo en Mongo**, para usar más de un worker.
- **Validar con el modelo real** lo que solo tiene modelos falsos: LangSmith, el corte de `TURN_MAX_SECONDS` (unos 3 s; valor real propuesto 180 s), `EFFECT_APPROVAL` con bigtool y el CRM de demo, y archivos con bigtool.
- **Seguridad de la auditoría:** S1, S3, S4, S6 y S7 están resueltas; S2 está mitigada con `UNTRUSTED_WRAP` y `MEMORY_REQUIRE_QUOTE` (y siempre en archivos). Queda abierta la parte de S5: presupuesto por usuario y rate limit (el largo máximo del mensaje ya existe).
- **Base de negocio en tu `.env`:** para activar `TURN_METRICS` o `FEEDBACK_ENABLED` hace falta definirla.
