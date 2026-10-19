# HANDOFF — frente «memoria» (rama etapa1/memoria, worktree wt-memoria, puerto 5203)

Lista 19-oct, puntos 4, 5, 6 y 11. Commits previos: 254ea77 … 685a6d3. **Regresión datos/pestañas v2** (este cierre): lo que el modelo ve en un turno normal vuelve a parecerse a david; la carga grande se queda.

## Regresión datos/pestañas v2

El revisor midió lado a lado contra david (`documentos/mediciones/2026-10-19_memoria_revision/`): banco_memoria 7→18/18, banco_datos 61/63→57/63, banco_pestañas 15/18→12/18 y más lento (2.1→2.5 s). El detector por palabras ya se había quitado (685a6d3); no volvió.

Los dos fallos de datos son de la **primera** llamada (~1.0–1.9 s, sin herramientas): «¿quiénes vencen este mes?» contestaba con la config del bloque de vencimientos (rango de 30 días) y no llamaba `consultar_datos`; «agrega una gráfica de dona por estado» preguntaba en vez de agregar la gráfica (`hizo: []`, el caso pide una dona y que los registros no cambien). Esos bancos no mandan historial: el cambio que veía el modelo en ese turno era el catálogo y el prompt, no la ventana.

### Qué cambió (y por qué esa opción)

1. **Misma herramienta, con lista.** Se quitó `agregar_registros` del catálogo de diseño. `agregar_registro` sigue llamándose igual y sigue exigiendo `seccion` + `valores`; además acepta `registros` (lista) y esa llamada cuenta como **una** acción (`_varios`). Una herramienta nueva, siempre visible, era lo que el modelo veía de más en cada turno (~la descripción empujaba a «agregar»). El alias de Carlos, si lo llama, sigue yendo al mismo handler, pero no se le ofrece. La frase extra de `INSTRUCCIONES_DISENO` («usa agregar_registros») también salió: esa sección del prompt queda como en david.
2. **Ventana = los mismos 16 mensajes, completos.** Antes el presupuesto de 3 000 tokens metía ~40 «sí» (más charla que david) y, con mensajes enormes, se quedaba en 2. Ahora `ventana()` corta por cantidad (16), no por tokens, y no recorta cada texto a 500. Un turno corto ve el mismo número de mensajes que david; si alguno pasa de 500 caracteres, el modelo lo ve entero (el caso «ya te los pasé»). El resumen rodante solo se pide y solo entra al prompt cuando hay mensajes **fuera** de esos 16. Con 16 o menos, no hay resumen.
3. **Pendientes y campos vacíos solo si hay algo.** `por_hacer.bloque` y `aviso_campos_vacios` ya devolvían vacío si no había nada; un turno sin pendientes no lleva ni «Pendiente de mensajes anteriores» ni el aviso de huecos. El cerco de promesas no está en el primer prompt: solo agrega una corrección si la respuesta promete en futuro algo que no corrió. En un turno normal (el modelo hace la herramienta o contesta sin prometer) el modelo no ve ese aviso.

Lo que **no** cambia lo que ve el modelo, y se conserva: cada mensaje se guarda completo en `crm_conversaciones` (`MAX_TEXTO` 16 000), numerado. La carga de muchos registros cabe en una llamada; lo que pase del tope de acciones o de 50 por llamada sigue en `por_hacer` con sus datos.

### Qué debe medir el revisor (IA real; aquí no se corrieron bancos)

`BASE=http://localhost:5203 RUTA_CHAT=/api/v1/crm/lab/chat` desde este worktree. Salida nueva en `documentos/mediciones/2026-10-19_memoria/` (corrida post-v2), al lado de `2026-10-19_memoria_revision/`.

- `laboratorio/pruebas/banco_datos.py 3` — «¿quiénes vencen este mes?» con `consultas` (no hablar del bloque de 30 días); «agrega una gráfica de dona por estado» agrega un bloque `grafico` y no toca registros. Meta: volver hacia 61/63.
- `laboratorio/pruebas/banco_pestanas.py 3` — tiempo hacia ~2.1 s (la revisión dio 2.5 s) y los casos que preguntaron en vez de hacer: calendario en el inicio, dona + nube de palabras, gráfica en la pestaña de pagos. Meta: no quedar en 12/18.
- `laboratorio/pruebas/banco_memoria.py` — la carga grande no debe bajar: 18/18 registros, mensaje guardado completo, «ya te los pasé» recupera lo que faltó.

