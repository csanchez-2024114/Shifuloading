/* Buscador de arriba (lista 36): busca en todas las secciones visibles. Corre con: node --test src/crm/__pruebas__/buscar.test.mjs */
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { buscarEnCrm } from '../buscar.js'

const crm = {
  camposContacto: [{ id: 'f_ciudad', nombre: 'Ciudad', tipo: 'texto' }],
  contactos: [{ id: 'c1', n: 'Laura Gómez', det: '5555-1234', canal: 'WhatsApp', etapa: 'Nuevo', dueno: 'Tú', extra: { f_ciudad: 'Xela' } },
    { id: 'c2', n: 'Pedro Ramírez', det: '', canal: 'Local', etapa: 'Cliente', dueno: 'Tú' }],
  tareas: { porHacer: [{ id: 't1', t: 'Cita con Ramírez', vence: '2026-10-20', hora: '15:00' }], enCurso: [], hecho: [] },
  listas: [
    { id: 'l_inv', nombre: 'Inventario', campos: [{ id: 'equipo', nombre: 'Equipo' }, { id: 'marca', nombre: 'Marca' }],
      registros: [{ id: 'r1', valores: { equipo: 'Laptop', marca: 'HP' } }, { id: 'r2', valores: { equipo: 'Monitor', marca: 'Dell' } }] },
    { id: 'l_oculta', nombre: 'Viejas', campos: [{ id: 'x', nombre: 'X' }], registros: [{ id: 'r9', valores: { x: 'Ramírez escondido' } }] },
  ],
}
const MENU = [{ id: 'inicio', t: 'Inicio' }, { id: 'contactos', t: 'Clientes' }, { id: 'desarrollo', t: 'Pendientes' }, { id: 'l_inv', t: 'Inventario' }]

test('busca en contactos, tareas y secciones propias, en el orden del menú', () => {
  const r = buscarEnCrm(crm, MENU, 'ramirez')
  assert.deepEqual(r.map((s) => s.id), ['contactos', 'desarrollo'])
  assert.equal(r[0].resultados[0].titulo, 'Pedro Ramírez')
  assert.equal(r[1].resultados[0].titulo, 'Cita con Ramírez')
})

test('una sección que no está en el menú (oculta) no se busca', () => {
  assert.ok(!buscarEnCrm(crm, MENU, 'escondido').length)
})

test('si coincide un campo que no es el nombre, dice cuál', () => {
  const [inv] = buscarEnCrm(crm, MENU, 'hp')
  assert.equal(inv.id, 'l_inv')
  assert.deepEqual(inv.resultados[0], { id: 'r1', titulo: 'Laptop', detalle: 'Marca: HP' })
  assert.equal(buscarEnCrm(crm, MENU, 'xela')[0].resultados[0].detalle, 'Ciudad: Xela')
})

test('sin acentos ni mayúsculas, y con menos de 2 letras no busca', () => {
  assert.equal(buscarEnCrm(crm, MENU, 'GOMEZ')[0].resultados[0].id, 'c1')
  assert.deepEqual(buscarEnCrm(crm, MENU, 'l'), [])
})

test('como mucho N por sección, con el total', () => {
  const muchos = { ...crm, contactos: Array.from({ length: 9 }, (_, i) => ({ id: `c${i}`, n: `Ana ${i}` })) }
  const [c] = buscarEnCrm(muchos, MENU, 'ana', 5)
  assert.equal(c.total, 9); assert.equal(c.resultados.length, 5)
})
