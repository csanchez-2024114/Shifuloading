# Phase 9 — Planning & Reasoning

**Estado:** ❌ No implementada

---

## Qué hace

Shifu puede descomponer un objetivo complejo en pasos, razonar sobre cómo lograrlo, y mantener un plan activo que guía la conversación hasta que se completa. No solo responde — ejecuta una secuencia de pasos con estado.

---

## Objetivos

| Objetivo | Estado | Descripción | Verificación en debug |
|----------|--------|-------------|----------------------|
| Task Decomposition | ❌ | Partir un objetivo grande en pasos concretos y ordenados | Shifu lista los pasos antes de empezar a ejecutar |
| Goal Planning | ❌ | Crear un plan con pasos, dependencias y estado (pending/done) | Plan visible como estructura en el state |
| Multi-Step Reasoning | ❌ | Razonar paso a paso antes de dar una respuesta final | "Pensando..." o trace visible en debug |
| Execution Planning | ❌ | Decidir qué herramienta usar en cada paso | Shifu explica por qué elige cada herramienta |
| Decision Making | ❌ | Elegir entre alternativas cuando hay más de un camino posible | Shifu presenta opciones y pregunta o decide según contexto |

---

## Por qué importa

Sin planning:
- Shifu solo puede ayudar con tareas de un solo paso
- Para crear un workflow complejo, el usuario tiene que guiar cada microdetalle
- Si una herramienta falla en el paso 3, Shifu no sabe retomar desde ahí

Con planning:
- El usuario describe el objetivo final → Shifu construye el plan → ejecuta paso a paso
- El usuario puede pausar, corregir y retomar desde cualquier punto
- Los planes persisten en MongoDB (`objective_state`) — sobreviven entre sesiones

---

## Implementación propuesta

**Colección MongoDB:** `objective_state`

```json
{
  "user_id": "...",
  "title": "Crear workflow de leads",
  "steps": [
    { "id": "1", "description": "Conectar Gmail", "status": "completed", "completed_at": "..." },
    { "id": "2", "description": "Configurar trigger de nuevo email", "status": "in_progress" },
    { "id": "3", "description": "Agregar acción de notificación", "status": "pending" }
  ],
  "current_step": "2",
  "progress_pct": 33,
  "status": "active"
}
```

**Nuevo nodo: `planner`**

Posición en graph:
```
intent_reconstructor → planner → chat
```

**Qué hace:**
1. Si `intent_context.user_goal` es nuevo y complejo → crea nuevo `objective_state`
2. Si ya hay un objetivo activo → carga los pasos y el step actual
3. Inyecta el plan como SystemMessage con el paso actual resaltado
4. Después del chat: actualiza el step completado si el turno lo resolvió

---

## Cómo verificarlo en la interfaz de debug

1. Pedir algo complejo: "quiero crear un flujo que cuando llegue un email de un cliente, lo guarde en Notion y me notifique por Slack"
2. Shifu debe responder con un plan de pasos antes de preguntar por el primero
3. Confirmar primer paso → Shifu avanza al segundo automáticamente
4. Cerrar conversación y volver → Shifu retoma desde donde quedaron
5. En MongoDB: `db.objective_state.findOne({user_id: "..."})` debe mostrar el plan con `status: active`

---

## Dependencias

- Requiere Phase 8 ❌ (Intent — para saber qué planificar)
- Requiere Phase 11 ❌ (Tool Execution — para ejecutar cada paso del plan)
- `objective_state` colección nueva en MongoDB

---

## Prioridad sugerida

Alta a mediano plazo. Es lo que diferencia a Shifu de un chatbot — la capacidad de guiar al usuario en objetivos multi-paso. Implementar después de Phase 8.
