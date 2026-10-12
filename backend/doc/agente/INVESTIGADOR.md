# El investigador: búsqueda web del agente

Estado al 2026-10-11, versión del agente 0.9.5, rama `feat/functions-base`. Este documento sirve para retomar el trabajo en una sesión nueva sin leer la conversación anterior.

## Qué es

Cuando el usuario pregunta algo que no está en sus apps ni en la memoria (un precio, una noticia, los límites de una API), el agente busca en internet con Tavily, razona sobre lo que encontró y responde con el dato, su fecha y su fuente.

El dueño del proyecto pidió tres cosas, en este orden:

1. Información vigente. Nada viejo salvo que lo pida de forma explícita.
2. Respuesta correcta, aunque tarde más.
3. Que el agente tenga juicio sobre los datos: que piense, no que repita la primera fuente.

## Flujo

```
semantic_intake ──► tavily_subgraph ──────────────────────────────────► fan_in ──► responder ⇄ response_evaluator
                    tavily_searcher → research_curator → research_analyst
```

El subgrafo corre en paralelo con `catalog_checker`, `auth_validator` y `document_analyzer`. Tiene un tope de 60 s (`_RESEARCH_TIMEOUT` en `builder_standard.py`); si se pasa, el turno sigue sin investigación.

| Paso | Archivo | Qué hace |
|---|---|---|
| Decidir | `app/agent/shared/prompts/semantic_intake.py`, `nodes/semantic_intake.py` | Marca `needs_external_info`, escribe la consulta en inglés (`optimized_search_query`) y elige ventana de fechas e índice |
| Buscar | `nodes/tavily_searcher.py` | Llama a Tavily con la ventana y el índice; si no hay resultados amplía la ventana |
| Curar | `nodes/research_curator.py` | Extrae los hechos relevantes y quita repetidos |
| Juzgar | `nodes/research_analyst.py` | Razona sobre las fuentes y puede pedir una búsqueda más |
| Responder | `nodes/responder.py` | Construye la respuesta sobre la conclusión del analista |
| Evaluar | `nodes/response_evaluator.py` | Los jueces reciben la investigación como evidencia |

## Campos del estado

Todos se reinician en `_EMPTY_RESULT` de `semantic_intake`. `_tavily_with_timeout` devuelve solo los cuatro últimos para no pisar campos de otras ramas.

| Campo | Lo escribe | Valores |
|---|---|---|
| `needs_external_info` | intake | bool |
| `optimized_search_query` | intake | consulta en inglés |
| `search_recency` | intake | `day`, `week`, `month`, `any` |
| `search_topic` | intake | `news`, `general` |
| `needs_fact_verification` | intake | bool; activa la verificación del curador |
| `retrieved_research` | buscador | texto crudo con título, URL y `Published:` por fuente |
| `retrieved_sources` | buscador, analista | lista `{title, url, domain, published?}`; su orden define las citas `[N]` |
| `research_freshness` | buscador | frase: ventana usada de verdad y fecha de hoy |
| `curated_research` | curador, analista | lo que lee el responder; empieza con el juicio del analista |

## Decisiones tomadas y por qué

Cada una salió de una medición. No revertir sin volver a medir.

