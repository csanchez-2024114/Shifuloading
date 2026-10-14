/* Cálculos compartidos del catálogo de gráficos (puros: registros → lo que se dibuja). Sin React ni DOM.
 * Devuelven un objeto para dibujar o un TEXTO (= estado vacío que se muestra tal cual). */
import * as E from './estadistica'

const { COLORES, fmt } = E
export const ACENTO = 'var(--acento, #7c5cff)'
export const GRIS = 'var(--tx3)'
export const sumaDe = (xs) => xs.reduce((s, x) => s + (Number(x) || 0), 0)
export const fechaCorta = (d) => `${d.getDate()} ${E.MESES[d.getMonth()]}`
export const fechaLarga = (d) => `${['dom', 'lun', 'mar', 'mié', 'jue', 'vie', 'sáb'][d.getDay()]} ${d.getDate()} ${E.MESES[d.getMonth()]} ${d.getFullYear()}`

// ── Campos y opciones ─────────────────────────────────────────────────────────────────────────────
/** Clases de campo que puede pedir un gráfico en `requiere`. */
export const CLASES = {
  estado: (c) => c.tipo === 'estado',
  estado3: (c) => c.tipo === 'estado' && (c.opciones?.length || 0) >= 3, // estado con 3 o más opciones (radar)
  fecha: (c) => c.tipo === 'fecha',
  hora: (c) => c.tipo === 'hora',
  medida: (c) => c.tipo === 'numero' || c.tipo === 'dinero',
  texto: (c) => c.tipo === 'texto',
  categoria: (c) => c.tipo === 'estado' || c.tipo === 'texto',
}
/** `requiere` es un objeto { clase: cantidad } o una lista de alternativas (basta con cumplir una). */
export const cumple = (requiere, campos) => [].concat(requiere).some((alt) => Object.entries(alt).every(([cl, n]) => campos.filter(CLASES[cl] || (() => false)).length >= n))

/** Campos que se eligen solos: el primer estado, la primera (y segunda) fecha, la primera hora, la primera medida
 *  (dinero antes que número) y el primer texto. */
export function base(campos) {
  const de = (cl) => campos.filter(CLASES[cl])
  const medidas = [...campos.filter((c) => c.tipo === 'dinero'), ...campos.filter((c) => c.tipo === 'numero')]
  const estado = de('estado')[0]?.id
  const texto = de('texto')[0]?.id
  return { estado, fecha: de('fecha')[0]?.id, fecha2: de('fecha')[1]?.id, hora: de('hora')[0]?.id, valor: medidas[0]?.id, valor2: medidas[1]?.id, texto, agrupar: estado || texto }
}
export const campoDe = (campos, id) => campos.find((c) => c.id === id)
export const fnDe = (o) => (!o.valor || o.funcion === 'conteo' ? 'conteo' : o.funcion || 'suma')
export const medirDe = (o) => (fnDe(o) === 'conteo' ? null : o.valor)
export const tipoDe = (o, campos) => (fnDe(o) === 'conteo' ? 'numero' : campoDe(campos, o.valor)?.tipo || 'numero')
const NOMBRE_FN = { conteo: 'Cantidad', suma: 'Total', promedio: 'Promedio', mediana: 'Mediana', minimo: 'Mínimo', maximo: 'Máximo', moda: 'Moda', desviacion: 'Desviación' }
export const queMide = (o, campos) => (fnDe(o) === 'conteo' ? 'Cantidad' : `${NOMBRE_FN[fnDe(o)] || 'Total'} de ${(campoDe(campos, o.valor)?.nombre || '').toLowerCase()}`)
export const nombre = (campos, id) => (campoDe(campos, id)?.nombre || '').toLowerCase()
export const FALTA = 'Faltan campos para este gráfico'
export const SIN_DATOS = 'Sin datos todavía'
export const colorDe = (g, i) => (g.indice >= 0 ? COLORES[g.indice % COLORES.length] : g.clave === E.SIN_DATO ? GRIS : COLORES[i % COLORES.length])

// ── Cálculos base ─────────────────────────────────────────────────────────────────────────────────
export function calcCategorias(regs, campos, o, top = 8) {
  const c = campoDe(campos, o.agrupar)
  if (!c) return FALTA
  const items = E.serie(regs, { agrupar: c.id, medir: medirDe(o), funcion: fnDe(o), campos, top: c.tipo === 'texto' ? o.top || top : undefined })
    .map((it) => ({ ...it, id: it.clave, color: it.color || GRIS }))
  const tipo = tipoDe(o, campos)
  const total = sumaDe(items.map((i) => i.valor))
  return { items, tipo, total, que: queMide(o, campos), campo: c, pie: `${queMide(o, campos)} por ${c.nombre.toLowerCase()}` }
}

