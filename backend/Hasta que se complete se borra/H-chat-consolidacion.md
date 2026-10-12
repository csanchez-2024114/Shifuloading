# Grupo H — Consolidación de chat: 4 sitios Gemini → backend real

- [x] H.1 FloatingChat: reemplazar `fetchGeminiResponse` por SSE a `/chat/stream`, leer `access_token` (no `token`)
- [x] H.2 Resources "Generate AI summary": construir prompt con metadata del archivo, consumir SSE hasta `done`
- [x] H.3 Memory graph AI (3 sub-features): instruir JSON-en-prosa + parseo defensivo, comentario `ponytail:` marcando el techo conocido
- [x] H.4 WorkflowBoard inline chat — reemplazar Gemini mock + `[UPDATE_STEPS]` por `streamChat()` SSE con `workflow_id` en el texto, refresh vía `GET /api/v1/workflows/{id}` en `done`
- [ ] Verificación: mandar un mensaje real en cada uno de los 4 chats y confirmar respuesta del agente real (no canned response) — requiere backend corriendo
