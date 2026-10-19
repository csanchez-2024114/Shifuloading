/* documentoDeArchivo — corre con: node src/components/__pruebas__/adjuntos.test.mjs */
import { createServer } from 'vite'
import assert from 'node:assert/strict'

const v = await createServer({
  configFile: 'vite.config.js',
  cacheDir: process.env.VITE_CACHE_DIR,
  server: { middlewareMode: true, hmr: false },
  optimizeDeps: { noDiscovery: true, entries: [] },
  logLevel: 'error',
})
const { documentoDeArchivo } = await v.ssrLoadModule('/src/components/adjuntos.js')

const archivo = (nombre, tipo, cuerpo) => new File([cuerpo], nombre, { type: tipo })

let ok = 0
const caso = async (n, fn) => {
  try { await fn(); ok++; console.log('✓', n) } catch (e) { console.log('✗', n, '\n ', e.stack); process.exitCode = 1 }
}

await caso('acepta txt y devuelve data URL', async () => {
  const r = await documentoDeArchivo(archivo('a.txt', 'text/plain', 'hola'))
  assert.equal(r.nombre, 'a.txt')
  assert.match(r.datos, /^data:text\/plain;base64,/)
  assert.equal(r.tamano, 4)
})

await caso('rechaza exe', async () => {
  await assert.rejects(() => documentoDeArchivo(archivo('x.exe', 'application/octet-stream', 'MZ')), /Solo puedo leer/)
})

console.log(`\n${ok} pruebas OK`)
await v.close()
