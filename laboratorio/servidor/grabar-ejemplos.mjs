/* Graba los fixtures dorados de los datos de ejemplo (datosEjemplo.js) para comparar el port a Python (nucleo/src/assistant/packs/crm/ejemplos.py).
 * El «hoy» se fija en 2026-10-16 (hora de Guatemala) reemplazando Date: así las fechas relativas salen siempre iguales.
 * Uso (desde la raíz del repo): TZ=America/Guatemala node laboratorio/servidor/grabar-ejemplos.mjs */
import { createServer } from 'vite'
import { writeFileSync } from 'node:fs'
import { createHash } from 'node:crypto'

process.env.TZ = 'America/Guatemala'
const FIJO = new Date(2026, 9, 16, 12, 0, 0).getTime()
const DateReal = Date
globalThis.Date = class extends DateReal {
  constructor(...a) { if (a.length) super(...a); else super(FIJO) }
  static now() { return FIJO }
}

const v = await createServer({ configFile: 'laboratorio/vite.config.js', server: { middlewareMode: true, hmr: false }, logLevel: 'error' })
const { datosEjemplo, extenderDatos, sinEjemplos } = await v.ssrLoadModule('/src/plantillas/datosEjemplo.js')
const { PLANTILLAS } = await v.ssrLoadModule('/src/plantillas/semillas.js')

// Solo lo que usa la generación: id y, por sección, id, fuente y campos (las plantillas mismas las lee el CRM de catalogos/plantillas.json).
const compacta = (p) => ({ id: p.id, secciones: p.secciones.map((s) => ({ id: s.id, ...(s.fuente ? { fuente: s.fuente } : {}), ...(s.campos ? { campos: s.campos } : {}) })) })
const ordenar = (x) => (Array.isArray(x) ? x.map(ordenar) : x && typeof x === 'object' ? Object.fromEntries(Object.keys(x).sort().map((k) => [k, ordenar(x[k])])) : x)
const huella = (x) => createHash('sha256').update(JSON.stringify(ordenar(x))).digest('hex')

const plantillas = PLANTILLAS.map(compacta)
const casos = []
for (const p of plantillas) {
  for (const nivel of ['vacio', 'pocos']) casos.push({ caso: `${p.id}:${nivel}`, entrada: { plantilla: p.id, nivel }, salida: datosEjemplo(p, nivel) })
}
// «muchos» (220 por sección): completo para 3 plantillas y, para todas, la huella sha256 del JSON con claves ordenadas.
const completos = ['membresias', 'gimnasio', 'clinica-dental']
for (const p of plantillas) {
  const d = datosEjemplo(p, 'muchos')
  casos.push({ caso: `${p.id}:muchos`, entrada: { plantilla: p.id, nivel: 'muchos' }, ...(completos.includes(p.id) ? { salida: d } : {}), huella: huella(d) })
}
// Lo que Shifu agrega después (secciones y campos nuevos, opciones de estado renombradas): cada cosa con su semilla.
const base = PLANTILLAS.find((p) => p.id === 'membresias')
const est = {
  secciones: [{ id: 'cobros', titulo: 'Cobros', campos: [{ id: 'miembro', nombre: 'Miembro', tipo: 'texto' }, { id: 'monto', nombre: 'Monto', tipo: 'dinero' }, { id: 'vence', nombre: 'Vence', tipo: 'fecha' }, { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Pendiente', 'Pagado'] }] }],
  campos: { miembros: [{ id: 'telefono', nombre: 'Teléfono', tipo: 'texto' }, { id: 'cumple', nombre: 'Cumpleaños', tipo: 'fecha' }] },
}
const camposMiembros = base.secciones.find((s) => s.id === 'miembros').campos
const cEstado = camposMiembros.find((c) => c.tipo === 'estado')
if (cEstado) est.mapeoEstado = { miembros: { [cEstado.id]: { [cEstado.opciones[0]]: 'Renombrada' } } }
const extender = ['pocos', 'muchos'].map((nivel) => ({ caso: `membresias+extras:${nivel}`, entrada: { plantilla: 'membresias', nivel, est }, salida: extenderDatos(datosEjemplo(base, nivel), base, est, nivel) }))
const sin = [{ caso: 'membresias:pocos sin ejemplos', entrada: { plantilla: 'membresias', nivel: 'pocos' }, salida: sinEjemplos(datosEjemplo(base, 'pocos')) }]

writeFileSync('nucleo/tests/crm/fixtures/lab/ejemplos_datos.json', JSON.stringify({ hoy: '2026-10-16', casos }))
writeFileSync('nucleo/tests/crm/fixtures/lab/ejemplos_extender.json', JSON.stringify({ hoy: '2026-10-16', casos: [...extender, ...sin] }))
console.log(`${plantillas.length} plantillas · ${casos.length} casos de datos · ${extender.length + sin.length} de extender/sin ejemplos`)
await v.close()
