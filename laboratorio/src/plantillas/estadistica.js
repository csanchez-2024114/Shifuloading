/* Funciones estadísticas puras (sin React, sin DOM, sin API) para los gráficos del CRM.
 * Regla: todo número que se dibuja sale de aquí y se calcula de los registros reales; nada escrito a mano.
 * Convenciones:
 *  - Los valores vacíos (null, undefined, '') y los que no son número finito se IGNORAN en las medidas (no cuentan como 0).
 *  - Las medidas sin datos devuelven null (nunca NaN); quien dibuja muestra '—'.
 *  - Porcentajes y variaciones se devuelven como FRACCIÓN (0.25 = 25 %). `fmtPct` los escribe.
 *  - `percentil(xs, p)` recibe p de 0 a 100 e interpola como PERCENTIL.INC de Excel.
 *  - `desviacion` es muestral (n − 1, como DESVEST.M de Excel) salvo que se pida { muestral: false }. */

/** Paleta de marca (la misma de vistas.jsx; aquí se repite para que este módulo no dependa de React). */
export const COLORES = ['#7c5cff', '#22d3a6', '#f5a623', '#f0587a', '#5b6bff', '#3fb8ff', '#b06cff']
export const MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
export const SIN_DATO = 'Sin dato'

// ── Formato (el mismo del CRM: `Q ${n.toLocaleString('es')}`) ────────────────────────────────────────
/** Escribe un número según el tipo de campo. Redondea a 2 decimales (promedios) y nunca devuelve "NaN". */
export function fmt(tipo, n) {
  if (n === null || n === undefined || n === '' || !Number.isFinite(Number(n))) return '—'
  const r = Math.round(Number(n) * 100) / 100 || 0 // `|| 0` evita "-0"
  return tipo === 'dinero' ? `Q ${r.toLocaleString('es')}` : r.toLocaleString('es')
}
/** Fracción → "12,5 %". Con `signo` antepone + o −. */
export function fmtPct(f, signo = false) {
  if (f === null || f === undefined || !Number.isFinite(f)) return '—'
  const r = Math.round(f * 1000) / 10 || 0
  const s = `${Math.abs(r).toLocaleString('es')} %`
  return signo ? `${r > 0 ? '+' : r < 0 ? '−' : ''}${s}` : (r < 0 ? `−${s}` : s)
}

// ── Básicas ───────────────────────────────────────────────────────────────────────────────────────
/** Convierte a número finito o null. */
export const num = (v) => {
  if (v === null || v === undefined || v === '' || typeof v === 'boolean') return null
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(n) ? n : null
}
/** Solo los números válidos de una lista. */
export const numeros = (xs) => (xs || []).map(num).filter((x) => x !== null)
const ordenados = (xs) => numeros(xs).sort((a, b) => a - b)

/** Cantidad de valores no vacíos (como CONTARA). */
export const conteo = (xs) => (xs || []).filter((v) => v !== null && v !== undefined && v !== '').length
export const suma = (xs) => numeros(xs).reduce((s, x) => s + x, 0)
export const promedio = (xs) => { const v = numeros(xs); return v.length ? suma(v) / v.length : null }
export const mediana = (xs) => percentil(xs, 50)
export const minimo = (xs) => { const v = numeros(xs); return v.length ? Math.min(...v) : null }
export const maximo = (xs) => { const v = numeros(xs); return v.length ? Math.max(...v) : null }
export const rango = (xs) => { const v = numeros(xs); return v.length ? Math.max(...v) - Math.min(...v) : null }

/** Valor más frecuente (sirve también para texto). Empate: el que apareció primero. */
export function moda(xs) {
  const cuenta = new Map() // Map conserva el orden de primera aparición
  for (const v of xs || []) {
    if (v === null || v === undefined || v === '') continue
    const k = typeof v === 'number' || typeof v === 'string' ? v : String(v)
    cuenta.set(k, (cuenta.get(k) || 0) + 1)
  }
  let mejor = null; let max = 0
  for (const [k, c] of cuenta) if (c > max) { max = c; mejor = k }
  return mejor
}

