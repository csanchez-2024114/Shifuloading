🌌 HyperShifu Backend V2 

Sistema Central de Orquestación de Agentes IA e Integraciones OAuth.

Este repositorio aloja el núcleo lógico de HyperShifu. Es una arquitectura backend robusta diseñada para gestionar identidades digitales, orquestar agentes inteligentes (basados en LangGraph) y mantener una pasarela de integración masiva con más de 30 plataformas externas (Google Workspace, Microsoft 365, Slack, Jira, CRM, etc.).

📋 Tabla de Contenidos
Arquitectura del Sistema

Stack Tecnológico

Instalación y Despliegue

Sistema de Integraciones (V1 vs V2)

🔐 Bóveda de Seguridad (OAuth Vault)

Protocolos de Mantenimiento y Scripts

Estructura del Proyecto

🏗 Arquitectura del Sistema
El backend opera bajo un modelo modular dividido en tres pilares:

Core API & Routes: Manejo de peticiones HTTP, autenticación de usuarios y endpoints de servicios.

Integration Hub (Interpreters): Una capa de abstracción que normaliza las APIs externas. Cada servicio (ej. Gmail, Asana) tiene su propio Interpreter y AuthHandler para traducir acciones de IA a llamadas de API reales.

AI Agent Engine: Ubicado en app/agents/. Utiliza LangGraph para gestionar estados, memoria y ejecución de herramientas complejas (BigTools).

🛠 Stack Tecnológico
Lenguaje: Python 3.11+

Framework Web: FastAPI / Flask (Arquitectura Híbrida)

Base de Datos: MongoDB Atlas (Production Tier M10+)

Orquestación IA: LangChain / LangGraph

Contenedores: Docker & Docker Compose

Seguridad: Encriptación AES-256 (Fernet) para tokens OAuth.

🚀 Instalación y Despliegue
Prerrequisitos
Docker Desktop (Running)

Python 3.11 (para desarrollo local)

Acceso a MongoDB Atlas

Despliegue con Docker (Recomendado)
El proyecto está contenerizado para garantizar consistencia entre entornos.

El backend está dividido en **dos servicios independientes** que pueden correr en el mismo servidor o en servidores separados:

| Servicio | Qué hace | Puerto |
|----------|----------|--------|
| **api** | Recibe peticiones HTTP, autentica usuarios, gestiona integraciones OAuth, responde al frontend | `5000` |
| **worker** | Corre en segundo plano, consulta MongoDB cada 5 segundos, ejecuta jobs programados con LangGraph | ninguno |

Ambos se comunican **únicamente a través de MongoDB**. No se llaman entre sí.

---

### 1. Configuración inicial

```bash
# Clonar el repositorio
git clone <repo_url>
cd HyperShifu_V2

# Configurar variables de entorno
cp example.env .env
# (Rellenar con credenciales reales: MONGO_URI, OPENAI_API_KEY, ENCRYPTION_KEY, etc.)
```

---

### 2. Elegir modo de arranque (desarrollo local)

```bash
# Modo por defecto: SOLO API (worker desactivado)
docker-compose up --build

# Próximas veces (sin rebuild)
docker-compose up

# API + Worker (activando profile worker)
docker-compose --profile worker up --build

# API + Worker en segundo plano
docker-compose --profile worker up -d

# Solo Worker (útil para servidor dedicado de background)
docker-compose --profile worker up worker --build

# Solo API explícito (opcional, equivalente al modo por defecto)
docker-compose up api

# Detener todo
docker-compose down
```

---

### 2.1 Entorno de prueba y modo desarrollo

Usa esta guia cuando quieras validar cambios de forma segura antes de desplegar.

```bash
# A) Modo desarrollo rapido (API con hot reload)
docker-compose up

# B) Modo desarrollo completo (API + Worker)
docker-compose --profile worker up

# C) Entorno de prueba (levanta servicios, ejecuta tests y apaga todo)
docker-compose --profile worker up -d --build
docker-compose run --rm api pytest -q
docker-compose down
```

Validaciones rapidas recomendadas:

```bash
# Verificar health de la API
curl http://localhost:5000/health

# Ver logs en vivo de API y Worker
docker-compose logs -f api
docker-compose logs -f worker
```

Notas:
- Si cambias `requirements.txt` o `dockerfile`, vuelve a usar `--build`.
- Si solo cambias codigo Python, normalmente basta con `docker-compose up` por el `--reload` de la API.

---

### 3. Levantar solo la API

