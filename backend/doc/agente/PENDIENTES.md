# Lo que le falta al agente, por esfuerzo

## Plan de cierre (2026-10-11, v0.8.0)

Lo que queda, en sub-planes. Cada sub-plan lo construye un subagente Sonnet en archivos que no se cruzan con los demás; al terminar, un agente supervisor (Opus, esfuerzo bajo) revisa todos los cambios juntos antes del commit.

| Sub-plan | Qué | Quién | Estado |
|---|---|---|---|
| A | Google Docs en el sistema nuevo (5 funciones: leer, crear, agregar texto, reemplazar, cuenta; buscar y renombrar van por Drive) | Subagente | Hecho (v0.8.1) |
| B | Lo que falta de Gmail (crear etiqueta, listar y enviar borradores), Sheets (limpiar rango, renombrar pestaña, buscar valor) y Drive (renombrar, copiar) | Subagente | Hecho (v0.8.1) |
| C | Google Slides: leer contenido y escribir (crear, agregar y duplicar diapositiva, reemplazar texto) | Subagente | Hecho (v0.8.1) |
| D | Revisión conjunta de A, B y C: contrato, permisos, pruebas, que nada pise funciones existentes | Supervisor | Hecho: 1 bloqueante y 5 arreglos, aplicados |
| E | Medir el agente con las funciones nuevas (búsqueda, nodo act y planificador; unos $0.05) y registrar la versión | Claude | Hecho (v0.8.1) |
| F | Buscar hojas por nombre: encadenar `google_drive.files.search` → Sheets en el planificador | Claude | No logrado: la regla de prompt rompía otros casos; el plan pregunta por la hoja |
| G | Aviso en vivo dentro de la app | Claude | Hecho (v0.8.1): evento `notification` por el canal de eventos; este repo no monta ese WebSocket, la UI de pruebas sondea cada 30 s |

**Bloqueado por decisiones o datos del usuario:**
- **Pruebas con cuentas reales y activar funciones** (6, 7, 12): pospuestas por el usuario el 2026-10-11. Todo lo anterior queda medido solo con funciones simuladas.
- **Borrar el código viejo de BigTools** (14, etapa 2): después de la prueba con cuentas reales.
- **Probar los avisos por correo:** faltan las variables `SMTP_*`.
- **Push al navegador o al móvil:** necesita llaves VAPID, un service worker en el frontend real y una dependencia nueva.
- **Precios y planes** (5): al final; faltan los precios.

**Abierto sin solución todavía:** el planificador inventa el rango de la hoja cuando el usuario no lo da (dos reglas de prompt y un filtro por código descartados, ver CHANGELOG 0.6.6 y 0.7.3).

---

Estado histórico de la lista (v0.6.5). Hechos en v0.5.1: 1 (Slack), 2, 3 y 4.

**Cómo leer las columnas:**
- **Esfuerzo:** el trabajo de construirlo.
- **Impacto:** cuánto cambia para el usuario.
- **Costo de prueba:** el gasto estimado en OpenAI para medirlo, siguiendo la regla de "pytest primero, después el nodo aislado, al final el agente con `--repeats 1`".

## Resumen

