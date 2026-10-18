/* Adaptador del CRM de la API a las piezas del laboratorio (D61). Código puro, sin pantalla.
 * Corre con: node src/crm/plantillas/__pruebas__/desdeCrm.test.mjs (desde la raíz del proyecto). */
import { createServer } from 'vite'
import assert from 'node:assert/strict'
const v = await createServer({ configFile: 'vite.config.js', server: { middlewareMode: true, hmr: false }, optimizeDeps: { noDiscovery: true, entries: [] }, logLevel: 'error' })
const { desdeCrm, tieneInicio, contactoDesdeValores, tareaDesdeValores } = await v.ssrLoadModule('/src/crm/plantillas/desdeCrm.js')
let ok = 0
const caso = (n, fn) => { try { fn(); ok++; console.log('✓', n) } catch (e) { console.log('✗', n, '\n ', e.message); process.exitCode = 1 } }

const crm = {
  brief: { nombre: 'Gimnasio Roca' },
  esquema: 2, plantilla: { id: 'membresias', origen: 'asignar', porque: [] },
  etapas: ['Nuevo', 'Cliente'], ocultas: ['rrhh'],
  camposContacto: [{ id: 'f_cumple', nombre: 'Cumpleaños', tipo: 'fecha' }, { id: 'f_talla', nombre: 'Talla', tipo: 'lista', opciones: ['S', 'M', 'L'] }],
  contactos: [{ id: 'c1', n: 'Ana López', det: '5555-1234', canal: 'WhatsApp', etapa: 'Nuevo', dueno: 'Tú', dias: 0, extra: { f_talla: 'M' } }],
  tareas: { porHacer: [{ id: 't1', t: 'Llamar a Ana', vence: '2026-10-20', hora: '16:30' }], enCurso: [], hecho: [{ id: 't2', t: 'Pagar luz' }] },
  listas: [
    { id: 'l_miembros', nombre: 'Miembros', vista: 'tablero', opciones: { por: 'estado', titulo: 'nombre' }, icono: 'usuarios', grupo: 0,
      opcionesEstado: { estado: ['Activa', 'Pausada', 'Cancelada'] }, tarjeta: { campos: ['nombre', 'plan'] },
      campos: [{ id: 'nombre', nombre: 'Nombre', tipo: 'texto' }, { id: 'plan', nombre: 'Plan', tipo: 'texto' }, { id: 'cuota', nombre: 'Cuota', tipo: 'dinero' },
        { id: 'vence', nombre: 'Vence', tipo: 'fecha' }, { id: 'hora', nombre: 'Hora', tipo: 'hora' }, { id: 'estado', nombre: 'Estado', tipo: 'lista', opciones: ['Activa', 'Pausada'] }],
      registros: [{ id: 'r1', valores: { nombre: 'Luis', plan: 'Mensual', cuota: 250, vence: '2026-11-01', estado: 'Activa' }, ejemplo: true }, { id: 'r2', valores: { nombre: 'Rosa' } }] },
    { id: 'l_rota', nombre: 'Rota', vista: 'agenda', opciones: { fecha: 'noexiste' }, campos: [{ id: 'x', nombre: 'X', tipo: 'raro' }], registros: [] },
  ],
  inicio: [
    { uid: 'b0', vista: 'kpis', seccion: 'l_miembros', opciones: { por: 'estado' }, ancho: 12, alto: 1 },
    { vista: 'kpis', seccion: 'contactos', opciones: { por: 'etapa' } },
    { uid: 'b2', vista: 'tablero', seccion: 'desarrollo', opciones: { por: 'estado', titulo: 'tarea' }, ancho: 7, alto: 9 },
    { uid: 'b3', vista: 'vencimientos', seccion: 'l_miembros', opciones: { fecha: 'plan' } }, // plan no es fecha: fuera
    { uid: 'b4', vista: 'tabla', seccion: 'l_borrada' }, // sección que no existe: fuera
  ],
  paginas: { l_miembros: [{ uid: 'p1', vista: 'tabla', seccion: 'l_miembros', ancho: 12, alto: 3 }, { uid: 'p2', vista: 'grafico', seccion: 'l_miembros', opciones: { tipo: 'dona' }, ancho: 6, alto: 2 }] },
  marca: { primario: '#3fb8ff', logo_id: 'abc' },
  eventos: [{ id: 'e1', e: '🤖', t: 'Shifu creó tu CRM', h: 'ahora' }], vendedores: ['Tú'], automatizaciones: [],
}
const r = desdeCrm(crm, { titulos: { contactos: 'Socios', desarrollo: 'Pendientes' } })

