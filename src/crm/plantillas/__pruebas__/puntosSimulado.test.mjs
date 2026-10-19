/* Puntos de deshacer del servidor simulado (src/api/mock/puntos.js): selectivo por categoría y sección, en cadena, los últimos 30.
 * Corre con: node src/crm/plantillas/__pruebas__/puntosSimulado.test.mjs (desde la raíz del proyecto). */
import { createServer } from 'vite'
import assert from 'node:assert/strict'
const mem = new Map()
globalThis.localStorage = { getItem: (k) => (mem.has(k) ? mem.get(k) : null), setItem: (k, v) => mem.set(k, String(v)), removeItem: (k) => mem.delete(k) }
const v = await createServer({ configFile: 'vite.config.js', cacheDir: process.env.VITE_CACHE_DIR, server: { middlewareMode: true, hmr: false }, optimizeDeps: { noDiscovery: true, entries: [] }, logLevel: 'error' })
const P = await v.ssrLoadModule('/src/api/mock/puntos.js')
let ok = 0
const caso = (n, fn) => { try { mem.clear(); fn(); ok++; console.log('✓', n) } catch (e) { console.log('✗', n, '\n ', e.stack); process.exitCode = 1 } }

const base = () => ({
  contactos: [{ id: 'c1', n: 'Ana' }], totalContactos: 1, tareas: { porHacer: [{ id: 't1', t: 'Llamar' }], enCurso: [], hecho: [] },
  listas: [{ id: 'l_m', nombre: 'Miembros', campos: [], registros: [{ id: 'r1', valores: { nombre: 'Ejemplo' }, ejemplo: true }, { id: 'r2', valores: { nombre: 'Mío' } }], importaciones: [] }],
  secciones: {}, eventos: [],
})

caso('sin cambio no hay punto', () => { const s = base(); P.anotar(s, { ...s }, 'nada'); assert.equal(P.vista().length, 0) })

caso('deshacer solo lo de ese pedido (otra sección se queda)', () => {
  const s0 = base()
  const s1 = { ...s0, contactos: [{ id: 'c2', n: 'Beto' }, ...s0.contactos], totalContactos: 2 }; P.anotar(s0, s1, 'A mano: agregó a Beto')
  const s2 = { ...s1, tareas: { ...s1.tareas, porHacer: [] } }; P.anotar(s1, s2, 'A mano: eliminó la tarea «Llamar»')
  assert.deepEqual(P.vista().map((p) => [p.n, p.antesDe, p.cambio]), [[1, 'A mano: agregó a Beto', ['datos']], [2, 'A mano: eliminó la tarea «Llamar»', ['datos']]])
  const r = P.deshacer(s2, 1)
  assert.equal(r.crm.contactos.length, 1); assert.equal(r.crm.totalContactos, 1)
  assert.equal(r.crm.tareas.porHacer.length, 0, 'la tarea borrada después sigue borrada')
  assert.deepEqual(r.deshechos, [1]); assert.match(r.texto, /^Deshecho el pedido 1 «A mano: agregó a Beto» \(los registros quedaron como antes\)\. Lo demás quedó igual\.$/)
  assert.deepEqual(P.vista().map((p) => p.n), [2])
})

caso('a 3 vías: deshacer un registro de la misma sección deja los demás, y los posteriores no lo reviven', () => {
  const s0 = base()
  const s1 = { ...s0, contactos: [{ id: 'c2', n: 'Beto' }, ...s0.contactos], totalContactos: 2 }; P.anotar(s0, s1, 'agrega a Beto')
  const s2 = { ...s1, contactos: [{ id: 'c3', n: 'Carla' }, ...s1.contactos], totalContactos: 3 }; P.anotar(s1, s2, 'agrega a Carla')
  const r = P.deshacer(s2, 1)
  assert.deepEqual(r.deshechos, [1]); assert.deepEqual(r.crm.contactos.map((c) => c.n), ['Carla', 'Ana']); assert.equal(r.crm.totalContactos, 2)
  const r2 = P.deshacer(r.crm, 2)
  assert.deepEqual(r2.crm.contactos.map((c) => c.n), ['Ana'], 'deshacer a Carla no revive a Beto'); assert.equal(r2.crm.totalContactos, 1)
})

