# 📱 Flujo de Integraciones - HyperShifu

## 📑 Tabla de Contenidos
1. [Descripción General](#descripción-general)
2. [Arquitectura](#arquitectura)
3. [Flujo de Conexión OAuth](#flujo-de-conexión-oauth)
4. [Flujo de Desconexión](#flujo-de-desconexión)
5. [Seguridad](#seguridad)
6. [Proveedores Soportados](#proveedores-soportados)
7. [Modelos de Datos](#modelos-de-datos)

---

## 🎯 Descripción General

El sistema de integraciones permite a los usuarios conectar aplicaciones externas (Gmail, Slack, HubSpot, etc.) de manera segura. Los tokens y credenciales se **encriptan con AES-256** antes de almacenarse en la base de datos.

### Características Principales
- ✅ Autenticación OAuth 2.0
- 🔐 Encriptación de credenciales (AES-256)
- 📊 Auditoría de conexiones (IP, User-Agent)
- 🛑 Kill Switch de seguridad (is_active)
- ⚡ Just-In-Time (JIT) decryption

---

## 🏗️ Arquitectura

```
┌─────────────────────────────────────────────────────────────────┐
│                        FRONTEND (React)                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  1. ConnectApps.tsx (UI Component)                             │
│     ├─ Catalogo de aplicaciones (Gmail, Slack, etc)            │
│     ├─ Grid/List view                                           │
│     └─ Botones: Connect / Disconnect                            │
│                                                                   │
│  2. IntegrationContext.tsx (State Management)                  │
│     ├─ fetchIntegrations() - Lee integraciones del usuario     │
│     ├─ handleSubmit() - Procesa token recibido                │
│     ├─ deleteIntegration() - Elimina una integración          │
│     └─ updateIntegrations() - Sincroniza con API              │
│                                                                   │
│  3. useOAuthCallback.ts (OAuth Hook)                           │
│     ├─ Detecta callback URL                                    │
│     ├─ Extrae código/token de URL                             │
│     └─ Envía a handleSubmit                                    │
│                                                                   │
│  4. oauthConfigs.ts (Configuration)                            │
│     └─ URLs OAuth, ClientIDs, Scopes por proveedor            │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
                              ⬇️ HTTP (Authentication Header)
                         Authorization: Bearer <token>
                              ⬇️
┌─────────────────────────────────────────────────────────────────┐
│                       BACKEND (FastAPI)                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  1. integrationRoutes.py (API Endpoints)                        │
│     ├─ POST /add_integration                                    │
│     ├─ GET /get_integrations                                    │
│     └─ DELETE /delete_integration/{id}                          │
│                                                                   │
│  2. IntegrationService.py (Business Logic)                      │
│     ├─ create_integration() - Crea/actualiza con encriptación │
│     ├─ get_decrypted_credentials() - Lee credenciales JIT      │
│     └─ delete_integration() - Elimina registro                 │
│                                                                   │
│  3. integration.py (Models)                                      │
│     ├─ ProviderType (Enum: Gmail, Slack, HubSpot, Drive)      │
│     ├─ IntegrationPayload (DTO - Input)                        │
│     └─ IntegrationDB (Database Model)                          │
│                                                                   │
│  4. security.py (Encryption)                                     │
│     ├─ encrypt_data() - AES-256                                │
│     └─ decrypt_data() - AES-256                                │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
                              ⬇️
         ┌──────────────────────────────────────┐
         │    MongoDB (integrations collection) │
         │                                      │
         │  {                                   │
         │    user_id: "...",                  │
         │    provider: "gmail",                │
         │    encrypted_credentials: "...",    │
         │    is_active: true,                 │
         │    status: "connected",              │
         │    metadata: {...},                  │
         │    created_at, updated_at            │
         │  }                                   │
         └──────────────────────────────────────┘
```

---

## 🔐 Flujo de Conexión OAuth

### Paso 1: El Usuario Cliquea "Conectar"
```
Usuario abre ConnectApps.tsx y selecciona una app (ej: Gmail)
            ⬇️
        onConnect(app)
```

### Paso 2: Redirección a OAuth Provider
```
Frontend construye URL OAuth usando oauthConfigs:

https://accounts.google.com/o/oauth2/auth?
  client_id=VITE_GMAIL_CLIENT_ID
  redirect_uri=https://hypershifu.com/chat
  scope=gmail.modify,gmail.readonly,...
  response_type=code

Usuario autoriza en página de Google
```

### Paso 3: Callback URL
```
Google redirige a:
https://hypershifu.com/chat?code=AUTHORIZATION_CODE

useOAuthCallback.ts detecta el ?code en URL
                ⬇️
            Extrae el código
                ⬇️
    handleSubmit("Gmail", "AUTHORIZATION_CODE")
```

### Paso 4: Intercambio de Código por Token (Backend)
```
Frontend envía:
POST /api/integrations/add_integration
{
  "email": "usuario@ejemplo.com",
  "integration": "Gmail",
  "token": "AUTHORIZATION_CODE",
  "refresh_token": null,
  "expires_in": 3600
}

Backend procesa:
  1. get_user_from_db(email) - Busca usuario en oauth_vault o usuarios
  2. Valida que el provider sea conocido
  3. Encripta payload con AES-256
  4. Guarda en MongoDB
```

### Paso 5: Almacenamiento Encriptado
```
IntegrationService.create_integration():

1. Convierte payload a JSON
   {
     "access_token": "ya29.a0...",
     "refresh_token": "1//...",
     "expires_in": 3600
   }

2. Encripta con encrypt_data(payload_str)
   ❌ TEXTO PLANO → ✅ AES-256 (Military Grade)
   
3. Guarda documento en MongoDB:
   {
     "_id": ObjectId(...),
     "user_id": "...",
     "provider": "gmail",
     "encrypted_credentials": "<BLOB ENCRIPTADO>",
     "is_active": true,
     "status": "connected",
     "metadata": {
       "last_ip": "192.168.1.1",
       "user_agent": "Mozilla/5.0...",
       "last_handshake": "2026-03-24T10:15:30Z"
     },
     "created_at": "2026-03-24T10:15:30Z",
     "updated_at": "2026-03-24T10:15:30Z"
   }

4. Retorna respuesta al Frontend
```

### Paso 6: Confirmación en Frontend
```
Frontend recibe respuesta exitosa:

IntegrationContext.handleSubmit():
  1. Muestra SweetAlert "¡Integración guardada!"
  2. Llama a fetchIntegrations() para actualizar lista
  3. Cierra modal ConnectApps

fetchIntegrations() hace:
  GET /api/integrations/get_integrations
  Authorization: Bearer <JWT_TOKEN>
  
Backend retorna:
{
  "integrations": {
    "gmail": {
      "id": "...",
      "status": "active",
      "metadata": {...},
      "created_at": "...",
      "updated_at": "..."
    }
  }
}

Frontend actualiza estado:
  setIntegrations({gmail: {...}})
```

---

## 🗑️ Flujo de Desconexión

### Paso 1: Usuario Cliquea "Desconectar"
```
En ConnectApps.tsx:
  onDisconnect(app) → deleteIntegration(integrationName)
```

### Paso 2: Solicitud al Backend
```
DELETE /api/integrations/delete_integration/{integration_id}
Authorization: Bearer <JWT_TOKEN>

Validaciones:
  1. ¿Token válido?
  2. ¿integration_id es ObjectId válido?
  3. ¿El documento existe?
  4. ¿El usuario es propietario?
```

### Paso 3: Eliminación Física
```
db.oauth_vault.delete_one({"_id": ObjectId(integration_id)})

Se elimina completamente el registro de integración
No es soft delete, es eliminación física de los datos
```

### Paso 4: Actualización en Frontend
```
Frontend recibe confirmación

deleteIntegration():
  1. Muestra SweetAlert "Desconectado"
  2. Actualiza estado local
  3. Refresca lista con fetchIntegrations()
```

---

## 🔒 Seguridad

### 1. Encriptación de Credenciales (AES-256)
```python
# En integration_service.py
encrypted_blob = encrypt_data(payload_str)

# En security.py (Pseudocódigo)
def encrypt_data(plaintext: str) -> str:
    """Usa AES-256 en modo GCM"""
    cipher = AES.new(ENCRYPTION_KEY, AES.MODE_GCM)
    ciphertext = cipher.encrypt(plaintext.encode())
    return base64.b64encode(
        cipher.nonce + cipher.tag + ciphertext
    ).decode()
```

### 2. Auditoría de Acceso
```json
{
  "metadata": {
    "last_ip": "192.168.1.100",
    "user_agent": "Mozilla/5.0 (Windows; U; Windows NT 5.1...",
    "updated_by": "system_service",
    "last_handshake": "2026-03-24T10:15:30.123456"
  }
}
```

### 3. Kill Switch (is_active)
```python
# En IntegrationService.get_decrypted_credentials()
if not integration.get("is_active"):
    logger.warning(f" Acceso denegado: Integración DESACTIVADA")
    return None
```

Si sospechas que una integración fue comprometida:
```
db.integrations.update_one(
  {"_id": ObjectId(...)},
  {"$set": {"is_active": false}}
)
```

### 4. Just-In-Time (JIT) Decryption
```
Las credenciales se desencriptan SOLO cuando se necesitan
NO se almacenan en caché sin encriptar
NO se devuelven al frontend
Se usan directamente en el servidor
```

### 5. Validación de Provider
```python
class ProviderType(str, Enum):
    GMAIL = "gmail"
    SLACK = "slack"
    HUBSPOT = "hubspot"
    DRIVE = "drive"

# Solo permite estos proveedores conocidos
provider: ProviderType = Field(...)
```

---

## 📱 Proveedores Soportados

| Provider | Status | OAuth Client | Scopes |
|----------|--------|-------------|--------|
| **Gmail** | ✅ Active | `VITE_GMAIL_CLIENT_ID` | `gmail.modify`, `gmail.readonly`, `userinfo.profile` |
| **Drive** | ✅ Active | `VITE_DRIVE_CLIENT_ID` | `drive.file`, `drive.readonly`, `drive` |
| **Google Docs** | ✅ Active | `VITE_GOOGLE_DOCS_CLIENT_ID` | `documents` |
| **Google Sheets** | ✅ Active | `VITE_GOOGLE_SHEETS_CLIENT_ID` | `spreadsheets` |
| **Google Slides** | ✅ Active | `VITE_GOOGLE_SLIDES_CLIENT_ID` | `presentations` |
| **Slack** | ✅ Active | `VITE_SLACK_CLIENT_ID` | `channels:read`, `chat:write` |
| **Notion** | ✅ Active | `VITE_NOTION_CLIENT_ID` | `read`, `write` |
| **HubSpot** | ✅ Active | `VITE_HUBSPOT_CLIENT_ID` | CRM permisos |
| **Mailchimp** | ✅ Active | `VITE_MAILCHIMP_CLIENT_ID` | Marketing |
| **Jira** | ✅ Active | `VITE_JIRA_CLIENT_ID` | Issue management |
| **Salesforce** | ✅ Active | `VITE_SALESFORCE_CLIENT_ID` | CRM |
| **Teams** | ✅ Active | `VITE_TEAMS_CLIENT_ID` | Chat |
| **Discord** | ✅ Active | `VITE_DISCORD_CLIENT_ID` | Servidores |
| **Asana** | ✅ Active | `VITE_ASANA_CLIENT_ID` | Tareas |
| **Monday** | ✅ Active | `VITE_MONDAY_CLIENT_ID` | Proyectos |
| **ClickUp** | ✅ Active | `VITE_CLICKUP_CLIENT_ID` | Tareas |
| **Dropbox** | ✅ Active | `VITE_DROPBOX_CLIENT_ID` | Almacenamiento |
| **OneDrive** | ✅ Active | `VITE_ONEDRIVE_CLIENT_ID` | Cloud storage |
| **Outlook** | ✅ Active | `VITE_OUTLOOK_CLIENT_ID` | Email |
| **LinkedIn** | ✅ Active | `VITE_LINKEDIN_CLIENT_ID` | Perfil |
| **Facebook** | ✅ Active | `VITE_FACEBOOK_CLIENT_ID` | Social |
| **WhatsApp** | ✅ Active | `VITE_WHATSAPP_CLIENT_ID` | Mensajería |

---

## 💾 Modelos de Datos

### 1. IntegrationPayload (Frontend → API)
```python
class IntegrationPayload(BaseModel):
    """DTO: Datos sensibles en memoria volátil (Input)"""
    access_token: str
    refresh_token: Optional[str] = None
    api_key: Optional[str] = None
    webhook_url: Optional[HttpUrl] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)
```

### 2. IntegrationDB (MongoDB Storage)
```python
class IntegrationDB(BaseModel):
    """ENTIDAD: Modelo de persistencia en MongoDB"""
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    user_id: str  # ID del usuario propietario
    provider: ProviderType  # Enum: gmail, slack, hubspot, drive
    encrypted_credentials: str  # Blob encriptado AES-256
    is_active: bool = True  # Kill Switch
    status: str = "connected"  # Estado de conexión
    metadata: Dict[str, Any]  # Auditoría (IP, User-Agent, etc)
    created_at: datetime  # Timezone-aware UTC
    updated_at: datetime  # Timezone-aware UTC
```

### 3. AddIntegrationRequest (Frontend POST)
```python
class AddIntegrationRequest(BaseModel):
    email: str  # Email del usuario
    integration: str  # Nombre del proveedor
    token: str  # OAuth code o token
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None  # Segundos
```

---

## 📊 Diagrama de Secuencia

```
┌──────────┐              ┌──────────┐           ┌────────┐
│ Frontend │              │  Backend │           │ Google │
└────┬─────┘              └────┬─────┘           └───┬────┘
     │                          │                     │
     │ 1. Click "Connect Gmail" │                     │
     ├─────────────────────────>│                     │
     │                          │                     │
     │ 2. Redirect to OAuth     │                     │
     ├─────────────────────────────────────────────>│
     │                          │                     │
     │                          │ 3. User Authorizes │
     │                          │<────────────────────┤
     │                          │                     │
     │ 4. Callback with code    │                     │
     │<─────────────────────────────────────────────┤
     │                          │                     │
     │ 5. POST /add_integration │                     │
     ├─────────────────────────>│                     │
     │    {email, token, ...}   │                     │
     │                          │                     │
     │                          │ 6. Encrypt payload │
     │                          │ 7. Save to DB      │
     │                          │ 8. Audit metadata  │
     │                          │                     │
     │<─────────────────────────┤                     │
     │   {"status": "connected"}│                     │
     │                          │                     │
     │ 9. GET /get_integrations │                     │
     ├─────────────────────────>│                     │
     │                          │                     │
     │ 10. Return integrations  │                     │
     │<─────────────────────────┤                     │
     │                          │                     │
     │ 11. Update UI            │                     │
     │ Show "Gmail Connected"   │                     │
     │                          │                     │
```

---

## 🔧 Implementación Técnica

### Backend Endpoints

#### POST /add_integration
```bash
curl -X POST http://localhost:8000/api/integrations/add_integration \
  -H "Content-Type: application/json" \
  -d '{
    "email": "usuario@ejemplo.com",
    "integration": "gmail",
    "token": "4/0AY0e-g...",
    "refresh_token": "1//0gxxx...",
    "expires_in": 3600
  }'
```

#### GET /get_integrations
```bash
curl -X GET http://localhost:8000/api/integrations/get_integrations \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..."
```

#### DELETE /delete_integration/{integration_id}
```bash
curl -X DELETE http://localhost:8000/api/integrations/delete_integration/507f1f77bcf86cd799439011 \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..."
```

---

## 🐛 Troubleshooting

### Problema: "Integración no encontrada"
**Causa:** El usuario aún no tiene la integración guardada
**Solución:** Verificar que `fetchIntegrations()` se ejecutó después de conectar

### Problema: "Error al desencriptar credenciales"
**Causa:** Rotación de claves de encriptación
**Solución:** Verificar que `ENCRYPTION_KEY` sea consistente

### Problema: "Acceso denegado: Integración DESACTIVADA"
**Causa:** El kill switch está activado (`is_active=false`)
**Solución:** Re-conectar la integración

### Problema: "Token inválido: user_id ausente"
**Causa:** JWT token no contiene user_id
**Solución:** Verificar que el token JWT sea válido

---

## 📝 Notas Importantes

1. **Encriptación:** Los tokens NUNCA se almacenan en texto plano
2. **Auditoría:** Cada conexión registra IP y User-Agent
3. **Kill Switch:** Las integraciones pueden desactivarse sin eliminar datos
4. **JIT Decryption:** Los tokens se desencriptan solo cuando se usan
5. **Upsert:** Si existe integración del mismo user+provider, se actualiza
6. **Timezone:** Todas las fechas usan UTC con timezone info

