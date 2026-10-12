# 📋 Plan de Trabajo: Testing de Integraciones OAuth

**Objetivo:** Probar todas las 33 aplicaciones, verificar cuáles funcionan, cuáles fallan, y documentar el estado de cada una.

---

## 📊 Resumen Ejecutivo

**Total de Aplicaciones:** 33
- **Produktividad:** 8 (Gmail, Drive, Google Docs/Sheets/Slides, OneDrive, Outlook, Notion, Trello)
- **Gestión de Proyectos:** 5 (ClickUp, Asana, Monday, Jira, + 1 no listado)
- **Comunicación:** 5 (Slack, Discord, Teams, Telegram, WhatsApp Business)
- **Redes Sociales:** 7 (Instagram, Facebook, LinkedIn, TikTok, X, Threads, + 1)
- **Marketing/Email:** 3 (Brevo, Mailchimp, + 1)
- **Otros:** 5+ (Dropbox, OnlyFans, Kick, Uber Eats, Pedidos Ya, HubSpot)

**Problemas Identificados (de la tabla de imagen):**
- ❌ Google Docs: No verifica auth, no guarda datos
- ❌ Google Sheets: No verifica auth, no guarda datos
- ❌ Dropbox: No verifica auth, no guarda datos
- ❌ Asana: Falta client_id
- ⚠️ Slack: "no hay credenciales"
- ⚠️ Monday: "invalid_scope"
- ⚠️ Otros: redirect_uri, invalid_request, etc.

---

## 🎯 Fase 1: Preparación (Día 1)

### 1.1 Setup del Entorno
- [ ] Clonar/actualizar repo frontend
- [ ] Verificar que backend esté corriendo y accesible
- [ ] Tener acceso a variables de entorno `.env` en frontend
- [ ] Instalar herramientas: Postman o Insomnia (para probar endpoints)
- [ ] Tener acceso a admin panel MongoDB para ver `user_connected_accounts` collection

### 1.2 Preparar Ambiente de Testing
```bash
# Crear cuenta de test email
# Crear cuentas de test en cada proveedor (si es necesario)
# Notas:
# - Algunas apps requieren credenciales previas (HubSpot, Salesforce)
# - Algunas son gratuitas (Gmail, Slack, Discord)
# - Algunas son freemium (OnlyFans, Stripe, etc.)
```

### 1.3 Documentación de Referencia
Leer estos documentos primero:
- `doc/INTEGRACIONES_FLUJO.md` - Cómo funciona el flujo OAuth
- `doc/HEALTH_CHECK_INTEGRACIONES.md` - Validación de estado
- `doc/HEALTH_CHECK_EJEMPLOS.md` - Ejemplos de requests
- `src/lib/oauthConfigs.ts` - Configuración OAuth del frontend

---

## 📌 Matriz Operativa: Notion

Objetivo de esta tabla: que el dev siga el flujo completo de Notion y confirme que el auth termina guardado en base de datos dentro de `oauth_vault`.

