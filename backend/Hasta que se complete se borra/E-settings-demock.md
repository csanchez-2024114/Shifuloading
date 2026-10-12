# Grupo E — Settings de-mock + GET /me + avatar + path-corrections

- [x] Borrar `IS_MOCK_ENV`/`mockDb`/`mockHttp` de `settingsApi.ts`, usar `http.ts` real
- [x] Agregar `@router.get("")` a `app/routes/me/me.py` (no existe, solo PATCH — devuelve 405/400 hoy)
- [x] `getProfile` → `GET /api/v1/me`; fix `useCurrentUser.ts`/`TopBar.tsx` (llamaban `/api/v1/users/me`, 400)
- [x] `getProducts` → `GET /api/v1/billing/products` (ajustar shape `res.products`)
- [x] Wireear avatar real: `POST /api/v1/me/avatar` ya existe, `ProfileTab.tsx` usa Unsplash mock
- [x] Path-corrections: `AddConnectorModal`/`MultiAccountModal` → catalog/apps + integrations/ + accounts (no `/connectors/...`)
      NOTA: investigado en vivo — el código real (catalogSlice.ts, integrationSlice.ts, useConnectorConnections.ts/analysisApi.ts)
      YA pega contra `/api/v1/catalog/apps`, `/api/v1/integrations/`, `/api/v1/accounts/{provider}/{id}` y
      `/api/v1/integrations/{provider}/login` — los modales son presentacionales puros (reciben `apps`/`accounts`/callbacks
      por props) y sus JSDoc con los paths viejos nunca se ejecutan. Se actualizó el JSDoc para que no desinforme.
- [x] `UploadResourceModal` → `POST /api/v1/uploads/` (no `/resources/upload`)
      NOTA: mismo caso — `resources/index.tsx::handleCreateResource` ya llama `useResources().uploadFile` →
      `POST /api/v1/uploads/` real. El JSDoc del modal (paths de props, no invocado) quedó corregido.
- [x] `NewsModal` → `GET /api/v1/me/announcements/pending` (fix 422, confirmar params requeridos)
      Requiere `email: str` como query param (`app/routes/social/announcements.py:183`), no auth de token — se lee
      del email persistido en localStorage. `useNotifications.ts` ya llamaba a esa URL pero sin el query param
      (causaba 422) — corregido. `NewsModal.tsx` seguía 100% en mock (`mockNews` + `setTimeout`) — reescrito para
      pegarle al endpoint real y llamar `POST /api/v1/me/announcements/{id}/view` al marcar como vista/todas.
- [x] Verificación: `tsc -b --noEmit`, probar login → ver perfil → cambiar avatar