| # | Pendiente | Esfuerzo | Impacto | Costo de prueba | Depende de |
|---|---|---|---|---|---|
| 1 | ~~Detalles: Slack, Discord, negocio vago~~ (hechos en v0.5.1 y v0.6.2) | Bajo | Bajo | ~$0.05 | — |
| 2 | ~~Seguridad: tokens en el log y `X-Forwarded-For`~~ (hecho) | Bajo | Medio | $0 | — |
| 3 | ~~`action_policy` en Mongo~~ (hecho) | Bajo | Bajo | $0 | — |
| 4 | ~~Calificar respuestas (👍/👎)~~ (hecho; falta el panel, 11) | Bajo | Medio | $0 | — |
| 6 | Activar funciones con cuentas reales | Medio | **Alto** | ~$0.05 | Una cuenta de Asana o ClickUp |
| 7 | ~~Escrituras con confirmación~~ (hecho en v0.5.2 con funciones simuladas; falta probar con cuenta real, 6) | Medio | **Alto** | ~$0.05 | 6 |
| 8 | ~~Memoria global~~ (A en v0.5.3, 2/3; B en v0.5.4, 4/4 revisado a mano) | Medio | Medio | ~$0.30 | — |
| 9 | ~~Compactar conversaciones largas~~ (v0.6.2: 4/4, −69% de tokens en el turno 49) | Medio | Bajo | ~$0.20 | — |
| 10 | ~~Respuesta duplicada al reescribir~~ (no es bug; ver detalle) | Medio | Medio | $0 | Reproducirla primero |
| 11 | ~~Panel de métricas~~ (v0.6.1; `ADMIN_EMAILS` en v0.6.2) | Medio | Medio | $0 | 4 |
| 12 | ~~Gmail, Sheets y Drive en el sistema nuevo~~ (hecho en v0.6.0, simulado; falta cuenta real) | **Alto** | **Alto** | ~$0.10 | Cuentas de Google de prueba |
| 13 | Workflows que corran de verdad: etapas 1 y 2 hechas en v0.6.2 (motor con funciones nuevas, "ejecutar ahora"); etapa 3 (planear con funciones reales) en v0.6.3, 93% de funciones correctas; etapa 4 (programador, webhook) en v0.6.4, probada en vivo; flujo de creación en 3 pasos en v0.6.5 (2 turnos, queda activo y programado); etapa 5 (arrancar cuando llega un correo, por sondeo de Gmail) en v0.7.0, probada en vivo con funciones simuladas; falta probar con cuentas reales | **Alto** | **Alto** | ~$0.20 | 6, 12 |
| 14 | Herramientas viejas rotas (BigTools) | Alto | Bajo | — | Se resuelve con 12 |
| 15 | Avisos que el agente mande solo: primera parte en v0.7.1 (lista de avisos, recordatorio de compromisos, el agente los cuenta al saludar); avisos por correo en v0.7.2 (SMTP de la plataforma, apagado por defecto; sin probar con un SMTP real); falta push | **Alto** | Medio | ~$0.10 | 13 |
| 5 | Precios y planes como dato (**al final, por decisión del usuario**) | Bajo | Medio | ~$0.02 | Que tú pases los precios |

## Esfuerzo bajo (horas)

### 1. Detalles del agente
- **Slack como alternativa.** En `act_sin_funcion` ofreció Slack como canal para avisar, y Slack no está disponible. El juez `mentions_limits` solo revisa apps que el usuario nombró. Hay que extenderlo para que cualquier oración que nombre una app no disponible diga que todavía no lo está.
- **Discord.** Una de cada 3 respuestas todavía empieza con "para que recibas notificaciones" antes de aclarar que es de solo lectura.
- **Negocio vago.** Cuando el usuario describe su negocio sin detalle, la respuesta es genérica. Se puede medir con `vaga_negocio`.

### 2. Seguridad
- `app/integrations/providers/google/oauth_shared.py` escribe tokens descifrados en el log a nivel debug. Se quita esa línea.
- `app/core/limiter.py` confía en `X-Forwarded-For`, que cualquier cliente puede falsificar. Hay que leerlo solo si la petición viene de un proxy de confianza.
- Las trazas (`SHIFU_TRACE_LOG`) guardan contraseñas. Es aceptable en desarrollo, pero no debe encenderse en producción.

### 3. `action_policy` en Mongo
Los límites del modo act (4 consultas a la vez, 4 vueltas, 12 llamadas) hoy son valores por defecto en el código. Se agregan con un script de Mongo, como los demás datos de comportamiento.

### 4. Calificar respuestas
- La UI pone 👍/👎 en cada respuesta y se guarda en Mongo junto al mensaje, la versión y la traza.
- Es la señal más barata para saber qué falla en uso real, y además sirve para escribir escenarios nuevos.

## Esfuerzo medio (1 a 3 días)

### 6. Activar funciones con cuentas reales
- **Por qué es el primero:** las 324 funciones están en `draft`, así que en producción el modo act no tiene ninguna disponible.
- **Pasos:**
  1. Conectar una cuenta real (Asana o ClickUp).
  2. Probar las lecturas más usadas con `/internal/functions/{id}/test`.
  3. Pasar a `active` las que funcionen.
  4. Hacer una prueba real en el chat.
- **Riesgos:** fichas cuya respuesta no cumple su `output_schema` (error `upstream_changed`) y permisos (scopes) que falten.

