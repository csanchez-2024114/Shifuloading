# 🏥 Health Check de Integraciones - Documentación

## 📋 Descripción General

El **Health Check** es un nuevo sistema que verifica el estado en tiempo real de cada integración OAuth conectada. Detalla cuales están activas, cuales han expirado, y cuales necesitan actualización.

### ¿Qué Hace?
- ✅ Valida tokens con los proveedores (Gmail, Slack, HubSpot, etc)
- ⏰ Detecta tokens próximos a expirar
- ❌ Identifica credenciales expiradas
- 🔄 Indica cuales pueden recuperarse con `refresh_token`
- 📊 Proporciona un resumen aggregado de salud

---

## 🚀 Endpoints Disponibles

### 1. GET `/api/integrations/health_check` - Verificar TODAS las integraciones

**Descripción:** Verifica el estado de TODAS las integraciones del usuario autenticado.

**Autenticación:** Bearer Token (JWT)

**Ejemplo de solicitud:**
```bash
curl -X GET "http://localhost:8000/api/integrations/health_check" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

**Respuesta exitosa (200):**
```json
{
  "user_id": "507f1f77bcf86cd799439011",
  "total_integrations": 5,
  "status_counts": {
    "active": 3,
    "expired": 1,
    "invalid": 0,
    "needs_refresh": 1,
    "unknown": 0,
    "disconnected": 0
  },
  "integrations": {
    "gmail": {
      "id": "507f1f77bcf86cd799439012",
      "provider": "gmail",
      "is_active": true,
      "status": "active",
      "expires_in": 2589,
      "scope": "openid email profile https://www.googleapis.com/auth/gmail.modify",
      "checked_at": "2026-03-24T10:15:30.123456Z",
      "is_recoverable": false,
      "created_at": "2026-03-20T08:00:00Z",
      "last_checked": "2026-03-24T10:15:30Z"
    },
    "slack": {
      "id": "507f1f77bcf86cd799439013",
      "provider": "slack",
      "is_active": true,
      "status": "active",
      "org_id": "T5555XXXX",
      "user_id": "U5555XXXX",
      "team_id": "T5555XXXX",
      "checked_at": "2026-03-24T10:15:30.123456Z",
      "is_recoverable": false,
      "created_at": "2026-03-18T12:30:00Z",
      "last_checked": "2026-03-24T10:15:30Z"
    },
    "notion": {
      "id": "507f1f77bcf86cd799439014",
      "provider": "notion",
      "is_active": true,
      "status": "expired",
      "reason": "Token expirado o inválido",
      "checked_at": "2026-03-24T10:15:30.123456Z",
      "is_recoverable": true,
      "created_at": "2026-03-15T09:00:00Z",
      "last_checked": "2026-03-24T10:15:30Z"
    },
    "hubspot": {
      "id": "507f1f77bcf86cd799439015",
      "provider": "hubspot",
      "is_active": true,
      "status": "needs_refresh",
      "expires_in": 120,
      "checked_at": "2026-03-24T10:15:30.123456Z",
      "is_recoverable": true,
      "created_at": "2026-03-10T14:45:00Z",
      "last_checked": "2026-03-24T10:15:30Z"
    },
    "monday": {
      "id": "507f1f77bcf86cd799439016",
      "provider": "monday",
      "is_active": true,
      "status": "active",
      "message": "Sin expiración conocida",
      "checked_at": "2026-03-24T10:15:30.123456Z",
      "created_at": "2026-03-22T11:20:00Z",
      "last_checked": "2026-03-24T10:15:30Z"
    }
  },
  "summary": {
    "all_healthy": false,
    "requires_action": true,
    "healthy_count": 3,
    "problematic_count": 2,
    "checked_at": "2026-03-24T10:15:30Z",
    "message": "✅ 3 activas | ❌ 1 expirada | 🔄 1 necesita refresh"
  }
}
```

**Códigos de estado:**
- `200` - Verified successfully
- `401` - Token JWT inválido
- `500` - Error del servidor

---

### 2. GET `/api/integrations/health_check/{provider}` - Verificar UNA integración

**Descripción:** Verifica el estado de un único proveedor específico.

**Parámetros:**
- `provider` (path): Nombre de proveedor (gmail, slack, hubspot, notion, etc)

**Ejemplo de solicitud:**
```bash
curl -X GET "http://localhost:8000/api/integrations/health_check/gmail" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

**Respuesta exitosa (200) - Token válido:**
```json
{
  "provider": "gmail",
  "status": "active",
  "expires_in": 2589,
  "scope": "openid email profile https://www.googleapis.com/auth/gmail.modify",
  "checked_at": "2026-03-24T10:15:30.123456Z",
  "is_recoverable": false,
  "is_active": true,
  "created_at": "2026-03-20T08:00:00Z"
}
```

