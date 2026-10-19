# HANDOFF — frente «memoria» (rama etapa1/memoria, worktree wt-memoria, puerto 5203)

Lista 19-oct, puntos 4, 5, 6 y 11. Commits previos: 254ea77 … 4464ba2. **Regresión datos:** commit nuevo (ver abajo).

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
- **Regresión datos (cerrada en código, banco IA pendiente del revisor):**
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
1. **Bancos con IA real** tras este fix: no corridos aquí (sin clave). Usar `correr.sh` o comandos de la sección «Regresión datos».
2. **Tiempos** banco2/ficha/pestañas: hipótesis prompt más largo + posibles correcciones de promesas; no medido post-fix.
3. banco2 2.ª corrida 14/16: ver `banco2_2.txt`.
4. Bug previo: `afirma_sin_respaldo` y cifras en ids hex (intermitente).
5. `test_reloj.py` falla sin `ENCRYPTION_KEY` en el entorno (no relacionado con memoria).

## Pruebas automatizadas (este worktree)
`cd backend && MONGO_URI=mongodb://x:1 SECRET_KEY=prueba-local-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx OPENAI_API_KEY=sk-falso /Users/josueboror/CURSOR/HyperShifu/HyperShifu-crm-agent/backend/.venv/bin/python -m pytest test/crm -q -p no:cacheprovider`

Resultado real al cerrar regresión datos: **17893 passed** en `test/crm` (1 skipped); falla `test_reloj.py` si falta `ENCRYPTION_KEY`.

## Cómo probar bancos (revisor)
Servidor: `cd backend && CRM_DISENO=1 CRM_LAB_ADAPTER=1 <venv python> scripts/crm_dev_server.py --puerto 5203`
`documentos/mediciones/2026-10-19_memoria/correr.sh` (incluye `banco_memoria.py`).
