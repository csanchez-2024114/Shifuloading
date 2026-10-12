# Phase 12 — Workflow Intelligence

**Estado:** ❌ No implementada en v2 (v1 lo tenía completo)

---

## Qué hace

Shifu puede crear, entender, y orquestar workflows de automatización. No solo ejecuta herramientas una vez — diseña flujos que se ejecutan solos en el futuro: "cuando llegue un email de un cliente, guárdalo en Notion y notifícame por Slack".

---

## Objetivos

| Objetivo | Estado | Descripción | Verificación en debug |
|----------|--------|-------------|----------------------|
| Workflow Creation | ❌ | Diseñar un workflow desde lenguaje natural | Shifu produce un JSON de workflow a partir de la descripción del usuario |
| Workflow Understanding | ❌ | Leer un workflow existente y explicarlo en lenguaje natural | Shifu describe correctamente qué hace el workflow |
| Workflow Orchestration | ❌ | Ejecutar los pasos de un workflow en orden con manejo de errores | El workflow corre sin intervención humana |
| Automation Planning | ❌ | Planificar qué automatizaciones necesita el usuario para su objetivo | Shifu sugiere workflows relevantes al contexto del usuario |
| Process Optimization | ❌ | Detectar ineficiencias en workflows existentes y proponer mejoras | "Este workflow puede simplificarse así..." |

---

## Cómo lo tenía v1

**`process_discovery/`** — sistema completo:
- `session_manager.py` — manejaba sesiones de discovery con estado multi-turno
- `workflow_builder.py` — construía el JSON de workflow desde observaciones
- `discovery_prompt.py` — prompts especializados para descubrimiento de procesos
- `process_builder.py` — ensamblaba el proceso final

**Colecciones:**
- `processes` — definiciones de procesos del usuario
- `workflows` — workflows activos con triggers y acciones
- `processes_temp` — borradores durante el discovery

**El discovery flow:**
1. Shifu detecta que el usuario quiere automatizar algo (stage = `discovery`)
2. Activa modo discovery: hace preguntas dirigidas para entender trigger, condiciones, y acciones
3. Construye el JSON del workflow paso a paso
4. Confirma con el usuario antes de guardar
5. Workflow queda activo y listo para ejecutarse

---

## Implementación propuesta para v2

**Nuevos nodos:**

```
(cuando intent = crear workflow)
intent_reconstructor → workflow_planner → chat
                              ↓
                    (al final del turno)
                    workflow_builder_node → guarda en MongoDB
```

**Estado:**
```python
state.workflow_session: Optional[dict]  # estado del discovery en curso
state.workflow_draft: Optional[dict]    # JSON del workflow construido
```

**Estructura de un workflow:**
```json
{
  "user_id": "...",
  "title": "Alertas de emails de clientes",
  "trigger": {
    "type": "gmail_new_email",
    "filter": "from:@cliente.com"
  },
  "conditions": [
    { "field": "subject", "contains": "urgente" }
  ],
  "actions": [
    { "type": "notion_create_page", "database": "CRM" },
    { "type": "slack_send_message", "channel": "#alertas" }
  ],
  "status": "active"
}
```

---

## Cómo verificarlo en la interfaz de debug

1. Decir: "quiero que cuando llegue un email de un cliente importante me avises por Slack"
2. Shifu debe iniciar modo discovery: "¿De qué clientes? ¿Cómo los identifico?"
3. Después de responder las preguntas → Shifu muestra el workflow propuesto
4. Confirmar → se guarda en `workflows` collection
5. En MongoDB: `db.workflows.findOne({user_id: "..."})` debe mostrar el workflow activo

---

## Dependencias

- Requiere Phase 8 ❌ (Intent — detectar cuándo el usuario quiere crear un workflow vs simplemente preguntar)
- Requiere Phase 11 ❌ (Tool Execution — para ejecutar los pasos del workflow)
- Requiere Phase 9 ❌ (Planning — para guiar el discovery en múltiples turnos)

---

## Prioridad sugerida

Muy alta — es el producto principal de HyperShifu. Pero es la fase más compleja y requiere las bases de Phase 8, 9, 10 y 11. Implementar al final del stack de automatización.
