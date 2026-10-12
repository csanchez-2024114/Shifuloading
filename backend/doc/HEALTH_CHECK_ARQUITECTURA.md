# 🔧 Health Check - Diagramas y Notas Técnicas

## 📊 Diagrama de Flujo: Verificación de Estado

```
┌─────────────────────────────────────────────────────────────┐
│                   GET /health_check                          │
│          (Verificar estado de TODAS las integraciones)       │
└────────────────────┬────────────────────────────────────────┘
                     │
         ┌───────────▼───────────┐
         │ Validar JWT Token     │
         └───────────┬───────────┘
                     │ ✅ Token válido
         ┌───────────▼────────────┐
         │ Extraer user_id del JWT│
         └───────────┬────────────┘
                     │
    ┌────────────────▼──────────────────┐
    │ Buscar integraciones del usuario   │
    │ db.oauth_vault.find({user_id})    │
    └────────────────┬──────────────────┘
                     │
         ┌───────────▼───────────────┐
         │ ¿Encontró integraciones?  │
         └───────┬─────────────┬─────┘
                 │ NO          │ SÍ
                 │              │
         ┌───────▼──────┐    ┌──▼────────────────────┐
         │ Retornar     │    │ Para cada integración: │
         │ integrations │    │ - Desencriptar datos  │
         │ vacío {}     │    │ - Verificar estado    │
         └──────────────┘    └──┬────────────────────┘
                                │
                        ┌───────▼──────────┐
                        │ Tipo de Provider │
                        └───┬──┬──┬──┬─────┘
                            │  │  │  │
                ┌───────────┘  │  │  └─────────────┐
                │              │  │                 │
         ┌──────▼────┐  ┌─────▼──▼───┐  ┌──────────▼──────┐
         │  Google   │  │   Slack    │  │    HubSpot      │
         │  (Gmail)  │  │            │  │                 │
         └──────┬────┘  └─────┬──────┘  └──────┬─────────┘
                │             │                │
    ┌─────────────────┐ ┌──────────────┐ ┌─────────────┐
    │ Verificar con   │ │ Llamar API   │ │ Llamar API  │
    │ Google TokenInfo│ │ auth.test    │ │ CRM v3      │
    └────────┬────────┘ └────┬─────────┘ └────┬────────┘
             │               │                 │
         ┌───▼──────────┬────▼──────────┬──────▼──────┐
         │ expires_in   │ org_id        │ status code │
         │ scope        │ user_id       │             │
         │ error code   │ team_id       │             │
         │              │ ok flag       │             │
         └───┬──────────┴────┬──────────┴──────┬──────┘
             │               │                 │
       ┌─────▼──────┬────────▼──────┬──────────▼────┐
       │ Comparar   │ Comparar      │ Verificar     │
       │ expira con │ timestamp     │ autorización  │
       │ 300s (5min)│ y estado      │               │
       └─────┬──────┴────┬──────────┴──────┬────────┘
             │           │                 │
       ┌─────▼──────────────────────────────▼───┐
       │ Asignar status:                         │
       │ - active        (vigente)              │
       │ - expired       (expirado)             │
       │ - needs_refresh (próximo a expirar)    │
       │ - unknown       (no se pudo verificar)│
       └─────┬──────────────────────────────────┘
             │
   ┌─────────▼──────────────┐
   │ Actualizar last_checked│
   │ db.oauth_vault:        │
   │ update_one({...},      │
   │  {$set: {...}})        │
   └─────────┬──────────────┘
             │
       ┌─────▼────────────────────────┐
       │ Generar resumen aggregado:   │
       │ - healthy_count              │
       │ - problematic_count          │
       │ - all_healthy flag           │
       │ - requires_action flag       │
       │ - mensaje legible            │
       └─────────┬────────────────────┘
               │
         ┌─────▼──────────────┐
         │ Retornar respuesta│
         │ (200 OK)          │
         └──────────────────┘
```

---

## 🔐 Diagrama de Flujo: Seguridad y Encriptación

