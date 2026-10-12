# Fase 1 — identity_loader

**Objetivo:** Nodo dedicado que carga los 4 docs globales del agente con cache TTL 1h,
agregado al grafo `START → identity_loader → context_loader`.

---

## Estado general

✅ Completada — 2026-06-01

---

## Hitos

### 1. Agregar campos a `state.py`
- [x] `agent_identity_doc: Optional[dict]`
- [x] `agent_personality_doc: Optional[dict]`
- [x] `agent_goals_doc: Optional[dict]`
- [x] `agent_system_model_doc: Optional[dict]`

### 2. Crear `nodes/identity_loader.py`
- [x] Cache en memoria (dict + timestamp por colección)
- [x] TTL configurable via env `IDENTITY_CACHE_TTL_SECONDS` (default 3600)
- [x] Carga las 4 colecciones: `agent_identity`, `agent_personality`, `agent_goals`, `agent_system_model`
- [x] Fallback: si un doc no existe en DB, retorna `{}` — no rompe el grafo
- [x] Log entrada: `[► identity_loader] user={user_id} cache_hit={True/False}`
- [x] Log salida: `[✓ identity_loader] agent_id={agent_id} loaded_from={cache|db}`

### 3. Conectar en `graph.py`
- [x] Añadir nodo `identity_loader` al StateGraph
- [x] Edge: `START → identity_loader`
- [x] Edge: `identity_loader → conversation_context_builder` (en lugar de `START → conversation_context_builder`)

### 4. `context_loader` lee del state (sin cambiar lógica todavía)
- [ ] En `_prompt_builders.py`: si `state.agent_identity_doc` existe, usarlo para llenar variables
- [ ] Fallback a `_BASE_IDENTITY_MINIMAL` si el doc está vacío
- [ ] Sin cambios en la estructura del system prompt — solo la fuente del dato
> ⚠️ Pendiente para Fase 2 — agente_v2 aún no tiene context_loader propio

---

## Extra — prompts/ folder (agregado en sesión)

> No estaba en el plan original. Se agrega para evitar prompts hardcodeados en los nodos.

- [x] Crear carpeta `prompts/` en `agente_v2/`
- [x] `prompts/conversation_context.py` — `SYSTEM_PROMPT` + `CONTEXT_BLOCK_HEADER`
- [x] `prompts/identity.py` — `FALLBACK_IDENTITY` + `CREATOR_RULE`
- [x] `prompts/__init__.py` — re-exports de todos los prompts
- [x] `nodes/conversation_context_builder.py` — reemplaza strings hardcodeados con imports
- [x] `nodes/chat.py` — reemplaza `_FALLBACK_IDENTITY` con import; `CREATOR_RULE` siempre al final del bloque
- [x] `nodes/chat.py` — strings en inglés en `_build_identity_block` (fix de mezcla de idiomas)
- [x] `seed_agent_identity.py` — todos los valores traducidos a inglés + seed corrido
- [x] `RULES.md` creado con 5 reglas: código/DB/prompts/logs en inglés

**Regla que motiva este extra:** los prompts estáticos NO deben vivir inline en los nodos.
Cambiar un prompt no debe requerir tocar lógica de nodo.

---

## Criterios de aceptación

| Criterio | Cómo verificar |
|----------|---------------|
| `agent_identity_doc` en state | Log de context_loader muestra campo no vacío |
| Cache hit en segunda llamada | Log muestra `cache_hit=True`, latencia < 1ms |
| Sin regresión en respuestas | Chat funciona igual que antes |
| Latencia cache miss < 30ms | Log de identity_loader muestra tiempo de carga |
| Latencia cache hit < 5ms | Segunda request al mismo agente |
| Fallback activo si DB falla | Apagar mongo localmente → agente sigue respondiendo con identidad default |

---

## Notas de sesión

### 2026-06-01
- Fase 0 confirmada completa: seed corrido, CREATOR RULE en prompt, cache invalidation endpoint operativo
- Arrancando Fase 1
- ✅ state.py: 4 campos `agent_*_doc` agregados
- ✅ nodes/identity_loader.py creado: cache TTL, fallback, logs entrada/salida
- ✅ nodes/__init__.py: identity_loader_node registrado
- ✅ graph.py: flow actualizado `START → identity_loader → conversation_context_builder → chat → END`
- ⚠️ Hito 4 (context_loader lee del state) diferido a Fase 2 — agente_v2 no tiene context_loader todavía

### 2026-06-02 (extra)
- ✅ prompts/ folder creado con conversation_context.py, identity.py, __init__.py
- ✅ Nodos actualizados para importar prompts desde prompts/ — sin strings hardcodeados en lógica
- ✅ CREATOR_RULE reemplazado por `build_creator_rule()` — dinámico desde DB, nunca hardcodeado
- ✅ Fallback de fundadores en chat.py eliminado — `identity.get("fundadores") or []`
- ✅ _build_identity_block: strings corregidos a inglés
- ✅ seed_agent_identity.py: todos los valores en inglés + seed corrido en DB
- ✅ RULES.md creado con 5 reglas de idioma/estilo para el proyecto
- ✅ conversation_context_builder: modelo cambiado a `gpt-4.1-nano` (tarea ultraliviana)
- ✅ chat_node: modelo default `gpt-4o-mini` confirmado

### 2026-06-02 (fixes post-review)
- ✅ state.py: comentario traducido al inglés (violaba RULES.md regla 1)
- ✅ identity_loader.py: docstring y log de error traducidos al inglés (violaban RULES.md reglas 1 y 4)
- ✅ RULES.md: endpoint corregido de `/api/v3/agent/debug/` a `/api/v4/debug/`
