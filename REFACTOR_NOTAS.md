# REFACTOR_NOTAS: pendientes fuera del alcance del refactor

Este refactor solo reorganiza. Todo lo de aquí abajo es un **cambio de comportamiento** y va en commits o tareas aparte, después de terminar el refactor y con la suite en verde.

## Seguridad (de la auditoría del 2026-10-17, `docs/AUDITORIA_AGENTE.md`): siguiente fase, sin implementar

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

