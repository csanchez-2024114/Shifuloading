/* Genera src/plantillas/catalogos/fuentes.js (D33) desde el catálogo PÚBLICO de Google Fonts (fonts.google.com/metadata/fonts):
 * nombres, categorías y pesos reales; nada escrito a mano. Se queda con las ~200 familias más usadas que tienen letras
 * latinas (acentos y ñ) y marca cuáles sirven para la interfaz (legible_ui) con una regla medible.
 * Uso (desde la raíz de Shifuloading): node laboratorio/servidor/generar-fuentes.mjs */
import { writeFileSync, mkdirSync } from 'node:fs'

const CANTIDAD = 200
const txt = await (await fetch('https://fonts.google.com/metadata/fonts')).text()
const lista = JSON.parse(txt.slice(txt.indexOf('{'))).familyMetadataList
const CAT = { 'Sans Serif': 'sans', Serif: 'serif', Display: 'display', Monospace: 'mono', Handwriting: 'manuscrita' }
const slug = (s) => s.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')

const fuentes = lista
  .filter((f) => f.subsets.includes('latin') && CAT[f.category] && !f.family.includes('Material') && !/Icons|Symbols|Emoji/i.test(f.family))
  .sort((a, b) => a.popularity - b.popularity) // 1 = la más usada
  .slice(0, CANTIDAD)
  .map((f) => {
    const pesos = [...new Set(Object.keys(f.fonts).filter((k) => !k.endsWith('i')).map(Number))].sort((a, b) => a - b)
    const variable = (f.axes || []).some((a) => a.tag === 'wght')
    const categoria = CAT[f.category]
    // Legible en interfaz: sans o serif, con normal (400) y negrita (≥600) y al menos 3 pesos, o variable en grosor.
    const legible_ui = ['sans', 'serif'].includes(categoria) && pesos.includes(400) && pesos.some((p) => p >= 600) && (pesos.length >= 3 || variable)
    return { id: slug(f.family), nombre: f.family, categoria, pesos, variable, legible_ui, popularidad: f.popularity, latin_ext: f.subsets.includes('latin-ext') }
  })

// Pares título + texto: una regla fija (contraste de categoría o la misma familia variable), solo entre fuentes del catálogo.
const ui = fuentes.filter((f) => f.legible_ui)
const sans = ui.filter((f) => f.categoria === 'sans').slice(0, 14), serif = ui.filter((f) => f.categoria === 'serif').slice(0, 8)
const display = fuentes.filter((f) => f.categoria === 'display' && f.pesos.some((p) => p >= 600)).slice(0, 6)
const PARES = []
for (let i = 0; i < 8 && i < serif.length; i++) PARES.push({ titulo: serif[i].id, texto: sans[i].id, estilo: 'clásico' })
for (let i = 0; i < 8 && i < serif.length; i++) PARES.push({ titulo: sans[i + 6]?.id || sans[i].id, texto: serif[i].id, estilo: 'editorial' })
for (let i = 0; i < 12; i++) PARES.push({ titulo: sans[i].id, texto: sans[i].id, estilo: 'moderno' })
for (let i = 0; i < display.length; i++) PARES.push({ titulo: display[i].id, texto: sans[i].id, estilo: 'llamativo' })
for (const [t, x] of [['montserrat', 'open-sans'], ['poppins', 'inter'], ['playfair-display', 'lato'], ['oswald', 'roboto'], ['raleway', 'merriweather'], ['nunito', 'nunito-sans']]) if (fuentes.some((f) => f.id === t) && fuentes.some((f) => f.id === x)) PARES.push({ titulo: t, texto: x, estilo: 'clásico de la web' })

mkdirSync('laboratorio/src/plantillas/catalogos', { recursive: true })
writeFileSync('laboratorio/src/plantillas/catalogos/fuentes.js', `/* Catálogo de tipografías (D33). GENERADO por servidor/generar-fuentes.mjs desde el catálogo público de Google Fonts
 * (${new Date().toISOString().slice(0, 10)}): ${fuentes.length} familias con letras latinas, ${ui.length} aptas para la interfaz, ${PARES.length} pares título + texto.
 * No se edita a mano. */
export const FUENTES = ${JSON.stringify(fuentes)}

export const PARES = ${JSON.stringify(PARES)}

/** URL de Google Fonts para cargar una familia con los pesos pedidos (solo los que tiene; si no, 400 y 700). */
export function urlFuente(id, pesos = [400, 600, 700]) {
  const f = FUENTES.find((x) => x.id === id); if (!f) return null
  const usar = pesos.filter((p) => f.pesos.includes(p)); const lista = usar.length ? usar : f.pesos.filter((p) => p === 400 || p === 700)
  return \`https://fonts.googleapis.com/css2?family=\${encodeURIComponent(f.nombre).replace(/%20/g, '+')}:wght@\${(lista.length ? lista : [f.pesos[0]]).join(';')}&display=swap\`
}
`)
console.log(`${fuentes.length} familias · ${ui.length} aptas para interfaz · ${PARES.length} pares · categorías: ${JSON.stringify(fuentes.reduce((m, f) => ({ ...m, [f.categoria]: (m[f.categoria] || 0) + 1 }), {}))}`)
