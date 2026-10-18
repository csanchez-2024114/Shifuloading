# PARIDAD: inventario de funcionalidades antes del refactor núcleo/perfiles

Línea base: rama `refactor/core-profiles` desde `main@0dce7d4`.
- `pytest -q` antes de los tests nuevos: **269 passed** (56 s).
- Con los tests de caracterización (commit `05773c4`): **346 passed** (269 + 77).

Las líneas son las de `main@0dce7d4` (los archivos aún no se movieron). Los tests van como `archivo::test`, sin `tests/` ni `test_`. Los de `caracterizacion` y la **huella** (`tests/snapshots/perfil_por_defecto.json`) se escribieron en la Fase 0, precisamente para las filas que no tenían test.

La **huella** fija, de una vez:
- las variables de entorno que se leen y sus defaults;
- las herramientas por defecto y con todas las opciones (nombre, descripción y argumentos);
- el prompt del sistema (la fecha va enmascarada) y las políticas de memoria;
- el grafo (nodos y aristas) por defecto y con todas las opciones;
- las rutas HTTP;
- las 136 constantes en MAYÚSCULAS (textos al usuario y al modelo, regex, topes). Antes decía 139 por error: era la cuenta de la primera generación, antes de excluir el estado en vivo `_TURNS`/`_ACTIVE_TURNS`/`_PAUSED_SPEND`;
- el registro de bigtool y los documentos indexados;
- el sha256 de `static/index.html` y de `prompts/system.md`;
- los eventos SSE de 4 escenarios: respuesta simple, búsqueda, HITL aprobado e investigación rechazada.

Columna "Fase 6": se marca ✅ al terminar el refactor, con el test que lo respalda.

**Verificación de la Fase 6** (2026-10-17, sobre `f083182`):
- La suite completa se corrió 3 veces, con Playwright (Edge headless) y Mongo local. Cada corrida dio **370 passed y 0 skipped**, sin tests inestables.
- Cada fila se cruzó con los resultados JUnit de las 3 corridas:
  - ✅ solo si cada test que cita existe y pasó, no saltado, en las 3;
  - un `archivo::*` o un `prefijo_*` cuenta todos los tests que casan, y se comprobó que su número coincide con el que dice la fila;
  - "huella" cuenta los 4 tests de la huella: `huella_del_perfil_por_defecto`, `huella_de_constantes_es_la_de_05773c4`, `multiconjunto_de_valores_igual_al_de_05773c4` y `cada_valor_de_05773c4_sigue_existiendo_sin_el_mapa`.
- La única fila sin test explícito era la 31, y ganó uno en C23.
- La columna "Dónde vive" conserva las líneas de `main@0dce7d4`; tras el refactor, el código está en `src/assistant/core/`, `packs/` y `profiles/default/`.

## Agente y turno

