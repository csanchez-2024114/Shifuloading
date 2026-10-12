# Phase 7 — Long-Term Memory

**Estado:** ✅ Completada — todos los objetivos implementados

---

## Qué hace

Shifu recuerda entre sesiones. No solo el perfil del usuario (Phase 6), sino el contexto de trabajo: proyectos, decisiones, temas discutidos en conversaciones anteriores. La memoria se construye progresivamente: conversación → diario diario → memoria global.

---

## Objetivos

| Objetivo | Estado | Descripción |
|----------|--------|-------------|
| Persistent Memory | ✅ | `user_global_memory` — síntesis narrativa generada tras cada 3+ conversaciones nuevas |
| Memory Storage | ✅ | 3 colecciones: `agente_v2_chat_context` (por conv) + `user_daily_diary` (por día) + `user_global_memory` (global) |
| Memory Retrieval | ✅ | Jerárquico: global_memory → daily_diary (últimos 3 días) → summaries recientes (top-5). Siempre hay algo disponible |
| Memory Updates | ✅ | `asyncio.create_task` al final de cada turno — diary + global refresh en background, no bloquea respuesta |
| Memory Consolidation | ✅ | Vector search sobre `user_global_memory_chunks` — activa automáticamente cuando global_memory supera 800 palabras (`AGENTE_V2_CHUNK_WORD_THRESHOLD`) |

---

## Pipeline de memoria

```
[Turno] → memory_saver (sync: guarda summary de conv)
              ↓ (background, no bloquea)
         update_daily_diary (agrupa summaries del día)
              ↓ (cada 3 actualizaciones del diary)
         refresh_global_memory (síntesis de últimos 14 días)
              ↓ (próximo turno, cualquier conversación)
         long_term_memory_loader (inyecta como SystemMessage)
```

---

## Cómo verificarlo en la interfaz de debug

### Primera conversación (sin memoria)
1. Abrir conversación → logs: `[long_term_memory_loader] has_memory=False`
2. Normal — no hay historial todavía

### Acumular memoria
1. Tener 1+ conversación con contenido real (proyectos, decisiones)
2. En logs buscar: `[memory_saver] summary saved user=X conv=Y words=N`
3. Buscar: `[memory_saver] diary updated user=X date=YYYY-MM-DD convs=N`

### Global memory generada
1. Después de 3 actualizaciones del diary:
2. Logs: `[memory_saver] global memory refreshed user=X date_range=... words=N`
3. Nueva conversación → logs: `[long_term_memory_loader] has_memory=True words=N`
4. Preguntar: "¿qué proyectos he mencionado antes?" → Shifu debe responder con datos reales

### Verificar en MongoDB
```
db.user_global_memory.findOne({user_id: "..."})
db.user_daily_diary.find({user_id: "..."})
db.agente_v2_chat_context.find({user_id: "..."})
```

---

## Nodos responsables

**Carga:** `long_term_memory_loader` — [nodes/context/long_term_memory_loader.py](../nodes/context/long_term_memory_loader.py)
- Lee `user_global_memory` de MongoDB
- Inyecta como SystemMessage antes del contexto de conversación
- No-op si no existe memoria todavía

**Guardado:** `memory_saver` — [nodes/memory/memory_saver.py](../nodes/memory/memory_saver.py)
- Corre como último nodo del pipeline
- Guarda summary de conversación (sync)
- Dispara diary + global memory en background (no bloquea)

---

## Colecciones MongoDB

| Colección | Doc por | Contenido |
|-----------|---------|-----------|
| `agente_v2_chat_context` | usuario + conversación | Summary de esa conversación (max 150 palabras) |
| `user_daily_diary` | usuario + día | Narrativa del día completo (max 300 palabras) |
| `user_global_memory` | usuario | Narrativa acumulada de los últimos 14 días (max 600 palabras) |
| `user_global_memory_chunks` | usuario | Párrafos de global_memory con embeddings `text-embedding-3-small` — activa cuando supera 800 palabras |

---

## Variables de entorno

```env
AGENTE_V2_SUMMARY_MODEL=gpt-4.1-nano
AGENTE_V2_DIARY_REFRESH_TURNS=3
AGENTE_V2_GLOBAL_MEMORY_DAYS=14
AGENTE_V2_CHUNK_WORD_THRESHOLD=800   # palabras mínimas para activar chunking
AGENTE_V2_EMBEDDING_MODEL=text-embedding-3-small
AGENTE_V2_TOP_K_CHUNKS=4             # chunks más relevantes a inyectar
```

---

## Lo que supera el spec original

| Feature | Descripción |
|---|---|
| **Retrieval jerárquico 3 capas** | Si no hay global → diarios; si no hay diarios → últimos 5 summaries. El agente siempre tiene contexto histórico disponible |
| **key_facts preservados verbatim** | Extracción separada de hechos exactos (números, thresholds, nombres) que sobreviven la síntesis narrativa |
| **Deduplicación de facts** | `seen: set` deduplica hechos entre conversaciones antes de incluirlos en diary y global |
| **conversation_context persistido** | Stage, topic, goal, entities se guardan en `agente_v2_chat_context` cada turno |
| **Cap de key_facts configurable** | `AGENTE_V2_MAX_KEY_FACTS=50` (env) — preparado para reemplazar con vector top-N en Fase 4 |

---

## Pipeline completo

```
[Turno] → memory_saver
            ├─ (sync)  guarda summary + key_facts en agente_v2_chat_context
            └─ (background)
                 ├─ _update_daily_diary     → user_daily_diary
                 ├─ _refresh_global_memory  → user_global_memory
                 └─ _rebuild_chunks         → user_global_memory_chunks (si words > 800)

[Siguiente turno] → long_term_memory_loader
            ├─ Layer 0: vector_chunks   (si existen chunks — cosine top-4)
            ├─ Layer 1: global_memory   (blob completo — bajo el threshold)
            ├─ Layer 2: daily_diary     (últimos 3 días)
            └─ Layer 3: summaries       (últimas 5 conversaciones)
```

## Pendiente

### Memoria Episódica — user_episodic_memory (opcional, post-Fase 7)
Eventos puntuales de alta importancia (decisiones clave, hitos, integraciones configuradas). Requiere nodo `reflection` adicional.
Activar si el usuario reporta que Shifu no recuerda eventos específicos que `user_global_memory` no captura bien.
