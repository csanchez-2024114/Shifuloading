/* Datos por chat (D50): agregar, editar, borrar y consultar registros, con el código entendiendo y validando. Sin IA.
 * Corre con: node laboratorio/pruebas/registros.test.mjs (desde la raíz de Shifuloading). */
import { createServer } from 'vite'
import assert from 'node:assert/strict'
const v = await createServer({ configFile: 'laboratorio/vite.config.js', server: { middlewareMode: true, hmr: false }, logLevel: 'error' })
const { ejecutar, consultarDatos, datosActuales, describirPantalla, etiquetaCambio, creadoSinDecir } = await v.ssrLoadModule('/src/plantillas/edicion.js')
const { plantillaPorId } = await v.ssrLoadModule('/src/plantillas/semillas.js')
const { datosEjemplo } = await v.ssrLoadModule('/src/plantillas/datosEjemplo.js')
const p = plantillaPorId('membresias')
const M = { nivel: 'pocos', ejemplos: true, pais: 'gt' }
const E = { bloques: [] }
const ctx = { muestra: M }
let ok = 0
const caso = (n, fn) => { try { fn(); ok++; console.log('✓', n) } catch (e) { console.log('✗', n, '\n ', e.message); process.exitCode = 1 } }
const miembros = (e, m = M) => datosActuales(p, e, m).registros.miembros
const de = (e, nombre) => miembros(e).find((r) => r.valores.nombre === nombre)
const hoy = new Date(); const anio = hoy.getFullYear()