caso('secciones: contactos y tareas virtuales primero (ids contactos/desarrollo, §2), luego cada lista', () => {
  assert.deepEqual(r.plantilla.secciones.map((s) => s.id), ['contactos', 'desarrollo', 'l_miembros', 'l_rota'])
  assert.equal(r.porId.contactos.titulo, 'Socios'); assert.equal(r.porId.desarrollo.titulo, 'Pendientes')
  assert.equal(r.plantilla.id, 'membresias'); assert.equal(r.plantilla.nombre, 'Gimnasio Roca')
})
caso('contactos: campos fijos + los propios; «lista» pasa a «estado»; etapa con las etapas del CRM', () => {
  const cs = r.porId.contactos.campos
  assert.deepEqual(cs.map((c) => c.id), ['nombre', 'detalle', 'canal', 'etapa', 'responsable', 'f_cumple', 'f_talla'])
  assert.deepEqual(cs.find((c) => c.id === 'etapa').opciones, ['Nuevo', 'Cliente'])
  assert.deepEqual(cs.find((c) => c.id === 'f_talla'), { id: 'f_talla', nombre: 'Talla', tipo: 'estado', opciones: ['S', 'M', 'L'] })
  assert.deepEqual(r.datos.registros.contactos, [{ id: 'c1', valores: { nombre: 'Ana López', detalle: '5555-1234', canal: 'WhatsApp', etapa: 'Nuevo', responsable: 'Tú', f_talla: 'M' } }])
})
caso('tareas: una sola sección con estado por columna (Por hacer / En curso / Hecho)', () => {
  assert.deepEqual(r.datos.registros.desarrollo, [
    { id: 't1', valores: { tarea: 'Llamar a Ana', vence: '2026-10-20', hora: '16:30', estado: 'Por hacer' } },
    { id: 't2', valores: { tarea: 'Pagar luz', estado: 'Hecho' } }])
  assert.equal(r.porId.desarrollo.vista, 'tablero')
})
caso('listas v2: vista, opciones, icono, tarjeta, opcionesEstado y tipos nuevos; los ejemplos se marcan', () => {
  const s = r.porId.l_miembros
  assert.equal(s.vista, 'tablero'); assert.deepEqual(s.opciones, { por: 'estado', titulo: 'nombre' }); assert.equal(s.icono, 'usuarios')
  assert.deepEqual(s.tarjeta, { campos: ['nombre', 'plan'] })
  assert.deepEqual(s.campos.map((c) => c.tipo), ['texto', 'texto', 'dinero', 'fecha', 'hora', 'estado'])
  assert.deepEqual(s.campos.at(-1).opciones, ['Activa', 'Pausada', 'Cancelada']) // opcionesEstado manda sobre las del campo
  assert.equal(r.datos.registros.l_miembros[0].ejemplo, true); assert.equal('ejemplo' in r.datos.registros.l_miembros[1], false)
})
caso('una lista con vista que no pasa el cerco cae a su tabla y lo anota; un tipo desconocido se ve como texto', () => {
  assert.equal(r.porId.l_rota.vista, 'tabla'); assert.deepEqual(r.porId.l_rota.opciones, {})
  assert.equal(r.porId.l_rota.campos[0].tipo, 'texto')
  assert.ok(r.avisos.some((a) => a.includes('Rota')))
})
caso('inicio: uid y tamaño; los bloques que no pasan el cerco o de secciones que no existen quedan fuera', () => {
  assert.deepEqual(r.bloques.map((b) => b.uid), ['b0', 'b1', 'b2'])
  assert.equal(r.bloques[1].ancho, 12); assert.equal(r.bloques[1].alto, 1) // kpis a lo ancho y de una fila
  assert.equal(r.bloques[2].ancho, 12); assert.equal(r.bloques[2].alto, 4) // ancho fuera de la rejilla → el de partida; alto tope 4
  assert.ok(r.avisos.some((a) => a.includes('l_borrada'))); assert.ok(r.avisos.some((a) => a.includes('vencimientos')))
  assert.deepEqual(r.plantilla.inicio, r.bloques)
})
caso('paginas: el lienzo propio de una pestaña queda en la sección (como plantillaEfectiva)', () => {
  assert.deepEqual(r.paginas.l_miembros.map((b) => b.uid), ['p1', 'p2'])
  assert.equal(r.porId.l_miembros.pagina, r.paginas.l_miembros)
  assert.equal(r.porId.contactos.pagina, undefined)
})
caso('marca: se pasa tal cual, sin logo_id (no hay ruta para el logo)', () => { assert.deepEqual(r.marca, { primario: '#3fb8ff' }) })
caso('datos: eventos, equipo y automatizaciones para las vistas fijas', () => {
  assert.equal(r.datos.eventos.length, 1); assert.deepEqual(r.datos.equipo, ['Tú'])
})
caso('secciones ocultas no aparecen y sus bloques se descartan', () => {
  const x = desdeCrm({ ...crm, ocultas: ['contactos'] })
  assert.ok(!x.porId.contactos); assert.deepEqual(x.bloques.map((b) => b.uid), ['b0', 'b2'])
})
caso('CRM de antes (sin campos v2): sin inicio, cada lista como tabla', () => {
  const x = desdeCrm({ contactos: [], tareas: { porHacer: [], enCurso: [], hecho: [] }, listas: [{ id: 'l_a', nombre: 'A', campos: [{ id: 'f1', nombre: 'Uno', tipo: 'numero' }], registros: [] }] })
  assert.equal(tieneInicio({}), false); assert.equal(tieneInicio(crm), true)
  assert.deepEqual(x.bloques, []); assert.equal(x.porId.l_a.vista, 'tabla'); assert.deepEqual(x.avisos, [])
})
caso('de vuelta: valores de la ficha de un contacto → cambios de la API (extra completo)', () => {
  assert.deepEqual(contactoDesdeValores({ nombre: 'Ana', etapa: 'Cliente', responsable: 'Kevin', f_cumple: '2000-01-01' }, { f_talla: 'M' }),
    { n: 'Ana', etapa: 'Cliente', dueno: 'Kevin', extra: { f_talla: 'M', f_cumple: '2000-01-01' } })
  assert.deepEqual(contactoDesdeValores({ detalle: 'x@y.com' }), { det: 'x@y.com' })
})
caso('de vuelta: valores de la ficha de una tarea → cambios y columna', () => {
  assert.deepEqual(tareaDesdeValores({ tarea: 'Otra', vence: '' }), { cambios: { t: 'Otra', vence: '' }, columna: null })
  assert.deepEqual(tareaDesdeValores({ estado: 'En curso' }), { cambios: {}, columna: 'enCurso' })
})

console.log(`\n${ok} pruebas bien`)
await v.close()