## Qué quedó hecho
- **4 Memoria** (`backend/app/crm/memoria.py`): cada mensaje se guarda COMPLETO (`MAX_TEXTO` 16 000) y numerado (`n`, `contador`) en
  `crm_conversaciones`. Al modelo: los últimos 16 mensajes, completos (`ventana`). El resumen rodante (`resumen: {texto, hasta}`) solo pliega
  lo que ya no cabe en esos 16, en la MISMA llamada en segundo plano (`actualizar_memoria`, `a_plegar`, `sanear_resumen`), con la instrucción
  del compactor de Alan en `SISTEMA_MEMORIA`. `agente._mensajes` ya no corta a 500: usa `memoria.ventana` (tope 16).
- **5 Carga por lotes / pendientes** (`agente_diseno.py`, `por_hacer.py`): la lista va en `agregar_registro` (mismo nombre; `HERR_AGREGAR_REGISTRO`),
  mismo handler `_varios`. Lo que pasa del tope de acciones (`AVISO_TOPE`) o de 50 por llamada queda en `sesion.por_hacer`; `salida["por_hacer"]`
  = `ph.seguir(...)`. La ruta lo guarda en `crm_conversaciones.por_hacer` y lo pasa al turno siguiente **solo si la lista no está vacía**.
- **6 Promesas**: `SesionDiseno.promesas_sin_respaldo` + `aviso_promesa` en `agente.revisar_respuesta` (corrección, no texto fijo del prompt).
- **11 Campos vacíos**: `SesionDiseno.aviso_campos_vacios` tras una vuelta con herramientas, solo si quedó un hueco con el dato en el texto.
- Pruebas: `test_memoria_larga.py`. Banco: `laboratorio/pruebas/banco_memoria.py`.

## Qué quedó hecho
- **4 Memoria** (`backend/app/crm/memoria.py`): cada mensaje se guarda COMPLETO (`MAX_TEXTO` 16 000) y numerado (`n`, `contador`) en
  `crm_conversaciones`. Al modelo: `ventana()` por presupuesto de tokens (`PRESUPUESTO_VENTANA` 3 000, 3.2 caracteres/token medido con
  o200k_base) + `bloque_resumen()`. El resumen rodante (`resumen: {texto, hasta}`) lo pone al día la MISMA llamada en segundo plano de cada
  4 mensajes (`actualizar_memoria`, `a_plegar`, `sanear_resumen`), con la instrucción del compactor de Alan en `SISTEMA_MEMORIA`.
  `agente._mensajes` ya no corta a 500 ni a 16 mensajes: usa `memoria.ventana`. La ruta (`crmRoutes.chat_crm`) suma el resumen al bloque de persona.
- **5 Carga por lotes / pendientes** (`agente_diseno.py`, `por_hacer.py`): `agregar_registros` visible en diseño (`HERR_AGREGAR_VARIOS`,
  mismo handler `_varios`). Lo que pasa del tope de acciones (`AVISO_TOPE`) o de 50 por llamada queda en `sesion.por_hacer`; `salida["por_hacer"]`
  = `ph.seguir(...)`. La ruta lo guarda en `crm_conversaciones.por_hacer` y lo pasa al turno siguiente.