| # | Funcionalidad | Dónde vive | Test que la cubre | Fase 6 |
|---|---|---|---|---|
| 1 | Esfuerzo automático bajo/medio/alto (5/15/`EFFORT_HIGH_MAX_CALLS` llamadas; razonamiento low/medium/high) | `agent.py:48`, `agent.py:137-149` | caracterizacion::contexto_por_esfuerzo, esfuerzo::esfuerzo_bajo_corta_en_5_llamadas, mejoras::esfuerzo_alto_usa_el_tope_configurable | ✅ 3 tests, 3/3 corridas |
| 2 | Regla de mensaje corto (sin clasificador) | `agent.py:74-90` | caracterizacion::regla_de_mensaje_corto (12 casos), mejoras::clasificador_solo_cuando_hace_falta, chip_honesto::palabras_de_actualidad_pasan_por_el_clasificador | ✅ 22 tests, 3/3 corridas |
| 3 | Clasificador LLM del esfuerzo, con respaldo "medio" | `agent.py:109-134` | caracterizacion::clasificador_mapea_la_respuesta_y_cae_a_medio, caracterizacion::clasificador_con_error_devuelve_medio | ✅ 6 tests, 3/3 corridas |
| 4 | Selector de la UI manda; `MODEL_CALL_LIMIT>0` fija el tope | `agent.py:97-106` | mejoras::servidor_salta_el_clasificador_y_respeta_el_selector, esfuerzo::tope_fijo_ignora_esfuerzo | ✅ 2 tests, 3/3 corridas |
| 5 | Evento `effort` primero | `agent.py:1007-1009` | caracterizacion::evento_effort_va_primero_con_esfuerzo | ✅ 1 tests, 3/3 corridas |
| 6 | Margen de salida con esfuerzo alto (`EFFORT_HIGH_MAX_TOKENS`) | `agent.py:143-148`, `agent.py:281-288` | herramientas_caras::esfuerzo_alto_reserva_margen_de_salida, caracterizacion::contexto_por_esfuerzo | ✅ 2 tests, 3/3 corridas |
| 7 | Tope de llamadas por mensaje; la última va sin herramientas | `agent.py:152-172` | mejoras::ultima_llamada_permitida_va_sin_herramientas_y_avisa, esfuerzo::esfuerzo_bajo_corta_en_5_llamadas | ✅ 2 tests, 3/3 corridas |
| 8 | Tope de repetición de una herramienta (`TOOL_REPEAT_LIMIT`) | `agent.py:182-197` | mejoras::tope_de_herramienta_repetida | ✅ 1 tests, 3/3 corridas |
| 9 | `recursion_limit` ajustado a llamadas×8 y error legible | `agent.py:729-733`, `agent.py:1012`, `agent.py:1070-1075` | esfuerzo::esfuerzo_alto_permite_mas_que_recursion_limit_base, caracterizacion::stream_con_recursion_excedida_da_error_legible_sin_done | ✅ 2 tests, 3/3 corridas |
| 10 | Tope de tokens por mensaje (`TURN_TOKEN_CAP`) con callback `TurnTokens` | `agent.py:847-882` | mejoras::tope_general_por_turno_aborta_con_aviso_y_deja_el_hilo_usable | ✅ 1 tests, 3/3 corridas |
| 11 | Aterrizaje suave al 80% (`tool_choice="none"` + nota) | `agent.py:885-963` | aterrizaje::aterrizaje_suave_responde_con_lo_recuperado, aterrizaje::aterrizaje_por_gasto_no_es_aviso_de_sin_herramientas | ✅ 2 tests, 3/3 corridas |
| 12 | Historial más pesado que el tope: turno sin herramientas y evento `no_tools` (marca al recargar) | `agent.py:900-916`, `agent.py:957-963` | aterrizaje::historial_mas_pesado_que_el_tope_va_sin_herramientas, aterrizaje::sin_herramientas_por_historial_avisa_en_vivo_y_al_recargar, ui_navegador::aviso_sin_herramientas_se_ve_en_vivo_y_al_recargar | ✅ 3 tests, 3/3 corridas |
| 13 | Aborto de respaldo en una frontera de paso (sin cortar la respuesta final) | `agent.py:827-836`, `agent.py:1025-1038` | aterrizaje::aborto_de_respaldo_si_salta_del_70_al_110, aterrizaje::respuesta_final_que_cruza_el_tope_no_se_aborta | ✅ 2 tests, 3/3 corridas |
| 14 | Cierre consistente de turnos abortados (llamadas canceladas, id de tarea propio) | `agent.py:973-1001` | cierre_abortado::* (10 tests, con Mongo) | ✅ 10 tests, 3/3 corridas |
| 15 | Aviso al arrancar si el tope no alcanza para el prompt y las herramientas | `agent.py:919-935` | aterrizaje::aviso_al_arrancar_si_el_tope_no_alcanza_para_prompt_y_herramientas | ✅ 1 tests, 3/3 corridas |
| 16 | Gasto de un turno pausado (aprobación) que se suma en `/resume` | `agent.py:851-857`, `agent.py:873`, `agent.py:1013`, `agent.py:1053-1055` | caracterizacion::gasto_del_turno_pausado_se_guarda_y_se_retoma_en_resume | ✅ 1 tests, 3/3 corridas |
| 17 | Aviso de corte por `MAX_TOKENS` y reintento si salió vacío | `agent.py:200-231` | mejoras::respuesta_cortada_por_max_tokens_lo_dice_y_ofrece_seguir, mejoras::respuesta_vacia_por_max_tokens_se_reintenta_una_vez_con_razonamiento_bajo, cierre_abortado::aviso_de_corte_y_reintento_con_mismo_id_en_mongo | ✅ 3 tests, 3/3 corridas |
| 18 | "continúa" sigue donde quedó (`_CONTINUE_RE` + `CONTINUE_NOTE`) | `agent.py:57-63`, `agent.py:234-247` | herramientas_caras::continua_sigue_donde_quedo_sin_rehacer, caracterizacion::regex_de_continuar (12 casos) | ✅ 13 tests, 3/3 corridas |
| 19 | Nombres antiguos de herramientas (hilos viejos) | `agent.py:250-278`, `bigtool_agent.py:254-260` | nombres_antiguos::* (4 tests) | ✅ 4 tests, 3/3 corridas |
| 20 | Prompt dinámico: `system.md` + política de memoria + fecha local | `agent.py:577-595`, `config.py:197-198` | caracterizacion::prompt_del_sistema_lleva_archivo_politica_y_fecha, huella (`system_prompt_*`) | ✅ 5 tests, 3/3 corridas |
| 21 | Modelos: Responses API, streaming, verificador y resumidor sin stream | `agent.py:291-312` | caracterizacion::parametros_de_los_modelos, mejoras::max_tokens_por_defecto_deja_lugar_al_razonamiento | ✅ 2 tests, 3/3 corridas |
| 22 | Errores de herramienta devueltos al modelo (`ToolErrorMiddleware`) | `agent.py:573-574`, `agent.py:698` | huella (`agent` y textos); bigtool::herramienta_que_falla_devuelve_error_sin_tumbar_el_turno (bigtool) | ✅ 5 tests, 3/3 corridas |
| 23 | Pila de middleware y su orden | `agent.py:687-726` | huella (`graph_default`, `graph_all_flags`) | ✅ 4 tests, 3/3 corridas |

