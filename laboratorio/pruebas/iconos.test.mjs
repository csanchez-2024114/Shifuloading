/* Qué ícono recibe cada pestaña (por su título) en todas las plantillas y pestañas de la biblioteca: medida de cobertura. */
import { createServer } from 'vite'
const v = await createServer({ configFile: 'laboratorio/vite.config.js', server: { middlewareMode: true, hmr: false }, logLevel: 'error' })
const { conceptoPara, cargarIconos } = await v.ssrLoadModule('/src/plantillas/iconos.jsx')
await cargarIconos()
const { PLANTILLAS } = await v.ssrLoadModule('/src/plantillas/semillas.js')
const { PESTANAS } = await v.ssrLoadModule('/src/plantillas/edicion.js')
const titulos = [...new Set([...PLANTILLAS.flatMap((p) => p.secciones.map((s) => s.titulo)), ...Object.values(PESTANAS).map((p) => p.seccion.titulo)])]
const sin = []; const con = []
for (const t of titulos) { const c = conceptoPara(t); (c ? con : sin).push(`${t} → ${c || '—'}`) }
console.log(con.join('\n')); console.log('\nSIN CONCEPTO:\n' + sin.join('\n'))
console.log(`\n${con.length}/${titulos.length} títulos con ícono propio`)
await v.close()
