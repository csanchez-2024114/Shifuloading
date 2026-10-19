# Cómo correr Shifu en tu computadora

Guía para colaboradores. En unos 15 minutos tienes el frontend, el backend y las bases de datos funcionando.

## Qué necesitas instalado

| Programa | Versión | Para qué |
|---|---|---|
| Git | cualquiera | bajar y subir el código |
| Python | 3.11 o más (probado con 3.12) | backend |
| Node.js | 18 o más (probado con 24) | frontend |
| Docker Desktop | cualquiera | MongoDB y Redis |

Antes de empezar: acepta la invitación de colaborador que te llegó por correo de GitHub, si no, no podrás clonar el repo.

## 1. Bajar el código

```bash
git clone https://github.com/csanchez-2024114/Shifuloading.git
cd Shifuloading
```

## 2. Levantar las bases de datos (una sola vez)

Con Docker Desktop abierto:

```bash
docker run -d --name shifu_mongo -p 27017:27017 mongo:6
docker run -d --name shifu_redis -p 6379:6379 redis:7
```

Los días siguientes, si se apagó la computadora: `docker start shifu_mongo shifu_redis`.

## 3. Backend

Todo esto dentro de la carpeta `backend`:

```bash
cd backend
python -m venv .venv
```

Activa el entorno (la carpeta se llama `.venv`, con punto):

| Sistema | Comando |
|---|---|
| Windows (CMD) | `.venv\Scripts\activate` |
| Windows (PowerShell) | `.venv\Scripts\Activate.ps1` |
| Mac o Linux | `source .venv/bin/activate` |

Instala las dependencias (tarda unos minutos) y crea tu archivo de configuración:

```bash
pip install -r requirements.txt
python scripts/crear_env_local.py
```

El script crea `backend/.env` con claves de seguridad aleatorias, solo tuyas. No lo subas a GitHub (ya está ignorado).

Levanta el servidor:

```bash
uvicorn main:app --reload --port 5000
```

Debe terminar diciendo `Application startup complete`. Déjalo corriendo en esa terminal.

## 4. Frontend

En **otra terminal**, en la carpeta raíz del proyecto (donde está `package.json`):

```bash
npm install
```

Crea el archivo `.env` de la raíz con una sola línea:

```
VITE_API_URL=http://localhost:5000/api/v1
```

(En la raíz hay un `.env.example` que puedes copiar y llenar.) Luego:

```bash
npm run dev
```

Abre http://localhost:5180

## 5. Probarlo

1. Entra a http://localhost:5180 y empieza el cuestionario. Al terminar crea una cuenta con cualquier correo (es local, nadie lo ve).
2. Verás tu CRM y el chat con Shifu abajo a la derecha.
3. Sin claves de IA el encabezado del chat dice **"Modo básico"**: el CRM funciona con reglas (por ejemplo "Agrega a Laura Gómez"), sin IA.

## 6. Activar la IA (opcional, con tu propia clave)

Cada persona usa **sus propias claves**. No pidas ni compartas claves por chat, correo ni GitHub.

1. Crea tu clave de OpenAI siguiendo [`backend/docs/CREAR_CLAVES_ENV.md`](backend/docs/CREAR_CLAVES_ENV.md). Con 5 dólares de saldo alcanza para muchísimas pruebas.
2. Abre `backend/.env` y reemplaza `sk-pendiente-pega-aqui-tu-clave` por tu clave, sin comillas ni espacios. (Opcional: `TAVILY_API_KEY` para que Shifu busque en internet.)
3. El servidor se reinicia solo (`--reload`). Si no, ciérralo con `Ctrl+C` y vuelve a lanzarlo.

Con IA activa Shifu hace preguntas de seguimiento según el negocio, arma el CRM a la medida, lee capturas y agenda citas. La primera petición tras arrancar puede tardar unos segundos mientras carga.

## 7. CRM generativo: todo desde el chat (sistema de diseño)

Con dos banderas el CRM nace con su propia pantalla de inicio (bloques, gráficas, tableros) y todo se cambia hablando con Shifu: crear o quitar pestañas y campos, agregar, mover, agrandar o achicar piezas, cambiar colores, preguntar por los datos y deshacer. Los registros también se agregan, editan y borran a mano desde la ficha. En el chat se pueden adjuntar fotos, documentos (PDF, Word, Excel, CSV, TXT, JSON; máximo 5 MB) y pegar enlaces. Necesita la IA activa (paso 6). Las automatizaciones quedan en pausa en este modo.

Backend (en `backend/`):

```bash
CRM_DISENO=1 uvicorn main:app --reload --port 8001
```

Frontend (en la raíz), con `VITE_API_URL` apuntando a ese puerto:

```bash
VITE_CRM_DISENO=1 npx vite --port 5180
```

Sin Mongo ni Redis también se puede probar con el servidor de desarrollo (todo en memoria, se pierde al apagarlo): `CRM_DISENO=1 python scripts/crm_dev_server.py --puerto 5193` y el frontend con `VITE_API_URL=http://localhost:5193/api/v1 VITE_CRM_DISENO=1 npx vite --port 5199`.

## Guardar trazas de los turnos del chat (opcional)