- **Ventana de fechas por pregunta.** `day` para lo que cambia a diario (precios, clima), `week` para noticias, `month` para novedades y lanzamientos, `any` para lo demás. Antes solo las "noticias" tenían filtro.
- **No hay ventana `year`.** Un filtro de último año sacaba la documentación oficial y Wikipedia, que no tienen fecha de publicación reciente, y dejaba blogs. Los datos estables van sin filtro.
- **Si la ventana no trae nada, se amplía un escalón** y `research_freshness` lo dice, para que el responder no presente lo viejo como actual.
- **El índice `news` solo con ventana.** Es el único que devuelve fecha de publicación, pero sin ventana devolvía notas de hace un año, y para clima o precios trae notas sueltas. Lo elige el intake.
- **La ciudad del usuario no se pega a la consulta.** `location_aware` salía verdadero en 14 de 17 preguntas y "bitcoin price … Guadalajara, Mexico" devolvía un partido de fútbol. El intake escribe el lugar en la consulta cuando importa.
- **El esfuerzo `medio` no descarga páginas completas** (`_EFFORT_CONFIGS`); `high` y `max` sí. Bajó el turno de ~55 s a ~25 s.
- **Los jueces ven la investigación.** Sin ella rechazaban 5 veces la respuesta correcta por "inventar datos en tiempo real".
- **Pregunta informativa no es pedido de acción.** Con investigación e intención `question`, `exploring` o `chat`:
  - el responder no pausa la respuesta por una cuenta sin conectar (`_aggregate`);
  - el evaluador no trata un dato sobre una app como promesa de actuar en ella (`_WEB_INFO`), y `mentions_limits` se salta.
- **La resta de fechas la hace el código.** 4o-mini escribió "septiembre de 2026, que aún no ocurre al 11 de octubre de 2026", incluso con la regla escrita en su criterio. Ver la sección del analista.

## El analista (`research_analyst.py`)

Una llamada a 4o-mini con salida estructurada (`_Judgment`). Recibe la fecha de hoy, la ventana usada, la pregunta original del usuario, la lista numerada de fuentes y el texto crudo (tope 24,000 caracteres).

Devuelve, en este orden:

1. `announced`: lo que las fuentes llaman próximo, esperado o rumoreado, con su fecha y una consulta para comprobar si ya pasó. Va primero a propósito: al final el modelo ya había concluido sin mirarlo.
2. `reasoning`, `conclusion`, `confidence` (`high`, `medium`, `low`).
3. `caveats`, `discarded` (fuentes que no se deben usar, con motivo), `follow_up_query`.

Segunda búsqueda, una como máximo (`max_followups`):

- si el código ve en `announced` una fecha anterior a hoy (`_already_past`), la fuerza con la consulta de comprobación y le pasa al segundo juicio el hecho calculado ("DATE CHECK: ya pasó");
- si no, solo cuando la confianza no es alta y el analista propuso una consulta.

La segunda búsqueda no hereda la ventana de fechas. Sus fuentes se agregan al final de `retrieved_sources`, así los `[N]` anteriores no se mueven.

Si el analista falla, el turno sigue con lo que había.

## Lo que es dato en Mongo (`agent_personality`)

Se cambia con un script chico que fija el campo, nunca volviendo a correr el seed. La personalidad tiene caché de 10 minutos: reiniciar el backend después.

| Campo | Para qué |
|---|---|
| `research_policy` | `enabled`, `model`, `max_followups`, `criteria` (cómo juzga el analista). La copia única del texto está en `_DEFAULT_POLICY` de `research_analyst.py`; el seed la importa |
| `prompt_snippets.web_found` | cómo responder cuando la búsqueda trajo algo |
| `prompt_snippets.web_unavailable` | qué decir cuando hacía falta buscar y no se pudo |

Los criterios de `search_recency` y `search_topic` están en el prompt de `semantic_intake`, que vive en código.

## Cómo medir

```bash
python scripts/eval_web.py --n 6                 # sortea 6 de 17 temas; intake + Tavily reales
python scripts/eval_web.py --all --judge         # los 17, con el juicio del analista impreso
python scripts/eval_web.py --judge --match iPhone
python scripts/eval_agent.py --base http://localhost:5001 --label x --repeats 1 --max-usd 0.15 \
  --only web_dato_actual,web_novedades,web_precio,web_noticias,web_estable,web_juicio
pytest test/agente_v3/nodes/test_tavily_recency.py test/agente_v3/nodes/test_research_analyst.py -q
```

