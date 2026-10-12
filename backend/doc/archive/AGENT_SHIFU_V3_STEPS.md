# AgentShifuV3 — Plan de implementación y pasos

Este documento describe los pasos necesarios para completar la implementación del agente `agentShifuV3`.
Incluye el diseño de la lógica, endpoints, esquema de base de datos, worker, prompts y pruebas E2E.

## 1. Objetivo

- Crear un agente autocontenido que pueda: crear, editar, revisar y eliminar procesos (workflows).
- Ejecutar procesos en background mediante `worker`.
- Pausar/Resumir ejecuciones cuando falten integraciones o confirmaciones del usuario.
- Guiar al usuario por chat (respuesta en Markdown + acciones) cuando se requiera intervención.

## 2. Archivos añadidos (PoC)

- `app/routes/V2/core/procesos/static_process_agent.py`: endpoint placeholder `/agentShifuV3` (ya creado).
- `app/agents/agent_shifu_v3.py`: módulo PoC con `handle_request(payload, user)`.

## 3. Esquema de base de datos sugerido (MongoDB)

1. `process_definitions` (colección)
   - `_id`, `owner_id`, `title`, `description`, `steps` (array), `triggers` (object), `autonomy_level`, `created_at`, `updated_at`

2. `process_runs` (colección)
   - `_id`, `process_def_id`, `run_id`, `status` (pending,running,paused,failed,done), `current_step_index`, `results` (array), `created_at`, `updated_at`, `resume_token`

3. `langgraph_pending_states`
   - `_id`, `conversation_id`, `owner_id`, `state_partial`, `required_providers`, `resume_token`, `created_at`, `expires_at`

## 4. Endpoints necesarios (resumen)

- `POST /api/v2/agent/agentShifuV3` — entrada principal (PoC ya presente).
- `POST /api/v2/agent/agentShifuV3/resume` — reanudar ejecución con `resume_token`.
- `POST /api/v2/processes` — crear definición de proceso.
- `PUT /api/v2/processes/{id}` — editar definición.
- `GET /api/v2/processes/{id}` — ver definición.
- `POST /api/v2/processes/{id}/run` — crear `process_run` y disparar ejecución (worker).
- `POST /api/v2/process_runs/{run_id}/resume` — reanudar run pausado.

Nota: la identidad del usuario debe obtenerse del token JWT (`current_user`) en todos los endpoints; no confiar ni requerir un campo `email` en el body de las peticiones.

## 5. Worker

- Reutilizar `worker/worker.py` (actual). Cambios:
  - Leer `process_runs` con `status: pending` o `scheduled`.
  - Marcar `running` antes de ejecutar; lock/atomicidad para evitar concurrencia.
  - En cada step, comprobar `required_providers` usando `get_user_vault_with_fallback`.
  - Si falta proveedor, persistir `langgraph_pending_states` y marcar run `paused`.
  - Soportar `resume` que cargue `state_partial` y continúe ejecución.

## 6. Integración con herramientas (tools)

- Reusar `ToolRegistry` y `bigTools_registry` para instanciar herramientas por usuario.
- Usar `EmbeddingBasedRouter` para routing semántico cuando sea necesario.
- Extraer args con `extract_args` y manejar `ToolException` y `handle_tool_error=True`.

## 7. Flow de pausa y reanudación (detallado)

1. Durante ejecución, antes de llamar una tool, verificar credenciales (bóveda).
2. Si faltan, crear `langgraph_pending_states` con `resume_token` y `state_partial`.
3. Responder al frontend con `status: awaiting_integrations`, `final_answer_md`, `required_providers`, `resume_token`, `actions`.
4. Usuario conecta integraciones en UI y llama `/process_runs/{run_id}/resume` con `resume_token`.
5. Backend valida y reanuda worker.

## 8. Prompts y templates recomendados

- Planner prompt: reescribir tarea para maximizar coincidencia con tools.
- Extract args prompt: JSON-only parser con reglas estrictas (ver `utils.extract_args`).
- Pause prompt: mensaje claro en MD indicando qué conectar y pasos a seguir.

