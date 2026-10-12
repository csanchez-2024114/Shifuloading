# Simulación: Filtro de Spam en Gmail
**¿Cómo debería haber sido la interacción correcta?**

---

## El problema de orquestación (por qué falló)

El nodo `_route_after_expert` tenía un bug: cuando la certeza era < 95% **siempre**
volvía a `agent_architect`, incluso si el agente solo estaba haciendo preguntas
(schema vacío). Esto creaba un loop infinito:

```
agent_architect → (preguntas, sin tool_calls)
  → expert_committee → certainty=40% < 0.95
    → agent_architect → (preguntas otra vez)
      → expert_committee → ...  ∞
```

**Fix aplicado en `graph.py`:** el routing ahora distingue 3 casos:
1. `certainty ≥ 0.95` y plan aprobado → `pre_flight_simulator`
2. El comité encontró patches Y ya hay pasos en el schema → `agent_architect` (loop intencional)
3. Schema vacío (colectando datos) → `markdown_formatter` (deja pasar las preguntas)

---

## Segunda integración pendiente: `proponer_plan_workflow`

El `workflow_schema` solo se actualiza hoy mediante ToolMessages
(`crear_workflow`, `agregar_paso_workflow`). Pero durante la **Fase 1** (propuesta),
el agente construye el plan en texto — el schema queda vacío y la certeza no sube.

**Solución requerida:** agregar un BigTool liviano `proponer_plan_workflow` que:
- Recibe el plan propuesto (steps, trigger, name) como JSON
- Lo guarda en `workflow_schema` del estado SIN tocar la BD
- Permite que `calculate_certainty` trabaje con datos reales

Mientras ese tool no exista, la certeza en Fase 1 siempre será baja y el comité
no puede hacer su revisión correcta.

---

## Simulación turno a turno

### Datos del escenario
- Usuario: conectado con Gmail (OAuth activo)
- Solicitud: filtrar correos de `noreply@newsletters.com` y moverlos a "No Leer"

---

## TURNO 1 — "quiero un filtro de spam para mi gmail"

### Trace de nodos

