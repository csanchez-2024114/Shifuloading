Perfecto.
A continuación te redacto **la documentación completa del flujo OAuth de tu proyecto**, basada **exclusivamente en el código que me entregaste**.

Tal como pediste, **todo estará envuelto entre** `'''` **al inicio y al final**, para que lo copies como un bloque markdown limpio.

---

'''markdown

# ** Documentación del Flujo OAuth en el Proyecto**

Este documento describe **cómo funciona el flujo OAuth** dentro del frontend del proyecto, específicamente en el componente `IntegrationsProvider`.
Su objetivo es centralizar la lógica de conexión, procesamiento y almacenamiento de tokens OAuth provenientes de distintos proveedores (Google, Microsoft, Meta, Slack, etc.).

---

#  **1. Arquitectura General del Proceso OAuth**

El flujo OAuth en el proyecto sigue siempre la misma secuencia:

1. **El usuario hace clic en “Conectar”** en una integración (Gmail, Slack, etc.).
2. El frontend **redirecciona al usuario al proveedor OAuth** usando las URLs definidas en `oauthConfigs`.
3. Tras aprobar permisos, el proveedor redirige al frontend al `redirect_uri` con un **authorization code**.
4. Ese *authorization code* llega al componente `IntegrationsProvider` y se pasa a:

   ```js
   handleSubmit(integrationName, code)
   ```
5. Según el proveedor, el frontend:

   * **Intercambia el code por tokens** directamente con el proveedor (Google usa axios directamente).
   * O **manda el code al backend** vía un endpoint `*-proxy` que hace el intercambio (Notion, Slack, Meta, Microsoft, etc.).
6. El componente extrae:

   * `access_token`
   * `refresh_token` (si aplica)
   * `expires_in` (si aplica)
7. El frontend guarda estos valores en:

   * **localStorage**
   * **backend** mediante `/add_integration`
8. La integración queda registrada y disponible en el sistema.

---

#  **2. El Contexto: `IntegrationsProvider`**

El archivo crea un contexto React para administrar:

* Integraciones disponibles.
* Tokens procesados.
* Email del usuario.
* Métodos para refrescar y registrar integraciones.

```js
export const IntegrationsProvider = ({ children }) => {
  const [integrations, setIntegrations] = useState({});
  const [userEmail, setUserEmail] = useState("");
  const [processedTokens, setProcessedTokens] = useState(new Set());
```

---

#  **3. Obtención de Integraciones Guardadas**

El método `fetchIntegrations` consulta al backend:

```js
const response = await api.get(`/get_integrations?email=${email}`);
setIntegrations(response.data.integrations || {});
```

---

# 🧩 **4. Método Principal: `handleSubmit(integrationName, token)`**

Este método controla el **100% del flujo OAuth**, independientemente del proveedor.

## ✔ Paso 1: Mostrar loading

Usa SweetAlert2 para mostrar un estado "Procesando integración…".

## ✔ Paso 2: Determinar tipo de proveedor

El método detecta cuál proveedor se está conectando usando:

```js
if (["Gmail", "Drive", ...].includes(integrationName))
```

Luego ejecuta una de estas rutas:

* **Google OAuth 2.0 (Gmail, Drive, Docs, Sheets, Slides):**
  El frontend usa `axios.post("https://oauth2.googleapis.com/token")` directamente.

* **Proveedores con intercambio vía backend:**

  * Notion → `/notion-proxy`
  * ClickUp → `/clickup-proxy`
  * Asana → `/asana-proxy`
  * Dropbox → `/dropbox-proxy`
  * HubSpot → `/hubspot-proxy`
  * Slack → `/slack-proxy`
  * Microsoft (Outlook, OneDrive, Teams) → `/outlook-proxy`, `/onedrive-proxy`, `/teams-proxy`
  * Jira, Salesforce → `/jira-proxy`, `/salesforce-proxy`
  * Meta: Facebook, Instagram, WhatsApp → `/facebook-proxy`, `/instagram-proxy`, `/whatsapp-proxy`
  * LinkedIn, LinkedIn Sales → `/linkedin-proxy`, `/linkedin-sales-proxy`
  * Monday → `/monday-proxy`

## ✔ Paso 3: Intercambiar authorization code → tokens

Dependiendo del proveedor:

* **Google:**
  Directo al endpoint oficial.
* **Microsoft:**
  Requiere **PKCE**, usando `code_verifier` guardado en localStorage.
* **Slack:**
  Requiere `x-www-form-urlencoded`.
* **Meta / LinkedIn:**
  Por backend para proteger el client_secret.
* **Otros:**
  Cada uno tiene un formato de intercambio ligeramente distinto.

## ✔ Paso 4: Guardar tokens localmente

Los resultados se guardan en `localStorage` con nombres consistentes:

```
gmail_access_token
drive_refresh_token
onedrive_expires_at
linkedin_sales_access_token
instagram_refresh_token
...
```

## ✔ Paso 5: Registrar integración en backend

Por último, se envía:

```js
await api.post("/add_integration", {
  email,
  integration: integrationName,
  token: accessToken,
  refresh_token: refreshToken,
  expires_in: expiresIn,
  token_acquisition_time: currentDateTime.toISOString(),
});
```

**El backend se encarga de almacenar y refresh tokens si aplica.**

---

#  **5. Resumen del Flujo OAuth por Tipo de Proveedor**

| Proveedor                          | Intercambio de Token           | Refresh Token | Guardado Local | Uso de Proxy |
| ---------------------------------- | ------------------------------ | ------------- | -------------- | ------------ |
| Google                             | Directo (`axios` → Google API) | Sí            | Sí             | ❌            |
| Microsoft (Outlook/OneDrive/Teams) | Backend                        | Sí            | Sí             | ✔            |
| Notion                             | Backend                        | No            | No             | ✔            |
| ClickUp                            | Backend                        | No            | No             | ✔            |
| Asana                              | Backend                        | Sí            | No             | ✔            |
| Dropbox                            | Backend                        | Sí            | No             | ✔            |
| HubSpot                            | Backend                        | Sí            | No             | ✔            |
| Slack                              | Backend                        | No            | No             | ✔            |
| Discord                            | Backend                        | Sí            | Sí             | ✔            |
| Facebook / IG / WhatsApp           | Backend                        | Sí            | Sí             | ✔            |
| LinkedIn / LinkedIn Sales          | Backend                        | Sí            | Sí             | ✔            |
| Monday                             | Backend                        | No            | Sí             | ✔            |

---

#  **6. Responsabilidades del Frontend**

## ✔ 1. Genera el `authorization_url` usando `oauthConfigs`

## ✔ 2. Recibe el `authorization_code` en el redirect

## ✔ 3. Ejecuta `handleSubmit()`

## ✔ 4. Llama al backend para registrar token

## ✔ 5. Guarda tokens en localStorage cuando aplica

## ✔ 6. Deja contexto listo para el resto de la app

---

#  **7. Responsabilidades del Backend**

* Manejar los endpoints `*-proxy`
* Proteger `client_secret`
* Intercambiar authorization codes por tokens
* Guardar tokens en DB
* Refrescar tokens si aplica
* Exponer `/get_integrations` y `/add_integration`

---

#  **8. Resumen Visual del Flujo OAuth**

```
Usuario → Botón Conectar
   ↓
Proveedor OAuth muestra pantalla de acceso
   ↓
Proveedor redirige con ?code=XXXX
   ↓
handleSubmit(integrationName, code)
   ↓
Intercambio del code → tokens
   ↓
localStorage + backend (/add_integration)
   ↓
Integración registrada y lista para uso
```

---

#  **9. Conclusión**

El `IntegrationsProvider` actúa como **el orquestador central de todo el flujo OAuth**, normalizando la interacción con más de 20 proveedores.
Su diseño permite seguir agregando integraciones sin romper la arquitectura, manteniendo:

* seguridad (secrets nunca están en frontend),
* consistencia,
* extensibilidad,
* trazabilidad del proceso.

---

'''