/** Desviación estándar. Muestral (n−1) por defecto; con menos de 2 valores la muestral es null. */
export function desviacion(xs, { muestral = true } = {}) {
  const v = numeros(xs)
  if (!v.length || (muestral && v.length < 2)) return v.length === 1 && !muestral ? 0 : null
  const m = suma(v) / v.length
  const ss = v.reduce((s, x) => s + (x - m) ** 2, 0)
  return Math.sqrt(ss / (v.length - (muestral ? 1 : 0)))
}

/** Percentil p (0–100) con interpolación lineal inclusiva (PERCENTIL.INC). */
export function percentil(xs, p) {
  const v = ordenados(xs)
  if (!v.length) return null
  const k = Math.min(100, Math.max(0, Number(p) || 0)) / 100
  const pos = (v.length - 1) * k
  const i = Math.floor(pos)
  const f = pos - i
  return i + 1 < v.length ? v[i] + (v[i + 1] - v[i]) * f : v[i]
}

/** Los 5 números de la caja y bigotes. null si no hay datos. */
export function cuartiles(xs) {
  const v = numeros(xs)
  if (!v.length) return null
  return { min: minimo(v), q1: percentil(v, 25), mediana: percentil(v, 50), q3: percentil(v, 75), max: maximo(v), n: v.length }
}

/** Parte de un total como fracción (total 0 → 0). */
export const porcentajeDelTotal = (v, total) => { const a = num(v); const t = num(total); return a === null || !t ? 0 : a / t }
/** Cada valor como fracción de la suma de todos (suma 0 → todos 0). */
export const porcentajes = (xs) => { const t = suma(xs); return (xs || []).map((x) => porcentajeDelTotal(x, t)) }
/** Suma acumulada (los vacíos suman 0). */
export const acumulado = (xs) => { let s = 0; return (xs || []).map((x) => (s += num(x) ?? 0)) }

/** Variación entre periodos como fracción. Anterior 0: si actual también es 0 → 0; si no → null (no hay % posible). */
export function variacion(actual, anterior) {
  const a = num(actual); const b = num(anterior)
  if (a === null || b === null) return null
  if (b === 0) return a === 0 ? 0 : null
  return (a - b) / Math.abs(b)
}
/** Variación de cada periodo contra el anterior (el primero es null). */
export const variaciones = (xs) => (xs || []).map((x, i) => (i === 0 ? null : variacion(x, xs[i - 1])))

/** Media móvil simple: null mientras la ventana no está completa. */
export function mediaMovil(xs, ventana = 3) {
  const n = Math.max(1, Math.floor(ventana))
  return (xs || []).map((_, i) => {
    if (i < n - 1) return null
    const trozo = xs.slice(i - n + 1, i + 1).map(num)
    return trozo.some((x) => x === null) ? null : trozo.reduce((s, x) => s + x, 0) / n
  })
}

/** Recta de mínimos cuadrados y = pendiente·x + intercepto. Sin `xs`, x = 0, 1, 2… Devuelve también r² y `en(x)`. */
export function tendenciaLineal(ys, xs) {
  const pares = (ys || []).map((y, i) => [num(xs ? xs[i] : i), num(y)]).filter(([x, y]) => x !== null && y !== null)
  const n = pares.length
  if (!n) return { pendiente: 0, intercepto: 0, r2: null, n: 0, en: () => 0 }
  const mx = pares.reduce((s, [x]) => s + x, 0) / n
  const my = pares.reduce((s, [, y]) => s + y, 0) / n
  let sxy = 0; let sxx = 0; let syy = 0
  for (const [x, y] of pares) { sxy += (x - mx) * (y - my); sxx += (x - mx) ** 2; syy += (y - my) ** 2 }
  const pendiente = sxx === 0 ? 0 : sxy / sxx
  const intercepto = my - pendiente * mx
  const r2 = sxx === 0 || syy === 0 ? null : (sxy * sxy) / (sxx * syy)
  return { pendiente, intercepto, r2, n, en: (x) => intercepto + pendiente * x }
}

