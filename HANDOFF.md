# HANDOFF — frente «citas» (rama `etapa1/citas`, worktree `wt-citas`, puerto 5202)

Base: `b4f578f` (= Shifuloading/david al partir; `david` luego avanzó). Commits: `e478028` (Pendientes), `e63cf29` (citas/borrado/pantalla/no elegir/ocultas),
`602c8e9` (banco_citas), `c502c4b` (ajuste del cerco de pantalla), `39c0714` (el resumen pedido en la pestaña abierta no se cambia en el inicio). Sin push ni merge.

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
| pestañas | 20/27 2.0 s | 18/27 y 19/27 (2.2–2.4 s), antes del arreglo de abajo |

## Regresión pestañas

**Causa** (diff de lo que ve el modelo + salidas en `documentos/mediciones/2026-10-19_citas/pestanas*.txt`). El caso ya fallaba 1/3 en
david con el mismo error de `edicion`. Aquí falló 5/6. Dos cambios de esta rama lo empujan, y el atajo de `c502c4b` cierra mal la salida:

1. En el estado, `desarrollo.para_que` pasó de «aquí se llevan pedidos…» a «las citas van en una agenda, **no aquí**». «aquí» es la
   palabra que ata el pedido a `pestana_abierta` (comentario de `pestana_abierta`: sin eso «aquí pon…» caía en el inicio). Es el único
   «aquí» nuevo en el prompt y el contexto de este caso. La herramienta `agendar` no nombra «aquí», «resumen» ni «inicio».
2. El resumen por estado ya está en `bloques` como b0 (kpis, `por: estado`, fila 1). El modelo llama `cambiar_visual` sobre b0. `c502c4b`
   dejó pasar ese cambio a `edicion`, cuyo error dice «si pidió el inicio, pon pestana="inicio"». Las 5 fallas lo confirman:
   `hizo: [('cambiar_visual', 'inicio', 'kpis')]` y la respuesta dice que lo puso en el inicio. La pestaña Miembros no recibe la pieza.
   En la base, la única falla de este caso tiene `hizo: []`: no llegó a aplicar el `pestana="inicio"`.

La frase «no crees una igual» (secciones ocultas) también se leía como «no dupliques la pieza que ya existe». Quedó «no crees otra sección
para lo mismo».

**Cambio.** `SesionDiseno._a_la_pestana_abierta`: si llama `cambiar_visual` sobre una pieza del inicio mientras mira una pestaña que no
nombró, el código agrega esa vista en la pestaña abierta (`agregar_bloque`). El modelo eligió la vista; el destino lo calcula el código
(la misma regla que `agregar_bloque` sin pestana). Si nombró el inicio, se cambia el inicio. `para_que` del tablero dice «no en este
tablero», ya no «no aquí». Al quitar una pieza de otra pestaña, el error dice que no ofrezca quitarla (el calendario que no existe).

**Caso a medir** (no corrí la IA real: no hay clave). Con el servidor en el puerto 5202, desde la raíz del worktree:

`BASE=http://localhost:5202 RUTA_CHAT=/api/v1/crm/lab/chat python laboratorio/pruebas/banco_pestanas.py 3`

El caso es «pieza en la pestaña que está mirando» / «aquí pon arriba un resumen por estado»: la pestaña Miembros debe quedar con un kpis
y el inicio en `['kpis', 'vencimientos']`. Repetirlo (el caso es ruidoso: la base dio 2/3 y diseño, sin estos textos, 2/6). También
`banco_citas.py` con `VER=1`, el caso «quita el calendario»: no debe borrar y no debe ofrecer quitar un calendario del inicio.
`banco_citas` tiene que seguir 27/27.

## Falta
1. Medir la regresión (comando de arriba) y `banco_citas` otra vez con IA real. El código y el modelo falso ya cubren el camino que
   fallaba; la tasa con gpt-4.1-mini no está medida en esta pasada.
2. Correr `banco_citas.py 3` en base guardado en archivo (hoy solo hay la corrida de 1 rep en este documento: 2/9).
3. Los puntos de deshacer en el «sí» del adaptador del lab no se recalculan (en la ruta real sí: `crmRoutes._turno_de_chat`).