### 7. Escrituras con confirmación
- **Según la política de cada función:**
  - lo interno y reversible (crear una tarea) se hace directo, y el agente dice qué supuso;
  - lo que sale afuera, borra o no se puede deshacer muestra un borrador y pide un sí.
- **Cómo funciona:**
  - `pending_action` queda guardado en el checkpoint;
  - el clasificador decide entre confirmar, cancelar o cambiar, y si falla cuenta como "no";
  - un botón opcional "Confirmar";
  - un registro de cada escritura en `action_log`.
- **Alcance hoy:** solo Asana (7 funciones) y ClickUp (6) pueden escribir.

### 8. Memoria global
- **Parte A: conversaciones viejas.**
  - Hoy el agente lee las últimas 8 conversaciones.
  - Se busca por significado en todo el diario y se traen como máximo 2 registros, solo cuando parecen relacionados.
  - Se mide primero con un caso de 12 conversaciones.
- **Parte B: compromisos con fecha.**
  - "El viernes entrego la nómina" se guarda con su fecha.
  - El agente lo menciona al saludar si ya venció o está cerca.

### 9. Compactar conversaciones largas
- La memoria aguanta 50 turnos (8/8), pero el contexto pasa de 2.7k a 18k tokens.
- La compactación consiste en resumir lo viejo y mandar al modelo solo los últimos mensajes.
- Solo vale la pena si el costo empieza a importar.

### 10. Respuesta duplicada al reescribir: descartado (revisado el 2026-10-10)
- **No hay duplicado.** Al reintentar, el streamer manda `reset` (`chat.py:229`) y la UI vacía la burbuja (`ui/app.js:448`). `done.text` y `save_message` llevan solo el borrador entregado, también cuando se agotan los intentos y se entrega el mejor borrador.
- **Lo único visible:** el borrador rechazado aparece unos segundos antes del `reset`. Si molesta, el cliente de producción debe mandar `hold: true` para no transmitir tokens hasta que el juez apruebe.

### 11. Panel de métricas y trazas en producción
- **Hoy:** las trazas son archivos locales.
- **Falta:** guardar por turno la versión, la ruta, el costo, la latencia, el veredicto del juez y la calificación del usuario (4), y un panel simple con eso.

## Esfuerzo alto (una semana o más)

### 12. Gmail, Sheets y Drive en el sistema nuevo
- Son las apps que más piden los usuarios, pero viven en el sistema viejo (BigTools), que tiene errores.
- Hay que portarlas como funciones (`doc/funciones/GUIA_JUNIOR.md`): ficha, handler, OAuth de Google, ejemplos y pruebas.
- Al terminar, el modo act las usa sin cambios.

### 13. Workflows que corran de verdad
- **Problemas hoy:**
  - los procesos de fondo no arrancan en este repo;
  - los pasos que crea `req_investigator` no guardan los argumentos de la herramienta;
  - la simulación lee `step_trace` en vez de `trace` y siempre dice "sin pasos para simular";
  - `WorkflowExecutor` usa el sistema viejo.
- **Falta:** arreglar esos puntos y conectar el ejecutor a `app/functions/runner.py`.

### 14. Herramientas viejas rotas
- Fallan los providers de HubSpot, Facebook, Dropbox, Jira y Google, y las listas de herramientas mantenidas a mano no coinciden.
- **Recomendación:** no arreglarlas. Pasarlas al sistema nuevo (12) y retirar el viejo.

### 15. Avisos que el agente mande solo
Recordatorios y notificaciones sin que el usuario escriba primero. Necesita los procesos de fondo de workflows (13).

## Orden recomendado
1. **Rápidos y baratos, sin gastar en OpenAI:** 2, 3 y 4, y 1 si sobra tiempo.
2. **Que el modo act funcione de verdad:** 6 y luego 7.
3. **Mayor valor siguiente:** 12, porque desbloquea 13 y deja 14 sin necesidad de arreglo.
4. **Cuando haga falta:** 8, y 9 si el costo empieza a pesar.
5. **Lo grande:** 13 y luego 15.
6. **Al final (decisión del usuario, 2026-10-10):** 5, precios y planes.

## Para el final

### 5. Precios y planes
- Hoy el agente manda a soporte. Con los precios en un dato (`platform_knowledge`) respondería directo.
- Se retoma cuando el usuario pase los planes y precios reales.