/**
 * Histograma de ancho fijo. bins por defecto: regla de Sturges (1–20). La suma de los conteos es siempre n.
 * Con { bonito: true } el ancho se redondea a 1, 2, 2.5 o 5 × 10^n y los bordes caen en múltiplos de él (0, 1000, 2000…):
 * el número de intervalos puede variar un poco respecto a `bins`. El último intervalo incluye el máximo.
 */
export function histograma(xs, bins, { bonito = false } = {}) {
  const v = numeros(xs)
  if (!v.length) return []
  const min = Math.min(...v); const max = Math.max(...v)
  if (min === max) return [{ desde: min, hasta: max, conteo: v.length }]
  const k = Math.max(1, Math.min(50, Math.floor(bins || Math.min(20, Math.ceil(Math.log2(v.length)) + 1))))
  if (bonito) {
    const crudo = (max - min) / k
    const mag = 10 ** Math.floor(Math.log10(crudo))
    const r = crudo / mag
    const paso = (r <= 1 ? 1 : r <= 2 ? 2 : r <= 2.5 ? 2.5 : r <= 5 ? 5 : 10) * mag
    const ini = Math.floor(min / paso) * paso
    const n = Math.max(1, Math.floor((max - ini) / paso) + 1)
    const out = Array.from({ length: n }, (_, i) => ({ desde: ini + i * paso, hasta: ini + (i + 1) * paso, conteo: 0 }))
    for (const x of v) out[Math.max(0, Math.min(n - 1, Math.floor((x - ini) / paso)))].conteo++
    return out
  }
  const ancho = (max - min) / k
  const out = Array.from({ length: k }, (_, i) => ({ desde: min + i * ancho, hasta: i === k - 1 ? max : min + (i + 1) * ancho, conteo: 0 }))
  for (const x of v) out[Math.min(k - 1, Math.floor((x - min) / ancho))].conteo++
  return out
}

// ── Agrupaciones de registros ({ id, valores }) ──────────────────────────────────────────────────────
const idDe = (campo) => (typeof campo === 'string' ? campo : campo?.id)
const vacio = (v) => v === null || v === undefined || v === ''
export const esFechaIso = (v) => typeof v === 'string' && /^\d{4}-\d{2}-\d{2}/.test(v)
export const isoDia = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
/** 'yyyy-mm-dd' → Date local a medianoche. */
export const deIso = (iso) => { const [a, m, d] = iso.slice(0, 10).split('-').map(Number); return new Date(a, m - 1, d) }

/**
 * Agrupa registros por el valor de un campo.
 * - Campo `estado` (objeto con opciones): un grupo por opción, en el orden de las opciones (también las que tienen 0).
 * - Otro campo: un grupo por valor, del más frecuente al menos (empate: alfabético). `top` junta el resto en «Otros».
 * - Los registros sin valor (o con una opción que no existe) van a «Sin dato», solo si hay alguno: así la suma de los
 *   grupos es SIEMPRE el total de registros.
 * Devuelve [{ clave, etiqueta, indice, registros }] (`indice` = posición de la opción del estado, -1 si no aplica).
 */
export function agrupar(registros, campo, { top } = {}) {
  const id = idDe(campo)
  const regs = registros || []
  const opciones = typeof campo === 'object' && campo?.tipo === 'estado' ? campo.opciones || [] : null
  const sinDato = []
  if (opciones) {
    const grupos = opciones.map((op, i) => ({ clave: op, etiqueta: op, indice: i, registros: [] }))
    const porOp = new Map(grupos.map((g) => [g.clave, g]))
    for (const r of regs) { const g = porOp.get(r.valores?.[id]); if (g) g.registros.push(r); else sinDato.push(r) }
    if (sinDato.length) grupos.push({ clave: SIN_DATO, etiqueta: SIN_DATO, indice: -1, registros: sinDato })
    return grupos
  }
  const mapa = new Map()
  for (const r of regs) {
    const v = r.valores?.[id]
    if (vacio(v)) { sinDato.push(r); continue }
    const k = String(v)
    if (!mapa.has(k)) mapa.set(k, [])
    mapa.get(k).push(r)
  }
  let grupos = [...mapa.entries()].map(([k, rs]) => ({ clave: k, etiqueta: k, indice: -1, registros: rs }))
    .sort((a, b) => b.registros.length - a.registros.length || a.clave.localeCompare(b.clave, 'es'))
  if (top && grupos.length > top) {
    const resto = grupos.slice(top - 1)
    grupos = [...grupos.slice(0, top - 1), { clave: 'Otros', etiqueta: `Otros (${resto.length})`, indice: -1, otros: true, registros: resto.flatMap((g) => g.registros) }]
  }
  if (sinDato.length) grupos.push({ clave: SIN_DATO, etiqueta: SIN_DATO, indice: -1, registros: sinDato })
  return grupos
}

