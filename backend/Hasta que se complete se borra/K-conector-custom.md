# Grupo K — Conector custom vía Shifu (ShifuConnectorModal)

- [x] Colección nueva `custom_connector_requests` (`app/core/constants.py::Collections.CUSTOM_CONNECTOR_REQUESTS`)
- [x] `POST /api/v1/connectors/custom-request`: persistir `{user_id, name, description, status:"analyzing", created_at}` — `app/routes/connectors/customRequestRoutes.py`, montado en `main.py`
- [x] v1: sin automatizar construcción real vía IA (feature aparte), sin evento WS `custom_connector_status`
- [x] Opcional: notificación interna/email al equipo — reusa `app/utils/mail.py::_send_email_message` (mismo patrón que `contact.py`), best-effort en background task, no rompe la request si SMTP falla/no está configurado
- [x] Frontend: modal muestra estado fijo "en análisis" tras enviar, sin polling — `ShifuConnectorModal.tsx` ahora llama al endpoint real vía `http.ts`, quitado el `setTimeout` simulado y el JSDoc del WS opcional
- [x] Verificación: `python -c "import main"` limpio; `npx tsc -b --noEmit` limpio (sin errores nuevos); request de punta a punta contra Mongo real vía TestClient — 202 `{request_id, status:"analyzing"}`, doc persistido con el shape exacto, email de notificación interna enviado OK a `contact@hypershifu.com` (doc de prueba borrado después)
