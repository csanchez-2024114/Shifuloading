# Índice — Conectar el 100% del dashboard a backend real

Plan completo: `C:\Users\alane\.claude\plans\si-la-idea-es-cheeky-stallman.md`

## Estado de los 12 grupos

| Grupo | Nombre | Depende de | Estado |
|---|---|---|---|
| A | Workflows REST router | — | hecho |
| B | Tasks + Flow Designer execution | A | hecho |
| C | Secrets vault (dual: conector/personal) | — | hecho |
| D | Workspace members + Departamentos | — | hecho |
| E | Settings de-mock + GET /me + avatar + path-corrections | — | hecho |
| F | Chat producción: token tracking real | — | hecho |
| G | Home/Insights: 9 endpoints de analytics | — | hecho |
| H | Consolidación de chat (4 sitios Gemini → real) | H.4 (WorkflowBoard) depende de B | hecho |
| I | Notificaciones REST persistidas | F (conviene) | hecho |
| J | Telegram Login Widget | — | hecho |
| K | Conector custom vía Shifu | — | hecho |
| L | Canje de código de referido | — | hecho |

## Orden de ejecución

Primera ola (sin dependencias, en paralelo): A, C, D, E, F, G, H.1-3, J, K, L
Segunda ola: B (cuando A termine)
Tercera ola: H.4 — WorkflowBoard inline chat (cuando B termine), I (cuando F termine)

## ✅ TODOS LOS 12 GRUPOS COMPLETADOS

Carpeta pendiente de eliminar cuando se confirme que todo funciona en producción.
