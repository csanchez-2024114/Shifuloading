# Cómo crear las claves del `.env`

Guía paso a paso para llenar `backend/.env`. Los menús de cada sitio cambian con el tiempo: si algo se ve un poco distinto, busca el nombre equivalente.

## Antes de empezar

- Usa la **cuenta de Shifu** para crear todo (la de la página de Accesos del equipo), para que las claves no queden ligadas a una cuenta personal.
- Crea claves **solo para desarrollo**, separadas de las de producción. Si una se filtra, no afecta a la otra.
- Cada clave se muestra **una sola vez** al crearla. Cópiala y pégala directo en `backend/.env`. Si la pierdes, se crea otra y se borra la vieja.
- **Nunca** pegues una clave en un chat, correo, captura o commit. `backend/.env` está ignorado por git y debe seguir así.
- Formato en el `.env`: `NOMBRE=valor`, sin comillas y sin espacios alrededor del `=`.
- Después de cambiar el `.env`, **reinicia la API**: solo lo lee al arrancar.

Las llaves de seguridad (`SECRET_KEY`, `ENCRYPTION_KEY`, `SECRETS_ENCRYPTION_KEY`, `ENCRYPTION_SALT`) no salen de ninguna cuenta: ya se generaron en tu `.env`. Si necesitas unas nuevas:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

La primera sirve para `ENCRYPTION_KEY` y `SECRETS_ENCRYPTION_KEY` (cada una con su propio valor); la segunda para `SECRET_KEY`.

---

## 1. Lo mínimo para arrancar

### OpenAI → `OPENAI_API_KEY` y `CHAT_API_KEY`

El agente de Shifu usa los modelos de OpenAI. **Las dos variables llevan la misma clave.**

1. Entra a https://platform.openai.com con la cuenta de Shifu.
2. Si no hay saldo, ve a **Settings → Billing** y agrega crédito (la API se paga aparte de ChatGPT).
3. Ve a **API keys** (menú lateral o en Settings) → **Create new secret key**.
4. Ponle un nombre claro, por ejemplo `shifu-dev-<tu nombre>`, y créala. Copia la clave (empieza con `sk-`).
5. Pégala en el `.env`:
   ```
   OPENAI_API_KEY=sk-...
   CHAT_API_KEY=sk-...
   ```
6. Recomendado: en **Settings → Billing → Limits** pon un límite mensual bajo para desarrollo.

### Tavily → `TAVILY_API_KEY`

Es el buscador web que usa el agente.

1. Entra a https://app.tavily.com y regístrate o inicia sesión con la cuenta de Shifu.
2. En el panel principal aparece **API Key** (empieza con `tvly-`). Cópiala. Si no hay ninguna, crea una.
3. Pégala:
   ```
   TAVILY_API_KEY=tvly-...
   ```
4. El plan gratuito tiene un cupo mensual de búsquedas, suficiente para desarrollo.

Con estas dos claves (más las llaves de seguridad que ya están) el backend debería arrancar.

---

## 2. Iniciar sesión con Google (opcional)

Para el botón "Continuar con Google". Se crea una vez en Google Cloud y sirve también para el punto 3.

1. Entra a https://console.cloud.google.com con la cuenta de Shifu.
2. Arriba, selector de proyectos → **Proyecto nuevo** → nombre `shifu-dev` → Crear. Selecciónalo.
3. Menú **APIs y servicios → Pantalla de consentimiento de OAuth** (o **Google Auth Platform**):
   - Tipo de usuario: **Externo**.
   - Nombre de la app: `Shifu (desarrollo)`. Correo de asistencia: el de la cuenta de Shifu.
   - Mientras la app esté en modo **Prueba**, agrega en **Usuarios de prueba** los correos que van a probar el inicio de sesión. Solo ellos podrán entrar.
4. **APIs y servicios → Credenciales → Crear credenciales → ID de cliente de OAuth**:
   - Tipo de aplicación: **Aplicación web**.
   - **URIs de redireccionamiento autorizados** (agrega las dos):
     - `http://localhost:5000/api/v1/auth/google/callback` (iniciar sesión)
     - `http://localhost:5000/api/v1/integrations/google/callback` (Gmail, Drive y demás, punto 3)
   - Crear. Copia el **ID de cliente** y el **Secreto de cliente**.
5. En el `.env`:
   ```
   GOOGLE_SIGNIN_CLIENT_ID=...apps.googleusercontent.com
   GOOGLE_SIGNIN_CLIENT_SECRET=GOCSPX-...
   GOOGLE_SIGNIN_REDIRECT_URI=http://localhost:5000/api/v1/auth/google/callback
   ```
   La URI del `.env` debe ser **idéntica, carácter por carácter**, a la registrada en Google (si no, error `redirect_uri_mismatch`).

