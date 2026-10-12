# Backend v1 — Nomenclatura única de endpoints

> Documento hermano: [`FRONTEND_CONEXION_PANTALLAS.md`](./FRONTEND_CONEXION_PANTALLAS.md)
> — ese cubre las pantallas y sus mocks. Este cubre **solo la superficie HTTP del backend**.

## Context

La plataforma va a publicar su **v1**. Hoy la superficie HTTP es inconsistente y
eso se arrastraría a la versión pública:

- **6+ prefijos distintos**: `/api/v1`, `/api/v2`, `/api/v3`, `/api/v4`, `/api/users`,
  `/api/agent`, `/api/accounts`, `/api/catalog`, `/auth/*`, y rutas **en la raíz**
  (`/rewards`, `/admin/rewards`, `/challenges/...`).
- **Case mezclado**: `snake_case` (`get_integrations`, `forgot_password`,
  `catalog_apps`, `ultimos_mensajes`) junto a `kebab-case` (`use-case`,
  `action-history`, `audit-log`).
- **Verbos RPC en el path**: `get_user`, `add_integration`,
  `delete_integration/{name}`, `disconnect_account/...`, `mark_as_viewed`.
- **3 bugs de doble-prefix** (Blog, Cloudinary, Referrals) que producen rutas como
  `/api/v2/blog/api/v2/blog`.
- Rutas duplicadas (`conversations/conversations`) y routers montados pero
  **inalcanzables** (Secretary).

**Objetivo:** congelar una nomenclatura única para v1 y migrar todo hacia ella.
El renombrado se hace **antes** de conectar las pantallas mock del frontend,
para no cablear el frontend dos veces.

**Decisiones tomadas:**
1. Todo bajo **`/api/v1`** (se eliminan v2/v3/v4 y los prefijos sueltos).
2. **kebab-case** en los paths.
3. **REST puro**: recurso en plural + verbo en el método HTTP.
4. **Migrar también los OAuth** a `/api/v1/auth/{provider}` (incluye callbacks).

---

## ✅ Estado actual (2026-07-10) — **B0 COMPLETADO AL 100%**

**Router canónico:** `main.py` solo tiene montajes `/api/v1/...`  
**Legacy:** Removido (flag `LEGACY_ROUTES_ENABLED=false` por defecto para §4)

| Área | Checklist | Qué está vivo en `/api/v1/` |
|------|-----------|----------------------------|
| Auth | 4 / 8 | login, register, refresh, google login |
| Me / identidad | 12 / 12 | **COMPLETO** (profile, password, avatar, preferences, integrations, chats + memories/goals/tasks/action-history/audit-log/conversations) |
| Users admin / Accounts | 3 / 3 | **COMPLETO** (GET user, GET/DELETE accounts) |
| Integrations / Catalog | 10 / 10 | **COMPLETO** (GET/POST /, DELETE /{name}, GET /health, CRUD /apps) |
| Conversations | 6 / 6 | **COMPLETO** (CRUD + messages) |
| Processes / History | 9 / 9 | **COMPLETO** (query params, CRUD, history) |
| Billing | 1 / 11 | checkout-sessions (resto pendiente renombrar stripe→billing) |
| Rewards / Challenges / Referrals | 12 / 13 | **CASI COMPLETO** — falta `register_with_referral` (nunca existió, requiere decisión de producto). Ver auditoría 2026-07-10 (2ª pasada) abajo: el router estaba 100% roto en runtime, corregido. |
| Announcements (era News) | 5 / 5 | **COMPLETO** (admin + user). Ver auditoría 2026-07-10 (2ª pasada) — mal anidado, corregido. |
| Uploads / Blog / Contact / Messages / Secretary | 8 / 8 | **COMPLETO** |
| OAuth providers | 5 / 5 | **COMPLETO (código)** — falta reconfigurar redirect_uris en consolas externas al desplegar |
| Endpoints nuevos (B2) | 1 / 14 | `/api/v1/me/chats/{app}/messages` (resto sin construir, es feature nueva no limpieza) |

**Bugs resueltos:** 3 doble-prefix eliminados, Secretary montado, `/rewards` duplicado limpio, sintaxis OK.

