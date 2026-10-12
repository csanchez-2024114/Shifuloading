# Tareas: funciones y pruebas de autenticación por app

Lista de lo que hay que construir en el sistema de funciones nuevo, **una app por archivo**. Cada archivo trae dos fases:
- **Fase A, autenticación (primero):** tareas muy explícitas para probar la conexión de esa app con una cuenta real y comprobar que cada falla se comporta como dice el contrato. Protocolo común y script en [`PROBAR_AUTH.md`](PROBAR_AUTH.md).
- **Fase B, funciones:** todas las operaciones útiles de la API oficial de la app, una fila por función, con su **resultado** esperado y su casilla `[ ]`.

Antes de empezar, lee [`doc/funciones/GUIA_JUNIOR.md`](../doc/funciones/GUIA_JUNIOR.md) y [`doc/funciones/CONTRATO.md`](../doc/funciones/CONTRATO.md); la plantilla es [`app/functions/apps/_template/`](../app/functions/apps/_template/README.md).

## Cuántas funciones hay por app

Salen del **catálogo completo de la API oficial de cada app** (investigado el 2026-10-07 por IA, un agente por app, y revisado con un validador de formato). Cada fila marca como "herramienta vieja" la que ya existía en el código del repo, para no perder la trazabilidad.

| App | Archivo | Funciones | De lectura | Herramientas viejas | Hechas | Autenticación |
|---|---|---:|---:|---:|---:|---|
| Brevo | [brevo.md](brevo.md) | 289 | 119 | — | 3 | API key |
| Slack | [slack.md](slack.md) | 282 | 101 | — | — | token largo / sin refresh |
| Trello | [trello.md](trello.md) | 250 | 124 | — | — | token largo / sin refresh |
| Asana | [asana.md](asana.md) | 244 | 116 | 21 | — | OAuth2 con refresh |
| HubSpot | [hubspot.md](hubspot.md) | 217 | 108 | 52 | — | OAuth2 con refresh |
| Jira Cloud | [jira.md](jira.md) | 206 | 91 | 5 | — | OAuth2 con refresh |
| ClickUp | [clickup.md](clickup.md) | 179 | 71 | 14 | — | token largo / sin refresh |
| monday.com | [monday.md](monday.md) | 133 | 25 | — | — | token largo / sin refresh |
| Microsoft Teams | [teams.md](teams.md) | 133 | 54 | — | — | OAuth2 con refresh |
| Dropbox | [dropbox.md](dropbox.md) | 127 | 64 | 11 | 3 | OAuth2 con refresh |
| Telegram | [telegram.md](telegram.md) | 126 | 23 | — | — | token largo / sin refresh |
| Salesforce | [salesforce.md](salesforce.md) | 110 | 63 | — | — | OAuth2 con refresh |
| Outlook | [outlook.md](outlook.md) | 99 | 39 | — | — | OAuth2 con refresh |
| LinkedIn | [linkedin.md](linkedin.md) | 80 | 45 | — | — | token largo / sin refresh |
| Google Drive | [google_drive.md](google_drive.md) | 79 | 30 | 9 | — | OAuth2 con refresh |
| Google Sheets | [google_sheets.md](google_sheets.md) | 79 | 17 | 17 | — | OAuth2 con refresh |
| X (Twitter) | [twitter.md](twitter.md) | 79 | 46 | — | — | OAuth2 con refresh |
| Gmail | [gmail.md](gmail.md) | 76 | 30 | 13 | — | OAuth2 con refresh |
| Discord | [discord.md](discord.md) | 75 | 33 | — | — | OAuth2 con refresh |
| Facebook | [facebook.md](facebook.md) | 70 | 43 | 1 | — | token largo / sin refresh |
| Google Slides | [google_slides.md](google_slides.md) | 66 | 9 | 15 | — | OAuth2 con refresh |
| Google Docs | [google_docs.md](google_docs.md) | 62 | 10 | 15 | — | OAuth2 con refresh |
| Notion | [notion.md](notion.md) | 61 | 30 | — | — | token largo / sin refresh |
| Instagram | [instagram.md](instagram.md) | 57 | 30 | 23 | — | token largo / sin refresh |
| OneDrive | [onedrive.md](onedrive.md) | 54 | 31 | — | — | OAuth2 con refresh |
| Google Calendar | [google_calendar.md](google_calendar.md) | 39 | 13 | — | — | OAuth2 con refresh |
| Kick | [kick.md](kick.md) | 32 | 17 | — | — | OAuth2 con refresh |
| Threads | [threads.md](threads.md) | 23 | 17 | — | — | token largo / sin refresh |
| TikTok | [tiktok.md](tiktok.md) | 20 | 12 | — | — | OAuth2 con refresh |
| **Total (29 apps)** | | **3347** | **1411** | **196** | **6** | |