## Streaming, eventos y servidor

| # | Funcionalidad | Dónde vive | Test que la cubre | Fase 6 |
|---|---|---|---|---|
| 24 | Traducción de updates a eventos SSE (`token`, `tool_start`, `tool_end`, `interrupt`, `summarized`, `context`, `progress`, `phase`, `verify`, `no_tools`, `error`, `done`) | `agent.py:750-815`, `agent.py:1004-1082` | agent::stream_emite_tokens_y_done, agent::stream_tool_start_y_tool_end_en_orden, huella (`sse`, 4 escenarios), tiempos_ui::phase_verifying_llega_antes_que_verify | ✅ 7 tests, 3/3 corridas |
| 25 | `status: skipped` y `reason: duplicate` (nunca "✓" a lo que no corrió) | `agent.py:621-631`, `agent.py:1085-1094` | chip_honesto::* (6), memoria_dedup::evento_e_historial_marcan_el_duplicado_con_reason, ui_navegador::busqueda_no_realizada_no_se_marca_como_hecha_ni_al_recargar | ✅ 8 tests, 3/3 corridas |
| 26 | `engine` en `tool_end` | `agent.py:736-740` | agent::buscar_web_expone_engine_duckduckgo | ✅ 1 tests, 3/3 corridas |
| 27 | Error del stream sin `done` (desde `feat/seguridad-core`: aviso genérico al cliente y detalle solo en el log, S7) | `agent.py:1076-1079` | caracterizacion::stream_con_excepcion_da_aviso_generico_sin_done | ✅ 1 tests, 3/3 corridas (cambio de comportamiento posterior, S7) |
| 28 | Historial para la UI (`summary`, `original`, `verify`, `no_tools`, `status`, `reason`) | `agent.py:1097-1126` | server::chat_stream_sse_y_history, cierre_abortado::correccion_de_answer_verify_con_mismo_id_en_mongo, aterrizaje::sin_herramientas_por_historial_avisa_en_vivo_y_al_recargar | ✅ 3 tests, 3/3 corridas |
| 29 | SSE con keepalive `: ping` | `server.py:83-126`, `server.py:197-204` | mejoras::keepalive_envia_ping_en_silencios_sin_tocar_los_eventos, caracterizacion::keepalive_reenvia_la_excepcion_del_productor | ✅ 2 tests, 3/3 corridas |
| 30 | Endpoints: `/`, `/health`, `/chat`, `/resume`, `/history`, `/threads*`, `/threads/{id}/context`, `/threads/{id}/compact`, `/me/memories*`, `/memories/*`, `/auth/*` | `server.py:206-399` | huella (`routes`), server::* (5, uno agregado en la Fase 6), propiedad::* (11), contexto::compactar_sin_compactador_responde_501, caracterizacion::compactar_con_aprobacion_pendiente_responde_409, memoria_avanzada::endpoints_* | ✅ 24 tests, 3/3 corridas |
| 31 | `app` perezoso (importar no conecta) y `ConfigError` sin traceback | `server.py:404-413` | perfil::importar_el_nucleo_no_carga_ningun_perfil, server::app_perezoso_y_configerror_sin_traceback (el segundo, agregado en la Fase 6 en C23) | ✅ 2 tests, 3/3 corridas |
| 32 | Reanudación tras aprobación (`/resume`, `Command(resume=...)`) | `server.py:226-234` | agent::hitl_interrupt_y_resume, cierre_abortado::hitl_interrupcion_y_reanudacion_en_mongo, ui_navegador::investigacion_aprobada | ✅ 3 tests, 3/3 corridas |

