# Instrucciones para otra sesión de Claude: llevar el sistema de funciones a otro proyecto

**Para quién es este documento:** una sesión de Claude (y la persona que la dirige) que va a **recibir el sistema de funciones** en un proyecto distinto de este. Aquí se explica **qué es, por qué se diseñó así, cómo está construido y cómo configurarlo en el proyecto nuevo**. **Es autocontenido: todo lo necesario está en este único archivo** (los anexos A a E al final reemplazan a los demás documentos). Solo el **código** se copia aparte desde el repositorio de origen. Léelo completo antes de tocar nada.

> **Estado honesto, léelo primero.** El sistema está construido y probado **solo con HTTP y Mongo simulados** (123 pruebas en `test/functions`). **Nunca** se llamó a una API real (Brevo, Dropbox...), **nunca** se probó con un Mongo real y **nunca** se arrancó la app completa. Todo lo que diga "funciona" aquí significa "pasa sus pruebas con simulación". Los catálogos de funciones de `tareas/` los generó una IA pequeña leyendo documentación y **no están verificados por una persona**.

---

## Prompt de arranque (pégalo al abrir la otra sesión)

```
Vas a recibir en este proyecto un "sistema de funciones" que se diseñó y construyó en otro repositorio (Shifu). Lee COMPLETO el archivo
LLEVAR_A_OTRO_PROYECTO.md: es autocontenido (explica el qué, el porqué y el cómo, e incluye los anexos A a E con el contrato,
la autenticación, el modelo de datos, el protocolo de pruebas y el resumen de catálogos). Solo el CÓDIGO se copia aparte, desde el repositorio de origen.
Reglas de trabajo: (1) no escribas ni copies código hasta que hayas explorado ESTE proyecto y yo confirme el plan; (2) hazme UNA pregunta a la vez,
con tu recomendación; (3) cada número que propongas lleva su métrica y cómo medirla; (4) si algo no lo verificaste, dilo; (5) todo es aditivo:
no modifiques código existente salvo lo mínimo y listado; (6) un commit por paso. Empieza por el paso 0 del documento.
```

---

## 1. Qué es esto y por qué existe

**Shifu** es un **agente de IA** (no un bot de acciones predeterminadas) que trabaja con las apps del usuario: Gmail, Drive, Asana, HubSpot, Slack... El producto planea ~100 apps y, por app, 150 funciones o más (del orden de 15.000 funciones). El agente decide qué hacer; las funciones son **las acciones que puede ejecutar** en esas apps con las credenciales del usuario.

**El problema que resuelve.** En el sistema anterior cada herramienta se escribía a su manera: la clase `BigTool` copiada en cada proveedor, sin esquema de salida, sin versiones, con los errores convertidos en texto y las credenciales repartidas en varios sitios (con código roto). Consecuencias reales:
- Las apps externas **cambian sin avisar** y rompen los flujos de los clientes; no había forma de saber qué función cambió ni de congelar la versión que usa un cliente.
- Un error de una app salía como texto normal, así que el sistema nunca lo veía como fallo.
- Un junior no tenía un estándar para escribir la función número 151 igual que la 1.

**La respuesta: un sistema aparte, con un ciclo de tres piezas:**

```
catalog_apps ─────────▶ user_connected_accounts ─────────▶ functions / function_apps ─────────▶ ejecución
(qué apps existen)       (credenciales por usuario,         (fichas versionadas de cada            (chat o workflow)
                          app y cuenta: el "vault")          función, con su estado)                      │
                                  ▲                                                                       ▼
                                  └────────── estado de la cuenta (vencida, revocada...) ◀──── resultado {ok, data | error}
```

## 2. Principios de diseño (y el porqué de cada uno)

Entiéndelos: en el proyecto nuevo habrá decisiones que no cubre este documento, y estos principios son los que se aplican.

| Principio | Qué significa | Por qué |
|---|---|---|
| **El código define el cerco, el modelo elige dentro** | El código decide lo **no negociable** (permisos, seguridad, qué es irreversible, límites reales de la app). Las decisiones del agente las toma el modelo, **no reglas escritas a mano** (`if "borrar" in texto`) | El producto es un agente, no un bot. Una regla fija limita al usuario y se rompe con casos nuevos. La lógica de negocio sí se codifica |
| **Una ficha + un handler por función** | Una función = datos (ficha versionada) + código (handler). Entrada y salida son modelos Pydantic de los que **se generan** los JSON Schema | Un solo estándar; nada escrito a mano que se desincronice |
| **Resultado uniforme** | Toda función devuelve `{ok, data}` o `{ok:false, error:{code,...}}`; nunca lanza al agente | El agente puede **actuar según el fallo** (reconectar, pedir otro permiso, reintentar) |
| **Versionado estricto** | Una versión publicada **no se edita**. Si algo rompe, se sube `version` y la anterior sigue viva. Mejorar el texto no rompe nada | Los workflows de un cliente fijan `id + versión`; no deben cambiar por debajo |
| **Fallar en voz alta** | El registro rechaza una ficha inválida al cargar; el publicador se niega ante un cambio sin versión nueva. El código viejo **saltaba en silencio** los módulos rotos | Un fallo silencioso es un cliente frustrado |
| **Autenticación extensible** | No todas las apps usan OAuth 2: API key, token largo, usuario/clave, varios campos, firma OAuth1/HMAC. Es un **registro de estrategias** | "Super adaptable al mercado": una app nueva con otro método = una clase + un test |
| **Un solo almacén de credenciales, multicuenta** | `user_connected_accounts`, clave lógica `(user_id, provider, account_id)`. Un usuario puede tener **varias cuentas** de la misma app | Las dos cuentas **no deben cruzarse** nunca; lo prueba una suite y un endpoint |
| **Probar por API es opcional y escala** | Se prueba una función con **una cuenta o con diez**, nunca obligatorio | Si se obliga, se limita; el equipo decide cuánto probar |
| **Lo que no es lectura, se simula** | El endpoint de prueba no ejecuta crear/actualizar/borrar salvo `allow_write=true` | Probar no debe enviar correos ni borrar datos de nadie |
| **Descripciones en inglés y completas** | Cada función y cada campo de entrada llevan descripción en inglés y completa (≥ 200 y ≥ 10 caracteres, **hipótesis a medir**) | El agente **busca** las funciones por su descripción (con 15.000 no se le muestran todas) y llena los argumentos con ella. Una descripción vaga = función no encontrada o mal usada |
| **No se borra, se marca por estado** | Los datos "eliminados" se conservan con un estado; solo se borran físicamente si el usuario lo pide expresamente | Decisión del producto |
| **Aditivo** | El sistema nuevo convive con el viejo; no lo modifica | Poder volver atrás (el repo tiene punto de retorno `baseline-v0`) |

