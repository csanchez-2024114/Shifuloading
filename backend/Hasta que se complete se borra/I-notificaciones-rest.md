# Grupo I — Notificaciones REST persistidas (conviene después de F)

- [x] Colección nueva `user_notifications` — `app/core/constants.py:45` (`Collections.USER_NOTIFICATIONS`)
- [x] Router nuevo `app/routes/me/notifications.py`, `prefix="/api/v1/me/notifications"` — registrado en `main.py:691`
- [x] `GET /?page=&limit=&unread_only=`, `PATCH /{id}/read`, `PATCH /mark-all-read` — los 3 endpoints implementados
- [x] Insertar notificaciones desde eventos reales ya existentes:
  - `usage_warning`: `app/core/quota.py:108-115` → `create_notification()`
  - `run_completed` / `run_failed`: `app/workers/workflow_executor.py:1043-1057` → `create_notification()`
- [x] Frontend `useNotifications.ts`: sincronizar contra REST además del WS en vivo — `fetchPersisted()` en mount + post-WS-event, PATCH para markAsRead/markAllAsRead
- [x] Ajustar `NotificationsModal` al path real (`/me/notifications`, no `/notifications`) — todos los http calls usan `/api/v1/me/notifications/...`
- [x] Verificación: `markAsRead()` → `PATCH /api/v1/me/notifications/{id}/read`, sobrevive page refresh gracias a `fetchPersisted()` en mount