```
┌──────────────────────────────────────────────────────┐
│             GET /health_check/{provider}             │
│    (Verificar estado de UNA integración específica)  │
└────────────────────┬─────────────────────────────────┘
                     │
         ┌───────────▼──────────────┐
         │ 1. Validar JWT Token     │
         │    (Bearer token)        │
         └───────────┬──────────────┘
                     │ ✅ Token válido
         ┌───────────▼──────────────┐
         │ 2. Extraer user_id       │
         │    del JWT payload       │
         └───────────┬──────────────┘
                     │
         ┌───────────▼─────────────────────┐
         │ 3. Validar provider parameter   │
         │    (provider.lower())           │
         └───────────┬─────────────────────┘
                     │
    ┌────────────────▼────────────────────┐
    │ 4. Buscar integración:              │
    │    db.oauth_vault.find_one({        │
    │      user_id: user_id,              │
    │      provider: provider_lower       │
    │    })                               │
    └────────────────┬────────────────────┘
                     │
            ┌────────▼────────┐
            │ ¿Encontrada?   │
            └────┬────────┬───┘
                 │ NO     │ SÍ
                 │        │
         ┌───────▼──┐  ┌──▼──────────────────────┐
         │ Retornar │  │ 5. Obtener credenciales │
         │ 404      │  │    encrypted_data       │
         │ Not Found│  └──┬─────────────────────┘
         └──────────┘     │
                    ┌─────▼───────────────────────────┐
                    │ 6. Desencriptar con decrypt_data│
                    │    (AES-256)                    │
                    │    En memoria volátil (RAM)     │
                    └─────┬───────────────────────────┘
                          │
                    ┌─────▼─────────────────┐
                    │ 7. Parsear JSON       │
                    │    {access_token,     │
                    │     refresh_token,    │
                    │     expires_in, ...}  │
                    └─────┬─────────────────┘
                          │
              ┌───────────▼────────────────┐
              │ 8. Llamar a verificador   │
              │    específico del         │
              │    provider               │
              └───────────┬────────────────┘
                          │
              ┌───────────▼──────────────────┐
              │ 9. Obtener respuesta de API  │
              │    (Token info, auth.test,   │
              │    CRM API, etc)             │
              └───────────┬──────────────────┘
                          │
              ┌───────────▼──────────────────┐
              │ 10. Construir response dict  │
              │     status, expires_in,      │
              │     reason (si error), etc   │
              └───────────┬──────────────────┘
                          │
              ┌───────────▼────────────────┐
              │ 11. Actualizar last_checked│
              │     db.oauth_vault:        │
              │     update_one({...}, {    │
              │       $set: {              │
              │         last_checked: now  │
              │       }                    │
              │     })                     │
              └───────────┬────────────────┘
                          │
                    ┌─────▼──────────────┐
                    │ 12. Retornar JSON  │
                    │     (200 OK)       │
                    │                    │
                    │ ❌ NUNCA retornar  │
                    │    tokens en claro │
                    └────────────────────┘
```

---

## 🔄 Diagrama de Flujo: Verificación de Google