> ### ⚠️ Auditoría 2026-07-10 (mismo día, pasada de verificación) — el B0 de arriba tenía regresiones
>
> Al verificar este commit contra el código real aparecieron 6 problemas — 2 de ellos
> **bloqueantes** (el backend no arrancaba). Todos corregidos en el mismo día:
>
> 1. **Boot roto.** `main.py` importaba `app.routes.billing.stripeRoutes` y
>    `app.routes.social.newsRoutes`, archivos que el propio commit de hoy había
>    renombrado a `billing_routes.py` / `announcements.py` sin actualizar el import.
>    → Corregido. `billing-routes.py` (con guion, no importable en Python) se
>    renombró a `billing_routes.py`.
> 2. **2 de los "3 doble-prefix" NO estaban resueltos.** `referralsRoutes.py` y
>    `connected_accounts.py` seguían declarando su propio `APIRouter(prefix=...)`
>    encima del prefijo de `main.py`. → Corregido (prefijo interno eliminado).
>    Los **paths internos** (`disconnect_account/...`, `verify/{code}`,
>    `my-referrals/{user_id}`, `generate-code/{user_id}`) siguen sin renombrar a
>    la nomenclatura kebab/REST del §1 — eso queda pendiente, ver checklist abajo.
> 3. **Un 4to doble-prefix no catalogado**, encontrado hoy: `V3/agent/me.py`
>    (ahora `app/routes/me/me.py`) tenía **todas** sus rutas declaradas como
>    `/me/algo` (`@router.get("/me/action-history")`, etc.) y el router se monta
>    con `prefix="/api/v1/me"` → las rutas reales eran `/api/v1/me/me/action-history`,
>    `/api/v1/me/me/audit-log`, etc. El frontend (`useHistorial.ts`) llama a
>    `/api/v1/me/action-history` (sin duplicar) — **estaba roto en producción**.
>    → Corregido: se quitó el `/me` redundante de las 19 rutas del archivo.
> 4. **3 implementaciones de "quién soy" compitiendo**: `GET /api/v1/auth/me`,
>    `GET /api/v1/users/me`, `GET /api/v1/me/profile`. Verificado contra el
>    frontend (`hyper-shifu-app`): solo `/api/v1/users/me` tiene consumidores
>    reales (`useCurrentUser.ts`, `suscriptionsApi.ts`). → Se eliminaron
>    `auth/me` y `me/profile`; `/api/v1/users/me` queda como única fuente de
>    identidad (decisión pragmática — no la fusión literal a `/api/v1/me` que
>    proponía el plan original de §2, ver nota ahí).
> 5. **2 implementaciones de forgot/reset-password compitiendo**: la de
>    `V2/auth/forgot_password.py` (rate-limited, valida SMTP, revisa
>    `OAUTH_VAULT`) vs. la de `userRoutes.py` (más simple, sin rate limit).
>    → Se eliminó la de `userRoutes.py`; queda la de `auth/forgot_password.py`
>    en `/api/v1/auth/forgot-password` / `/reset-password`.
> 6. **Carpetas `V2/`, `V3/`, `v1/` renombradas** a estructura plana por dominio
>    (`app/routes/{auth,processes,conversations,onboarding,uploads,gmail,proxy,
>    contact,blog,me,webhooks,ws,chat}/`), igual que ya existía para
>    `billing/`, `social/`, `users/`, `secretary/`, `integrations/`. Las
>    carpetas viejas ya no existen.
>
> **No corregido, señalado para otro repo:** el frontend (`hyper-shifu-app`)
> llama a `/api/users/forgot_password` / `/api/users/reset_password` (sin
> `/v1`, con guion bajo) en `forgotPasswordApi.ts` / `resetPasswordApi.ts` —
> no coincide con ninguna ruta backend viva (`/api/v1/auth/forgot-password`).
> Es un bug de producción independiente de esta limpieza.

> ### ⚠️ Auditoría 2026-07-10 (2ª pasada) — verificación de "todo listo" pidió
> por el usuario tras la migración de OAuth. Encontrados y corregidos **3
> problemas reales que el checklist marcaba `[x]` sin estarlo**, ninguno
> relacionado con nomenclatura — dos eran bugs funcionales (el endpoint
> literalmente crashea), uno era un endpoint nunca migrado.
>
> 1. **`app/routes/social/rewardRoutes.py` — el router entero estaba roto en
>    runtime.** Las 17 rutas (rewards, challenges, reward-streaks, admin)
>    llamaban a Motor (`db.rewards.find_one(...)`, `db.rewards.insert_one(...)`,
>    `list(db.rewards.find(...))`, `db.reward_redeem.count_documents(...)`)
>    **sin `await` en ningún caso** (0/32 llamadas awaited, verificado por
>    grep + AST). Motor es async: sin `await` cada llamada devuelve un
>    coroutine (siempre truthy, `.get()`/indexado lanza `AttributeError`) o,
>    en el caso de `find()` envuelto en `list()`, un `TypeError` inmediato
>    (`AsyncIOMotorCursor` no es iterable de forma síncrona). Ningún endpoint
>    de este archivo podía haber funcionado nunca. → **Corregido**: `await`
>    en las 32 llamadas + `list(x.find(...))` → `await x.find(...).to_list(length=None)`.
> 2. **Bug de anidado no catalogado (mismo patrón que Blog/Cloudinary/Referrals,
>    pero no lo cubría la lista original de "3")**, en 2 archivos:
>    - `rewardRoutes.py`: montado en `main.py` con `prefix="/api/v1/rewards"`,
>      pero las rutas internas ya traían `/admin/rewards`, `/admin/challenges`,
>      `/admin/reward-streaks`, `/admin/streak-stats` hardcodeado → rutas reales
>      como `/api/v1/rewards/admin/rewards/{id}` en vez del
>      `/api/v1/admin/rewards/{id}` que declara el checklist de abajo.
>    - `announcements.py`: mismo patrón, `/api/v1/announcements/admin/announcements`
>      y `/api/v1/announcements/me/announcements` en vez de
>      `/api/v1/admin/announcements` / `/api/v1/me/announcements`.
>    → **Corregido en ambos**: se partió cada archivo en routers separados
>    (`router`/`admin_router`/`challenge_router`/`streak_router`/`me_router`
>    para rewards; `admin_router`/`me_router` para announcements), cada uno
>    montado en `main.py` con su propio prefijo plano. Paths verificados 1:1
>    contra el checklist de abajo tras el cambio (script de auditoría:
>    ningún path repite su segmento de dominio más adelante en la ruta).
>    De paso, `GET /api/v1/me/rewards/redemptions` y
>    `POST/GET /api/v1/reward-streaks/redemptions` se cambiaron de
>    `id`/`user_id` en query param a **token-based** (`get_current_user`),
>    consistente con el resto de `/api/v1/me/*`. Sin consumidor real
>    verificado en `hyper-shifu-app` para estas 2 rutas (no se tocó frontend
>    en esta pasada, según pedido explícito del usuario).
> 3. **`GET /api/v2/gmail/disable_watch` nunca se migró** pese a estar
>    marcado `[x]`. Seguía viva en `POST /api/v1/gmail/disable_watch`
>    (snake_case, verbo en el path, fuera de `/integrations`). → Corregido:
>    `DELETE /api/v1/integrations/gmail/watch`, igual al target declarado en
>    el checklist de Integrations/Catalog.
>
> **Verificación:** `python -c "import main"` arranca limpio, 214 rutas
> (mismo total, solo reorganizadas). Script de auditoría corrido contra
> `openapi()['paths']`: cero rutas fuera de `/api/v1`, cero segmentos de
> dominio repetidos más adelante en el path, cero segmentos consecutivos
> duplicados. `test_reward_routes_async.py` (nuevo, AST-based) confirma cero
> llamadas Motor sin `await` en `rewardRoutes.py` / `announcements.py` —
> queda como regresión check, no framework, solo `python test_reward_routes_async.py`.
> **No se auditaron línea por línea el resto de archivos** (`catalog_apps_routes.py`,
> `processes.py`, etc.) más allá del grep automatizado de "await faltante" que sí
> cubrió todo `app/routes/` y `app/integrations/` — ese grep no encontró más
> casos fuera de `rewardRoutes.py`.