- **6 Promesas**: `SesionDiseno.promesas_sin_respaldo` + `aviso_promesa` en `agente.revisar_respuesta`.
- **11 Campos vacíos**: `SesionDiseno.aviso_campos_vacios` tras cada vuelta con herramientas.
- Pruebas: `test_memoria_larga.py` (21). Banco: `laboratorio/pruebas/banco_memoria.py`.
- **Regresión datos, primer intento (revertido en 685a6d3; no es el arreglo vigente):**
  - **Causa (evidencia):** En `banco_datos.py` el caso «¿quiénes vencen este mes?» fallaba ~3/6 con respuesta en ~1.2 s, sin `consultas`, hablando del
    **bloque** de vencimientos (`grupos_actuales` en el JSON de pantalla, p. ej. «30 días») en vez de `consultar_datos`. Comparando `david...HEAD`:
    el contexto de pantalla no cambió; sí el prompt del sistema (herramienta `HERR_AGREGAR_VARIOS` ~+400 caracteres en el catálogo) y una línea extra en
    `INSTRUCCIONES_DISENO` sobre lotes (redundante con la descripción de la herramienta). `revisar_respuesta` ya tenía salida temprana para preguntas sin
    acciones (l.948–949 `agente.py`) y `aviso_numero_inventado` solo corre **después** de una consulta, así que no había cerco cuando el modelo no llamaba
    herramientas. No era el cerco de promesas (sin segunda vuelta en los fallos de 1.2 s).
  - **Cambio:** `registros.pregunta_pide_consulta` (periodo con `parse_periodo`, cuántos + sección nombrada, quién + campo fecha, etc.) +
    `SesionDiseno.aviso_consulta_datos` en `revisar_respuesta` **antes** de la salida temprana de preguntas. Quitada la línea duplicada de `INSTRUCCIONES_DISENO`
    sobre `agregar_registros` (sigue en `HERR_AGREGAR_VARIOS`). Prueba: `test_pregunta_vencimientos_sin_consultar_se_corrige` en `test_agente_diseno.py`.
  - **Qué medir (revisor, IA real):** `BASE=http://localhost:5203 RUTA_CHAT=/api/v1/crm/lab/chat` → `laboratorio/pruebas/banco_datos.py 3` (el caso del mes
    debe ir 6/6 con `consultas`); repetir `banco2.py`, `banco_ficha.py`, `banco_pestanas.py 3` para ver si bajan los +0.3–0.5 s (menos prompt + una corrección
    extra solo cuando el modelo se salta la consulta). Salida en `documentos/mediciones/2026-10-19_memoria/` (nueva corrida post-fix).

## Bancos (IA real) — salidas en documentos/mediciones/2026-10-19_memoria/
| banco | base (linea_base / veracidad = b4f578f) | rama (antes del fix) |
|---|---|---|
| memoria (nuevo) | 9.0/18, verdad 0/3, completo 0/3, 9.5 s | 18/18 y 16.3/18, verdad 3/3 y 3/3, completo 3/3, 9.8 / 9.7 s |
| banco2 | 15/16 1.9–2.1 s | 16/16 2.4 s · 14/16 2.4 s |
| deshacer | 18/18 | 18/18 |
| toma | 11/11 1.9 s | 11/11 1.6 s |
| ficha | 7/7 2.0 s | 7/7 2.3 s · 7/7 2.6 s |
| datos | 61/63 1.9 s | 59/63 2.0 s · 60/63 2.1 s (**«este mes»** intermitente) |
| pestañas | 20/27 2.0 s | 20/27 2.3 s · 20/27 2.5 s |

## Qué falta / riesgos
1. **Bancos con IA real** de la v2: no corridos aquí (sin clave). Los casos están en «Regresión datos/pestañas v2». El detector por palabras de f54471c sigue fuera (685a6d3).
2. **Tiempos** banco2/ficha/pestañas: no medidos post-v2. El primer prompt de un turno normal ya no lleva la herramienta extra ni más de 16 mensajes; una corrección de promesa sigue sumando una vuelta solo si el modelo promete sin hacer.
3. banco2 2.ª corrida 14/16: ver `banco2_2.txt` (corrida anterior, no de esta v2).
4. Bug previo: `afirma_sin_respaldo` y cifras en ids hex (intermitente).
5. `test_reloj.py` importa `app.core.security`, que exige `SECRETS_ENCRYPTION_KEY` al cargar el módulo (no es de memoria). Con un valor falso pasa.

## Pruebas automatizadas (este worktree)
`cd backend && MONGO_URI=mongodb://x:1 SECRET_KEY=prueba-local-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx OPENAI_API_KEY=sk-falso SECRETS_ENCRYPTION_KEY=prueba-local-secrets-key-xxxxxxxx /Users/josueboror/CURSOR/HyperShifu/HyperShifu-crm-agent/backend/.venv/bin/python -m pytest test/crm -q -p no:cacheprovider`

Resultado real al cerrar la v2: **17895 passed**, 1 skipped, en `test/crm`. Sin `SECRETS_ENCRYPTION_KEY`: **17894 passed**, 1 skipped, y falla `test_reloj.py` (`Missing SECRETS_ENCRYPTION_KEY`). Modelo falso; no se llamó a OpenAI.

## Cómo probar bancos (revisor)
Servidor: `cd backend && CRM_DISENO=1 CRM_LAB_ADAPTER=1 <venv python> scripts/crm_dev_server.py --puerto 5203`
`documentos/mediciones/2026-10-19_memoria/correr.sh` (incluye `banco_memoria.py`).