| Paso | Acción del dev | Qué debe pasar en frontend | Request o evento esperado | Validación en backend / BD | Resultado esperado | Si falla, revisar |
|------|----------------|----------------------------|---------------------------|----------------------------|-------------------|-------------------|
| 1 | Verificar configuración previa | La app carga Notion como integración visible | Existe config `notion` en `oauthConfigs.ts` con `clientId`, `redirectUri` y `responseType=code` | No aplica todavía | El botón de Notion se muestra y se puede clickear | `VITE_NOTION_CLIENT_ID`, `VITE_NOTION_CLIENT_SECRET`, `redirectUri` |
| 2 | Click en conectar Notion | El navegador redirige al OAuth de Notion | Request browser a `https://api.notion.com/v1/oauth/authorize` | No aplica todavía | Aparece pantalla de autorización de Notion | URL generada, `client_id`, `redirect_uri`, scopes |
| 3 | Autorizar en Notion | Notion redirige a la app | Vuelta a `https://hypershifu.com/chat?code=...` | No aplica todavía | La URL vuelve con `code` | Si no vuelve, revisar redirect URI en Notion app settings |
| 4 | Confirmar captura del code | El frontend detecta el callback y dispara el guardado | `handleSubmit("Notion", code)` desde el flujo de callback | No aplica todavía | Se abre modal de carga tipo “Guardando integración...” | Hook de callback, parsing del query param `code` |
| 5 | Intercambio code por token | El frontend llama al proxy interno | POST a `/api/proxy/notion-proxy` con `client_id`, `client_secret`, `code`, `redirect_uri`, `grant_type=authorization_code` | Backend proxy responde con `access_token` | El frontend recibe `access_token` válido | Proxy de Notion, secret, body enviado, respuesta del proveedor |
| 6 | Confirmar payload antes de persistir | El frontend arma el guardado final | POST a `/api/integrations/add_integration` con `email`, `integration: "Notion"`, `token: access_token`, `refresh_token: "n/a"` | Backend entra a `add_integration` | El request llega con datos completos | `email` en localStorage, `accessToken` no vacío, nombre exacto de integración |
| 7 | Persistencia en backend | No visible en UI todavía | `add_integration` normaliza provider a `notion`, arma payload y lo encripta | Se ejecuta `db.oauth_vault.update_one(..., upsert=True)` | Documento creado o actualizado con `status: "active"` | `encrypt_data`, colección `oauth_vault`, user lookup por email |
| 8 | Verificar documento en BD | No aplica | No hay request nuevo | Buscar en MongoDB: `db.oauth_vault.find({ provider: "notion", user_id: USER_ID })` | Debe existir `security.encrypted_data`, `provider: notion`, `status: active`, `metadata.email` | Si no existe, revisar errores en `add_integration` o búsqueda de usuario |
| 9 | Refresco del estado en UI | La integración aparece como conectada | GET a `/api/integrations/get_integrations` después del guardado | Backend devuelve `notion` dentro de `integrations` | El estado de Notion queda visible en frontend | `fetchIntegrations`, token JWT, respuesta del endpoint |
| 10 | Validación final funcional | El dev confirma que quedó persistida | GET a `/api/integrations/health_check/notion` | Backend lee el registro y devuelve estado | Al menos debe devolver registro existente; idealmente `active` | Health check, credenciales guardadas, expiración o estado `unknown` |

### Checklist corto de Notion

- [ ] Existe `VITE_NOTION_CLIENT_ID` en frontend
- [ ] Existe `VITE_NOTION_CLIENT_SECRET` en frontend
- [ ] El OAuth devuelve `code` en la URL
- [ ] El proxy `/api/proxy/notion-proxy` devuelve `access_token`
- [ ] `POST /api/integrations/add_integration` responde 200
- [ ] MongoDB contiene documento `provider: notion`
- [ ] El documento tiene `security.encrypted_data`
- [ ] `GET /api/integrations/get_integrations` devuelve Notion
- [ ] `GET /api/integrations/health_check/notion` devuelve estado usable

### Evidencia mínima que debe guardar el dev

| Evidencia | Qué capturar |
|-----------|--------------|
| Frontend | Screenshot de la URL con `code` o del modal de guardado |
| Network | Request y response de `/api/proxy/notion-proxy` |
| Network | Request y response de `/api/integrations/add_integration` |
| MongoDB | Documento de `user_connected_accounts` con `provider: notion` y `security.encrypted_data` |
| API | Response de `/api/integrations/get_integrations` y `/api/integrations/health_check/notion` |

### Definición de éxito para Notion

Notion queda marcada como funcional solo si se cumplen las 4 condiciones:

1. El proveedor devuelve `code` al frontend.
2. El proxy devuelve `access_token` válido.
3. `add_integration` guarda o actualiza el documento en `user_connected_accounts`.
4. La integración reaparece en `get_integrations` y puede verificarse desde health check.

---

## 📋 Fase 2: Plan de Testing por Categoría

### **2.1 GOOGLE SERVICES** (Gmail, Drive, Google Docs/Sheets/Slides)

