/* Pruebas del acomodo automático (D38). Corre con: node laboratorio/pruebas/acomodar.test.mjs (desde la raíz de Shifuloading).
 * edicion.js importa .jsx, así que se carga con Vite (igual que lo hace el servidor del chat). */
import { createServer } from 'vite'
import assert from 'node:assert/strict'

const vite = await createServer({ configFile: 'laboratorio/vite.config.js', server: { middlewareMode: true, hmr: false }, logLevel: 'error' })
const { acomodar, ubicar, ejecutar } = await vite.ssrLoadModule('/src/plantillas/edicion.js')
const { plantillaPorId } = await vite.ssrLoadModule('/src/plantillas/semillas.js')

// Huecos de la rejilla de 12 columnas (misma simulación "dense" que el CSS).
function huecos(bs) {
  const celdas = []
  for (const b of bs) {
    const w = b.ancho, h = b.vista === 'kpis' ? 1 : b.alto || 1
    let f = 0, c
    const libre = (f, c) => { for (let y = f; y < f + h; y++) for (let x = c; x < c + w; x++) if (celdas[y]?.[x]) return false; return c + w <= 12 }
    for (;; f++) { c = [...Array(13 - w).keys()].find((x) => libre(f, x)); if (c !== undefined) break }
    for (let y = f; y < f + h; y++) { celdas[y] ||= []; for (let x = c; x < c + w; x++) celdas[y][x] = b.uid }
  }
  let n = 0; for (const fila of celdas) for (let c = 0; c < 12; c++) if (!fila?.[c]) n++
  return n
}
const B = (uid, ancho, alto = 2, vista = 'grafico') => ({ uid, ancho, alto, vista, seccion: 's', opciones: {} })
let ok = 0
const caso = (nombre, fn) => { try { fn(); ok++; console.log('✓', nombre) } catch (e) { console.log('✗', nombre, '\n ', e.message); process.exitCode = 1 } }

caso('sin huecos no cambia nada', () => { const bs = [B('a', 12, 1, 'kpis'), B('b', 6), B('c', 6)]; assert.deepEqual(acomodar(bs), bs) })
caso('8 + 3 → el de la izquierda se ensancha a 4... no: el último llena la fila', () => { const r = acomodar([B('a', 8), B('b', 3)]); assert.equal(huecos(r), 0); assert.equal(r[1].ancho, 4) })
caso('quitar uno de tres (4+4+4 → 4+4) deja 0 huecos', () => { const r = acomodar([B('a', 4), B('b', 4)]); assert.equal(huecos(r), 0) })
caso('fila incompleta al final (6 + 6 + 6) se completa', () => { const r = acomodar([B('a', 6), B('b', 6), B('c', 6)]); assert.equal(huecos(r), 0); assert.equal(r[2].ancho, 12) })
caso('alto distinto (8×2 + 4×1) → el chico crece hacia abajo', () => { const r = acomodar([B('a', 8, 2), B('b', 4, 1)]); assert.equal(huecos(r), 0); assert.equal(r[1].alto, 2) })
caso('el resumen (kpis) nunca crece de alto', () => { const r = acomodar([B('k', 8, 1, 'kpis'), B('a', 4, 2)]); assert.equal(r[0].alto, 1) })
caso('el bloque fijo (recién redimensionado) no se toca', () => { const r = acomodar([B('a', 4), B('b', 8)], new Set(['a'])); assert.equal(r[0].ancho, 4) })
caso('no cambia el orden ni quita bloques', () => { const bs = [B('a', 3), B('b', 8), B('c', 3, 1), B('d', 6)]; const r = acomodar(bs); assert.deepEqual(r.map((b) => b.uid), ['a', 'b', 'c', 'd']) })
caso('ubicar coincide con el acomodo', () => { const u = ubicar([B('a', 6), B('b', 6)]); assert.equal(u.a.lado, 'izquierda'); assert.equal(u.b.lado, 'derecha') })

// Todas las plantillas: quitar cualquier bloque deja 0 huecos (acomodo automático corre dentro de ejecutar).
for (const id of ['embudo', 'agenda', 'pedidos', 'membresias', 'proyectos', 'simple']) {
  const p = plantillaPorId(id)
  caso(`${id}: quitar cada bloque deja 0 huecos`, () => {
    const bloques = p.inicio.map((b, i) => ({ ...b, uid: `b${i + 1}`, ancho: b.ancho || (['kpis', 'tablero', 'agenda'].includes(b.vista) ? 12 : 6), alto: b.alto || (b.vista === 'kpis' ? 1 : 2) }))
    for (const b of bloques) {
      const r = ejecutar(p, { bloques }, 'quitar_bloque', { bloque: b.uid })
      assert.ok(r.ok, r.resultado)
      assert.equal(huecos(r.estado.bloques), 0, `al quitar ${b.uid} (${b.vista}) quedan ${huecos(r.estado.bloques)} celdas vacías: ${JSON.stringify(r.estado.bloques.map((x) => [x.uid, x.ancho, x.alto]))}`)
    }
  })
}
// Medida: 500 inicios al azar (anchos 3/4/6/8/12, altos 1–3). Cuántos tenían huecos antes y cuántos después.
let semilla = 7; const azar = () => ((semilla = (semilla * 1103515245 + 12345) % 2147483648) / 2147483648)
let antes = 0, despues = 0, celdasAntes = 0, celdasDespues = 0
for (let i = 0; i < 500; i++) {
  const n = 2 + Math.floor(azar() * 6)
  const bs = Array.from({ length: n }, (_, j) => B(`r${j}`, [3, 4, 6, 8, 12][Math.floor(azar() * 5)], 1 + Math.floor(azar() * 3)))
  const h0 = huecos(bs), h1 = huecos(acomodar(bs))
  antes += h0 > 0; despues += h1 > 0; celdasAntes += h0; celdasDespues += h1
}
console.log(`Al azar (500 inicios): con huecos antes ${antes}, después ${despues} · celdas vacías ${celdasAntes} → ${celdasDespues}`)
console.log(`\n${ok} pruebas bien`)
await vite.close()