## Herramientas

| # | Funcionalidad | Dónde vive | Test que la cubre | Fase 6 |
|---|---|---|---|---|
| 33 | Conjunto por defecto y orden; `send_simulated_email` con `ENABLE_HITL_DEMO` | `tools.py:631-646` | caracterizacion::herramientas_por_defecto_y_con_demo_hitl, huella (`tools_*`) | ✅ 5 tests, 3/3 corridas |
| 34 | `web_search` hospedado (contexto y `max_tool_calls`) con respaldo DuckDuckGo | `tools.py:245-274` | caracterizacion::web_search_hospedado_y_respaldo_duckduckgo, caracterizacion::formato_de_duckduckgo | ✅ 2 tests, 3/3 corridas |
| 35 | Una búsqueda por respuesta del modelo | `tools.py:344-360` | herramientas_caras::una_sola_busqueda_por_llamada_al_modelo, herramientas_caras::una_sola_busqueda_por_llamada_en_bigtool, ui_navegador::tres_busquedas_en_paralelo_muestran_las_no_realizadas | ✅ 3 tests, 3/3 corridas |
| 36 | Presupuesto web compartido por mensaje (tokens, búsquedas, reserva) | `tools.py:287-341` | mejoras::buscar_web_del_agente_comparte_el_presupuesto_del_turno, mejoras::agente_e_investigador_juntos_respetan_presupuesto_y_maximo_en_paralelo, caracterizacion::presupuesto_de_busqueda_olvida_los_turnos_mas_viejos | ✅ 3 tests, 3/3 corridas |
| 37 | `deep_research`: subagente con topes, progreso, corte, URLs filtradas y sin fuentes si no buscó | `tools.py:392-532` | mejoras::investigador_* (7), agent::investigador_emite_progreso_sin_filtrar_tokens, chip_honesto::chip_del_investigador_cuenta_solo_busquedas_ejecutadas, cierre_abortado::aborto_dentro_del_investigador | ✅ 10 tests, 3/3 corridas |
| 38 | Reutiliza la investigación anterior en seguimientos breves | `tools.py:410-417`, `tools.py:535-549` | mejoras::seguimiento_breve_no_relanza_la_investigacion, caracterizacion::seguimiento_breve_reutiliza_la_investigacion_anterior | ✅ 2 tests, 3/3 corridas |
| 39 | Confirmación de `deep_research` salvo petición explícita | `tools.py:552-569`, `agent.py:700-705` | herramientas_caras::deep_research_* (4), caracterizacion::cuando_deep_research_pide_confirmacion (9 casos), ui_navegador::investigacion_* (3) | ✅ 16 tests, 3/3 corridas |
| 40 | HITL del email simulado | `tools.py:234-239`, `agent.py:701` | agent::hitl_interrupt_y_resume, caracterizacion::email_simulado_no_envia_nada, huella (`sse.hitl_approve`) | ✅ 6 tests, 3/3 corridas |
| 41 | Rechazo de la tarjeta: `tool_end` skipped desde el middleware | `agent.py:802-814` | chip_honesto::rechazo_de_la_tarjeta_emite_tool_end_skipped, huella (`sse.research_rejected`) | ✅ 5 tests, 3/3 corridas |
| 42 | `calculator` (ast, sin eval, tope de potencia) | `tools.py:26-103` | tools::calculadora_* (4), caracterizacion::calculadora_caracterizada (21 casos) | ✅ 25 tests, 3/3 corridas |
| 43 | `current_datetime` con zona IANA | `tools.py:108-127` | tools::fecha_hora_incluye_anio_actual, caracterizacion::fecha_hora_con_zonas | ✅ 2 tests, 3/3 corridas |
| 44 | `check_python_syntax` (solo `ast.parse`) | `tools.py:606-628` | sintaxis::* (5) | ✅ 5 tests, 3/3 corridas |
| 45 | Todo lo que lee el modelo en inglés; la UI lo traduce | constantes `*_MSG`/`*_DOC`/`*_PROMPT`, `index.html` (`TOOL-LABELS`) | idioma::* (4), nombres_antiguos::todas_las_herramientas_se_llaman_en_ingles | ✅ 5 tests, 3/3 corridas |

