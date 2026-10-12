# Cómo probar la autenticación de una app (protocolo para el junior)

Es la **Fase A de cada app** y se hace **antes de escribir las demás funciones**. Objetivo: comprobar con una cuenta real que la conexión funciona de verdad y que **cada falla se comporta como dice el contrato** (código de error correcto, sin cruzar cuentas, sin dejar la cuenta rota).
Cada `tareas/<app>.md` trae su lista con los valores propios de la app (variables, rutas, función `whoami`, permisos). Este archivo explica el **cómo** de cada caso.

> **Estado de lo escrito aquí (2026-10-07):** las rutas y los códigos salen de leer el código del repo. Los pasos de abajo **no se ejecutaron todavía contra una app real**: si algo no coincide, anótalo en tu tabla de resultados y avisa; no lo "arregles" en el handler.
> **Seguridad:** nunca pegues tokens, claves ni el `.env` en chats, PR, issues ni capturas. El script de abajo no imprime secretos.

## 0. Requisitos

- Venv fuera de OneDrive con `pip install -r requirements-dev.txt` (ver [`GUIA_JUNIOR.md`](../doc/funciones/GUIA_JUNIOR.md), sección 0).
- `.env` con **tu propia** app de desarrollador en la plataforma (el líder te da las variables o te dice cómo crearla). Para OAuth, la URI de redirección registrada en la plataforma debe ser **exactamente** la del `.env`.
- Mongo local arriba y la app corriendo: `uvicorn main:app --port 5001`.
- Un usuario de prueba de Shifu (correo y contraseña).
- Una **cuenta de prueba** de la app externa (no uses la de un cliente). Para el caso de dos cuentas, necesitas una **segunda** cuenta distinta.

## 1. Obtener el JWT (una vez por sesión)

```
POST http://localhost:5001/api/v1/auth/login
{ "email": "<tu usuario>", "password": "<tu clave>" }
```
Copia el campo `access_token` de la respuesta (es el JWT de Shifu, **no** el de la app externa). En Postman guárdalo en la variable `token` del entorno ([`POSTMAN.md`](../doc/funciones/POSTMAN.md)). Además necesitas tu `user_id`: es `user.id` de esa misma respuesta. Límite del login: 5 por minuto.

## 2. Los casos (se repiten en todas las apps)

Salvo que la app indique otra cosa, `FUNCION_WHOAMI` es la función marcada con ★ en la tabla de funciones de la app, y el endpoint de prueba es:

```
POST http://localhost:5001/internal/functions/<FUNCION_WHOAMI>/test        (Authorization: Bearer <JWT de Shifu>)
{ "input": {}, "account_ids": [], "allow_write": false }
```
En la respuesta mira `runs[0].result.ok`, `runs[0].result.error.code`, `runs[0].identity.match` y `summary`. El endpoint admite 30 pruebas por minuto.