Útil para el servidor principal que recibe tráfico del frontend.

```bash
# Primera vez
docker-compose up --build

# Próximas veces
docker-compose up
```

La API queda disponible en: `http://localhost:5000`

Para verificar que está corriendo:
```bash
curl http://localhost:5000/health
```

---

### 4. Levantar solo el Worker

Útil para un servidor dedicado a tareas en segundo plano.

```bash
# Primera vez
docker-compose --profile worker up worker --build

# Próximas veces
docker-compose --profile worker up worker
```

El worker **no expone ningún puerto**. Solo imprime logs en consola mostrando qué jobs ejecuta cada 5 segundos.

---

### 5. Build manual de imágenes (para Render u otros cloud)

```bash
# Construir imagen de la API
docker build --target api -t hyper-api .

# Construir imagen del Worker
docker build --target worker -t hyper-worker .

# Ver tamaño de las imágenes generadas
docker image ls | findstr hyper-
```

---

### 6. Despliegue en Render (dos servicios separados)

**Servicio 1 — API (Web Service):**
- Dockerfile: `dockerfile`
- Docker target: `api`
- Start command: `uvicorn main:app --host 0.0.0.0 --port 5000`
- Variables de entorno: todas las del `.env`

**Servicio 2 — Worker (Background Worker):**
- Dockerfile: `dockerfile`
- Docker target: `worker`
- Start command: `python -m worker.worker`
- Variables de entorno: las mismas que la API (mismo `MONGO_URI`, `ENCRYPTION_KEY`, etc.)
- **No expone URL pública** — configurar como Background Worker en Render

> ⚠️ El Worker necesita la misma `ENCRYPTION_KEY` que la API para poder desencriptar las credenciales OAuth de los usuarios guardadas en MongoDB.

---

### 7. Comandos útiles de mantenimiento

```bash
# Ver logs de la API en tiempo real
docker-compose logs -f api

# Ver logs del Worker en tiempo real
docker-compose logs -f worker

# Entrar al contenedor de la API (para scripts de diagnóstico)
docker exec -it fastapi_api bash

# Ver uso de RAM/CPU de los contenedores activos
docker stats
```

🔌 Sistema de Integraciones (V1 vs V2)
El backend maneja un ecosistema masivo de integraciones.

Rutas V1 (app/routes/V1/apis/): Contiene la lógica de negocio, webhooks y ejecución de acciones (ej: postFunctionGmail.py, interpreter_asana.py).

Rutas V2 (app/routes/V2/apis/): Dedicado exclusivamente a los flujos de autenticación OAuth 2.0 y autorización (auth_slack.py, auth_hubspot.py).

Plataformas Soportadas:
Google (Gmail, Drive, Docs, Sheets, Slides), Microsoft (Outlook, Teams, OneDrive), Slack, Jira, Trello, Asana, Monday, ClickUp, Notion, HubSpot, Salesforce, Facebook, Instagram, LinkedIn, TikTok, WhatsApp, Discord, Dropbox, entre otros.

🔐 Bóveda de Seguridad (OAuth Vault) [NUEVO]
A partir de la versión v2.5 (Feb 2026), se implementó un cambio crítico en la gestión de credenciales.

Antes: Los tokens vivían en texto plano o estructuras débiles dentro de la colección usuarios.

Ahora: Todas las credenciales residen en la colección oauth_vault.

Encriptación: AES-256 (Fernet) en reposo.

Estructura:

{
  "user_id": "...",
  "provider": "google",
  "security": {
    "encrypted_data": "gAAAAABk...", // Token encriptado
    "iv": "bundled",
    "version": "v2_migration"
  },
  "metadata": { ... }
}

💳 Stripe — Pagos y Desarrollo Local

### Variables de entorno requeridas

