# Grupo D — Workspace members + Departamentos

- [x] Colecciones nuevas `workspace_members`, `workspace_departments`; extender `workspaces` con `invite_code`
- [x] Router nuevo `app/routes/workspaces/workspaceRoutes.py`, `prefix="/api/v1/workspaces"`
- [x] `GET /` (lista workspaces del usuario), `POST /join` (por código), `POST /{id}/invite-code/regenerate`
- [x] `GET/{id}/members`, `POST /{id}/members/invite`, `PATCH .../role`, `PATCH .../status`, `DELETE .../members/{id}`
- [x] `GET/POST /{id}/departments` (crear solo el dueño)
- [x] `require_workspace_role()` nueva, blindar contra remover al único owner
- [x] `authRoutes.py`: completar invitaciones pendientes al registrar/loguear (match por email)
- [x] Frontend: `workspaceSlice.ts` de mock/localStorage a los endpoints reales (mismo shape)
- [x] `useWorkspaceMembers.ts`: descomentar bloque de integración futura
- [x] Verificación: unirse a un workspace por código, crear un departamento