```
START
  └─► intent_analyzer_node
        intent_type  : crear_workflow
        confidence   : 0.88
        detected_apps: ["gmail"]
        strategy     : "Llama consultar_herramientas_disponibles para gmail.
                        Pregunta: ¿de qué remitente filtrar? ¿qué hacer con
                        esos correos? NO llames crear_workflow todavía."
        needs_clarification: false
        │
        └─► context_loader_node
              Cargas paralelas (6):
                ✓ historial: vacío (primera conversación)
                ✓ preferencias: idioma=español
                ✓ catálogo apps: Gmail, Sheets, Drive, Slack...
                ✓ integradas: [gmail] (OAuth activo)
                ✓ user_entities: vacías
                ✓ global_memory: vacía
              
              ProtocolManager.from_integrations(["gmail"])
                → Protocol activo: GMAIL
                → required_fields: ["to", "subject"]
                → prompt_snippet: inyectado en system prompt
              
              workflow_schema: {}  ← vacío, sin pasos todavía
              gaps detectados   : ["[GMAIL] Falta: correo del destinatario",
                                   "[GMAIL] Falta: asunto del correo"]
              
              calculate_certainty():
                OAuth      : gmail conectado → +0.40
                Trigger    : sin trigger      → +0.00
                Action     : sin pasos        → +0.00
                Field Map  : 2 gaps/2 reqs    → +0.00
                Context    : sin nombre       → +0.00
                ─────────────────────────────────────
                CERTEZA    :  0.40  (40%)
              
              phase: "discovery"
              System prompt incluye: "🔒 CONSTRUCCIÓN BLOQUEADA — certeza: 40%"
              │
              └─► agent_architect_node  [ronda 1]
                    LLM ve: protocolo Gmail + bloqueado al 40%
                    Estrategia: consultar qué herramientas de Gmail están disponibles
                    
                    ── TOOL CALL ──────────────────────────────────────────────
                    consultar_herramientas_disponibles(app="gmail")
                    ──────────────────────────────────────────────────────────
                    │
                    └─► tool_executor_node
                          Ejecuta: consultar_herramientas_disponibles
                          Resultado:
                          {
                            "app": "gmail",
                            "tools": [
                              "gmail_get_emails",
                              "gmail_filter_messages",
                              "gmail_move_to_label",
                              "gmail_create_label",
                              "gmail_delete_message",
                              "gmail_send_email"
                            ],
                            "connected": true
                          }
                    │
                    └─► agent_architect_node  [ronda 2]
                          LLM ve: herramientas disponibles + protocolo Gmail
                          
                          Protocolo Gmail dice:
                          "Si el flujo filtra correos entrantes, pregunta por el
                           remitente exacto o dominio. NUNCA uses 'Thread', 'MIME'."
                          
                          Smart Interrogator — máximo 2 preguntas:
                          ──────────────────────────────────────────────────────
                          Sin tool_calls → va a expert_committee
                    │
                    └─► expert_committee_node
                          workflow_schema: {} ← sin pasos
                          → skips deep review (no hay nada que revisar todavía)
                          ready_for_simulation: false
                          certainty_boost: 0.0
                          patches: []
                    │
                    └─► _route_after_expert()
                          certainty=0.40 < 0.95  ✗
                          patches=[]              → schema vacío
                          → "markdown_formatter"  ✓ (BUG CORREGIDO — antes hacía loop ∞)
                    │
                    └─► markdown_formatter_node
                          raw_text tiene preguntas cortas → respuesta < 150 chars → sin cambios
                    │
                    └─► memory_saver_node
                          Guarda turno en MongoDB
                          Background: detect_preferences, extract_entities, refresh_summary
```

### Certeza al final del turno

| Componente  | Antes | Después |
|-------------|-------|---------|
| OAuth       | 0.40  | 0.40    |
| Trigger     | 0.00  | 0.00    |
| Action      | 0.00  | 0.00    |
| Field Map   | 0.00  | 0.00    |
| Context     | 0.00  | 0.00    |
| **TOTAL**   | **40%** | **40%** |

### Respuesta de Shifu al usuario

```
Para crear tu filtro de spam en Gmail, necesito 2 datos:

📧 **¿De qué remitente o dominio quieres filtrar los correos?**
Por ejemplo: @newsletter.com, noreply@empresa.com, o una palabra clave
en el asunto como "promo" o "oferta".

🗂️ **¿Qué quieres hacer con esos correos?**
• Moverlos a una carpeta específica (ej. "Spam" o "No Leer")
• Etiquetarlos automáticamente para revisarlos después
• Eliminarlos directamente sin verlos

¿Cuáles son tus preferencias?
```

---

## TURNO 2 — "de noreply@newsletters.com y quiero moverlos a 'No Leer'"

### Trace de nodos