**Estado Actual:** ⚠️ Parcialmente funcionando (Gmail ok, otros con problemas)

#### Gmail
```
✅ Paso 1: Conectar
   - Click en "Conectar Gmail"
   - Autorizar en Google
   - Verificar que vuelve a la app
   - Debería ir a: https://hypershifu.com/chat?code=XXXXX

✅ Paso 2: Verificar token guardado
   - Backend: GET /api/integrations/get_integrations
   - Debería retornar: {gmail: {status: "active", ...}}
   - MongoDB: db.user_connected_accounts.find({provider: "gmail"})
   - Debería ver documento con encrypted_data

✅ Paso 3: Health Check
   - GET /api/integrations/health_check/gmail
   - Debería retornar: {status: "active", expires_in: XXXX}

✅ Paso 4: Documentar Resultado
   - ✅ FUNCIONA
   - Token guardado correctamente
   - Health check valida token
```

#### Google Docs / Sheets / Slides
```
❌ Problema Identificado: No verifica auth ni guarda datos

🔍 Investigación:
   1. Verificar si tienen clientId en .env
      - VITE_GOOGLE_DOCS_CLIENT_ID=?
      - VITE_GOOGLE_SHEETS_CLIENT_ID=?
      - VITE_GOOGLE_SLIDES_CLIENT_ID=?
   
   2. Revisar oauthConfigs.ts
      - ¿Tienen entry en oauthConfigs?
      - ¿ClientId está correctamente asignado?
   
   3. Verificar IntegrationContext.tsx
      - ¿Haycase para Google Docs/Sheets/Slides?
      - ¿Se mapean correctamente a "google_docs", "google_sheets", "google_slides"?
   
   4. Testear manualmente:
      - Abrir browser console
      - localStorage.setItem('email', 'test@gmail.com')
      - Click Connect en Google Docs
      - ¿Abre URL OAuth?
      - ¿Vuelve con code?
      - ¿Se guarda en BD?

💡 Acción Correctiva:
   - [ ] Confirmar que están en oauthConfigs.ts
   - [ ] Confirmar que IntegrationContext tiene logic para ellas
   - [ ] Si falta, agregar case para mapear correctamente
   - [ ] Re-probar después del fix
```

#### Drive
```
✅ Paso 1-4: Similar a Gmail
   - Debería funcionar igual que Gmail (mismo provider de OAuth)
   - Si Gmail funciona, Drive también debería
```

---

### **2.2 COMUNICACIÓN** (Slack, Discord, Teams, Telegram, WhatsApp)

#### Slack
```
⚠️ Problema: "no hay credenciales"

🔍 Investigación:
   1. ¿Existe VITE_SLACK_CLIENT_ID en .env?
      - Si no existe, agregarlo
   2. ¿Slack tiene entry en oauthConfigs.ts?
      - Verificar URL de OAuth
      - Verificar scopes
   3. ¿Existe entry en apps1.ts catalog?
      - Buscar "Slack" en data
      - Verificar que nameApi sea correcto

🧪 Testing Manual:
   curl -X GET "http://localhost:8000/api/integrations/health_check/slack" \
     -H "Authorization: Bearer TOKEN"
   
   - Retorna: "status": "unknown" o "invalid"?
   - Revisar logs del backend para error specific

💡 Acción Correctiva:
   - [ ] Verificar env vars en .env
   - [ ] Verificar oauthConfigs.ts tiene config correcta
   - [ ] Probar flujo completo
   - [ ] Si sigue fallando, ver logs backend
```

#### Discord
```
✅ Similar a Slack
   - Seguir mismo proceso de validación
   - Verificar VITE_DISCORD_CLIENT_ID
```

#### Teams / Outlook / OneDrive
```
⚠️ Podrían tener conflictos porque comparten Microsoft OAuth
   - Más complejo de testear
   - Podría requerir Azure app registration adicional
   - Considerar como "lower priority" por ahora
```

