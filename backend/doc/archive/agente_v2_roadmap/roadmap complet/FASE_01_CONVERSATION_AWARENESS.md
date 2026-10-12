# Phase 1 — Conversation Awareness

**Estado:** ✅ Completa

---

## Qué hace

Cada turno, Shifu analiza el historial reciente de la conversación y extrae un mapa de la situación actual: de qué se está hablando, qué quiere lograr el usuario, en qué etapa están, y qué quedó sin responder.

---

## Objetivos implementados

| Objetivo | Estado | Verificación en debug |
|----------|--------|-----------------------|
| Active Topic — qué tema se discute ahora | ✅ | Campo `active_topic` en el log de ConvContextBuilder |
| Current Goal — qué intenta lograr el usuario | ✅ | Campo `current_goal` en el log |
| Conversation Stage — en qué etapa está la conversación | ✅ | Campo `stage` en el log (idle / discovery / requirements / planning / execution / clarification / completed) |
| Open Questions — preguntas hechas sin responder | ✅ | Campo `open_q` en el log, cuenta de preguntas abiertas |
| Recent Entities — entidades concretas mencionadas (apps, nombres, servicios) | ✅ | Campo `entities` en el log |

---

## Cómo verificarlo en la interfaz de debug

1. Abrir una conversación nueva
2. Escribir algo como: "quiero conectar mi Gmail para recibir alertas"
3. En los logs buscar: `[ConvContextBuilder] topic=... stage=... goal=... entities=...`
4. El siguiente turno Shifu ya debe tener contexto del tema y adaptar su respuesta

**Primera conversación:** no hay contexto (< 2 mensajes). Shifu opera solo con perfil del usuario.
**Segundo turno en adelante:** `conversation_context_builder` escribe `conversation_context` en state,
y `chat_node` ensambla ese bloque dentro del SystemMessage final del turno.

---

## Nodos responsables

`conversation_context_builder` — [nodes/conversation_context_builder.py](../nodes/conversation_context_builder.py)

- Modelo: `gpt-4.1-nano` (T=0, max_tokens=250)
- Ventana: últimos 8 mensajes Human/AI
- Stateless — se reconstruye cada turno desde el historial
- No inyecta mensajes directamente; solo actualiza `conversation_context` en state

`chat` — [nodes/chat.py](../nodes/chat.py)

- Ensambla el SystemMessage final del turno (identity + profile + long-term + Phase 1 + Phase 2)
- Consume `conversation_context` y lo convierte en bloque de contexto conversacional

`context_subgraph` — [context_subgraph.py](../context_subgraph.py)

- Ejecuta el flujo de contexto completo:
	`identity_loader -> user_context_loader -> long_term_memory_loader -> conversation_context_builder -> working_memory_builder`

---

## Stages disponibles

| Stage | Cuándo aplica |
|-------|--------------|
| `idle` | Sin objetivo claro, conversación casual |
| `discovery` | Explorando qué quiere el usuario |
| `requirements` | Recabando detalles de lo que necesita |
| `planning` | Diseñando solución o flujo |
| `execution` | Ejecutando pasos concretos |
| `clarification` | Resolviendo ambigüedad |
| `completed` | Objetivo alcanzado |

El stage también afecta la temperatura del LLM (más frío en `execution`, más cálido en `idle`).

---

## Limitaciones conocidas

- Ventana de 8 mensajes — si la conversación tiene > 8 turnos, el topic puede perder contexto muy antiguo (Phase 2 — Working Memory lo compensa)
- No hay resolución de referencias entre conversaciones distintas (Phase 3)