## Memoria larga

| # | Funcionalidad | Dónde vive | Test que la cubre | Fase 6 |
|---|---|---|---|---|
| 46 | Store por usuario, namespace `("user", id, "memories")` | `memory.py:76-104` | memory::memory_namespace, memory::memorias_aisladas_por_usuario, persistence::memoria_no_se_filtra_a_otro_usuario | ✅ 3 tests, 3/3 corridas |
| 47 | Guardado con procedencia (evidence/confidence/thread_id) y forma neutra | `memory.py:107-133`, `memory.py:313-321` | memoria_avanzada::cita_literal_da_quoted_y_cita_inventada_queda_sin_evidencia, memory::recuerdos_nuevos_se_guardan_en_forma_neutra | ✅ 7 tests, 3/3 corridas |
| 48 | Verificación con LLM (`MEMORY_VERIFY`) | `memory.py:204-214`, `memory.py:295-310` | memoria_avanzada::recuerdo_respaldado_se_guarda_verificado, memoria_avanzada::recuerdo_no_respaldado_no_se_guarda, memoria_avanzada::dato_solo_en_el_resumen_no_cuenta_como_evidencia | ✅ 3 tests, 3/3 corridas |
| 49 | Dedup (`MEMORY_DEDUP`, por palabras y por puntuación) | `memory.py:324-352` | memoria_dedup::* (7) | ✅ 9 tests, 3/3 corridas |
| 50 | Tope por mensaje (`MEMORY_MAX_PER_TURN`) | `memory.py:251-267`, `memory.py:361-362` | contexto::tope_de_recuerdos_por_mensaje | ✅ 1 tests, 3/3 corridas |
| 51 | `update_memory` con `previous_text`, aislado por usuario | `memory.py:177-189`, `memory.py:377-388` | memoria_avanzada::resolver_cafe_vs_te_deja_un_solo_recuerdo_con_previous_text, memoria_avanzada::id_de_otro_usuario_se_rechaza_sin_revelar_y_no_cambia, memoria_avanzada::actualizacion_sin_respaldo_se_rechaza | ✅ 3 tests, 3/3 corridas |
| 52 | Búsqueda semántica (Atlas) con umbral y respaldo por palabras marcado | `memory.py:156-174`, `memory.py:454-495` | memoria_avanzada::umbral_relevante_si_irrelevante_no_y_es_configurable, mejoras::respaldo_por_palabras_* (2), memory::semantic_sin_atlas_cae_a_palabras | ✅ 8 tests, 3/3 corridas |
| 53 | Búsqueda por palabras (raíces, stopwords, temas, nombres propios, 5 más recientes) | `memory.py:391-513` | memory::por_palabras_* (2), memory::recuerdos_neutros_se_encuentran_por_raiz, mejoras::sinonimos_de_vivienda_y_trabajo | ✅ 8 tests, 3/3 corridas |
| 54 | Políticas de guardado strict/broad y regla de búsqueda económica | `memory.py:217-248` | contexto::politica_estricta_por_defecto_en_prompt_y_herramienta, memoria_dedup::regla_de_busqueda_economica_solo_con_interruptor, herramientas_caras::reglas_del_prompt_y_de_save_memory, huella (`memory_policies`) | ✅ 7 tests, 3/3 corridas |
| 55 | Listado y borrado por endpoint; panel 🧠 | `server.py:377-399` | memoria_avanzada::endpoints_listan_y_borran_aislados_por_usuario, memoria_avanzada::endpoints_sin_store_responden_503 | ✅ 2 tests, 3/3 corridas |
| 56 | Recuerdos viejos sin campos | `memory.py:136-144` | memoria_avanzada::recuerdos_viejos_sin_campos_siguen_funcionando, memoria_avanzada::recuerdo_viejo_sin_campos_se_puede_actualizar | ✅ 2 tests, 3/3 corridas |
| 57 | Migración de embeddings (script, dry-run) | `scripts/migrate_memories.py` | migracion::migracion_conserva_campos_y_es_idempotente | ✅ 1 tests, 3/3 corridas |

