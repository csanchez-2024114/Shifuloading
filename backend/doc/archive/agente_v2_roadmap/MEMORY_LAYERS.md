# Memory Layers — agente_v2

Documento de decisión para las capas de memoria del agente. Define qué se implementa, en qué orden, y por qué.

---

## Arquitectura de capas

```
┌─────────────────────────────────────────────────────┐
│  LLM Context (SystemMessages inyectados por turno)  │
├─────────────┬───────────────────────────────────────┤
│ Capa        │ Origen                                 │
├─────────────┼───────────────────────────────────────┤
│ Identidad   │ MongoDB agent_identity/* (cache 1h)   │
│ Perfil user │ MongoDB user_preferences               │
│ LT Memory   │ MongoDB user_global_memory ← Fase 3   │
│ Conv context│ LLM sobre hist. reciente (stateless)  │
│ Working mem │ LLM sobre hist. completa (stateless)  │
└─────────────┴───────────────────────────────────────┘
```

---

## Estado actual (post Fase 2)

| Capa | Colección / Estado | Tipo | Nodo |
|------|--------------------|------|------|
| Identidad del agente | `agent_identity/personality/goals` (MongoDB) | Global, cached 1h | identity_loader |
| Perfil del usuario | `user_preferences` (MongoDB) | Persistente | user_context_loader |
| Contexto de conversación | `conversation_context` (state) | Sesión, stateless | conversation_context_builder |
| Working memory | `working_memory_context` (state) | Sesión, stateless | working_memory_builder |

**Gap actual:** Shifu no recuerda nada de conversaciones anteriores a la sesión actual.

---

## Evaluación de capas propuestas

### 1. `user_global_memory` ✅ Fase 3

**Qué es:** Resumen narrativo acumulado de toda la historia del usuario. Máx 600 palabras.

- Colección: `user_global_memory` (1 doc por usuario)
- Generado desde: últimas 14 entradas de `user_daily_diary`
- Se regenera cada 3 actualizaciones del diario (configurable)
- **Inyectado directamente como SystemMessage** en cada turno

**Por qué vale la pena:** Sin esto Shifu no recuerda proyectos, decisiones ni preferencias de sesiones pasadas.

---

### 2. `user_daily_diary` ✅ Fase 3 (infraestructura)

**Qué es:** Síntesis narrativa de todas las conversaciones del usuario en un día. Máx 300 palabras.

- Colección: `user_daily_diary` (1 doc por usuario por día)
- Trigger: background job al final de cada turno
- Input: todos los `agente_v2_chat_context.summary` del día
- **NO se inyecta directamente** — es la materia prima para `user_global_memory`

**Por qué vale la pena:** Es el puente entre conversaciones individuales y la memoria de largo plazo.

---

### 3. `user_global_memory_chunks` ✅ Fase 4

**Qué es:** `user_global_memory` partido en párrafos con embeddings vectoriales. Permite búsqueda semántica.

- Colección: `user_global_memory_chunks`
- Embedding: OpenAI text-embedding-3-small
- Query: cosine similarity contra la query del usuario → top-4 chunks relevantes
- Ventaja sobre inyección completa: no gasta tokens cuando hay mucha historia

**Por qué esperar:** En Fase 3, 600 palabras de texto plano es manejable. Agregar esto cuando el global_memory empiece a afectar la calidad por longitud.

---

### 4. `user_episodic_memory` ⚠️ Fase 5+ (opcional)

**Qué es:** Log append-only de eventos significativos (importance >= 0.7). Un doc por evento.

- Tipos: `resolved_problem`, `key_decision`, `milestone`, `blocker_identified`, `integration_configured`
- Requiere: nodo `reflection` adicional en el pipeline
- Inyectado: top-5 episodios recientes con labels temporales relativos ("ayer", "hace 3 días")

**Por qué esperar:** `working_memory_builder` ya captura decisions/threads de la sesión. `user_global_memory` captura eventos importantes a largo plazo. La memoria episódica agrega granularidad pero con costo de implementación alto.

**Reconsiderar si:** el usuario reporta que Shifu no recuerda eventos específicos que el global_memory no captura bien.

---

### 5. `temporal_context_block` ❌ Ya existe

**Qué es:** Contexto de lo que pasa en la conversación actual (topic, stage, entities).

**No implementar:** `conversation_context_builder` ya hace exactamente esto. Agregar un tercer bloque sería redundancia pura.

---

## Resumen de hoja de ruta

| Fase | Qué | Colecciones nuevas |
|------|-----|-------------------|
| **Fase 3** (actual) | user_global_memory + user_daily_diary | `agente_v2_chat_context`, `user_daily_diary`, `user_global_memory` |
| **Fase 4** | Vector search sobre global_memory | `user_global_memory_chunks` |
| **Fase 5+** | Memoria episódica + nodo reflection | `user_episodic_memory` |

---

## Graph — Fase 3

```
START
  → identity_loader
  → user_context_loader
  → long_term_memory_loader    ← NUEVO (lee user_global_memory)
  → conversation_context_builder
  → working_memory_builder
  → chat
  → user_profile_updater
  → memory_saver               ← NUEVO (guarda summary + dispara diary/global jobs)
  → END
```

---

## Variables de entorno

```env
AGENTE_V2_SUMMARY_MODEL=gpt-4.1-nano
AGENTE_V2_DIARY_REFRESH_TURNS=3
AGENTE_V2_GLOBAL_MEMORY_DAYS=14
```
