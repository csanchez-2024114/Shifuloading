# 📝 Health Check - Ejemplos de Requests y Respuestas

## 📌 Ejemplos Curl

### 1. Verificar TODAS las integraciones

```bash
curl -X GET "http://localhost:8000/api/integrations/health_check" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json"
```

### 2. Verificar integración específica (Gmail)

```bash
curl -X GET "http://localhost:8000/api/integrations/health_check/gmail" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

### 3. Verificar Slack

```bash
curl -X GET "http://localhost:8000/api/integrations/health_check/slack" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

### 4. Verificar HubSpot

```bash
curl -X GET "http://localhost:8000/api/integrations/health_check/hubspot" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

### 5. Intentar refrescar token

```bash
curl -X POST "http://localhost:8000/api/integrations/refresh_integration/507f1f77bcf86cd799439012" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

---

## 🎯 Ejemplos Axios/Fetch (JavaScript/TypeScript)

### Usando Axios

```typescript
import axios from 'axios';

const token = localStorage.getItem('token');

// Verificar todas las integraciones
async function checkAllIntegrations() {
  try {
    const response = await axios.get(
      'http://localhost:8000/api/integrations/health_check',
      {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      }
    );
    console.log('Health status:', response.data);
    return response.data;
  } catch (error) {
    console.error('Error:', error.response?.data);
  }
}

// Verificar una integración
async function checkSingleIntegration(provider: string) {
  try {
    const response = await axios.get(
      `http://localhost:8000/api/integrations/health_check/${provider}`,
      {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      }
    );
    console.log(`${provider} status:`, response.data);
    return response.data;
  } catch (error) {
    if (error.response?.status === 404) {
      console.log(`${provider} not connected`);
    } else {
      console.error('Error:', error.response?.data);
    }
  }
}

// Usar en React
function IntegrationHealthMonitor() {
  const [health, setHealth] = React.useState(null);

  React.useEffect(() => {
    checkAllIntegrations().then(setHealth);
  }, []);

  return (
    <div>
      <h2>Integration Health</h2>
      {health?.summary?.message && (
        <p style={{
          color: health.summary.all_healthy ? 'green' : 'red'
        }}>
          {health.summary.message}
        </p>
      )}
      
      <ul>
        {Object.entries(health?.integrations || {}).map(([provider, status]) => (
          <li key={provider}>
            {provider}: {status.status}
            {status.reason && ` - ${status.reason}`}
          </li>
        ))}
      </ul>
    </div>
  );
}
```

### Usando Fetch API

```typescript
const token = localStorage.getItem('token');

async function getIntegrationHealth() {
  const response = await fetch(
    'http://localhost:8000/api/integrations/health_check',
    {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      }
    }
  );

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }

  const data = await response.json();
  return data;
}

// Usar
getIntegrationHealth()
  .then(health => {
    console.log('All integrations:', health);
    health.integrations.forEach((integration, provider) => {
      console.log(`${provider}: ${integration.status}`);
    });
  })
  .catch(error => console.error('Error:', error));
