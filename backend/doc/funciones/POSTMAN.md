# Postman: pruebas por API y registro

Cada app tiene su colección en `doc/postman/<app>.json`, **generada desde las fichas** (`python scripts/export_postman.py`). Es el punto de partida: ya trae lo básico,
y tu trabajo es ejecutarlo, ampliarlo y **guardar tus respuestas de ejemplo**. Esas respuestas guardadas son tu registro de lo que probaste.

## Primer uso

1. En Postman: **Import** → `doc/postman/<app>.json` y `doc/postman/shifu.postman_environment.template.json`.
2. **Duplica** el entorno importado (no edites la plantilla), y llena en tu copia: `email` y `password` de tu usuario de Shifu, y `account_id_<app>_a` / `_b` con los `account_id` de tus cuentas de prueba
   (`baseUrl` ya apunta a `http://localhost:5001`). Selecciona tu copia.
3. Ejecuta **"0 · Login"**: guarda el token en el entorno (`token`) y el resto de solicitudes lo usan solo.
4. Por cada función hay una carpeta con:
   - **Ver ficha**: `GET /internal/functions/{id}`.
   - **Caso normal**: usa el ejemplo de la ficha. Con una sola cuenta conectada se usa esa.
   - **Entrada inválida**: debe devolver `invalid_input` (se omite si la función no tiene campos).
   - **Cuenta A / Cuenta B**: la misma prueba con `account_ids`. **Usa las que necesites**: una, diez o ninguna; borra o duplica solicitudes libremente. No hay mínimo.
   - **ATENCIÓN: ejecución real (allow_write)**: solo en funciones que no son de lectura; sin `allow_write` esas funciones se simulan.
5. Después de ejecutar cada solicitud, **Save Response → Save as example** (con un nombre claro: `ok`, `cuenta expirada`, `sin permiso`...).

## Qué se versiona y qué no

| Archivo | ¿Va a git? |
|---|---|
| `doc/postman/<app>.json` | **Sí.** Es el registro de la app (con tus ejemplos guardados) |
| `doc/postman/shifu.postman_environment.template.json` | **Sí.** Solo nombres de variables, valores vacíos |
| Tu entorno con valores reales (`*postman_environment.json` que no sea `.template.json`) | **No.** Está en `.gitignore`. Contiene tu contraseña y tu token |

Las colecciones **no** llevan valores de secretos: todo va por variables `{{...}}` (hay una prueba que lo comprueba).

## Mantener la colección

- **Re-exportar desde Postman** (Collection → Export → v2.1) a `doc/postman/<app>.json` cuando agregues ejemplos o solicitudes. Así el JSON guarda tus respuestas.
- **Cuidado:** `python scripts/export_postman.py` **sobrescribe** las colecciones con la versión generada y **pierde los ejemplos que guardaste**. Úsalo al crear una app nueva
  o cuando cambien las fichas; si cambió una función existente, mejor edita esa carpeta a mano en Postman y exporta. (Pendiente por mejorar: fusionar en lugar de sobrescribir.)
- La salida del generador es determinista: si no cambiaron las fichas, no cambia nada en git.

## Importar directo desde OpenAPI

FastAPI publica `GET /openapi.json` (sin restricción en este repo). Postman puede importarlo y trae **todas** las rutas del backend, no solo las de funciones;
las colecciones de `doc/postman/` son más cómodas porque ya traen el login, los ejemplos y las cuentas.

## Qué mirar en la respuesta del test

`summary.identity_mismatches` > 0 = una cuenta respondió con la identidad de **otra** (cuentas cruzadas): es un bug serio, no lo ignores.
`summary.simulated: true` = no se llamó a la app externa. `runs[].result.error.code` te dice el código del contrato ([`CONTRATO.md`](CONTRATO.md)).
