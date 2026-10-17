/* Lo calculable de meter datos por chat (valores.js): fechas, montos, horas, opciones y a qué registro se refiere.
 * Corre con: node laboratorio/pruebas/valores.test.mjs (desde la raíz de Shifuloading). Sin IA. */
import assert from 'node:assert/strict'
import { parseFecha, parseNumero, parseHora, opcionDe, buscarRegistro, parsePeriodo, fechaLarga } from '../src/plantillas/valores.js'
const HOY = new Date(2026, 9, 16) // viernes 16 de octubre de 2026
let ok = 0
const caso = (n, fn) => { try { fn(); ok++ } catch (e) { console.log('✗', n, '\n ', e.message); process.exitCode = 1 } }
const F = [['2026-10-30', '2026-10-30'], ['30/10/2026', '2026-10-30'], ['30-10-26', '2026-10-30'], ['30/10', '2026-10-30'], ['el 30 de octubre', '2026-10-30'],
  ['30 de octubre de 2027', '2027-10-30'], ['30 oct', '2026-10-30'], ['oct 30', '2026-10-30'], ['hoy', '2026-10-16'], ['mañana', '2026-10-17'], ['pasado mañana', '2026-10-18'],
  ['ayer', '2026-10-15'], ['en 5 días', '2026-10-21'], ['dentro de dos semanas', '2026-10-30'], ['en un mes', '2026-11-16'], ['hace 3 días', '2026-10-13'],
  ['el viernes', '2026-10-23'], ['el próximo jueves', '2026-10-22'], ['el lunes', '2026-10-19'], ['31/02/2026', null], ['cuando pueda', null], ['', null]]
for (const [t, e] of F) caso(`fecha «${t}»`, () => assert.equal(parseFecha(t, HOY), e))
const N = [['Q1,200.50', 1200.5], ['1.200,50', 1200.5], ['$ 300', 300], ['500 quetzales', 500], ['12,5', 12.5], ['1,200', 1200], ['1,200,000', 1200000], ['1.200.000', 1200000], ['3.5', 3.5], [45, 45], ['nada', null]]
for (const [t, e] of N) caso(`número «${t}»`, () => assert.equal(parseNumero(t), e))
const H = [['9am', '09:00'], ['9:30', '09:30'], ['15:00', '15:00'], ['3 pm', '15:00'], ['3 de la tarde', '15:00'], ['8 de la noche', '20:00'], ['12 am', '00:00'], ['mediodía', '12:00'], ['25:00', null], ['tarde', null]]
for (const [t, e] of H) caso(`hora «${t}»`, () => assert.equal(parseHora(t), e))
const est = { opciones: ['Activa', 'Pausada', 'Cancelada'] }
caso('opción sin mayúsculas ni acentos', () => { assert.equal(opcionDe(est, 'pausada'), 'Pausada'); assert.equal(opcionDe(est, 'Congelada'), null) })
const sec = { id: 'miembros' }, campos = [{ id: 'nombre', tipo: 'texto' }, { id: 'plan', tipo: 'texto' }, { id: 'estado', tipo: 'estado' }]
const R = [{ id: 'a', valores: { nombre: 'Ana López', plan: 'Mensual' } }, { id: 'b', valores: { nombre: 'Ana Martínez', plan: 'Anual' } }, { id: 'c', valores: { nombre: 'Carlos Pérez', plan: 'Mensual' } }]
caso('nombre exacto (sin acentos)', () => assert.equal(buscarRegistro(R, sec, campos, 'ana lopez').registro.id, 'a'))
caso('palabra suelta que coincide con 2 → candidatos (no adivina)', () => assert.deepEqual(buscarRegistro(R, sec, campos, 'Ana').candidatos.map((r) => r.id), ['a', 'b']))
caso('apellido único', () => assert.equal(buscarRegistro(R, sec, campos, 'Pérez').registro.id, 'c'))
caso('por id', () => assert.equal(buscarRegistro(R, sec, campos, 'b').registro.id, 'b'))
caso('no existe', () => assert.ok(buscarRegistro(R, sec, campos, 'Rosa Gómez').ninguno))
const P = [['hoy', '2026-10-16', '2026-10-16'], ['esta semana', '2026-10-12', '2026-10-18'], ['la semana pasada', '2026-10-05', '2026-10-11'], ['la próxima semana', '2026-10-19', '2026-10-25'],
  ['este mes', '2026-10-01', '2026-10-31'], ['el mes pasado', '2026-09-01', '2026-09-30'], ['el próximo mes', '2026-11-01', '2026-11-30'], ['este año', '2026-01-01', '2026-12-31'],
  ['los últimos 30 días', '2026-09-16', '2026-10-16'], ['los próximos 7 días', '2026-10-16', '2026-10-23'], ['vencidos', null, '2026-10-15'], ['octubre', '2026-10-01', '2026-10-31'],
  ['en febrero', '2026-02-01', '2026-02-28'], ['diciembre de 2025', '2025-12-01', '2025-12-31'], ['del 1 al 15 de octubre', '2026-10-01', '2026-10-15'], ['del 3 de octubre al 2 de noviembre', '2026-10-03', '2026-11-02'], ['el 30 de octubre', '2026-10-30', '2026-10-30']]
for (const [t, a, b] of P) caso(`periodo «${t}»`, () => assert.deepEqual(parsePeriodo(t, HOY), { desde: a, hasta: b }))
caso('periodo que no se entiende', () => { assert.equal(parsePeriodo('cuando llueva', HOY), null); assert.equal(parsePeriodo('del 15 al 1 de octubre', HOY), null) })
caso('fecha larga', () => { assert.equal(fechaLarga('2026-10-30'), '30 de octubre de 2026'); assert.equal(fechaLarga('2026-01-05'), '5 de enero de 2026') })
console.log(`${ok} pruebas bien`)