#### Telegram / WhatsApp Business
```
❌ Probablemente no funcionen
   - Telegram requiere Bot API (no OAuth estándar)
   - WhatsApp requiere WhatsApp Business API
   - No son OAuth 2.0 estándar
   
💡 Acción:
   - [ ] Marcar como "no soportado" o "requiere manual setup"
   - [ ] Documentar en una tabla
```

---

### **2.3 REDES SOCIALES** (Instagram, Facebook, LinkedIn, TikTok, X, Threads)

```
📌 Nota Importante: La mayoría requiere API keys especiales, no OAuth simple

Instagram
   ❌ Requiere Business Account + Meta App
   ⚠️ No es OAuth 2.0 estándar
   💡 Marcar como "WIP" o "Requiere Setup Manual"

Facebook
   ✅ OAuth 2.0 completo
   🧪 Probar como Gmail
   - VITE_FACEBOOK_CLIENT_ID debe estar en .env

LinkedIn
   ✅ OAuth 2.0 completo
   🧪 Probar como Gmail
   - VITE_LINKEDIN_CLIENT_ID debe estar en .env

TikTok / X (Twitter) / Threads
   ⚠️ Requieren API especial y aprobación
   💡 Lower priority - probar solo si otros están 100%
```

---

### **2.4 GESTIÓN DE PROYECTOS** (ClickUp, Asana, Monday, Jira)

#### ClickUp
```
✅ En la tabla dice ✓ app inicializa
✅ En la tabla dice ✓ verifica auth

🧪 Testing:
   - Conectar ClickUp
   - Verificar token guardado
   - GET /api/integrations/health_check/clickup
```

#### Asana
```
❌ En la tabla dice: "invalid_request: The required parameter 'client_id' is missing or invalid"

🔍 Investigación:
   - VITE_ASANA_CLIENT_ID ¿existe en .env?
   - En oauthConfigs.ts, ¿tiene clientId correcto?
   - Verificar documentación oficial Asana OAuth

💡 Acción Correctiva:
   - [ ] Agregar VITE_ASANA_CLIENT_ID a .env
   - [ ] Validar en oauthConfigs.ts
   - [ ] Re-probar
```

#### Monday
```
❌ En la tabla dice: "invalid_scope"

🔍 Investigación:
   - Scopes incorrectos en oauthConfigs.ts
   - Monday tiene scopes específicos que revisar en: 
     https://developer.monday.com/apps/docs/oauth-20-flow

💡 Acción Correctiva:
   - [ ] Revisar scopes requeridos por Monday
   - [ ] Actualizar en oauthConfigs.ts
   - [ ] Re-probar
```

#### Jira
```
✅ Similar a otros servicios OAuth
   - Probar como Gmail
```

---

### **2.5 MARKETING / EMAIL** (Brevo, Mailchimp)

```
✅ Ambas usan OAuth 2.0 estándar
   - Probar como Gmail
   - Verificar VITE_BREVO_CLIENT_ID, VITE_MAILCHIMP_CLIENT_ID en .env
```

---

### **2.6 CRM / NEGOCIO** (HubSpot, Salesforce)

#### HubSpot
```
✅ En la tabla dice "redirect_uri" 
   (en columna de error, pero app inicializa)

🧪 Testing:
   - Conectar HubSpot
   - Verificar token
   - Health check debe validar haciendo llamada a CRM API

✅ Health Check debería:
   GET https://api.hubapi.com/crm/v3/objects/contacts?limit=1
   - Si retorna 200 = token válido
   - Si retorna 401 = token expirado
```

#### Salesforce
```
⚠️ En tabla dice active: false
   - ¿Por qué desactivado?
   - Requiere setup especial: Connected App en Salesforce

💡 Acción:
   - [ ] Decidir si es prioridad
   - [ ] Si sí: Crear Connected App en Salesforce
   - [ ] Si no: Marcar como "Disabled"
```

---

### **2.7 OTROS** (Dropbox, OnlyFans, Kick, Uber Eats, Pedidos Ya, Trello, Notion)