## 3. Cómo está construido (mapa del código)

Todo vive en `app/functions/` (≈ 1.900 líneas entre código y pruebas de `test/functions/`).

| Archivo | Qué hace |
|---|---|
| `app/functions/spec.py` | Modelos del contrato: `FunctionSpec` (ficha), `AppSpec`/`AuthSpec`, `Result`/`ErrorInfo`/`ResultMeta`, `ErrorCode` (9 códigos), `Verb`, `AuthType`, `looks_spanish`, `spec_hash` (huella del contrato) |
| `app/functions/errors.py`, `context.py` | `FunctionError(code, message)`; `Context(user_id, conn, account_id, dry_run)` = lo único que recibe un handler |
| `app/functions/auth/{base,strategies}.py` | Registro de estrategias (`@register_auth`): `none`, `api_key`, `bearer`, `basic`, `custom_params`, `oauth2_code` (con refresh) implementadas; `oauth1`, `oauth2_client_credentials`, `hmac_signature` **declaradas sin implementar** (fallan en voz alta) |
| `app/functions/connections.py` | `get_connection(db, user_id, app, account_id)` y `Connection.request(...)`: aplica la estrategia, refresca una vez ante 401, reintenta 429/5xx una vez y **traduce HTTP → `ErrorCode`** |
| `app/functions/registry.py` | `register_app`, `@function`, `get_function`, `validate_registry`, `load_all`, `isolated_registry` (para pruebas). **Estricto**: una ficha inválida impide cargar |
| `app/functions/runner.py` | `execute(...)`: valida entrada, resuelve la conexión, corre el handler con timeout, **revalida la salida**, siempre devuelve `Result` |
| `app/functions/publish.py`, `scripts/publish_functions.py` | Publica las fichas a Mongo con versionado (todo o nada); crea los índices |
| `app/functions/postman.py`, `scripts/export_postman.py` | Genera una colección de Postman por app, determinista |
| `app/functions/apps/_template/` | **Plantilla para copiar** al crear una app |
| `app/functions/apps/{brevo,dropbox}/` | Apps de referencia: Brevo (API key), Dropbox (OAuth2) |
| `app/routes/internal/functions.py` | `GET /internal/functions`, `GET /internal/functions/{id}`, `POST /internal/functions/{id}/test` |
| `test/functions/` | 123 pruebas (HTTP simulado con `httpx.MockTransport`, Mongo simulado con `mongomock-motor`) |
| `doc/funciones/*.md` | Documentación de origen (`CONTRATO`, `AUTENTICACION`, `MODELO_DE_DATOS`, `GUIA_JUNIOR`, `POSTMAN`, `CHANGELOG`). **Su contenido esencial ya está en los anexos A a D de este archivo** |
| `tareas/` | El trabajo pendiente por app (ver sección 9) |

### Una función completa (patrón de `apps/_template/`)

```python
# app_spec.py: cómo se conecta la app
APP = register_app(AppSpec(app="example", provider_keys=["example"], api_version="v1", multi_account=True,
                           whoami="example.account.get",
                           auth=AuthSpec(type=AuthType.bearer, scopes=["items.read"])))

# functions.py: una función
class ListItemsIn(BaseModel):
    limit: int = Field(default=10, ge=1, le=100, description="How many items to return, from 1 to 100 (default 10)")

@function(id="example.items.list", version=1, verb=Verb.read, upstream_api="v1", scopes=["items.read"],
          description="Lists the items stored in the connected Example app ... (≥ 200 caracteres, en inglés, completa)",
          examples=[{"name": "default", "input": {"limit": 2}, "output": {"items": [{"id": "1", "name": "Uno"}]}}])
async def items_list(ctx: Context, args: ListItemsIn) -> ListItemsOut:
    resp = await ctx.conn.request("GET", f"{BASE_URL}/items", params={"limit": args.limit})
    return ListItemsOut(items=[Item(id=str(i["id"]), name=i["name"]) for i in resp.json()["items"]])
```

El handler **solo** habla con la app por `ctx.conn.request(...)`: no lee Mongo, no descifra, no loguea tokens, no conoce otras cuentas. El `account_id` lo pone quien ejecuta, **nunca el modelo**.

## 4. El contrato en una página

(Detalle ampliado en el anexo A.)