| Caso | Qué haces | Resultado esperado | Qué guardas como evidencia |
|---|---|---|---|
| **C1 Conectar** | Con el JWT: `GET /api/v1/integrations/<app>/login` (la respuesta trae `url`). Ábrela en el navegador, acepta los permisos; el callback guarda la cuenta. Apps de clave (Brevo) y Trello usan su propio endpoint: lo indica el archivo de la app | El navegador vuelve al front sin `error=` en la URL | Captura de la URL final (sin tokens) |
| **C2 Quedó guardada** | `GET /api/v1/accounts/` con el JWT **y** `python cuenta_prueba.py ver <user_id> <provider>` | Aparece una cuenta con el `provider` esperado, `account_id` con valor real, `status: active`. En OAuth con refresco, `refresh_token` presente (sale `<cifrado>`). Si **no** hay `refresh_token`, anótalo: la app no lo entregó (ver "Si falla") | Salida de `ver` |
| **C3 Funciona** | Llamar a la función `whoami` con el cuerpo de arriba | `ok: true`, `data.account_id` igual al `account_id` guardado, `identity.match: true` | JSON de la respuesta (sin datos personales) |
| **C4 Respaldar** | `python cuenta_prueba.py respaldar <user_id> <provider> <account_id>` | Crea `respaldo_cuenta.json` junto al script | — |
| **C5 Token vencido** | `romper_access` y luego repetir C3 | **Con refresh:** `ok: true`; en `ver` aparece `last_refreshed_at` nuevo (la conexión renovó el token sola). **Sin refresh:** `error.code = auth_expired` y la cuenta pasa a `status: expired` | Respuesta + salida de `ver` |
| **C6 Todo vencido** | `restaurar`, luego `romper_todo` y repetir C3 | `error.code = auth_expired`; `status: expired` **solo en esa cuenta** | Respuesta + salida de `ver` |
| **C7 Cuenta que no existe** | C3 con `"account_ids": ["no-existe"]` (tras `restaurar`) | `error.code = missing_connection` | Respuesta |
| **C8 Sin conexión** | Repetir C3 con **otro** usuario de Shifu que no tenga la app conectada | `error.code = missing_connection` | Respuesta |
| **C9 Dos cuentas** | Conecta una 2ª cuenta de la app (otro `account_id`). **a)** C3 sin `account_ids`; **b)** con `"account_ids": ["A","B"]`; **c)** `romper_todo` solo de A (pasando su `account_id`) y repetir b) | **a)** `account_selection_required`. **b)** dos corridas `ok`, cada `identity.match: true`, ids distintos. **c)** A falla con `auth_expired`, **B sigue `ok`** | Respuesta de a, b y c |
| **C10 Permiso faltante** | Si la plataforma deja conectar con menos permisos (o quitarlos en el panel de la app), ejecuta una función que necesite el permiso quitado | `error.code = missing_scope` (no `auth_expired`) y la cuenta **no** se marca vencida | Respuesta, o "no se pudo forzar" y por qué |
| **C11 Acceso revocado** | Revoca el acceso de Shifu desde el panel de la app (no desde Shifu) y repite C3 | `error.code = auth_expired` | Respuesta |
| **C12 Registro** | Exporta la colección de Postman de la app y llena la tabla "Resultado de las pruebas" de su archivo | Todas las filas completas | La colección en `doc/postman/` |

Entre casos que dañan la cuenta (C5, C6, C9c, C11), **restaura** con `restaurar` o vuelve a conectar (C1). El script solo restaura lo que respaldaste en C4.

## 3. El script `cuenta_prueba.py`

Guárdalo **fuera del repo** (p. ej. en tu escritorio); no se commitea. Cambia `SHIFU_REPO` (variable de entorno o la ruta del código). Usa el `.env` del repo, no imprime secretos y **se niega a romper una cuenta si hay varias y no pasas `account_id`**.

```
python cuenta_prueba.py ver            <user_id> <provider> [account_id]
python cuenta_prueba.py respaldar      <user_id> <provider> [account_id]
python cuenta_prueba.py romper_access  <user_id> <provider> <account_id>
python cuenta_prueba.py romper_todo    <user_id> <provider> <account_id>
python cuenta_prueba.py restaurar      <user_id> <provider> [account_id]
```

`<provider>` es el valor que guarda el flujo de conexión (lo dice cada archivo de app; **verifícalo con `ver`**: si no encuentra cuentas, el valor está mal).

