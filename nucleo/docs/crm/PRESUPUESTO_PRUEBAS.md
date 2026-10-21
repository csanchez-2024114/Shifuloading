# Cuánto gastar en pruebas con la IA real (20-oct-2026)

Las pruebas con la API de OpenAI cuestan dinero. Esta regla dice qué correr, cuántas veces y cuándo vale la pena. Va antes de
cada medición, sea quien sea el que la corra (Claude, Cursor o una persona).

## Cuánto cuesta (medido sin gastar: tokens contados con tiktoken)

| Pieza | Tokens |
|---|---|
| Prompt del sistema por llamada | ~6.000 (de eso, 1.600 son el catálogo de conceptos) |
| Herramientas por llamada | ~5.900 |
| Llamadas al modelo por mensaje | ~2,2 (y hasta 7) |
| **Un mensaje del chat** | **~28.000** |

| Banco | Mensajes por corrida | Tokens aprox. |
|---|---|---|
| datos (con `3`) | 63 | 1,8 M |
| pestañas (con `3`) | 27 | 0,8 M |
| deshacer | ~18 | 0,5 M |
| conceptos | 14 | 0,4 M |
| banco2 | 16 | 0,45 M |
| toma | 11 | 0,3 M |
| citas | 9 | 0,25 M |
| ficha | 7 | 0,2 M |
| creación (primer diseño) | 6 | 0,15 M |
| memoria | 2 grandes | 0,1 M |
| conversación (20 mensajes, crece el historial) | 20 | 0,7 M |
| **Los 10 bancos una vez** | **~170** | **~4,8 M ≈ US$2** (gpt-4.1-mini) |

El 19 y el 20 de octubre se corrieron unas 20 veces los 10 bancos completos (≈ US$40–50), y la mayoría fue repetir todo por cambios
chicos. Por eso esta regla.

## La regla: de lo gratis a lo caro

1. **Siempre primero, gratis:** las pruebas sin IA (`cd nucleo && .venv/bin/python -m pytest tests/crm`, ~10 s; con
   `CRM_MOTOR=agente0` también) y, si se tocó el bucle, `tests/crm/test_paridad_nucleo.py`. Si algo falla aquí, no se gasta API.
2. **Mientras se itera un arreglo:** solo **el caso** que se está arreglando, a mano (un script de 2–3 mensajes contra el servidor
   de desarrollo), **una vez**. Nada de bancos completos por cada intento.
3. **Al terminar un arreglo:** solo **los bancos que el cambio puede tocar**, **una vez**:
   - cambio en el prompt o en el Estado (`prompt_sistema`, `contexto`, conceptos) → afecta todo: ver punto 4;
   - cerco de una herramienta → los bancos que usan esa herramienta (registros → datos y citas; quitar/bloques → pestañas y banco2;
     deshacer → deshacer);
   - memoria o ruta del chat → conversación (con `RELLENO=1`) y memoria.
4. **Antes de juntar en `david` (la compuerta), y solo ahí:** los 10 bancos **una vez**. Se repite **solo** el banco que salga más
   de 1 punto abajo de su rango conocido (abajo). Nunca 2 o 3 corridas de todo «por si acaso».
5. **Conversación larga (`RELLENO=3`, 44 mensajes, ~2 M tokens):** solo si se tocó la memoria. Una corrida.
6. **Antes de una medición, decir el costo estimado** (con esta tabla) y anotarlo en el resumen junto al resultado.
7. **Si OpenAI responde 429 «no credits»:** parar. Lo medido después de eso no cuenta.

## Rangos conocidos (para no repetir de más)

Los bancos varían solos entre corridas con el mismo código. Un resultado dentro de su rango no es regresión:

| Banco | Rango normal |
|---|---|
| datos | 62–63 / 63 |
| citas | 7–9 / 9 |
| deshacer | 15–18 / 18 (casos inestables: «solo el color», «mejor azul», «agregar no reemplaza») |
| pestañas | 22–24 / 27 |
| banco2 | 14–16 / 16 |
| conceptos | 9–12 / 14 |
| memoria | 13–18 / 18 |
| toma 11/11 · ficha 7/7 · creación 6/6 | siempre completos |
| conversación (20 mensajes) | 4–5 / 5 |

Solo cuenta como regresión salir del rango, o un caso que antes nunca fallaba y ahora falla 2 veces.

## Para gastar menos en cada llamada (pendiente, medir antes)

- **Caché de OpenAI:** los prompts de más de 1.024 tokens con el mismo inicio se cobran más barato. El orden ya ayuda (lo fijo
  primero, el Estado al final), pero las herramientas cambian entre vueltas (toma, deshacer) y cortan el caché.
- **Catálogo de conceptos:** 1.600 tokens en cada llamada; achicarlo era una sugerencia pendiente.
- **Herramientas:** 5.900 tokens; mandar solo las del modo en que está la persona bajaría mucho el costo. Hay que medir que no se
  pierda calidad.