- **Ficha:** `id` (`app.recurso.verbo`, tres tramos, minúsculas, inglés, **nunca se renombra**), `version`, `verb` (`create|read|update|delete`), `exits_outside` (envía algo fuera), `reversible`, `scopes`, `description`, `examples`, `status` (`draft → testing → active → degraded → obsolete`).
- **Política de confirmación derivada** (no se guarda): `delete` o irreversible → preguntar; sale al exterior → borrador y pedir un sí; lo demás → asumir y decir el supuesto.
- **Nueve códigos de error:** `auth_expired`, `missing_scope`, `rate_limited`, `not_found`, `invalid_input`, `upstream_changed`, `upstream_down`, `missing_connection`, `account_selection_required`. Cada uno trae `retryable` y `user_action` (`reconnect_app`, `grant_scopes`, `retry_later`, `fix_input`, `report_bug`, `connect_app`, `choose_account`).
- **`spec_hash`** = huella del **contrato**: ignora `status`, `description`, `examples` y los textos de los esquemas. Mismo hash + texto distinto → el publicador actualiza solo el texto. Hash distinto con la misma versión → **rechaza toda la publicación**: hay que subir `version`.
- **`whoami`:** función de lectura sin parámetros que devuelve `account_id` con **el mismo valor guardado al conectar**; sirve para detectar cuentas cruzadas.

## 5. Conexiones y multicuenta (la parte delicada)

`get_connection` lee **solo** `user_connected_accounts` y aplica estas reglas:

| Situación | Resultado |
|---|---|
| Ninguna cuenta del usuario para la app | `missing_connection` |
| Una cuenta usable | se usa |
| Varias usables y no se eligió | `account_selection_required` |
| `account_id` dado | esa cuenta; si no existe → `missing_connection`; si está vencida → `auth_expired` |
| Token que no se puede descifrar | `auth_expired` (**nunca** se manda el texto cifrado como si fuera un token) |

- El refresco de token y el marcado "cuenta vencida" se hacen **por el `_id` exacto del documento**, nunca por `user_id + provider` (en el código viejo se hacía por proveedor y podía **cruzar cuentas**).
- Un 401 definitivo marca **solo esa** cuenta como `expired`. Si la app avisa de un permiso faltante con un 401 (Dropbox), se declara en `AuthSpec.scope_error_marker` para devolver `missing_scope` sin refrescar ni marcar la cuenta.
- Credenciales de un campo van cifradas en `access_token` (y `refresh_token`); de varios campos, en `credentials_enc` (JSON cifrado). **Nada escribe `credentials_enc` todavía**: falta el flujo de conexión para apps tipo Trello.
- Cifrado: `encrypt_data` / `decrypt_data` (Fernet) del proyecto anfitrión.

## 6. Qué necesita el proyecto nuevo (dependencias del anfitrión)

El paquete `app/functions/` es casi independiente. Esto es **todo** lo que importa de fuera (verificado leyendo los `import`):

| Importa | De | Qué debe ofrecer el proyecto nuevo |
|---|---|---|
| `AppBaseModel` | `app.models._base` | Una base Pydantic v2 (puede ser un `BaseModel` normal con la misma configuración) |
| `Collections` (+ `FUNCTIONS`, `FUNCTION_APPS`, `USER_CONNECTED_ACCOUNTS`) y `ConnectedAccountStatus` (`ACTIVE`, `EXPIRED`, `USABLE`...) | `app.core.constants` | Constantes con los nombres de colección y los estados de cuenta |
| `encrypt_data`, `decrypt_data` | `app.core.security` | Cifrado simétrico (Fernet) para los tokens |
| `get_current_user`, `get_db` | `app.database` | Dependencias FastAPI: usuario autenticado y base Mongo (Motor) |
| `limiter` | `app.core.limiter` | Un limitador de ritmo `slowapi` (el endpoint usa `30/minute`) |
| `log_event` | `app.services.audit_service` | Registro de auditoría (acción `function_tested`); si no hay, un envoltorio mínimo |
| `MongoManager` | `app.core.mongo` | Solo lo usa `scripts/publish_functions.py` para conectarse |

Dependencias de Python: `pydantic` v2, `httpx`, `motor`/`pymongo`, `fastapi`, `slowapi`, `cryptography`. De desarrollo: `mongomock-motor` y `mongomock` (los `FakeDB` caseros suelen **ignorar filtros como `$in`** y dan pruebas engañosas).

**Si el proyecto nuevo no es Python/FastAPI/Mongo, para y avisa:** este código no se porta tal cual; lo que sí se porta son el **contrato, los principios, las reglas de conexión y los catálogos**.

Cambios mínimos en el anfitrión, y solo estos: montar el router (`app.include_router(functions_router, prefix="/internal", ...)`), las dos constantes de colección, la acción de auditoría `function_tested` y la variable `FUNCTIONS_TEST_ENABLED` (interruptor de emergencia del endpoint, activo por defecto).

## 7. Cómo configurarlo en el proyecto nuevo (pasos para la otra sesión)

Trabaja **un paso a la vez**, con un commit por paso, y **pregunta antes de decidir** lo que no esté aquí.

