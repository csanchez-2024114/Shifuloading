# Estado actual — continuar aquí

**Última sesión:** 2026-05-25  
**Branch:** `feature/fase2-batch3-pydantic-aliases`

**Servidor:** `nohup .venv/Scripts/python -m uvicorn main:app --host 0.0.0.0 --port 5000`  
**Run tests:** `$env:PYTHONIOENCODING="utf-8"; .venv\Scripts\python test/test_shifu_behavioral.py`

---

## Qué está completo

### Process Discovery — Arquitectura 4 niveles
Implementado y funcionando en producción:

- **4 niveles conversacionales** (Level 1–4) con stages mapeados a MongoDB (`intent_detection`, `context_discovery`, `tool_exploration`, `structuring`, `validation`, `completed`)
- **Entidad `Workflow`** — colección `workflows`, se crea al avanzar a `validation`; se marca `ready` al completar
- **Entidad `Process`** — colección `processes`, incluye `conversation_log` y `workflow_id`
- **`user_familiarity`** — campo en cognitive pass (`new | returning | active`); controla si/cómo se menciona sesión pendiente al saludar
- **Session migration** — cuando el usuario abre una nueva conversación, la sesión activa migra al nuevo `conversation_id`
- **HARD RULE frecuencia** — no se puede avanzar a `structuring` sin `frequency` confirmada
- **Executor framing** — el agente habla como el que ejecuta, nunca como asesor
- **Tavily con fuentes** — resultados incluyen `[N] Título\nSource: URL\ncontenido`
- **Señales de abandono** — tolerante a typos (`"olvidem"` = `"olvidemos"`)
- **`discovery_clear` WS event** — cuando no hay sesión activa, frontend limpia el panel

### Frontend ChatDebug.tsx
- Discovery panel con stage badge, barra de progreso 5 etapas, info recolectada, preguntas pendientes, tool findings, ambigüedades
- Maneja `discovery_status` y `discovery_clear`
- WebSocket persistente al `/api/v3/ws/chat-direct`

---

## Archivos clave modificados en esta sesión

| Archivo | Cambio principal |
|---|---|
| `app/agents/multiAgent/context_loader.py` | `user_familiarity`, session migration, `_discovery_resuming` via `greeting_pattern` |
| `app/agents/multiAgent/reflection.py` | HARD RULE frecuencia, señales de abandono ampliadas, workflow upsert trigger |
| `app/agents/multiAgent/process_discovery/discovery_prompt.py` | 4 niveles, executor framing, Tavily sources, ejemplos ES+EN, frequency gate |
| `app/agents/multiAgent/process_discovery/workflow_builder.py` | **nuevo** — CRUD de `workflows` |
| `app/agents/multiAgent/process_discovery/process_builder.py` | `conversation_log`, `workflow_id`, `append_conversation_entry` |
| `app/agents/multiAgent/process_discovery/session_manager.py` | `workflow_id: None`, `conversation_log: []` en doc inicial |
| `app/agents/multiAgent/process_discovery/__init__.py` | exports de `workflow_builder`, `abandon_session`, `update_session` |
| `app/agents/agent_langGraph/tools.py` | Tavily formatea título + URL + contenido por resultado |
| `app/routes/V3/ws/chat_direct_ws.py` | `discovery_clear` WS event |
| `front-hyper-shifu/src/pages/debug/ChatDebug.tsx` | Discovery panel completo |
| `doc/MULTIAGENT_COMO_FUNCIONA.md` | Documentación completa reescrita |

---

## Para correr el frontend (debug chat)

```bash
cd "front-hyper-shifu"
npm run dev
# Abrir http://localhost:5173/debug/chat
```
Asegurarse de que `VITE_API_URL=http://localhost:5000` esté en `.env.local`.

---

## Próximos pasos posibles

- **Worker de ejecución** — el runtime que procesa los docs `Workflow` con status `ready`
- **UI de automatizaciones** — página para ver y gestionar los workflows creados del usuario
- **Refinamiento del Process Discovery** — basado en sesiones reales con usuarios