---

## 3. Gmail, Drive, Docs, Sheets, Slides y Calendar (opcional)

Usan el mismo proyecto de Google Cloud del punto 2.

1. **APIs y servicios → Biblioteca**: busca y **habilita** las que vayas a usar: Gmail API, Google Drive API, Google Docs API, Google Sheets API, Google Slides API, Google Calendar API.
2. Puedes reutilizar el mismo ID de cliente del punto 2 o crear otro igual. El backend lee estas variables:
   ```
   DRIVE_CLIENT_ID=...
   DRIVE_CLIENT_SECRET=...
   GMAIL_CLIENT_ID=...
   GMAIL_CLIENT_SECRET=...
   GOOGLE_REDIRECT_URI=http://localhost:5000/api/v1/integrations/google/callback
   ```
3. Al conectar una app, Google puede avisar que la aplicación "no está verificada". En modo Prueba y con tu correo como usuario de prueba es normal: **Avanzado → Ir a Shifu (no seguro)**.

---

## 4. Otras integraciones (opcional, una por una)

Se hacen igual: crear una "app" en el portal del proveedor, registrar la URL de retorno y copiar el ID y el secreto. Hazlo **solo cuando vayas a probar esa integración**.

| Integración | Dónde se crea | Variables |
|---|---|---|
| Slack | api.slack.com/apps | `SLACK_CLIENT_ID`, `SLACK_CLIENT_SECRET` |
| Notion | notion.so/my-integrations | `NOTION_CLIENT_ID`, `NOTION_CLIENT_SECRET` |
| Asana | app.asana.com/0/my-apps | `ASANA_CLIENT_ID`, `ASANA_CLIENT_SECRET` |
| HubSpot | developers.hubspot.com | `HUBSPOT_CLIENT_ID`, `HUBSPOT_CLIENT_SECRET` |
| Dropbox | dropbox.com/developers/apps | `DROPBOX_CLIENT_ID`, `DROPBOX_CLIENT_SECRET` |
| Outlook / OneDrive / Teams | portal.azure.com → Registros de aplicaciones | `OUTLOOK_*`, `ONEDRIVE_*`, `TEAMS_*` |
| Salesforce | Salesforce → Setup → App Manager | `SALESFORCE_CLIENT_ID`, `SALESFORCE_CLIENT_SECRET` |

La URL de retorno suele ser `http://localhost:5000/api/v1/integrations/<proveedor>/callback`. Algunas integraciones (por ejemplo OneDrive) también piden su propia variable `..._REDIRECT_URI`: confírmalo en `app/integrations/providers/<proveedor>.py`.

---

## 5. Pagos con Stripe (opcional)

Solo si vas a probar planes y cobros.

1. https://dashboard.stripe.com → activa el **modo de prueba** (interruptor "Test mode").
2. **Developers → API keys**: copia la clave secreta de prueba (`sk_test_...`) y la publicable (`pk_test_...`):
   ```
   STRIPE_SECRET_KEY=sk_test_...
   STRIPE_PUBLISHABLE_KEY=pk_test_...
   ```
3. Para los avisos de pago en local, instala el Stripe CLI, ejecuta `stripe listen --forward-to localhost:5000/api/v1/billing/webhook` y copia el `whsec_...` que imprime a `WEBHOOK_SECRET`.
4. **Nunca** uses claves `sk_live_...` en desarrollo.

---

## 6. Comprobar que quedó bien

1. Guarda el `.env` y **reinicia la API** (`uvicorn main:app --reload --port 5000`).
2. Abre http://localhost:5000/docs: si carga, el servidor arrancó.
3. Errores comunes:
   - `Missing ... env var` o `CRITICAL`: falta una variable obligatoria o tiene un espacio o comilla de más.
   - `redirect_uri_mismatch`: la URI del `.env` no coincide exactamente con la de Google Cloud.
   - `invalid_api_key` / `401` de OpenAI: clave mal copiada, borrada o sin saldo.
   - `Access blocked` de Google: tu correo no está en **Usuarios de prueba**.

## 7. Si una clave se filtra

1. Bórrala o **revócala** de inmediato en el portal donde se creó.
2. Crea una nueva y cámbiala en el `.env`.
3. Si llegó a subirse a git, **la clave ya se considera pública** aunque borres el commit: revócala siempre.
