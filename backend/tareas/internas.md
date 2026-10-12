# Herramientas internas del agente (no son apps de terceros)

Son **40 herramientas** de `app/agent/shared/tools/providers/` que operan sobre el propio Shifu (IA, workflows, programaciones, procesos, memoria y contexto). No llaman a una API externa con credenciales del usuario, así que **no encajan en el estándar de función de app** (que gira en torno a `get_connection`).

**Decisión pendiente del líder:** qué se hace con ellas (migrarlas a otro mecanismo del sistema nuevo, dejarlas como están o redefinirlas). Hasta entonces **no hay tareas de programación** aquí; es solo el inventario. Leído del código el 2026-10-07; no se ejecutó nada.

| Grupo | Archivo | Cantidad | Herramientas |
|---|---|---:|---|
| IA | `ai_bigtools.py` | 7 | `ai_summarize`, `ai_transform`, `ai_extract`, `ai_classify`, `ai_generate`, `ai_filter`, `ai_decide` |
| Workflows | `workflow_bigtools.py` | 22 | `scheduled_workflow`, `crear_workflow`, `agregar_paso_workflow`, `ver_borrador_workflow`, `confirmar_workflow`, `eliminar_paso_workflow`, `reemplazar_paso_workflow`, `editar_workflow`, `listar_mis_workflows`, `ver_workflow`, `pausar_workflow`, `reactivar_workflow`, `eliminar_workflow`, `fijar_frecuencia_workflow`, `programar_workflow`, `listar_programaciones_workflow`, `pausar_programacion`, `reanudar_programacion`, `eliminar_programacion`, `configurar_metadata_workflow`, `configurar_metricas_workflow`, `configurar_webhook_workflow` |
| Programaciones | `scheduler_bigtools.py` | 4 | `listar_programaciones`, `pausar_programacion`, `reanudar_programacion`, `eliminar_programacion_bt` |
| Procesos | `procesos_bigtools.py` | 4 | `listar_procesos`, `ver_proceso`, `recuperar_y_modificar_proceso`, `eliminar_proceso_por_id` |
| Programar proceso | `scheduleProcessTool_bigtools.py` | 1 | `schedule_process` |
| Memoria | `memory_search_bigtools.py` | 1 | `buscar_en_historial` |
| Contexto | `conversation_context_bigtools.py` | 1 | `recuperar_contexto_conversacion` |

## Observaciones

- `pausar_programacion` y `reanudar_programacion` están definidas **en dos archivos** (workflow y scheduler): hay 38 nombres distintos para 40 herramientas.
- `scheduler_bigtools.py` define cada nombre dos veces (dos ramas del mismo archivo).
- `gmail_reactivo` y `gmail_desactivar` (en `gmail_bigtools.py`) también son de este grupo: activan y desactivan un disparador de workflow, no llaman a Gmail. Están contadas en `gmail.md`.
- Eliminar un workflow, un proceso o una programación es un borrado de datos del usuario: el diseño del sistema nuevo no borra, marca por estado (ver `doc/PLAN_MAESTRO_sistema_nuevo.md`).
