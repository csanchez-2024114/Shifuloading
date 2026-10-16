/* Captura de una región de la pantalla para el chat del laboratorio, y QUÉ CONTENEDORES quedaron dentro.
 * - html2canvas 1.4.1 (la del CRM base) no entiende colores modernos (color-mix, color(), oklab): fallaba con
 *   "unsupported color function". En la copia que dibuja, el código convierte esos colores a rgb antes de dibujar.
 * - Además se calcula, con las posiciones reales, qué bloques, pestañas del menú, logo o encabezado quedaron dentro
 *   del recuadro, con su id: así Shifu sabe EXACTAMENTE qué quiere cambiar la persona (sin adivinar por la imagen). */

const ANCHO_MAX = 1400
const MODERNO = /color\(|color-mix\(|oklab\(|oklch\(|lab\(|lch\(/i
const COLORES = ['color', 'background-color', 'border-top-color', 'border-right-color', 'border-bottom-color', 'border-left-color', 'outline-color', 'fill', 'stroke', 'text-decoration-color', 'column-rule-color', 'caret-color']
const QUITAR = ['box-shadow', 'text-shadow', 'background-image', 'mask-image', '-webkit-mask-image', 'filter', 'backdrop-filter']

/** Convierte cualquier color que entienda el navegador a rgba() usando un lienzo de 1 píxel. */
function aRgba(ctx, valor) {
  ctx.clearRect(0, 0, 1, 1); ctx.fillStyle = '#000'; ctx.fillStyle = valor; ctx.fillRect(0, 0, 1, 1)
  const [r, g, b, a] = ctx.getImageData(0, 0, 1, 1).data
  return `rgba(${r}, ${g}, ${b}, ${(a / 255).toFixed(3)})`
}

function limpiarColores(doc) {
  const lienzo = doc.createElement('canvas'); lienzo.width = lienzo.height = 1
  const ctx = lienzo.getContext('2d', { willReadFrequently: true })
  const ver = doc.defaultView
  for (const el of doc.querySelectorAll('*')) {
    const cs = ver.getComputedStyle(el)
    for (const p of COLORES) { const v = cs.getPropertyValue(p); if (v && MODERNO.test(v)) el.style.setProperty(p, aRgba(ctx, v), 'important') }
    for (const p of QUITAR) { const v = cs.getPropertyValue(p); if (v && MODERNO.test(v)) el.style.setProperty(p, 'none', 'important') }
    // Texto con degradado recortado (títulos del estilo Vivo): sin el degradado quedaría transparente.
    if (cs.getPropertyValue('-webkit-background-clip') === 'text' || cs.getPropertyValue('background-clip') === 'text') { el.style.setProperty('color', aRgba(ctx, ver.getComputedStyle(doc.body).color || '#fff'), 'important'); el.style.setProperty('background', 'none', 'important') }
  }
}

/** Dibuja la región `{ x, y, ancho, alto }` (coordenadas de la ventana) y devuelve { url, ancho, alto }. */
export async function capturarRegionLab(r) {
  const { default: html2canvas } = await import('html2canvas')
  const lienzo = await html2canvas(document.body, {
    x: r.x + window.scrollX, y: r.y + window.scrollY, width: r.ancho, height: r.alto,
    scale: Math.min(2, window.devicePixelRatio || 1), useCORS: true, logging: false,
    ignoreElements: (el) => !!el.closest?.('.mc-chat, .mc-captura, .rc'),
    onclone: (doc) => {
      const estilo = doc.createElement('style')
      estilo.textContent = '*, *::before, *::after { animation: none !important; transition: none !important; }'
      doc.head.appendChild(estilo)
      limpiarColores(doc)
    },
  })
  let salida = lienzo
  if (lienzo.width > ANCHO_MAX) {
    salida = document.createElement('canvas'); salida.width = ANCHO_MAX; salida.height = Math.round((lienzo.height * ANCHO_MAX) / lienzo.width)
    salida.getContext('2d').drawImage(lienzo, 0, 0, salida.width, salida.height)
  }
  return { url: salida.toDataURL('image/jpeg', 0.88), ancho: salida.width, alto: salida.height }
}

/** Qué piezas con id quedaron dentro del recuadro (al menos 40% de su área). */
export function piezasEnRegion(r) {
  const dentro = (el) => {
    const b = el.getBoundingClientRect(); if (!b.width || !b.height) return false
    const ix = Math.max(0, Math.min(b.right, r.x + r.ancho) - Math.max(b.left, r.x)), iy = Math.max(0, Math.min(b.bottom, r.y + r.alto) - Math.max(b.top, r.y))
    return (ix * iy) / (b.width * b.height) >= 0.4
  }
  const out = []
  for (const el of document.querySelectorAll('[data-bloque]')) if (dentro(el)) out.push({ tipo: 'bloque', id: el.dataset.bloque, nombre: el.querySelector('h2')?.textContent || '' })
  for (const el of document.querySelectorAll('.mc-menu li button')) if (dentro(el)) out.push({ tipo: 'pestaña', id: el.dataset.seccion || '', nombre: el.textContent.trim() })
  const logo = document.querySelector('.mc-top .pl-logo, .mc-top svg'); if (logo && dentro(logo)) out.push({ tipo: 'logo', nombre: 'logo del encabezado' })
  const cab = document.querySelector('.mc-cab'); if (cab && dentro(cab)) out.push({ tipo: 'encabezado', nombre: cab.querySelector('h1')?.textContent || 'título' })
  return out
}