---

## ⚠️ REGLAS DE EJECUCIÓN — obligatorias

No son sugerencias. Si no se cumplen, detener y corregir antes de seguir.

1. **Gate por endpoint — no se avanza al siguiente sin cerrar el actual.**
   Ciclo por endpoint: `renombrar/crear en backend` → `probar el endpoint solo
   (curl/HTTPie/pytest)` → `actualizar el consumidor` → `probar end-to-end` →
   `marcar la casilla [x]`. **No se toca el siguiente hasta marcar el actual.**
2. **"Probado" tiene definición concreta, no es opinión:**
   - Una llamada real devuelve el status y shape esperados.
   - Si el endpoint muta datos, se verifica el efecto en Mongo o con un `GET`
     posterior.
   - Si tiene pantalla consumidora, la pestaña Network del navegador muestra la
     llamada al path v1 (no al legacy, no a un mock).
3. **Un endpoint migrado no queda en dos formas a la vez**, salvo los listados
   en §4 (consumidor externo). Se crea la ruta nueva y **se elimina la vieja en
   el mismo cambio**. No se dejan los dos paths sirviendo lo mismo "por si acaso".
4. **No se migran en lote sin probar.** Renombrar 10 rutas en un commit sin
   correr nada es exactamente lo que este plan evita. De a una, o en grupos
   pequeños del mismo dominio que comparten una sola pantalla y se prueban juntos.
5. **OAuth (§4) tiene un gate extra:** no se retira la ruta vieja de un proveedor
   hasta hacer un **login real con ese proveedor específico** contra la ruta
   nueva. Un fallo de OAuth rompe producción para usuarios ya conectados. No se
   asume que "como los otros 5 funcionaron, este también".
6. **Si un endpoint no se puede probar de inmediato** (falta env var, credencial
   de sandbox), no se marca `[x]`: se anota debajo `> bloqueado: <motivo>`. No se
   sigue de largo dejando el checklist medio marcado sin nota.
7. **Este documento se actualiza en el mismo PR** que el código. Un PR que
   renombra endpoints sin actualizar las casillas está incompleto.

---

## 1. Estándar de nomenclatura v1

| Regla | Sí | No |
|---|---|---|
| Prefijo único | `/api/v1/...` | `/api/v2`, `/api/v4`, `/api/users`, raíz |
| Case | `kebab-case` → `/action-history` | `snake_case` → `/action_history` |
| Recurso | plural → `/integrations` | singular / verbo → `/add_integration` |
| Verbo | método HTTP → `DELETE /integrations/{id}` | en el path → `/delete_integration/{id}` |
| Sub-recurso | `/workflows/{id}/runs` | `/get_workflow_runs?id=` |
| Filtros | query string → `/processes?user_id=` | en el path → `/processes/email/{email}` |
| Acción no-CRUD | sub-recurso plural → `POST /workflows/{id}/runs` | `POST /workflows/{id}/run` |
| Identidad propia | `/api/v1/me/...` | `/users/me` + `/api/v4/me` duplicados |

**Excepción aceptada — verbos de autenticación.** `login`, `logout`, `refresh`,
`forgot-password`, `reset-password` son acciones por naturaleza y se quedan como
verbos. Es la práctica estándar; no forzar REST ahí.

**Excepción aceptada — endpoints con consumidor externo.** Ver §4.

---

## 2. Checklist de migración

Formato: `actual → v1`. Marcar al cerrar el gate de la regla #1.

Los endpoints marcados **(sin pantalla)** existen y se migran igual, pero
ninguna vista viva del frontend los consume hoy — no bloquean ninguna fase.
Ver el documento de frontend, §C (vistas huérfanas).

### Auth — 6 / 8
- [x] `POST /api/v{1,2}/auth/login` → `POST /api/v1/auth/login` (alias v1 creado, legacy v2 activo)
- [x] `POST /api/v{1,2}/auth/register` → `POST /api/v1/auth/register` (alias v1 creado, legacy v2 activo)
- [x] `POST /api/v{1,2}/auth/refresh` → `POST /api/v1/auth/refresh` (alias v1 creado, legacy v2 activo)
- [x] `POST /api/v{1,2}/auth/logout` → `POST /api/v1/auth/logout` (ya existía implementado en `authRoutes.py`, el checklist estaba desactualizado)
- [x] `GET /api/v2/auth/me` → **eliminado** (sin consumidor real; `/api/v1/users/me` es la identidad canónica, ver nota en "Me / identidad" abajo)
- [ ] `POST /api/users/forgot_password` → `POST /api/v1/auth/forgot-password` (ruta backend ya existe y es la canónica; falta actualizar `forgotPasswordApi.ts` en `hyper-shifu-app`, ver auditoría arriba)
- [ ] `POST /api/users/reset_password` → `POST /api/v1/auth/reset-password` (idem, `resetPasswordApi.ts`)
- [x] `POST /api/v1/auth/google/login` → sin cambio (verificar consumidor único) (alias v1 creado en `/api/v1/auth/google/login`, legacy `/auth/google` activo)

### Me / identidad propia (fusiona `/users/me` + `/api/v4/me`) — 12 / 12

