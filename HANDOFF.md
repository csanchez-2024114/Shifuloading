# HANDOFF — frente diagnóstico (rama `etapa1/diagnostico`, worktree `wt-diagnostico`)

No se corrieron los bancos con IA real: no hay clave y no se creó `backend/.env`. Pytest con modelo falso: **17878 passed, 1 skipped** (`test/crm`, 19-oct). La línea base que sí existe es `documentos/mediciones/2026-10-19_linea_base/` (banco2 15/16, datos 61/63, pestañas 20/27).

## Qué cerré

### 15 — «calendario» ofrece en vez de actuar (3/3 en pestañas)

**Causa (evidencia).** En las tres corridas de `pestanas.txt` el modelo no llamó herramientas (`hizo: []`, `fallos: []`) y dijo «No hay vista de calendario…». El prompt copiado de `chat.js` ponía como ejemplo de lo que no existe «un calendario, un mapa, una gráfica de radar». En el estado, `calendario_mes` es una vista (`VISTAS_INICIO`) y `calendario` / `radar` son tipos de gráfico. El ejemplo contradecía el catálogo.

**Arreglo.** El prompt ya no nombra ejemplos viejos: lo que existe es lo que está en el estado (`vistas` y `graficos_posibles`). No es una lista de palabras del caso.

**Prueba.** `test_el_prompt_no_niega_lo_que_el_catalogo_tiene`. No re-medido con IA real. El agente anterior anotó en el diff que, sin el ejemplo, el caso pasaba 3/3; esa traza no está en este worktree y no la repetí.

### 16 — CSV por el chat descarta una columna sin avisar

**Causa (evidencia).** `leer_adjunto` devolvía el CSV tal cual (`test_csv_tal_cual`: el texto no pierde celdas). No había columnas medidas. Al guardar, `campo_por_clave` solo ve las claves que el modelo manda; una columna que no es campo y que el modelo no copia no aparece en «Sin llenar» ni en un error. El chat podía meter las filas sin decir qué quedó fuera.

**Arreglo.** El código lee los títulos (coma, punto y coma o tab; una coma entre comillas sigue siendo una celda) y los compara con los campos con el mismo emparejamiento que al guardar. Si una columna no es campo, el aviso se lo dice al modelo y, si la respuesta no la nombra, el código agrega: «No guardé la columna «…». ¿La agrego?». El texto del archivo se sigue entregando entero.

**Prueba.** `test_csv_con_punto_y_coma_y_comas_entre_comillas_no_pierde_columnas`, `test_csv_sin_titulos_no_inventa_columnas`, `test_columna_que_no_es_campo_se_dice_aunque_el_modelo_no_la_nombre`.

### 17 — «cuánto me paga cada miembro en promedio» (banco2)

**Causa (evidencia).** `banco2.txt`: `ERROR: la vista «estadisticas» no existe` y la respuesta ofrece barras. El prompt decía que esas cifras van en un bloque `"estadisticas"`. `estadisticas` es un tipo de gráfico (`vista "grafico"`, `opciones.tipo`), no una vista. Con solo «no existe», el modelo se rendía.

**Arreglo.** El prompt dice la forma real de la herramienta. Si piden un tipo de gráfico como vista, el error explica cómo pedirlo (`edicion.py`). El estado no cambia.

**Prueba.** El caso de paridad «agregar: gráfico que no existe…» paso 3 (vista `radar`) espera ese texto. No re-medido con IA real.

### 18 — los 7 fallos de pestañas (20/27), uno por uno

Son 3 casos, no 7 causas. 3+1+3 = 7.

1. **Calendario, 3/3.** Es el punto 15.
2. **«aquí pon arriba un resumen por estado», 1/3.** La corrida que falla tiene `fallos: ['… «b1» es un bloque del INICIO …']` y la respuesta pregunta si lo pone también en Miembros. Con la pestaña abierta, la clave `bloques` eran los del inicio. **Arreglo:** esa clave pasa a `bloques_del_inicio_no_se_ven_ahora` (mismo contenido). Prueba: `test_con_pestana_abierta_los_bloques_del_inicio_cambian_de_nombre`. Las otras 2 corridas de la base ya pasaban; falta la IA real para ver si el 1/3 se cierra.
3. **«dona y nube de palabras», 3/3.** `hizo: []`. La regla decía: si piden un tipo que no existe, no agregues nada todavía. La nube no existe y la dona sí, y no se hacía ninguna. **Arreglo:** lo que no existe no se agrega y se pregunta; lo que sí existe en el mismo pedido se hace en el turno. El cerco de sustituto ya no deshace una pieza cuyo tipo o vista está en el pedido (el id o el nombre del catálogo): «agregué la dona; lo más parecido a la nube…» deja la dona. Pruebas: `test_el_sustituto_no_deshace_la_pieza_que_si_pidieron`, `test_negar_otra_cosa_no_niega_la_dona_pedida`. No re-medido con IA real.

