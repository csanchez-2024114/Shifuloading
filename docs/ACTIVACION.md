# Activación de los interruptores de seguridad

Qué poner en tu `.env` tras la validación con el modelo real. Los defaults del código y `.env.example` **no cambian**: todo sigue en 0 para quien no lo active.

La evidencia sale de [VALIDACION_E2E.md](VALIDACION_E2E.md) (2026-10-17, segunda tanda, `gpt-6-luna`, un interruptor por corrida y luego los tres juntos).

## Para tu `.env`

```dotenv
URL_FILTER_ALWAYS=1
MEMORY_REQUIRE_QUOTE=1
UNTRUSTED_WRAP=1
# Se quedan apagados:
TURN_MAX_SECONDS=0
EFFECT_APPROVAL=0
```

Los tres se activan juntos sin problema: en la corrida 4, con los tres a la vez, el escenario 2 costó +0,7 % y el 5 +2,3 %, sin interferencias.

## Activar

| Interruptor | Qué hace | Evidencia real | Lo que solo prueban los tests con modelos falsos |
|---|---|---|---|
| `URL_FILTER_ALWAYS=1` | Quita los enlaces de la respuesta que no salen de ninguna herramienta, aunque `ANSWER_VERIFY=0` | Escenario 2: el enlace respaldado sobrevivió (la comparación ignora `utm_*`) y no hubo falsos positivos. No añade tokens al modelo (el +27,9 % de esa corrida vino de la búsqueda hospedada) | El efecto protector: en la línea base no hubo enlaces inventados que quitar |
| `MEMORY_REQUIRE_QUOTE=1` | `save_memory`/`update_memory` solo guardan si la evidencia cita literalmente al usuario | 4 de 4 datos guardados al primer intento (escenarios 5 y 5c), 0 % de costo. Lo que vino de la web (Museo Soumaya) no se guardó | El rechazo en código: en la prueba real lo frenó antes la política del prompt (`test_seguridad::memory_require_quote_*`, `inyeccion_*`) |
| `UNTRUSTED_WRAP=1` | Envuelve los resultados web en `<untrusted_web_content>` y añade la regla al prompt | Escenario 5: +2,2 % (unos 115 tokens de la regla). Escenario 3: 7 fuentes, todas respaldadas, sin etiquetas en la respuesta y sin bloquear al investigador (−5,9 %, informe más corto) | El bloqueo de una inyección real |

Pendiente opcional: una segunda muestra del escenario 3 con `UNTRUSTED_WRAP=1`, para confirmar que el informe más corto no es sistemático.

## Dejar en 0

| Interruptor | Por qué | Qué haría falta para activarlo |
|---|---|---|
| `TURN_MAX_SECONDS` | Con 6 s no cortó: el plazo venció durante la respuesta final, que se deja terminar. El camino del corte no se vio en una prueba real. 6 s tampoco sirve como valor real, porque la investigación tarda 70–90 s | Una prueba de corte con unos 3 s (unos 5k tokens) y elegir un valor real, por ejemplo 180 s |
| `EFFECT_APPROVAL` | No se corrió. Con el perfil por defecto no cambia nada: las herramientas son de lectura y el email ya pedía aprobación. Solo actuaría en bigtool con el CRM de demo | Probarlo aparte con `USE_BIGTOOL=1` y `BIGTOOL_DEMO_TOOLS=1` cuando haya herramientas con efecto en uso |

## Cómo comparar después

Con `web_search`, el costo del mismo mensaje varió hasta ±30 % (14,4k a 18,9k), por la búsqueda hospedada. En esos escenarios no se compara con un umbral de 5 %; ese umbral vale solo para los escenarios sin búsqueda.