## Contexto y compactación

| # | Funcionalidad | Dónde vive | Test que la cubre | Fase 6 |
|---|---|---|---|---|
| 58 | Compactación por % de la ventana (o modo anterior por tokens), una por turno, no tras aterrizar | `agent.py:432-483`, `config.py:147-173` | contexto::compacta_por_porcentaje_..., contexto::compacta_antes_si_la_siguiente_llamada_no_cabe, contexto::no_compacta_si_el_turno_ya_aterrizo, contexto::variables_anteriores_..., mejoras::un_solo_resumen_por_turno_... | ✅ 5 tests, 3/3 corridas |
| 59 | Resumen estructurado incremental con tope | `agent.py:356-382`, `agent.py:421-429`, `agent.py:523-535` | contexto::resumen_estructurado_incremental_conserva_anterior_y_respeta_el_tope | ✅ 1 tests, 3/3 corridas |
| 60 | Cita del primer mensaje (`COMPACT_FIRST_MESSAGE`) | `agent.py:385-418`, `agent.py:494-506` | contexto::resumen_cita_el_primer_mensaje_una_sola_vez_tras_dos_compactaciones, contexto::sin_la_opcion_el_resumen_no_lleva_la_cita | ✅ 3 tests, 3/3 corridas |
| 61 | Compactación manual (`/compact`): 501 sin compactador, 409 con aprobación pendiente | `agent.py:538-560`, `server.py:357-368` | contexto::compactar_ahora_reduce_el_contexto_y_deja_marca, contexto::compactar_sin_compactador_responde_501, caracterizacion::compactar_con_aprobacion_pendiente_responde_409 | ✅ 3 tests, 3/3 corridas |
| 62 | Poda de resultados viejos (`COMPACT_PRUNE_TOOLS`) | `context.py:217-270` | contexto::poda_viejos_conserva_recientes_llamadas_respuestas_y_memoria, contexto::poda_en_el_agente_cambia_la_vista_no_el_checkpoint | ✅ 2 tests, 3/3 corridas |
| 63 | Medidor de contexto (uso real o estimado, overhead, totales) y `GET /threads/{id}/context` | `context.py:166-372`, `server.py:349-355` | contexto::medidor_usa_el_uso_real_..., contexto::hilo_nuevo_empieza_en_el_contexto_base_estimado, contexto::conteo_usa_el_texto_..., ui_contexto::medidor_sube_cambia_de_color_... | ✅ 4 tests, 3/3 corridas |
| 64 | Ventana por defecto del perfil del modelo; variables vacías valen su default | `config.py:21-24`, `config.py:147-151`, `config.py:183-194` | contexto::ventana_por_defecto_sale_del_perfil_del_modelo, contexto::variables_numericas_vacias_usan_su_default | ✅ 2 tests, 3/3 corridas |