/**
 * Agrupa por mes los últimos `meses` meses que terminan en el mes de `hoy`, en orden cronológico (también los vacíos).
 * Los registros sin fecha o fuera de esa ventana NO entran (la etiqueta del gráfico lo dice: «últimos 12 meses»).
 * Devuelve [{ clave: 'yyyy-mm', etiqueta: 'mar', larga: 'mar 2026', anio, mes, registros }].
 */
export function agruparPorMes(registros, campoFecha, meses = 12, hoy = new Date()) {
  const id = idDe(campoFecha)
  const n = Math.max(1, Math.floor(meses))
  const grupos = Array.from({ length: n }, (_, i) => {
    const d = new Date(hoy.getFullYear(), hoy.getMonth() - (n - 1) + i, 1)
    const clave = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
    return { clave, etiqueta: MESES[d.getMonth()], larga: `${MESES[d.getMonth()]} ${d.getFullYear()}`, anio: d.getFullYear(), mes: d.getMonth(), registros: [] }
  })
  const porClave = new Map(grupos.map((g) => [g.clave, g]))
  for (const r of registros || []) {
    const v = r.valores?.[id]
    if (esFechaIso(v)) porClave.get(v.slice(0, 7))?.registros.push(r)
  }
  return grupos
}

/** Registros por día: Map('yyyy-mm-dd' → registros). */
export function agruparPorDia(registros, campoFecha) {
  const id = idDe(campoFecha)
  const mapa = new Map()
  for (const r of registros || []) {
    const v = r.valores?.[id]
    if (!esFechaIso(v)) continue
    const k = v.slice(0, 10)
    if (!mapa.has(k)) mapa.set(k, [])
    mapa.get(k).push(r)
  }
  return mapa
}

export const FUNCIONES = ['conteo', 'suma', 'promedio', 'mediana', 'minimo', 'maximo', 'moda', 'desviacion']
/** Aplica una función de resumen a los registros de un grupo. `conteo` cuenta registros; las demás usan el campo `medir`. */
export function resumir(registros, medir, funcion = medir ? 'suma' : 'conteo') {
  const regs = registros || []
  if (funcion === 'conteo' || !medir) return regs.length
  const xs = regs.map((r) => r.valores?.[medir])
  switch (funcion) {
    case 'suma': return suma(xs)
    case 'promedio': return promedio(xs)
    case 'mediana': return mediana(xs)
    case 'minimo': return minimo(xs)
    case 'maximo': return maximo(xs)
    case 'moda': return num(moda(numeros(xs)))
    case 'desviacion': return desviacion(xs)
    default: return suma(xs)
  }
}

/**
 * Serie lista para dibujar: [{ etiqueta, valor, color, clave, n, registros, larga? }].
 * - agrupar: id de un campo (estado o texto) o 'mes' (usa `fecha`, o el primer campo fecha de `campos`).
 * - medir: id de un campo numero/dinero o null; funcion: conteo | suma | promedio | mediana | minimo | maximo | moda | desviacion.
 * - color: por estado = COLORES[índice de la opción]; por texto = COLORES[posición]; por mes = COLORES[0].
 * `valor` nunca es NaN: un grupo sin datos para la función vale 0 y su `n` dice cuántos registros tenía.
 */
