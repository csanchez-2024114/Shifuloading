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

## Variables de entorno

- Frontend: copiar `.env.example` a `.env`.
- Backend: copiar `backend/example.env` a `backend/.env` y llenar las credenciales (nunca se suben al repositorio).
