# Phase 2 — Session Working Memory

**Estado:** ✅ Completa

---

## Qué hace

Mantiene un mapa de lo que importa dentro de la sesión actual: el proyecto activo, la tarea en curso, los hechos que el usuario declaró, las decisiones tomadas, y los hilos abiertos. Se reconstruye cada turno desde el historial reciente — sin base de datos.

El nodo de Phase 2 extrae y guarda `working_memory_context` en state; luego `chat_node` lo incorpora al SystemMessage final del turno.

---

## Objetivos implementados

| Objetivo | Estado | Verificación en debug |
|----------|--------|-----------------------|
| Current Focus — qué recibe más atención ahora mismo | ✅ | Log `[working_memory_builder] facts=N decisions=N threads=N` |
| Active Project — proyecto principal de la conversación | ✅ | Ensamblado por `chat_node` en SystemMessage como "Active Project:" |
| Active Task — tarea específica en curso | ✅ | Ensamblado por `chat_node` en SystemMessage como "Active Task:" |
| Important Facts — hechos declarados por el usuario | ✅ | Ensamblado por `chat_node` en SystemMessage bajo "Important Facts:" |
| Decisions — decisiones confirmadas en la sesión | ✅ | Ensamblado por `chat_node` en SystemMessage bajo "Decisions:" |
| Open Threads — temas abiertos sin resolver | ✅ | Ensamblado por `chat_node` en SystemMessage bajo "Open Threads:" |

---

## Cómo verificarlo en la interfaz de debug

1. Abrir conversación nueva
2. Decir: "mi proyecto se llama HyperShifu y estoy construyendo el módulo de automatización"
3. Siguiente turno: en logs buscar `[working_memory_builder]` — debe mostrar `facts=1`
4. Hacer 5-10 turnos más y tomar una decisión: "ok, vamos a usar webhooks"
5. El log debe mostrar `decisions=1`
6. Preguntar 10 turnos después: "¿qué decidimos sobre la integración?" — Shifu debe recordarlo

En implementación actual:
- `working_memory_builder` no inyecta mensajes directamente.
- `chat_node` consume `working_memory_context` y arma el bloque "Working Memory Context" dentro del SystemMessage final.

**Límite de ventana:** últimos 20 mensajes. En sesiones muy largas (20+ turnos), hechos muy antiguos pueden no aparecer.

---

## Nodos responsables

`working_memory_builder` — [nodes/working_memory_builder.py](../nodes/working_memory_builder.py)

- Modelo: `gpt-4o-mini` (T=0, max_tokens=400)
- Ventana: últimos 20 mensajes Human/AI, truncados a 400 chars cada uno
- No-op si < 2 mensajes Human/AI en el historial
- Stateless — no escribe a DB
- Escribe `working_memory_context` en state

`chat` — [nodes/chat.py](../nodes/chat.py)

- Lee `working_memory_context`
- Construye el bloque "Working Memory Context" y lo incluye en el SystemMessage final del turno

`context_subgraph` — [context_subgraph.py](../context_subgraph.py)

- Ejecuta Phase 2 dentro del flujo de contexto consolidado
	(`identity_loader -> user_context_loader -> long_term_memory_loader -> conversation_context_builder -> working_memory_builder`)

---

## Diferencia con Phase 1

| Phase 1 | Phase 2 |
|---------|---------|
| ¿De qué hablamos ahora? | ¿Qué sabemos de esta sesión? |
| Ventana: 8 mensajes | Ventana: 20 mensajes |
| Topic, goal, stage, entities | Facts, decisions, threads, project, task |
| Se pierde entre conversaciones | También se pierde entre conversaciones (ver Phase 7) |

---

## Limitaciones conocidas

- Stateless: al cerrar la conversación, todo se pierde
- La persistencia cross-session está en Phase 7 (Long-Term Memory)
- Hechos de más de 20 turnos atrás pueden no capturarse