caso('a 3 vías por campo: una tarea movida y luego renombrada', () => {
  const s0 = base()
  const s1 = { ...s0, tareas: { porHacer: [], enCurso: [{ id: 't1', t: 'Llamar' }], hecho: [] } }; P.anotar(s0, s1, 'mueve')
  const s2 = { ...s1, tareas: { porHacer: [], enCurso: [{ id: 't1', t: 'Llamar hoy' }], hecho: [] } }; P.anotar(s1, s2, 'renombra')
  const r = P.deshacer(s2, 1)
  assert.deepEqual(r.deshechos, [1]); assert.deepEqual(r.crm.tareas.porHacer, [{ id: 't1', t: 'Llamar hoy' }], 'vuelve de columna y se queda con su nombre nuevo')
})

caso('en cadena si uno posterior tocó lo mismo, y se dice', () => {
  const s0 = base()
  const s1 = { ...s0, contactos: [{ id: 'c2', n: 'Beto' }, ...s0.contactos] }; P.anotar(s0, s1, 'agrega a Beto')
  const s2 = { ...s1, contactos: s1.contactos.map((c) => ({ ...c, n: c.n + '!' })) }; P.anotar(s1, s2, 'ponles !')
  const r = P.deshacer(s2) // sin n: el último
  assert.deepEqual(r.deshechos, [2]); assert.deepEqual(r.crm.contactos.map((c) => c.n), ['Beto', 'Ana'])
  const s3 = { ...r.crm, contactos: r.crm.contactos.map((c) => (c.id === 'c2' ? { ...c, det: '555' } : c)) }; P.anotar(r.crm, s3, 'teléfono de Beto')
  const r2 = P.deshacer(s3, 1)
  assert.deepEqual(r2.deshechos, [1, 3]); assert.match(r2.texto, /También se deshizo «teléfono de Beto» porque cambiaba lo mismo\./)
  assert.deepEqual(r2.crm.contactos, s0.contactos); assert.equal(P.vista().length, 0)
})

caso('estructura y datos por separado', () => {
  const s0 = base()
  const s1 = { ...s0, secciones: { contactos: 'Clientes' } }; P.anotar(s0, s1, 'renombra')
  assert.deepEqual(P.vista()[0].cambio, ['estructura'])
  const s2 = { ...s1, listas: s1.listas.map((l) => ({ ...l, registros: [] })) }; P.anotar(s1, s2, 'vacía')
  const r = P.deshacer(s2, 1)
  assert.deepEqual(r.crm.secciones, {}); assert.equal(r.crm.listas[0].registros.length, 0, 'los registros no vuelven con la estructura')
})

caso('quitar ejemplos: solo los marcados; sin ejemplos, 404', () => {
  const s = P.quitarEjemplos(base())
  assert.deepEqual(s.listas[0].registros.map((r) => r.id), ['r2']); assert.match(s.eventos[0].t, /Quitaste 1 registro de ejemplo/)
  assert.throws(() => P.quitarEjemplos(s), (e) => e.estado === 404)
})

caso('se guardan los últimos 30', () => {
  let s = base()
  for (let i = 0; i < 35; i++) { const x = { ...s, contactos: [{ id: `x${i}`, n: `N${i}` }] }; P.anotar(s, x, `p${i}`); s = x }
  const ps = P.vista(); assert.equal(ps.length, 30); assert.equal(ps[0].n, 6); assert.equal(ps.at(-1).n, 35)
})

caso('nada que deshacer: 404', () => { assert.throws(() => P.deshacer(base()), (e) => e.estado === 404 && e.message === 'No hay nada que deshacer.') })

await v.close()
console.log(`${ok} bien`)