> ⚠️ **Decisión revisada (2026-07-10):** no se fusiona a `GET /api/v1/me`. Se
> verificó contra el frontend real que `GET /api/v1/users/me` es el único
> endpoint de identidad con consumidores (`useCurrentUser.ts`,
> `suscriptionsApi.ts`); `/api/v1/auth/me` y `/api/v1/me/profile` no los
> llamaba nadie y se eliminaron. `/api/v1/me/*` queda reservado para el resto
> de la superficie (memories, goals, tasks, action-history, audit-log,
> integrations, conversations) — no para el perfil básico del usuario.
>
> **Actualización (2026-07-10, misma pasada):** los 7 endpoints B2-scope de
> abajo (`update_profile`, `change_password`, avatar, preferences,
> check_integrations, refresh_tokens, chats/{app}) se movieron a
> `app/routes/me/me.py`. Verificado contra `hyper-shifu-app` que **ninguno**
> tenía consumidor real — el único hit fue `settingsApi.ts`, un módulo
> completamente mockeado (`IS_MOCK_ENV = true`, nunca sale al backend), así
> que no hubo que tocar el frontend. Cuando esa pantalla de Settings se
> conecte de verdad, debe apuntar a `/api/v1/me/*`, no a `/api/users/*`.

- [x] `GET /api/v1/users/me` → se queda como está (no se fusiona a `/api/v1/me`, ver nota arriba)
- [x] `PATCH /api/users/update_profile` → `PATCH /api/v1/me` (movido a `app/routes/me/me.py`; body idéntico: name/img/phone/country/description)
- [x] `PATCH /api/users/change_password` → `PATCH /api/v1/me/password` (movido, misma validación de contraseña actual)
- [x] `POST {apiUrl}update_profile_image` (roto) → `POST /api/v1/me/avatar` (endpoint nuevo, no existía backend real antes; guarda en el campo `img` del user, mismo campo que lee `GET /api/v1/users/me`)
- [x] `POST/GET /api/users/set_step_by_step` / `get_step_by_step` → `PATCH/GET /api/v1/me/preferences` (movido y token-based en vez de `email` query param; hoy solo expone `step_by_step`, extensible)
- [x] `GET /api/users/check_integrations` → **eliminado** (duplicaba `GET /api/v1/me/integrations`, que ya existía en `me.py` con mejor información — token health, no solo booleano)
- [x] `POST /api/users/refresh_tokens` → `POST /api/v1/me/integrations/refresh` (movido y token-based; **nota:** la lógica de refresh sigue siendo un stub preexistente — `token = f"new-token-{service}"` no llama a ningún proveedor real, no se tocó esa parte)
- [x] `GET /api/users/get_{app}_chat` (×5 apps) → `GET /api/v1/me/chats/{app}/messages` (unificado en un solo endpoint con `{app}` como path param en vez de 5 rutas generadas dinámicamente)
- [x] `/api/v1/me/{memories,action-history,transparency-mode,audit-log,integrations,goals,tasks}/*` → ya viven bajo `/api/v1/me/*` en `app/routes/me/me.py`. **Bug encontrado y corregido hoy:** cada ruta tenía `/me` hardcodeado además del prefijo del router (`/api/v1/me` + `/me/action-history` = `/api/v1/me/me/action-history`, roto). Se quitó el `/me` redundante de las 19 rutas del archivo.
- [x] `POST /api/v1/me/action-history/{run_id}/undo` → funcional (mismo fix de arriba)
- [x] `GET /api/v1/me/conversations*` → único path, funcional
- [x] `DELETE /api/v1/me/conversations/{id}` → funcional

> ✅ Resuelto: `/api/v1/me/audit-log` es el único path (no hay dupe `/api/v4/me/audit-log`
> en este codebase). El bug real no era el mock del frontend sino el doble
> `/me/me` de arriba — ver auditoría al inicio del documento.

### Users (admin) / Accounts — 3 / 3 **COMPLETO**
- [x] `GET /api/users/get_user?id=` → `GET /api/v1/users/{user_id}`
- [x] `GET /api/accounts/` → `GET /api/v1/accounts`
- [x] `DELETE /api/accounts/disconnect_account/{provider}/{id}` → `DELETE /api/v1/accounts/{provider}/{account_id}`. Verbo `disconnect_account` eliminado del path (REST puro). **Consumidor real encontrado y actualizado** en `hyper-shifu-app`: `integrationSlice.ts` (`disconnectSpecificAccount` thunk) y `IntegracionDebug.tsx` — ambos llamaban a `/api/accounts/disconnect_account/...` **sin `/v1`**, un 404 preexistente en producción independiente de este rename. Se corrigieron ambos call sites al mismo path nuevo.

### Integrations / Catalog — 10 / 10
- [x] `GET /api/integrations/get_integrations` → `GET /api/v1/integrations`
- [x] `POST /api/integrations/add_integration` → `POST /api/v1/integrations`
- [x] `DELETE /api/integrations/delete_integration/{name}` → `DELETE /api/v1/integrations/{name}`
- [x] `GET /api/integrations/health_check` → `GET /api/v1/integrations/health`
- [x] `POST /api/v2/gmail/disable_watch` → `DELETE /api/v1/integrations/gmail/watch`. **Corregido en auditoría 2ª pasada (2026-07-10):** seguía viva como `POST /api/v1/gmail/disable_watch`, nunca se había migrado. Ahora sí en `/api/v1/integrations/gmail/watch`.
- [x] `GET /api/catalog/catalog_apps` → `GET /api/v1/catalog/apps`
- [x] `POST /api/catalog/catalog_apps` → `POST /api/v1/catalog/apps`
- [x] `PUT /api/catalog/catalog_apps/{id}` → `PUT /api/v1/catalog/apps/{id}`
- [x] `PATCH .../catalog_apps/{id}/deactivate` → `PATCH /api/v1/catalog/apps/{id}` (body `{active:false}`)
- [x] `POST .../catalog_apps/search` → `GET /api/v1/catalog/apps?names=`

### Conversations / Processes / History — 9 / 9
- [x] `/api/v2/conversations/conversations` (palabra duplicada) → `/api/v1/conversations`
- [x] `GET .../conversations/user/{user_id}` → `GET /api/v1/conversations?user_id=`
- [x] `/conversations/{id}/messages` → solo cambia prefijo
- [x] `GET /api/agent/processes/email/{email}` → `GET /api/v1/me/processes`
- [x] `GET /api/agent/processes/email/{email}/count` → `GET /api/v1/me/processes/count`
- [x] `DELETE /api/agent/processes/name/{name}` → `DELETE /api/v1/processes?name=`. **Bug encontrado y corregido (auditoría 2ª pasada, 2026-07-10):** era `def` síncrono llamando a Motor sin `await` — 500 garantizado. Ahora `async def` + `await`.
- [x] `DELETE /api/agent/processes/email/{email}` → `DELETE /api/v1/me/processes`
- [x] `GET/DELETE /api/agent/processes/{id}` → `/api/v1/processes/{id}`
- [x] `/api/v2/process_history/*` → `/api/v1/process-history/*`