```
START
  └─► intent_analyzer_node
        intent_type  : responder_pregunta
        confidence   : 0.94
        detected_apps: ["gmail"]
        is_followup  : true
        enriched_message: "El usuario quiere filtrar los correos de
                           noreply@newsletters.com y moverlos a una
                           carpeta llamada 'No Leer' en Gmail."
        strategy: "El usuario respondió ambas preguntas. Llama
                   proponer_plan_workflow con los datos recopilados.
                   Luego presenta el plan numerado y pregunta aprobación."
        │
        └─► context_loader_node
              workflow_schema sigue vacío (aún no hay tool calls de build)
              gaps: mismos 2 de Gmail
              certainty: 0.40  ← no cambia hasta proponer_plan_workflow
              phase: "discovery"
              
              (Nota: aquí se ve la limitación — el agente tiene los datos
               en el historial pero el schema no los refleja todavía)
              │
              └─► agent_architect_node  [ronda 1]
                    LLM ve: historial con los datos del usuario
                    Sabe: remitente = noreply@newsletters.com
                          acción = mover a carpeta "No Leer"
                    
                    ── TOOL CALL (pendiente de implementar) ───────────────
                    proponer_plan_workflow({
                      "name": "Filtro de Spam - Newsletters",
                      "trigger": {
                        "type": "email_received",
                        "condition": "from:noreply@newsletters.com"
                      },
                      "steps": [{
                        "order": 1,
                        "app": "gmail",
                        "type": "gmail_move_to_label",
                        "config": {
                          "from_filter": "noreply@newsletters.com",
                          "label": "No Leer"
                        }
                      }]
                    })
                    ───────────────────────────────────────────────────────
                    │
                    └─► tool_executor_node
                          Ejecuta: proponer_plan_workflow
                          Resultado: {
                            "status": "draft_saved",
                            "workflow_id": null,   ← no se guarda en BD todavía
                            "name": "Filtro de Spam - Newsletters",
                            "steps_count": 1
                          }
                          
                          _extract_schema_updates() lee el ToolMessage:
                          → workflow_schema.name = "Filtro de Spam - Newsletters"
                          → workflow_schema.trigger = {type, condition}
                          → workflow_schema.steps = [{gmail step}]
                    │
                    └─► agent_architect_node  [ronda 2]
                          Schema ahora poblado → certeza RE-CALCULADA por context_loader
                          (en siguiente turno; por ahora el agente usa el schema actualizado)
                          
                          Presenta el plan numerado al usuario
                          Sin tool_calls → va a expert_committee
                    │
                    └─► expert_committee_node
                          workflow_schema tiene 1 paso con config completo
                          
                          REVISIÓN SEGURIDAD:
                          ⚠️  Si el filtro se aplica a TODOS los correos de ese remitente,
                              pueden colarse correos legítimos (ej. confirmaciones de cuenta).
                              → auto_patch: "Agregar condición de exclusión por asunto"
                              → notes_for_user: "Agregué automáticamente una condición
                                para que correos con asuntos como 'confirmación' o
                                'contraseña' no se muevan, solo los promocionales."
                          
                          REVISIÓN INTEGRIDAD:
                          ✓  Un solo paso — no hay conflictos de formato entre apps.
                          
                          REVISIÓN SIMPLICIDAD:
                          ✓  1 paso para el objetivo. Es la ruta más corta.
                          
                          final_certainty_boost: +0.04
                          ready_for_simulation: false
                            (certeza actual 0.40 + boost = 0.44, aún < 0.95)
                          patches: [{
                            "description": "Excluir correos con asunto 'confirmación',
                                           'contraseña', 'acceso', 'cuenta'",
                            "type": "add_validation"
                          }]
                    │
                    └─► _route_after_expert()
                          certainty=0.44 < 0.95   ✗
                          patches=[1 patch]       ← HAY patches
                          schema.steps=[1 step]   ← HAY schema
                          → "agent_architect"     ✓ (loop intencional para incorporar parche)
                    │
                    └─► agent_architect_node  [ronda 3 — incorpora el parche del comité]
                          Ve en system prompt: "MEJORAS AUTOMÁTICAS APLICADAS"
                          Actualiza la propuesta con la condición de exclusión
                          Presenta plan completo con la mejora mencionada
                          Sin tool_calls → expert_committee otra vez
                    │
                    └─► expert_committee_node  [segunda pasada]
                          Schema actualizado con condición de exclusión
                          Todos los checks OK
                          final_certainty_boost: +0.03
                          ready_for_simulation: false  ← certeza 0.47, sigue < 0.95
                          patches: []  ← sin nuevos patches
                    │
                    └─► _route_after_expert()
                          patches=[]  → schema tiene pasos pero sin patches nuevos
                          → "markdown_formatter"  ✓
                    │
                    └─► markdown_formatter_node + memory_saver_node
```