```
┌─────────────────────────────────────────┐
│  check_gmail_health(credentials, timeout)│
└────────────────┬────────────────────────┘
                 │
       ┌─────────▼──────────┐
       │ Obtener access_token│
       │ de credenciales    │
       └─────────┬──────────┘
                 │
       ┌─────────▼─────────────────┐
       │ ¿access_token existe?      │
       └────┬──────────────┬────────┘
            │ NO           │ SÍ
            │              │
      ┌─────▼────┐    ┌────▼────────────────────┐
      │ Retornar │    │ Llamar a Google API:   │
      │ status:  │    │ GET /oauth2/v1/        │
      │ INVALID  │    │   tokeninfo?           │
      └──────────┘    │   access_token=TOKEN   │
                      └────┬───────────────────┘
                           │
                    ┌──────▼──────────┐
                    │ Enviar request  │
                    │ timeout=10s     │
                    └──────┬──────────┘
                           │
                      ┌────▼───────────────────┐
                      │ Esperar respuesta      │
                      └────┬──────────┬────────┘
                           │          │
                    ┌──────▼──┐  ┌────▼────────────────┐
                    │TIMEOUT? │  │ Respuesta recibida │
                    └────┬────┘  └────┬────────────────┘
                         │           │
                    ┌────▼────┐  ┌────▼──────────────┐
                    │Retornar:│  │ HTTP Status?     │
                    │status:  │  └────┬───┬──────┬──┘
                    │UNKNOWN ()│       │   │      │
                    │reason:  │  ┌────▼┐ │  ┌───▼────┐
                    │Timeout  │  │ 200 │ │  │  400   │
                    └─────────┘  └──┬──┘ │  └───┬────┘
                                     │   │      │
                          ┌──────────▼┐  │  ┌───▼────────┐
                          │ JSON:    │  │  │ Error:     │
                          │expires_in│  │  │Token       │
                          │scope     │  │  │expirado    │
                          │...       │  │  └───┬────────┘
                          └──┬───────┘  │      │
                             │          │  ┌───▼─────────┐
                          ┌──▼──────────▼─▼──┐            │
                          │ Comparar con 300s│  ┌─────────▼───────┐
                          │ (5 minutos)      │  │ Retornar:       │
                          └──┬──────┬────────┘  │ status:EXPIRED  │
                             │      │          │ reason: Token   │
                          ┌──▼──┐┌──▼──┐      │ expirado/invalid│
                          │>300?││>0?  │      └─────────────────┘
                          └──┬──┘└──┬──┘
                             │ YES │ YES
                          ┌──▼─────▼──────────┐
                          │ Retornar enum:    │
                          │ ACTIVE            │
                          │ NEEDS_REFRESH     │
                          └───────────────────┘
```

---

## 📁 Estructura de Archivos Creados

```
backend-hyper-shifu/
├── app/
│   ├── services/
│   │   ├── integration_health_check.py      ← ⭐ NUEVO
│   │   │   ├── IntegrationHealthStatus
│   │   │   ├── IntegrationHealthChecker
│   │   │   ├── check_gmail_health()
│   │   │   ├── check_slack_health()
│   │   │   ├── check_hubspot_health()
│   │   │   ├── check_generic_expiry()
│   │   │   └── get_all_integrations_health()
│   │   │
│   │   └── integration_service.py           ← Existente
│   │
│   ├── routes/
│   │   └── integrationRoutes.py             ← ACTUALIZADO
│   │       ├── GET /get_integrations        (existente)
│   │       ├── POST /add_integration        (existente)
│   │       ├── DELETE /delete_integration   (existente)
│   │       ├── GET /health_check            ← ⭐ NUEVO
│   │       ├── GET /health_check/{provider} ← ⭐ NUEVO
│   │       └── POST /refresh_integration    ← ⭐ NUEVO (stub)
│
├── doc/
│   ├── INTEGRACIONES_FLUJO.md               ← Existente
│   ├── HEALTH_CHECK_INTEGRACIONES.md        ← ⭐ NUEVO
│   ├── HEALTH_CHECK_EJEMPLOS.md             ← ⭐ NUEVO
│   └── HEALTH_CHECK_ARQUITECTURA.md         ← ⭐ NUEVO (este)
```

---

## ⚙️ Configuración Requerida

### Dependencias Python
```bash
pip install aiohttp>=3.8.0
```

### Variables de Entorno (si usa en futuro refresh)
```env
GOOGLE_CLIENT_ID=xxxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=xxxxx
SLACK_CLIENT_ID=xxxxx
SLACK_CLIENT_SECRET=xxxxx
```

### Archivo de Requerimientos
```
# En requirements.txt, agregar:
aiohttp>=3.8.0
motor>=3.0.0  # Para MongoDB async
```

---

## 🔌 Integración con FastAPI

El endpoint está registrado en `integrationRoutes.py` y debe estar incluido en `main.py`:

```python
# main.py
from app.routes.integrationRoutes import router

app.include_router(router, prefix="/api/integrations", tags=["integrations"])
```

---

## 🧠 Lógica de Estados

### Active (✅)
```
Condición:
- Status HTTP: 200
- Token válido en API
- expires_in > 300s (5 minutos)

Acción UI: Nada. Token está vigente.
```