## Verificación y citas

| # | Funcionalidad | Dónde vive | Test que la cubre | Fase 6 |
|---|---|---|---|---|
| 65 | `AnswerVerifier` (solo con evidencia real; corrige sin silencio; "no verificada" por tope) | `agent.py:598-684` | memoria_avanzada::answer_verify_* (2), chip_honesto::answer_verify_* (2), aterrizaje::pasado_el_tope_no_verifica_..., aterrizaje::bajo_el_tope_si_verifica, ui_navegador::respuesta_no_verificada_... | ✅ 7 tests, 3/3 corridas |
| 66 | Reglas de citas en código (URL normalizada, restaurar, quitar inventadas, cifras nuevas) | `citations.py` | citas::* (9) | ✅ 10 tests, 3/3 corridas |

## Cuentas, datos y persistencia

| # | Funcionalidad | Dónde vive | Test que la cubre | Fase 6 |
|---|---|---|---|---|
| 67 | Checkpoints en Mongo; historial tras reinicio | `memory.py:67-69` | persistence::historial_persiste_tras_reinicio, persistence::memoria_compartida_entre_threads | ✅ 2 tests, 3/3 corridas |
| 68 | Arranque: API key, Mongo, modelo (mensajes claros, URI sin contraseña) | `memory.py:25-64`, `memory.py:543-552`, `config.py:175-180` | config::* (4), citas::error_de_conexion_no_muestra_la_contrasena, citas::srv_inexistente_no_muestra_la_contrasena, citas::errores_al_construir_el_cliente_dan_mensaje_claro | ✅ 8 tests, 3/3 corridas |
| 69 | Cuentas: argon2id, sesiones con hash, renovación deslizante, bloqueo por correo/IP | `auth.py` | auth::* (9) | ✅ 17 tests, 3/3 corridas |
| 70 | CSRF de dos capas, origen, cookie HttpOnly/SameSite/Secure | `server.py:162-192` | propiedad::csrf_y_origen, propiedad::cookie_httponly_samesite_y_secure_configurable, auth::csrf_derivado_del_token | ✅ 3 tests, 3/3 corridas |
| 71 | Propiedad de hilos (404 ajeno), renombrar, borrar hilo y cuenta | `server.py:176-181`, `server.py:288-343` | propiedad::* (11), ui_auth::registro_chat_salir_entrar_y_aislamiento | ✅ 12 tests, 3/3 corridas |
| 72 | Dos bases que nunca son la misma; variables `AI_*` compatibles | `memory.py:516-540`, `config.py:92-94` | dos_bases::* (4), aislamiento::ninguna_base_guarda_lo_de_la_otra | ✅ 6 tests, 3/3 corridas |
| 73 | Asignación de datos anteriores (script) | `scripts/assign_legacy_data.py` | asignar_legado::dry_run_lista_y_apply_asigna_y_copia | ✅ 1 tests, 3/3 corridas |
| 74 | Variables de entorno y defaults | `config.py:87-145` | huella (`config`: 57 variables y todos los defaults) | ✅ 4 tests, 3/3 corridas |

## Bigtool (`USE_BIGTOOL=1`) y apps

