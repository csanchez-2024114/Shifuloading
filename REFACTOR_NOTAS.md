# REFACTOR_NOTAS: pendientes fuera del alcance del refactor

Este refactor solo reorganiza. Todo lo de aquí abajo es un **cambio de comportamiento** y va en commits o tareas aparte, después de terminar el refactor y con la suite en verde.

## Seguridad (de la auditoría del 2026-10-17, `AUDITORIA_AGENTE.md`): siguiente fase, sin implementar

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

  La sección de eventos SSE sí coincide con el código. El refactor no cambiará su formato. ¿Se corrige la parte desactualizada en un commit de docs aparte? (a confirmar)
- **Concurrencia en un mismo hilo:** `_ACTIVE_TURNS[thread_id]` se pisa con dos `/chat` simultáneos (`agent.py:872`, `agent.py:1015`, `agent.py:1081`).
- **Estado de proceso** (`_ACTIVE_TURNS`, `_PAUSED_SPEND`, `tools._TURNS`): no escala a varios workers.
- **Bigtool:**
  - `effect="write"` (`crm_create_order`) no pide aprobación: `effect` solo se valida (`tool_spec.py:161`). La interfaz de perfil ya trae `ToolPolicy.effect/approval`; **aplicarlo** a herramientas que hoy no piden aprobación sería un cambio de comportamiento.
  - Sin compactación, `ANSWER_VERIFY` ni tope por esfuerzo.
- **Dependencias sin fijar y sin lockfile** (`pyproject.toml:5-21`).
- **La UI depende de los mensajes en inglés del núcleo** (`toolOutputLabel`). Un perfil que cambie esos mensajes rompe las etiquetas. Tarea aparte: etiquetas de la UI por perfil (`labels.json`) y una cáscara de UI genérica.
- **Defaults de configuración por perfil** (Q6 del plan): mejora posterior.
