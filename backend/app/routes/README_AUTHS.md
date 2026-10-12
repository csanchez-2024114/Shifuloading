# 🔐 Módulo de Integraciones y Autenticación OAuth 2.0 - Hyper Shifu

Este documento detalla la arquitectura técnica, configuración y flujo de datos para las **16 integraciones** de terceros implementadas en la plataforma Hyper Shifu.

## 📋 Tabla de Servicios Soportados

El sistema implementa diferentes patrones de diseño según los requisitos de seguridad de cada proveedor. A continuación, se clasifican las 16 integraciones activas:

### 1. OAuth 2.0 Backend-Redirect (Estándar)
*El frontend redirige al endpoint del backend, este gestiona el intercambio de tokens y guarda en BD.*
* **Jira**
* **Slack**
* **Monday**
* **Notion**
* **Salesforce**
* **Kick**
* **Trello**

### 2. OAuth 2.0 Híbrido con PKCE (Alta Seguridad)
*Requiere generación de `code_challenge` y `code_verifier` para mitigar ataques de intercepción.*
* **TikTok**
* **Twitter (X)**

### 3. Flujo "Stateless" con State Compuesto (Environment Aware)
*Lógica personalizada para prevenir pérdida de sesiones entre entornos de desarrollo y producción.*
* **Uber Eats** (Ver sección detallada abajo)

### 4. OAuth 2.0 con Metadata (Server-Specific)
*Requiere una consulta adicional para determinar el "Data Center" (dc) del usuario.*
* **Mailchimp**

### 5. Widgets y Túneles
* **Telegram:** Utiliza el Widget de Login oficial de Telegram. Requiere **Ngrok** (HTTPS) en el puerto 5173 para renderizar y validar el hash del usuario.
* **Threads:** Requiere redirección segura vía túnel para callbacks en desarrollo.

### 6. Otros Flujos
* **OnlyFans:** Redirección externa (apertura en `_blank`) hacia la plataforma oficial (sin API pública de escritura).
* **Facebook / Instagram:** Configuración Legacy apuntando a URLs de producción.
* **Brevo:** Autenticación directa mediante **API Key** (endpoint `/connect`).

---

## 🏗️ Arquitectura del Sistema

### Frontend (`ServiceView.jsx`)
El componente actúa como despachador de autenticación:
1.  Detecta el servicio seleccionado.
2.  Para servicios **Frontend-First** (ej. Google), maneja el popup y envía el `code` al backend.
3.  Para servicios **Backend-Redirect** (la mayoría de esta lista), redirige al navegador completo hacia:
    `{API_URL}/auth/{servicio}/login?token={user_jwt}`

### Backend (Flask + Blueprints)
Cada servicio tiene su propio controlador en `app/routes/auth_{servicio}.py`.
* **Persistencia:** Los tokens se guardan en MongoDB, colección `users`, bajo el objeto `integrations.{servicio}`.
* **Estrategia Upsert:** Se utiliza `update_one(..., upsert=True)` para crear o actualizar credenciales sin duplicar registros.

---

## 🚀 Integración Especial: Uber Eats

Uber Eats utiliza una arquitectura **Environment Aware** para facilitar el desarrollo sin romper producción.

### Lógica "Stateless"
Para evitar errores de `session_lost` (comunes al saltar entre `localhost` y dominios de Uber), no dependemos de cookies de sesión para recordar al usuario.
* **El Truco:** Empaquetamos el JWT del usuario dentro del parámetro `state` de OAuth (`random_string|user_jwt`).
* **El Resultado:** Uber nos devuelve ese `state` intacto al callback, permitiéndonos identificar al usuario incluso si el navegador borró las cookies.

### Variables de Entorno (`.env`)
Esta integración lee la variable `UBER_ENV` para decidir a qué servidores conectar:

| Variable | Valor | Efecto |
| :--- | :--- | :--- |
| `UBER_ENV` | `SANDBOX` | Usa `sandbox-login.uber.com`. Permite desarrollo sin cobros reales. |
| `UBER_ENV` | `PRODUCTION` | Usa `login.uber.com`. Habilita gestión real de pedidos y tiendas. |

---

## ⚙️ Guía de Configuración (.env)

Para desplegar el módulo de integraciones, configura las siguientes claves en tu archivo `.env`.

### Variables Globales
```env
FRONTEND_REDIRECT_URL=http://localhost:5173/chat  # (O tu dominio en prod)
SECRET_KEY=tu_clave_segura_jwt
MONGO_URI=mongodb+srv://...