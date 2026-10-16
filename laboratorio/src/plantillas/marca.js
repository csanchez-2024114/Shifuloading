/* Branding del negocio (D19-D21): una BASE de tokens (los del CRM) y una "marca" que la persona cambia pidiéndoselo a Shifu.
 * Nada se inventa en la pantalla: la marca solo reemplaza tokens (--acento, --bg, --card, --tx, --fuente…), y TODAS las
 * piezas los usan, así cada plantilla, vista y gráfico toma la marca sola.
 * El código cuida que siempre se lea: cada color que se usa como texto o sobre el que va texto se ajusta (más claro u
 * oscuro) hasta llegar al contraste mínimo, y se reporta qué se ajustó para que Shifu lo diga con honestidad. */

/** Tipografías permitidas (Google Fonts). Una para títulos y otra para el texto; si no se pide nada, Inter. */
export const FUENTES = {
  Inter: 'Inter:wght@400;500;600;700;800', Poppins: 'Poppins:wght@400;500;600;700', Nunito: 'Nunito:wght@400;600;700;800',
  Montserrat: 'Montserrat:wght@400;500;600;700', 'DM Sans': 'DM+Sans:wght@400;500;700', Rubik: 'Rubik:wght@400;500;600;700',
  'Work Sans': 'Work+Sans:wght@400;500;600;700', Lato: 'Lato:wght@400;700', 'Playfair Display': 'Playfair+Display:wght@500;600;700',
  Lora: 'Lora:wght@400;500;600;700', Merriweather: 'Merriweather:wght@400;700', Outfit: 'Outfit:wght@400;500;600;700',
}

/** La base: los tokens actuales del CRM (crm-extra.css), por tema. */
export const BASE = {
  oscuro: { bg: '#070b0a', bgTop: '#0a0f0e', card: '#0c1211', tx: '#ffffff', acento: '#22d3a6', secundario: '#7c5cff' },
  claro: { bg: '#eef3f1', bgTop: '#ffffff', card: '#ffffff', tx: '#14211d', acento: '#22d3a6', secundario: '#7c5cff' },
}

// ── Color ────────────────────────────────────────────────────────────────────────────────────────────
const HEX = /^#?([0-9a-f]{3}|[0-9a-f]{6})$/i
export const esHex = (c) => typeof c === 'string' && HEX.test(c.trim())
const aRgb = (c) => { let h = c.trim().replace('#', ''); if (h.length === 3) h = [...h].map((x) => x + x).join(''); return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)) }
const aHex = (rgb) => `#${rgb.map((v) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0')).join('')}`
const lum = (c) => { const [r, g, b] = aRgb(c).map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4 }); return 0.2126 * r + 0.7152 * g + 0.0722 * b }
export const contraste = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((m, n) => n - m); return (x + 0.05) / (y + 0.05) }
const mezclar = (a, b, t) => aHex(aRgb(a).map((v, i) => v + (aRgb(b)[i] - v) * t))
/** Acerca `color` a blanco o negro (lo que más contraste dé contra `fondo`) hasta llegar a `minimo`. */
function legible(color, fondo, minimo) {
  if (contraste(color, fondo) >= minimo) return { color, ajustado: false }
  const meta = lum(fondo) > 0.4 ? '#000000' : '#ffffff'
  for (let t = 0.05; t <= 1.0001; t += 0.05) { const c = mezclar(color, meta, t); if (contraste(c, fondo) >= minimo) return { color: c, ajustado: true } }
  return { color: meta, ajustado: true }
}
const rgbTriplete = (c) => aRgb(c).join(', ')

/**
 * Tokens finales para un tema: base + marca, con los ajustes de legibilidad aplicados.
 * marca = { primario?, secundario?, fondo?, superficie?, texto?, fuenteTitulos?, fuenteTexto?, logo?, nombre? }
 * Devuelve { vars: {'--acento': ...}, ajustes: ['…'] } — los ajustes son frases para que Shifu diga qué tuvo que corregir.
 */