#### Dropbox
```
❌ En tabla: no verifica auth, no guarda datos

🔍 Investigación:
   - ¿Tiene VITE_DROPBOX_CLIENT_ID?
   - ¿Está en oauthConfigs.ts?
```

#### Notion
```
✅ OAuth 2.0 completo
   - Probar completo
```

#### Trello
```
✅ OAuth 2.0 completo
   - Probar completo
```

#### OnlyFans, Kick, Uber Eats, Pedidos Ya
```
⚠️ Requieren setup especial o no pueden integrarse fácilmente
   - OnlyFans: Requiere creator account special
   - Kick: No tiene OAuth público
   - Uber Eats / Pedidos Ya: Requieren business account

💡 Acción:
   - [ ] Decidir si son prioridad
   - [ ] Si no: Marcar como "Requires Manual Setup" o "Disabled"
```

---

## 🧪 Fase 3: Ejecución del Testing (Días 2-5)

### Testing Checklist para CADA aplicación

```markdown
## [APP_NAME]

**Status:** ⬜ TO TEST

### Pre-Testing
- [ ] Env var exists (VITE_[APP_NAME]_CLIENT_ID)
- [ ] In oauthConfigs.ts
- [ ] In apps catalog (data/apps1.ts)
- [ ] In IntegrationContext.tsx (if special handling needed)

### Connection Test
- [ ] Click "Connect [APP_NAME]"
- [ ] OAuth flow starts (redirects to provider)
- [ ] User authorizes
- [ ] Callback URL received
- [ ] Frontend receives token/code

### Backend Storage Test
- [ ] Token stored in oauth_vault collection
- [ ] Data is encrypted (security.encrypted_data exists)
- [ ] User_id is correct
- [ ] Status is "active"

### Health Check Test
- [ ] GET /api/integrations/health_check/[APP_NAME]
- [ ] Returns: {"status": "active", ...}
- [ ] Not: {"status": "unknown", "reason": "..."}

### Final Result
- [ ] ✅ WORKS: Token stored, health check passes
- [ ] ⚠️ PARTIAL: Token stored but health check fails
- [ ] ❌ BROKEN: Cannot connect or token not stored

### Notes
[Describe any issues found]

### Action Required
[ ] None / [ ] Fix env var / [ ] Update config / [ ] Other
```

---

## 📋 Fase 4: Documentación de Resultados (Día 5)

### Crear Tabla de Resultados

```markdown
| App | Active | Env Var | Works | Token Saved | Health Check | Notes | Priority |
|-----|--------|---------|-------|-------------|--------------|-------|----------|
| Gmail | ✅ | ✅ | ✅ | ✅ | ✅ | Working perfectly | HIGH |
| Drive | ✅ | ✅ | ✅ | ✅ | ✅ | Working perfectly | HIGH |
| Google Docs | ✅ | ❌ | ❌ | ❌ | ❌ | Missing client_id | HIGH |
| Slack | ✅ | ❌ | ❌ | ❌ | ❌ | Missing credentials | HIGH |
| ... | | | | | | | |
```

### Generar Reporte Ejecutivo
```
## INTEGRACIONES STATUS REPORT

✅ WORKING (6):
- Gmail
- Drive
- Notion
- Slack
- HubSpot
- Discord

⚠️ PARTIAL (3):
- Google Docs (token saved but no health check)
- Asana (wrong scope)
- Monday (wrong scope)

❌ BROKEN (8):
- Dropbox (no env var)
- OneDrive (microsoft auth issues)
- Teams (microsoft auth issues)
- Telegram (not standard oauth)
- WhatsApp Business (not standard oauth)
- etc.

🔲 NOT TESTED (16):
- OnlyFans (requires special account)
- Kick (no public api)
- etc.
```

---

## 🔧 Acciones Correctivas Comunes

### Problema: "Client ID inválido o falta"
```
✅ Solución:
1. Verificar .env tiene VITE_[APP]_CLIENT_ID=valor_real
2. Verificar en oauthConfigs.ts se usa correctamente
3. Verificar valor en consola: console.log(import.meta.env.VITE_GMAIL_CLIENT_ID)
4. Si está vacío, agregar a .env.local o .env
5. Recargar página completamente
```