**Paso 0 · Explorar, sin escribir.**
- ¿Es Python/FastAPI/Mongo? ¿Hay `git`? Si no hay repositorio, propón `git init` y una etiqueta de punto de retorno **antes** de cambiar nada.
- ¿Ya existe un almacén de credenciales de usuarios? ¿Con qué nombre y forma de documento? (la clave lógica debe poder ser `user_id + provider + account_id`; si hoy es una cuenta por proveedor, hay que decidir cómo migrar o convivir).
- ¿Ya hay cifrado de tokens, autenticación de usuarios, limitador y auditoría? Anota cada una de las 7 dependencias de la sección 6: existe / hay que crear.
- Pregunta al usuario **una cosa a la vez** con tu recomendación. Preguntas candidatas: ¿es el mismo Mongo?, ¿mismas colecciones?, ¿qué apps van primero?

**Paso 1 · Copiar** (lista exacta en la sección 8) en una rama nueva. No modifiques lo copiado todavía.

**Paso 2 · Adaptar las 7 dependencias.** Prefiere un adaptador fino que reexporte lo del proyecto sobre editar los archivos copiados, para poder traer futuras versiones del sistema.

**Paso 3 · Correr las pruebas.** `pytest test/functions -q`. Deben pasar las 123 (o explicar cuáles y por qué no). El `conftest.py` fija un entorno falso y **no necesita** `.env`, Mongo ni Redis. Si falla algo de imports, es una dependencia mal adaptada, no un error del sistema.

**Paso 4 · Montar el router y publicar.** Arranca la app, mira `/openapi.json` (deben aparecer `/internal/functions*`) y corre `python scripts/publish_functions.py` **dos veces** (la segunda debe ser un no-op).

**Paso 5 · Probar con una app real.** Conecta Brevo (API key) o la app que se elija con una cuenta de prueba y sigue el protocolo del **anexo D**. Aquí se verifica por primera vez lo que hasta hoy solo está simulado.

**Paso 6 · Postman.** `python scripts/export_postman.py`; el entorno con valores reales **no** se commitea (hay `.gitignore` para ello).

**Paso 7 · Empezar las funciones** con `tareas/<app>.md`, en el orden de prioridad que decida el líder.

## 8. Qué copiar y qué NO

**Copiar (rutas del repo de origen):**
- `app/functions/` completo (incluye `apps/_template`, `apps/brevo`, `apps/dropbox`, `auth/`).
- `app/routes/internal/` (`functions.py`, `__init__.py`).
- `scripts/publish_functions.py`, `scripts/export_postman.py`.
- `test/functions/` completo, `requirements-dev.txt`.
- `doc/funciones/` y `doc/postman/` (incluida `shifu.postman_environment.template.json`).
- `tareas/` completo.
- Las reglas de `.gitignore` de `doc/postman/*environment.json` (salvo `*.template.json`) y de `.env`.

**NO copiar:** el agente LangGraph (`app/agent/`), `bigtools_loader`, los providers y conectores viejos (`app/tools/connectors`, `app/integrations/providers`) ni `oauth_vault`. **No son parte de este sistema**: varios están rotos (ver "Deuda conocida" en `CLAUDE.md` del repo de origen) y el diseño los reemplaza. Los flujos de conexión OAuth de cada app (`/login` y `/callback`) hay que **tenerlos o reescribirlos** en el proyecto nuevo: el sistema de funciones asume que la cuenta ya está guardada en `user_connected_accounts` con el `provider` correcto.

## 9. El trabajo pendiente: `tareas/`

- **`tareas/README.md`**: índice. 29 apps y **3.347 funciones** catalogadas (1.411 de lectura); 196 son herramientas que ya existían en el sistema viejo.
- **`tareas/<app>.md`**: una por app, con dos fases. **Fase A:** tareas de autenticación muy explícitas (casos C1 a C12 con rutas, variables del `.env`, `provider` y función `whoami` de esa app). **Fase B:** una fila por función con endpoint, entrada, **resultado esperado**, permiso y marcas (`E` sale al exterior, `I` irreversible, `D` ya hecha).
- **Protocolo común de pruebas de autenticación y script `cuenta_prueba.py`** (en el repo de origen: `tareas/PROBAR_AUTH.md`; aquí: **anexo D**) (ver / respaldar / romper token / restaurar una cuenta de prueba sin imprimir secretos).
- **`tareas/internas.md`**: 40 herramientas internas del agente (IA, workflows, programaciones, memoria) que **no** son apps de terceros y no encajan en el estándar; sin tareas hasta decidir qué hacer con ellas.

**Cómo leer las cifras:** 3.347 es el **techo** de lo que ofrecen las APIs, no un plan. Propuesta de prioridad (pendiente de aprobar): 1) las 196 herramientas existentes; 2) las funciones de lectura; 3) crear, actualizar y borrar solo por demanda real.

## 10. Qué NO está verificado y qué sigue abierto

**Sin verificar (no lo des por hecho):**
- Ninguna llamada a las APIs reales de Brevo ni Dropbox; el scope de `list_folder` de Dropbox y la etiqueta `.tag` están por comprobar.
- Nada probado con un Mongo real ni con la aplicación completa arrancada.
- Los catálogos de `tareas/` (endpoints, permisos, límites) los generó una IA pequeña; un validador solo comprobó el **formato**. Hubo que corregir columnas desplazadas, ids en español (Salesforce) y de cuatro tramos (Brevo, Slack, Facebook), y varios reportes de los agentes tenían cifras falsas.
- Las rutas de conexión (`/api/v1/integrations/<app>/login`) y las variables del `.env` por app salen de **leer** el código, no de ejecutarlo.
- Los mínimos de 200 y 10 caracteres de las descripciones son **hipótesis**: se calibran midiendo el acierto de búsqueda del selector.

