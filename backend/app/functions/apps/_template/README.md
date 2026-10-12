# Plantilla de una app de funciones

1. Copia esta carpeta a `app/functions/apps/<tu_app>/` (nombre en minusculas, sin guion bajo inicial: las que empiezan por `_` se ignoran).
2. En `app_spec.py` declara como se autentica la app (un solo tipo de `AuthType`).
3. En `functions.py` escribe una funcion por operacion: `app.recurso.verbo`.
4. Copia `test/functions/test_template_app.py` como `test/functions/apps/test_<tu_app>.py` y adaptalo.
5. Publica y prueba por API (ver `doc/funciones/GUIA_JUNIOR.md` y `doc/funciones/POSTMAN.md`).

## Listo cuando...

- [ ] El `id` es `app.recurso.verbo`, en ingles y minusculas, y empieza por el nombre de la app.
- [ ] `verb` es correcto; si la funcion envia algo fuera (correo, mensaje, publicacion) tiene `exits_outside=True`; si no se puede deshacer, `reversible=False`.
- [ ] Entrada y salida son modelos Pydantic; **cada campo de entrada tiene `Field(description=...)` en INGLES** (el agente llena los argumentos con eso).
- [ ] La `description` de la funcion esta en INGLES y es COMPLETA (min. 200 caracteres): que hace, que devuelve, cuando usarla, parametros y limites, y que NO hace. Describe, no mandes.
- [ ] Hay al menos un `example` valido (con `output` si es de lectura: sirve de resultado simulado).
- [ ] Los `scopes` de la funcion estan entre los de la app.
- [ ] El handler solo usa `ctx.conn.request(...)`; no lee Mongo, no descifra, no loguea tokens.
- [ ] Los errores se lanzan como `FunctionError(ErrorCode.x)`; ningun `except Exception: return "texto"`.
- [ ] Hay una prueba con `httpx.MockTransport` que cubre el caso normal y un error (`not_found` o `invalid_input`).
- [ ] Se probo por API con una cuenta real (una o las que necesites) y la coleccion de Postman esta exportada en `doc/funciones/postman/<tu_app>.json`.
- [ ] Si la app tiene una funcion `whoami`, esta declarada en `AppSpec.whoami`.
- [ ] `python app.functions.scripts.publish_functions` corre sin conflicto (si cambiaste algo que rompe, subiste `version`).
