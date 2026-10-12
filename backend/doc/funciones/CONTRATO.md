# Contrato de una función

`contract_version: 1`. Código: `app/functions/spec.py`. Una función = **una ficha** (datos) + **un handler** (código).

## La ficha (`FunctionSpec`)

| Campo | Qué es | Regla |
|---|---|---|
| `id` | `app.recurso.verbo`, p. ej. `dropbox.files.list` | Tres tramos, minúsculas, inglés; empieza por el nombre de la app. **Nunca se renombra** una vez publicada |
| `version` | Versión mayor del contrato (entero ≥ 1) | Un cambio que rompe la sube. Ver "Versionado" |
| `app` | Nombre de la app | Igual al primer tramo del `id` |
| `upstream_api` | Versión de la API externa que usa (`v3`, `2`) | Informativa; ayuda a ver qué rompió un cambio externo |
| `verb` | `create`, `read`, `update`, `delete` | Una lectura no puede `exits_outside` |
| `exits_outside` | Envía algo fuera (correo, mensaje, invitación, publicación) | |
| `reversible` | Se puede deshacer | Una actualización puede ser destructiva: se marca función por función |
| `scopes` | Permisos que necesita **esta** función | Deben estar entre los de la app |
| `description` | **En inglés y completa** (mínimo 200 caracteres): qué hace, cuándo usarla, qué devuelve, parámetros y límites | La lee el agente para **buscar** la función. Sin órdenes ("ALWAYS use this"). Ver "Descripciones" |
| `examples` | Al menos uno, con `input` (y `output` si es lectura) | Se validan contra los esquemas al registrar; el `output` sirve de resultado simulado |
| `input_schema` / `output_schema` | JSON Schema | **Se generan** de los modelos Pydantic del handler; no se escriben a mano. **Cada campo de entrada lleva `Field(description=...)` en inglés** (mín. 10 caracteres) |
| `status` | `draft`, `testing`, `active`, `degraded`, `obsolete` | Ver "Estados" |

**Política de confirmación (derivada, no se guarda):** `delete` o irreversible → `ask` (preguntar); sale al exterior → `draft_and_confirm`
(borrador y pedir un sí); lo demás → `assume` (asumir y decir el supuesto). Un irreversible gana sobre "sale al exterior".

## Descripciones (las lee el agente)

El agente **busca** las funciones por su descripción (con ~15,000 funciones no se le muestran todas) y **llena los argumentos** leyendo la descripción de cada campo.
Una descripción corta o vaga hace que no encuentre la función o la use mal; por eso el registro la exige **en inglés y completa** y falla al cargar si no lo es.

**Qué debe incluir** (3 a 6 frases):
1. **Qué hace** y sobre qué recurso (`Lists the files and folders directly inside a Dropbox folder...`).
2. **Qué devuelve**: los campos importantes de la respuesta.
3. **Cuándo usarla**: lo que suele pedir el usuario (`Use it when the user wants to browse a folder, find the exact path of something...`). Incluye frases típicas.
4. **Parámetros importantes y valores por defecto**, y los **límites** (máximos, paginación).
5. **Si lee o modifica**, y **qué NO hace**, nombrando la función vecina cuando exista (`it does not search by name: use dropbox.files.search`). Eso evita elegir mal entre funciones parecidas.

**Mal:** `Lista archivos de Dropbox.` (español, una línea, sin nada que distinga la función).
**Bien:** ver `app/functions/apps/dropbox/functions.py` y `brevo/functions.py` (470 a 700 caracteres).

**Reglas que el código comprueba** (`spec.py` y `registry.py`):
- `description` ≥ 200 caracteres (**hipótesis**; se ajusta midiendo el acierto de recuperación del selector, tarea T5).
- Cada campo de entrada con `description` de ≥ 10 caracteres (también hipótesis).
- Ambas en inglés, con una **heurística** barata (`looks_spanish`: letras con tilde o `¿ ¡ ñ`, o dos o más palabras comunes del español como *el, la, para, con*). Atrapa lo evidente;
  puede dejar pasar español sin tildes ni esas palabras: no reemplaza la revisión.
- Describe, **no mandes**: el diseño deja que el modelo decida dentro del cerco. Las herramientas viejas decían `HERRAMIENTA OBLIGATORIA... Úsala SIEMPRE` y eso se quedó fuera a propósito.

**Mejorar el texto no rompe nada:** la huella de versión ignora `description`, `examples` y los `description`/`title` de los esquemas, y al republicar se actualiza el texto
en Mongo sin pedir versión nueva (y sin tocar el `status`). Los mensajes de error de `FunctionError` siguen en español por ahora (ver `CHANGELOG.md`).

## El handler

```python
@function(id="dropbox.files.list", version=1, verb=Verb.read, scopes=["files.metadata.read"],
          description="...", examples=[{"input": {}, "output": {...}}])
async def files_list(ctx: Context, args: ListFilesIn) -> ListFilesOut: ...
```

