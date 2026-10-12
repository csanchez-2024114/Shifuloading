# HyperShifu Backend — Guía de Desarrollo Local

## Requisitos previos
- Python 3.12
- MongoDB corriendo en `localhost:27017`
- Redis Cloud configurado en `.env`

---

## 1. Activar entorno virtual

```bash
.venv\Scripts\activate
```

---

## 2. Levantar el servidor API

```bash
uvicorn main:app --reload --port 8000
```

Disponible en: `http://localhost:8000`  
Docs Swagger: `http://localhost:8000/docs`

---

## 3. Levantar el worker (terminal separada)

```bash
.venv\Scripts\activate
python worker_main.py
```

El worker hace polling cada **10 segundos** para ejecutar workflows y cada **60 segundos** para tareas programadas (scheduler).

---

## 4. Levantar Langgraph (opcional)

```bash
.venv\Scripts\activate
      Langgraph dev 
```

## Variables de entorno clave (`.env`)

| Variable | Descripción |
|---|---|
| `MONGO_URI` | URI de MongoDB |
| `REDIS_URL` | URI de Redis (pub/sub entre worker y API) |
| `SECRET_KEY` | JWT secret |
| `INLINE_WORKER` | `true` para correr el worker dentro del mismo proceso del API (no recomendado en prod) |

---

## Flujo completo en dos terminales

```
Terminal 1                    Terminal 2
──────────────────────────    ──────────────────────────
.venv\Scripts\activate        .venv\Scripts\activate
uvicorn main:app --reload     python worker_main.py
      │                             │
      │ WebSocket /ws/runs          │ polls MongoDB
      │ REST /api/v3/...            │ publica eventos → Redis
      └─────────── Redis ───────────┘
```

---

## Render.com (producción)

| Servicio | Tipo | Start Command |
|---|---|---|
| `hypershifu-api` | Web Service | `uvicorn main:app --host 0.0.0.0 --port $PORT` |
| `hypershifu-worker` | Background Worker | `python worker_main.py` |

Ambos servicios comparten las mismas variables de entorno.
