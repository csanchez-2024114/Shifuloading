/* Piezas de dibujo compartidas por el catálogo de gráficos (graficos.jsx y graficos-nuevos.jsx).
 *  - Medición de texto REAL (canvas con la fuente del CRM; sin DOM, una estimación conservadora).
 *  - Pintura: superficie, acento y gris leídos del DOM → rellenos suavizados y color de texto por contraste medido (WCAG).
 *  - Colisiones: cajas de texto y aceptación por prioridad (lo que choca o no cabe NO se dibuja: queda en leyenda/tooltip).
 *  - Ejes, rejilla, leyendas, sectores circulares, número que cuenta y orden de animación por variante. */
import { createContext, useContext, useEffect, useState } from 'react'
import { AnimarContext, VelContext } from './vistas'
import * as E from './estadistica'

const { fmt, fmtCorto } = E
export const sinMovimiento = () => typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

// ── Texto ─────────────────────────────────────────────────────────────────────────────────────────
let familia = 'Inter, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'
let ctxTexto = null
const anchos = new Map()
/** Fija la familia real (la que resolvió el navegador para var(--fuente)) y olvida las medidas anteriores. */
export function fijarFuente(f) { if (f && f !== familia) { familia = f; anchos.clear() } }
export const olvidarAnchos = () => anchos.clear()
/** Ancho en px de un texto. Etiquetas: 11 px / 500. Valores: 12 px / 600 (anchoVal). */
export function anchoTexto(s, px = 11, peso = 500) {
  const t = String(s ?? '')
  if (!t) return 0
  if (typeof document === 'undefined') return t.length * px * (peso >= 600 ? 0.66 : 0.62) // sin DOM: estimación holgada
  const k = `${peso}|${px}|${t}`
  let w = anchos.get(k)
  if (w === undefined) {
    ctxTexto ||= document.createElement('canvas').getContext('2d')
    ctxTexto.font = `${peso} ${px}px ${familia}`
    // Los valores usan cifras tabulares (todas del ancho del «0»): se miden así para no quedarse cortos.
    // Medido en Chrome: con cifras como «0» la estimación de números/porcentajes es exacta (41,98 vs 41,80 px); los textos
    // con letras llegan a 1,016 × la estimación, así que solo ellos llevan holgura.
    const soloCifras = /^[\d\s.,%+\-−·]*$/.test(t)
    w = ctxTexto.measureText(t.replace(/\d/g, '0')).width * (soloCifras ? 1 : 1.02) + 0.5
    anchos.set(k, w)
  }
  return w
}
export const anchoVal = (s) => anchoTexto(s, 12, 600)
/** Alto de la caja de un texto (Inter: ascendente + descendente ≈ 1,21 em). */
export const altoTexto = (px = 11) => px * 1.22
/** Corta un texto al ancho `max` (por palabra si se puede) con «…». Si quedaría casi nada, devuelve ''. */
export function cortar(s, max, px = 11, peso = 500) {
  const t = String(s ?? '')
  if (anchoTexto(t, px, peso) <= max + 0.5) return t
  if (max < px * 2.2) return ''
  let n = t.length - 1
  while (n > 1 && anchoTexto(`${t.slice(0, n).trimEnd()}…`, px, peso) > max) n--
  let r = t.slice(0, n)
  const esp = r.lastIndexOf(' ')
  if (esp >= Math.max(3, n * 0.55)) r = r.slice(0, esp) // corta en la palabra si no pierde demasiado
  r = r.trimEnd()
  return r.length >= 2 ? `${r}…` : ''
}
/** Caja de un texto SVG. `medio` = centrado vertical con dy="0.35em"; si no, `y` es la línea base. */
export function cajaTexto(x, y, w, ancla = 'start', px = 11, medio = true) {
  const x0 = ancla === 'middle' ? x - w / 2 : ancla === 'end' ? x - w : x
  const h = altoTexto(px)
  return { x: x0, y: medio ? y - h / 2 : y - px * 0.97, w, h }
}
export const choca = (a, b, m = 1) => a.x < b.x + b.w + m && b.x < a.x + a.w + m && a.y < b.y + b.h + m && b.y < a.y + a.h + m
export const cabeEn = (a, lim, m = 0) => a.x >= lim.x + m - 0.01 && a.y >= lim.y + m - 0.01 && a.x + a.w <= lim.x + lim.w - m + 0.01 && a.y + a.h <= lim.y + lim.h - m + 0.01
/**
 * Acepta etiquetas por prioridad (mayor primero): descarta las que salen de `lim`, chocan con una ya aceptada o con
 * un obstáculo. cands = [{ id, caja, prio }]. Devuelve el Set de ids aceptados.
 */
