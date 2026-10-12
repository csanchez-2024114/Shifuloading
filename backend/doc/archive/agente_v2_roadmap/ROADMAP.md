# Roadmap — Reimplementacion Agente V2

> Documento vivo. Actualizar al cerrar cada hito.
> Estado actual (macro): Fase 2 — En progreso
> Estado actual (conversacional v2): Fase 8 — Pendiente (siguente)

---

## Resumen ejecutivo

- Rama activa: agente_00
- Commit de referencia: 85ac274
- Avance macro: Fases 0 y 1 completas, Fase 2 parcial, Fases 3-6 pendientes
- Avance conversacional v2: Fases 1-7 completas (pipeline largo plazo implementado), Fases 8-14 pendientes

---

## Roadmap macro (reimplementacion)

| # | Nombre | Estado | Duracion estimada |
|---|--------|--------|-------------------|
| 0 | Infraestructura DB | Completada | — |
| 1 | identity_loader | Completada | — |
| 2 | identity_block desde DB | En progreso | 2-3 dias |
| 3 | memory_update + user_state + objective_state + agent_internal_state | Pendiente | 7-8 dias |
| 4 | world_model + world_events + learning_memory + memory_loader | Pendiente | 6-7 dias |
| 5 | cognitive_context_builder + refactorizacion context_loader | Pendiente | 4-5 dias |
| 6 | Cleanup | Pendiente | 2 dias (post-estabilidad) |

---

## Estado por fase (sin redundancia)

### Fase 0 — Infraestructura DB

Resultado: base global del agente migrada a DB y operativa.

- [x] Colecciones creadas: agent_identity, agent_personality, agent_goals, agent_system_model
- [x] Seed inicial operativo (scripts/seed_agent_identity.py)
- [x] Endpoint de invalidacion de cache activo

### Fase 1 — identity_loader

Resultado: carga de identidad global integrada al pipeline de contexto.

- [x] Nodo app/agents/agente_v2/nodes/context/identity_loader.py
- [x] Campos de identidad agregados a state.py
- [x] Integracion al context_subgraph
- [x] Ensamblado de contexto consume docs de identidad desde state

### Fase 2 — identity_block desde DB

Completado:

- [x] Ensamblado desde state.agent_identity_doc + state.agent_personality_doc
- [x] Integracion de agent_goals_doc en system prompt (initiative/personalidad)

Pendiente:

- [ ] Integracion explicita de agent_system_model_doc en prompt final
- [ ] Test A/B de equivalencia funcional del bloque de identidad

### Fase 3 — memory_update + user_state + objective_state + agent_internal_state

Pendientes clave:

- [ ] Servicios user_state_service.py y objective_service.py
- [ ] Nodo nodes/memory_update.py con reglas deterministicas + escrituras bulk
- [ ] Refactor de reflection.py para producir solo structured_observations
- [ ] Migracion user_summary_context -> user_state

### Fase 4 — world_model + world_events + learning_memory + memory_loader

Pendientes clave:

- [ ] world_model_service.py y learning_memory_service.py
- [ ] nodes/memory_loader.py con carga concurrente (asyncio.gather)
- [ ] Aplicacion de eventos de turno a world_model + world_events

### Fase 5 — cognitive_context_builder + refactorizacion context_loader

Pendientes clave:

- [ ] nodes/cognitive_context_builder.py con ranking + budget de tokens
- [ ] Mover construccion de contexto pesado fuera de context_loader
- [ ] Remover hardcodes restantes de identidad

### Fase 6 — Cleanup

Pendientes clave:

- [ ] Eliminar fallback a user_summary_context
- [ ] Archivar coleccion legacy y limpiar deuda tecnica remanente

---

## Conversational roadmap (Agente V2 Development Milestones)