**Respuesta exitosa (200) - Token expirado:**
```json
{
  "provider": "gmail",
  "status": "expired",
  "reason": "Token expirado o inválido",
  "checked_at": "2026-03-24T10:15:30.123456Z",
  "is_recoverable": true,
  "is_active": true,
  "created_at": "2026-03-20T08:00:00Z"
}
```

**Respuesta exitosa (200) - Necesita refresh:**
```json
{
  "provider": "gmail",
  "status": "needs_refresh",
  "expires_in": 120,
  "checked_at": "2026-03-24T10:15:30.123456Z",
  "is_recoverable": true,
  "is_active": true,
  "created_at": "2026-03-20T08:00:00Z"
}
```

**Códigos de estado:**
- `200` - Checked successfully
- `401` - Token JWT inválido
- `404` - Integración no encontrada
- `500` - Error del servidor

---

### 3. POST `/api/integrations/refresh_integration/{integration_id}` - Intentar refrescar

**Descripción:** Intenta refrescar un token expirado usando el `refresh_token`. (Estado: En desarrollo)

**Parámetros:**
- `integration_id` (path): ID de MongoDB de la integración

**Ejemplo de solicitud:**
```bash
curl -X POST "http://localhost:8000/api/integrations/refresh_integration/507f1f77bcf86cd799439012" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

**Respuesta (actual - no implementado aún):**
```json
{
  "success": false,
  "provider": "gmail",
  "message": "El sistema aún no implementa refresh automático. Por favor, reconecta la integración.",
  "recommendation": "DELETE el integración actual y conecta nuevamente"
}
```

---

## 📊 Estados de Integración

| Estado | Icono | Significado | Acción Requerida |
|--------|-------|-------------|------------------|
| **active** | ✅ | Token vigente y válido | Ninguna |
| **expired** | ❌ | Token expirado | Reconectar integración |
| **needs_refresh** | 🔄 | Token próximo a expirar | Refrescar o reconectar |
| **invalid** | ❌ | Token rechazado por proveedor | Reconectar integración |
| **unknown** | ❓ | No se pudo verificar | Reintentar más tarde |
| **disconnected** | 🔌 | Inactivo | Activar nuevamente |

---

## 🔍 Detalles de Verificación por Proveedor

### Google Services (Gmail, Drive, Sheets, Docs, Slides)
```
Método: Google TokenInfo API
GET https://www.googleapis.com/oauth2/v1/tokeninfo?access_token=TOKEN

- Valida token en vivo con Google
- Obtiene tiempo restante (expires_in)
- Obtiene scopes asignados
- Detecta automáticamente expiración
- Timeout: 10 segundos
```

### Slack
```
Método: Slack auth.test API
GET https://slack.com/api/auth.test
Header: Authorization: Bearer TOKEN

- Valida token en vivo con Slack
- Obtiene IDs de workspace y usuario
- Detecta tokens revocados
- Timeout: 8 segundos
```

### HubSpot
```
Método: HubSpot CRM API
GET https://api.hubapi.com/crm/v3/objects/contacts?limit=1
Header: Authorization: Bearer TOKEN