export function serie(registros, { agrupar: por, medir = null, funcion, campos = [], fecha, meses = 12, hoy = new Date(), top } = {}) {
  const f = funcion || (medir ? 'suma' : 'conteo')
  let grupos
  if (por === 'mes') {
    const cf = fecha || campos.find((c) => c.tipo === 'fecha')?.id
    if (!cf) return []
    grupos = agruparPorMes(registros, cf, meses, hoy)
  } else {
    const campo = campos.find((c) => c.id === por) || por
    if (!campo) return []
    grupos = agrupar(registros, campo, { top })
  }
  return grupos.map((g, i) => ({
    etiqueta: g.etiqueta,
    larga: g.larga || g.etiqueta,
    clave: g.clave,
    valor: resumir(g.registros, medir, f) ?? 0,
    n: g.registros.length,
    color: por === 'mes' ? COLORES[0] : g.indice >= 0 ? COLORES[g.indice % COLORES.length] : g.clave === SIN_DATO ? null : COLORES[i % COLORES.length],
    registros: g.registros,
  }))
}

// ── Montos compactos ────────────────────────────────────────────────────────────────────────────────
/** Versión corta para espacios chicos: 'Q 241,8 mil', 'Q 1,2 M', '12,5 mil'. Menos de 10 000 se escribe completo (fmt). */
export function fmtCorto(tipo, n) {
  if (n === null || n === undefined || n === '' || !Number.isFinite(Number(n))) return '—'
  const v = Number(n)
  const a = Math.abs(v)
  if (a < 1e4) return fmt(tipo, v)
  const r1 = (x) => Math.round(x * 10) / 10 || 0
  const s = a >= 1e6 || r1(a / 1e3) >= 1000 ? `${r1(v / 1e6).toLocaleString('es')} M` : `${r1(v / 1e3).toLocaleString('es')} mil`
  return tipo === 'dinero' ? `Q ${s}` : s
}

/** Reparte 100 casillas según los valores (método del mayor residuo): la suma es SIEMPRE 100 si hay algo que repartir. */
export function repartir100(xs, total = 100) {
  const v = (xs || []).map((x) => Math.max(0, num(x) ?? 0))
  const s = v.reduce((a, b) => a + b, 0)
  if (!s) return v.map(() => 0)
  const crudo = v.map((x) => (x / s) * total)
  const base = crudo.map(Math.floor)
  let falta = total - base.reduce((a, b) => a + b, 0)
  const orden = crudo.map((c, i) => [c - base[i], i]).sort((a, b) => b[0] - a[0] || a[1] - b[1])
  for (let k = 0; falta > 0 && k < orden.length; k++, falta--) base[orden[k][1]]++
  return base
}

// ── Colores: mezcla y contraste (WCAG 2.x) ───────────────────────────────────────────────────────────
export const TEXTO_OSCURO = '#14211d'
export const TEXTO_CLARO = '#ffffff'
/** '#rgb' | '#rrggbb' | 'rgb(a)(r, g, b[, a])' → [r, g, b, a] (0–255, a 0–1) o null. */
export function aRgba(c) {
  const s = String(c || '').trim()
  let m = s.match(/^#([0-9a-f]{3,8})$/i)
  if (m) {
    let h = m[1]
    if (h.length === 3 || h.length === 4) h = h.split('').map((x) => x + x).join('')
    if (h.length !== 6 && h.length !== 8) return null
    return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16), h.length === 8 ? parseInt(h.slice(6, 8), 16) / 255 : 1]
  }
  m = s.match(/^rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)(?:[\s,/]+([\d.]+%?))?\s*\)$/i)
  if (m) { const a = m[4] === undefined ? 1 : m[4].endsWith('%') ? parseFloat(m[4]) / 100 : parseFloat(m[4]); return [+m[1], +m[2], +m[3], a] }
  return null
}
export const aHex = ([r, g, b]) => `#${[r, g, b].map((x) => Math.round(Math.max(0, Math.min(255, x))).toString(16).padStart(2, '0')).join('')}`
/** Mezcla `k` de `a` con (1 − k) de `b` (como color-mix in srgb). Devuelve '#rrggbb'. */
export function mezclar(a, b, k) {
  const x = aRgba(a); const y = aRgba(b)
  if (!x || !y) return a
  return aHex([0, 1, 2].map((i) => x[i] * k + y[i] * (1 - k)))
}
/** Luminancia relativa WCAG (0 negro – 1 blanco). */
export function luminancia(c) {
  const x = aRgba(c)
  if (!x) return 0
  const [r, g, b] = x.slice(0, 3).map((v) => { const s = v / 255; return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4 })
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}
/** Razón de contraste WCAG entre dos colores (1–21). */
export function contraste(a, b) {
  const la = luminancia(a); const lb = luminancia(b)
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05)
}
/** El texto (oscuro de marca o blanco) con más contraste sobre `fondo`, y cuánto contraste da. */
export function textoSobre(fondo) {
  const o = contraste(TEXTO_OSCURO, fondo); const c = contraste(TEXTO_CLARO, fondo)
  return o >= c ? { color: TEXTO_OSCURO, contraste: o } : { color: TEXTO_CLARO, contraste: c }
}
/**
 * Relleno suavizado: `k` del color con la superficie. Si con ese relleno ningún texto (oscuro o blanco) llega a `minimo`
 * de contraste, se acerca un poco más a la superficie hasta lograrlo (sin inventar colores: misma paleta, más suave).
 */