| # | Nombre | Estado v1 | Estado v2 | Archivo |
|---|--------|-----------|-----------|---------|
| 1 | Conversation Awareness | Completada | Completada | [FASE_01](roadmap complet/FASE_01_CONVERSATION_AWARENESS.md) |
| 2 | Session Working Memory | Completada | Completada | [FASE_02](roadmap complet/FASE_02_SESSION_WORKING_MEMORY.md) |
| 3 | Reference Resolution | No implementada | Completada | [FASE_03](roadmap complet/FASE_03_REFERENCE_RESOLUTION.md) |
| 4 | Conversational Personality | Parcial | Completada | [FASE_04](roadmap complet/FASE_04_CONVERSATIONAL_PERSONALITY.md) |
| 5 | Identity Context | Completada | Completada | [FASE_05](FASE_05_IDENTITY_CONTEXT.md) |
| 6 | User Understanding | Completada | Completada | [FASE_06](FASE_06_USER_UNDERSTANDING.md) |
| 7 | Long-Term Memory | Completada | Completada | [FASE_07](FASE_07_LONG_TERM_MEMORY.md) |
| 8 | Intent & Understanding | Parcial | No implementada | [FASE_08](FASE_08_INTENT_UNDERSTANDING.md) |
| 9 | Planning & Reasoning | Parcial | No implementada | [FASE_09](FASE_09_PLANNING_REASONING.md) |
| 10 | Tool Awareness | Completada | Completada | [FASE_10](FASE_10_TOOL_AWARENESS.md) |
| 11 | Tool Execution | Completada | No implementada | [FASE_11](FASE_11_TOOL_EXECUTION.md) |
| 12 | Workflow Intelligence | Completada | No implementada | [FASE_12](FASE_12_WORKFLOW_INTELLIGENCE.md) |
| 13 | MCP & External Systems | No implementada | No implementada | [FASE_13](FASE_13_MCP_EXTERNAL_SYSTEMS.md) |
| 14 | Autonomous Agent Layer | No implementada | No implementada | [FASE_14](FASE_14_AUTONOMOUS_AGENT.md) |

---

## Notas de progreso (resumidas)

### 2026-06-01

- Inicio formal del roadmap
- Fase 0 completada

### 2026-06-02

- Fase 1 completada con identity_loader + cache TTL
- Correccion critica de orden de SystemMessage (ensamblado centralizado en chat)
- Refactor de topologia: context_subgraph integrado al grafo principal
- Fase 3 conversacional implementada (reference_resolver)
- Fase 4 conversacional completada (personality + initiative rules)
- Validacion por logs operativa
- Rama publicada: agente_v2/fase-4-personality-complete

### 2026-06-02 (continuacion 2)

- Fase 10 (Tool Awareness) implementada:
  - Nuevo nodo tool_context_loader: lee catalog_apps (cache 10min) + user_connected_accounts (fresco por turno)
  - Multi-cuenta soportada: si el usuario tiene 2+ cuentas de la misma app, Shifu pregunta cuál usar
  - Bloque ## Platform Context inyectado en SystemMessage: apps conectadas + catálogo disponible
  - Shifu ya no inventa plataformas externas (Make, Zapier) ni dice "no tengo acceso"
  - Log: [tool_context_loader] connected=N available=M catalog=31

### 2026-06-02 (continuacion)

- Verificacion de Fase 5 (Identity Context): completada, sin pendientes
  - identity_loader operativo con cache TTL 1h y fallback a hardcodes
  - _build_identity_block() en chat.py consume todos los campos de DB: nombre, empresa, fundadores, proposito, mision, principios, restricciones, CREATOR RULE
  - Ningun nombre o empresa hardcodeado en logica de identidad
- Fase 7 (Long-Term Memory) con pipeline completo implementado:
  - long_term_memory_loader: carga user_global_memory desde MongoDB, inyecta como bloque de sistema
  - memory_saver: guarda summary de conversacion + dispara background jobs para diary y global memory
  - Pipeline: conv summary → user_daily_diary (por dia) → user_global_memory (ultimos 14 dias)