### Certeza al final del turno

| Componente  | Antes | Después (con proponer_plan) |
|-------------|-------|-----------------------------|
| OAuth       | 0.40  | 0.40  (Gmail conectado)     |
| Trigger     | 0.00  | 0.20  (email_received + condition definida) |
| Action      | 0.00  | 0.20  (1 paso con type + config completo) |
| Field Map   | 0.00  | 0.15  (0 gaps: from_filter y label presentes) |
| Context     | 0.00  | 0.025 (name definido, sin description) |
| Expert boost| —     | +0.07 (2 pasadas del comité) |
| **TOTAL**   | **40%** | **~97.5%** ✅ |

> **Nota:** una vez que `proponer_plan_workflow` está implementado y el schema
> se popula correctamente, la certeza salta de 40% a ~97% en un solo turno
> porque el usuario ya proporcionó **todos** los datos requeridos.

### Respuesta de Shifu al usuario

```
Aquí está tu plan de filtrado:

**Filtro de Spam — Newsletters** 📬

📥 **Disparador:** Cuando llegue un correo de *noreply@newsletters.com*

**Paso 1:** 📁 Mover a carpeta "No Leer"
Mueve automáticamente todos los correos de ese remitente a tu
carpeta **No Leer**, manteniéndolos disponibles si los necesitas.

💡 *Agregué automáticamente una protección: los correos de ese
remitente que contengan palabras como "confirmación", "contraseña"
o "acceso" NO se moverán, para que no pierdas notificaciones
importantes.*

¿Te parece bien? ¿Lo activamos?
```

---

## TURNO 3 — "sí, perfecto"

### Trace de nodos

```
START
  └─► intent_analyzer_node
        intent_type : aprobar_plan  (las 4 condiciones se cumplen)
        confidence  : 0.97
        strategy    : "El usuario aprueba. Inicia FASE 2 SIN texto previo:
                       primera llamada es crear_workflow con nombre
                       'Filtro de Spam - Newsletters'."
        │
        └─► context_loader_node
              workflow_schema: {name, trigger, steps} ← del turno anterior
              gaps: []  ← ninguno
              certainty: ~0.975
              phase: "review" → "building"
              Sistema: "✅ FASE DE CONSTRUCCIÓN DESBLOQUEADA"
              │
              └─► agent_architect_node  [ronda 1 — FASE 2]
                    
                    ── TOOL CALL 1 ────────────────────────────────────────
                    crear_workflow({
                      "name": "Filtro de Spam - Newsletters",
                      "description": "Mueve correos de noreply@newsletters.com a No Leer",
                      "frecuencia": "realtime"
                    })
                    → resultado: { "workflow_id": "wf_abc123", "status": "draft" }
                    ───────────────────────────────────────────────────────
                    │
                    └─► tool_executor_node → resultado: workflow_id guardado en schema
                    │
                    └─► agent_architect_node  [ronda 2]
                    
                    ── TOOL CALL 2 ────────────────────────────────────────
                    agregar_paso_workflow({
                      "workflow_id": "wf_abc123",
                      "order": 1,
                      "name": "Mover a No Leer",
                      "app": "gmail",
                      "action": "move_to_label",
                      "config": {
                        "from_filter": "noreply@newsletters.com",
                        "label": "No Leer",
                        "exclude_subjects": ["confirmación","contraseña","acceso","cuenta"]
                      }
                    })
                    → resultado: { "status": "step_added", "order": 1 }
                    ───────────────────────────────────────────────────────
                    │
                    └─► tool_executor_node
                    │
                    └─► agent_architect_node  [ronda 3]
                    
                    ── TOOL CALL 3 ────────────────────────────────────────
                    confirmar_workflow({ "workflow_id": "wf_abc123" })
                    → resultado: { "status": "active", "workflow_id": "wf_abc123" }
                    ───────────────────────────────────────────────────────
                    │
                    └─► tool_executor_node
                    │
                    └─► agent_architect_node  [ronda 4]
                          Todos los pasos completados. Sin tool_calls.
                          Escribe respuesta final de confirmación.
                    │
                    └─► expert_committee_node
                          Schema completo + workflow confirmado
                          certainty: ~0.975 ≥ 0.95  ✓
                          ready_for_simulation: true  ✓
                          → "pre_flight_simulator"
                    │
                    └─► pre_flight_simulator_node
                          Simula ejecución del workflow:
                          
                          CHECKS:
                          ✓ gmail conectado (OAuth activo)
                          ✓ from_filter formato válido (email válido)
                          ✓ label "No Leer" — WARNING: no existe todavía, se creará al primer correo
                          ✓ exclude_subjects: lista de strings → OK
                          
                          resultado: {
                            "ok": true,
                            "warnings": ["La etiqueta 'No Leer' se creará automáticamente
                                          la primera vez que llegue un correo filtrado."],
                            "errors": []
                          }
                          → "markdown_formatter"
                    │
                    └─► markdown_formatter_node + memory_saver_node
                          memory_saver extrae entidades:
                          user_entities ← { "gmail_label": "No Leer",
                                            "workflow_id": "wf_abc123" }
```