**Fuera de este sistema (no lo implementes sin que se pida):**
- **Selector por búsqueda del agente** (con ~15.000 funciones no se inyectan en los prompts; se buscan bajo demanda; el plan parte de `langgraph-bigtool`, prototipo T5). La release de PyPI 0.0.3 **falla** con `langgraph` 1.2.4 (`inject_tool_args`); la rama `main` lo corrige.
- **Puente** con el agente y con el ejecutor de workflows.
- **Canario** (la misma prueba corriendo sola y marcando `degraded`): requiere un proceso fuera de la app.
- **Flujo de conexión para `credentials_enc`** (Trello y similares) y las estrategias `oauth1`, `oauth2_client_credentials`, `hmac_signature`.
- **Migración** del almacén de credenciales viejo (`oauth_vault`) a `user_connected_accounts` (antes hay que medir cuántos usuarios solo existen en el viejo).
- Decidir si los **mensajes de `FunctionError`** (hoy en español) pasan a inglés, como las descripciones.

**Decisiones pendientes del líder:** método de conexión de Telegram (Bot API con bot propio del usuario), Discord (el token OAuth de usuario casi solo lee; 50 funciones exigen bot token), Trello (`credentials_enc`), destino de las herramientas internas, y qué función se conserva cuando dos apps duplican otra (Drive frente a Docs/Sheets/Slides).

## 11. Reglas de trabajo del usuario (cómo conviene trabajar con él)

Hablan español; el líder dirige a juniors que escribirán el código. Preferencias confirmadas a lo largo del diseño:
- **Una pregunta a la vez, con tu recomendación.** No listas largas de preguntas.
- **Cada número que propongas lleva su métrica** y cómo medirlo; si no tiene fuente, di que es una hipótesis.
- **Comporta como un AI developer senior:** cuestiona al usuario **y** cuestiónate a ti. No presentes como hecho lo que no verificaste (en esta sesión hubo correcciones por afirmar cosas sin fuente primaria).
- **Es un agente, no un bot:** sin límites fijos para el usuario ni reglas rígidas de decisión; solo la lógica de negocio va en código.
- **No se elimina nada:** se marca por estado. Solo se borra si el usuario lo pide de forma directa.
- **Discusión antes que implementación** para lo que no se pidió construir. Los planes de facturación están fuera de alcance.
- **Git:** un commit por fase y un respaldo (`git bundle`) fuera de OneDrive al cerrar cada una; el repo de origen vive dentro de OneDrive, que puede bloquear archivos.

## 12. Trampas ya encontradas (te ahorran tiempo)

- **Python 3.12** es lo más seguro; con 3.13 `pymupdf` no tenía rueda. Crea el venv **fuera de OneDrive**.
- `load_dotenv()` debe correr **antes** de importar módulos de la app que crean clientes a nivel de módulo.
- Con `REDIS_URL` del `.env` real, las pruebas tardan (el limitador intenta conectar a Redis): `test/functions/conftest.py` la deja vacía.
- Al probar una app plantilla dos veces el registro lanza "ya está registrada": usa `isolated_registry` y limpia `sys.modules`, y **no** llames a `load_all` dentro.
- El `FakeDB` casero **ignora los filtros con operadores** (`$in`): por eso las pruebas de conexión usan `mongomock-motor`.
- Una salida armada con `model_construct` se salta la validación: por eso el ejecutor **siempre** revalida.
- `AuthSpec.scheme`: `None` significa `Bearer`; `""` significa token crudo (ClickUp). Confundirlos rompe la autenticación sin avisar.
- Si un endpoint de la app devuelve un error "de negocio" con un status que no es 4xx/5xx claro (Dropbox 409), pide `ok_statuses=(409,)` en `request()` y tradúcelo en el handler.

## 13. Glosario

- **Ficha / `FunctionSpec`:** los datos versionados de una función. **Handler:** su código.
- **Cerco:** lo que el código impone (permisos, irreversibles, límites); dentro de él elige el modelo.
- **Cuenta:** una credencial de un usuario en una app; un usuario puede tener varias por app.
- **`whoami`:** función que dice qué cuenta respondió; detecta cuentas cruzadas.
- **Vault:** almacén de credenciales de usuario (`user_connected_accounts`).
- **Catálogo:** `catalog_apps` (qué apps existen) y, aparte, el catálogo de funciones (`functions`).
- **Selector:** la búsqueda bajo demanda de funciones para el agente (pendiente).
- **Canario:** prueba programada que vigila que una función siga funcionando (pendiente).

---

# ANEXOS (reemplazan a los demás documentos: este archivo basta)

## Anexo A · El contrato completo

### Ficha (`FunctionSpec`)

| Campo | Qué es | Regla |
|---|---|---|
| `id` | `app.recurso.verbo` (p. ej. `dropbox.files.list`) | Tres tramos, minúsculas, inglés, regex `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`; empieza por el nombre de la app; **nunca se renombra** una vez publicada |
| `version` | Versión mayor (entero ≥ 1) | Un cambio que rompe la sube |
| `app` | Nombre de la app | Igual al primer tramo del `id` |
| `upstream_api` | Versión de la API externa (`v3`, `2`) | Informativa; ayuda a ver qué rompió un cambio externo |
| `verb` | `create`, `read`, `update`, `delete` | Una lectura no puede tener `exits_outside` |
| `exits_outside` | Envía algo fuera (correo, mensaje, invitación, publicación) | |
| `reversible` | Se puede deshacer | Una actualización puede ser destructiva: se marca función por función |
| `scopes` | Permisos de **esta** función | Deben estar entre los de la app |
| `description` | **En inglés y completa** (≥ 200 caracteres) | La lee el agente para **buscar** la función |
| `examples` | Al menos uno, con `input` (y `output` si es lectura) | Se validan contra los esquemas; el `output` sirve de resultado simulado |
| `input_schema` / `output_schema` | JSON Schema | **Se generan** de los modelos Pydantic; cada campo de entrada lleva `Field(description=...)` en inglés (≥ 10 caracteres) |
| `status` | `draft`, `testing`, `active`, `degraded`, `obsolete` | Después de publicar manda el de Mongo |

