/* Graba los fixtures dorados de la regla de asignación (asignar.js) para el port a Python (nucleo/src/assistant/packs/crm/asignar.py).
 * Combina rubros, ciclos, objetivos y «qué vendes» de las plantillas reales (más valores que no existen y respuestas vacías).
 * Uso (desde la raíz del repo): node laboratorio/servidor/grabar-asignar.mjs */
import { createServer } from 'vite'
import { writeFileSync } from 'node:fs'

const v = await createServer({ configFile: 'laboratorio/vite.config.js', server: { middlewareMode: true, hmr: false }, logLevel: 'error' })
const { asignar } = await v.ssrLoadModule('/src/plantillas/asignar.js')
const { PLANTILLAS } = await v.ssrLoadModule('/src/plantillas/semillas.js')

const uniq = (xs) => [...new Set(xs)]
const conAsig = PLANTILLAS.filter((p) => p.asignacion)
const rubros = [...uniq(conAsig.flatMap((p) => p.asignacion.rubros)), 'otro', undefined]
const ciclos = [...uniq(conAsig.flatMap((p) => p.asignacion.ciclos)), 'nunca', undefined]
const objs = uniq(conAsig.flatMap((p) => p.asignacion.objetivos || []))
const vendes = ['', 'Membresías de gimnasio y clases de yoga', 'pasteles, pan y café', 'Consultas dentales y ortodoncia', 'casas y apartamentos en renta',
  'Software de facturación en la nube', 'reparación de carros', 'cortes de pelo y barba', 'seguros de vida y de auto', 'envíos y mensajería',
  'Vendo ropa por Instagram', 'asesoría contable e impuestos', 'cuartos de hotel', 'comida y bebidas', 'diseño, campañas y redes sociales',
  'materiales de construcción, cemento, varillas', 'Clases de inglés para niños', 'vacunas y baños para mascotas', 'sesiones de fotografía para bodas',
  'donaciones', 'xyz', 'ñandú pingüino ÁRBOL', 'Membresías mensuales']

// Combinaciones deterministas: un recorrido mixto de todo (sin azar del sistema).
let s = 12345
const sig = () => { s = (s * 1103515245 + 12345) % 2147483648; return s / 2147483648 }
const de = (xs) => xs[Math.floor(sig() * xs.length)]
const casos = []
for (const rubro of rubros) for (const ciclo of ciclos) {
  for (let k = 0; k < 3; k++) {
    const n = Math.floor(sig() * 4)
    const objetivos = uniq(Array.from({ length: n }, () => de([...objs, 'inventado'])))
    const queVendes = de(vendes)
    const entrada = { ...(rubro !== undefined ? { rubro } : {}), ...(ciclo !== undefined ? { ciclo } : {}), objetivos, queVendes }
    casos.push({ caso: `${rubro}|${ciclo}|${objetivos.join('+')}|${queVendes}`, entrada, salida: asignar(entrada) })
  }
}
for (const q of vendes) casos.push({ caso: `solo vendes: ${q}`, entrada: { queVendes: q }, salida: asignar({ queVendes: q }) })
casos.push({ caso: 'sin respuestas', entrada: {}, salida: asignar({}) })
writeFileSync('nucleo/tests/crm/fixtures/lab/asignar_casos.json', JSON.stringify(casos))
console.log(`${PLANTILLAS.length} plantillas (${conAsig.length} con asignación) · ${casos.length} casos · ambiguos ${casos.filter((c) => c.salida.ambiguo).length}`)
await v.close()