/**
 * Comparación honesta del mes en curso: días 1…N de este mes contra días 1…N del anterior (E.tramosComparables).
 * Devuelve { t (tramos), actual, anterior, var, texto } con la misma función de resumen que el gráfico.
 */
export function compararTramos(regs, campoFecha, o, hoy, filtro = null) {
  const t = E.tramosComparables(hoy)
  const base = filtro ? regs.filter(filtro) : regs
  const actual = E.resumir(E.registrosEntre(base, campoFecha, t.actual.desde, t.actual.hasta), medirDe(o), fnDe(o)) ?? 0
  const anterior = E.resumir(E.registrosEntre(base, campoFecha, t.anterior.desde, t.anterior.hasta), medirDe(o), fnDe(o)) ?? 0
  return { t, actual, anterior, var: E.variacion(actual, anterior), texto: `${t.actual.etiqueta} vs ${t.anterior.etiqueta}` }
}

/** Por mes (últimos `meses`). El último mes es el EN CURSO: va marcado `parcial` y trae su comparación justa (`tramo`). */
export function calcMeses(regs, campos, o, hoy) {
  const cf = campoDe(campos, o.fecha)
  if (!cf) return FALTA
  const items = E.serie(regs, { agrupar: 'mes', fecha: o.fecha, medir: medirDe(o), funcion: fnDe(o), campos, meses: o.meses || 12, hoy })
    .map((it, i, xs) => ({ ...it, id: it.clave, parcial: i === xs.length - 1 }))
  const tramo = compararTramos(regs, cf.id, o, hoy)
  return { items, tipo: tipoDe(o, campos), que: queMide(o, campos), entero: fnDe(o) === 'conteo', tramo,
    pie: `${queMide(o, campos)} por mes de ${nombre(campos, o.fecha)} · últimos ${items.length} meses (${items[items.length - 1]?.etiqueta} en curso)` }
}

/** Matriz categorías × series del estado (para apiladas). `filas` = 'mes' o un campo texto. */
export function calcMatriz(regs, campos, o, hoy, filas = 'mes', topFilas = 6) {
  const ce = campoDe(campos, o.estado)
  if (!ce) return FALTA
  let cats
  if (filas === 'mes') {
    if (!campoDe(campos, o.fecha)) return FALTA
    cats = E.agruparPorMes(regs, o.fecha, o.meses || 12, hoy).map((g, i, xs) => ({ id: g.clave, etiqueta: g.etiqueta, larga: i === xs.length - 1 ? `${g.larga} (en curso)` : g.larga, registros: g.registros }))
  } else {
    const ct = campoDe(campos, filas)
    if (!ct) return FALTA
    cats = E.agrupar(regs, ct, { top: topFilas }).map((g) => ({ id: g.clave, etiqueta: g.etiqueta, larga: g.etiqueta, registros: g.registros }))
  }
  const grupos = cats.map((c) => E.agrupar(c.registros, ce))
  const conSinDato = grupos.some((gs) => gs.some((g) => g.clave === E.SIN_DATO && g.registros.length))
  const series = [...ce.opciones.map((op, i) => ({ id: `s:${op}`, clave: op, nombre: op, color: COLORES[i % COLORES.length] })),
    ...(conSinDato ? [{ id: `s:${E.SIN_DATO}`, clave: E.SIN_DATO, nombre: E.SIN_DATO, color: GRIS }] : [])]
  const m = grupos.map((gs) => series.map((s) => E.resumir(gs.find((g) => g.clave === s.clave)?.registros || [], medirDe(o), fnDe(o)) ?? 0))
  const tipo = tipoDe(o, campos)
  const porFila = filas === 'mes' ? `mes de ${nombre(campos, o.fecha)}` : nombre(campos, filas)
  return { cats, series, m, tipo, que: queMide(o, campos), entero: fnDe(o) === 'conteo', pie: `${queMide(o, campos)} por ${porFila} y ${ce.nombre.toLowerCase()}` }
}

export const conTotal = (d, msg = SIN_DATOS) => (typeof d === 'string' ? d : d.total > 0 ? d : msg)
export const conMeses = (d) => (typeof d === 'string' ? d : d.items.some((i) => i.valor) ? d : 'Sin datos en los últimos meses')
export const conMatriz = (d) => (typeof d === 'string' ? d : d.m.some((f) => f.some((v) => v)) ? d : SIN_DATOS)
export const sumaOConteo = (b) => (b.valor ? 'suma' : 'conteo')
export { fmt }