export function sinChoques(cands, lim, obst = [], margen = 1.5) {
  const ok = []
  for (const c of [...cands].sort((a, b) => (b.prio ?? 0) - (a.prio ?? 0))) {
    if (lim && !cabeEn(c.caja, lim)) continue
    if (obst.some((o) => choca(c.caja, o, margen)) || ok.some((o) => choca(c.caja, o.caja, margen))) continue
    ok.push(c)
  }
  return new Set(ok.map((c) => c.id))
}

// ── Pintura (colores reales según el tema) ────────────────────────────────────────────────────────
export const PinturaContext = createContext(null)
/** Variante de animación de este montaje (0, 1 o 2): cambia el ORDEN en que se arman las marcas. */
export const VarianteContext = createContext(0)

export function crearPintura({ sup = '#0c1211', acento = '#7c5cff', gris = '#98a0aa', vars = {} } = {}) {
  const oscuro = E.luminancia(sup) < 0.4
  const k = oscuro ? 0.76 : 0.7 // ~70–80 % del color en oscuro, ~65–75 % en claro
  const cache = new Map()
  const col = (c) => { const s = String(c || ''); return !s ? gris : s.includes('--acento') ? acento : s.includes('--tx3') ? gris : s }
  /** Relleno grande suavizado (misma paleta mezclada con la superficie). `f` lo aclara más (anillos externos, bandas). */
  const relleno = (c, f = 1) => {
    const key = `${c}|${f}`
    if (!cache.has(key)) cache.set(key, E.suavizar(col(c), sup, k * f))
    return cache.get(key)
  }
  /** Texto (oscuro de marca o blanco) con más contraste sobre un relleno. */
  const texto = (fondo) => E.textoSobre(fondo).color
  return { sup, oscuro, acento, gris, col, relleno, texto, k, vars }
}
const PINTURA_DEF = crearPintura()
export const usePintura = () => useContext(PinturaContext) || PINTURA_DEF

/** Cualquier color CSS → '#rrggbb' (vía canvas). '' si no es un color. */
function normalizar(v) {
  const s = String(v || '').trim()
  if (!s || typeof document === 'undefined') return ''
  ctxTexto ||= document.createElement('canvas').getContext('2d')
  ctxTexto.fillStyle = '#010203'; ctxTexto.fillStyle = s; const a = ctxTexto.fillStyle
  ctxTexto.fillStyle = '#030201'; ctxTexto.fillStyle = s; const b = ctxTexto.fillStyle
  if (a !== b) return ''
  const x = E.aRgba(a)
  return x ? E.aHex(x) : ''
}
/** Lee del DOM la superficie REAL bajo el gráfico (compone los fondos semitransparentes de los ancestros), el acento y el gris. */
export function leerPintura(el) {
  if (!el || typeof getComputedStyle === 'undefined') return PINTURA_DEF
  const capas = []
  for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
    const c = E.aRgba(normalizarRgba(getComputedStyle(n).backgroundColor))
    if (c && c[3] > 0.001) { capas.push(c); if (c[3] >= 0.999) break }
  }
  let b = [255, 255, 255]
  for (const c of capas.reverse()) b = [0, 1, 2].map((i) => c[i] * c[3] + b[i] * (1 - c[3]))
  const cs = getComputedStyle(el)
  fijarFuente(cs.fontFamily)
  // Variables del tema para el tooltip (que se dibuja fuera del gráfico, en <body>, para que ninguna tarjeta lo recorte).
  const vars = Object.fromEntries(['--card', '--linea', '--tx', '--tx2', '--tx3', '--sombra', '--ink', '--fuente'].map((k) => [k, cs.getPropertyValue(k).trim()]).filter(([, v]) => v))
  return crearPintura({ vars, sup: E.aHex(b), acento: normalizar(cs.getPropertyValue('--acento')) || '#7c5cff', gris: normalizar(cs.getPropertyValue('--tx3')) || '#98a0aa' })
}
const normalizarRgba = (s) => String(s || '').replace(/^color\(srgb ([\d.]+) ([\d.]+) ([\d.]+)(?: \/ ([\d.]+))?\)$/, (_, r, g, b, a) => `rgba(${r * 255}, ${g * 255}, ${b * 255}, ${a ?? 1})`)

