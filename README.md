# Shifu

Plataforma para crear CRMs con IA.

## Estructura

| Carpeta | Qué es |
|---|---|
| `/` (raíz) | Frontend de Shifu: React + Vite. Inicio, login, cuestionario, carga y CRM con chat. `npm install` y `npm run dev`. |
| `backend/` | Backend de agentes (FastAPI, MongoDB, Redis, LangGraph), extraído de `Alan4745/HyperShifu-crm-agent` (commit `271bbe6`). Ver `backend/README.md`. |

## Cómo se conectan

El frontend habla con los datos solo a través de `src/api`. Con `VITE_API_URL` apunta a un servidor real; sin ella usa un servidor simulado en el navegador. Las rutas que espera están en [`API.md`](API.md).

El backend de `backend/` ya trae autenticación, onboarding, chat con el agente y subida de archivos bajo `/api/v1`, y ahora también el **módulo de CRM** (`backend/app/crm`, rutas en `/api/v1/crm`): contactos, tareas, secciones y automatizaciones, con su chat. Pruebas: `cd backend && pytest test/crm`.

## Cómo verlo funcionando

**Solo el frontend** (todo se guarda en el navegador, sin cuentas): `npm install` y `npm run dev`, y abrir http://localhost:5180.

**Con cuentas y el CRM en un servidor, sin Mongo ni Redis** (servidor de desarrollo, todo en memoria):

1. En una terminal, dentro de `backend/`: `pip install fastapi uvicorn pydantic` y luego `python scripts/crm_dev_server.py` (puerto 5000).
2. En la raíz, crear `.env` con `VITE_API_URL=http://localhost:5000/api/v1` y reiniciar `npm run dev`.

**Con el backend completo** (Mongo, Redis y agente): llenar `backend/.env` a partir de `backend/example.env`, arrancar según `backend/README.md` y usar la misma `VITE_API_URL`.

## Variables de entorno

- Frontend: copiar `.env.example` a `.env`.
- Backend: copiar `backend/example.env` a `backend/.env` y llenar las credenciales (nunca se suben al repositorio).