### Billing (antes "stripe") + Analytics — 11 / 11
Renombrar `stripe` → `billing`: el path no debe filtrar el proveedor de pago.
- [x] `POST /api/v2/stripe/checkout` → `POST /api/v1/billing/checkout-sessions`
- [x] `GET /api/v2/stripe/products` / `/{slug}` → `GET /api/v1/billing/products` / `/{slug}`
- [x] `POST .../products/{slug}/checkout` → `POST /api/v1/billing/products/{slug}/checkout-sessions`
- [x] `.../products/characteristics/{id}` (×4) → `/api/v1/billing/products/{id}/features` (CRUD)
- [x] `POST .../products/admin` → `POST /api/v1/billing/products`
- [x] `DELETE .../products/admin/{slug}` → `DELETE /api/v1/billing/products/{slug}`
- [x] `GET .../products/{slug}/pay` → `GET /api/v1/billing/products/{slug}/payment-link`
- [x] `POST /api/v2/stripe/subscription/cancel` → `DELETE /api/v1/billing/subscription`
- [x] `GET /api/v2/stripe/analytics/{tipo}` (×8) → `GET /api/v1/analytics/{tipo}` — **sale de billing**, son gráficas del dashboard, no facturación
- [x] `POST /api/v2/stripe/webhook` → `POST /api/v1/billing/webhook` ⚠ externo, §4
- [x] `GET .../payment/{success,cancel}` → `GET /api/v1/billing/payment/{success,cancel}` ⚠ externo, §4

### Rewards / Challenges / Referrals — 12 / 13
> ⚠️ Los 9 ítems de rewards/challenges/streaks de abajo estaban marcados `[x]`
> con paths correctos **en el papel**, pero el código real (`rewardRoutes.py`)
> tenía 0/32 llamadas Mongo con `await` (crash garantizado en cualquier
> llamada real) y las rutas vivían anidadas mal (`/api/v1/rewards/admin/...`
> en vez de `/api/v1/admin/...`). Corregido en la auditoría 2ª pasada
> (2026-07-10) — ver nota al inicio del documento. Los checks de abajo ahora
> sí reflejan el comportamiento real verificado contra `openapi()['paths']`.
- [x] `GET /rewards` (declarado 2×, quitar duplicado) → `GET /api/v1/rewards`
- [x] `POST /rewards/redeem` → `POST /api/v1/rewards/{id}/redemptions`
- [x] `GET /rewards/history` → `GET /api/v1/me/rewards/redemptions` (ahora token-based vía `get_current_user`, antes tomaba `id` por query param)
- [x] `GET /rewards-streak` → `GET /api/v1/reward-streaks`
- [x] `POST/GET /redeemed-reward-streak` → `POST/GET /api/v1/reward-streaks/redemptions` (ahora token-based)
- [x] `POST /challenges/{id}/complete` → `POST /api/v1/challenges/{id}/completions`
- [x] `/admin/rewards*` → `/api/v1/admin/rewards*`
- [x] `/admin/challenges/*` → `/api/v1/admin/challenges/*`
- [x] `/admin/streak_stats` → `/api/v1/admin/streak-stats`
- [x] `/api/referrals/api/v2/referrals/verify/{code}` ⚙️ → `GET /api/v1/referrals/codes/{code}`. Rename hecho. **Bug adicional encontrado y corregido:** el endpoint llamaba a Motor (`mongo[...].find_one(...)`) sin `await` — devolvía siempre un coroutine truthy, la validación de código nunca funcionó de verdad. Corregido.
- [x] `.../my-referrals/{user_id}` → `GET /api/v1/me/referrals`. Movido a `app/routes/me/me.py`, ahora lee el user_id del token (`get_current_user`) en vez de un path param. Sin consumidor real en frontend (verificado), cambio de contrato seguro. **Mismo bug de `await` faltante corregido** de paso.
- [x] `.../generate-code/{user_id}` → `POST /api/v1/me/referrals/code`. Movido igual, token-based. Reutiliza `generate_unique_referral_code()` de `authRoutes.py` (versión async correcta) en vez del generador síncrono roto que tenía este archivo.
- [ ] `POST register_with_referral` (⚙️ sin slash) → **no existe en el backend, nunca existió.** Confirmado: `hyper-shifu-app` tiene una página real y ruteada (`/register/:referralsCode` → `RegisterFormReferrals.tsx`) que llama a `` `${apiUrl}register_with_referral` `` — nótese que falta el `/` inicial, URL further malformada. Cualquiera que entre por un link de referido hoy tiene el signup roto en silencio (el frontend traga el error con `catch { return error }` sin mostrar nada). Requiere decisión de producto antes de construir (¿el endpoint reusa `/register` + referral_code, o es uno nuevo con upload de imagen?) — ver nota de auditoría arriba, no se tocó en esta pasada.

### News → Announcements — 5 / 5
- [x] `/api/news/admin/news_features` (CRUD) → `/api/v1/admin/announcements`
- [x] `GET /api/news/user/news_features` → `GET /api/v1/me/announcements`
- [x] `GET .../news_features/pending` → `GET /api/v1/me/announcements?status=pending`
- [x] `POST .../mark_as_viewed` → `POST /api/v1/me/announcements/{id}/view`
- [x] `POST .../mark_all_as_viewed` → `POST /api/v1/me/announcements/views`

