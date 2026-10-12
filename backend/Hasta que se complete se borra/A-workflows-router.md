# Grupo A — Workflows REST router (backend)

- [x] Crear `app/routes/workflows/workflows.py`, montar en `main.py` (`prefix="/api/v1/workflows"`)
- [x] `GET /api/v1/workflows` → `list_user_workflows()`
- [x] `POST /api/v1/workflows` → nueva función de servicio (sin semántica conversation_id/dedup), enforce `max_workflows`, aceptar+guardar `workspace_id` opcional sin filtrar por él
- [x] `GET /api/v1/workflows/{id}` → `get_workflow_by_id()`, 404 si None
- [x] `PATCH /api/v1/workflows/{id}` → nueva `update_workflow_fields()`, validar `max_apps_per_workflow` si body incluye `steps`
- [x] `DELETE /api/v1/workflows/{id}` → `delete_workflow()`
- [x] `GET /api/v1/workflows/{id}/runs` → agregar filtro `workflow_id` a `list_user_runs()`
- [x] `POST /api/v1/workflows/{id}/runs` → patrón de `webhook_inbound.py` SIN el `asyncio.create_task` duplicado. Sin exigir `status=="active"`
- [x] Actualizar `docs/BACKEND_ENDPOINTS_V1.md`
- [x] Verificación: `python -c "import main"` limpio

## Grupo A — COMPLETO

Archivos tocados:
- `app/routes/workflows/workflows.py` (nuevo)
- `app/routes/workflows/__init__.py` (nuevo)
- `app/services/workflow_service.py` (+`create_blank_workflow()`, +`update_workflow_fields()`)
- `app/services/workflow_run_service.py` (`list_user_runs()` ahora acepta `workflow_id: Optional[str]`)
- `main.py` (import + `app.include_router(workflows_router, prefix="/api/v1/workflows", ...)` cerca de la línea 681-682)
- `docs/BACKEND_ENDPOINTS_V1.md` (3 filas marcadas resueltas)

`python -c "import main"` corre limpio, router registrado sin errores.
