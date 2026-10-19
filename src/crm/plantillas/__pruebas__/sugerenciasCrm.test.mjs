/* Sugerencias del CRM en modo diseño (carga aparte). Corre con: node src/crm/plantillas/__pruebas__/sugerenciasCrm.test.mjs */
import { createServer } from 'vite'
import assert from 'node:assert/strict'

const v = await createServer({ configFile: 'vite.config.js', server: { middlewareMode: true, hmr: false }, optimizeDeps: { noDiscovery: true, entries: [] }, logLevel: 'error' })
const { ideasDe } = await v.ssrLoadModule('/src/crm/plantillas/sugerenciasCrm.js')
let ok = 0
const caso = (n, fn) => { try { fn(); ok++; console.log('✓', n) } catch (e) { console.log('✗', n, '\n ', e.message); process.exitCode = 1 } }

const crm = {
  brief: { nombre: 'Gimnasio Roca' },
  esquema: 2, plantilla: { id: 'membresias', origen: 'asignar', porque: [] },
  etapas: ['Nuevo', 'Cliente'], ocultas: ['rrhh'],
  camposContacto: [{ id: 'f_cumple', nombre: 'Cumpleaños', tipo: 'fecha' }],
  contactos: [{ id: 'c1', n: 'Ana López', det: '5555', canal: 'WhatsApp', etapa: 'Nuevo', dueno: 'Tú', dias: 0 }],
  tareas: { porHacer: [{ id: 't1', t: 'Llamar a Ana' }], enCurso: [], hecho: [] },
  listas: [{ id: 'l_miembros', nombre: 'Miembros', vista: 'tablero', opciones: { por: 'estado', titulo: 'nombre' }, icono: 'usuarios', grupo: 0,
    campos: [{ id: 'nombre', nombre: 'Nombre', tipo: 'texto' }, { id: 'estado', nombre: 'Estado', tipo: 'lista', opciones: ['Activa'] }],
    registros: [{ id: 'r1', valores: { nombre: 'Luis', estado: 'Activa' } }] }],
  inicio: [{ uid: 'b0', vista: 'kpis', seccion: 'l_miembros', opciones: { por: 'estado' }, ancho: 12, alto: 1 }],
  marca: { primario: '#3fb8ff' },
  eventos: [], vendedores: ['Tú'], automatizaciones: [],
}

caso('ideasDe devuelve pares de strings no vacíos', () => {
  const ideas = ideasDe(crm, 'inicio', 0, { contactos: 'Socios', desarrollo: 'Pendientes' })
  assert.ok(Array.isArray(ideas) && ideas.length > 0)
  for (const par of ideas) {
    assert.equal(par.length, 2)
    assert.equal(typeof par[0], 'string')
    assert.equal(typeof par[1], 'string')
    assert.ok(par[0].length && par[1].length)
  }
})

caso('las ideas cambian con la vista', () => {
  const a = ideasDe(crm, 'inicio', 0, { contactos: 'Socios', desarrollo: 'Pendientes' })
  const b = ideasDe(crm, 'l_miembros', 0, { contactos: 'Socios', desarrollo: 'Pendientes' })
  assert.notDeepEqual(a.map((x) => x[1]), b.map((x) => x[1]))
})

const T = { contactos: 'Socios', desarrollo: 'Pendientes' }
const conGrafica = { ...crm, inicio: [...crm.inicio, { uid: 'g1', vista: 'grafico', seccion: 'l_miembros', opciones: { tipo: 'dona', por: 'estado' }, ancho: 6, alto: 2 }] }
const textos = (ideas) => ideas.map((x) => x[1])

caso('como mucho 3 ideas', () => {
  for (const v of ['inicio', 'l_miembros', 'contactos']) assert.ok(ideasDe(conGrafica, v, 0, T).length <= 3)
})

caso('lo de una gráfica del inicio solo se ofrece en el inicio (no desde otra pestaña)', () => {
  const todas = (v) => [0, 1, 2, 3, 4, 5].flatMap((t) => textos(ideasDe(conGrafica, v, t, T, 20)))
  assert.ok(todas('inicio').some((t) => /gráfica de miembros/i.test(t)), 'en el inicio sí')
  assert.ok(!todas('l_miembros').some((t) => /gráfica de miembros (más chica|por)/i.test(t) || /^Cambia la gráfica/.test(t)), 'en Miembros no')
})

caso('sin gráfica en pantalla no hay ideas sobre una gráfica', () => {
  const todas = [0, 1, 2, 3, 4, 5].flatMap((t) => textos(ideasDe(crm, 'inicio', t, T, 20)))
  assert.ok(!todas.some((t) => /^(Cambia|Haz) la gráfica/.test(t)))
})

caso('sin ningún dato no se pregunta qué gráficas poner «con mis datos»', () => {
  const vacio = { ...crm, contactos: [], tareas: { porHacer: [], enCurso: [], hecho: [] }, listas: crm.listas.map((l) => ({ ...l, registros: [] })) }
  const todas = [0, 1, 2, 3].flatMap((t) => textos(ideasDe(vacio, 'inicio', t, T, 20)))
  assert.ok(!todas.includes('¿Qué gráficas puedo poner con mis datos?'))
  assert.ok([0, 1, 2, 3].flatMap((t) => textos(ideasDe(crm, 'inicio', t, T, 20))).includes('¿Qué gráficas puedo poner con mis datos?'))
})

caso('con logo puesto no se ofrece «Agrega mi logo»', () => {
  const conLogo = { ...crm, marca: { primario: '#3fb8ff', logo_id: 'logo_x' } }
  const todas = [0, 1, 2, 3].flatMap((t) => textos(ideasDe(conLogo, 'inicio', t, T, 20)))
  assert.ok(!todas.some((t) => /logo/i.test(t)))
  assert.ok([0, 1, 2, 3].flatMap((t) => textos(ideasDe(crm, 'inicio', t, T, 20))).some((t) => /Agrega mi logo/.test(t)))
})

console.log(`\n${ok} pruebas bien`)
await v.close()
