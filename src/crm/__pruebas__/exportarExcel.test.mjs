/* Punto 45: la exportación a Excel decide el formato por el TIPO del campo, no por el nombre de la columna.
 * Corre con: node --test src/crm/__pruebas__/exportarExcel.test.mjs (desde la raíz del proyecto). */
import test from 'node:test'
import assert from 'node:assert/strict'
import { celda, hojasDelCrm } from '../exportarExcel.js'

test('dinero sale como número con dos decimales, aunque la columna no diga «precio»', () => {
  assert.deepEqual(celda('dinero', 1250.5), { value: 1250.5, type: Number, format: '#,##0.00' })
  assert.deepEqual(celda('dinero', '300'), { value: 300, type: Number, format: '#,##0.00' })
  assert.deepEqual(celda('dinero', 0), { value: 0, type: Number, format: '#,##0.00' })
})

test('un número cuyo nombre parece dinero ya no se formatea como dinero', () => {
  assert.deepEqual(celda('numero', 7), { value: 7, type: Number, format: '#,##0.##' })
})

test('texto que parece precio sigue siendo texto; lo que no es número queda tal cual', () => {
  assert.deepEqual(celda('texto', '150'), { value: '150', type: String })
  assert.deepEqual(celda('dinero', 'a convenir'), { value: 'a convenir', type: String })
  assert.deepEqual(celda('dinero', '  '), { value: '  ', type: String })
  assert.equal(celda('dinero', null), null)
  assert.equal(celda('dinero', ''), null)
})

test('fechas como fechas', () => {
  const c = celda('fecha', '2026-10-19')
  assert.equal(c.type, Date)
  assert.equal(c.value.toISOString().slice(0, 10), '2026-10-19')
})

test('hojasDelCrm usa el tipo de cada campo en listas y en campos extra de clientes', () => {
  const crm = {
    ocultas: ['desarrollo'],
    camposContacto: [{ id: 'f_saldo', nombre: 'Le debe', tipo: 'dinero' }],
    contactos: [{ n: 'Ana', det: '5555', canal: 'WhatsApp', etapa: 'Nuevo', dueno: 'Tú', dias: 3, extra: { f_saldo: 80 } }],
    listas: [{ nombre: 'Ventas', campos: [{ id: 'q', nombre: 'Cuánto', tipo: 'dinero' }, { id: 'p', nombre: 'Precio de lista', tipo: 'texto' }],
      registros: [{ valores: { q: 99.9, p: 'Q100' } }] }],
  }
  const [clientes, ventas] = hojasDelCrm(crm)
  assert.equal(clientes.sheet, 'Clientes')
  assert.deepEqual(clientes.data[1][5], { value: 80, type: Number, format: '#,##0.00' })
  assert.deepEqual(clientes.data[1][6], { value: 3, type: Number, format: '#,##0.##' })
  assert.deepEqual(ventas.data[1][0], { value: 99.9, type: Number, format: '#,##0.00' })
  assert.deepEqual(ventas.data[1][1], { value: 'Q100', type: String })
})