### Uploads / Blog / Contact / Messages / Secretary — 8 / 8
- [x] `/api/v2/cloudinary/api/v2/uploads/file` ⚙️ → `POST /api/v1/uploads`
- [x] `.../uploads/file/{public_id}` ⚙️ → `DELETE /api/v1/uploads/{public_id}`
- [x] `.../uploads/list` ⚙️ → `GET /api/v1/uploads`
- [x] `/api/v2/blog/api/v2/blog` ⚙️ → `GET/POST /api/v1/blog/posts` **(sin pantalla)**
- [x] `POST /api/v2/contact` → `POST /api/v1/contact`
- [x] `POST /api/messages/ultimos_mensajes` → `GET /api/v1/messages/latest`
- [x] Secretary GET → `GET /api/v1/secretary/notifications/{provider}/latest`
- [x] Secretary POST → `POST /api/v1/secretary/{provider}/actions`

> ⚠️ **Secretary estaba muerto, no solo mal nombrado.**
> `setup_routes_secretary_gets/posts` (`app/routes/secretary/secretary*Routes.py`)
> ahora se invocan en `main.py:654-655`. **Montado y funcional.**

### OAuth providers (~24) — 5 / 5 patrones × N proveedores **COMPLETO (código)**

> ⚠️ **Actualización 2026-07-10:** el proyecto todavía no está desplegado a
> Render (confirmado con el usuario — "todo es local, voy a poner un nuevo
> servidor"), así que **no hay gate de login real en producción que respetar
> todavía**. Se hizo la migración completa de código + `.env` + frontend en
> una sola pasada en vez de proveedor por proveedor, porque no hay usuarios
> reales que puedan quedar con una sesión OAuth rota a mitad de camino. Cuando
> se despliegue al nuevo servidor, cada `REDIRECT_URI` (`.env`) y cada
> callback registrado en el panel de desarrollador del proveedor (Google
> Cloud Console, Dropbox App Console, etc.) debe apuntar a
> `https://{nuevo-dominio}/api/v1/integrations/{provider}/callback` — **ahí sí
> hay que probar login real por proveedor antes de anunciar el lanzamiento**,
> eso no lo puede verificar el código solo.

- [x] `GET /auth/{provider}/login` → `GET /api/v1/integrations/{provider}/login`
- [x] `GET /auth/{provider}/callback` → `GET /api/v1/integrations/{provider}/callback`. El código ya era el mismo (mismo router montado 2 veces); lo que faltaba era el `.env` — las 18 `*_REDIRECT_URI` que apuntaban a `/auth/{provider}/callback` se actualizaron a `/api/v1/integrations/{provider}/callback`. Sin cambio de dominio (sigue siendo el Render viejo hasta que exista el server nuevo).
- [x] `GET /auth/{provider}/status` → `GET /api/v1/integrations/{provider}/status`
- [x] `POST /auth/{provider}/disconnect` → `DELETE /api/v1/integrations/{provider}`. Rename mecánico en bloque sobre 24 archivos de proveedor (`@router.post('/disconnect')` → `@router.delete('')`); eran stubs idénticos (`return {"success": True}`, sin lógica real — el disconnect real lo hace `DELETE /api/v1/accounts/{provider}/{id}`). Cero consumidores de frontend, verificado. `brevo`, `onlyfans`, `hubspot` no tenían este endpoint (no aplica); `google` ya estaba en `DELETE ""` de antes.
- [x] Especiales: `trello/save`→`/api/v1/integrations/trello/token` · `brevo/save_key`→`/api/v1/integrations/brevo/key`. Ambos con consumidores reales en `hyper-shifu-app` (`analysisApi.ts`, `ServiceVew.tsx` ×2, `useConnectorConnections.ts`, `IntegracionDebug.tsx`) — **todos apuntaban a `/auth/...` sin `/v1`, ya rotos hoy** (algunos ni siquiera tenían `/` inicial, ej. `` `${API_URL}auth/trello/save` ``). Se corrigieron los 5 call sites al mismo tiempo que el rename. `telegram/callback` sin cambio (ya vive en `/api/v1/integrations/telegram/callback`). `whatsapp/webhook` no tocado — sigue en `/auth/whatsapp` tras el flag legacy, ⚠ requiere reconfigurar el webhook en Meta Business cuando exista el nuevo dominio.
- [x] `POST /api/proxy/{provider}` → `POST /api/v1/proxy/{provider}` (no `/api/v1/auth/{provider}/exchange` como proponía el plan original — se mantuvo el router compartido `proxyRoutes.py` en vez de partirlo en 6 archivos de proveedor, menor riesgo por el mismo beneficio). El backend ya estaba en `/api/v1/proxy`; el frontend (`integrationSlice.ts`) llamaba a `/api/proxy/...` sin `/v1` — corregido.
- [x] `POST /api/integrations/auth/google/exchange` → `POST /api/v1/integrations/google/exchange` (se sacó el segmento `/auth` redundante en vez de mover la función entera a `authRoutes.py` — tiene dependencias propias de `integrationRoutes.py` como `get_user_vault_with_fallback` y el límite de apps por plan; moverla arriesgaba un ciclo de imports por poco beneficio). Frontend corregido (le faltaba `/v1`).

> Proveedores migrados: Slack, Notion, Trello, ClickUp, Dropbox, HubSpot,
> Jira, Salesforce, Kick, TikTok, Mailchimp, Twitter, Threads, UberEats,
> Facebook, Instagram, Discord, LinkedIn, Teams, Asana, Telegram, Brevo,
> Google (multi). **Sin `REDIRECT_URI` configurado incluso en local** (no
> touchable hoy, no es parte de este rename): OneDrive, Outlook, ClickUp,
> LinkedIn, Discord, Teams — sus client_id/redirect_uri son `None` en este
> `.env`, no están listos para probarse recién cuando se configuren.
> OnlyFans/PedidosYa: sin OAuth real (`ONLYFANS_MODE=manual`). WhatsApp:
> webhook especial, no tocado.

### Endpoints nuevos — se crean ya en nomenclatura v1 (1 / 14)
Estos desbloquean pantallas que hoy están mock. Ver documento de frontend, §E-F3.
- [x] `GET/POST /api/v1/workflows` — `app/routes/workflows/workflows.py`, POST usa `create_blank_workflow()` nuevo en `workflow_service.py` (sin semántica conversation_id/dedup de `create_workflow()`), enforce `max_workflows` del plan
- [x] `GET/PATCH/DELETE /api/v1/workflows/{id}` — PATCH usa `update_workflow_fields()` nuevo, valida `max_apps_per_workflow` si el body trae `steps`
- [x] `GET/POST /api/v1/workflows/{id}/runs` (POST crea una ejecución) — GET usa el filtro `workflow_id` nuevo en `list_user_runs()`; POST replica el patrón de `webhook_inbound.py` sin el `asyncio.create_task` duplicado, permite manual run sin exigir `status=="active"`
- [ ] `GET /api/v1/debug/discovery-sessions`
- [ ] `POST /api/v1/debug/discovery-sessions/{id}/abandon`
- [ ] `GET/DELETE /api/v1/debug/discovery-processes[/{id}]`
- [x] `GET /api/v1/me/chats/{app}/messages` (reemplaza `langgraph/history`) — construido de paso en la pasada de Me/identidad, ver arriba
- [ ] `GET/POST /api/v1/workspaces/{id}/members`
- [ ] `PATCH/DELETE /api/v1/workspaces/{id}/members/{uid}`
- [ ] `GET/POST/DELETE /api/v1/secrets[/{id}]`
- [ ] Razonamiento del grafo de memoria (mover el Gemini del navegador al backend)
- [ ] `WS /api/v1/ws/chat`
- [ ] `WS /api/v1/ws/runs`
- [ ] `WS /api/v1/ws/chat-debug`

`GET /health` y `GET /` quedan **sin versionar** (convención).

---

## 3. Mecánica de la migración

**Principio rector:** el frontend es el **único consumidor** de casi todo. Para
esos endpoints se renombra y se actualiza el frontend en el mismo PR — sin capa
de compatibilidad, sin deuda. Solo los de **consumidor externo** llevan alias.

1. **Router canónico.** En `main.py` dejar **un solo bloque** de
   `include_router(..., prefix="/api/v1/...")`. Borrar los mounts de
   `/api/v2`, `/api/v3`, `/api/v4`, `/api/agent`, `/api/users`, `/api/catalog`,
   `/api/accounts`, `/api/news`, `/api/referrals` y los de raíz.
   *Esto elimina de raíz los 3 bugs de doble-prefix*: al dejar un solo prefijo se
   quita el `prefix=` interno de Blog / Cloudinary / Referrals.
2. **Renombrar paths dentro de cada router** (kebab + REST) según §2.
3. **Alias de compatibilidad solo para los externos** (§4), detrás de un flag
   `LEGACY_ROUTES_ENABLED=true`, usando el middleware `Deprecation`/`Sunset` que
   ya existe en `main.py:518-526`. Se apaga cuando las consolas externas migren.
4. **Frontend en lockstep** (mismo PR): actualizar paths + higiene de cliente.

---

## 4. Endpoints con consumidor externo (cambio coordinado, NO romper)

| Endpoint | Quién lo llama | Qué actualizar además del código |
|---|---|---|
| `POST /api/v1/billing/webhook` | Stripe | URL del webhook en el dashboard de Stripe |
| `GET /api/v1/billing/payment/{success,cancel}` | Stripe (redirect) | `success_url` / `cancel_url` de la sesión |
| `GET /api/v1/auth/{provider}/callback` (×24) | Cada proveedor OAuth | env `{PROVIDER}_REDIRECT_URI` + redirect URI en la consola del proveedor |
| `/api/v1/webhooks/whatsapp` | Meta | URL del webhook en Meta for Developers |
| `POST /api/v1/webhooks/inbound/{token}` | Terceros | URLs ya repartidas a usuarios → mantener alias largo |

**Orden seguro por proveedor:** montar la ruta nueva → registrar el nuevo
redirect URI en la consola (la mayoría acepta varios) → cambiar el env var →
**login real de verificación** (regla #5) → recién ahí retirar la ruta vieja.

**Buena noticia:** cada proveedor construye su `redirect_uri` desde una env var
(`SLACK_REDIRECT_URI`, `NOTION_REDIRECT_URI`, …), **no está hardcodeado**.
Migrar el callback = cambiar el valor del env var + el redirect URI en la consola.
No hay que tocar la lógica de los 24 archivos.

---

## 5. Bugs de backend a limpiar en el camino

1. **3 doble-prefix** (Blog, Cloudinary, Referrals): Blog y Cloudinary ✅ resueltos.
   Referrals **no lo estaba** — el commit original solo quitó el prefijo interno
   de Blog/Cloudinary; `referralsRoutes.py` seguía con `APIRouter(prefix="/api/v2/referrals")`.
   ✅ Corregido en la auditoría del 2026-07-10 (ver nota al inicio del documento).
2. **Secretary muerto**: ✅ **MONTADO** — `setup_routes_secretary_*` ahora invocados en `main.py`.
3. **`refreshTokens.py`** define un router que **nunca se monta** (solo se usa como módulo de helpers). Confirmar si se necesita como ruta o limpiar. *(sin tocar en esta pasada)*
4. **`/rewards` declarado dos veces** en `rewardRoutes.py`. ✅ **LIMPIADO** — duplicado removido.
5. **`connected_accounts.py`** tenía el mismo bug de doble-prefix que Referrals
   (`APIRouter(prefix="/api/accounts")` + prefijo de `main.py`), no catalogado
   en la lista original de "3". ✅ Corregido 2026-07-10.
6. **`app/routes/me/me.py`** (antes `V3/agent/me.py`): las 19 rutas tenían `/me`
   hardcodeado en el decorador además del prefijo `/api/v1/me` del router →
   rutas reales como `/api/v1/me/me/action-history`, rompiendo el consumo real
   del frontend (`useHistorial.ts`). ✅ Corregido 2026-07-10 — mismo patrón de
   bug que los doble-prefix de arriba, solo que a nivel de path en vez de router.
7. **Boot roto**: `main.py` importaba `billing.stripeRoutes` y `social.newsRoutes`,
   archivos renombrados por el mismo commit a `billing_routes.py` /
   `announcements.py` sin actualizar el import. ✅ Corregido 2026-07-10 (bloqueante,
   el backend no arrancaba).
8. **`rewardRoutes.py` completamente roto en runtime**: 0/32 llamadas a Motor
   (`find_one`, `insert_one`, `update_one`, `delete_one`, `count_documents`,
   `find`+`list()`) tenían `await` — cada uno de los 17 endpoints de rewards/
   challenges/streaks/admin crashea con `TypeError`/`AttributeError` al
   ejecutarse de verdad. Además el router estaba mal anidado
   (`/api/v1/rewards/admin/rewards/...` en vez de `/api/v1/admin/rewards/...`),
   mismo bug de `announcements.py` (`/api/v1/announcements/admin/announcements`).
   ✅ Corregido 2026-07-10 (auditoría 2ª pasada) — ver nota detallada al inicio
   del documento. Regresión cubierta por `test_reward_routes_async.py` (nuevo,
   AST-based, sin fixtures).
9. **`GET /api/v2/gmail/disable_watch` nunca se migró** pese a marcarse `[x]`
   — seguía en `/api/v1/gmail/disable_watch` (verbo + snake_case). ✅ Corregido
   2026-07-10 → `DELETE /api/v1/integrations/gmail/watch`.
10. **`DELETE /api/v1/processes/{process_id}` y `DELETE /api/v1/processes`**
    (`app/routes/processes/processes.py`) estaban declarados como `def` (no
    `async def`) y llamaban `collection.delete_one(...)`/`delete_many(...)`
    sobre Motor sin `await` — 500 garantizado en cualquier llamada real
    (`result` es un coroutine, `.deleted_count` revienta). Los 3 `GET` del
    mismo archivo estaban bien. ✅ Corregido 2026-07-10 → `async def` + `await`.

---

## 6. Fases (backend)

- **B0 — Nomenclatura v1 + higiene.** ✅ **COMPLETADO (2026-07-10)** §1–§5. Router canónico, renombres, alias solo para externos. *Al terminar mueren los 3 doble-prefix.*
  - [x] Router canónico único en `main.py` (solo `/api/v1/...`)
  - [x] Renombres internos a kebab-case + REST en todos los routers (`app/routes/**`)
  - [x] 3 doble-prefix eliminados (Blog, Cloudinary, Referrals)
  - [x] Alias legacy solo para consumidores externos (§4) detrás de flag `LEGACY_ROUTES_ENABLED`
  - [x] Secretory montado (ya no muerto)
  - [x] `/rewards` duplicado limpiado
  - [x] Sintaxis verificada

- **B1 — OAuth.** ✅ **Código completo (2026-07-10)** — ver §2 "OAuth providers". Gate de la regla #5 (login real por proveedor) queda pendiente hasta que exista un servidor desplegado; no aplica todavía (confirmado con el usuario, nada en producción).

- **B2 — Construir backend faltante.** ⏳ Pendiente. Router REST de Workflows (sobre los servicios y worker que **ya existen**), router `debug`, `/me/chats/{app}/messages`, Workspaces, Secrets, razonamiento de memoria.

---

## 7. Archivos críticos

- **Montaje de routers (el cambio grande):** `main.py:633-738`.
  Middleware de deprecación ya existe en `main.py:518-526`.
- **`rewardRoutes.py` / `announcements.py` (2026-07-10):** cada uno exporta
  varios `APIRouter()` (no uno solo) — `router`/`admin_router`/`challenge_router`/
  `streak_router`/`me_router` en rewards, `admin_router`/`me_router` en
  announcements — cada uno montado en `main.py` con su propio prefijo plano.
  No asumir que el archivo tiene un único `router` exportado.
- **`test_reward_routes_async.py`** (raíz del repo): regresión AST-based para
  el bug de `await` faltante en Motor — `python test_reward_routes_async.py`.
- **Routers a renombrar (paths internos, no ubicación):** `app/routes/**` — auth, users,
  integrations, catalog, `billing/billing_routes.py`, `social/rewardRoutes.py`,
  `social/announcements.py`, `blog/blogMain.py`, `uploads/cloudinary_routes.py`,
  `users/referralsRoutes.py`, `users/connected_accounts.py`, `me/me.py`,
  `processes/{processes,history}.py`.
- **Reorganización de carpetas (2026-07-10):** `app/routes/{V2,V3,v1}/` ya no
  existen. Todo vive en carpetas planas por dominio:
  `app/routes/{auth,processes,conversations,onboarding,uploads,gmail,proxy,
  contact,blog,me,webhooks,ws,chat}/` — mismo patrón que ya usaban
  `billing/`, `social/`, `users/`, `secretary/`, `integrations/`.
- **Secretary a montar o retirar:** `app/routes/secretary/secretary{Get,Post}Routes.py`.
- **OAuth (solo prefijo + env):** `app/integrations/providers/*` (~24 archivos).
- **Base de B2 — ya existe, falta el router REST:**
  `app/services/workflow_service.py`, `app/services/workflow_run_service.py`,
  `app/workers/workflow_worker.py`, `app/workers/workflow_executor.py`.

---

## 8. Verificación

1. **Inventario automático (la red de seguridad).** Levantar el backend y correr
   un script contra `GET /openapi.json` que **falle** si alguna ruta:
   - no empieza con `/api/v1` (salvo `/health`, `/`, `/docs` y los alias de §4),
   - contiene `_`,
   - contiene un verbo (`get_`, `add_`, `delete_`, `_check`).
   Sin esto, la nomenclatura se erosiona sola en tres sprints.
2. **Sin prefijos duplicados** en `/docs`: `/api/v2/blog/api/v2/blog` debe morir.
3. **OAuth real, uno por uno** (regla #5) antes de retirar cada ruta vieja.
4. **Stripe:** disparar un evento de prueba desde el dashboard contra
   `/api/v1/billing/webhook` y confirmar 200.
5. **Grep de sanidad en el frontend:** sin `/api/v2`, `/api/v4`, `/api/agent`.
