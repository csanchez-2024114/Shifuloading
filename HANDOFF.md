# HANDOFF — frente «memoria» (rama etapa1/memoria, worktree wt-memoria, puerto 5203)

Lista 19-oct, puntos 4, 5, 6 y 11. Todo commiteado (254ea77, ef01a87, e245c43). Pruebas: 17892 en verde (`test/crm`).

## Qué quedó hecho
- **4 Memoria** (`backend/app/crm/memoria.py`): cada mensaje se guarda COMPLETO (`MAX_TEXTO` 16 000) y numerado (`n`, `contador`) en
  `crm_conversaciones`. Al modelo: `ventana()` por presupuesto de tokens (`PRESUPUESTO_VENTANA` 3 000, 3.2 caracteres/token medido con
  o200k_base) + `bloque_resumen()`. El resumen rodante (`resumen: {texto, hasta}`) lo pone al día la MISMA llamada en segundo plano de cada
  4 mensajes (`actualizar_memoria`, `a_plegar`, `sanear_resumen`), con la instrucción del compactor de Alan en `SISTEMA_MEMORIA`.
  `agente._mensajes` ya no corta a 500 ni a 16 mensajes: usa `memoria.ventana`. La ruta (`crmRoutes.chat_crm`) suma el resumen al bloque de persona.
- **5 Carga por lotes / pendientes** (`agente_diseno.py`, nuevo `por_hacer.py`): `agregar_registros` visible en diseño (`HERR_AGREGAR_VARIOS`,
  mismo handler `_varios`). Lo que pasa del tope de acciones (`AVISO_TOPE`) o de 50 por llamada queda en `sesion.por_hacer` con sus datos;
  `salida["por_hacer"]` = `ph.seguir(...)` (quita lo que ya está en el CRM, máx. 3 turnos). La ruta lo guarda en `crm_conversaciones.por_hacer`
  y lo pasa al turno siguiente (`agente.responder(..., por_hacer=)`), que lo ve en el prompt (`ph.bloque`). El código escribe la línea
  «Quedó pendiente por el límite…» (`ph.linea`). Si el modelo agota vueltas, responde `respuesta_del_codigo`, no el texto crudo de una herramienta.
- **6 Promesas**: `SesionDiseno.promesas_sin_respaldo` (futuro -aré/-eré/-iré/-dré, sin preguntas ni negaciones; respaldado si sus palabras
  están en los args de los cambios o en lo pendiente). `aviso_promesa` en `agente.revisar_respuesta` (antes de la salida de preguntas). Si
  insiste, queda como `promesa` pendiente + línea «Ojo: … todavía no está hecho» del código.
- **11 Campos vacíos**: `SesionDiseno.aviso_campos_vacios` tras cada vuelta con herramientas (sin llamada extra): campo vacío en un registro
  del turno que otro registro del turno llenó con dato del texto, o cuyo nombre aparece en el texto.
- Pruebas nuevas: `backend/test/crm/test_memoria_larga.py` (21). Banco nuevo: `laboratorio/pruebas/banco_memoria.py` (ruta real, crea cuenta).

## Bancos (IA real) — salidas en documentos/mediciones/2026-10-19_memoria/
| banco | base (linea_base / veracidad = b4f578f) | rama (1.ª / 2.ª corrida) |
|---|---|---|
| memoria (nuevo) | 9.0/18, verdad 0/3, completo 0/3, 9.5 s | 18/18 y 16.3/18, verdad 3/3 y 3/3, completo 3/3, 9.8 / 9.7 s |
| banco2 | 15/16 1.9–2.1 s | 16/16 2.4 s · 14/16 2.4 s |
| deshacer | 18/18 | 18/18 |
| toma | 11/11 1.9 s | 11/11 1.6 s |
| ficha | 7/7 2.0 s | 7/7 2.3 s · 7/7 2.6 s |
| datos | 61/63 1.9 s | 59/63 2.0 s · 60/63 2.1 s |
| pestañas | 20/27 2.0 s | 20/27 2.3 s · 20/27 2.5 s |

## Qué falta / riesgos sin cerrar (NO verificado que esté bien)
1. **datos**: «¿quiénes vencen este mes?» falla 3 de 6 en la rama (en la base no fallaba): el modelo responde en 1 llamada sin consultar.
   No es un cerco (1.2 s, sin corrección); sospecha: el prompt cambió (herramienta `agregar_registros` + línea nueva en `INSTRUCCIONES_DISENO`).
   Probar quitando esa línea de INSTRUCCIONES_DISENO y repetir `banco_datos.py 3`.
2. **Tiempos** +0.3–0.5 s en banco2/ficha/pestañas. Medir cuántas veces dispara `aviso_promesa` (no se registró): contar `avisos` con «Dices «»
   en la salida del lab. Si es el cerco de promesas, restringirlo.
3. banco2 2.ª corrida 14/16: ver `banco2_2.txt` (no revisado).
4. Bug previo (no mío): `afirma_sin_respaldo` toma cifras de los ids hex de los resultados → el aviso es aleatorio (vi una prueba intermitente).
5. Corrida 2 del banco de memoria: el modelo agregó bloques al inicio sin que se pidieran y gastó el tope (quedaron como pendientes).

## Cómo probar
`cd backend && /Users/josueboror/CURSOR/HyperShifu/HyperShifu-crm-agent/backend/.venv/bin/python -m pytest test/crm -q -p no:cacheprovider`
Servidor: `cd backend && CRM_DISENO=1 CRM_LAB_ADAPTER=1 <venv python> scripts/crm_dev_server.py --puerto 5203`; bancos:
`documentos/mediciones/2026-10-19_memoria/correr.sh` (incluye banco_memoria).