export function suavizar(color, superficie, k, minimo = 4.6) {
  let kk = k
  let f = mezclar(color, superficie, kk)
  while (textoSobre(f).contraste < minimo && kk > 0.3) { kk -= 0.04; f = mezclar(color, superficie, kk) }
  return f
}

// ── Periodos comparables ────────────────────────────────────────────────────────────────────────────
/**
 * Mes en curso contra el mes anterior SIN comparar un mes incompleto contra uno completo:
 * días 1…N del mes en curso (N = día de hoy) contra días 1…N del mes anterior (si el anterior es más corto, hasta su último día).
 */
export function tramosComparables(hoy = new Date()) {
  const a = hoy.getFullYear(); const m = hoy.getMonth(); const d = hoy.getDate()
  const ultimoAnt = new Date(a, m, 0).getDate()
  const dAnt = Math.min(d, ultimoAnt)
  const ant = new Date(a, m - 1, 1)
  const tramo = (ini, fin) => ({ desde: isoDia(ini), hasta: isoDia(fin), etiqueta: `${ini.getDate() === fin.getDate() ? '' : `${ini.getDate()}–`}${fin.getDate()} ${MESES[fin.getMonth()]}`, mes: MESES[fin.getMonth()], larga: `${MESES[fin.getMonth()]} ${fin.getFullYear()}` })
  return { dias: d, actual: tramo(new Date(a, m, 1), new Date(a, m, d)), anterior: tramo(ant, new Date(a, m - 1, dAnt)) }
}
/** Registros cuya fecha (yyyy-mm-dd) cae entre `desde` y `hasta` (incluidos, en texto iso). */
export function registrosEntre(registros, campoFecha, desde, hasta) {
  const id = idDe(campoFecha)
  return (registros || []).filter((r) => { const v = r.valores?.[id]; if (!esFechaIso(v)) return false; const k = v.slice(0, 10); return k >= desde && k <= hasta })
}

/** Registros por día de la semana (0 = lunes … 6 = domingo) y hora entera (campo 'HH:MM'). Devuelve Map('d-h' → registros). */
export function agruparPorDiaHora(registros, campoFecha, campoHora) {
  const idf = idDe(campoFecha); const idh = idDe(campoHora)
  const mapa = new Map()
  for (const r of registros || []) {
    const f = r.valores?.[idf]; const h = String(r.valores?.[idh] ?? '')
    const m = h.match(/^(\d{1,2}):?(\d{2})?/)
    if (!esFechaIso(f) || !m) continue
    const hora = Number(m[1])
    if (!(hora >= 0 && hora <= 23)) continue
    const k = `${(deIso(f).getDay() + 6) % 7}-${hora}`
    if (!mapa.has(k)) mapa.set(k, [])
    mapa.get(k).push(r)
  }
  return mapa
}