/** Separación entre partes de un total (pastel, dona, rosa, sol, apiladas, barra 100 %): 1 px del color REAL de la
 *  superficie, igual de liviana en claro y en oscuro. */
export const SEPARADOR = 1

// ── Orden de animación ────────────────────────────────────────────────────────────────────────────
/** Índice de demora para la marca i de n según la variante: 0 en orden, 1 desde el centro, 2 al revés. */
export function useOrden() {
  const v = useContext(VarianteContext)
  return (i, n) => (v === 1 ? Math.round(Math.abs(i - (n - 1) / 2)) : v === 2 ? n - 1 - i : i)
}
export const tope = (i, n = 24) => Math.min(i, n) // las demoras escalonadas no crecen sin fin

// ── Escalas y ejes ────────────────────────────────────────────────────────────────────────────────
export const escala = (d0, d1, r0, r1) => { const k = d1 === d0 ? 0 : (r1 - r0) / (d1 - d0); return (v) => r0 + ((Number(v) || 0) - d0) * k }
/** Marcas de eje "bonitas" (1, 2, 2.5, 5 × 10^n) que cubren [min, max]. */
export function ticks(min, max, n = 4, entero = false) {
  const a = Number.isFinite(min) ? min : 0
  let b = Number.isFinite(max) ? max : 0
  if (!(b > a)) b = a + (entero ? Math.max(1, n) : 1)
  const crudo = (b - a) / Math.max(1, n)
  const mag = 10 ** Math.floor(Math.log10(crudo))
  const r = crudo / mag
  let paso = (r <= 1 ? 1 : r <= 2 ? 2 : r <= 2.5 ? 2.5 : r <= 5 ? 5 : 10) * mag
  if (entero) paso = Math.max(1, Math.ceil(paso))
  const ini = Math.floor(a / paso) * paso
  const fin = Math.ceil(b / paso) * paso
  const out = []
  for (let v = ini; v <= fin + paso / 2 && out.length < 12; v += paso) out.push(Number((Math.round(v / paso) * paso).toFixed(10)))
  return out
}
/** Formato de eje: compacto (Q 240 mil). */
export const fEje = (tipo) => (v) => fmtCorto(tipo, v)

/** Área de dibujo cartesiana: márgenes según lo que cabe, escala Y y marcas. */
export function plano(w, h, { min = 0, max = 0, f = (v) => fmt('numero', v), entero = false, etiquetas = true, arriba = 10, der = 10 }) {
  const tk = ticks(min, max, h < 130 ? 2 : h < 230 ? 4 : 5, entero)
  const textos = tk.map(f)
  const necesita = Math.ceil(Math.max(...textos.map((t) => anchoTexto(t)))) + 10
  const conY = w >= 170 && h >= 80 && necesita <= w * 0.4 // si no caben, se ocultan (nunca se recortan)
  const izq = conY ? necesita : 6
  const conX = etiquetas && h >= 64
  const x0 = izq; const x1 = Math.max(x0 + 10, w - der); const y1 = arriba; const y0 = Math.max(y1 + 10, h - (conX ? 20 : 8))
  return { w, h, der, x0, x1, y0, y1, y: escala(tk[0], tk[tk.length - 1], y0, y1), tk, textos, conY, conX, ancho: x1 - x0, alto: y0 - y1 }
}

