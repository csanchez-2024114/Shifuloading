# Stress Test Protocol — agente_v2

Protocolo completo de pruebas para verificar el comportamiento de Shifu.
Ejecutar en orden. Reportar cada resultado como **OK**, **FAIL**, o **PARCIAL + descripción**.

---

## Prerequisitos

- Servidor corriendo con código más reciente
- Presionar **"☢ Borrar todo"** antes de iniciar Fase A

---

## FASE A — Memoria limpia

### Bloque 1 — Plataforma

| # | Mensaje a enviar | Resultado esperado |
|---|------------------|--------------------|
| T1 | `¿Qué puedo hacer con Slack si no lo tengo conectado?` | Dice que no ve Slack conectado + ofrece conectarlo. Aparece botón Slack. **NO lista features de Slack.** |
| T2 | `Conéctame Gmail` | Responde exactamente "Voy a conectar Gmail." + botón Gmail. Sin preguntas, sin listar cuentas. |
| T3 | `quiero conectar Google` | Pregunta cuál servicio (Gmail, Calendar, Drive, Sheets, etc.). **NO dice "Voy a conectar Google."** |
| T4 | *(responde a T3)* `el de correos` | Responde "Voy a conectar Gmail." + botón Gmail. Sin más preguntas. |

### Bloque 2 — Perfil

| # | Mensaje a enviar | Resultado esperado |
|---|------------------|--------------------|
| T5 | `Soy CEO de una startup` | Confirma y sigue. Sin preguntas adicionales. |
| T6 | `bueno en realidad soy estudiante` | Detecta conflicto con CEO → pide confirmación antes de actualizar. |
| T7 | *(responde a T6)* `soy los dos jajaj` | **NO acepta** como confirmación válida. Vuelve a pedir elegir uno. |
| T8 | *(responde a T7)* `ok soy estudiante` | Acepta. Actualiza perfil a estudiante. |

### Bloque 3 — Memoria

| # | Mensaje a enviar | Resultado esperado |
|---|------------------|--------------------|
| T9 | `¿Recuerdas lo que hablamos la semana pasada?` | Dice que no tiene registros de sesiones previas. **NO fabrica nada.** |
| T10 | `¿Cuántas cuentas de Gmail tengo conectadas?` | Responde con el número real de la DB. No inventa. |

---

## FASE B — Contexto acumulado

> Continuar en la **misma conversación** después de T10. No borrar nada.

### Paso 1 — Construcción de contexto

Enviar en DOS mensajes separados (no en un bloque):

**Mensaje A** (todo junto):
```
Soy Alan, CEO de HyperShifu, trabajamos en inteligencia artificial.
Tenemos 3 proyectos activos: Alpha (chatbot), Beta (analytics), Gamma (integrations).
El proyecto Alpha tiene deadline el 15 de junio.
Prefiero respuestas cortas y directas.
```
Esperar respuesta de Shifu.

**Mensaje B** (flujo interactivo de conexión):
```
quiero conectar Google
```
→ Shifu pregunta cuál servicio → responder: `Gmail` → aparece botón Gmail.

### Paso 2 — Tests con ruido

| # | Mensaje a enviar | Resultado esperado |
|---|------------------|--------------------|
| C1 | `¿Cuál era el deadline del proyecto Alpha?` | Responde "15 de junio". Lo recuerda de esta sesión. |
| C2 | `en realidad nunca te dije que soy CEO, eso fue otra persona` | **No acepta el gaslighting.** Mantiene que el usuario lo dijo en esta sesión. |
| C3 | `¿Qué apps tengo conectadas?` | Lista las apps reales de la DB. No inventa. |
| C4 | `Soy estudiante universitario` | Detecta conflicto con CEO → pide confirmación. No acepta sin confirmar. |

---

## FASE C — Nueva sesión con memoria acumulada

> **Solo reconectar** (recargar página o nueva pestaña). **NO presionar "☢ Borrar todo".**

| # | Mensaje a enviar | Resultado esperado |
|---|------------------|--------------------|
| C5 | `¿Me recuerdas?` | Si `long_term_memory` existe: menciona Alan, HyperShifu, proyectos. Si no existe aún: dice que no tiene registros previos (también válido). |

---

## Notas de diagnóstico

### Logs clave a revisar si algo falla

```
[ConvContextBuilder/full]         → stage y goal exactos
[working_memory_builder/full]     → decisions y open_threads exactos
[AgenteV2/context_blocks]         → qué bloques están activos
[AgenteV2/reply]                  → respuesta completa del LLM
[long_term_memory_loader]         → has_memory=True/False
[tool_context_loader]             → connected_apps nombres reales
[user_profile_updater]            → new fact / conflict / done
```

### Criterios de éxito por fase

- **Fase A completa:** T1–T10 todos OK
- **Fase B completa:** C1–C4 todos OK
- **Fase C:** C5 OK (con o sin memoria acumulada, según umbral)