| # | Funcionalidad | Dónde vive | Test que la cubre | Fase 6 |
|---|---|---|---|---|
| 75 | Agente bigtool: `retrieve_tools`, índice semántico, registro | `bigtool_agent.py` | bigtool::* (6), huella (`bigtool_*`) | ✅ 10 tests, 3/3 corridas |
| 76 | `PromptedModel` (prompt, esfuerzo, aterrizaje) | `bigtool_agent.py:263-301` | aterrizaje::*_bigtool (3) | ✅ 3 tests, 3/3 corridas |
| 77 | `interrupt()` de `deep_research` en bigtool | `bigtool_agent.py:200-215` | herramientas_caras::deep_research_en_bigtool_pide_confirmacion | ✅ 1 tests, 3/3 corridas |
| 78 | Memoria con procedencia en bigtool | `bigtool_agent.py:182-198` | memoria_avanzada::bigtool_guarda_con_procedencia_y_verificacion, memoria_avanzada::bigtool_tiene_actualizar_recuerdo_sin_argumentos_inyectados, bigtool::memoria_por_user_id_entre_threads | ✅ 3 tests, 3/3 corridas |
| 79 | 31 herramientas extra | `extra_tools.py` | extra_tools::* (5) | ✅ 5 tests, 3/3 corridas |
| 80 | `@tool_spec`, `requires`/`auto` y validación del registro | `tool_spec.py` | tool_spec::* (5) | ✅ 5 tests, 3/3 corridas |
| 81 | App de ejemplo `crm_demo` | `apps/crm_demo.py` | tool_spec::auto_resuelve_customer_id_y_errores_claros, tool_spec::flujo_agente_llama_la_prefuncion | ✅ 2 tests, 3/3 corridas |

## Interfaz (`static/index.html`)

| # | Funcionalidad | Dónde vive | Test que la cubre | Fase 6 |
|---|---|---|---|---|
| 82 | Chat, chips agrupados, tarjetas de aprobación, medidor, panel 🧠, cuentas, ajustes de esfuerzo | `static/index.html` | ui_navegador::* (10), ui_contexto::*, ui_auth::*, huella (`index_html_sha256`) | ✅ 27 tests, 3/3 corridas |
| 83 | Markdown y LaTeX legibles | `index.html` (`MATH-START`…`MATH-END`) | mejoras::latex_se_muestra_legible_sin_texto_crudo | ✅ 1 tests, 3/3 corridas |
| 84 | Desglose de tiempos | `index.html` (`BREAKDOWN-*`) | tiempos_ui::* (3) | ✅ 3 tests, 3/3 corridas |
| 85 | Etiquetas en español para mensajes y nombres viejos y nuevos | `index.html` (`TOOL-LABELS-*`) | idioma::la_interfaz_muestra_los_mensajes_de_herramientas_en_espanol, nombres_antiguos::la_interfaz_muestra_etiquetas_en_espanol_para_nombres_viejos_y_nuevos, sintaxis::el_agente_la_usa_y_la_ui_la_muestra_en_espanol | ✅ 3 tests, 3/3 corridas |

## Sin test, incluso tras la Fase 0

- **LangSmith:** solo variables de entorno, sin código propio. No se puede probar sin red. **No demostrada con un test.** Verificado en la Fase 6: `.env.example` no cambió desde `main@0dce7d4`, y el README conserva su sección (las mismas 5 menciones de `LANGSMITH`).
- **Pruebas de navegador:** se saltan si no hay Edge o Chrome, y algunas usan `node`. Hoy corren en esta máquina (cuentan dentro de los 269, y en la Fase 6 corrieron en las 3 corridas, sin saltarse).
- **Comportamiento con el modelo real:** calidad de las respuestas y cumplimiento del prompt. **No demostrada:** ningún test lo cubre y en el refactor no se llamó a la API. La huella solo garantiza que, con el perfil por defecto, el modelo recibe exactamente lo mismo que antes: el prompt, las herramientas, el grafo y las constantes.