export function tokensDeMarca(marca = {}, tema = 'oscuro') {
  if (!Object.keys(marca).some((k) => k !== 'logo' && k !== 'nombre' && marca[k])) return { vars: {}, ajustes: [] } // sin marca: la base tal cual
  const b = BASE[tema] || BASE.oscuro
  const ajustes = []
  // Fondos: si piden un fondo propio se usa; la superficie de las tarjetas sale del fondo si no la dan.
  const bg = esHex(marca.fondo) ? marca.fondo : b.bg
  const card = esHex(marca.superficie) ? marca.superficie : esHex(marca.fondo) ? mezclar(bg, tema === 'oscuro' ? '#ffffff' : '#ffffff', tema === 'oscuro' ? 0.05 : 0.7) : b.card
  // Texto: 7:1 sobre las tarjetas (texto principal); los secundarios salen de él.
  let tx = esHex(marca.texto) ? marca.texto : b.tx
  const t1 = legible(tx, card, 7); const tono = (c) => (lum(c) > 0.4 ? 'claro' : 'oscuro')
  if (t1.ajustado && esHex(marca.texto)) ajustes.push(`en tema ${tema} el texto ${marca.texto} no se lee sobre ${card}: quedó ${t1.color} (${tono(t1.color)}), no ${marca.texto}`); tx = t1.color
  // Acento (primario): se usa para números, líneas, botones y texto destacado → mínimo 4.5 contra las tarjetas.
  const prim = esHex(marca.primario) ? marca.primario : b.acento
  const a = legible(prim, card, 4.5); if (a.ajustado && esHex(marca.primario)) ajustes.push(`en tema ${tema} el color principal ${marca.primario} se ${lum(a.color) > lum(prim) ? 'aclaró' : 'oscureció'} a ${a.color} para que los números se lean`)
  const sec = esHex(marca.secundario) ? marca.secundario : b.secundario
  const vars = {
    '--bg': bg, '--bg-top': esHex(marca.fondo) ? mezclar(bg, card, 0.5) : b.bgTop, '--card': card,
    '--tx': tx, '--tx2': mezclar(tx, card, 0.22), '--tx3': legible(mezclar(tx, card, 0.42), card, 4.5).color,
    '--ink': rgbTriplete(tx), '--morado': sec,
    ...(esHex(marca.primario) ? { '--acento': a.color, '--verde': a.color } : {}), // sin color propio, cada plantilla conserva su color de firma
  }
  if (marca.fuenteTexto && FUENTES[marca.fuenteTexto]) vars['--fuente'] = `'${marca.fuenteTexto}', system-ui, sans-serif`
  if (marca.fuenteTitulos && FUENTES[marca.fuenteTitulos]) vars['--fuente-titulos'] = `'${marca.fuenteTitulos}', system-ui, sans-serif`
  return { vars, ajustes }
}

/** Carga (una sola vez) las fuentes de Google que use la marca. */
export function cargarFuentes(marca = {}) {
  for (const f of [marca.fuenteTitulos, marca.fuenteTexto]) {
    if (!f || !FUENTES[f] || typeof document === 'undefined' || document.querySelector(`link[data-fuente="${f}"]`)) continue
    const l = document.createElement('link'); l.rel = 'stylesheet'; l.dataset.fuente = f
    l.href = `https://fonts.googleapis.com/css2?family=${FUENTES[f]}&display=swap`; document.head.appendChild(l)
  }
}

/** Formato del logo (D20): imagen SVG, PNG o WebP (con fondo transparente), máximo 1.5 MB. Devuelve un error legible o null. */
export function revisarLogo(dataUrl) {
  if (typeof dataUrl !== 'string' || !dataUrl.startsWith('data:image/')) return 'no llegó ninguna imagen: pídele a la persona que adjunte su logo en el chat (cámara o pegar).'
  const tipo = dataUrl.slice(5, dataUrl.indexOf(';'))
  if (!['image/svg+xml', 'image/png', 'image/webp'].includes(tipo)) return `el logo llegó como ${tipo.replace('image/', '').toUpperCase()}; pide el logo en SVG o PNG con fondo transparente (un JPG trae fondo blanco y se ve como un recuadro).`
  if (dataUrl.length > 2_000_000) return 'el logo pesa más de 1.5 MB; pide una versión más liviana (PNG de 512 px de ancho alcanza).'
  return null
}