Copia estas claves desde [dashboard.stripe.com/apikeys](https://dashboard.stripe.com/apikeys) y ponlas en tu `.env`:

```env
STRIPE_SECRET_KEY=sk_test_REEMPLAZAR      # Clave secreta (NUNCA exponerla al frontend)
STRIPE_PUBLISHABLE_KEY=pk_test_..  # Clave pública (puede ir al frontend)
WEBHOOK_SECRET=whsec_REEMPLAZAR           # Se genera al correr el CLI (ver abajo)
```

> ⚠️ Nunca uses claves `sk_live_` en desarrollo. Las claves `sk_test_` no cobran dinero real.

---

### Arquitectura de pagos

| Endpoint | Qué hace |
|---|---|
| `GET /api/v2/stripe/products` | Lista el catálogo de productos desde MongoDB |
| `GET /api/v2/stripe/products/{slug}` | Detalle de un producto |
| `POST /api/v2/stripe/products/admin` | Crea o actualiza un producto en Stripe + MongoDB |
| `DELETE /api/v2/stripe/products/admin/{slug}` | Elimina un producto del catálogo |
| `GET /api/v2/stripe/products/{slug}/pay` | Devuelve la URL de PaymentLink (enlace reutilizable) |
| `POST /api/v2/stripe/products/{slug}/checkout` | Crea una sesión de Checkout personalizada por usuario |
| `POST /api/v2/stripe/webhook` | Recibe eventos de Stripe (checkout completado, etc.) |

Los productos se guardan en la colección `stripe_products` de MongoDB.

---

### Configuración inicial — crear los productos en Stripe

Con el backend corriendo, ejecutar una vez por plan:

```bash
# Pro
curl -X POST http://localhost:5000/api/v2/stripe/products/admin \
  -H "Content-Type: application/json" \
  -d '{"slug":"pro","name":"Shifu Pro","description":"Plan Pro mensual","plan_code":"pro","unit_amount":3500,"currency":"usd","interval":"month"}'

# Master
curl -X POST http://localhost:5000/api/v2/stripe/products/admin \
  -H "Content-Type: application/json" \
  -d '{"slug":"master","name":"Shifu Master","description":"Plan Master mensual","plan_code":"master","unit_amount":6500,"currency":"usd","interval":"month"}'

# Premium
curl -X POST http://localhost:5000/api/v2/stripe/products/admin \
  -H "Content-Type: application/json" \
  -d '{"slug":"premium","name":"Shifu Premium","description":"Plan Premium mensual","plan_code":"premium","unit_amount":10000,"currency":"usd","interval":"month"}'

# Enterprise
curl -X POST http://localhost:5000/api/v2/stripe/products/admin \
  -H "Content-Type: application/json" \
  -d '{"slug":"enterprise","name":"Shifu Enterprise","description":"Plan Enterprise mensual","plan_code":"enterprise","unit_amount":35000,"currency":"usd","interval":"month"}'
```

> **Windows (PowerShell):** reemplaza `curl` por `Invoke-RestMethod` o usa [Insomnia](https://insomnia.rest/) / [Postman](https://www.postman.com/).

---

### Desarrollo local con Stripe CLI (vía Docker)

El Stripe CLI es necesario para **recibir webhooks en localhost** durante el desarrollo. No requiere instalación nativa — usa Docker.

#### Prerequisitos
- Docker Desktop corriendo
- Backend corriendo (via `docker-compose up`) en `localhost:5000`

#### Paso 1 — Levantar el backend

```bash
# Primera vez
docker-compose up --build

# Las demás veces
docker-compose up
```

> Si usas `python -m uvicorn` directamente (sin Docker), el puerto es 8000 y debes activar `.venv` primero. Pero la forma recomendada es docker-compose (puerto 5000).

#### Paso 2 — Iniciar el listener de webhooks con Stripe CLI

En una **segunda terminal** (sin cerrar el backend):

```bash
# Con docker-compose (recomendado) — puerto 5000
docker run --rm -it stripe/stripe-cli:latest listen \
  --api-key sk_test_REEMPLAZAR \
  --forward-to http://host.docker.internal:5000/api/v2/stripe/webhook

# Con uvicorn local — puerto 8000
docker run --rm -it stripe/stripe-cli:latest listen --api-key sk_test_REEMPLAZAR --forward-to http://localhost:5000/api/v2/stripe/webhook
```

El CLI imprimirá algo como:
```
Ready! Your webhook signing secret is whsec_REEMPLAZAR
```

> Copia ese valor `whsec_REEMPLAZAR` y ponlo en tu `.env` como `WEBHOOK_SECRET=whsec_REEMPLAZAR`
> Luego **reinicia el backend** para que tome el nuevo valor.

#### Paso 3 — Verificar que funciona

```bash
# Disparar un evento de prueba de pago completado
docker run --rm -it stripe/stripe-cli:latest trigger \
  --api-key sk_test_REEMPLAZAR \
  checkout.session.completed
```

Deberías ver en los logs del backend:
```
INFO: Webhook recibido: checkout.session.completed
```

#### Paso 4 — Probar el flujo completo de checkout

```bash
# 1. Crear sesión de checkout para el plan pro
curl -X POST http://localhost:5000/api/v2/stripe/products/pro/checkout \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test_user_123","email":"test@ejemplo.com"}'

# 2. Abrir la URL devuelta en el navegador
# 3. Pagar con la tarjeta de prueba: 4242 4242 4242 4242
#    Fecha: cualquier fecha futura | CVC: cualquier 3 dígitos | CP: cualquier 5 dígitos
# 4. Verificar en los logs del backend que el webhook actualizó el plan del usuario
```

---

### Tarjetas de prueba de Stripe

| Número | Resultado |
|---|---|
| `4242 4242 4242 4242` | Pago exitoso |
| `4000 0000 0000 0002` | Tarjeta declinada |
| `4000 0025 0000 3155` | Requiere autenticación 3D Secure |
| `4000 0000 0000 9995` | Fondos insuficientes |

Fecha, CVC y código postal pueden ser cualquier valor válido (ej. `12/34`, `123`, `12345`).

---

### Solución de problemas comunes

**El webhook no llega al backend:**
- Verifica que el backend esté corriendo (`docker-compose up`) — puerto 5000
- En Windows, `host.docker.internal` resuelve al host — asegúrate de que Docker Desktop esté en modo WSL2 o con la opción "Use host networking" activa
- Revisa que `WEBHOOK_SECRET` en `.env` coincida con el `whsec_` que imprimió el CLI
- Asegúrate de haber reiniciado el backend tras actualizar `.env`

**Error `stripe.error.SignatureVerificationError`:**
- El `WEBHOOK_SECRET` en `.env` no coincide con el del CLI
- El CLI fue reiniciado — genera un nuevo `whsec_` en cada arranque; actualiza `.env`

**`No module named uvicorn` al iniciar el backend:**
- El entorno virtual no está activado: ejecuta `.venv\Scripts\Activate.ps1` primero
- Luego instala dependencias: `pip install -r requirements.txt`

**`host.docker.internal` no resuelve (Linux):**
- Linux no tiene `host.docker.internal` por defecto; usar `--add-host=host.docker.internal:host-gateway`:
```bash
docker run --rm -it --add-host=host.docker.internal:host-gateway \
  stripe/stripe-cli:latest listen \
  --api-key sk_test_REEMPLAZAR \
  --forward-to http://host.docker.internal:8000/api/v2/stripe/webhook
```

---

⚙️ Protocolos de Mantenimiento y Scripts
En la carpeta app/scripts/ se encuentran las herramientas críticas de administración. Úsese con precaución.

1. Respaldo de Base de Datos
Script para generar un dump JSON local de la base de datos de producción (bypass del tier gratuito de Atlas).
Este script descarga todas las colecciones en formato JSON a una carpeta local segura configurada en el script.

python app/scripts/backup_production.py
# Salida: ./backups/backup_shifu_<TIMESTAMP>

2. Migración de Integraciones
Script idempotente para mover y encriptar credenciales legacy a la nueva bóveda.

# EJECUTAR DENTRO DEL CONTENEDOR DOCKER
python app/scripts/migrate_integrations_v2.py

3. Auditoría de Seguridad
Verifica la integridad criptográfica y la estructura JSON de la bóveda.

python app/scripts/audit_migration.py
# Debe retornar: "Calidad: 100.00%"

📂 Estructura del Proyecto (Resumen)

HyperShifu_V2/
├── app/
│   ├── agents/                 # Cerebro de la IA (LangGraph)
│   │   ├── agent_langGraph/    # Nodos y Grafos de decisión
│   │   └── tools/              # Herramientas unitarias (GmailTool, JiraTool)
│   ├── core/                   # Lógica central
│   │   ├── security.py         # Módulo de Encriptación AES-256
│   │   └── principal_ia.py     # Prompt del sistema
│   ├── models/                 # Modelos de Base de Datos (Pydantic/Mongo)
│   ├── routes/                 # Endpoints del API
│   │   ├── V1/apis/            # Lógica de negocio por integración (Interpreters)
│   │   └── V2/apis/            # Autenticación OAuth (Auth Handlers)
│   ├── scripts/                # Scripts de Migración, Backup y Auditoría
│   └── services/               # Capa de servicios reutilizables
├── helpers/                    # Scripts de utilidad y diagnóstico
├── test/                       # Tests unitarios
├── docker-compose.yml          # Orquestación de contenedores
└── requirements.txt            # Dependencias Python