- `args` y el retorno son modelos Pydantic (de ahí salen los esquemas). Cualquier otra firma se rechaza al registrar.
- Habla con la app **solo** con `ctx.conn.request(...)`. No lee Mongo, no descifra, no loguea tokens; no conoce otras cuentas.
- Errores: `raise FunctionError(ErrorCode.x, "mensaje")`. Nada de `except Exception: return "texto"`.
- El `account_id` lo pone quien ejecuta, **nunca el modelo**: no va en `input_schema`.

## El resultado (`Result`)

Toda función devuelve siempre esto; nunca se lanza una excepción al agente:

```json
{"ok": true,  "data": {...},  "meta": {"function_id": "...", "version": 1, "account_id": "...", "duration_ms": 120, "simulated": false}}
{"ok": false, "error": {"code": "not_found", "message": "...", "retryable": false, "user_action": "fix_input"}, "meta": {...}}
```

El ejecutor **revalida la salida** contra `output_schema` aunque el handler ya devuelva el modelo.

## Códigos de error (diez)

| Código | Cuándo | Reintentable | `user_action` | Cómo se produce |
|---|---|---|---|---|
| `auth_expired` | La app rechaza la credencial, la cuenta está vencida/revocada, o no se pueden leer las credenciales | no | `reconnect_app` | HTTP 401 (tras un intento de refresco si el método lo permite); estado de la cuenta |
| `missing_scope` | Falta un permiso | no | `grant_scopes` | HTTP 403, o un 401 con el texto de `AuthSpec.scope_error_marker` (Dropbox) |
| `access_denied` | La cuenta tiene el permiso pero no acceso a ese recurso (archivo no compartido) | no | `request_access` | HTTP 403 de Google con `insufficientFilePermissions` o "does not have permission", sin mencionar scopes |
| `rate_limited` | Límite de ritmo de la app | sí | `retry_later` | HTTP 429 tras un reintento |
| `not_found` | No existe lo pedido | no | `fix_input` | HTTP 404 o traducción en el handler |
| `invalid_input` | Entrada inválida | no | `fix_input` | Validación Pydantic, o HTTP 400/422 |
| `upstream_changed` | La respuesta de la app no cumple el contrato, o excepción inesperada en el handler | no | `report_bug` | Salida fuera de `output_schema`; se registra el traceback |
| `upstream_down` | Caída, timeout o error 5xx | sí | `retry_later` | HTTP 5xx tras un reintento, timeout, error de red |
| `missing_connection` | El usuario no tiene la app (o esa cuenta) conectada | no | `connect_app` | `get_connection` |
| `account_selection_required` | Varias cuentas activas y no se eligió | no | `choose_account` | `get_connection` |

Los dos últimos **no estaban** en los siete del diseño original: se agregaron al implementar (ver `CHANGELOG.md`).
`retryable` y `user_action` son datos por código (`_ERROR_DEFAULTS` en `spec.py`): el `responder` los convertirá en texto y botones.

## Versionado

- **Rompe** (sube `version`): quitar un campo de la entrada o la salida, cambiar su tipo, volver obligatorio uno opcional, cambiar lo que significa un valor, cambiar `verb`, `scopes`, `exits_outside` o `reversible`.
- **No rompe** (misma versión): mejorar la `description`, agregar o editar ejemplos, mejorar la descripción de un campo.
- `spec_hash` es la **huella del contrato**: ignora `status` y todo el texto (`description`, `examples`, y `description`/`title` dentro de los esquemas). `scripts/publish_functions.py` la compara por `(id, version)`:
  - **igual huella** → el contrato no cambió; si el texto cambió, **se actualiza solo el texto** en Mongo (y el `status` no se toca);
  - **otra huella** → **se niega toda la publicación** (todo o nada) y pide subir `version`. Es deliberado: un workflow de un cliente fija `id + versión` y no debe cambiar por debajo.
- Una versión nueva se publica **junto** a la anterior. `get_function(id)` sin versión devuelve la mayor.

## Estados

`draft` → `testing` → `active` → `degraded` → `obsolete`. El estado inicial viene del código; **después de publicar, manda el de Mongo** (`functions.status`),
que se cambia sin desplegar (p. ej. apagar una función rota). `GET /internal/functions` muestra el de Mongo si existe.
Hoy ningún proceso cambia el estado solo (canario pendiente).

## `whoami` (opcional por app)

Si la app declara `AppSpec.whoami`, esa función de lectura **sin parámetros** debe devolver un campo `account_id` con **el mismo valor guardado al conectar**
(Brevo: el correo; Dropbox: el id de cuenta). Con él, el endpoint de prueba compara quién respondió con la cuenta usada y detecta **cuentas cruzadas**.
El registro lo exige al arrancar (`validate_registry`).
