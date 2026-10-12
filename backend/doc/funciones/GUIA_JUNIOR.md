# Guía para escribir las funciones de una app

Objetivo: dejar una app completa (ficha, handlers, pruebas, colección de Postman) siguiendo el estándar. Antes lee [`CONTRATO.md`](CONTRATO.md) (10 minutos).
Tienes dos ejemplos reales: `app/functions/apps/brevo/` (API key) y `app/functions/apps/dropbox/` (OAuth2); y la plantilla `app/functions/apps/_template/`.

Qué funciones te tocan por app y cómo probar su autenticación: [`../../tareas/README.md`](../../tareas/README.md) (un archivo con casillas por app).

## 0. Entorno

- Crea un venv **fuera de OneDrive** (OneDrive bloquea archivos al sincronizar) e instala `pip install -r requirements-dev.txt`.
- Copia `.env.example` a `.env` y llena lo que necesites. Para las **pruebas automáticas** no hace falta nada del `.env` (`test/functions/conftest.py` fija valores falsos y no toca Mongo, Redis ni OpenAI).
- Dato observado: en una máquina con Python 3.13, instalar el `requirements.txt` completo intentó compilar `pymupdf` (sin rueda para esa versión); el repo trae `.pyc` de `cpython-312`, así que **Python 3.12 es lo más seguro**.
- Mongo local en `:27018` (README) solo lo necesitas para publicar y para probar por API.

## 1. Pasos

1. **Copia** `app/functions/apps/_template/` a `app/functions/apps/<tu_app>/` (minúsculas, sin `_` inicial: las carpetas con `_` se ignoran).
2. **`app_spec.py`:** el nombre de la app, sus `provider_keys` (el valor de `provider` que guarda el flujo de conexión en `user_connected_accounts`) y su `AuthSpec`
   (elige el tipo en [`AUTENTICACION.md`](AUTENTICACION.md)). Si la app no tiene una estrategia implementada, **avisa**: no se resuelve con un parche en tu handler.
3. **`functions.py`:** una función por operación, `id = app.recurso.verbo`. Entrada y salida como modelos Pydantic; el handler usa solo `ctx.conn.request(...)`.
   Verifica los endpoints, parámetros y campos contra la **documentación oficial** de la app (anota la fecha en el docstring del módulo, como hacen Brevo y Dropbox).
4. **Prueba:** copia `test/functions/test_template_app.py` a `test/functions/apps/test_<tu_app>.py`. Mínimo: caso normal, un error de la app (404/401/429) y entrada inválida,
   con `httpx.MockTransport`. Si hay varias cuentas, prueba que **no se cruzan** (ver `test_brevo.py`).
5. **Corre:** `python -m pytest test/functions -q`.
6. **Publica** (necesita Mongo): `python scripts/publish_functions.py`. Corre sin conflicto o te dice qué función cambió sin subir versión.
7. **Prueba por API con una cuenta real** (sección 3) y **registra en Postman** ([`POSTMAN.md`](POSTMAN.md)).
8. **Lista "listo cuando…"** de `_template/README.md`. Haz commit.

## 2. Reglas de oro

- `id` nunca se renombra. Si hay que cambiar algo que rompe, **sube `version`** y deja la anterior.
- No edites una versión publicada: el publicador lo rechaza (y es lo que protege los workflows de los clientes).
- Nunca `except Exception: return "texto"`. Lanza `FunctionError(ErrorCode.x, ...)`; el ejecutor siempre devuelve un `Result`.
- Nada de leer Mongo, descifrar ni loguear tokens dentro de un handler. Todo pasa por `ctx.conn`.
- `account_id` **no** es un parámetro de la función: lo pone quien ejecuta.
- `verb`, `exits_outside` y `reversible` mandan en cuándo el agente pregunta: márcalos con cuidado (una actualización puede ser destructiva).
- **Descripción en inglés y completa** (mín. 200 caracteres; qué hace, cuándo usarla, qué devuelve, límites, qué NO hace) y **cada campo de entrada con su descripción en inglés**: el agente busca la función y llena los argumentos con ese texto. Descríbela, no le des órdenes (`ALWAYS use this`). Detalle y ejemplos en [`CONTRATO.md`](CONTRATO.md), sección "Descripciones".
- Mejorar el texto (descripciones, ejemplos) **no** pide versión nueva; cambiar tipos, campos, `verb`, `scopes` o las marcas, sí.
- Si la respuesta de la app puede ser enorme (HTML de plantillas, cuerpos de correo), **no la devuelvas entera**: recorta el modelo de salida (como `brevo.templates.list`, sin `htmlContent`).