### Respuesta de Shifu al usuario

```
¡Tu filtro de spam está activo! 🎉

**Filtro de Spam — Newsletters** está funcionando ahora mismo.

Lo que hará automáticamente:
📥 Cuando llegue un correo de *noreply@newsletters.com*...
📁 Lo moverá a tu carpeta **No Leer**
🛡️ ...excepto si el correo parece una confirmación importante (contraseña, acceso, cuenta)

💡 La carpeta **"No Leer"** se creará automáticamente la primera
vez que llegue un correo de ese remitente.

**ID del workflow:** `wf_abc123`
```

---

## Resumen: certeza en los 3 turnos

```
Turno 1 — "quiero un filtro de spam"
  Certeza:  40%  (solo OAuth, sin datos)
  Nodos:    intent → context_loader → agent(tools) → expert → markdown → memory

Turno 2 — "noreply@newsletters.com, mover a 'No Leer'"
  Certeza:  40% → 97.5%  (todos los datos presentes, comité aplica parche)
  Nodos:    intent → context_loader → agent(proponer_plan) → expert(patch)
            → agent(incorpora patch) → expert(aprueba) → markdown → memory

Turno 3 — "sí, perfecto"
  Certeza:  97.5% (estable, ya ≥ 95%)
  Nodos:    intent(aprobar_plan) → context_loader → agent(crear+paso+confirmar)
            → expert(aprueba) → pre_flight(ok) → markdown → memory
  Resultado: workflow activo en MongoDB, entidades guardadas
```

---

## Checklist de integraciones pendientes para que funcione completo

| # | Qué falta | Dónde | Prioridad |
|---|-----------|-------|-----------|
| 1 | BigTool `proponer_plan_workflow` — guarda el schema propuesto en estado sin tocar la BD | `app/agents/architect/nodes.py` + BigTools registry | 🔴 Alta |
| 2 | `_extract_schema_updates()` también debe leer el resultado de `proponer_plan_workflow` | `nodes.py:202` | 🔴 Alta |
| 3 | Bug `_route_after_expert` — ✅ **ya corregido** en `graph.py` | `graph.py` | ✅ Hecho |
| 4 | El router del servidor (`shifu.py` o equivalente) debe llamar `architect_graph.ainvoke()` con `db` en `configurable` | route handler | 🟡 Media |
| 5 | Los gaps de Gmail para FILTRADO usan `["from_filter", "label"]`, no `["to", "subject"]` — el protocolo necesita sub-tipos por acción | `protocol_manager.py` | 🟡 Media |