### Cómo escribir una descripción (la lee el agente)

Debe incluir, en 3 a 6 frases: (1) **qué hace** y sobre qué recurso; (2) **qué devuelve**; (3) **cuándo usarla** (frases típicas del usuario); (4) **parámetros, valores por defecto y límites**; (5) **si lee o modifica y qué NO hace**, nombrando la función vecina (`it does not search by name: use dropbox.files.search`). **Describe, no mandes:** sin `ALWAYS use this` / `MUST`; el modelo decide dentro del cerco.
El registro comprueba: longitudes mínimas, que esté en inglés (heurística `looks_spanish`: tildes, `¿ ¡ ñ` o dos o más palabras comunes del español; puede dejar pasar español sin tildes) y que cada campo de entrada tenga descripción. Los mínimos son **hipótesis** a calibrar midiendo el acierto del selector.

### Resultado (`Result`) y errores

```json
{"ok": true,  "data": {...},  "meta": {"function_id": "...", "version": 1, "account_id": "...", "duration_ms": 120, "simulated": false}}
{"ok": false, "error": {"code": "not_found", "message": "...", "retryable": false, "user_action": "fix_input"}, "meta": {...}}
```

| Código | Cuándo | Reintentable | `user_action` | Cómo se produce |
|---|---|---|---|---|
| `auth_expired` | La app rechaza la credencial; cuenta vencida/revocada; no se pueden leer las credenciales | no | `reconnect_app` | HTTP 401 (tras un intento de refresco si el método lo permite) o estado de la cuenta |
| `missing_scope` | Falta un permiso | no | `grant_scopes` | HTTP 403, o un 401 con el texto de `AuthSpec.scope_error_marker` |
| `rate_limited` | Límite de ritmo de la app | sí | `retry_later` | HTTP 429 tras un reintento |
| `not_found` | No existe lo pedido | no | `fix_input` | HTTP 404 o traducción en el handler |
| `invalid_input` | Entrada inválida | no | `fix_input` | Validación Pydantic, o HTTP 400/422 |
| `upstream_changed` | La respuesta de la app no cumple el contrato, o excepción inesperada | no | `report_bug` | Salida fuera de `output_schema`; se registra el traceback |
| `upstream_down` | Caída, timeout o 5xx | sí | `retry_later` | HTTP 5xx tras un reintento, timeout, error de red |
| `missing_connection` | El usuario no tiene la app (o esa cuenta) conectada | no | `connect_app` | `get_connection` |
| `account_selection_required` | Varias cuentas activas y no se eligió | no | `choose_account` | `get_connection` |

Los dos últimos se agregaron al implementar (el diseño original tenía siete). El ejecutor **revalida la salida** contra `output_schema` siempre.

### Versionado y estados

- **Rompe** (sube `version`): quitar un campo de entrada o salida, cambiar su tipo, volver obligatorio uno opcional, cambiar lo que significa un valor, cambiar `verb`, `scopes`, `exits_outside` o `reversible`.
- **No rompe:** mejorar `description`, ejemplos o la descripción de un campo.
- `publish` compara el `spec_hash` por `(id, version)`: igual → actualiza solo el texto (y **no** toca `status`); distinto → **rechaza toda la publicación** y pide subir `version`. Una versión nueva se publica junto a la anterior; `get_function(id)` sin versión devuelve la mayor.
- Estados: `draft → testing → active → degraded → obsolete`. El inicial viene del código; después manda Mongo y se cambia sin desplegar (p. ej. apagar una función rota). Hoy ningún proceso lo cambia solo.

### Datos de una app (`AppSpec`)

`app`, `provider_keys` (valores de `provider` que guarda el flujo de conexión; Google usa varios), `api_version`, `multi_account`, `whoami` (id de la función de identidad, opcional) y `auth` (`AuthSpec`). `validate_registry()` exige: estrategia implementada, y que `whoami` exista, sea de lectura, sin parámetros y devuelva `account_id`.

## Anexo B · Autenticación

| `AuthType` | Cómo aplica la credencial | Refresca | Estado | Ejemplo |
|---|---|---|---|---|
| `oauth2_code` | `Authorization: Bearer <access_token>` (configurable con `header_name` y `scheme`) | sí, con `refresh_token`, `token_url` y `client_id_env` / `client_secret_env` | **implementada** | Dropbox, Google, Asana, HubSpot |
| `bearer` | Token largo en un header (`scheme=None` → `Bearer`; `""` → crudo) | no | **implementada** | ClickUp (`scheme=""`), Notion, Slack bot |
| `api_key` | Una clave en un header (`header_name`) o en la query (`placement="query"`, `param_names[0]`) | no | **implementada** | Brevo (`api-key`) |
| `basic` | `Authorization: Basic base64(username:password)` | no | **implementada** | APIs con usuario y clave |
| `custom_params` | Varios campos (`param_names`) en headers o query según `placement` | no | **implementada** | Trello (`key` + `token`) |
| `none` | Nada | — | **implementada** | APIs públicas |
| `oauth2_client_credentials`, `oauth1`, `hmac_signature` | — | — | **declaradas, sin implementar** (el registro falla en voz alta) | PedidosYa, OAuth1 con firma, webhooks firmados |