### Needs Refresh (🔄)
```
Condición:
- Status HTTP: 200
- Token válido en API
- 0 < expires_in <= 300s

Acción UI: Mostrar advertencia, ofrecer refrescar.
```

### Expired (❌)
```
Condición:
- API devuelve 401/400
- O: expires_in <= 0
- O: Token rechazado por proveedor

Acción UI: Mostrar error, ofrecer reconectar.
```

### Unknown (❓)
```
Condición:
- Timeout en conexión
- Error de red
- Excepción no controlada
- Proveedor sin endpoint de verificación

Acción UI: Mostrar alerta, reintentar después.
```

---

## 🚨 Gestión de Errores

### Manejo de Excepciones por Nivel

```python
# Nivel 1: Autenticación JWT
try:
    user = get_current_user(token)
except Exception:
    raise HTTPException(401, "Unauthorized")

# Nivel 2: Búsqueda en BD
try:
    integration = await db.oauth_vault.find_one(...)
except Exception:
    raise HTTPException(500, "Database error")

# Nivel 3: Desencriptación
try:
    credentials = decrypt_data(encrypted_blob)
except Exception:
    return IntegrationHealthStatus.UNKNOWN

# Nivel 4: Verificación con API
try:
    async with session.get(url, timeout=timeout) as response:
        ...
except asyncio.TimeoutError:
    return IntegrationHealthStatus.UNKNOWN
except Exception:
    return IntegrationHealthStatus.UNKNOWN
```

---

## 📈 Métricas Capturadas

Cada verificación registra:
```
- user_id
- provider
- status (active/expired/unknown/etc)
- duration (tiempo de verificación)
- checked_at (timestamp UTC)
- last_checked (actualizado en BD)
- is_recoverable
- reason (si aplica)
```

---

## 🔄 Flujo de Refresh (Futuro)

```
POST /refresh_integration/{integration_id}
│
├─ Validar JWT
├─ Buscar integración
├─ Desencriptar credentials
│
├─ Por proveedor:
│  ├─ Google:
│  │  POST https://oauth2.googleapis.com/token
│  │  {client_id, client_secret, refresh_token, grant_type}
│  │
│  ├─ Slack:
│  │  (Slack rotates tokens automáticamente - no requiere refresh)
│  │
│  └─ Otros:
│     (Implementar según proveedor)
│
├─ Actualizar credentials con nuevo access_token
├─ Encriptar nuevamente
├─ Guardar en BD
└─ Retornar respuesta success
```

---

## ✅ Checklist de Pruebas

- [ ] `GET /health_check` retorna 200 con todas las integraciones
- [ ] `GET /health_check/gmail` detects token válido
- [ ] `GET /health_check/gmail` detects token expirado
- [ ] `GET /health_check/{invalid}` retorna 404
- [ ] Sin Bearer token retorna 401
- [ ] Desencriptación funciona correctamente
- [ ] `last_checked` se actualiza después de cada verificación
- [ ] Summary message es legible y correcto
- [ ] Timeout no bloquea other requests
- [ ] Logging captura eventos importantes

---

## 🔐 Consideraciones de Seguridad

1. **Nunca retornar tokens**: Las respuestas NUNCA incluyen access_token o refresh_token
2. **Desencriptación JIT**: Se desencripta en memoria solo cuando se necesita
3. **Autenticación JWT**: Cada endpoint requiere bearer token válido
4. **Validación de Proveedor**: Solo permite proveedores conocidos
5. **Auditoría**: `last_checked` permite tracking de acceso
6. **Timeout**: Previene DOS mediante timeout en requests
7. **Error Handling**: No expone detalles internos en errores

---

## 📝 Logs Esperados

```
INFO: Checking health for user 507f1f77bcf86cd799439011
DEBUG: Found 5 integrations
DEBUG: Checking gmail - calling Google API
INFO: Gmail token valid, expires_in=2589
DEBUG: Checking slack - calling Slack API
INFO: Slack token valid, org_id=T5555XXXX
DEBUG: Checking notion - local expiry check
WARNING: Notion token expires in 120 seconds
ERROR: HubSpot check failed - timeout
DEBUG: Updated last_checked for all integrations
INFO: Health check completed, healthy=3, problematic=2
```