```python
"""Ayudante para probar la autenticacion. Guardalo FUERA del repo (no se commitea).
Uso:  python cuenta_prueba.py <comando> <user_id> <provider> [account_id]
Comandos: ver | respaldar | romper_access | romper_todo | restaurar
"""
import json
import os
import sys

REPO = os.environ.get("SHIFU_REPO", r"C:\ruta\al\repo\shifu-agent-standalone")  # cambia esta ruta
sys.path.insert(0, REPO)
from dotenv import load_dotenv

load_dotenv(os.path.join(REPO, ".env"))  # antes de importar app.*
from pymongo import MongoClient

from app.core.security import encrypt_data

BASURA = "token-invalido-de-prueba"
RESPALDO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "respaldo_cuenta.json")
SECRETOS = ("access_token", "refresh_token", "credentials_enc")


def coleccion():
    uri = os.environ["MONGO_URI"]
    nombre = os.environ.get("MONGO_DB_NAME") or uri.rsplit("/", 1)[-1].split("?")[0]
    return MongoClient(uri)[nombre]["user_connected_accounts"]


def filtro(user_id, provider, account_id=None):
    f = {"user_id": user_id, "provider": provider}
    if account_id:
        f["account_id"] = account_id
    return f


def main(cmd, user_id, provider, account_id=None):
    col = coleccion()
    docs = list(col.find(filtro(user_id, provider, account_id)))
    if not docs:
        sys.exit("No hay cuentas con ese user_id/provider/account_id")
    if cmd == "ver":  # nunca imprime los secretos, solo si existen
        for d in docs:
            print({k: ("<cifrado>" if k in SECRETOS and d[k] else v) for k, v in d.items() if k != "_id"})
    elif cmd == "respaldar":
        copia = {str(d["_id"]): {k: d.get(k) for k in SECRETOS + ("status",)} for d in docs}
        json.dump(copia, open(RESPALDO, "w"))
        print("respaldo en", RESPALDO, "-> cuentas:", len(copia))
    elif cmd in ("romper_access", "romper_todo"):
        if len(docs) > 1:
            sys.exit("Hay varias cuentas: pasa el account_id para romper solo una")
        cambios = {"access_token": encrypt_data(BASURA), "status": "active"}
        if cmd == "romper_todo":
            cambios["refresh_token"] = encrypt_data(BASURA)
        col.update_one({"_id": docs[0]["_id"]}, {"$set": cambios})
        print("roto:", docs[0].get("account_id"), "campos:", list(cambios))
    elif cmd == "restaurar":
        copia = json.load(open(RESPALDO))
        for d in docs:
            orig = copia.get(str(d["_id"]))
            if orig:
                col.update_one({"_id": d["_id"]}, {"$set": {k: v for k, v in orig.items() if v is not None}})
                print("restaurada:", d.get("account_id"))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    main(*sys.argv[1:5])
```

Se probó la lógica de este script contra una base simulada (`mongomock`): `ver`, `respaldar`, `romper_todo` y `restaurar` hacen lo descrito. **No** se probó contra el Mongo real ni con una app externa.
Necesita `pymongo` y `python-dotenv` (ya están en `requirements.txt`).

## 4. Qué cambia según el tipo de autenticación

| Tipo | C5 (token vencido) | Notas |
|---|---|---|
| OAuth 2 con refresh (`oauth2_code`) | La conexión renueva sola: esperar `ok: true` | Si no hay `refresh_token`, el flujo de conexión no lo pidió bien (en Google falta `access_type=offline`; en otras apps falta un scope tipo `offline_access`): se documenta y se avisa |
| Token largo (`bearer`) | No hay refresco: esperar `auth_expired` | Fíjate cuánto dura el token en la plataforma (Meta: ~60 días) |
| Clave de API (`api_key`) | No hay refresco: esperar `auth_expired` | Probar también una clave inventada al conectar: debe rechazarla el endpoint de conexión |
| Varios campos (Trello) | No hay refresco | **Nada escribe `credentials_enc` todavía**: primero hay que resolver esa brecha (ver [`AUTENTICACION.md`](../doc/funciones/AUTENTICACION.md)) |
| Sin credencial de usuario (Telegram) | — | No se prueba hasta que el líder decida el método (ver `telegram.md`) |

## 5. Si algo falla

- **`redirect_uri` no coincide / `invalid_client`:** la URI registrada en la plataforma no es idéntica a `<APP>_REDIRECT_URI` del `.env` (cuidado con `/` final, `http`/`https`, puerto).
- **Vuelve con `error=session_lost` (u otro `error=`):** el `state` del login se perdió o caducó (en Google dura 10 minutos): repite C1 sin tardar. Si persiste, anota el texto exacto del `error=`.
- **La app dice que la aplicación no está aprobada / modo desarrollo:** solo las cuentas añadidas como probadoras pueden conectarse; añade tu cuenta de prueba en el panel de la plataforma.
- **`C3` devuelve `upstream_changed`:** la respuesta de la app no coincide con tu modelo de salida; revisa el log del servidor.
- **`C2` no muestra la cuenta pero el flujo terminó bien:** puede que el callback haya guardado con otro `provider`. Mira el código del callback (`app/integrations/providers/<app>.py`) y anota el valor real.
- **Algo del flujo viejo está roto** (ver "Deuda conocida" en [`CLAUDE.md`](../CLAUDE.md)): **no lo reutilices ni lo parches dentro de la función**; avisa al líder.
- Una prueba que no se pudo hacer se marca `N/A` con la razón, **no** se deja en blanco ni se marca ✅.