**Agregar un método nuevo:** (1) una clase que herede de `AuthStrategy` con `apply(req, creds, spec)` (y `refresh(...)` + `can_refresh = True` si renueva), decorada con `@register_auth(AuthType.xxx)`; (2) si hace falta configuración, un campo opcional en `AuthSpec`; (3) pruebas en `test_auth.py` y, si refresca, en `test_connections.py`; (4) actualizar esta tabla. El handler **nunca** ve el secreto crudo.

**Dónde se guardan las credenciales:** una sola colección, `user_connected_accounts`, clave lógica `user_id + provider + account_id`.

| Campo | Uso |
|---|---|
| `access_token` | Credencial de **un campo** (token o API key), cifrada (Fernet) |
| `refresh_token` | Cifrado, o `n/a` / vacío si no hay |
| `credentials_enc` | **Opcional, nuevo:** varios campos como JSON cifrado (`{"key": "...", "token": "..."}`); si existe, manda sobre `access_token`. **Nada lo escribe todavía** |
| `status` | `active`, `needs_refresh` (usables), `expired`, `revoked` |
| `account_id` | Id de la cuenta en la app (correo, id de cuenta...) |
| `last_refreshed_at`, `last_health_check`, `metadata` | Los dos primeros los pone el sistema; `metadata` es libre |

Métodos por app según el repo de origen (leído, **no ejecutado**): OAuth 2 con código y refresco: Google (Gmail, Drive, Docs, Sheets, Slides, Calendar), Asana, HubSpot, Dropbox, Jira (con `cloud_id`), Teams, Outlook, OneDrive, Discord, LinkedIn, Monday, Salesforce, TikTok. OAuth 2 + PKCE: Twitter, Kick. Token largo sin refresco: ClickUp, Notion, Slack (bot), Facebook / Instagram / Threads. API key: Brevo. Clave de app + token de usuario: Trello. Servidor a servidor: PedidosYa. Sin credencial de usuario utilizable: Telegram, WhatsApp.

## Anexo C · Modelo de datos

| Colección | Modelo | Quién escribe | Quién lee | Índice |
|---|---|---|---|---|
| `functions` | `FunctionSpec` + `spec_hash`, `created_at`, `updated_at` | `publish()`: inserta versiones nuevas y, si el contrato no cambió, actualiza solo el texto | `GET /internal/functions` (el `status`) | única `(id, version)` |
| `function_apps` | `AppSpec` + fechas | `publish()`: upsert por `app` | nadie todavía (el registro lee del código) | única `app` |
| `user_connected_accounts` | documento libre (ver anexo B) | los flujos de conexión; las funciones solo en 2 casos, **por `_id` exacto**: refresco exitoso y 401 definitivo | `get_connection` | — |
| `audit_events` | evento append-only | cada prueba por API (`function_tested`: versión, cuentas, ok, simulada, cruces de identidad) | — | — |

Fuente de verdad: la **ficha** vive en el código (Mongo recibe una copia al publicar); el **`status`** de una función publicada es de Mongo; las **credenciales y el estado de cada cuenta** son de Mongo; **cómo se autentica** una app (`AuthSpec`) es del código. Los índices los crea `publish()` (idempotente), no la app al arrancar. Colecciones heredadas que el sistema **no** lee: `oauth_vault`, `users.integrations`, `user_secrets`, `app_tools_catalog`.

## Anexo D · Probar la autenticación (protocolo completo)

Se hace **antes de escribir las demás funciones** de cada app, con una cuenta de prueba (no de un cliente). Nunca pegues tokens ni el `.env` en chats, PR ni capturas.

1. **JWT:** `POST /api/v1/auth/login` con `{"email","password"}`; guarda `access_token` y `user.id`. (Es la ruta del repo de origen: usa la del proyecto nuevo.)
2. **Endpoint de prueba:** `POST /internal/functions/<FUNCION_WHOAMI>/test` con `{"input": {}, "account_ids": [], "allow_write": false}`. Mira `runs[0].result.ok`, `runs[0].result.error.code`, `runs[0].identity.match` y `summary`. Límite: 30 por minuto. Lo que no es lectura se **simula** salvo `allow_write=true`; usa **solo las conexiones del usuario del token**.

| Caso | Qué hacer | Resultado esperado |
|---|---|---|
| **C1 Conectar** | `GET <ruta de login de la app>` con el JWT; abrir la URL y aceptar permisos (apps de clave: su endpoint de clave) | Vuelve al front sin `error=` |
| **C2 Guardada** | Listar las cuentas del usuario y `cuenta_prueba.py ver` | Cuenta con `provider` esperado, `account_id` real, `status: active`; en OAuth, `refresh_token` presente |
| **C3 Funciona** | Llamar a la función `whoami` | `ok: true`, `data.account_id` igual al guardado, `identity.match: true` |
| **C4 Respaldar** | `cuenta_prueba.py respaldar` | Crea `respaldo_cuenta.json` |
| **C5 Token vencido** | `romper_access` y repetir C3 | Con refresh: `ok: true` y `last_refreshed_at` nuevo. Sin refresh: `auth_expired` y cuenta `expired` |
| **C6 Todo vencido** | `restaurar`, `romper_todo`, repetir C3 | `auth_expired`; `expired` solo en esa cuenta |
| **C7 Cuenta inexistente** | C3 con `"account_ids": ["no-existe"]` | `missing_connection` |
| **C8 Sin conexión** | C3 con otro usuario sin la app | `missing_connection` |
| **C9 Dos cuentas** | Conectar una 2ª cuenta. (a) C3 sin `account_ids`; (b) con `["A","B"]`; (c) `romper_todo` solo de A y repetir (b) | (a) `account_selection_required`; (b) dos `ok` con `identity.match: true`; (c) A `auth_expired` y **B sigue `ok`** |
| **C10 Permiso faltante** | Conectar con menos permisos y ejecutar una función que lo necesite | `missing_scope` y la cuenta **no** se marca vencida (o `N/A`) |
| **C11 Revocado** | Revocar el acceso desde el panel de la app y repetir C3 | `auth_expired` |
| **C12 Registro** | Exportar la colección de Postman y completar la tabla de resultados | Todo completo |