export function Rejilla({ p }) {
  return (
    <g className="gr-rejilla" aria-hidden="true">
      {p.tk.map((v, i) => (
        <g key={i}>
          <line x1={p.x0} x2={p.x1} y1={p.y(v)} y2={p.y(v)} className={v === 0 ? 'gr-cero' : undefined} />
          {p.conY && <text x={p.x0 - 6} y={p.y(v)} dy="0.35em" textAnchor="end">{p.textos[i]}</text>}
        </g>
      ))}
    </g>
  )
}

/** Etiquetas del eje X: se saltan las que no caben; el último (lo más reciente) siempre se ve. Nunca se enciman. */
export function EjeX({ p, items }) {
  if (!p.conX || !items.length) return null
  const banda = p.ancho / items.length
  const maxW = Math.max(...items.map((it) => anchoTexto(it.t)))
  const paso = Math.max(1, Math.ceil((maxW + 8) / banda))
  const puestas = []
  let limite = p.w - 1
  for (let i = items.length - 1; i >= 0; i--) {
    if ((items.length - 1 - i) % paso) continue
    const t = cortar(items[i].t, Math.max(banda * paso - 6, 0))
    if (!t) continue
    const a = anchoTexto(t)
    // Nunca invade la columna de números del eje Y (izquierda) ni la de un eje derecho.
    const minX = p.conY ? p.x0 - 2 : 1
    const maxX = (p.der > 10 ? p.x1 + 2 : p.w - 1) - a
    if (maxX < minX) continue
    const x0 = Math.max(minX, Math.min(maxX, items[i].x - a / 2))
    if (x0 + a > limite - 4) continue
    puestas.push({ i, t, x0, a })
    limite = x0
  }
  return (
    <g className="gr-ejex" aria-hidden="true">
      {puestas.map(({ i, t, x0 }) => <text key={i} x={x0} y={p.y0 + 14}>{t}</text>)}
    </g>
  )
}

// ── Leyenda ───────────────────────────────────────────────────────────────────────────────────────
/** Ancho de la muestra de color, o de la placa con el número de referencia (it.ref). */
const anchoMuestra = (it) => (it.ref ? anchoPlaca(it.ref) + 5 : 14)
const anchoItem = (it) => anchoMuestra(it) + anchoTexto(it.nombre) + (it.valor ? anchoVal(it.valor) + 8 : 0) + 12
/** Cuántas filas ocupa una leyenda que fluye a lo ancho `w`. */
export function filasAbajo(w, items) {
  let filas = 1; let x = 0
  for (const it of items) { const a = Math.min(anchoItem(it), w); if (x > 0 && x + a > w) { filas++; x = 0 } x += a }
  return filas
}
/** Decide dónde va la leyenda según el tamaño: a la derecha, abajo o ninguna. */
export function planLeyenda(w, h, items) {
  if (!items.length) return { lado: null, ancho: 0, alto: 0 }
  if (w >= 330 && w >= h * 1.25) {
    const ancho = Math.min(200, Math.max(110, w * 0.4), Math.max(...items.map(anchoItem)))
    return { lado: 'der', ancho, alto: 0 }
  }
  if (h >= 170 && w >= 180) {
    const filas = filasAbajo(w, items)
    if (filas <= 3) return { lado: 'abajo', ancho: 0, alto: filas * 18 + 6 }
  }
  return { lado: null, ancho: 0, alto: 0 }
}
/** Recorta el área de dibujo según la leyenda. */
export const areaCon = (plan, w, h) => ({ w: plan.lado === 'der' ? Math.max(40, w - plan.ancho - 10) : w, h: plan.lado === 'abajo' ? Math.max(30, h - plan.alto) : h })