Para revisar después qué pasó en conversaciones reales (pruebas manuales, bancos), con `CRM_TRAZA=1` cada turno del chat del CRM generativo (`CRM_DISENO=1`) deja una línea JSON en un archivo por día:

```bash
CRM_DISENO=1 CRM_TRAZA=1 uvicorn main:app --reload --port 8001
# o con otra carpeta: CRM_TRAZA_DIR=~/trazas_shifu
```

- Carpeta: `CRM_TRAZA_DIR` o, si no se define, `backend/trazas_chat/` (ignorada por git: tiene lo que escribió la persona, no se sube).
- Archivo: `AAAA-MM-DD.jsonl` (día UTC), una línea por turno.
- Cada línea trae: el texto de la persona, cada llamada al modelo y cada herramienta en orden (nombre, argumentos, resultado y milisegundos), los avisos del código, cambios, fallos, la respuesta final y el tiempo total (`ms_total`). Si el modelo falla, el tipo de error.
- No guarda el CRM completo, la imagen, el contenido de archivos o enlaces adjuntos (solo su largo o la URL), el historial (solo cuántos mensajes) ni la configuración. Lo que parezca una clave (`sk-…`, `Bearer …`, JWT) se tapa y los textos largos se recortan.
- Sin la variable no se mide ni se escribe nada. Si no se puede escribir el archivo, el chat responde igual (queda un aviso en el log). Los turnos que resuelven las reglas (sin IA) no dejan traza.
- Para leerlas: `tail -n 5 backend/trazas_chat/$(date -u +%F).jsonl | python -m json.tool --json-lines`.

## Abrir el backend desde otro dominio o desde la red (opcional)

El backend solo responde a peticiones dirigidas a `localhost`, `127.0.0.1`, `hypershifu.com`, `www.hypershifu.com` y `backend-hyper-shifu-nyzm.onrender.com`; con otro nombre responde `400 Invalid host header`. Para sumar más (un dominio propio, la IP de tu computadora en la red, un túnel), agrega en `backend/.env`:

```
TRUSTED_HOSTS_EXTRA=crm.midominio.com,192.168.1.20,*.ngrok-free.app
```

- Separados por coma; se **suman** a los de siempre, no los reemplazan. Sin la variable todo queda igual.
- Solo el nombre: si pegas una URL (`https://crm.midominio.com:8443`) se toma el host y se ignoran esquema y puerto.
- `*.dominio.com` acepta sus subdominios. Un `*` solo se ignora porque apagaría la protección.
- Si el frontend también corre en ese dominio, súmalo a `CORS_ALLOWED_ORIGINS` (ese sí con `https://` y puerto).

## Automatizaciones que corren solas (opcional)

Las automatizaciones del CRM (recordatorios de seguimiento y resumen semanal) se calculan siempre que alguien abre el CRM. Para que además corran **solas**, aunque nadie lo tenga abierto, y dejen un aviso en la campana 🔔:

1. En `backend/.env` debe estar `SHIFU_SCHEDULER=1` (el script `crear_env_local.py` ya lo pone). Reinicia el servidor.
2. Cada 5 minutos el programador revisa los CRM y, si hay algo, crea la tarea y el aviso. Se cambia con `CRM_RELOJ_SEGUNDOS`.

**Avisos por correo** (opcional, necesita un correo de envío): en `backend/.env` agrega `SHIFU_NOTICE_EMAILS=1` y los datos `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS` y `SMTP_FROM_EMAIL`. Los avisos del CRM saldrán juntos en un solo correo, con un tope de 5 al día por persona. Sin estos datos no sale ningún correo; los avisos igual aparecen en la campana.

## Correr las pruebas

Con el entorno `.venv` activado, dentro de `backend`:

```bash
pytest test/crm
```

Ninguna prueba llama a OpenAI ni cuesta dinero.

## Trabajar en equipo

- Antes de empezar: `git pull`.
- Nunca subas `.env`, claves ni contraseñas. Si subes una por error, avisa para cambiarla: borrar el commit no basta.
- Commits pequeños, con un mensaje que diga qué cambió y por qué.
- Si tocas algo del contrato entre frontend y backend, actualiza `API.md`.

## Si algo falla

| Síntoma | Qué hacer |
|---|---|
| `El sistema no puede encontrar la ruta` al activar | La carpeta es `.venv` (con punto), no `venv`. |
| PowerShell no deja activar el entorno | Usa CMD, o ejecuta una vez `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`. |
| El servidor se cae al iniciar con `Missing credentials` | Falta la línea `OPENAI_API_KEY=` en `backend/.env`. Deja el marcador `sk-pendiente-…` o pon tu clave. |
| Error de conexión con Mongo o Redis | Revisa que los contenedores estén corriendo: `docker ps`. Si no, `docker start shifu_mongo shifu_redis`. |
| El puerto 5000 o 5180 está ocupado | Hay otro servidor abierto. Ciérralo, o usa otro puerto (en el frontend ajusta `VITE_API_URL`). |
| La página queda en blanco o cargando sin parar | Borra la carpeta `node_modules/.vite` y vuelve a lanzar `npm run dev`. |
| El chat dice "Modo básico" teniendo clave | La clave está mal pegada, sin saldo, o el servidor no se reinició. Mira la terminal del servidor. |