- Valida token accediendo a API
- Detecta tokens no autorizados
- Timeout: 8 segundos
```

### Otros Proveedores
```
Método: Verificación Local de Expiración
- Calcula tiempo restante basado en: created_at + expires_in
- Si no hay expiración conocida, asume que es vigente
- Retorna is_recoverable basado en presence de refresh_token
```

---

## 💾 Estructura de Respuesta Detallada

### Propiedades Comunes (Todas las integraciones)
```json
{
  "provider": "string",              // Nombre del proveedor
  "status": "active|expired|...",    // Estado actual
  "checked_at": "ISO8601 datetime",  // Cuándo se verificó
  "is_active": "boolean",            // Está activada en BD
  "is_recoverable": "boolean",       // Puede recuperarse con refresh
  "created_at": "ISO8601 datetime"   // Cuándo se conectó
}
```

### Propiedades Specificas de Google
```json
{
  "expires_in": 3600,                // Segundos hasta expiración
  "scope": "space-separated scopes"  // Permisos otorgados
}
```

### Propiedades Specificas de Slack
```json
{
  "org_id": "T5555XXXX",             // ID de la organización
  "user_id": "U5555XXXX",            // ID del usuario
  "team_id": "T5555XXXX"             // ID del equipo
}
```

### Propiedades de Error
```json
{
  "reason": "string",                // Descripción del error
  "message": "string"                // Mensaje legible
}
```

---

## 🔐 Seguridad

### Principios Implementados
1. **Autenticación**: Requiere JWT Bearer token válido
2. **Autorización**: Solo ve integraciones del usuario autenticado
3. **Encriptación**: Las credenciales se desencriptan bajo demanda
4. **Auditoría**: Registra `last_checked` en cada verificación
5. **JIT Access**: Credenciales se desencriptan en memoria solo para verificar

### Flujo de Seguridad
```
1. Frontend envía JWT en header
2. Backend valida JWT
3. Extrae user_id del JWT
4. Busca integraciones del usuario
5. Desencripta credenciales (AES-256)
6. Verifica con API externa
7. Encrípta nuevamente antes de guardar
8. Retorna estado SIN retornar tokens
```

---

## 📱 Casos de Uso en Frontend

### Caso 1: Mostrar Estado de Integraciones

```typescript
// React Component
const IntegrationStatus = () => {
  const [health, setHealth] = useState(null);

  useEffect(() => {
    const fetchHealth = async () => {
      const response = await api.get("/api/integrations/health_check", {
        headers: { Authorization: `Bearer ${token}` }
      });
      setHealth(response.data);
    };
    fetchHealth();
  }, []);

  if (health?.summary?.requires_action) {
    return <Alert message={health.summary.message} />;
  }

  return (
    <div>
      {Object.entries(health?.integrations || {}).map(([provider, status]) => (
        <IntegrationCard
          key={provider}
          provider={provider}
          status={status.status}
          message={status.reason}
        />
      ))}
    </div>
  );
};
```

### Caso 2: Verificar Integración Específica

```typescript
// Antes de usar una integración
const checkAndUse = async (provider: string) => {
  const response = await api.get(
    `/api/integrations/health_check/${provider}`,
    { headers: { Authorization: `Bearer ${token}` } }
  );

  if (response.data.status === "active") {
    // Usar la integración
    useIntegrationService(provider);
  } else if (response.data.status === "expired") {
    // Mostrar modal para reconectar
    showReconnectDialog(provider);
  }
};
```

### Caso 3: Dashboard de Salud

```typescript
// Mostrar dashboard con todas las integraciones
const HealthDashboard = () => {
  const [health, setHealth] = useState(null);

  useEffect(() => {
    const interval = setInterval(
      async () => {
        const response = await api.get("/api/integrations/health_check", {
          headers: { Authorization: `Bearer ${token}` }
        });
        setHealth(response.data);
      },
      300000  // Actualizar cada 5 minutos
    );
    return () => clearInterval(interval);
  }, []);

  return (
    <Dashboard>
      <SummaryCard
        title="Estado General"
        message={health?.summary?.message}
        allHealthy={health?.summary?.all_healthy}
      />
      
      <IntegrationsList
        integrations={health?.integrations}
        onReconnect={handleReconnect}
      />
    </Dashboard>
  );
};
```

---

## 🛠️ Implementación de Refresh Token (Futuro)

Cuando se implemente el refresh automático, el endpoint `POST /refresh_integration/{id}` hará:

```python
# Pseudocódigo
async def refresh_gmail_token(refresh_token):
    """Intercambia refresh_token por nuevo access_token"""
    response = await requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        }
    )
    return response.json()["access_token"]
```

---

## 📝 Logging y Debugging

El sistema registra eventos en `security.integration` logger:

```
DEBUG: Checking health for gmail
INFO: Gmail token valid, expires_in=2589
WARNING: Slack token needs refresh in 120 seconds
ERROR: HubSpot API returned 401 Unauthorized
```

Paraconsultar logs:
```bash
docker logs -f backend | grep "integration.health"
```

---

## 🔧 Instalación de Dependencias

Asegúrate de tener `aiohttp` instalado:

```bash
pip install aiohttp>=3.8.0
```

---

## 📊 Métricas y Monitoreo

El sistema actualiza `last_checked` en cada verificación para tracking:

```python
# Cada integración tiene:
{
  "provider": "gmail",
  "created_at": "2026-03-20T08:00:00Z",
  "last_checked": "2026-03-24T10:15:30Z",  # ← Actualizado
  "status": "active"
}
```

---

## ⚠️ Limitaciones Actuales

1. **Sin Refresh Automático**: El endpoint `/refresh_integration` aún no implementa OAuth refresh
2. **Sin Cache**: Cada solicitud verifica en vivo (puede ser lento)
3. **Timeout Fixed**: No es configurable por proveedor
4. **Sin Notificaciones**: No envía alertas cuando expiran tokens

---

## 🚀 Plan de Mejoras

- [ ] Implementar caching de verificaciones (5 min TTL)
- [ ] Agregar refresh automático de tokens
- [ ] Enviar notificaciones por email cuando expira token
- [ ] Background job para verificar salud periódicamente  
- [ ] Endpoint para obtener métricas agregadas
- [ ] Dashboard en UI con estado visual