```

---

## 📊 Respuesta Completa - Todas las Integraciones (200 OK)

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
      "scope": "https://www.googleapis.com/auth/gmail.modify https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/userinfo.email",
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
    "hubspot": {
      "id": "507f1f77bcf86cd799439014",
      "provider": "hubspot",
      "is_active": true,
      "status": "active",
      "checked_at": "2026-03-24T10:15:30.123456Z",
      "is_recoverable": false,
      "created_at": "2026-03-19T14:15:00Z",
      "last_checked": "2026-03-24T10:15:30Z"
    },
    "notion": {
      "id": "507f1f77bcf86cd799439015",
      "provider": "notion",
      "is_active": true,
      "status": "expired",
      "reason": "Token expirado o inválido",
      "checked_at": "2026-03-24T10:15:30.123456Z",
      "is_recoverable": true,
      "created_at": "2026-03-15T09:00:00Z",
      "last_checked": "2026-03-24T10:15:30Z"
    },
    "monday": {
      "id": "507f1f77bcf86cd799439016",
      "provider": "monday",
      "is_active": true,
      "status": "needs_refresh",
      "expires_in": 120,
      "checked_at": "2026-03-24T10:15:30.123456Z",
      "is_recoverable": true,
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

---

## 🟢 Respuesta: Gmail Activo

```json
{
  "provider": "gmail",
  "status": "active",
  "expires_in": 2589,
  "scope": "https://www.googleapis.com/auth/gmail.modify https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/userinfo.email",
  "checked_at": "2026-03-24T10:15:30.123456Z",
  "is_recoverable": false,
  "is_active": true,
  "created_at": "2026-03-20T08:00:00Z"
}
```

**Interpretación:**
- ✅ Token es válido
- ⏰ Expira en ~43 minutos (2589 segundos)
- 🔄 No necesita refresh
- 👤 Usuario tiene permisos de lectura y escritura en Gmail

---

## 🟡 Respuesta: Gmail Necesita Refresh

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

**Interpretación:**
- ⚠️ Token expirará en ~2 minutos (120 segundos)
- 🔄 Puede recuperarse con refresh_token
- 🔧 Acción recomendada: Refrescar token automáticamente

---

## 🔴 Respuesta: Gmail Expirado

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

**Interpretación:**
- ❌ Token ya no es válido
- 🔄 Tiene refresh_token pero necesita flujo de refresh
- 🔧 Acción recomendada: Reconectar la integración

---

## ❓ Respuesta: Estado Desconocido

```json
{
  "provider": "slack",
  "status": "unknown",
  "reason": "Timeout al conectar con Slack",
  "checked_at": "2026-03-24T10:15:30.123456Z",
  "is_recoverable": true,
  "is_active": true,
  "created_at": "2026-03-18T12:30:00Z"
}
```

**Interpretación:**
- ❓ No se pudo verifi car debido a timeout o error de red
- 🔧 Acción recomendada: Reintentar más tarde

---

## 🔴 Error: Integración No Encontrada

**Status Code: 404**

```json
{
  "detail": "Integración 'telegram' no encontrada para este usuario"
}
```

---

## 🔴 Error: Token JWT Inválido

**Status Code: 401**

```json
{
  "detail": "Token inválido: user_id ausente"
}
```

---

## 🔴 Error: Credenciales Corruptas

**Status Code: 500**

```json
{
  "detail": "Error al verificar: Credenciales corruptas"
}
```

---

## 🎯 Interpretando el Summary

### Caso 1: Todo Saludable ✅

```json
{
  "summary": {
    "all_healthy": true,
    "requires_action": false,
    "healthy_count": 5,
    "problematic_count": 0,
    "checked_at": "2026-03-24T10:15:30Z",
    "message": "✅ Todas las 5 integraciones están activas"
  }
}
```

**Acción:** Ninguna. Mostrar mensaje positivo.

---

### Caso 2: Requiere Atención ⚠️

```json
{
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

**Acciones:**
1. Mostrar notificación destacada
2. Listar las integraciones problemáticas
3. Ofrecer opciones de reconexión
4. Ofre cer refrescar tokens

---

## 🔄 Integración en React Context

```typescript
// IntegrationHealthContext.tsx

import { createContext, useContext, useState, useCallback } from 'react';

const HealthContext = createContext();

export const HealthProvider = ({ children }) => {
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(false);

  const checkHealth = useCallback(async () => {
    setLoading(true);
    try {
      const response = await api.get('/api/integrations/health_check', {
        headers: { Authorization: `Bearer ${token}` }
      });
      setHealth(response.data);
    } catch (error) {
      console.error('Health check error:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  const checkProviderHealth = useCallback(async (provider: string) => {
    try {
      return await api.get(
        `/api/integrations/health_check/${provider}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
    } catch (error) {
      return null;
    }
  }, []);

  return (
    <HealthContext.Provider value={{ health, loading, checkHealth, checkProviderHealth }}>
      {children}
    </HealthContext.Provider>
  );
};

export const useIntegrationHealth = () => useContext(HealthContext);
```

---

## 📊 Tabla de Decisiones para UI

| Estado | Icono | Color | Acción | Botones |
|--------|-------|-------|--------|---------|
| active | ✅ | Verde | Ninguna | Usar, Desconectar |
| needs_refresh | 🔄 | Amarillo | Refrescar | Refrescar, Desconectar |
| expired | ❌ | Rojo | Reconectar | Reconectar |
| unknown | ❓ | Azul | Reintentar | Reintentar, Desconectar |
| disconnected | 🔌 | Gris | Conectar | Conectar |