function Muestra({ it, pin }) {
  if (it.ref) return <Placa n={it.ref} x={anchoPlaca(it.ref) / 2} y={0} fondo={pin.relleno(it.color)} id={it.refId} pin={pin} />
  return <rect x="0" y="-5" width="10" height="10" rx="3" style={it.raya ? { fill: 'none', stroke: pin.col(it.color), strokeWidth: 2, strokeDasharray: '3 2' } : { fill: it.suave ? pin.relleno(it.color) : pin.col(it.color), stroke: pin.col(it.color), strokeWidth: it.suave ? 1 : 0 }} />
}
export function Leyenda({ plan, items, w, h, ix }) {
  const pin = usePintura()
  if (!plan.lado) return null
  if (plan.lado === 'der') {
    const caben = Math.max(1, Math.floor((h - 8) / 18))
    const ver = items.length > caben ? items.slice(0, caben - 1) : items
    const y0 = Math.max(4, (h - (ver.length + (items.length > caben ? 1 : 0)) * 18) / 2) + 9
    const x = w - plan.ancho
    return (
      <g className="gr-ley">
        {ver.map((it, i) => {
          const vw = it.valor ? anchoVal(it.valor) + 6 : 0
          const nom = cortar(it.nombre, plan.ancho - anchoMuestra(it) - 8 - vw)
          return (
            <g key={it.id} transform={`translate(${x},${y0 + i * 18})`} className={`gr-ley-it${ix.c(it.id)}`} style={{ '--i': tope(i) }} {...ix.p(it.id, it.nombre, it.filas || [])}>
              <Muestra it={it} pin={pin} />
              {nom && <text x={anchoMuestra(it) + 2} dy="0.35em">{nom}</text>}
              {it.valor && <text x={plan.ancho - 2} dy="0.35em" textAnchor="end" className="gr-ley-v">{it.valor}</text>}
            </g>
          )
        })}
        {items.length > caben && <text x={x + 16} y={y0 + ver.length * 18} dy="0.35em" className="gr-ley-mas">+{items.length - ver.length} más</text>}
      </g>
    )
  }
  // Abajo: en filas que fluyen.
  let x = 0; let fila = 0
  const pos = items.map((it) => {
    const a = Math.min(anchoItem(it), w)
    if (x > 0 && x + a > w) { fila++; x = 0 }
    const p = { x, y: h - plan.alto + 12 + fila * 18, a }
    x += a
    return p
  })
  return (
    <g className="gr-ley">
      {items.map((it, i) => {
        const vw = it.valor ? anchoVal(it.valor) + 5 : 0
        const nom = cortar(it.nombre, pos[i].a - anchoMuestra(it) - 12 - vw)
        return (
          <g key={it.id} transform={`translate(${pos[i].x},${pos[i].y})`} className={`gr-ley-it${ix.c(it.id)}`} style={{ '--i': tope(i) }} {...ix.p(it.id, it.nombre, it.filas || [])}>
            <Muestra it={it} pin={pin} />
            <text x={anchoMuestra(it) + 1} dy="0.35em">{nom}{it.valor && <tspan className="gr-ley-v" dx={nom ? 5 : 0}>{it.valor}</tspan>}</text>
          </g>
        )
      })}
    </g>
  )
}

/** Resaltado por serie (al pasar por la leyenda, cuyos ids empiezan por «s:»). */
export const porSerie = (ix) => typeof ix.activo === 'string' && ix.activo.startsWith('s:')
export const claseSerie = (ix, id) => (porSerie(ix) ? (ix.activo === id ? ' gr-on' : ' gr-off') : '')

