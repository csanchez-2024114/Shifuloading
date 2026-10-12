# Grupo B — Tasks + ejecución en Flow Designer (frontend) — ESPERA a Grupo A

- [x] WorkflowBoard: reemplazar `INITIAL_WORKFLOWS`/`INITIAL_STEPS_BY_WORKFLOW` por CRUD real `/api/v1/workflows`
- [x] Flow Designer save (`handleSave`) → `PATCH /api/v1/workflows/{id}`
- [x] Flow Designer tabs/canvas persistence (`useFlowTabs.ts`) → persistir vía el mismo PATCH
- [x] Flow Designer "Ejecutar" → `POST /api/v1/workflows/{id}/runs` + conectar `WS /api/v1/ws/runs` (reusar hook de `WorkflowsDebug.tsx`)
- [x] Tasks view → listar desde endpoints de workflows/runs reales
- [x] `WorkflowEditModal`: cambiar de `PUT` a `PATCH`
- [x] Verificación: `tsc -b --noEmit` — los únicos errores son pre-existentes en SecretaryChats, connectors y LoadingModal (no relacionados con estos cambios)