- `eval_web.py` cuesta ~$0.001 de OpenAI y 1–2 créditos de Tavily por caso. Marca ✓ si el intake eligió una ventana aceptable, la consulta no trae un año viejo y hubo resultados. La calidad de las fuentes y del juicio se lee a mano.
- Para temas nuevos se agregan filas a `BANK` en ese script.
- Backend local para las pruebas: `SHIFU_SCHEDULER=1 SHIFU_FUNCTIONS_SIMULATE=1 SHIFU_FUNCTIONS_STATUSES=active,testing,draft SHIFU_TRACE_LOG=1`, puerto 5001. Las trazas quedan en `logs/agent_traces/` y se leen con `scripts/review_traces.py`.

## Resultados al cierre (v0.9.5)

- `eval_web.py --all`: 17 de 17 con la ventana esperada.
- Agente completo (`v095_juicio`): 6 de 6 escenarios web, un intento por turno.
- Costo ~$0.0066 por turno; tiempo ~44 s (32–55 s según haya segunda búsqueda).
- 1732 tests en verde.

## Problemas abiertos

- **Caso del iPhone, resuelto en v0.10.2.** Fallaba cuando la primera búsqueda ya traía la fecha de salida sin llamarla "próxima". Ahora el código revisa la conclusión (`_future_about_past`) y la hace rehacer si habla en futuro de una fecha pasada: 8 de 8 en el replay del turno fallado, 6 de 6 con el agente. `_stamp_dates` marca cada fecha del texto contra la del sistema, pero por sí sola no bastó (0 de 8).
- **Búsqueda dentro del flujo de workflows** (v0.10.2): si el mismo mensaje pide crear algo y un dato de internet, la búsqueda corre a la par (`builder_standard._req_with_research`). Lo encontrado solo se usa cuando el turno lo redacta el responder; un mensaje del flujo entregado tal cual no lo incluye.
- **El analista es un modelo chico.** Mejorado en lo medido (v0.9.7): "presidente de Argentina" 3 de 3 con el año correcto, iPhone 7 de 7. El código le entrega las fechas ya comparadas contra la del sistema (nota al final del mensaje, segunda búsqueda primero, `_age` por fuente). Son muestras chicas.
- **No hay verificación contra una fuente propia.** El juicio es sobre lo que devuelve Tavily.
- **El índice general no da fecha de publicación.** Ahí la vigencia depende del filtro de Tavily y de lo que diga la página.
- **Sigue lento**: ~44 s por turno.
- **Partido de la selección**: con ventana de un día no encontró el resultado, ni con la segunda búsqueda. Lo dice con confianza baja, pero no responde.
- **El juez del arnés** (`eval_agent.py`, gpt-4.1-mini desde v0.9.6) todavía marca falsas: en `v097_web` dio por viejas unas noticias de la semana sin evidencia. Leer la respuesta antes de creerle un "violado".

## Ideas no construidas

- Lista de dominios primarios por tema (bancos centrales, documentación oficial) para `include_domains` en la segunda búsqueda.
- Ejecutar el juicio dos veces y comparar cuando la confianza es alta pero hay anuncios en las fuentes.
- Resumir por fuente antes del analista si el tope de 24,000 caracteres se queda corto.

## Reglas de trabajo del proyecto

- El comportamiento es dato en Mongo; el código es mecanismo. Se decide midiendo.
- Solo modelos chicos: gpt-4o-mini y gpt-4.1-nano.
- Pruebas baratas primero: pytest, luego el nodo suelto, luego el agente completo con `--only`, `--repeats 1` y `--max-usd`.
- Al terminar cada cambio: subir versión en `app/agent/version.py`, entrada en `CHANGELOG.md`, `python scripts/snapshot_prompts.py`, commit y push.
- `logs/` y `eval_results/` no se suben.
- En esta máquina los heredocs de Bash rompen las barras invertidas (`\n`, regex): el código que las lleva se edita con las herramientas de edición, no con heredocs.
