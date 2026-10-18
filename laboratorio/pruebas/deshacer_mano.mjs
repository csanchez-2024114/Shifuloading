/* «Deshaz» por chat después de cambios HECHOS A MANO (D56): el estado se arma con el mismo código de la pantalla
 * (ejecutar + conPunto) y la IA real recibe el pedido. Verifica los REGISTROS que quedan, no solo qué herramienta usó.
 * Uso (desde la raíz de Shifuloading, con el laboratorio corriendo): node laboratorio/pruebas/deshacer_mano.mjs [repeticiones=3] */
import { createServer } from 'vite'
const N = Number(process.argv[2] || 3)
const v = await createServer({ configFile: 'laboratorio/vite.config.js', server: { middlewareMode: true, hmr: false }, logLevel: 'error' })
const { ejecutar, conPunto, datosActuales } = await v.ssrLoadModule('/src/plantillas/edicion.js')
const { plantillaPorId } = await v.ssrLoadModule('/src/plantillas/semillas.js')
const p = plantillaPorId('membresias'), muestra = { nivel: 'pocos', ejemplos: true, pais: 'gt' }, ctx = { muestra, confirmado: true }
const B = [{ uid: 'b0', vista: 'kpis', seccion: 'miembros', opciones: { por: 'estado' }, ancho: 12, alto: 1 }]
const aMano = (e, nombre, args, que) => { const r = ejecutar(p, e, nombre, args, ctx); if (!r.ok) throw new Error(r.resultado); return conPunto(e, r.estado, `A mano: ${que}`) }
const nombres = (e) => datosActuales(p, e, muestra).registros.miembros.map((r) => r.valores.nombre)
const plan = (e, n) => datosActuales(p, e, muestra).registros.miembros.find((r) => r.valores.nombre === n)?.valores.plan
// Cadena: agregó a Rosa (a mano) → le cambió el plan (a mano) → borró a Carlos Pérez (a mano).
let e = { vista: 'miembros', bloques: B }
e = aMano(e, 'agregar_registro', { seccion: 'miembros', valores: { nombre: 'Rosa Gómez', plan: 'Mensual' } }, 'agregó «Rosa Gómez» a Miembros')
e = aMano(e, 'editar_registro', { seccion: 'miembros', registro: 'Rosa Gómez', valores: { plan: 'Anual' } }, 'editó «Rosa Gómez» en Miembros')
e = aMano(e, 'borrar_registro', { seccion: 'miembros', registro: 'Carlos Pérez' }, 'borró «Carlos Pérez» de Miembros')
const pide = async (estado, texto) => (await fetch((process.env.BASE || 'http://localhost:5190') + (process.env.RUTA_CHAT || '/api/lab/chat'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ plantilla: 'membresias', estado, texto, muestra }) })).json()
const CASOS = [
  ['deshaz lo último (el borrado a mano)', 'deshaz eso', (d) => nombres(d.estado).includes('Carlos Pérez') && plan(d.estado, 'Rosa Gómez') === 'Anual'],
  ['deshacer uno anterior por lo que dice', 'deshaz lo que le cambié a Rosa', (d) => plan(d.estado, 'Rosa Gómez') === 'Mensual' && !nombres(d.estado).includes('Carlos Pérez')],
  ['preguntar qué hizo a mano', '¿qué cambios hice a mano?', (d) => !d.cambios.length && /Rosa/.test(d.respuesta) && /Carlos/.test(d.respuesta)],
]
let ok = 0, tot = 0
for (let i = 0; i < N; i++) for (const [desc, texto, verif] of CASOS) {
  const d = await pide(e, texto); const b = !d.error && verif(d); ok += b; tot++
  console.log(`${b ? '✓' : '✗'} ${desc} | «${texto}»`)
  if (!b) console.log(`     hizo: ${JSON.stringify((d.cambios || []).map((c) => [c.herramienta, c.args]))}\n     dijo: ${String(d.respuesta || d.error).slice(0, 200)}`)
}
console.log(`\n${ok}/${tot} correctos`)
await v.close()