caso('los ejemplos tienen nombres únicos (antes «Ana López» salía ~11 veces con 220 registros)', () => {
  const rs = datosEjemplo(p, 'muchos').registros.miembros.map((r) => r.valores.nombre)
  assert.equal(new Set(rs).size, rs.length)
  // quien paga es alguien que existe en Miembros
  const nombres = new Set(rs); assert.ok(datosEjemplo(p, 'muchos').registros.pagos.every((r) => nombres.has(r.valores.miembro)))
})
let e1
caso('agregar: entiende la fecha en palabras, normaliza «mensual» y pone el estado por defecto (y lo dice)', () => {
  const r = ejecutar(p, E, 'agregar_registro', { seccion: 'Miembros', valores: { nombre: 'María López', plan: 'mensual', vence: '30 de octubre' } }, ctx)
  assert.ok(r.ok, r.resultado); e1 = r.estado
  const m = de(e1, 'María López')
  assert.deepEqual(m.valores, { nombre: 'María López', plan: 'Mensual', vence: `${anio}-10-30`, estado: 'Activa' })
  assert.match(r.resultado, /Estado: Activa por defecto/); assert.match(r.resultado, /Sin llenar: Alta/)
  assert.equal(miembros(e1).length, 9)
  assert.equal(etiquetaCambio({ herramienta: 'agregar_registro', args: {}, etiqueta: r.etiqueta }), 'agregó «María López» a Miembros')
})
caso('agregar sin el nombre: no inventa, pide el dato', () => {
  const r = ejecutar(p, E, 'agregar_registro', { seccion: 'miembros', valores: { plan: 'Anual' } }, ctx)
  assert.ok(!r.ok); assert.match(r.resultado, /falta Nombre/)
})
caso('agregar con una opción que no existe o una fecha imposible: error que dice qué preguntar', () => {
  const a = ejecutar(p, E, 'agregar_registro', { seccion: 'miembros', valores: { nombre: 'Rosa', estado: 'Congelada' } }, ctx)
  assert.ok(!a.ok); assert.match(a.resultado, /Congelada.*opciones: Activa, Pausada, Cancelada/)
  const b = ejecutar(p, E, 'agregar_registro', { seccion: 'miembros', valores: { nombre: 'Rosa', vence: '31 de febrero' } }, ctx)
  assert.ok(!b.ok); assert.match(b.resultado, /no entendí la fecha/)
  const c = ejecutar(p, E, 'agregar_registro', { seccion: 'miembros', valores: { nombre: 'Rosa', correo: 'rosa@x.com' } }, ctx)
  assert.ok(!c.ok); assert.match(c.resultado, /«correo» no es un campo de Miembros/)
})
caso('agregar un pago: el monto «Q1,200.50» se entiende y se suma bien', () => {
  const r = ejecutar(p, E, 'agregar_registro', { seccion: 'pagos', valores: { miembro: 'Ana López', monto: 'Q1,200.50', fecha: 'hoy' } }, ctx)
  assert.ok(r.ok, r.resultado)
  const pago = datosActuales(p, r.estado, M).registros.pagos.at(-1)
  assert.equal(pago.valores.monto, 1200.5); assert.match(r.resultado, /Q\s?1,200\.50/)
})
caso('editar un ejemplo: guarda solo lo que cambió y dice antes → después', () => {
  const r = ejecutar(p, E, 'editar_registro', { seccion: 'miembros', registro: 'ana lopez', valores: { estado: 'pausada' } }, ctx)
  assert.ok(r.ok, r.resultado)
  assert.equal(de(r.estado, 'Ana López').valores.estado, 'Pausada')
  assert.deepEqual(Object.keys(r.estado.datos.cambios.miembros), ['miembros-0'])
  assert.match(r.resultado, /Estado: \w+ → Pausada/); assert.match(r.etiqueta, /cambió «Ana López»: Estado → Pausada/)
})
caso('editar lo que agregó la persona: se cambia en su lugar (no queda en «cambios»)', () => {
  const r = ejecutar(p, e1, 'editar_registro', { seccion: 'miembros', registro: 'María López', valores: { vence: '15/11/2026' } }, ctx)
  assert.ok(r.ok, r.resultado)
  assert.equal(r.estado.datos.nuevos.miembros[0].valores.vence, '2026-11-15'); assert.equal(r.estado.datos.cambios, undefined)
})
caso('editar sin cambio real: no cuenta como cambio (sin etiqueta)', () => {
  const r = ejecutar(p, e1, 'editar_registro', { seccion: 'miembros', registro: 'María López', valores: { plan: 'Mensual' } }, ctx)
  assert.ok(r.ok); assert.equal(r.etiqueta, null); assert.equal(r.estado, e1)
})
caso('dos que coinciden: no adivina, lista los candidatos para preguntar', () => {
  const dos = ejecutar(p, e1, 'agregar_registro', { seccion: 'miembros', valores: { nombre: 'Ana Martínez' } }, ctx).estado
  const r = ejecutar(p, dos, 'editar_registro', { seccion: 'miembros', registro: 'Ana', valores: { estado: 'Cancelada' } }, ctx)
  assert.ok(!r.ok); assert.match(r.resultado, /hay 2 registros.*Ana López.*Ana Martínez.*pregúntale cuál/)
})
caso('no existe: lo dice y sugiere parecidos', () => {
  const r = ejecutar(p, E, 'borrar_registro', { seccion: 'miembros', registro: 'Carlos Pereira' }, ctx)
  assert.ok(!r.ok); assert.match(r.resultado, /no encontré «Carlos Pereira».*Se parecen: Carlos Pérez/)
})
caso('borrar un ejemplo y uno propio', () => {
  const a = ejecutar(p, e1, 'borrar_registro', { seccion: 'miembros', registro: 'Carlos Pérez' }, ctx)
  assert.ok(a.ok, a.resultado); assert.equal(de(a.estado, 'Carlos Pérez'), undefined); assert.deepEqual(a.estado.datos.borrados.miembros, ['miembros-1'])
  const b = ejecutar(p, a.estado, 'borrar_registro', { seccion: 'miembros', registro: 'María López' }, ctx)
  assert.ok(b.ok); assert.equal(b.estado.datos.nuevos.miembros.length, 0); assert.equal(miembros(b.estado).length, 7)
})
caso('la pestaña Vencimientos (muestra los de Miembros) guarda en Miembros', () => {
  const r = ejecutar(p, E, 'agregar_registro', { seccion: 'vencimientos', valores: { nombre: 'Pedro Ruiz' } }, ctx)
  assert.ok(r.ok, r.resultado); assert.equal(r.estado.datos.nuevos.miembros[0].valores.nombre, 'Pedro Ruiz'); assert.match(r.resultado, /a Miembros/)
})
caso('una opción de estado renombrada después también cambia lo que agregó la persona', () => {
  const r = ejecutar(p, e1, 'cambiar_opciones_estado', { seccion: 'miembros', campo: 'estado', opciones: ['Vigente', 'Pausada', 'Cancelada'], renombrar: { Activa: 'Vigente' } }, ctx)
  assert.ok(r.ok, r.resultado); assert.equal(de(r.estado, 'María López').valores.estado, 'Vigente')
  assert.equal(r.estado.datos.nuevos.miembros[0].valores.estado, 'Activa') // lo guardado no se toca: deshacer el cambio lo devuelve
})
caso('consultar: cuenta, filtra por estado y por periodo, suma montos (lo calcula el código)', () => {
  const todos = miembros(E), activos = todos.filter((r) => r.valores.estado === 'Activa').length
  assert.match(consultarDatos(p, E, { seccion: 'miembros', filtros: { estado: 'activa' } }, M), new RegExp(`\\): ${activos} de ${todos.length} registros`))
  const pagos = datosActuales(p, E, M).registros.pagos
  const ini = `${anio}-${String(hoy.getMonth() + 1).padStart(2, '0')}-01`
  const delMes = pagos.filter((r) => r.valores.fecha >= ini && r.valores.fecha <= new Date(anio, hoy.getMonth() + 1, 0).toISOString().slice(0, 10))
  const t = consultarDatos(p, E, { seccion: 'pagos', periodo: { cuando: 'este mes' }, sumar: 'monto' }, M)
  assert.match(t, new RegExp(`: ${delMes.length} de ${pagos.length}`)); assert.match(t, /Suma de Monto: Q/)
  assert.match(consultarDatos(p, E, { seccion: 'miembros', periodo: { cuando: 'este mes' } }, M), /¿por cuál fecha\?/) // tiene Alta y Vence
  assert.match(consultarDatos(p, E, { seccion: 'miembros', buscar: 'Ana López' }, M), /: 1 de 8 registros.*Ana López — Plan/)
  assert.match(consultarDatos(p, E, { seccion: 'miembros', buscar: 'Rosa Gómez' }, M), /no hay ningún registro que coincida/)
  assert.match(consultarDatos(p, E, { seccion: 'pagos', sumar: 'miembro' }, M), /no se puede sumar/)
})
caso('el estado para el modelo NO lleva conteos (medido: distraían; los números salen de consultar_datos)', () => {
  const d = describirPantalla(p, e1)
  assert.equal(d.secciones.find((s) => s.id === 'miembros').registros, undefined)
  assert.ok(!JSON.stringify(d).includes('María López')) // ni registros de la persona
})
caso('sin ejemplos (ya borrados): solo lo de la persona', () => {
  assert.equal(miembros(e1, { nivel: 'muchos', ejemplos: false }).length, 1)
})
caso('estructura creada para guardar un dato: si la respuesta no lo dice, se agrega (y no se repite si ya lo dijo)', () => {
  const opc = { herramienta: 'cambiar_opciones_estado', args: { seccion: 'miembros', campo: 'estado', opciones: ['Activa', 'Pausada', 'Cancelada', 'Congelada'] } }
  const ed = { herramienta: 'editar_registro', args: {} }
  assert.deepEqual(creadoSinDecir(p, E, [opc, ed], 'El estado de Ana López cambió a Congelada.'), ['la opción «Congelada»'])
  assert.deepEqual(creadoSinDecir(p, E, [opc, ed], 'Agregué la opción Congelada y cambié a Ana López.'), [])
  assert.deepEqual(creadoSinDecir(p, E, [opc], 'Listo.'), []) // sin dato: es un cambio de diseño pedido, no un rodeo
  const ren = { herramienta: 'cambiar_opciones_estado', args: { seccion: 'miembros', campo: 'estado', opciones: ['Vigente', 'Pausada', 'Cancelada'], renombrar: { Activa: 'Vigente' } } }
  assert.deepEqual(creadoSinDecir(p, E, [ren, ed], 'Listo.'), []) // renombrar no es crear
  const campo = { herramienta: 'agregar_campo', args: { seccion: 'miembros', nombre: 'Correo', tipo: 'texto' } }
  assert.deepEqual(creadoSinDecir(p, E, [campo, ed], 'Le puse ana@x.com a Ana.'), ['el campo «Correo»'])
})
console.log(`\n${ok} pruebas bien`)
await v.close()
