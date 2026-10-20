/* Exporta los catálogos del laboratorio a JSON para el CRM de Carlos (D61, contrato §5). Los JS siguen siendo la fuente
 * mientras viva el laboratorio; los JSON se commitean y test_catalogos.py falla si quedan viejos.
 * Uso (desde la raíz del repo): node laboratorio/servidor/exportar-catalogos.mjs [carpeta]
 *   carpeta por defecto: nucleo/src/assistant/packs/crm/catalogos
 * Escribe:
 *  - plantillas.json  { semillas: [6], biblioteca: [21, por id] }   (semillas.js / biblioteca/*.js, sin funciones)
 *  - pestanas.json    [35, por id]                                    (biblioteca-pestanas/*.js)
 *  - graficos.json    { <tipo>: { nombre, familia, requiere, opciones, html? } } en el ORDEN de compatibles()
 *  - vistas.json      VISTAS de validar.js
 *  - iconos.json      { familias, iconos }                            (catalogos/iconos.js)
 *  - fuentes.json     { fuentes, pares }                              (catalogos/fuentes.js)
 * Determinista: mismo código → mismos bytes (JSON con sangría de 2 y salto de línea final). Sin IA ni red. */
import { createServer } from 'vite'
import { mkdirSync, readdirSync, writeFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const LAB = fileURLToPath(new URL('..', import.meta.url))
const RAIZ = resolve(LAB, '..')
const destino = resolve(process.argv[2] || join(RAIZ, 'nucleo/src/assistant/packs/crm/catalogos'))

/** Copia apta para JSON. Una función en el catálogo es un error (el JSON la perdería sin avisar). */
function limpio(x, donde = '') {
  if (typeof x === 'function') throw new Error(`hay una función en ${donde}: el catálogo debe ser solo datos`)
  if (Array.isArray(x)) return x.map((v, i) => limpio(v, `${donde}[${i}]`))
  if (x && typeof x === 'object') return Object.fromEntries(Object.entries(x).filter(([, v]) => v !== undefined).map(([k, v]) => [k, limpio(v, `${donde}.${k}`)]))
  return x
}
const porId = (a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0)

const vite = await createServer({ configFile: join(LAB, 'vite.config.js'), server: { middlewareMode: true, hmr: false }, logLevel: 'error' })
try {
  const cargar = (p) => vite.ssrLoadModule(p)
  const { PLANTILLAS } = await cargar('/src/plantillas/semillas.js')
  const modulos = async (dir) => Promise.all(readdirSync(join(LAB, 'src/plantillas', dir)).filter((f) => f.endsWith('.js')).sort()
    .map(async (f) => (await cargar(`/src/plantillas/${dir}/${f}`)).default))
  const biblio = (await modulos('biblioteca')).filter(Boolean)
  const pestanas = (await modulos('biblioteca-pestanas')).filter(Boolean)
  // Semillas = lo que PLANTILLAS trae escrito en semillas.js (lo que no viene de ./biblioteca), en su orden.
  const semillas = PLANTILLAS.filter((p) => !biblio.includes(p))
  const { CATALOGO } = await cargar('/src/plantillas/graficos-catalogo.js')
  const { VISTAS } = await cargar('/src/plantillas/validar.js')
  const { FAMILIAS, ICONOS } = await cargar('/src/plantillas/catalogos/iconos.js')
  const { FUENTES, PARES } = await cargar('/src/plantillas/catalogos/fuentes.js')

  const archivos = {
    'plantillas.json': { semillas: limpio(semillas, 'semillas'), biblioteca: limpio([...biblio].sort(porId), 'biblioteca') },
    'pestanas.json': limpio([...pestanas].sort(porId), 'pestanas'),
    'graficos.json': limpio(CATALOGO, 'graficos'),
    'vistas.json': limpio(VISTAS, 'vistas'),
    'iconos.json': limpio({ familias: FAMILIAS, iconos: ICONOS }, 'iconos'),
    'fuentes.json': limpio({ fuentes: FUENTES, pares: PARES }, 'fuentes'),
  }
  mkdirSync(destino, { recursive: true })
  for (const [nombre, datos] of Object.entries(archivos)) writeFileSync(join(destino, nombre), `${JSON.stringify(datos, null, 2)}\n`)
  console.log(`Catálogos en ${destino}: ${semillas.length} semillas, ${biblio.length} de biblioteca, ${pestanas.length} pestañas, `
    + `${Object.keys(CATALOGO).length} gráficos, ${Object.keys(VISTAS).length} vistas, ${Object.keys(ICONOS).length} íconos, ${FUENTES.length} fuentes`)
} finally {
  await vite.close()
}