## 3. Conectar una cuenta para probar

| App | Cómo |
|---|---|
| Brevo (API key) | `POST /api/v1/integrations/brevo/key` con `{"api_key": "..."}` y el JWT del login. Valida la clave y guarda la cuenta (`account_id` = el correo de Brevo) |
| Dropbox (OAuth2) | Necesita `DROPBOX_CLIENT_ID`, `DROPBOX_CLIENT_SECRET` y `DROPBOX_REDIRECT_URI` en el `.env`. `GET /api/v1/integrations/dropbox/login` (con JWT) devuelve la URL; el callback guarda la cuenta |
| Otra app | Mira su `app/integrations/providers/<app>.py`. Si **no** existe un flujo de conexión para ese tipo de credencial, es parte del trabajo (y para varios campos, `credentials_enc`: ver "Brecha conocida" en `AUTENTICACION.md`) |

Para probar **con varias cuentas** conecta varias de la misma app; el endpoint ejecuta la función una vez por cada `account_id` que pases.

## 4. Probar por API

```
POST /internal/functions/{id}/test        (con el JWT del login)
{ "input": {...},                         # opcional; vacío = el primer ejemplo de la ficha
  "account_ids": [],                      # opcional; vacío = cuenta por defecto; una o varias = una ejecución por cuenta
  "allow_write": false }                  # lo que no es lectura se SIMULA salvo que lo pongas en true
```

Lee el informe: `function.spec_checks` (la ficha), `runs[]` (un resultado por cuenta, con `identity` si la app tiene `whoami`: `match: false` = respondió **otra** cuenta)
y `summary`. Si tienes **una sola** cuenta y no pasas `account_ids`, se usa esa; con varias y sin `account_ids` verás `account_selection_required` (es lo esperado).
También: `GET /internal/functions` (lista, con el estado de Mongo) y `GET /internal/functions/{id}` (la ficha).

> El endpoint ejecuta con **tus propias** conexiones y las pruebas quedan en `audit_events` (`function_tested`). Si lo necesitas apagado: `FUNCTIONS_TEST_ENABLED=false`.

## 5. Errores frecuentes

| Mensaje | Qué pasó |
|---|---|
| `registra primero la app 'x' con register_app()` | Tu `functions.py` no importa el `APP` de `app_spec.py` |
| `scopes [...] no estan declarados en la app` | Una función pide un scope que `AuthSpec.scopes` no lista |
| `la descripcion debe ser completa (minimo 200 caracteres...)` | Tu `description` es muy corta: agrega cuándo usarla, qué devuelve, límites y qué no hace |
| `la descripcion debe estar en INGLES` | Escribiste la descripción en español (o la heurística lo cree). Reescríbela en inglés |
| `todos los campos de entrada necesitan descripcion en ingles -> campo: ...` | Algún `Field(...)` de tu modelo de entrada no tiene `description` (≥ 10 caracteres, en inglés) |
| `el ejemplo '...' no cumple los esquemas` | Un `example` no valida contra tus modelos de entrada/salida |
| `ya esta registrada` | Dos funciones con el mismo `id` y versión, o importaste el módulo dos veces |
| `No hay estrategia de autenticacion para 'oauth1'...` | Ese método está declarado pero sin implementar |
| `Ficha cambiada sin subir version: ...` (publicar) | Cambiaste algo de una función ya publicada: sube `version` |
| `whoami '...' debe devolver un campo account_id` | La función `whoami` no cumple la convención del contrato |
| Resultado `upstream_changed` en las pruebas | La respuesta de la app no coincide con tu modelo de salida, o hubo una excepción inesperada (revisa el log) |