## Qué no cerré

### 17 — los 2 fallos de `banco_datos` (1 de 3 cada uno)

No encontré una causa determinista. No la inventé.

- **«¿qué miembros vencen en los próximos 7 días?»** (tercera corrida): `consultas=[]`, `fallos=[]`. Apuntó al bloque de vencimientos que ya está en el inicio y preguntó si listaba los nombres. Las otras dos corridas consultaron y pasaron. El verificador, a propósito, no corrige una pregunta sin acciones (`agente.py`, `_ES_PREGUNTA`): empujar ahí metería otra llamada al modelo en preguntas que ya salen en una («¿qué tengo?»).
- **«agrega una gráfica de dona por estado»** (tercera corrida): `hizo: []`. Preguntó dónde y de qué tamaño. Las otras dos la agregaron. No hubo error de herramienta. Un gancho de «no preguntes» chocaría con casos que deben preguntar («agrega a Pedro Ruiz»).

## Archivos

- `backend/app/crm/agente_diseno.py` — prompt, nombre de los bloques del inicio, cerco de sustituto, aviso de columnas
- `backend/app/crm/edicion.py` — error cuando un tipo de gráfico se pide como vista
- `backend/app/crm/adjuntos.py` — títulos del CSV/TSV/xlsx y texto de lo que no entró
- `backend/app/crm/agente.py`, `backend/app/routes/crm/crmRoutes.py` — pasan las columnas al agente de diseño
- `backend/test/crm/test_prompt_diseno.py`, `test_agente_piezas.py`, `test_adjuntos.py`, `test_herramientas_paridad.py`

## Cómo correr los bancos (lo hace el revisor)

Desde este worktree, con la clave en el entorno del servidor (no está en el repo). Puerto sugerido **5204** (en los handoffs, 5202 es citas y 5203 es memoria).

```bash
cd backend && CRM_DISENO=1 CRM_LAB_ADAPTER=1 \
  /Users/josueboror/CURSOR/HyperShifu/HyperShifu-crm-agent/backend/.venv/bin/python \
  scripts/crm_dev_server.py --puerto 5204
```

En otra terminal, desde la raíz del worktree:

```bash
export BASE=http://localhost:5204 RUTA_CHAT=/api/v1/crm/lab/chat
PY=/Users/josueboror/CURSOR/HyperShifu/HyperShifu-crm-agent/backend/.venv/bin/python
$PY laboratorio/pruebas/banco2.py
$PY laboratorio/pruebas/banco_deshacer.py 3
$PY laboratorio/pruebas/banco_toma.py 1
$PY laboratorio/pruebas/banco_ficha.py
$PY laboratorio/pruebas/banco_datos.py 3
$PY laboratorio/pruebas/banco_pestanas.py 3
```

Guardar las salidas en `~/CURSOR/HyperShifu/documentos/mediciones/2026-10-19_diagnostico/`. Comparar con la línea base. Lo que este frente toca y hay que mirar: banco2 el caso del promedio (base 15/16), banco_datos los dos casos de arriba (base 61/63; si fallan 1 de 3, repetir), banco_pestanas calendario, pieza en la pestaña abierta y dona+nube (base 20/27). No agregué casos nuevos a los bancos.

Pytest de este frente (hace falta `ENCRYPTION_KEY` y `SECRETS_ENCRYPTION_KEY` falsos: el test del reloj importa el cifrado; no leí ningún `.env`):

```bash
cd backend && MONGO_URI=mongodb://x:1 SECRET_KEY=prueba-local-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx \
  OPENAI_API_KEY=sk-falso ENCRYPTION_KEY=prueba-local-cifrado SECRETS_ENCRYPTION_KEY=prueba-local-secretos \
  /Users/josueboror/CURSOR/HyperShifu/HyperShifu-crm-agent/backend/.venv/bin/python \
  -m pytest test/crm -q -p no:cacheprovider
```

Resultado real: **17878 passed, 1 skipped**.
