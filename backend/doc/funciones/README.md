# Sistema de funciones y conexiones

Base para que el equipo escriba las funciones de todas las apps (Gmail, Dropbox, HubSpot, Brevo...) con **un solo estándar**,
las pruebe por API y las mantenga cuando las apps externas cambian. Diseño completo en
[`../PLAN_MAESTRO_sistema_nuevo.md`](../PLAN_MAESTRO_sistema_nuevo.md) (sección "Sistema aparte: funciones y conexiones").

**Estado:** la base está construida y probada con HTTP y Mongo simulados (`test/functions`). **No** está conectada todavía al agente
ni a los workflows: el loader viejo (`bigtools_loader`), los providers y los conectores actuales siguen intactos y conviven con esto.

## Por qué existe

Antes cada herramienta se escribía a su manera: la clase `BigTool` está copiada en cada provider, no había esquema de salida ni versiones,
los errores salían como texto y las credenciales estaban en varios sitios (con código roto, ver [`AUTENTICACION.md`](AUTENTICACION.md)).
Las apps externas cambian sin avisar y eso puede romper los workflows de los clientes. Este sistema da:

1. **Un contrato** por función (ficha + handler) con esquemas de entrada y salida obligatorios → [`CONTRATO.md`](CONTRATO.md).
2. **Versiones**: una función publicada no se edita; lo que rompe sube de versión y la anterior sigue viva. Mejorar el texto no rompe nada y no pide versión.
   Las descripciones van **en inglés y completas**: es lo que el agente usa para buscar la función.
3. **Autenticación extensible**: no solo OAuth 2.0 → [`AUTENTICACION.md`](AUTENTICACION.md).
4. **Un solo almacén de credenciales** (`user_connected_accounts`), con **varias cuentas por app**.
5. **Pruebas por API** (una cuenta o las que quieras) y **registro en Postman** → [`POSTMAN.md`](POSTMAN.md).

## El ciclo (tres piezas más un canario)

```
catalog_apps ──conectar──▶ user_connected_accounts ──▶ catálogo de funciones ──▶ ejecución (chat / workflow)
 (qué apps hay)             (credenciales por           (fichas versionadas)            │
                             usuario, app y cuenta)                                     ▼
                                      ▲                                       resultado {ok, data | error}
                                      └──── auth_expired / estado de la cuenta ◀───────┘   y el canario (futuro)
```

- **Hoy existe:** fichas en código → `scripts/publish_functions.py` las publica a Mongo → `get_connection` resuelve la cuenta →
  `runner.execute` ejecuta y devuelve siempre un `Result` → `/internal/functions/*` para probar.
- **Todavía no existe:** el canario programado (la misma prueba corriendo sola), el selector por búsqueda para el agente,
  el puente con `WorkflowExecutor`, y la lista de "funciones disponibles" según los scopes concedidos.

**Qué funciones hay que escribir, app por app (29 apps, 3.347 funciones catalogadas; 196 son herramientas ya existentes):** [`../../tareas/README.md`](../../tareas/README.md).

## Mapa del código

| Qué | Dónde |
|---|---|
| Ficha, app, resultado, errores | `app/functions/spec.py` |
| Estrategias de autenticación | `app/functions/auth/` |
| Conexión (resuelve cuenta, hace la petición, refresca) | `app/functions/connections.py` |
| Registro estricto de apps y funciones | `app/functions/registry.py` |
| Ejecutor | `app/functions/runner.py` |
| Publicación a Mongo (versionado) | `app/functions/publish.py`, `scripts/publish_functions.py` |
| Apps de referencia | `app/functions/apps/brevo/` (API key), `app/functions/apps/dropbox/` (OAuth2) |
| **Plantilla para copiar** | `app/functions/apps/_template/` |
| Endpoints de prueba | `app/routes/internal/functions.py` |
| Generador de Postman | `app/functions/postman.py`, `scripts/export_postman.py`, salida en `doc/postman/` |
| Pruebas | `test/functions/` |

## Qué queda fuera y cómo puede evolucionar

El contrato está en `contract_version: 1` ([`CHANGELOG.md`](CHANGELOG.md)). Cosas que se dejaron fuera a propósito, para decidir con datos:

| Pendiente | Cuándo se justifica |
|---|---|
| Estrategias `oauth1` (firma), `oauth2_client_credentials`, `hmac_signature` (declaradas, **sin implementar**) | Cuando una app real las necesite (p. ej. PedidosYa). Ver `AUTENTICACION.md` |
| Endpoint para **conectar** apps con credenciales de varios campos (`credentials_enc`) | Antes de la primera app tipo Trello. Hoy nada escribe ese campo |
| Canario programado y `status: degraded` automático | Cuando haya funciones en uso real; hace falta un proceso fuera de la app (el repo no tiene workers) |
| Scopes **concedidos** por cuenta y lista de "funciones disponibles" | Con el selector por búsqueda del agente |
| Puente con el agente y con `WorkflowExecutor` (que hoy usa su propia ruta de herramientas) | Fase siguiente; ahí se migran las más de 150 herramientas |
| Migración de `oauth_vault` a `user_connected_accounts` | Plan F1 del plan maestro; antes hay que medir cuántos usuarios solo están en el vault |
| Brevo no está en el catálogo (`LOGIN_PATHS` / `APIKEY_APPS`) | Al exponerlo en el front |
| `newman` / CI para correr las colecciones | Cuando las pruebas manuales se vuelvan repetitivas |

## Lo que NO está verificado (leer antes de confiar)

- **Nada se ha llamado contra las APIs reales** de Brevo ni Dropbox: los endpoints se verificaron contra su documentación/especificación oficial y las pruebas usan HTTP simulado.
  Por comprobar con una cuenta real: el scope de `list_folder` de Dropbox (se asume `files.metadata.read`) y que la etiqueta de unión llegue como `.tag`.
- **No se probó con un Mongo real**, solo con `mongomock-motor`.
- **No se arrancó la app completa** (`uvicorn main:app`): el Python global de la máquina de desarrollo no tiene todas las dependencias del proyecto
  (faltaban `cffi`, `defusedxml`, `limits`, `aiohttp`, `maxminddb`...). Las pruebas del endpoint usan una app FastAPI mínima con el router. Usa un venv limpio (ver `GUIA_JUNIOR.md`).
- **Las pruebas existentes del agente (`test/agente_v3`) no se pudieron ejecutar** en ese entorno por la misma razón; el trabajo nuevo no modifica su código (solo `main.py`, `constants.py`, `audit_service.py` y `.env.example`, con líneas añadidas).