// ── Formas ────────────────────────────────────────────────────────────────────────────────────────
/** Ángulo 0 = las 12 en punto, sentido horario (radianes). */
export const punto = (cx, cy, r, a) => [cx + r * Math.sin(a), cy - r * Math.cos(a)]
/** Sector circular (r0 = 0 → gajo de pastel; r0 > 0 → tramo de anillo). */
export function sector(cx, cy, r0, r1, a0, a1) {
  const f = (n) => n.toFixed(2)
  if (a1 - a0 >= 2 * Math.PI - 1e-6) {
    const anillo = `M${f(cx)},${f(cy - r1)} A${f(r1)},${f(r1)} 0 1 1 ${f(cx)},${f(cy + r1)} A${f(r1)},${f(r1)} 0 1 1 ${f(cx)},${f(cy - r1)} Z`
    return r0 > 0 ? `${anillo} M${f(cx)},${f(cy - r0)} A${f(r0)},${f(r0)} 0 1 0 ${f(cx)},${f(cy + r0)} A${f(r0)},${f(r0)} 0 1 0 ${f(cx)},${f(cy - r0)} Z` : anillo
  }
  const grande = a1 - a0 > Math.PI ? 1 : 0
  const [x1, y1] = punto(cx, cy, r1, a0); const [x2, y2] = punto(cx, cy, r1, a1)
  if (r0 <= 0) return `M${f(cx)},${f(cy)} L${f(x1)},${f(y1)} A${f(r1)},${f(r1)} 0 ${grande} 1 ${f(x2)},${f(y2)} Z`
  const [x3, y3] = punto(cx, cy, r0, a1); const [x4, y4] = punto(cx, cy, r0, a0)
  return `M${f(x1)},${f(y1)} A${f(r1)},${f(r1)} 0 ${grande} 1 ${f(x2)},${f(y2)} L${f(x3)},${f(y3)} A${f(r0)},${f(r0)} 0 ${grande} 0 ${f(x4)},${f(y4)} Z`
}
/** ¿La caja cabe entera dentro del sector (con margen)? Se prueban sus 4 esquinas y su centro. */
export function cajaEnSector(caja, cx, cy, r0, r1, a0, a1, m = 2) {
  const total = a1 - a0 >= 2 * Math.PI - 1e-6
  const esq = [[caja.x, caja.y], [caja.x + caja.w, caja.y], [caja.x, caja.y + caja.h], [caja.x + caja.w, caja.y + caja.h], [caja.x + caja.w / 2, caja.y + caja.h / 2]]
  return esq.every(([x, y]) => {
    const dx = x - cx; const dy = y - cy
    const r = Math.hypot(dx, dy)
    if (r > r1 - m || r < r0 + m) return false
    if (total) return true
    const dos = 2 * Math.PI
    const rel = (((Math.atan2(dx, -dy) - a0) % dos) + dos) % dos // ángulo relativo al inicio del sector (sirve con ángulos negativos)
    const marg = r > 0 ? m / r : 0
    return rel >= marg && rel <= a1 - a0 - marg
  })
}

/**
 * Etiquetas de % para partes circulares: dentro si la caja cabe en el gajo; si no (y se pide `fuera`), afuera con línea guía,
 * sin chocar entre sí ni con el círculo ni salir del área. Lo que no cabe en ningún lado queda en la leyenda/tooltip.
 */
