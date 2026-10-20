# Activación de los interruptores de seguridad

Qué poner en tu `.env` tras la validación con el modelo real. Los defaults del código y `.env.example` **no cambian**: todo sigue en 0 para quien no lo active.

La evidencia sale de [VALIDACION_E2E.md](VALIDACION_E2E.md) (2026-10-17, segunda tanda, `gpt-6-luna`, un interruptor por corrida y luego los tres juntos).

## Para tu `.env`

```dotenv
URL_FILTER_ALWAYS=1
MEMORY_REQUIRE_QUOTE=1
UNTRUSTED_WRAP=1
MEMORY_UPDATE_PRIOR_EVIDENCE=1
# Se quedan apagados:
TURN_MAX_SECONDS=0
EFFECT_APPROVAL=0
```

Los tres se activan juntos sin problema: en la corrida 4, con los tres a la vez, el escenario 2 costó +0,7 % y el 5 +2,3 %, sin interferencias.

## Activar

| Interruptor | Qué hace | Evidencia real | Lo que solo prueban los tests con modelos falsos |
|---|---|---|---|
| `URL_FILTER_ALWAYS=1` | Quita los enlaces de la respuesta que no salen de ninguna herramienta, aunque `ANSWER_VERIFY=0` | Escenario 2: el enlace respaldado sobrevivió (la comparación ignora `utm_*`) y no hubo falsos positivos. No añade tokens al modelo (el +27,9 % de esa corrida vino de la búsqueda hospedada) | El efecto protector: en la línea base no hubo enlaces inventados que quitar. Corregido el 2026-10-18: ya no borra un enlace respaldado pegado a un delimitador de cierre (comillas, paréntesis, corchetes, puntuación) y ve también las URL pegadas a un paréntesis de apertura. Validado en real con `url-del-usuario` (`evals/resultados/20261018-144911_real.json`) |
| `MEMORY_REQUIRE_QUOTE=1` | `save_memory`/`update_memory` solo guardan si la evidencia cita literalmente al usuario | 4 de 4 datos guardados al primer intento (escenarios 5 y 5c), 0 % de costo. Lo que vino de la web (Museo Soumaya) no se guardó | El rechazo en código: en la prueba real lo frenó antes la política del prompt (`test_seguridad::memory_require_quote_*`, `inyeccion_*`) |
| `UNTRUSTED_WRAP=1` | Envuelve los resultados web en `<untrusted_web_content>` y añade la regla al prompt | Escenario 5: +2,2 % (unos 115 tokens de la regla). Escenario 3: 7 fuentes, todas respaldadas, sin etiquetas en la respuesta y sin bloquear al investigador (−5,9 %, informe más corto) | El bloqueo de una inyección real |
| `MEMORY_UPDATE_PRIOR_EVIDENCE=1` | `update_memory` acepta como respaldo de lo que no cambia la cita literal ya guardada en el recuerdo, para poder corregir un dato después de una compactación (B2). El valor nuevo se sigue exigiendo en la conversación, así que `MEMORY_REQUIRE_QUOTE` no se relaja | Validación corta del 2026-10-18 (`PRUEBA_USUARIO_LARGA.md`, 196 360 tokens), con `MEMORY_SUMMARIZE=1`, `CONTEXT_WINDOW_TOKENS=24000`, `MEMORY_VERIFY=1` y `MEMORY_REQUIRE_QUOTE=1`. Tras compactar, "no son 3 empleadas, son 4" se guardó ("Memory updated.") y un hilo nuevo respondió "Tienes 4 empleadas…". En el modo A, sin el interruptor, la misma corrección se rechazó y el hilo nuevo dijo "tres". 0 % de costo: no añade llamadas | **Su camino nuevo** (verificar con la cita guardada lo que no cambia) solo lo prueban los modelos falsos (`test_memoria_compactada`): en la prueba real el modelo reescribió el recuerdo solo con lo dicho en ese mensaje y no necesitó la cita vieja. Solo tiene efecto con `MEMORY_VERIFY=1` o `MEMORY_REQUIRE_QUOTE=1`, y solo importa si hay compactación (`MEMORY_SUMMARIZE=1`). Ojo: no evita que el modelo borre al reescribir un dato no corregido (pendiente (a) en `REFACTOR_NOTAS.md`) |

Pendiente opcional: una segunda muestra del escenario 3 con `UNTRUSTED_WRAP=1`, para confirmar que el informe más corto no es sistemático.

## Dejar en 0

| Interruptor | Por qué | Qué haría falta para activarlo |
|---|---|---|
| `TURN_MAX_SECONDS` | Con 6 s no cortó: el plazo venció durante la respuesta final, que se deja terminar. El camino del corte no se vio en una prueba real. 6 s tampoco sirve como valor real, porque la investigación tarda 70–90 s | Una prueba de corte con unos 3 s (unos 5k tokens) y elegir un valor real, por ejemplo 180 s |
| `EFFECT_APPROVAL` | No se corrió. Con el perfil por defecto no cambia nada: las herramientas son de lectura y el email ya pedía aprobación. Solo actuaría en bigtool con el CRM de demo | Probarlo aparte con `USE_BIGTOOL=1` y `BIGTOOL_DEMO_TOOLS=1` cuando haya herramientas con efecto en uso |

## Archivos (`FILES_ENABLED`)

Validado con el modelo real el 2026-10-18 (tercera tanda de `VALIDACION_E2E.md`: evals 6/6 y 3 mensajes por la UI, con seguridad al 100 %). Si lo activas:
- necesita las dependencias del extra `[files]`: `uv pip install --python .venv -e ".[files]"`;
- funciona también con `USE_BIGTOOL=1` (desde la Fase 4: bigtool tiene `read_file`, `search_in_file` y la regla de archivos). Esa combinación solo está probada con modelos falsos;
- con el perfil `generic` se pueden subir archivos, pero el modelo no recibe `read_file` ni `search_in_file` (ver `docs/CREAR_PERFIL.md`).

## Trazas, métricas y feedback (`TRACE_METADATA`, `TURN_METRICS`, `FEEDBACK_ENABLED`)

Validados con el modelo real el 2026-10-18 (prueba corta en `VALIDACION_E2E.md`). Si los activas:
- **`TURN_METRICS` y `FEEDBACK_ENABLED` necesitan una base de negocio** (`APP_MONGODB_URI` y `APP_MONGODB_DB`, distinta de la de la IA). **Tu `.env` hoy no la define**: con cualquiera de los dos en 1 y sin ella, el servidor no arranca. `TRACE_METADATA` sola no la necesita.
- `FEEDBACK_ENABLED=1` exige además `TRACE_METADATA=1` y `TURN_METRICS=1`.
- El envío del feedback a LangSmith solo está probado con un cliente falso.

## Candado por hilo (siempre activo, sin variable)

Desde la Fase 4, un segundo `/chat` o `/resume` en un hilo con un turno en curso responde 409. **El candado vive en la memoria del proceso: vale solo con un worker de uvicorn** (como se arranca hoy: `uvicorn assistant.server:app`, sin `--workers`). Con varios workers o varias réplicas, cada proceso tiene su propio candado y dos turnos del mismo hilo podrían volver a correr a la vez: antes de escalar, hay que moverlo a Mongo (por ejemplo, un documento por hilo con `findOneAndUpdate` y caducidad).

## Cómo comparar después

Con `web_search`, el costo del mismo mensaje varió hasta ±30 % (14,4k a 18,9k), por la búsqueda hospedada. En esos escenarios no se compara con un umbral de 5 %; ese umbral vale solo para los escenarios sin búsqueda.
