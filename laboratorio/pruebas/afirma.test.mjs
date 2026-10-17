// Detector de «afirma un cambio» (D51): casos reales de la prueba de cliente. Uso: node laboratorio/pruebas/afirma.test.mjs
import assert from 'node:assert/strict'
import { afirmaCambio } from '../servidor/afirma.js'
let ok = 0
const caso = (t, e) => { try { assert.equal(afirmaCambio(t), e); ok++ } catch { console.log(`✗ «${t}» → esperaba ${e}`); process.exitCode = 1 } }
// Afirman un cambio (si ninguna herramienta cambió nada, es mentira y el código lo corrige)
for (const t of ['Agregué a Juan Pérez con plan mensual.', 'Listo, puse el tema oscuro.', 'Creé la sección Cobros y la puse en el inicio. ¿Quieres algo más?',
  'Hice la gráfica más grande y la moví arriba.', 'Borré a Ana Gómez de las membresías.', 'Cambié el estado de Ana a Pausada; no pude poner la fecha.',
  'Lista la tabla de clases.', 'Ya renombré la pestaña a Cobranza']) caso(t, true)
// No afirman nada (todos vistos en respuestas reales que el cerco descartaba)
for (const t of ['Tienes 2 miembros activos y no hay monto registrado para ellos. ¿Quieres que agregue el monto para Juan?',
  'Para registrar ese pago necesito que exista una sección de cobros. ¿Quieres que cree la sección "cobros"?',
  'No hice ningún cambio, solo consulté datos para responderte.', 'Todavía no lo agregué: dime la fecha exacta.',
  'No hay opción para exportar a Excel. ¿Quieres que te muestre la tabla de miembros?', 'Nadie vence este mes en membresías.',
  '¿Lo pongo arriba de todo?', 'Puedo agregar un bloque con la tabla, ¿lo agrego al inicio?', 'Este mes te pagaron un total de Q31,120.',
  'Si quieres, la creo para que puedas registrar pagos']) caso(t, false)
console.log(`${ok} pruebas bien`)