export function etiquetasCirculo({ partes, cx, cy, r0, R, a, fuera }) {
  const res = partes.map((pt) => {
    const t = E.fmtPct(pt.f)
    const am = (pt.a0 + pt.a1) / 2
    const aw = anchoVal(t)
    // Se prueban varios radios (el gajo es más ancho hacia afuera); el primero donde la caja cabe entera gana.
    const radios = r0 > 0 ? [(r0 + R) / 2] : [0.62, 0.7, 0.55, 0.76].map((k) => R * k)
    for (const rr of radios) {
      const [x, y] = punto(cx, cy, rr, am)
      const caja = cajaTexto(x, y, aw, 'middle', 12)
      if (R >= 26 && cajaEnSector(caja, cx, cy, r0, R, pt.a0, pt.a1, 3)) return { ...pt, t, am, x, y, caja, modo: 'dentro' }
    }
    const [x, y] = punto(cx, cy, radios[0], am)
    return { ...pt, t, am, x, y, caja: cajaTexto(x, y, aw, 'middle', 12), modo: null }
  })
  if (fuera) {
    const lim = { x: 0, y: 0, w: a.w, h: a.h }
    const puestas = res.filter((e) => e.modo === 'dentro').map((e) => e.caja)
    const lejos = (c) => { const nx = Math.max(c.x, Math.min(cx, c.x + c.w)); const ny = Math.max(c.y, Math.min(cy, c.y + c.h)); return Math.hypot(nx - cx, ny - cy) > R + 3 }
    for (const e of [...res].filter((x) => !x.modo).sort((p, q) => q.f - p.f)) {
      const der = Math.sin(e.am) >= 0
      const [ex, ey] = punto(cx, cy, R + 10, e.am)
      const aw = anchoVal(e.t)
      for (const dy of [0, 8, -8, 15, -15]) {
        const ty = ey + dy
        const tx = ex + (der ? 8 : -8)
        const caja = cajaTexto(tx, ty, aw, der ? 'start' : 'end', 12)
        if (!cabeEn(caja, lim, 1) || !lejos(caja) || puestas.some((o) => choca(o, caja, 2))) continue
        puestas.push(caja)
        Object.assign(e, { modo: 'fuera', tx, ty, ex, ey, der, caja })
        break
      }
    }
  }
  return res
}

/** Niveles de intensidad: el acento mezclado con la superficie (nada saturado a tope). */
export const nivelesCalor = (pin) => [0, 0.26, 0.46, 0.66, 0.86].map((k) => (k ? E.mezclar(pin.acento, pin.sup, k) : null))

// ── Texto rotado y placas de referencia ───────────────────────────────────────────────────────────
/** Esquinas de la caja de un texto centrado en (x, y) y girado `grados` (sentido horario, como transform rotate). */
export function esquinasGiradas(x, y, w, h, grados) {
  const a = (grados * Math.PI) / 180; const c = Math.cos(a); const s = Math.sin(a)
  return [[-w / 2, -h / 2], [w / 2, -h / 2], [w / 2, h / 2], [-w / 2, h / 2]].map(([u, v]) => [x + u * c - v * s, y + u * s + v * c])
}
/** ¿Todos los puntos caen dentro del tramo de anillo (con margen)? */
export function puntosEnSector(pts, cx, cy, r0, r1, a0, a1, m = 2) {
  const dos = 2 * Math.PI
  return pts.every(([x, y]) => {
    const dx = x - cx; const dy = y - cy; const r = Math.hypot(dx, dy)
    if (r > r1 - m || r < r0 + m) return false
    if (a1 - a0 >= dos - 1e-6) return true
    const rel = (((Math.atan2(dx, -dy) - a0) % dos) + dos) % dos
    const marg = r > 0 ? m / r : 0
    return rel >= marg && rel <= a1 - a0 - marg
  })
}
/**
 * Parte un nombre en hasta `lineas` renglones de ancho `max`, por palabras. Una palabra que no cabe sola se corta con «…».
 * Si el nombre entero no cabe, el último renglón termina en «…» — pero SOLO si quedan al menos 6 caracteres visibles
 * del nombre (si no, devuelve null). Devuelve { lineas: [...], completo } o null. Nunca corta una palabra sin «…».
 */
export function partirNombre(nombre, max, lineas = 2, px = 11, peso = 500) {
  const palabras = String(nombre ?? '').trim().split(/\s+/).filter(Boolean)
  if (!palabras.length || max < px) return null
  const cabe = (t) => anchoTexto(t, px, peso) <= max
  const out = []
  let i = 0
  while (i < palabras.length && out.length < lineas) {
    let linea = palabras[i]
    if (!cabe(linea)) break // la palabra sola no cabe: se resuelve abajo con «…»
    i++
    while (i < palabras.length && cabe(`${linea} ${palabras[i]}`)) linea += ` ${palabras[i++]}`
    out.push(linea)
  }
  if (i >= palabras.length) return { lineas: out, completo: true }
  // No cupo todo: el último renglón disponible termina en «…».
  const resto = palabras.slice(out.length < lineas ? i : i - (out[out.length - 1] || '').split(' ').length).join(' ')
  const previas = out.length < lineas ? out : out.slice(0, -1)
  let n = resto.length
  let ult = ''
  while (n > 0) { const t = `${resto.slice(0, n).trimEnd()}…`; if (cabe(t)) { ult = t; break } n-- }
  if (!ult) return null
  const visibles = previas.join(' ').replace(/\s/g, '').length + ult.slice(0, -1).replace(/\s/g, '').length
  if (visibles < 6) return null
  return { lineas: [...previas, ult], completo: false }
}

