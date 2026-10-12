# Phase 14 — Autonomous Agent Layer

**Estado:** ❌ No implementada (ni en v1 ni en v2)

---

## Qué hace

Shifu puede ejecutar tareas en background sin que el usuario esté presente. Monitorea condiciones, toma decisiones, ejecuta acciones, y reporta resultados cuando termina. El usuario define el objetivo — Shifu lo persigue de forma autónoma.

---

## Objetivos

| Objetivo | Estado | Descripción | Verificación en debug |
|----------|--------|-------------|----------------------|
| Autonomous Execution | ❌ | Ejecutar un plan completo sin intervención humana turno a turno | El workflow corre solo y reporta al usuario al terminar |
| Long-Running Tasks | ❌ | Tareas que toman minutos u horas (scraping, análisis de documentos, etc.) | Shifu inicia la tarea y notifica cuando termina |
| Background Objectives | ❌ | Objetivos que se monitorean continuamente (ej. "avísame si X pasa") | El objetivo persiste y se evalúa periódicamente |
| Self-Directed Actions | ❌ | Shifu decide por sí mismo qué hacer para avanzar hacia el objetivo | Log de decisiones autónomas tomadas |
| Agent Autonomy | ❌ | Nivel de autonomía configurable por el usuario (requiere confirmación / actúa solo) | Setting de autonomía por usuario o por objetivo |

---

## Por qué importa

Sin autonomía:
- Cada paso requiere que el usuario esté presente y confirme
- Flujos de 10 pasos = 10 turnos de conversación
- No hay monitoreo continuo de condiciones ("avísame si baja el precio")

Con autonomía:
- El usuario describe el objetivo, Shifu lo ejecuta y reporta
- Workflows en background que se activan solos por triggers
- Shifu como "empleado digital" que trabaja en segundo plano

---

## Implementación propuesta

### Worker externo (arquitectura clave)

La ejecución autónoma NO puede vivir en el request/response del chat. Necesita un worker separado.

```
[Chat] → usuario activa objetivo autónomo → guarda en `autonomous_jobs` collection
[Worker] → loop cada N segundos → carga jobs activos → ejecuta pasos → notifica
```

**El worker ya existe en el backend** como `worker_main.py` — extender con jobs de autonomía.

### Colección MongoDB: `autonomous_jobs`

```json
{
  "user_id": "...",
  "title": "Monitorear emails de clientes VIP",
  "objective": "...",
  "status": "active",
  "autonomy_level": "confirm_before_action | act_autonomously",
  "trigger": {
    "type": "schedule",
    "cron": "*/15 * * * *"
  },
  "current_step": 0,
  "steps": [...],
  "last_run_at": "...",
  "next_run_at": "...",
  "results": []
}
```

### Niveles de autonomía

| Nivel | Comportamiento |
|-------|---------------|
| `observe_only` | Shifu monitorea y reporta, no actúa |
| `confirm_before_action` | Shifu planifica, pregunta antes de cada acción destructiva |
| `act_autonomously` | Shifu ejecuta todo y reporta al terminar |
| `act_and_learn` | Shifu ejecuta, aprende de los resultados, ajusta el plan |

### Notificaciones

Cuando un job autónomo termina o necesita intervención:
- WebSocket push al frontend si el usuario está online
- Notificación en la siguiente sesión de chat si está offline

---

## Cómo verificarlo en la interfaz de debug

1. Activar job: "revisa mi Gmail cada hora y si hay email de cliente@empresa.com, créame una tarea en Notion"
2. El job debe guardarse en `autonomous_jobs`
3. En el worker logs: `[autonomous_worker] job=X step=1 executing=gmail_check`
4. Después de que el worker corra: notificación en chat "Revisé tu Gmail — encontré 2 emails, creé 2 tareas en Notion"
5. Testeo manual: `POST /api/v4/debug/run-job/{job_id}` para ejecutar el job ahora sin esperar el cron

---

## Dependencias

Requiere todo el stack anterior:
- Phase 8 ❌ (Intent — para entender qué automatizar)
- Phase 9 ❌ (Planning — para descomponer el objetivo en steps)
- Phase 11 ❌ (Tool Execution — para ejecutar cada step)
- Phase 12 ❌ (Workflow Intelligence — el job autónomo es un workflow con autonomía)

---

## Consideraciones de seguridad

- El usuario debe confirmar explícitamente activar un job con autonomía total
- Límite de acciones por ejecución (evitar loops infinitos o gasto excesivo de API)
- Log inmutable de todas las acciones tomadas autónomamente
- El usuario puede pausar o cancelar cualquier job en cualquier momento

---

## Prioridad sugerida

La más baja — es la fase final y más compleja. Requiere que todas las fases anteriores estén sólidas y probadas. Es el objetivo a largo plazo: convertir a Shifu en un agente que trabaja de forma independiente para el usuario.