Entre los casos que dañan la cuenta (C5, C6, C9c, C11) **restaura** con `restaurar` o reconecta. Si algo no se pudo hacer: `N/A` con la razón, nunca en blanco ni ✅. Si falla: `redirect_uri` no coincide → la URI registrada en la plataforma debe ser **idéntica** a la del `.env`; app en modo desarrollo → solo cuentas probadoras; flujo viejo roto → **no lo parches dentro de una función**, avisa.

**Script `cuenta_prueba.py`** (guárdalo **fuera del repo**; no imprime secretos; se niega a romper una cuenta si hay varias y no pasas `account_id`). Uso: `python cuenta_prueba.py <ver|respaldar|romper_access|romper_todo|restaurar> <user_id> <provider> [account_id]`. Se probó su lógica contra una base simulada, **no** contra Mongo real.

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

## Anexo E · Resumen de los catálogos de funciones

En el repositorio de origen hay un archivo `tareas/<app>.md` por app, con **Fase A** (las tareas del anexo D con los valores de esa app: `provider`, variables del `.env`, ruta de conexión y función `whoami`) y **Fase B** (una fila por función). Cada fila trae: `id`, verbo, endpoint, qué hace, entrada principal, **resultado**, permiso, marcas (`E` sale al exterior, `I` irreversible, `W` whoami, `D` ya hecha) y la herramienta vieja que cubre, si existe. Resumen:

| App | Archivo | Funciones | De lectura | Herramientas viejas | Hechas | Autenticación |
|---|---|---:|---:|---:|---:|---|
| Brevo | `brevo` | 289 | 119 | — | 3 | API key |
| Slack | `slack` | 282 | 101 | — | — | token largo / sin refresh |
| Trello | `trello` | 250 | 124 | — | — | token largo / sin refresh |
| Asana | `asana` | 244 | 116 | 21 | — | OAuth2 con refresh |
| HubSpot | `hubspot` | 217 | 108 | 52 | — | OAuth2 con refresh |
| Jira Cloud | `jira` | 206 | 91 | 5 | — | OAuth2 con refresh |
| ClickUp | `clickup` | 179 | 71 | 14 | — | token largo / sin refresh |
| monday.com | `monday` | 133 | 25 | — | — | token largo / sin refresh |
| Microsoft Teams | `teams` | 133 | 54 | — | — | OAuth2 con refresh |
| Dropbox | `dropbox` | 127 | 64 | 11 | 3 | OAuth2 con refresh |
| Telegram | `telegram` | 126 | 23 | — | — | token largo / sin refresh |
| Salesforce | `salesforce` | 110 | 63 | — | — | OAuth2 con refresh |
| Outlook | `outlook` | 99 | 39 | — | — | OAuth2 con refresh |
| LinkedIn | `linkedin` | 80 | 45 | — | — | token largo / sin refresh |
| Google Drive | `google_drive` | 79 | 30 | 9 | — | OAuth2 con refresh |
| Google Sheets | `google_sheets` | 79 | 17 | 17 | — | OAuth2 con refresh |
| X (Twitter) | `twitter` | 79 | 46 | — | — | OAuth2 con refresh |
| Gmail | `gmail` | 76 | 30 | 13 | — | OAuth2 con refresh |
| Discord | `discord` | 75 | 33 | — | — | OAuth2 con refresh |
| Facebook | `facebook` | 70 | 43 | 1 | — | token largo / sin refresh |
| Google Slides | `google_slides` | 66 | 9 | 15 | — | OAuth2 con refresh |
| Google Docs | `google_docs` | 62 | 10 | 15 | — | OAuth2 con refresh |
| Notion | `notion` | 61 | 30 | — | — | token largo / sin refresh |
| Instagram | `instagram` | 57 | 30 | 23 | — | token largo / sin refresh |
| OneDrive | `onedrive` | 54 | 31 | — | — | OAuth2 con refresh |
| Google Calendar | `google_calendar` | 39 | 13 | — | — | OAuth2 con refresh |
| Kick | `kick` | 32 | 17 | — | — | OAuth2 con refresh |
| Threads | `threads` | 23 | 17 | — | — | token largo / sin refresh |
| TikTok | `tiktok` | 20 | 12 | — | — | OAuth2 con refresh |
| **Total (29 apps)** | | **3347** | **1411** | **196** | **6** | |

Hay además 40 herramientas internas del agente (IA, workflows, programaciones, procesos, memoria) que no son apps de terceros y quedan fuera hasta decidir su destino. **Telegram:** sin OAuth de usuario; el catálogo recomienda la Bot API con un bot propio del usuario. **Discord:** 50 de sus 75 funciones exigen bot token. **Trello:** necesita `credentials_enc`.
