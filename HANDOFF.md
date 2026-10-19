# HANDOFF — frente «citas» (rama `etapa1/citas`, worktree `wt-citas`, puerto 5202)

Base: `b4f578f` (= Shifuloading/david). Commits: `e478028` (Pendientes), `e63cf29` (citas/borrado/pantalla/no elegir/ocultas),
`602c8e9` (banco_citas), `c502c4b` (ajuste del cerco de pantalla). Sin push ni merge.

## Hecho (LISTA_PENDIENTES_2026-10-19)
- **2/43** `secciones.py` + `src/crm/secciones.js`: en comercio el tablero se llama «Pendientes». Modo diseño: herramienta `agendar`
  (`agente_diseno.HERR_AGENDAR`, `SesionDiseno._h_agendar`): la cita va como registro en la sección con vista agenda; día/hora los entiende
  el código; repeticiones (`repetir {cada, veces, hasta}`) las expande `fechas_de_cita`. `agregar_tarea`/`agregar_registro` en tareas con
  día y hora → error «usa agendar» (`_cita_como_tarea`); sin agenda → propone `crear_seccion desde="citas"`. Estado lleva `agendas`.
  El modo clásico (CRM_DISENO=0) no cambió: allí no hay agendas.
- **3** `_pedir_quitar_secciones` + `pregunta_pendiente`: la lista sale de `pantalla.secciones_visibles` (nunca ocultas), queda como
  `pendiente {tipo: "secciones", ids}`; la pregunta la escribe el código (sin otra vuelta del modelo); el «sí» lo ejecuta
  `chat._quitar_secciones` vía `ejecutar_pendiente` (sin IA). `sanear_pendiente` acepta ese tipo. El adaptador del lab reenvía `pendiente`.
- **Pantalla** `_bloque_fuera_de_pantalla`: pieza de otra pestaña solo si la persona nombró esa pestaña o la seleccionó; pieza del inicio
  mirando una pestaña solo se frena al QUITARLA. El error dice qué se ve.
- **9** `_no_nombro_campo` / `_no_nombro_seccion`: quitar algo no nombrado (ni aceptado tras propuesta de Shifu) → error con cuántos
  registros tienen lleno cada campo.
- **10** `_oculta_equivalente` (+ `secciones.OTROS_NOMBRES`): crear sección parecida a una integrada oculta → pregunta «¿la muestro o creo
  otra?»; `_seccion_datos` dice que «Equipo» solo guarda nombres y está oculta.

## Pruebas
`cd backend && <venv>/python -m pytest test/crm -q -p no:cacheprovider` → 17894 passed (nuevo `test/crm/test_citas.py`; ajustados
`test_agente_diseno.py`, `test_veracidad.py`, `test_diseno.py`). Sintaxis verificada con python3.11.

## Bancos (IA real, salidas en `documentos/mediciones/2026-10-19_citas/`, `correr.sh`)
| banco | base | rama |
|---|---|---|
| banco_citas (nuevo) | 2/9 (1 rep, base sin cambios) | 27/27 ×2 corridas, 1.9–2.5 s |
| banco2 | 15/16 1.9 s | 15/16 2.4 s (mismo caso falla; máx 9.7 s en ese caso) |
| deshacer | 18/18 | 18/18 |
| toma | 11/11 | 11/11 |
| ficha | 7/7 | 7/7 |
| datos | 61/63 | 61/63 |
| pestañas | 20/27 2.0 s | 18/27 y 19/27 (2.2–2.4 s) **← regresión sin cerrar** |

## Falta
1. **Regresión pestañas** «aquí pon arriba un resumen por estado» (mirando Miembros): falla 5/6 vs 1/3 en base. El modelo llama
   `cambiar_visual b0` (inicio) y choca con el error de `edicion._ejecutar` (L131-138). Causa probable: los textos nuevos del prompt
   (`INSTRUCCIONES_DISENO`, `INSTRUCCIONES_CARLOS_EXTRA`) o la herramienta extra `agendar`. Probar quitando una cosa a la vez y medir
   `banco_pestanas.py 3` dos veces. El resto de fallas (calendario, compuesto) es igual a la base.
2. «quita el calendario» sin calendario: no borra nada, pero todavía pregunta «¿quito el calendario del inicio?» (no existe).
3. Correr `banco_citas.py 3` en base guardado en archivo (hoy solo hay la corrida de 1 rep en este documento: 2/9).
4. Los puntos de deshacer en el «sí» del adaptador del lab no se recalculan (en la ruta real sí: `crmRoutes._turno_de_chat`).