**Herramientas viejas:** 168 son las que están registradas hoy en `app/agent/shared/tools/providers/` (gmail, drive, docs, sheets, slides, asana, clickup, hubspot, dropbox, facebook). Las 23 de Instagram y las 5 de Jira salen de conectores escritos en `app/tools/connectors/` que **nunca se registraron** como herramientas; Discord no tiene ninguna.

**Lectura honesta de estos números:** son el techo de lo que cada API ofrece, no un plan realista. Hay grupos enteros que probablemente no se necesiten (p. ej. `admin` de Slack, lealtad de Brevo, Enterprise de HubSpot). Propuesta de prioridad, **por decidir con el líder**:
1. **Prioridad 1:** las herramientas viejas (columna "Herramienta vieja" de cada archivo), porque ya están en uso.
2. **Prioridad 2:** las funciones de **lectura** (`read`) de las apps que el producto quiera ofrecer; no cambian datos y son las más seguras de probar.
3. **Prioridad 3:** crear, actualizar y borrar, por demanda real de los clientes (medir qué piden antes de construirlas).

## Qué hacer con cada app (resumen)

1. Abre su archivo y completa la **Fase A** con una cuenta de prueba; no escribas funciones hasta que pase.
2. Programa las funciones de la **Fase B** en el orden de prioridad que se decida, con el estándar de [`GUIA_JUNIOR.md`](../doc/funciones/GUIA_JUNIOR.md).
3. Marca las casillas al avanzar y exporta la colección de Postman de la app.

## Qué cambia respecto a las herramientas viejas

- Una función por operación, con entrada y salida como modelos Pydantic y un resultado uniforme (`{ok, data}` o `{ok:false, error}`).
- **Descripción en inglés y completa** (mínimo 200 caracteres; los campos de entrada, 10): el agente busca y elige funciones con ese texto.
- Las funciones nuevas **no reutilizan los conectores viejos**: varios están rotos (ver "Deuda conocida" en [`CLAUDE.md`](../CLAUDE.md)) y leen el almacén de credenciales antiguo. Toda la conexión pasa por `get_connection` (`user_connected_accounts`).
- Lo que antes recibía un **nombre** o **lenguaje natural** (`..._por_nombre`) ahora recibe parámetros estructurados; interpretar el texto del usuario es trabajo del modelo.

## Qué NO está verificado (leer antes de confiar)

- Los catálogos los generó una IA de tamaño pequeño leyendo la documentación oficial: **endpoints, permisos, límites y restricciones deben confirmarse en la documentación** antes de programar cada función. Un validador comprobó el formato (ids únicos y válidos, una función `whoami` por app, nueve columnas, herramientas viejas presentes), no la exactitud técnica.
- Varios reportes de los agentes tenían cifras incorrectas (p. ej. decían 188 funciones y eran 244); los números de arriba salen del conteo de cada archivo, no de lo que dijo el agente. Hubo que corregir a mano columnas desplazadas, ids en español (Salesforce) y ids de cuatro partes (Brevo, Slack, Facebook).
- Las rutas de conexión y las variables del `.env` salen de leer el código de `app/integrations/providers/`; **nada se ejecutó**. Confirma las rutas en `http://localhost:5001/docs`.
- Los pasos de autenticación no se han probado contra ninguna app real.

## Decisiones pendientes del líder

- **Telegram:** hoy no hay credencial de usuario utilizable. El catálogo recomienda la Bot API con un bot que el propio usuario crea en @BotFather. Ver [`telegram.md`](telegram.md).
- **Discord:** el token OAuth de usuario es casi de solo lectura; 50 de sus funciones exigen un bot token (marcadas en la columna Permiso). Ver [`discord.md`](discord.md).
- **Trello:** el modo de varios campos pide `credentials_enc` y nada lo escribe todavía. Ver [`trello.md`](trello.md).
- **Herramientas internas** (40: IA, workflows, programaciones, memoria): [`internas.md`](internas.md), sin tareas hasta decidir.
- **Funciones duplicadas** entre apps (p. ej. Drive vs Docs/Sheets/Slides): decidir cuál se conserva.
- **Fuera de esta lista:** apps desactivadas del catálogo (`mailchimp`, `ubereats`, `pedidosya`), claves de usuario (`openai`, `anthropic`, `huggingface`, `replicate`) y `whatsapp` (webhook).