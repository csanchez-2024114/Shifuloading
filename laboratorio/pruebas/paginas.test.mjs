/* Pestaña como cuaderno en blanco (D49): las herramientas de bloques en cualquier pestaña. Sin IA (código puro).
 * Corre con: node laboratorio/pruebas/paginas.test.mjs (desde la raíz de Shifuloading). */
import { createServer } from 'vite'
import assert from 'node:assert/strict'
const v = await createServer({ configFile: 'laboratorio/vite.config.js', server: { middlewareMode: true, hmr: false }, logLevel: 'error' })
const { ejecutar, plantillaEfectiva, ubicarTodo } = await v.ssrLoadModule('/src/plantillas/edicion.js')
const { plantillaPorId } = await v.ssrLoadModule('/src/plantillas/semillas.js')
const p = plantillaPorId('membresias')
const E = { bloques: [{ uid: 'b0', vista: 'kpis', seccion: 'miembros', opciones: { por: 'estado' }, ancho: 12, alto: 1 }] }
let ok = 0
const caso = (n, fn) => { try { fn(); ok++; console.log('✓', n) } catch (e) { console.log('✗', n, '\n ', e.message); process.exitCode = 1 } }
const pag = (e, id) => e.estructura?.paginas?.[id]

let e1
caso('agregar en una pestaña crea su lienzo con su vista de siempre + la pieza nueva; el inicio no cambia', () => {
  const r = ejecutar(p, E, 'agregar_bloque', { pestana: 'miembros', vista: 'grafico', opciones: { tipo: 'dona' } })
  assert.ok(r.ok, r.resultado); e1 = r.estado
  assert.deepEqual(e1.bloques.map((b) => b.uid), ['b0'])
  assert.equal(pag(e1, 'miembros').length, 2)
  assert.equal(pag(e1, 'miembros')[0].vista, 'tabla') // la vista de siempre de Miembros
  assert.equal(pag(e1, 'miembros')[1].seccion, 'miembros') // sin «seccion», usa la de la pestaña
  assert.match(r.resultado, /En la pestaña «Miembros»/)
})
caso('la plantilla efectiva expone el lienzo de la pestaña', () => { assert.equal(plantillaEfectiva(p, e1).secciones.find((s) => s.id === 'miembros').pagina.length, 2) })
caso('quitar por id encuentra el bloque en la pestaña (sin decir cuál)', () => {
  const uid = pag(e1, 'miembros')[1].uid
  const r = ejecutar(p, e1, 'quitar_bloque', { bloque: uid }); assert.ok(r.ok, r.resultado)
  assert.equal(pag(r.estado, 'miembros').length, 1); assert.deepEqual(r.estado.bloques.map((b) => b.uid), ['b0'])
})
caso('la pieza por defecto (p_<id>) de una pestaña sin lienzo también se puede cambiar', () => {
  const r = ejecutar(p, E, 'cambiar_visual', { bloque: 'p_miembros', vista: 'tablero', opciones: { por: 'estado' } }); assert.ok(r.ok, r.resultado)
  assert.equal(pag(r.estado, 'miembros')[0].vista, 'tablero')
})
caso('acomodo automático también en la pestaña (sin huecos)', () => {
  const r = ejecutar(p, e1, 'cambiar_tamano', { bloque: pag(e1, 'miembros')[0].uid, ancho: 6 }); assert.ok(r.ok, r.resultado)
  const anchos = pag(r.estado, 'miembros').map((b) => b.ancho); assert.ok(anchos.reduce((a, b) => a + b, 0) % 12 === 0, `anchos ${anchos}`)
})
caso('ubicarTodo ve los bloques de todos los lienzos', () => { const u = ubicarTodo(e1); assert.ok(u.b0 && u[pag(e1, 'miembros')[1].uid]) })
caso('pestaña inexistente o fija: error claro, nada cambia', () => {
  const r1 = ejecutar(p, E, 'agregar_bloque', { pestana: 'nada', vista: 'tabla', seccion: 'miembros' }); assert.equal(r1.ok, false); assert.match(r1.resultado, /no existe/)
  const r2 = ejecutar(p, E, 'agregar_bloque', { pestana: 'actividad', vista: 'tabla', seccion: 'miembros' }); assert.equal(r2.ok, false); assert.match(r2.resultado, /no admite piezas/)
})
caso('una pestaña puede mostrar datos de OTRA sección', () => {
  const r = ejecutar(p, E, 'agregar_bloque', { pestana: 'miembros', vista: 'tabla', seccion: 'pagos' }); assert.ok(r.ok, r.resultado)
  assert.equal(pag(r.estado, 'miembros')[1].seccion, 'pagos')
})
caso('quitar una sección se lleva su lienzo y sus piezas en otras pestañas', () => {
  const a = ejecutar(p, E, 'agregar_bloque', { pestana: 'miembros', vista: 'tabla', seccion: 'pagos' }).estado
  const b = ejecutar(p, a, 'agregar_bloque', { pestana: 'pagos', vista: 'grafico', opciones: { tipo: 'columnas' } }).estado
  const r = ejecutar(p, b, 'quitar_seccion', { seccion: 'pagos' }); assert.ok(r.ok, r.resultado)
  assert.equal(pag(r.estado, 'pagos'), undefined); assert.ok(pag(r.estado, 'miembros').every((x) => x.seccion !== 'pagos'))
})
caso('mirando una pestaña: agregar va ahí por defecto (sin recursión)', () => {
  const r = ejecutar(p, { ...E, vista: 'miembros' }, 'agregar_bloque', { vista: 'kpis', opciones: { por: 'estado' } }); assert.ok(r.ok, r.resultado)
  assert.equal(pag(r.estado, 'miembros').length, 2); assert.deepEqual(r.estado.bloques.map((b) => b.uid), ['b0']); assert.equal(r.estado.vista, 'miembros')
})
caso('mirando una pestaña: tocar un bloque del inicio sin decirlo se rechaza; con pestana="inicio" sí', () => {
  const r1 = ejecutar(p, { ...E, vista: 'miembros' }, 'cambiar_visual', { bloque: 'b0', vista: 'tabla' }); assert.equal(r1.ok, false); assert.match(r1.resultado, /INICIO/)
  const r2 = ejecutar(p, { ...E, vista: 'miembros' }, 'agregar_bloque', { pestana: 'inicio', vista: 'tabla', seccion: 'pagos' }); assert.ok(r2.ok, r2.resultado); assert.equal(r2.estado.bloques.length, 2)
})
caso('pieza igual a otra del mismo lienzo (D55): no se agrega sin «sí»; con otro tipo u otra pestaña, sí', () => {
  const r1 = ejecutar(p, E, 'agregar_bloque', { vista: 'kpis', seccion: 'miembros', opciones: { por: 'estado' } }); assert.equal(r1.ok, false); assert.match(r1.resultado, /pieza igual.*b0/)
  const a = ejecutar(p, E, 'agregar_bloque', { vista: 'grafico', seccion: 'miembros', opciones: { tipo: 'dona' } }); assert.ok(a.ok, a.resultado)
  assert.equal(ejecutar(p, a.estado, 'agregar_bloque', { vista: 'grafico', seccion: 'miembros', opciones: { tipo: 'dona' } }).ok, false)
  assert.ok(ejecutar(p, a.estado, 'agregar_bloque', { vista: 'grafico', seccion: 'miembros', opciones: { tipo: 'columnas' } }).ok, 'otro tipo de gráfica')
  assert.ok(ejecutar(p, a.estado, 'agregar_bloque', { vista: 'grafico', seccion: 'miembros', opciones: { tipo: 'dona' } }, { confirmado: true }).ok, 'con «sí»')
  assert.ok(ejecutar(p, E, 'agregar_bloque', { pestana: 'miembros', vista: 'kpis', opciones: { por: 'estado' } }).ok, 'en otra pestaña no es duplicado')
})
console.log(`\n${ok} pruebas bien`); await v.close()