### Problema: "Invalid Scope"
```
✅ Solución:
1. Revisar documentación oficial del proveedor para scopes correctos
2. Actualizar en oauthConfigs.ts
3. Ejemplo Monday:
   scope: "me:read boards:read boards:write"
```

### Problema: "Token no se guarda"
```
✅ Solución:
1. Verificar backend está recibiendo token
2. POST /api/integrations/add_integration debe retornar 200
3. Revisar logs backend para error
4. Verificar encryption no está fallando
5. Verificar MongoDB connection
```

### Problema: "Health check retorna unknown"
```
✅ Solución:
1. Verificar token realmente funciona con proveedor
2. Verificar timeout (está configurado a 8-10s)
3. Verificar red tiene acceso a API del proveedor
4. Verificar scopes son correctos
```

---

## 📊 Métricas de Éxito

**Meta:** 80% de integraciones funcionando

| Métrica | Target | Current | Status |
|---------|--------|---------|--------|
| Apps Working | 80% (26/33) | ? | 🔲 TBD |
| All Google OAuth | 100% (5/5) | ? | 🔲 TBD |
| Communication Apps | 80% (4/5) | ? | 🔲 TBD |
| Proj Management | 100% (4/4) | ? | 🔲 TBD |
| CRM/Business | 80% (2/2.5) | ? | 🔲 TBD |

---

## 📝 Deliverables

Al final de este plan, entregar:

1. **Testing Report** (`TESTING_REPORT_2026-03-24.md`)
   - Status de cada aplicación
   - Problemas encontrados
   - Acciones correctivas aplicadas
   - Tabla final de resultados

2. **Broken Apps List** (`BROKEN_APPS.md`)
   - Apps que no funcionan
   - Razón del fallo
   - Recomendación (fix vs disable)

3. **Configuration Updates** (si aplica)
   - .env updates
   - oauthConfigs.ts updates
   - IntegrationContext.tsx updates

4. **Updated docs**
   - INTEGRACIONES_STATUS.md con tabla actualizada
   - PROBLEMAS_ENCONTRADOS.md con soluciones

---

## 🚀 Timeline Sugerido

| Día | Actividad | Duración |
|-----|-----------|----------|
| **Día 1** | Setup + Lectura docs | 2-3 horas |
| **Día 2** | Test Google (5) + Comunicación (5) | 3-4 horas |
| **Día 3** | Test Proyectos (4) + Marketing (2) | 3 horas |
| **Día 4** | Test otros (8) + Troubleshooting | 4 horas |
| **Día 5** | Fix issues encontrados | 4 horas |
| **Día 6** | Documentar resultados | 2 horas |

**Total:** 18-20 horas de work

---

## 🎯 Prioridades

### 🔴 CRITICAL (Test First)
1. Gmail - Google Docs - Google Sheets - Drive (Google suite)
2. Slack - Discord (Communication)
3. HubSpot (CRM)

### 🟠 HIGH (Test Second)
1. OneDrive - Outlook - Teams (Microsoft suite)
2. Notion - Trello (Productivity)
3. ClickUp - Asana - Monday (Project Mgmt)
4. Facebook - LinkedIn (Social)

### 🟡 MEDIUM (Test Third)
1. Mailchimp - Brevo (Marketing)
2. X - TikTok - Threads (Social)
3. Jira - Salesforce (Business)

### 🔵 LOW (Test Last or Skip)
1. Telegram - WhatsApp Business (not standard OAuth)
2. OnlyFans - Kick (special requirements)
3. Uber Eats - Pedidos Ya (delivery only)

---

# Checklist Final

- [ ] Plan leído y entendido
- [ ] Ambiente preparado
- [ ] .env actualizado con valores reales
- [ ] Testing iniciado (Día 1)
- [ ] Resultados documentados diariamente
- [ ] Reporte final completado (Día 6)
- [ ] Issues creados en GitHub para apps rotas
- [ ] PR creado con fixes (si aplica)