## 9. Seguridad

- No almacenar tokens en `state_partial` ni en `process_runs`.
- Validar `current_user` en resume y endpoints de reanudación.
- `resume_token` expirable (ej. 1 hora) y generado criptográficamente.

## 10. Tests sugeridos

- E2E: crear process_definition que requiere Gmail+HubSpot, ejecutar, simular falta de credenciales, comprobar `paused` y `resume`.
- Unit: `handle_request` PoC, persistencia `langgraph_pending_states`.

## 11. Tareas próximas (priorizadas)

1. Implementar persistencia `langgraph_pending_states` y endpoint `resume`.
2. Añadir CRUD `process_definitions` y endpoint para `run`.
3. Extender `worker` para ejecutar `process_runs` reales.
4. Agregar WebSocket/SSE para notificaciones en tiempo real.
5. Tests E2E.

---

Fin del plan PoC — usa este documento como checklist para la implementación completa.

## Checklist ejecutable (tareas con checkboxes y comportamiento esperado)

La siguiente lista permite marcar progreso y documenta el comportamiento esperado cuando cada ítem esté implementado. Usar esta checklist como guía operativa para desarrollo y pruebas.

- [ ] `Implementar persistencia langgraph_pending_states` :
   - Comportamiento esperado: almacenar `state_partial` sin credenciales, generar `resume_token` expirable, y devolver `status: awaiting_integrations` con `required_providers` y `actions` para el frontend.

- [ ] `Añadir endpoint POST /api/v2/agent/agentShifuV3/resume` :
   - Comportamiento esperado: aceptar `resume_token`, validar usuario y estado, reanudar ejecución desde `state_partial` y devolver `status: resumed` o error si expiró.

- [ ] `Diseñar esquema DB para process_definitions y process_runs` :
   - Comportamiento esperado: `process_definitions` guarda el blueprint; `process_runs` mantiene estado, `current_step_index`, `status` y `resume_token` sin credenciales sensibles.

- [ ] `Añadir endpoints CRUD para processes (create/edit/delete/list)` :
   - Comportamiento esperado: permitir creación y edición de procesos, validar esquema, permisos por `owner_id`, y publicar `process_def_id` para ejecuciones.

- [ ] `Implementar worker capaz de ejecutar process_runs y pausar` :
   - Comportamiento esperado: worker toma runs `pending`, marca `running`, ejecuta pasos; antes de llamar una tool verifica integraciones y, si faltan, crea `langgraph_pending_states` y marca run `paused`.

- [ ] `Integrar ToolRegistry / bigTools_registry por usuario` :
   - Comportamiento esperado: resolver herramientas disponibles por usuario, lanzar errors claros si una tool requerida falta o no tiene permisos.

- [ ] `Agregar endpoint UI flow para notificaciones y acciones (SSE/WebSocket)` :
   - Comportamiento esperado: enviar actualizaciones en tiempo real sobre el estado del run (paused/resumed/done) y permitir acciones desde el frontend.

- [ ] `Escribir tests E2E: crear → ejecutar → pausar → reanudar` :
   - Comportamiento esperado: reproducir el flujo completo en CI, validar que `resume_token` permite reanudar y que el estado final coincide con lo esperado.

- [ ] `Evaluar e implementar enfoque ReAct (opcional/híbrido)` :
   - Comportamiento esperado: planner/executor pueden usar señales estructuradas para decisiones, sin filtrar pensamientos internos en respuestas al usuario; mantener registro auditado de decisiones.

- [ ] `Integrar endpoint /agentShifuV3 con el módulo PoC` :
   - Comportamiento esperado: el endpoint delega a `app/agents/agent_shifu_v3.handle_request`, devuelve `final_answer_md` + `actions` para validar UI sin ejecutar herramientas.

- [ ] `Documentar ejemplos de payloads y respuestas (README/tests)` :
   - Comportamiento esperado: incluir ejemplos para Postman y para tests automatizados, con casos de pausa y reanudo.

---

Marcar cada item cuando el comportamiento descrito esté verificable mediante tests o validación manual en staging.