/**
 * Etiqueta para un tramo de anillo: prueba cada opción de texto primero horizontal (centrada en el radio medio) y luego
 * RADIAL (girada a lo largo del radio, sin quedar de cabeza). opciones = [{ nombre, valor }] (nombre 11 px, valor 12 px).
 * Devuelve { x, y, giro, nombre, valor } o null (no cabe nada: queda el tooltip).
 */
export function rotularSector({ cx, cy, r0, r1, a0, a1, opciones, m = 2.5 }) {
  const am = (a0 + a1) / 2; const rm = (r0 + r1) / 2
  const [x, y] = punto(cx, cy, rm, am)
  const grados = (am * 180) / Math.PI
  const giro = grados > 180 ? grados + 90 - 360 : grados - 90 // a lo largo del radio, siempre legible
  const ancho = (o) => (o.nombre ? anchoTexto(`${o.nombre}${o.valor ? ' · ' : ''}`) : 0) + (o.valor ? anchoVal(o.valor) : 0)
  for (const g of [0, giro]) {
    for (const o of opciones) {
      if (!o) continue
      const pts = esquinasGiradas(x, y, ancho(o), altoTexto(o.valor ? 12 : 11), g)
      if (puntosEnSector([...pts, [x, y]], cx, cy, r0, r1, a0, a1, m)) return { x, y, giro: g, ...o }
    }
  }
  return null
}

/** Placa con un número de referencia (se repite en la leyenda). 17 px de alto; el número va en 11 px/600. */
export const anchoPlaca = (n) => Math.max(17, anchoTexto(String(n), 11, 600) + 8)
export const ALTO_PLACA = 17
export function Placa({ n, x, y, fondo, id, pin }) {
  const w = anchoPlaca(n)
  const placa = pin.texto(fondo) // la placa toma el color de texto de más contraste; el número, el del relleno
  return (
    <g className="gr-placa" pointerEvents="none">
      <rect id={id} className="gr-forma-placa" x={x - w / 2} y={y - ALTO_PLACA / 2} width={w} height={ALTO_PLACA} rx="5" style={{ fill: placa }} />
      <text className="gr-chico gr-dentro" data-forma={id} x={x} y={y} dy="0.35em" textAnchor="middle" style={{ fill: fondo }}>{n}</text>
    </g>
  )
}

// ── Otros ─────────────────────────────────────────────────────────────────────────────────────────
/** Número que sube desde 0 hasta su valor (solo en estilos animados). El valor final es el exacto. */
export function Cuenta({ v, f }) {
  const animar = useContext(AnimarContext) && !sinMovimiento()
  const vel = useContext(VelContext)
  const [n, setN] = useState(animar && Number.isFinite(v) ? 0 : v)
  useEffect(() => {
    if (!animar || !Number.isFinite(v)) { setN(v); return undefined }
    let raf; const t0 = performance.now(); const dur = 1300 * vel
    const paso = (t) => { const k = Math.min(1, (t - t0) / dur); setN(k >= 1 ? v : v * (1 - (1 - k) ** 3)); if (k < 1) raf = requestAnimationFrame(paso) }
    raf = requestAnimationFrame(paso)
    return () => cancelAnimationFrame(raf)
  }, [v, animar, vel])
  return f(n)
}

export const Svg = ({ w, h, aria, children, className = '' }) => (
  <svg className={`gr-svg ${className}`} width={w} height={h} viewBox={`0 0 ${w} ${h}`} role="img" aria-label={aria}>{children}</svg>
)
