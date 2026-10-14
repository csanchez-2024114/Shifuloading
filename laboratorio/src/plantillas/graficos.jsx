/* Catálogo de gráficos del CRM ("todas las de Excel" + estadística), en SVG propio y sin dependencias.
 * Reglas:
 *  - Todo número sale de los registros (estadistica.js). Nada escrito a mano.
 *  - Cada gráfico mide su contenedor (ResizeObserver) y dibuja en PÍXELES REALES (viewBox = tamaño medido): el texto queda
 *    siempre en 11–12 px, sea el bloque de 220×140 o de pantalla completa. Leyendas y ejes se compactan u ocultan solos.
 *  - Animación de entrada lenta (CSS con var(--vel)) solo si AnimarContext = true; respeta prefers-reduced-motion.
 *  - Sin registros → «Sin datos todavía». Nunca NaN ni un SVG roto.
 * API:
 *  - <Grafico tipo seccion campos registros opciones />
 *  - compatibles(campos) → [{ id, nombre, familia, requiere, opciones }]
 *  - opcionesPorDefecto(tipo, campos) → opciones que elegiría solo
 *  - <GaleriaGraficos plantilla datos /> (página de prueba) */
import { useContext, useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { AnimarContext, VelContext } from './vistas'
import * as E from './estadistica'
import { registrosDe } from './datosEjemplo'
import { camposDe } from './validar'
import '@base/crm.css'
import '@base/crm-extra.css'
import './graficos.css'

const { COLORES, fmt, fmtPct } = E
const ACENTO = 'var(--acento, #7c5cff)'
const GRIS = 'var(--tx3)'
const VERDE = COLORES[1]
const ROJO = COLORES[3]
const sinMovimiento = () => typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

// ── Utilidades de dibujo ──────────────────────────────────────────────────────────────────────────
/** Ancho aproximado de un texto a 11 px (no hay DOM para medir en el render; basta para decidir qué cabe). */
const anchoTexto = (s, px = 11) => String(s ?? '').length * px * 0.58
const cortar = (s, max) => {
  const t = String(s ?? '')
  if (max <= 8) return ''
  if (anchoTexto(t) <= max + 0.5) return t // tolerancia: evita cortar por error de coma flotante
  const n = Math.max(1, Math.floor(max / 6.4) - 1)
  return `${t.slice(0, n)}…`
}
const escala = (d0, d1, r0, r1) => { const k = d1 === d0 ? 0 : (r1 - r0) / (d1 - d0); return (v) => r0 + ((Number(v) || 0) - d0) * k }
const sumaDe = (xs) => xs.reduce((s, x) => s + (Number(x) || 0), 0)
const tope = (i, n = 24) => Math.min(i, n) // las demoras escalonadas no crecen sin fin
const fechaCorta = (d) => `${d.getDate()} ${E.MESES[d.getMonth()]}`
const fechaLarga = (d) => `${['dom', 'lun', 'mar', 'mié', 'jue', 'vie', 'sáb'][d.getDay()]} ${d.getDate()} ${E.MESES[d.getMonth()]} ${d.getFullYear()}`

/** Marcas de eje "bonitas" (1, 2, 2.5, 5 × 10^n) que cubren [min, max]. */
function ticks(min, max, n = 4, entero = false) {
  let a = Number.isFinite(min) ? min : 0
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

/** Área de dibujo cartesiana: márgenes según lo que cabe, escala Y y marcas. */
function plano(w, h, { min = 0, max = 0, f = (v) => fmt('numero', v), entero = false, etiquetas = true, arriba = 10, der = 10 }) {
  const tk = ticks(min, max, h < 130 ? 2 : h < 230 ? 4 : 5, entero)
  const textos = tk.map(f)
  const necesita = Math.ceil(Math.max(...textos.map((t) => anchoTexto(t)))) + 10
  const conY = w >= 170 && h >= 80 && necesita <= w * 0.4 // si no caben, se ocultan (nunca se recortan)
  const izq = conY ? necesita : 6
  const conX = etiquetas && h >= 64
  const x0 = izq; const x1 = Math.max(x0 + 10, w - der); const y1 = arriba; const y0 = Math.max(y1 + 10, h - (conX ? 20 : 6))
  return { w, x0, x1, y0, y1, y: escala(tk[0], tk[tk.length - 1], y0, y1), tk, textos, conY, conX, ancho: x1 - x0, alto: y0 - y1 }
}

function Rejilla({ p }) {
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

/** Etiquetas del eje X: se saltan las que no caben (cada `paso`) y se cortan al ancho de su banda. */
function EjeX({ p, items }) {
  if (!p.conX || !items.length) return null
  const banda = p.ancho / items.length
  const maxW = Math.max(...items.map((it) => anchoTexto(it.t)))
  const paso = Math.max(1, Math.ceil((maxW + 8) / banda))
  return (
    <g className="gr-ejex" aria-hidden="true">
      {items.map((it, i) => (items.length - 1 - i) % paso === 0 && ( // se cuenta desde el final: el último (lo más reciente) siempre se ve
        <EtiquetaX key={i} x={it.x} y={p.y0 + 14} t={cortar(it.t, banda * paso - 4)} w={p.w} />
      ))}
    </g>
  )
}

const anchoItem = (it) => 14 + anchoTexto(it.nombre) + (it.valor ? anchoTexto(it.valor) + 8 : 0) + 12
/** Cuántas filas ocupa una leyenda que fluye a lo ancho `w`. */
function filasAbajo(w, items) {
  let filas = 1; let x = 0
  for (const it of items) { const a = Math.min(anchoItem(it), w); if (x > 0 && x + a > w) { filas++; x = 0 } x += a }
  return filas
}
/** Etiqueta centrada que nunca se sale del SVG: en los bordes se alinea al borde. */
function EtiquetaX({ x, y, t, w }) {
  const mitad = anchoTexto(t) / 2
  const ancla = x - mitad < 2 ? 'start' : x + mitad > w - 2 ? 'end' : 'middle'
  return <text x={ancla === 'start' ? Math.max(2, x - mitad) : ancla === 'end' ? Math.min(w - 2, x + mitad) : x} y={y} textAnchor={ancla}>{t}</text>
}
/** Decide dónde va la leyenda según el tamaño: a la derecha, abajo o ninguna. */
function planLeyenda(w, h, items) {
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

function Leyenda({ plan, items, w, h, ix }) {
  if (!plan.lado) return null
  if (plan.lado === 'der') {
    const caben = Math.max(1, Math.floor((h - 8) / 18))
    const ver = items.length > caben ? items.slice(0, caben - 1) : items
    const y0 = Math.max(4, (h - (ver.length + (items.length > caben ? 1 : 0)) * 18) / 2) + 9
    const x = w - plan.ancho
    return (
      <g className="gr-ley">
        {ver.map((it, i) => {
          const vw = it.valor ? anchoTexto(it.valor) + 6 : 0
          return (
            <g key={it.id} transform={`translate(${x},${y0 + i * 18})`} className={`gr-ley-it${ix.c(it.id)}`} style={{ '--i': tope(i) }} {...ix.p(it.id, it.nombre, it.filas || [])}>
              <rect x="0" y="-5" width="10" height="10" rx="3" style={{ fill: it.color, ...(it.raya ? { fill: 'none', stroke: it.color, strokeWidth: 2, strokeDasharray: '3 2' } : {}) }} />
              <text x="16" dy="0.35em">{cortar(it.nombre, plan.ancho - 22 - vw)}</text>
              {it.valor && <text x={plan.ancho - 4} dy="0.35em" textAnchor="end" className="gr-ley-v">{it.valor}</text>}
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
      {items.map((it, i) => (
        <g key={it.id} transform={`translate(${pos[i].x},${pos[i].y})`} className={`gr-ley-it${ix.c(it.id)}`} style={{ '--i': tope(i) }} {...ix.p(it.id, it.nombre, it.filas || [])}>
          <rect x="0" y="-5" width="10" height="10" rx="3" style={{ fill: it.color, ...(it.raya ? { fill: 'none', stroke: it.color, strokeWidth: 2, strokeDasharray: '3 2' } : {}) }} />
          <text x="15" dy="0.35em">{cortar(it.nombre, pos[i].a - 26 - (it.valor ? anchoTexto(it.valor) + 6 : 0))}{it.valor && <tspan className="gr-ley-v" dx="5">{it.valor}</tspan>}</text>
        </g>
      ))}
    </g>
  )
}

/** Resaltado por serie (al pasar por la leyenda, cuyos ids empiezan por «s:»). */
const porSerie = (ix) => typeof ix.activo === 'string' && ix.activo.startsWith('s:')
const claseSerie = (ix, id) => (porSerie(ix) ? (ix.activo === id ? ' gr-on' : ' gr-off') : '')
/** Recorta el área de dibujo según la leyenda. */
const areaCon = (plan, w, h) => ({ w: plan.lado === 'der' ? Math.max(40, w - plan.ancho - 10) : w, h: plan.lado === 'abajo' ? Math.max(30, h - plan.alto) : h })

/** Número que sube desde 0 hasta su valor (solo en estilos animados). El valor final es el exacto. */
function Cuenta({ v, f }) {
  const animar = useContext(AnimarContext) && !sinMovimiento()
  const vel = useContext(VelContext)
  const [n, setN] = useState(animar && Number.isFinite(v) ? 0 : v)
  useEffect(() => {
    if (!animar || !Number.isFinite(v)) { setN(v); return undefined }
    let raf; const t0 = performance.now(); const dur = 1100 * vel
    const paso = (t) => { const k = Math.min(1, (t - t0) / dur); setN(k >= 1 ? v : v * (1 - (1 - k) ** 3)); if (k < 1) raf = requestAnimationFrame(paso) }
    raf = requestAnimationFrame(paso)
    return () => cancelAnimationFrame(raf)
  }, [v, animar, vel])
  return f(n)
}

const Svg = ({ w, h, aria, children, className = '' }) => (
  <svg className={`gr-svg ${className}`} width={w} height={h} viewBox={`0 0 ${w} ${h}`} role="img" aria-label={aria}>{children}</svg>
)

// ── Campos y opciones ─────────────────────────────────────────────────────────────────────────────
/** Clases de campo que puede pedir un gráfico en `requiere`. */
export const CLASES = {
  estado: (c) => c.tipo === 'estado',
  estado3: (c) => c.tipo === 'estado' && (c.opciones?.length || 0) >= 3, // estado con 3 o más opciones (radar)
  fecha: (c) => c.tipo === 'fecha',
  medida: (c) => c.tipo === 'numero' || c.tipo === 'dinero',
  texto: (c) => c.tipo === 'texto',
  categoria: (c) => c.tipo === 'estado' || c.tipo === 'texto',
}
/** `requiere` es un objeto { clase: cantidad } o una lista de alternativas (basta con cumplir una). */
const cumple = (requiere, campos) => [].concat(requiere).some((alt) => Object.entries(alt).every(([cl, n]) => campos.filter(CLASES[cl] || (() => false)).length >= n))

/** Campos que se eligen solos: el primer estado, la primera fecha, la primera medida (dinero antes que número) y el primer texto. */
function base(campos) {
  const de = (cl) => campos.filter(CLASES[cl])
  const medidas = [...campos.filter((c) => c.tipo === 'dinero'), ...campos.filter((c) => c.tipo === 'numero')]
  const estado = de('estado')[0]?.id
  const texto = de('texto')[0]?.id
  return { estado, fecha: de('fecha')[0]?.id, valor: medidas[0]?.id, valor2: medidas[1]?.id, texto, agrupar: estado || texto }
}
const campoDe = (campos, id) => campos.find((c) => c.id === id)
const fnDe = (o) => (!o.valor || o.funcion === 'conteo' ? 'conteo' : o.funcion || 'suma')
const medirDe = (o) => (fnDe(o) === 'conteo' ? null : o.valor)
const tipoDe = (o, campos) => (fnDe(o) === 'conteo' ? 'numero' : campoDe(campos, o.valor)?.tipo || 'numero')
const NOMBRE_FN = { conteo: 'Cantidad', suma: 'Total', promedio: 'Promedio', mediana: 'Mediana', minimo: 'Mínimo', maximo: 'Máximo', moda: 'Moda', desviacion: 'Desviación' }
const queMide = (o, campos) => (fnDe(o) === 'conteo' ? 'Cantidad' : `${NOMBRE_FN[fnDe(o)] || 'Total'} de ${(campoDe(campos, o.valor)?.nombre || '').toLowerCase()}`)
const nombre = (campos, id) => (campoDe(campos, id)?.nombre || '').toLowerCase()
const FALTA = 'Faltan campos para este gráfico'
const SIN_DATOS = 'Sin datos todavía'

// ── Cálculos (puros: registros → lo que se dibuja). Devuelven un objeto o un texto (= estado vacío). ────────
function calcCategorias(regs, campos, o, top = 8) {
  const c = campoDe(campos, o.agrupar)
  if (!c) return FALTA
  const items = E.serie(regs, { agrupar: c.id, medir: medirDe(o), funcion: fnDe(o), campos, top: c.tipo === 'texto' ? o.top || top : undefined })
    .map((it) => ({ ...it, id: it.clave, color: it.color || GRIS }))
  const tipo = tipoDe(o, campos)
  const total = sumaDe(items.map((i) => i.valor))
  return { items, tipo, total, que: queMide(o, campos), pie: `${queMide(o, campos)} por ${c.nombre.toLowerCase()}` }
}
function calcMeses(regs, campos, o, hoy) {
  if (!campoDe(campos, o.fecha)) return FALTA
  const items = E.serie(regs, { agrupar: 'mes', fecha: o.fecha, medir: medirDe(o), funcion: fnDe(o), campos, meses: o.meses || 12, hoy })
    .map((it) => ({ ...it, id: it.clave }))
  return { items, tipo: tipoDe(o, campos), que: queMide(o, campos), entero: fnDe(o) === 'conteo', pie: `${queMide(o, campos)} por mes de ${nombre(campos, o.fecha)} · últimos ${items.length} meses` }
}
/** Matriz categorías × series del estado (para apiladas). `filas` = 'mes' o un campo texto. */
function calcMatriz(regs, campos, o, hoy, filas = 'mes', topFilas = 6) {
  const ce = campoDe(campos, o.estado)
  if (!ce) return FALTA
  let cats
  if (filas === 'mes') {
    if (!campoDe(campos, o.fecha)) return FALTA
    cats = E.agruparPorMes(regs, o.fecha, o.meses || 12, hoy).map((g) => ({ id: g.clave, etiqueta: g.etiqueta, larga: g.larga, registros: g.registros }))
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

// ── Componentes de dibujo. Reciben { w, h, d (cálculo), o (opciones), ix (interacción), uid } ──────────────────
function Columnas({ w, h, d, ix }) {
  const { items, tipo } = d
  const vals = items.map((i) => i.valor)
  const p = plano(w, h, { min: Math.min(0, ...vals), max: Math.max(0, ...vals), f: (v) => fmt(tipo, v), entero: d.entero })
  const banda = p.ancho / items.length
  const bw = Math.max(2, Math.min(56, banda * 0.66))
  const conValor = p.alto >= 80 && banda >= Math.max(...vals.map((v) => anchoTexto(fmt(tipo, v)))) + 4
  const total = sumaDe(vals)
  return (
    <Svg w={w} h={h} aria={`${d.pie}: ${items.map((i) => `${i.larga} ${fmt(tipo, i.valor)}`).join(', ')}`}>
      <Rejilla p={p} />
      <g className="gr-marcas">
        {items.map((it, i) => {
          const xc = p.x0 + banda * (i + 0.5)
          const ya = p.y(Math.max(0, it.valor)); const yb = p.y(Math.min(0, it.valor))
          return (
            <g key={it.id} className={`gr-m${ix.c(it.id)}`} {...ix.p(it.id, it.larga, [[d.que, fmt(tipo, it.valor), it.color === COLORES[0] ? ACENTO : it.color], ['Del total', fmtPct(E.porcentajeDelTotal(it.valor, total))], ['Registros', fmt('numero', it.n)]])}>
              <rect className="gr-hit" x={p.x0 + banda * i} y={p.y1} width={banda} height={p.alto} />
              <rect className={it.valor < 0 ? 'gr-baja' : 'gr-sube'} x={xc - bw / 2} y={ya} width={bw} height={Math.max(it.valor ? 1 : 0, yb - ya)} rx={Math.min(4, bw / 4)} style={{ fill: it.color === COLORES[0] ? ACENTO : it.color, '--i': tope(i) }} />
              {conValor && <text className="gr-valor gr-aparece" x={xc} y={ya - 5} textAnchor="middle" style={{ '--i': tope(i) }}>{fmt(tipo, it.valor)}</text>}
            </g>
          )
        })}
      </g>
      <EjeX p={p} items={items.map((it, i) => ({ x: p.x0 + banda * (i + 0.5), t: it.etiqueta }))} />
    </Svg>
  )
}

function ColumnasApiladas({ w, h, d, ix, normalizar }) {
  const { cats, series, m, tipo } = d
  const totales = m.map((fila) => sumaDe(fila))
  const totalSerie = series.map((_, k) => sumaDe(m.map((fila) => fila[k])))
  const ley = planLeyenda(w, h, series.map((s, k) => ({ ...s, valor: normalizar ? '' : fmt(tipo, totalSerie[k]) })))
  const a = areaCon(ley, w, h)
  const f = normalizar ? (v) => fmtPct(v) : (v) => fmt(tipo, v)
  const p = plano(a.w, a.h, { max: normalizar ? 1 : Math.max(0, ...totales), f, entero: !normalizar && d.entero })
  const banda = p.ancho / cats.length
  const bw = Math.max(2, Math.min(48, banda * 0.66))
  return (
    <Svg w={w} h={h} aria={`${d.pie}${normalizar ? ' (100 %)' : ''}`}>
      <Rejilla p={p} />
      <g className="gr-marcas">
        {cats.map((c, i) => {
          let acum = 0
          const xc = p.x0 + banda * (i + 0.5)
          const filas = series.map((s, k) => [s.nombre, `${fmt(tipo, m[i][k])}${totales[i] ? ` · ${fmtPct(m[i][k] / totales[i])}` : ''}`, s.color]).filter((_, k) => m[i][k])
          return (
            <g key={c.id} className={`gr-m${porSerie(ix) ? '' : ix.c(c.id)}`} {...ix.p(c.id, c.larga, [...filas, ['Total', fmt(tipo, totales[i])]])}>
              <rect className="gr-hit" x={p.x0 + banda * i} y={p.y1} width={banda} height={p.alto} />
              {series.map((s, k) => {
                const v = normalizar ? (totales[i] ? m[i][k] / totales[i] : 0) : m[i][k]
                if (!v) return null
                const y0 = p.y(acum); acum += v; const y1 = p.y(acum)
                return <rect key={s.id} className={`gr-sube gr-seg${claseSerie(ix, s.id)}`} x={xc - bw / 2} y={y1} width={bw} height={Math.max(0.5, y0 - y1 - (y0 - y1 > 3 ? 1 : 0))} rx="2" style={{ fill: s.color, '--i': tope(i) }} />
              })}
            </g>
          )
        })}
      </g>
      <EjeX p={p} items={cats.map((c, i) => ({ x: p.x0 + banda * (i + 0.5), t: c.etiqueta }))} />
      <Leyenda plan={ley} w={w} h={h} ix={ix} items={series.map((s, k) => ({ ...s, valor: normalizar ? '' : fmt(tipo, totalSerie[k]), filas: [['Total', fmt(tipo, totalSerie[k]), s.color]] }))} />
    </Svg>
  )
}

/** Filas horizontales con etiqueta a la izquierda y valor a la derecha. Si no caben todas, se adelgazan (nunca se esconden datos). */
function Barras({ w, h, d, ix }) {
  const { items, tipo, total } = d
  const conEtq = w >= 150
  const izq = conEtq ? Math.min(w * 0.36, Math.max(...items.map((i) => anchoTexto(i.etiqueta))) + 10) : 4
  const textos = items.map((i) => fmt(tipo, i.valor))
  const conValor = w >= 170
  const der = conValor ? Math.max(...textos.map((t) => anchoTexto(t))) + 10 : 4
  const x0 = izq; const x1 = Math.max(x0 + 10, w - der)
  const fila = (h - 6) / items.length
  const bh = Math.max(2, Math.min(24, fila * 0.62))
  const conTexto = fila >= 13
  const max = Math.max(1e-9, ...items.map((i) => i.valor))
  const x = escala(0, max, x0, x1)
  return (
    <Svg w={w} h={h} aria={`${d.pie}: ${items.map((i, k) => `${i.etiqueta} ${textos[k]}`).join(', ')}`}>
      <g className="gr-marcas">
        {items.map((it, i) => {
          const yc = 3 + fila * (i + 0.5)
          const largo = Math.max(it.valor > 0 ? 1.5 : 0, x(Math.max(0, it.valor)) - x0)
          return (
            <g key={it.id} className={`gr-m${ix.c(it.id)}`} {...ix.p(it.id, it.larga, [[d.que, textos[i], it.color], ['Del total', fmtPct(E.porcentajeDelTotal(it.valor, total))], ['Registros', fmt('numero', it.n)]])}>
              <rect className="gr-hit" x="0" y={yc - fila / 2} width={w} height={fila} />
              <rect className="gr-pista" x={x0} y={yc - bh / 2} width={x1 - x0} height={bh} rx={Math.min(5, bh / 2)} />
              <rect className="gr-crece" x={x0} y={yc - bh / 2} width={largo} height={bh} rx={Math.min(5, bh / 2)} style={{ fill: it.color, '--i': tope(i) }} />
              {conEtq && conTexto && <text x={x0 - 8} y={yc} dy="0.35em" textAnchor="end">{cortar(it.etiqueta, izq - 12)}</text>}
              {conValor && conTexto && <text className="gr-valor gr-aparece" x={x0 + largo + 6} y={yc} dy="0.35em" style={{ '--i': tope(i) }}>{textos[i]}</text>}
            </g>
          )
        })}
      </g>
    </Svg>
  )
}

function BarrasApiladas({ w, h, d, ix }) {
  const { cats, series, m, tipo } = d
  const totales = m.map((fila) => sumaDe(fila))
  const totalSerie = series.map((_, k) => sumaDe(m.map((fila) => fila[k])))
  const ley = planLeyenda(w, h, series)
  const a = areaCon(ley, w, h)
  const conEtq = a.w >= 150
  const izq = conEtq ? Math.min(a.w * 0.34, Math.max(...cats.map((c) => anchoTexto(c.etiqueta))) + 10) : 4
  const der = a.w >= 170 ? Math.max(...totales.map((t) => anchoTexto(fmt(tipo, t)))) + 10 : 4
  const x0 = izq; const x1 = Math.max(x0 + 10, a.w - der)
  const fila = (a.h - 6) / cats.length
  const bh = Math.max(2, Math.min(24, fila * 0.62))
  const max = Math.max(1e-9, ...totales)
  const x = escala(0, max, x0, x1)
  return (
    <Svg w={w} h={h} aria={d.pie}>
      <g className="gr-marcas">
        {cats.map((c, i) => {
          const yc = 3 + fila * (i + 0.5)
          let acum = 0
          const filas = series.map((s, k) => [s.nombre, `${fmt(tipo, m[i][k])}${totales[i] ? ` · ${fmtPct(m[i][k] / totales[i])}` : ''}`, s.color]).filter((_, k) => m[i][k])
          return (
            <g key={c.id} className={`gr-m${porSerie(ix) ? '' : ix.c(c.id)}`} {...ix.p(c.id, c.larga, [...filas, ['Total', fmt(tipo, totales[i])]])}>
              <rect className="gr-hit" x="0" y={yc - fila / 2} width={a.w} height={fila} />
              <g className="gr-crece" style={{ '--i': tope(i) }}>
                {series.map((s, k) => {
                  const v = m[i][k]
                  if (!v) return null
                  const xa = x(acum); acum += v; const xb = x(acum)
                  return <rect key={s.id} className={`gr-seg${claseSerie(ix, s.id)}`} x={xa} y={yc - bh / 2} width={Math.max(0.5, xb - xa - (xb - xa > 3 ? 1 : 0))} height={bh} rx="2" style={{ fill: s.color }} />
                })}
              </g>
              {conEtq && fila >= 13 && <text x={x0 - 8} y={yc} dy="0.35em" textAnchor="end">{cortar(c.etiqueta, izq - 12)}</text>}
              {a.w >= 170 && fila >= 13 && <text className="gr-valor gr-aparece" x={x(totales[i]) + 6} y={yc} dy="0.35em" style={{ '--i': tope(i) }}>{fmt(tipo, totales[i])}</text>}
            </g>
          )
        })}
      </g>
      <Leyenda plan={ley} w={w} h={h} ix={ix} items={series.map((s, k) => ({ ...s, filas: [['Total', fmt(tipo, totalSerie[k]), s.color]] }))} />
    </Svg>
  )
}

/** Una sola barra 100 % con las partes del total. */
function Barra100({ w, h, d, ix }) {
  const { items, tipo, total } = d
  const conPartes = items.filter((i) => i.valor > 0)
  const leyItems = items.map((i) => ({ id: i.id, nombre: i.etiqueta, color: i.color, valor: fmtPct(E.porcentajeDelTotal(i.valor, total)), filas: [[d.que, fmt(tipo, i.valor), i.color]] }))
  const altoLey = filasAbajo(w, leyItems) * 18 + 6
  const ley = h - altoLey >= 34 ? { lado: 'abajo', alto: altoLey } : { lado: null }
  const enLinea = ley.lado ? ley.alto : 0
  const bh = Math.max(14, Math.min(44, (h - enLinea) * 0.36))
  const yb = Math.max(4, (h - enLinea - bh) / 2)
  const x0 = 4; const x1 = w - 4
  let acum = 0
  return (
    <Svg w={w} h={h} aria={`${d.pie}: ${items.map((i) => `${i.etiqueta} ${fmtPct(E.porcentajeDelTotal(i.valor, total))}`).join(', ')}`}>
      <rect className="gr-pista" x={x0} y={yb} width={x1 - x0} height={bh} rx={Math.min(10, bh / 2)} />
      <g className="gr-marcas gr-crece" style={{ '--i': 0 }}>
        {conPartes.map((it, i) => {
          const f = it.valor / total
          const xa = x0 + (x1 - x0) * acum; acum += f; const ancho = (x1 - x0) * f
          const pct = fmtPct(f)
          return (
            <g key={it.id} className={`gr-m${ix.c(it.id)}`} {...ix.p(it.id, it.larga, [[d.que, fmt(tipo, it.valor), it.color], ['Del total', pct]])}>
              <rect x={xa} y={yb} width={Math.max(0.5, ancho - (ancho > 3 ? 1.5 : 0))} height={bh} rx={i === 0 || i === conPartes.length - 1 ? Math.min(10, bh / 2) : 2} style={{ fill: it.color }} />
              {ancho >= anchoTexto(pct) + 10 && bh >= 16 && <text className="gr-halo" x={xa + ancho / 2} y={yb + bh / 2} dy="0.35em" textAnchor="middle">{pct}</text>}
            </g>
          )
        })}
      </g>
      <Leyenda plan={ley} w={w} h={h} ix={ix} items={leyItems} />
    </Svg>
  )
}

/** Línea por mes. Variantes: con área degradada, o con recta de tendencia + media móvil. */
function Linea({ w, h, d, ix, uid, area, tendencia }) {
  const { items, tipo } = d
  const vals = items.map((i) => i.valor)
  const tl = tendencia ? E.tendenciaLineal(vals) : null
  const mm = tendencia ? E.mediaMovil(vals, d.ventana || 3) : []
  const ley = tendencia ? planLeyenda(w, h, d.leyenda) : { lado: null }
  const a = areaCon(ley, w, h)
  const extra = tendencia ? [tl.en(0), tl.en(vals.length - 1), ...mm.filter((x) => x !== null)] : []
  const p = plano(a.w, a.h, { min: Math.min(0, ...extra), max: Math.max(0, ...vals, ...extra), f: (v) => fmt(tipo, v), entero: d.entero, arriba: 12 })
  const banda = p.ancho / items.length
  const X = (i) => p.x0 + banda * (i + 0.5)
  const linea = vals.map((v, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)},${p.y(v).toFixed(1)}`).join(' ')
  const relleno = `${linea} L${X(vals.length - 1).toFixed(1)},${p.y0} L${X(0).toFixed(1)},${p.y0} Z`
  const mmPath = mm.map((v, i) => (v === null ? null : [X(i), p.y(v)])).filter(Boolean).map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ')
  const gid = `gr-deg-${uid}`
  const activo = items.findIndex((it) => it.id === ix.activo)
  const r = Math.max(2, Math.min(4, banda / 5))
  return (
    <Svg w={w} h={h} aria={`${d.pie}: ${items.map((i) => `${i.larga} ${fmt(tipo, i.valor)}`).join(', ')}`}>
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1"><stop offset="0" style={{ stopColor: ACENTO, stopOpacity: 0.38 }} /><stop offset="1" style={{ stopColor: ACENTO, stopOpacity: 0 }} /></linearGradient>
      </defs>
      <Rejilla p={p} />
      {(area || tendencia) && <path className="gr-area" d={relleno} style={{ fill: `url(#${gid})`, ...(tendencia ? { opacity: 0.45 } : {}) }} />}
      {activo >= 0 && <line className="gr-guia" x1={X(activo)} x2={X(activo)} y1={p.y1} y2={p.y0} />}
      <path className="gr-traza gr-linea" d={linea} pathLength="1" style={{ stroke: ACENTO }} />
      {tendencia && mmPath && <path className="gr-traza gr-linea gr-mm" d={mmPath} pathLength="1" style={{ stroke: COLORES[5], '--i': 6 }} />}
      {tendencia && <line className="gr-aparece gr-tendencia" x1={X(0)} y1={p.y(tl.en(0))} x2={X(vals.length - 1)} y2={p.y(tl.en(vals.length - 1))} style={{ stroke: COLORES[2], '--i': 10 }} />}
      <g className="gr-marcas">
        {items.map((it, i) => (
          <g key={it.id} {...ix.p(it.id, it.larga, [[d.que, fmt(tipo, it.valor), ACENTO],
            ...(tendencia ? [[`Media móvil ${d.ventana || 3} m`, fmt(tipo, mm[i]), COLORES[5]], ['Tendencia', fmt(tipo, tl.en(i)), COLORES[2]]] : []),
            ...(i > 0 ? [['vs mes anterior', fmtPct(E.variacion(it.valor, vals[i - 1]), true)]] : [])])}>
            <rect className="gr-hit" x={p.x0 + banda * i} y={p.y1} width={banda} height={p.alto} />
            {banda >= 9 && <circle className="gr-punto" cx={X(i)} cy={p.y(it.valor)} r={r} style={{ fill: 'var(--card)', stroke: ACENTO, '--i': tope(i) }} />}
          </g>
        ))}
        {activo >= 0 && <circle className="gr-punto-on" cx={X(activo)} cy={p.y(vals[activo])} r={r + 2.5} style={{ fill: ACENTO }} />}
      </g>
      <EjeX p={p} items={items.map((it, i) => ({ x: X(i), t: it.etiqueta }))} />
      {tendencia && <Leyenda plan={ley} w={w} h={h} ix={ix} items={d.leyenda} />}
    </Svg>
  )
}

function AreaApilada({ w, h, d, ix }) {
  const { cats, series, m, tipo } = d
  const totales = m.map((fila) => sumaDe(fila))
  const ley = planLeyenda(w, h, series)
  const a = areaCon(ley, w, h)
  const p = plano(a.w, a.h, { max: Math.max(0, ...totales), f: (v) => fmt(tipo, v), entero: d.entero, arriba: 12 })
  const banda = p.ancho / cats.length
  const X = (i) => p.x0 + banda * (i + 0.5)
  const acum = cats.map(() => 0)
  const capas = series.map((s, k) => {
    const abajo = acum.slice()
    cats.forEach((_, i) => { acum[i] += m[i][k] })
    const arriba = acum.slice()
    const ida = arriba.map((v, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)},${p.y(v).toFixed(1)}`).join(' ')
    const vuelta = abajo.map((v, i) => [X(i), p.y(v)]).reverse().map(([x, y]) => `L${x.toFixed(1)},${y.toFixed(1)}`).join(' ')
    return { s, k, d: `${ida} ${vuelta} Z`, borde: ida, vacia: arriba.every((v, i) => v === abajo[i]) }
  })
  const activo = cats.findIndex((c) => c.id === ix.activo)
  return (
    <Svg w={w} h={h} aria={d.pie}>
      <Rejilla p={p} />
      <g className="gr-capas">
        {capas.filter((c) => !c.vacia).map(({ s, k, d: path, borde }) => (
          <g key={s.id} className={`gr-capa${claseSerie(ix, s.id)}`} style={{ '--i': k }}>
            <path className="gr-area" d={path} style={{ fill: s.color, fillOpacity: 0.55 }} />
            <path className="gr-borde" d={borde} style={{ stroke: s.color }} />
          </g>
        ))}
      </g>
      {activo >= 0 && <line className="gr-guia" x1={X(activo)} x2={X(activo)} y1={p.y1} y2={p.y0} />}
      <g className="gr-marcas">
        {cats.map((c, i) => (
          <rect key={c.id} className="gr-hit" x={p.x0 + banda * i} y={p.y1} width={banda} height={p.alto}
            {...ix.p(c.id, c.larga, [...series.map((s, k) => [s.nombre, fmt(tipo, m[i][k]), s.color]).filter((_, k) => m[i][k]), ['Total', fmt(tipo, totales[i])]])} />
        ))}
      </g>
      <EjeX p={p} items={cats.map((c, i) => ({ x: X(i), t: c.etiqueta }))} />
      <Leyenda plan={ley} w={w} h={h} ix={ix} items={series.map((s, k) => ({ ...s, filas: [['Total', fmt(tipo, sumaDe(m.map((f) => f[k]))), s.color]] }))} />
    </Svg>
  )
}

/** Dona y pastel con la técnica de stroke-dasharray (un círculo por parte). */
function Circular({ w, h, d, ix, dona }) {
  const { items, tipo, total } = d
  const leyItems = items.map((it) => ({ id: it.id, nombre: it.etiqueta, color: it.color, valor: fmtPct(E.porcentajeDelTotal(it.valor, total)), filas: [[d.que, fmt(tipo, it.valor), it.color], ['Del total', fmtPct(E.porcentajeDelTotal(it.valor, total))]] }))
  const ley = planLeyenda(w, h, leyItems)
  const a = areaCon(ley, w, h)
  const R = Math.max(12, Math.min(a.w, a.h) / 2 - 6)
  const cx = a.w / 2; const cy = a.h / 2
  const sw = dona ? Math.max(6, R * 0.34) : R
  const r = dona ? R - sw / 2 : R / 2
  const C = 2 * Math.PI * r
  let acum = 0
  const partes = items.filter((it) => it.valor > 0).map((it, i) => {
    const f = it.valor / total
    const p = { it, i, f, ini: acum }
    acum += f
    return p
  })
  const separa = partes.length > 1 && dona ? Math.min(2, C * 0.004) : 0
  return (
    <Svg w={w} h={h} aria={`${d.pie}: ${items.map((i) => `${i.etiqueta} ${fmt(tipo, i.valor)} (${fmtPct(E.porcentajeDelTotal(i.valor, total))})`).join(', ')}`}>
      {dona && <circle className="gr-pista-c" cx={cx} cy={cy} r={r} style={{ strokeWidth: sw }} />}
      <g className="gr-marcas">
        {partes.map(({ it, i, f, ini }) => (
          <circle key={it.id} className={`gr-arco gr-m${ix.c(it.id)}`} cx={cx} cy={cy} r={r} transform={`rotate(-90 ${cx} ${cy})`}
            strokeDasharray={`${Math.max(0.01, f * C - separa)} ${C}`} strokeDashoffset={-ini * C}
            style={{ stroke: it.color, strokeWidth: sw, '--sw': `${sw}px`, '--i': i }}
            {...ix.p(it.id, it.larga, [[d.que, fmt(tipo, it.valor), it.color], ['Del total', fmtPct(f)], ['Registros', fmt('numero', it.n)]])} />
        ))}
      </g>
      {!dona && R >= 46 && partes.map(({ it, f, ini }) => {
        if (f < 0.07) return null
        const ang = (ini + f / 2) * 2 * Math.PI - Math.PI / 2
        return <text key={it.id} className="gr-halo gr-aparece" x={cx + Math.cos(ang) * R * 0.62} y={cy + Math.sin(ang) * R * 0.62} dy="0.35em" textAnchor="middle" style={{ '--i': 6 }} pointerEvents="none">{fmtPct(f)}</text>
      })}
      {dona && R >= 30 && (
        <g className="gr-centro-t" pointerEvents="none">
          <text x={cx} y={cy} dy={R >= 48 ? '0.1em' : '0.35em'} textAnchor="middle" className="gr-grande" style={{ fontSize: Math.round(Math.max(13, Math.min(28, r * 0.42))) }}><Cuenta v={total} f={(x) => fmt(tipo, x)} /></text>
          {R >= 48 && <text x={cx} y={cy} dy="1.5em" textAnchor="middle">{tipo === 'numero' && d.que === 'Cantidad' ? 'en total' : cortar(d.que.toLowerCase(), r * 1.4)}</text>}
        </g>
      )}
      <Leyenda plan={ley} w={w} h={h} ix={ix} items={leyItems} />
    </Svg>
  )
}

/** Anillos concéntricos (barras radiales): cada categoría es un anillo; el más grande llega a 3/4 de vuelta. */
function Anillos({ w, h, d, ix }) {
  const items = d.items.slice(0, 7)
  const { tipo, total } = d
  const leyItems = items.map((it) => ({ id: it.id, nombre: it.etiqueta, color: it.color, valor: fmt(tipo, it.valor), filas: [[d.que, fmt(tipo, it.valor), it.color]] }))
  const ley = planLeyenda(w, h, leyItems)
  const a = areaCon(ley, w, h)
  const R = Math.max(14, Math.min(a.w, a.h) / 2 - 4)
  const cx = a.w / 2; const cy = a.h / 2
  const r0 = R * 0.24
  const paso = (R - r0) / items.length
  const sw = Math.max(2, paso * 0.7)
  const max = Math.max(1e-9, ...items.map((i) => i.valor))
  return (
    <Svg w={w} h={h} aria={`${d.pie}: ${items.map((i) => `${i.etiqueta} ${fmt(tipo, i.valor)}`).join(', ')}`}>
      <g className="gr-marcas">
        {items.map((it, k) => {
          const r = R - paso * (k + 0.5)
          const C = 2 * Math.PI * r
          const f = (it.valor / max) * 0.75
          return (
            <g key={it.id} className={`gr-m${ix.c(it.id)}`} {...ix.p(it.id, it.larga, [[d.que, fmt(tipo, it.valor), it.color], ['Del total', fmtPct(E.porcentajeDelTotal(it.valor, total))]])}>
              <circle className="gr-pista-c" cx={cx} cy={cy} r={r} transform={`rotate(-90 ${cx} ${cy})`} strokeDasharray={`${0.75 * C} ${C}`} style={{ strokeWidth: sw }} />
              {f > 0 && <circle className="gr-arco" cx={cx} cy={cy} r={r} transform={`rotate(-90 ${cx} ${cy})`} strokeDasharray={`${f * C} ${C}`} strokeLinecap="round" style={{ stroke: it.color, strokeWidth: sw, '--sw': `${sw}px`, '--i': k }} />}
              {sw >= 9 && r >= 40 && <text x={cx - sw / 2 - 6} y={cy - r} dy="0.35em" textAnchor="end" className="gr-aparece" style={{ '--i': k }}>{cortar(`${it.etiqueta} · ${fmt(tipo, it.valor)}`, r - sw / 2 - 10)}</text>}
            </g>
          )
        })}
      </g>
      <Leyenda plan={ley} w={w} h={h} ix={ix} items={leyItems} />
    </Svg>
  )
}

/** Medidor semicircular: la parte de los registros que está en una opción del estado. */
function Medidor({ w, h, d, ix }) {
  const textoAbajo = h >= 110 ? 34 : 18
  const R = Math.max(14, Math.min(w / 2 - 10, h - textoAbajo - 8))
  const cx = w / 2; const cy = Math.max(R + 6, (h - textoAbajo + R) / 2 + 2)
  const sw = Math.max(5, R * 0.22)
  const r = R - sw / 2
  const arco = `M${cx - r},${cy} A${r},${r} 0 0 1 ${cx + r},${cy}`
  const f = Math.max(0, Math.min(1, d.f))
  const ang = Math.PI * (1 - f)
  return (
    <Svg w={w} h={h} aria={`${d.objetivo}: ${fmtPct(d.f)} del total (${d.n} de ${d.total})`}>
      <path className="gr-pista-c" d={arco} style={{ strokeWidth: sw }} />
      <g className="gr-marcas" {...ix.p('medidor', d.objetivo, [['Registros', `${fmt('numero', d.n)} de ${fmt('numero', d.total)}`, d.color], ['Del total', fmtPct(d.f)]])}>
        {f > 0 && <path className={`gr-arco gr-m${ix.c('medidor')}`} d={arco} pathLength="1" strokeDasharray={`${f} 1`} style={{ stroke: d.color, strokeWidth: sw, strokeLinecap: 'round', '--sw': `${sw}px` }} />}
        {R >= 40 && <circle className="gr-aparece" cx={cx + Math.cos(ang) * r} cy={cy - Math.sin(ang) * r} r={sw * 0.32} style={{ fill: 'var(--card)', '--i': 12 }} />}
      </g>
      <text x={cx} y={cy - (R >= 50 ? 6 : 2)} textAnchor="middle" className="gr-grande" style={{ fontSize: Math.round(Math.max(13, Math.min(30, R * 0.36))) }}><Cuenta v={d.f * 100} f={(x) => `${(Math.round(x * 10) / 10).toLocaleString('es')} %`} /></text>
      {R >= 84 && <><text x={cx - r} y={cy + sw / 2 + 14} textAnchor="middle" className="gr-sutil">0 %</text><text x={cx + r} y={cy + sw / 2 + 14} textAnchor="middle" className="gr-sutil">100 %</text></>}
      <text x={cx} y={cy + 16} textAnchor="middle">{cortar(`${d.objetivo}`, Math.max(40, R >= 84 ? r * 1.2 : w - 8))}</text>
      {h >= 110 && <text x={cx} y={cy + 31} textAnchor="middle" className="gr-sutil">{`${fmt('numero', d.n)} de ${fmt('numero', d.total)} registros`}</text>}
    </Svg>
  )
}

/** Anillo de meta: valor del mes en curso contra la meta. */
function Meta({ w, h, d, ix }) {
  const R = Math.max(14, Math.min(w, h) / 2 - 6)
  const cx = w / 2; const cy = h / 2
  const sw = Math.max(6, R * 0.2)
  const r = R - sw / 2
  const f = d.meta ? d.valor / d.meta : 0
  const C = 2 * Math.PI * r
  const ff = Math.max(0, Math.min(1, f))
  return (
    <Svg w={w} h={h} aria={`${d.etiqueta}: ${fmt(d.tipo, d.valor)} de ${fmt(d.tipo, d.meta)} (${fmtPct(f)})`}>
      <circle className="gr-pista-c" cx={cx} cy={cy} r={r} style={{ strokeWidth: sw }} />
      <g className="gr-marcas" {...ix.p('meta', d.etiqueta, [['Lleva', fmt(d.tipo, d.valor), f >= 1 ? VERDE : ACENTO], ['Meta', fmt(d.tipo, d.meta)], ['Avance', fmtPct(f)], ['Meta =', d.origen]])}>
        <circle className="gr-pista-c gr-hit-c" cx={cx} cy={cy} r={r} style={{ strokeWidth: sw, opacity: 0 }} />
        {ff > 0 && <circle className={`gr-arco gr-m${ix.c('meta')}`} cx={cx} cy={cy} r={r} transform={`rotate(-90 ${cx} ${cy})`} strokeDasharray={`${ff * C} ${C}`} strokeLinecap="round" style={{ stroke: f >= 1 ? VERDE : ACENTO, strokeWidth: sw, '--sw': `${sw}px` }} />}
      </g>
      <g pointerEvents="none">
        <text x={cx} y={cy} dy={R >= 50 ? '0.05em' : '0.35em'} textAnchor="middle" className="gr-grande" style={{ fontSize: Math.round(Math.max(13, Math.min(30, r * 0.4))) }}><Cuenta v={f * 100} f={(x) => `${Math.round(x).toLocaleString('es')} %`} /></text>
        {R >= 50 && <text x={cx} y={cy} dy="1.55em" textAnchor="middle">{cortar(`${fmt(d.tipo, d.valor)} de ${fmt(d.tipo, d.meta)}`, r * 1.6)}</text>}
        {R >= 64 && <text x={cx} y={cy} dy="2.9em" textAnchor="middle" className="gr-sutil">{f >= 1 ? '¡meta cumplida!' : d.etiqueta}</text>}
      </g>
    </Svg>
  )
}

/** Embudo: etapas del estado (en el orden de sus opciones) con el % que pasa de una a la siguiente. */
function Embudo({ w, h, d, ix }) {
  const { items } = d
  const max = Math.max(1e-9, ...items.map((i) => i.valor))
  const n = items.length
  const conPaso = w >= 300
  const anchoMax = (conPaso ? w - 92 : w - 8)
  const cx = conPaso ? anchoMax / 2 + 4 : w / 2
  const fila = (h - 4) / n
  const bh = Math.max(3, fila * (fila >= 30 ? 0.62 : 0.78))
  const anchoDe = (v) => Math.max(4, (v / max) * anchoMax)
  return (
    <Svg w={w} h={h} aria={`${d.pie}: ${items.map((i) => `${i.etiqueta} ${i.valor}`).join(', ')}`}>
      <g className="gr-marcas">
        {items.map((it, i) => {
          const y = 2 + fila * i + (fila - bh) / 2
          const ancho = anchoDe(it.valor)
          const sig = items[i + 1]
          const texto = `${it.etiqueta} · ${fmt('numero', it.valor)}`
          return (
            <g key={it.id} className={`gr-m${ix.c(it.id)}`} {...ix.p(it.id, it.etiqueta, [[d.modo === 'acumulado' ? 'Llegaron a esta etapa' : 'En esta etapa', fmt('numero', it.valor), it.color],
              ...(d.modo === 'acumulado' ? [['Están en ella ahora', fmt('numero', it.actual)]] : []),
              ...(i > 0 ? [[`Pasan desde ${items[i - 1].etiqueta}`, fmtPct(it.paso)]] : []), ['Del inicio', fmtPct(E.porcentajeDelTotal(it.valor, items[0].valor))]])}>
              <rect className="gr-hit" x="0" y={2 + fila * i} width={w} height={fila} />
              {sig && fila - bh >= 4 && <polygon className="gr-union gr-aparece" points={`${cx - ancho / 2},${y + bh} ${cx + ancho / 2},${y + bh} ${cx + anchoDe(sig.valor) / 2},${y + fila} ${cx - anchoDe(sig.valor) / 2},${y + fila}`} style={{ fill: it.color, '--i': tope(i) + 2 }} />}
              <rect className="gr-centro-x" x={cx - ancho / 2} y={y} width={ancho} height={bh} rx={Math.min(6, bh / 3)} style={{ fill: it.color, '--i': tope(i) }} />
              {bh >= 13 && <text className="gr-halo gr-aparece" x={cx} y={y + bh / 2} dy="0.35em" textAnchor="middle" style={{ '--i': tope(i) }}>{cortar(texto, Math.max(anchoMax * 0.9, 60))}</text>}
              {conPaso && i > 0 && <text className="gr-paso gr-aparece" x={w - 4} y={y - (fila - bh) / 2} dy="0.35em" textAnchor="end" style={{ '--i': tope(i) + 3 }}>↓ {fmtPct(it.paso)}</text>}
            </g>
          )
        })}
      </g>
    </Svg>
  )
}

/** Treemap «squarified» (Bruls et al.): rectángulos lo más cuadrados posible, área ∝ valor. */
function squarify(items, x, y, w, h) {
  const total = sumaDe(items.map((i) => i.valor))
  if (!(total > 0) || w <= 0 || h <= 0) return []
  const k = (w * h) / total
  const resto = items.map((it) => ({ it, a: it.valor * k }))
  const out = []
  let r = { x, y, w, h }
  const peor = (fila, lado) => { const s = sumaDe(fila.map((f) => f.a)); return Math.max(...fila.map((f) => Math.max((lado * lado * f.a) / (s * s), (s * s) / (lado * lado * f.a)))) }
  while (resto.length) {
    const lado = Math.min(r.w, r.h)
    const fila = [resto.shift()]
    while (resto.length && peor([...fila, resto[0]], lado) <= peor(fila, lado)) fila.push(resto.shift())
    const s = sumaDe(fila.map((f) => f.a))
    if (r.w >= r.h) {
      const cw = r.h ? s / r.h : 0; let yy = r.y
      for (const f of fila) { const hh = cw ? f.a / cw : 0; out.push({ it: f.it, x: r.x, y: yy, w: cw, h: hh }); yy += hh }
      r = { x: r.x + cw, y: r.y, w: r.w - cw, h: r.h }
    } else {
      const ch = r.w ? s / r.w : 0; let xx = r.x
      for (const f of fila) { const ww = ch ? f.a / ch : 0; out.push({ it: f.it, x: xx, y: r.y, w: ww, h: ch }); xx += ww }
      r = { x: r.x, y: r.y + ch, w: r.w, h: r.h - ch }
    }
  }
  return out
}
function Arbol({ w, h, d, ix }) {
  const { tipo, total } = d
  const items = d.items.filter((i) => i.valor > 0).sort((a, b) => b.valor - a.valor)
  const celdas = squarify(items, 0, 0, w, h)
  return (
    <Svg w={w} h={h} aria={`${d.pie}: ${items.map((i) => `${i.etiqueta} ${fmt(tipo, i.valor)}`).join(', ')}`}>
      <g className="gr-marcas">
        {celdas.map(({ it, x, y, w: cw, h: ch }, i) => {
          const pct = fmtPct(it.valor / total)
          return (
            <g key={it.id} className={`gr-m${ix.c(it.id)}`} {...ix.p(it.id, it.larga, [[d.que, fmt(tipo, it.valor), it.color], ['Del total', pct], ['Registros', fmt('numero', it.n)]])}>
              <rect className="gr-centro" x={x + 1} y={y + 1} width={Math.max(0, cw - 2)} height={Math.max(0, ch - 2)} rx={Math.min(8, cw / 4, ch / 4)} style={{ fill: it.color, '--i': tope(i) }} />
              {cw >= 46 && ch >= 24 && <text className="gr-halo gr-aparece" x={x + 8} y={y + 16} style={{ '--i': tope(i) + 2 }}>{cortar(it.etiqueta, cw - 14)}</text>}
              {cw >= 46 && ch >= 40 && <text className="gr-halo gr-fuerte gr-aparece" x={x + 8} y={y + 31} style={{ '--i': tope(i) + 2 }}>{cortar(fmt(tipo, it.valor), cw - 14)}</text>}
              {cw >= 46 && ch >= 56 && <text className="gr-halo gr-aparece" x={x + 8} y={y + 46} style={{ '--i': tope(i) + 2 }}>{pct}</text>}
            </g>
          )
        })}
      </g>
    </Svg>
  )
}

function Radar({ w, h, d, ix }) {
  const { items, tipo } = d
  const n = items.length
  const conEtq = w >= 200 && h >= 140
  const margenX = conEtq ? Math.min(78, Math.max(...items.map((i) => anchoTexto(i.etiqueta))) + 10) : 6
  const R = Math.max(12, Math.min(w / 2 - margenX, h / 2 - (conEtq ? 18 : 6)))
  const cx = w / 2; const cy = h / 2 + (conEtq ? 2 : 0)
  const tk = ticks(0, Math.max(0, ...items.map((i) => i.valor)), 4, d.entero)
  const max = tk[tk.length - 1] || 1
  const ang = (i) => -Math.PI / 2 + (i * 2 * Math.PI) / n
  const pt = (i, v) => [cx + Math.cos(ang(i)) * R * (v / max), cy + Math.sin(ang(i)) * R * (v / max)]
  const poly = items.map((it, i) => pt(i, it.valor).map((z) => z.toFixed(1)).join(',')).join(' ')
  return (
    <Svg w={w} h={h} aria={`${d.pie}: ${items.map((i) => `${i.etiqueta} ${fmt(tipo, i.valor)}`).join(', ')}`}>
      <g className="gr-rejilla" aria-hidden="true">
        {tk.slice(1).map((v) => <polygon key={v} points={items.map((_, i) => pt(i, v).join(',')).join(' ')} />)}
        {items.map((it, i) => { const [x, y] = pt(i, max); return <line key={it.id} x1={cx} y1={cy} x2={x} y2={y} /> })}
        {R >= 60 && tk.slice(1).map((v) => <text key={v} x={cx + 4} y={cy - R * (v / max)} dy="0.9em" className="gr-sutil">{fmt(tipo, v)}</text>)}
      </g>
      <polygon className="gr-radar gr-centro-v" points={poly} style={{ fill: ACENTO, stroke: ACENTO, transformOrigin: `${cx}px ${cy}px` }} />
      <g className="gr-marcas">
        {items.map((it, i) => {
          const [x, y] = pt(i, it.valor)
          const [lx, ly] = pt(i, max * 1.12)
          const c = Math.cos(ang(i))
          return (
            <g key={it.id} className={`gr-m${ix.c(it.id)}`} {...ix.p(it.id, it.larga, [[d.que, fmt(tipo, it.valor), it.color], ['Del total', fmtPct(E.porcentajeDelTotal(it.valor, d.total))]])}>
              <circle className="gr-hit" cx={x} cy={y} r="12" />
              <circle className="gr-punto" cx={x} cy={y} r={ix.activo === it.id ? 6 : 4} style={{ fill: it.color, stroke: 'var(--card)', '--i': tope(i) + 4 }} />
              {conEtq && <text x={lx} y={ly} dy="0.35em" textAnchor={c > 0.3 ? 'start' : c < -0.3 ? 'end' : 'middle'}>{cortar(it.etiqueta, margenX - 4)}</text>}
            </g>
          )
        })}
      </g>
    </Svg>
  )
}

/** Ejes numéricos libres (dispersión y burbujas). */
function ejesXY(w, h, { xmin, xmax, ymin, ymax, fx, fy, xFecha }) {
  const ty = ticks(ymin, ymax, h < 130 ? 2 : 4)
  const textosY = ty.map(fy)
  const necesita = Math.max(...textosY.map((t) => anchoTexto(t))) + 10
  const conY = w >= 170 && h >= 80 && necesita <= w * 0.4
  const izq = conY ? necesita : 6
  const conX = h >= 70
  const x0 = izq; const x1 = w - 12; const y1 = 10; const y0 = h - (conX ? 20 : 6)
  let tx
  if (xFecha) {
    const n = Math.max(2, Math.min(5, Math.floor((x1 - x0) / 70)))
    tx = Array.from({ length: n }, (_, i) => xmin + ((xmax - xmin) * i) / (n - 1))
  } else tx = ticks(xmin, xmax, Math.max(2, Math.min(5, Math.floor((x1 - x0) / 70))))
  const X = escala(xFecha ? xmin : tx[0], xFecha ? (xmax > xmin ? xmax : xmin + 1) : tx[tx.length - 1], x0, x1)
  const Y = escala(ty[0], ty[ty.length - 1], y0, y1)
  return { x0, x1, y0, y1, X, Y, tx, ty, textosY, conY, conX, fx }
}
function RejillaXY({ e }) {
  return (
    <g className="gr-rejilla" aria-hidden="true">
      {e.ty.map((v, i) => <g key={`y${i}`}><line x1={e.x0} x2={e.x1} y1={e.Y(v)} y2={e.Y(v)} />{e.conY && <text x={e.x0 - 6} y={e.Y(v)} dy="0.35em" textAnchor="end">{e.textosY[i]}</text>}</g>)}
      {e.conX && e.tx.map((v, i) => <text key={`x${i}`} x={e.X(v)} y={e.y0 + 14} textAnchor={i === 0 && e.X(v) - e.x0 < 20 ? 'start' : i === e.tx.length - 1 ? 'end' : 'middle'}>{e.fx(v)}</text>)}
    </g>
  )
}

function Dispersion({ w, h, d, ix, uid }) {
  const { puntos } = d
  const xs = puntos.map((p) => p.x); const ys = puntos.map((p) => p.y)
  const ley = d.series.length > 1 ? planLeyenda(w, h, d.series) : { lado: null }
  const a = areaCon(ley, w, h)
  const e = ejesXY(a.w, a.h, { xmin: Math.min(...xs), xmax: Math.max(...xs), ymin: Math.min(0, ...ys), ymax: Math.max(0, ...ys), fx: d.fx, fy: d.fy, xFecha: d.xFecha })
  const tl = d.tl
  const xa = Math.min(...xs); const xb = Math.max(...xs)
  const r = puntos.length > 120 ? 3 : 4
  return (
    <Svg w={w} h={h} aria={d.pie}>
      <defs><clipPath id={`gr-clip-${uid}`}><rect x={e.x0} y={e.y1} width={Math.max(0, e.x1 - e.x0)} height={Math.max(0, e.y0 - e.y1)} /></clipPath></defs>
      <RejillaXY e={e} />
      {tl.n >= 2 && xb > xa && <line className="gr-tendencia gr-aparece" clipPath={`url(#gr-clip-${uid})`} x1={e.X(xa)} y1={e.Y(tl.en(d.xFecha ? xa / 864e5 : xa))} x2={e.X(xb)} y2={e.Y(tl.en(d.xFecha ? xb / 864e5 : xb))} style={{ stroke: COLORES[2], '--i': 14 }} />}
      <g className="gr-marcas">
        {puntos.map((pt, i) => (
          <circle key={pt.id} className={`gr-punto gr-m${ix.c(pt.id, pt.serie)}`} cx={e.X(pt.x)} cy={e.Y(pt.y)} r={ix.activo === pt.id ? r + 2.5 : r}
            style={{ fill: pt.color, fillOpacity: 0.78, stroke: pt.color, '--i': tope(Math.floor(i / 6)) }}
            {...ix.p(pt.id, pt.titulo, [[d.nx, d.fx(pt.x, true)], [d.ny, d.fy(pt.y), pt.color], ...(pt.serieNombre ? [[d.ne, pt.serieNombre, pt.color]] : [])])} />
        ))}
      </g>
      {ley.lado && <Leyenda plan={ley} w={w} h={h} ix={ix} items={d.series} />}
    </Svg>
  )
}

function Burbujas({ w, h, d, ix }) {
  const { items, tipo } = d
  const e = ejesXY(w, h, { xmin: 0, xmax: Math.max(...items.map((i) => i.n)) * 1.15, ymin: 0, ymax: Math.max(...items.map((i) => i.prom)) * 1.18, fx: (v) => fmt('numero', v), fy: (v) => fmt(tipo, v) })
  const maxS = Math.max(1e-9, ...items.map((i) => i.suma))
  const rMax = Math.max(6, Math.min(e.x1 - e.x0, e.y0 - e.y1) / 6.5)
  const orden = [...items].sort((a, b) => b.suma - a.suma)
  const conEtiqueta = []
  const etiquetar = (x, y, r) => {
    if (r < 15 || conEtiqueta.some((o) => Math.hypot(o.x - x, o.y - y) < (o.r + r) * 0.75)) return false
    conEtiqueta.push({ x, y, r }); return true
  }
  return (
    <Svg w={w} h={h} aria={d.pie}>
      <RejillaXY e={e} />
      <g className="gr-marcas">
        {orden.map((it, i) => {
          const r = Math.max(4, rMax * Math.sqrt(Math.max(0, it.suma) / maxS))
          const x = e.X(it.n); const y = e.Y(it.prom)
          return (
            <g key={it.id} className={`gr-m${ix.c(it.id)}`} {...ix.p(it.id, it.etiqueta, [['Registros', fmt('numero', it.n)], [`Promedio de ${d.nv}`, fmt(tipo, it.prom), it.color], [`Total de ${d.nv}`, fmt(tipo, it.suma)]])}>
              <circle className="gr-centro gr-burbuja" cx={x} cy={y} r={r} style={{ fill: it.color, stroke: it.color, '--i': tope(i) }} />
              {etiquetar(x, y, r) && <text className="gr-halo gr-aparece" x={x} y={y} dy="0.35em" textAnchor="middle" style={{ '--i': tope(i) + 3 }} pointerEvents="none">{cortar(it.etiqueta, r * 2 - 6)}</text>}
            </g>
          )
        })}
      </g>
    </Svg>
  )
}

function Histograma({ w, h, d, ix }) {
  const { bins, tipo, prom, med } = d
  const p = plano(w, h, { max: Math.max(...bins.map((b) => b.conteo)), f: (v) => fmt('numero', v), entero: true, arriba: 14 })
  const banda = p.ancho / bins.length
  const X = escala(bins[0].desde, bins[bins.length - 1].hasta, p.x0, p.x1)
  const una = bins.length === 1
  const etiquetas = bins.map((b, i) => ({ x: p.x0 + banda * i + (una ? banda / 2 : 0), t: fmt(tipo, b.desde) }))
  return (
    <Svg w={w} h={h} aria={`${d.pie}: ${bins.map((b) => `${fmt(tipo, b.desde)}–${fmt(tipo, b.hasta)}: ${b.conteo}`).join(', ')}`}>
      <Rejilla p={p} />
      <g className="gr-marcas">
        {bins.map((b, i) => {
          const id = `b${i}`
          const ya = p.y(b.conteo)
          return (
            <g key={id} className={`gr-m${ix.c(id)}`} {...ix.p(id, `${fmt(tipo, b.desde)} – ${fmt(tipo, b.hasta)}`, [['Registros', fmt('numero', b.conteo), ACENTO], ['Del total', fmtPct(E.porcentajeDelTotal(b.conteo, d.n))]])}>
              <rect className="gr-hit" x={p.x0 + banda * i} y={p.y1} width={banda} height={p.alto} />
              <rect className="gr-sube" x={p.x0 + banda * i + 0.5} y={ya} width={Math.max(1, banda - 1.5)} height={Math.max(b.conteo ? 1 : 0, p.y0 - ya)} rx="2" style={{ fill: ACENTO, '--i': tope(i) }} />
            </g>
          )
        })}
      </g>
      {!una && [['promedio', prom, COLORES[2]], ['mediana', med, COLORES[5]]].map(([t, v, c], k) => (
        <g key={t} className="gr-aparece" style={{ '--i': 16 + k }} pointerEvents="none">
          <line className="gr-marca-v" x1={X(v)} x2={X(v)} y1={p.y1 - 4} y2={p.y0} style={{ stroke: c }} />
          {w >= 260 && <text x={X(v) + (k ? -4 : 4)} y={p.y1 + 2 + k * 13} textAnchor={k ? 'end' : 'start'} style={{ fill: c }} className="gr-fuerte">{t}</text>}
        </g>
      ))}
      {p.conX && <g className="gr-ejex" aria-hidden="true">
        {(() => { const paso = Math.max(1, Math.ceil((Math.max(...etiquetas.map((e) => anchoTexto(e.t))) + 8) / banda)); return etiquetas.map((e, i) => i % paso === 0 && <text key={i} x={e.x} y={p.y0 + 14} textAnchor={una ? 'middle' : i === 0 ? 'start' : 'middle'}>{e.t}</text>) })()}
      </g>}
    </Svg>
  )
}

function Caja({ w, h, d, ix }) {
  const { cajas, tipo } = d
  const conCaja = cajas.filter((c) => c.q)
  const p = plano(w, h, { min: Math.min(0, ...conCaja.map((c) => c.q.min)), max: Math.max(...conCaja.map((c) => c.q.max)), f: (v) => fmt(tipo, v), etiquetas: cajas.length > 1 })
  const banda = p.ancho / cajas.length
  const bw = Math.max(6, Math.min(54, banda * 0.5))
  return (
    <Svg w={w} h={h} aria={`${d.pie}: ${conCaja.map((c) => `${c.etiqueta}: mín ${fmt(tipo, c.q.min)}, Q1 ${fmt(tipo, c.q.q1)}, mediana ${fmt(tipo, c.q.mediana)}, Q3 ${fmt(tipo, c.q.q3)}, máx ${fmt(tipo, c.q.max)}`).join('; ')}`}>
      <Rejilla p={p} />
      <g className="gr-marcas">
        {cajas.map((c, i) => {
          if (!c.q) return null
          const xc = p.x0 + banda * (i + 0.5)
          const { q } = c
          return (
            <g key={c.id} className={`gr-m${ix.c(c.id)}`} {...ix.p(c.id, c.etiqueta, [['Máximo', fmt(tipo, q.max)], ['Q3 (75 %)', fmt(tipo, q.q3)], ['Mediana', fmt(tipo, q.mediana), c.color], ['Q1 (25 %)', fmt(tipo, q.q1)], ['Mínimo', fmt(tipo, q.min)], ['Registros', fmt('numero', q.n)]])}>
              <rect className="gr-hit" x={p.x0 + banda * i} y={p.y1} width={banda} height={p.alto} />
              <g className="gr-centro-y" style={{ '--i': tope(i) }}>
                <line className="gr-bigote" x1={xc} x2={xc} y1={p.y(q.max)} y2={p.y(q.q3)} style={{ stroke: c.color }} />
                <line className="gr-bigote" x1={xc} x2={xc} y1={p.y(q.q1)} y2={p.y(q.min)} style={{ stroke: c.color }} />
                <line className="gr-bigote" x1={xc - bw / 4} x2={xc + bw / 4} y1={p.y(q.max)} y2={p.y(q.max)} style={{ stroke: c.color }} />
                <line className="gr-bigote" x1={xc - bw / 4} x2={xc + bw / 4} y1={p.y(q.min)} y2={p.y(q.min)} style={{ stroke: c.color }} />
                <rect className="gr-caja" x={xc - bw / 2} y={p.y(q.q3)} width={bw} height={Math.max(1, p.y(q.q1) - p.y(q.q3))} rx="3" style={{ fill: c.color, stroke: c.color }} />
                <line className="gr-mediana" x1={xc - bw / 2} x2={xc + bw / 2} y1={p.y(q.mediana)} y2={p.y(q.mediana)} />
              </g>
            </g>
          )
        })}
      </g>
      <EjeX p={p} items={cajas.length > 1 ? cajas.map((c, i) => ({ x: p.x0 + banda * (i + 0.5), t: c.etiqueta })) : []} />
    </Svg>
  )
}

/** Calendario de calor estilo GitHub: columnas = semanas (lunes a domingo). */
function Calendario({ w, h, d, ix }) {
  const conDias = w >= 220 && h >= 100
  const conMeses = h >= 90
  const conLey = h >= 150 && w >= 240
  const izq = conDias ? 28 : 2
  const arriba = conMeses ? 16 : 2
  const abajo = conLey ? 20 : 2
  const gap = 3
  let cols = d.semanas
  let s = Math.min((w - izq) / cols - gap, (h - arriba - abajo) / 7 - gap)
  if (s < 6) { cols = Math.max(1, Math.floor((w - izq) / (6 + gap))); s = Math.min((w - izq) / cols - gap, (h - arriba - abajo) / 7 - gap) }
  s = Math.max(3, Math.min(22, s))
  const celdas = d.celdas.slice(-cols * 7)
  const anchoTotal = cols * (s + gap)
  const x0 = izq + Math.max(0, (w - izq - anchoTotal) / 2)
  const y0 = arriba + Math.max(0, (h - arriba - abajo - 7 * (s + gap)) / 2)
  const nivel = (v) => (v <= 0 ? 0 : Math.max(1, Math.ceil((v / d.max) * 4)))
  const OPAC = [0, 0.3, 0.52, 0.76, 1]
  const meses = []
  celdas.forEach((c, i) => { if (i % 7 === 0) { const col = i / 7; const m = c.fecha.getMonth(); if (!meses.length || meses[meses.length - 1].m !== m) meses.push({ m, col }) } })
  return (
    <Svg w={w} h={h} aria={`${d.pie}: ${d.totalTexto}`}>
      {conMeses && meses.map(({ m, col }, i) => (i > 0 || meses.length === 1 || (meses[1]?.col ?? 99) - col >= 3) && <text key={`${m}-${col}`} x={x0 + col * (s + gap)} y={y0 - 5} className="gr-sutil">{E.MESES[m]}</text>)}
      {conDias && [0, 2, 4].map((r) => <text key={r} x={x0 - 6} y={y0 + r * (s + gap) + s / 2} dy="0.35em" textAnchor="end" className="gr-sutil">{['lun', 'mar', 'mié', 'jue', 'vie', 'sáb', 'dom'][r]}</text>)}
      <g className="gr-marcas">
        {celdas.map((c, i) => {
          const col = Math.floor(i / 7); const fila = i % 7
          const lv = nivel(c.v)
          return (
            <rect key={c.iso} className={`gr-celda gr-centro${c.futuro ? ' gr-futuro' : ''}${c.hoy ? ' gr-hoy' : ''}${ix.c(c.iso)}`} x={x0 + col * (s + gap)} y={y0 + fila * (s + gap)} width={s} height={s} rx={Math.min(3, s / 4)}
              style={{ fill: lv ? ACENTO : undefined, fillOpacity: lv ? OPAC[lv] : undefined, '--i': tope(col, 30) }}
              {...ix.p(c.iso, fechaLarga(c.fecha), [[d.que, fmt(d.tipo, c.v), lv ? ACENTO : undefined], ...(c.futuro ? [['', 'día por venir']] : [])])} />
          )
        })}
      </g>
      {conLey && (
        <g className="gr-aparece" style={{ '--i': 20 }} transform={`translate(${w - 100},${h - 9})`}>
          <text x="-4" dy="0.35em" textAnchor="end" className="gr-sutil">Menos</text>
          {OPAC.map((o, k) => <rect key={k} className="gr-celda" x={k * 14} y="-5.5" width="11" height="11" rx="2.5" style={{ fill: k ? ACENTO : undefined, fillOpacity: k ? o : undefined }} />)}
          <text x={5 * 14 + 2} dy="0.35em" className="gr-sutil">Más</text>
        </g>
      )}
    </Svg>
  )
}

/** Cascada: valor del primer mes, variación de cada mes contra el anterior y valor final. */
function Cascada({ w, h, d, ix }) {
  const { barras, tipo } = d
  const niveles = barras.flatMap((b) => [b.desde, b.hasta])
  const p = plano(w, h, { min: Math.min(0, ...niveles), max: Math.max(0, ...niveles), f: (v) => fmt(tipo, v), entero: d.entero, arriba: 14 })
  const banda = p.ancho / barras.length
  const bw = Math.max(2, Math.min(44, banda * 0.62))
  const conValor = p.alto >= 90
  return (
    <Svg w={w} h={h} aria={`${d.pie}: ${barras.map((b) => `${b.larga} ${b.texto}`).join(', ')}`}>
      <Rejilla p={p} />
      <g className="gr-marcas">
        {barras.map((b, i) => {
          const xc = p.x0 + banda * (i + 0.5)
          const ya = p.y(Math.max(b.desde, b.hasta)); const yb = p.y(Math.min(b.desde, b.hasta))
          const color = b.tipo === 'total' ? ACENTO : b.hasta >= b.desde ? VERDE : ROJO
          const sig = barras[i + 1]
          return (
            <g key={b.id} className={`gr-m${ix.c(b.id)}`} {...ix.p(b.id, b.larga, b.tipo === 'total' ? [[d.que, fmt(tipo, b.hasta), color]] : [['Cambio', b.texto, color], ['Antes', fmt(tipo, b.desde)], ['Después', fmt(tipo, b.hasta)], ['Variación', fmtPct(E.variacion(b.hasta, b.desde), true)]])}>
              <rect className="gr-hit" x={p.x0 + banda * i} y={p.y1} width={banda} height={p.alto} />
              <rect className={b.hasta >= b.desde ? 'gr-sube' : 'gr-baja'} x={xc - bw / 2} y={ya} width={bw} height={Math.max(1, yb - ya)} rx="2.5" style={{ fill: color, '--i': tope(i) }} />
              {sig && <line className="gr-conector gr-aparece" x1={xc + bw / 2} x2={xc + banda - bw / 2} y1={p.y(b.hasta)} y2={p.y(b.hasta)} style={{ '--i': tope(i) + 1 }} />}
              {conValor && anchoTexto(b.corto) <= banda - 2 && <text className="gr-valor gr-aparece" x={xc} y={ya - 5} textAnchor="middle" style={{ '--i': tope(i) }}>{b.corto}</text>}
            </g>
          )
        })}
      </g>
      <EjeX p={p} items={barras.map((b, i) => ({ x: p.x0 + banda * (i + 0.5), t: b.etiqueta }))} />
    </Svg>
  )
}

/** KPI: valor del mes en curso, flecha de variación contra el mes anterior y sparkline de 12 meses. */
function Kpi({ w, h, d, ix, uid }) {
  const fila = w >= 360 && h < 170
  const tam = Math.round(Math.max(18, Math.min(40, w / 7, h / (fila ? 2.6 : 3.4))))
  const sw = fila ? Math.round(w * 0.42) : w - 4
  const sh = fila ? h - 20 : Math.max(0, h - tam - 58)
  const conSpark = sh >= 22 && sw >= 60
  const vals = d.items.map((i) => i.valor)
  const max = Math.max(1e-9, ...vals); const min = Math.min(0, ...vals)
  const X = escala(0, Math.max(1, vals.length - 1), 4, sw - 4)
  const Y = escala(min, max, sh - 4, 4)
  const linea = vals.map((v, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)},${Y(v).toFixed(1)}`).join(' ')
  const gid = `gr-kdeg-${uid}`
  const v = d.var
  const clase = v === null ? 'neutro' : v > 0 ? 'sube' : v < 0 ? 'baja' : 'neutro'
  const activo = d.items.findIndex((it) => it.id === ix.activo)
  return (
    <div className={`gr-kpi${fila ? ' gr-kpi-fila' : ''}`}>
      <div className="gr-kpi-txt">
        <small>{d.etiqueta}</small>
        <strong style={{ fontSize: tam }}><Cuenta v={d.actual} f={(x) => fmt(d.tipo, x)} /></strong>
        <span className={`gr-var ${clase}`}>
          <b>{v === null ? (d.anterior === 0 && d.actual > 0 ? '▲ nuevo' : '—') : v > 0 ? `▲ ${fmtPct(v)}` : v < 0 ? `▼ ${fmtPct(-v)}` : '= 0 %'}</b>
          {w >= 200 && <i> vs {d.mesAnterior} ({fmt(d.tipo, d.anterior)})</i>}
        </span>
      </div>
      {conSpark && (
        <svg className="gr-svg gr-spark" width={sw} height={sh} viewBox={`0 0 ${sw} ${sh}`} role="img" aria-label={`Últimos ${vals.length} meses: ${d.items.map((i) => `${i.larga} ${fmt(d.tipo, i.valor)}`).join(', ')}`}>
          <defs><linearGradient id={gid} x1="0" y1="0" x2="0" y2="1"><stop offset="0" style={{ stopColor: ACENTO, stopOpacity: 0.3 }} /><stop offset="1" style={{ stopColor: ACENTO, stopOpacity: 0 }} /></linearGradient></defs>
          <path className="gr-area" d={`${linea} L${X(vals.length - 1)},${sh} L${X(0)},${sh} Z`} style={{ fill: `url(#${gid})` }} />
          <path className="gr-traza gr-linea" d={linea} pathLength="1" style={{ stroke: ACENTO }} />
          <circle className="gr-punto gr-ultimo" cx={X(vals.length - 1)} cy={Y(vals[vals.length - 1])} r="3.5" style={{ fill: ACENTO, '--i': 14 }} />
          {activo >= 0 && <circle cx={X(activo)} cy={Y(vals[activo])} r="4" style={{ fill: ACENTO }} />}
          {d.items.map((it, i) => <rect key={it.id} className="gr-hit" x={X(i) - sw / vals.length / 2} y="0" width={sw / vals.length} height={sh} {...ix.p(it.id, it.larga, [[d.que, fmt(d.tipo, it.valor), ACENTO]])} />)}
        </svg>
      )}
    </div>
  )
}

/** Tabla de posiciones: top N por un campo texto, con barra relativa al primero. */
function Posiciones({ h, d, ix }) {
  const { items, tipo, total } = d
  const max = Math.max(1e-9, ...items.map((i) => i.valor))
  const compacta = h < items.length * 42 // filas normales ≈ 42 px; si no caben, se juntan (y si aún no caben, desplaza)
  return (
    <ol className={`gr-pos${compacta ? ' compacta' : ''}${h < items.length * 29 ? ' desborda' : ''}`} aria-label={d.pie}>
      {items.map((it, i) => (
        <li key={it.id} className={`gr-m gr-fila${ix.c(it.id)}`} style={{ '--i': i }} {...ix.p(it.id, it.etiqueta, [[d.que, fmt(tipo, it.valor), ACENTO], ['Del total', fmtPct(E.porcentajeDelTotal(it.valor, total))], ['Registros', fmt('numero', it.n)]])}>
          <b className="gr-pos-n">{i + 1}</b>
          <span className="gr-pos-t" title={it.etiqueta}>{it.etiqueta}</span>
          <em><Cuenta v={it.valor} f={(x) => fmt(tipo, x)} /></em>
          <i className="gr-pos-barra"><b className="gr-crece-h" style={{ width: `${(Math.max(0, it.valor) / max) * 100}%`, '--i': i }} /></i>
        </li>
      ))}
    </ol>
  )
}

/** Tarjeta de estadísticas de un campo numérico o de dinero. */
function Estadisticas({ w, h, d, ix }) {
  const { tipo, s } = d
  const tiles = [
    ['Promedio', s.promedio, 'Suma ÷ cantidad de registros con valor'],
    ['Mediana', s.mediana, 'El valor del medio: la mitad está por debajo'],
    ['Mínimo', s.min, 'El valor más bajo'],
    ['Máximo', s.max, 'El valor más alto'],
    ['Desviación', s.desv, 'Desviación estándar muestral: qué tanto se alejan los valores del promedio'],
    ['Total', s.suma, `Suma de ${s.n} registros con valor`],
  ]
  let cols = w < 260 ? 2 : w >= 560 && h < 200 ? 6 : 3
  const lista = h < Math.ceil(6 / cols) * 46 // las casillas no caben: renglones «etiqueta … valor»
  // En lista, solo tantas columnas como quepan con «etiqueta + valor» completos (lo que sobra desplaza, con desvanecido).
  const largo = Math.max(...[s.promedio, s.mediana, s.min, s.max, s.desv, s.suma].map((v) => anchoTexto(fmt(tipo, v), 12))) + 78
  if (lista) cols = Math.max(1, Math.min(3, Math.floor((w + 14) / (largo + 14))))
  const desborda = lista && h < Math.ceil(6 / cols) * 17
  const anchoCasilla = (w - (cols - 1) * 6) / cols - 20
  const letra = (txt) => Math.max(12, Math.min(16, anchoCasilla / Math.max(1, String(txt).length * 0.6)))
  const conTira = !lista && h >= Math.ceil(6 / cols) * 46 + 42 && s.q && s.max > s.min
  const X = s.q ? escala(s.min, s.max > s.min ? s.max : s.min + 1, 8, w - 8) : null
  return (
    <div className={`gr-stats${lista ? ' lista' : ''}${desborda ? ' desborda' : ''}`} style={{ '--cols': cols }}>
      <div className="gr-stats-rej">
        {tiles.map(([t, v, ayuda], i) => (
          <div key={t} className={`gr-stat gr-m gr-fila${ix.c(t)}`} style={{ '--i': i }} {...ix.p(t, t, [[ayuda, '']])}>
            <small>{t}</small><strong style={lista ? undefined : { fontSize: letra(fmt(tipo, v)) }}><Cuenta v={v} f={(x) => fmt(tipo, x)} /></strong>
          </div>
        ))}
      </div>
      {conTira && (
        <svg className="gr-svg gr-tira gr-aparece" style={{ '--i': 8 }} width={w} height="34" viewBox={`0 0 ${w} 34`} role="img" aria-label={`Distribución: Q1 ${fmt(tipo, s.q.q1)}, mediana ${fmt(tipo, s.q.mediana)}, Q3 ${fmt(tipo, s.q.q3)}`}>
          <line className="gr-bigote" x1={X(s.min)} x2={X(s.max)} y1="10" y2="10" style={{ stroke: ACENTO }} />
          <rect className="gr-caja" x={X(s.q.q1)} y="3" width={Math.max(1, X(s.q.q3) - X(s.q.q1))} height="14" rx="3" style={{ fill: ACENTO, stroke: ACENTO }} />
          <line className="gr-mediana" x1={X(s.q.mediana)} x2={X(s.q.mediana)} y1="3" y2="17" />
          <text x={X(s.min)} y="30" className="gr-sutil">{fmt(tipo, s.min)}</text>
          <text x={X(s.max)} y="30" textAnchor="end" className="gr-sutil">{fmt(tipo, s.max)}</text>
          {w >= 300 && <text x={X(s.q.mediana)} y="30" textAnchor="middle" className="gr-sutil">mediana</text>}
        </svg>
      )}
    </div>
  )
}

// ── Cálculos específicos ──────────────────────────────────────────────────────────────────────────
function calcEmbudo(regs, campos, o) {
  const ce = campoDe(campos, o.estado)
  if (!ce) return FALTA
  const excluir = o.excluir || []
  const grupos = E.agrupar(regs, ce).filter((g) => g.indice >= 0 && !excluir.includes(g.clave))
  const actuales = grupos.map((g) => g.registros.length)
  if (!sumaDe(actuales)) return SIN_DATOS
  const modo = o.modo === 'actual' ? 'actual' : 'acumulado'
  // Acumulado: «llegaron al menos a esta etapa» = están en ella o en una posterior (supone que las opciones van en orden de avance).
  const valores = modo === 'acumulado' ? actuales.map((_, i) => sumaDe(actuales.slice(i))) : actuales
  const items = grupos.map((g, i) => ({ id: g.clave, etiqueta: g.etiqueta, valor: valores[i], actual: actuales[i], color: COLORES[g.indice % COLORES.length], paso: i > 0 && valores[i - 1] ? valores[i] / valores[i - 1] : null }))
  return { items, modo, pie: `${modo === 'acumulado' ? 'Llegaron a cada etapa' : 'Registros en cada etapa'} de ${ce.nombre.toLowerCase()}${excluir.length ? ` (sin ${excluir.join(', ')})` : ''}` }
}

function calcCalendario(regs, campos, o, hoy) {
  const cf = campoDe(campos, o.fecha)
  if (!cf) return FALTA
  const dias = E.agruparPorDia(regs, cf.id)
  const hoy0 = new Date(hoy.getFullYear(), hoy.getMonth(), hoy.getDate())
  // Termina en la semana de hoy, o en la del último día con datos si cae en las próximas 8 semanas (agendas, entregas).
  let fin = hoy0
  for (const k of dias.keys()) { const f = E.deIso(k); if (f > fin && f - hoy0 <= 56 * 864e5) fin = f }
  const semanas = Math.max(4, Math.min(53, Math.floor(o.semanas || 16)))
  const domingo = new Date(fin); domingo.setDate(fin.getDate() + (6 - ((fin.getDay() + 6) % 7)))
  const ini = new Date(domingo); ini.setDate(domingo.getDate() - (semanas * 7 - 1))
  const celdas = Array.from({ length: semanas * 7 }, (_, i) => {
    const f = new Date(ini); f.setDate(ini.getDate() + i)
    const iso = E.isoDia(f)
    return { iso, fecha: f, v: E.resumir(dias.get(iso) || [], medirDe(o), fnDe(o)) ?? 0, futuro: f > hoy0, hoy: f.getTime() === hoy0.getTime() }
  })
  const total = sumaDe(celdas.map((c) => c.v))
  const tipo = tipoDe(o, campos)
  return { celdas, semanas, max: Math.max(1e-9, ...celdas.map((c) => c.v)), tipo, que: queMide(o, campos), totalTexto: `${fmt(tipo, total)} en ${semanas} semanas`,
    pie: `${queMide(o, campos)} por día de ${cf.nombre.toLowerCase()} · ${fechaCorta(ini)} – ${fechaCorta(domingo)}` }
}

function calcCascada(regs, campos, o, hoy) {
  const m = calcMeses(regs, campos, o, hoy)
  if (typeof m === 'string') return m
  const { items, tipo } = m
  if (!items.some((i) => i.valor)) return SIN_DATOS
  const signo = (x) => `${x > 0 ? '+' : x < 0 ? '−' : ''}${fmt(tipo, Math.abs(x))}`
  const barras = [{ id: 'inicio', tipo: 'total', etiqueta: items[0].etiqueta, larga: `${items[0].larga} (inicio)`, desde: 0, hasta: items[0].valor, texto: fmt(tipo, items[0].valor), corto: fmt(tipo, items[0].valor) }]
  for (let i = 1; i < items.length; i++) {
    const dlt = items[i].valor - items[i - 1].valor
    barras.push({ id: items[i].id, tipo: 'cambio', etiqueta: items[i].etiqueta, larga: `${items[i].larga} vs ${items[i - 1].larga}`, desde: items[i - 1].valor, hasta: items[i].valor, texto: signo(dlt), corto: signo(dlt) })
  }
  const ult = items[items.length - 1]
  barras.push({ id: 'fin', tipo: 'total', etiqueta: 'Final', larga: `${ult.larga} (final)`, desde: 0, hasta: ult.valor, texto: fmt(tipo, ult.valor), corto: fmt(tipo, ult.valor) })
  return { barras, tipo, que: m.que, entero: m.entero, pie: `${m.que}: cambio mes a mes por ${nombre(campos, o.fecha)} · ${items[0].larga} – ${ult.larga}` }
}

function calcKpi(regs, campos, o, hoy) {
  const m = calcMeses(regs, campos, { ...o, meses: o.meses || 12 }, hoy)
  if (typeof m === 'string') return m
  const { items, tipo } = m
  const actual = items[items.length - 1].valor
  const anterior = items.length > 1 ? items[items.length - 2].valor : 0
  return { items, tipo, que: m.que, actual, anterior, var: E.variacion(actual, anterior), mesAnterior: items[items.length - 2]?.etiqueta || '—',
    etiqueta: `${m.que} · ${items[items.length - 1].larga}`, pie: `${m.que} por mes de ${nombre(campos, o.fecha)} · últimos ${items.length} meses` }
}

function calcMeta(regs, campos, o, hoy) {
  const m = calcMeses(regs, campos, { ...o, meses: 12 }, hoy)
  if (typeof m === 'string') return m
  const { items, tipo } = m
  const valor = items[items.length - 1].valor
  const previos = items.slice(0, -1)
  const fija = E.num(o.meta)
  let meta; let origen
  if (fija !== null && fija > 0) { meta = fija; origen = 'fijada a mano' } else {
    const mejor = previos.reduce((b, it) => (it.valor > (b?.valor ?? -Infinity) ? it : b), null)
    if (!mejor || !(mejor.valor > 0)) return 'Sin meta: aún no hay meses anteriores con datos'
    meta = mejor.valor; origen = `tu mejor mes (${mejor.larga})`
  }
  return { valor, meta, tipo, origen, etiqueta: items[items.length - 1].larga, pie: `${m.que} de ${items[items.length - 1].larga} vs meta: ${origen}` }
}

function calcMedidor(regs, campos, o) {
  const ce = campoDe(campos, o.estado)
  if (!ce) return FALTA
  const grupos = E.agrupar(regs, ce).filter((g) => g.indice >= 0)
  const total = regs.length
  if (!total) return SIN_DATOS
  // Sin `objetivo`, se mide la opción con más registros (se nombra siempre en el gráfico).
  const g = grupos.find((x) => x.clave === o.objetivo) || grupos.reduce((b, x) => (x.registros.length > b.registros.length ? x : b), grupos[0])
  return { objetivo: g.clave, n: g.registros.length, total, f: g.registros.length / total, color: COLORES[g.indice % COLORES.length], pie: `% de registros en «${g.clave}» (${ce.nombre.toLowerCase()})` }
}

function calcDispersion(regs, campos, o) {
  const cy = campoDe(campos, o.y)
  const cx = campoDe(campos, o.x)
  if (!cy || !cx) return FALTA
  const xFecha = cx.tipo === 'fecha'
  const ce = campoDe(campos, o.estado)
  const ct = campoDe(campos, o.texto)
  const puntos = []
  for (const r of regs) {
    const vy = E.num(r.valores?.[cy.id])
    const rx = r.valores?.[cx.id]
    const vx = xFecha ? (E.esFechaIso(rx) ? E.deIso(rx).getTime() : null) : E.num(rx)
    if (vy === null || vx === null) continue
    const idx = ce ? ce.opciones.indexOf(r.valores?.[ce.id]) : -1
    puntos.push({ id: String(r.id), x: vx, y: vy, titulo: ct ? String(r.valores?.[ct.id] ?? '—') : `Registro ${r.id}`, color: idx >= 0 ? COLORES[idx % COLORES.length] : ce ? GRIS : ACENTO, serie: ce ? `s:${idx >= 0 ? ce.opciones[idx] : E.SIN_DATO}` : null, serieNombre: ce ? (idx >= 0 ? ce.opciones[idx] : E.SIN_DATO) : null })
  }
  if (!puntos.length) return SIN_DATOS
  const tl = E.tendenciaLineal(puntos.map((p) => p.y), puntos.map((p) => (xFecha ? p.x / 864e5 : p.x)))
  const series = ce ? ce.opciones.map((op, i) => ({ id: `s:${op}`, nombre: op, color: COLORES[i % COLORES.length] })).filter((s) => puntos.some((p) => p.serie === s.id)) : []
  const fx = xFecha ? (v) => fechaCorta(new Date(v)) : (v) => fmt(cx.tipo, v)
  const unidad = xFecha ? 'por día' : `por cada 1 de ${cx.nombre.toLowerCase()}`
  return { puntos, tl, xFecha, series, fx, fy: (v) => fmt(cy.tipo, v), nx: cx.nombre, ny: cy.nombre, ne: ce?.nombre,
    pie: `${cy.nombre} vs ${cx.nombre.toLowerCase()} · ${puntos.length} registros${tl.n >= 2 ? ` · tendencia ${tl.pendiente >= 0 ? '+' : '−'}${fmt(cy.tipo, Math.abs(tl.pendiente))} ${unidad}${tl.r2 !== null ? ` (r² ${fmt('numero', tl.r2)})` : ''}` : ''}` }
}

function calcBurbujas(regs, campos, o) {
  const c = campoDe(campos, o.agrupar); const cv = campoDe(campos, o.valor)
  if (!c || !cv) return FALTA
  const items = E.agrupar(regs, c, { top: c.tipo === 'texto' ? 10 : undefined }).map((g, i) => {
    const xs = g.registros.map((r) => r.valores?.[cv.id])
    return { id: g.clave, etiqueta: g.etiqueta, n: g.registros.length, prom: E.promedio(xs), suma: E.suma(xs), color: g.indice >= 0 ? COLORES[g.indice % COLORES.length] : g.clave === E.SIN_DATO ? GRIS : COLORES[i % COLORES.length] }
  }).filter((it) => it.n > 0 && it.prom !== null)
  if (!items.length) return SIN_DATOS
  return { items, tipo: cv.tipo, nv: cv.nombre.toLowerCase(), pie: `Por ${c.nombre.toLowerCase()}: cantidad (→), promedio de ${cv.nombre.toLowerCase()} (↑), tamaño = total` }
}

function calcHistograma(regs, campos, o) {
  const cv = campoDe(campos, o.valor)
  if (!cv) return FALTA
  const xs = E.numeros(regs.map((r) => r.valores?.[cv.id]))
  if (!xs.length) return SIN_DATOS
  return { bins: E.histograma(xs, o.bins, { bonito: true }), tipo: cv.tipo, n: xs.length, prom: E.promedio(xs), med: E.mediana(xs),
    pie: `Distribución de ${cv.nombre.toLowerCase()} · ${xs.length} registros · promedio ${fmt(cv.tipo, E.promedio(xs))}, mediana ${fmt(cv.tipo, E.mediana(xs))}` }
}

function calcCaja(regs, campos, o) {
  const cv = campoDe(campos, o.valor)
  if (!cv) return FALTA
  const c = campoDe(campos, o.agrupar)
  const grupos = c ? E.agrupar(regs, c, { top: c.tipo === 'texto' ? 6 : undefined }) : [{ clave: 'todos', etiqueta: 'Todos', indice: 0, registros: regs }]
  const cajas = grupos.map((g, i) => ({ id: g.clave, etiqueta: g.etiqueta, q: E.cuartiles(g.registros.map((r) => r.valores?.[cv.id])), color: g.indice >= 0 ? COLORES[g.indice % COLORES.length] : g.clave === E.SIN_DATO ? GRIS : COLORES[i % COLORES.length] }))
  if (!cajas.some((k) => k.q)) return SIN_DATOS
  return { cajas, tipo: cv.tipo, pie: `${cv.nombre}${c ? ` por ${c.nombre.toLowerCase()}` : ''}: mínimo, Q1, mediana, Q3 y máximo` }
}

function calcPosiciones(regs, campos, o) {
  const c = campoDe(campos, o.agrupar)
  if (!c) return FALTA
  const todos = E.serie(regs, { agrupar: c.id, medir: medirDe(o), funcion: fnDe(o), campos }).filter((it) => it.clave !== E.SIN_DATO)
  if (!todos.length) return SIN_DATOS
  const items = [...todos].sort((a, b) => b.valor - a.valor || a.etiqueta.localeCompare(b.etiqueta, 'es')).slice(0, o.top || 5).map((it) => ({ ...it, id: it.clave }))
  const total = sumaDe(todos.map((t) => t.valor))
  return { items, total, tipo: tipoDe(o, campos), que: queMide(o, campos), pie: `Top ${items.length} por ${c.nombre.toLowerCase()} · ${queMide(o, campos).toLowerCase()} (de ${todos.length})` }
}

function calcEstadisticas(regs, campos, o) {
  const cv = campoDe(campos, o.valor)
  if (!cv) return FALTA
  const xs = E.numeros(regs.map((r) => r.valores?.[cv.id]))
  if (!xs.length) return SIN_DATOS
  return { tipo: cv.tipo, s: { n: xs.length, promedio: E.promedio(xs), mediana: E.mediana(xs), min: E.minimo(xs), max: E.maximo(xs), desv: E.desviacion(xs), suma: E.suma(xs), q: E.cuartiles(xs) },
    pie: `${cv.nombre} · ${xs.length} de ${regs.length} registros con valor` }
}

const conTotal = (d, msg = SIN_DATOS) => (typeof d === 'string' ? d : d.total > 0 ? d : msg)
const conMeses = (d) => (typeof d === 'string' ? d : d.items.some((i) => i.valor) ? d : 'Sin datos en los últimos meses')
const conMatriz = (d) => (typeof d === 'string' ? d : d.m.some((f) => f.some((v) => v)) ? d : SIN_DATOS)

// ── Catálogo ──────────────────────────────────────────────────────────────────────────────────────
const F = { cb: 'Columnas y barras', la: 'Líneas y áreas', ci: 'Circulares', fl: 'Flujo y jerarquía', di: 'Distribución y correlación', ti: 'Tiempo', re: 'Resúmenes' }
const sumaOConteo = (b) => (b.valor ? 'suma' : 'conteo')

/**
 * GRAFICOS[id] = { nombre, familia, requiere, Componente, calcular, opciones }
 *  - requiere: { clase: n } o lista de alternativas. Clases: estado, estado3 (≥3 opciones), fecha, medida (numero|dinero),
 *    texto, categoria (estado|texto).
 *  - opciones(b, campos): opciones por defecto (b = campos elegidos solos: estado, fecha, valor, valor2, texto, agrupar).
 *  - calcular(registros, campos, o, hoy): objeto para dibujar, o texto = estado vacío.
 */
export const GRAFICOS = {
  columnas: { nombre: 'Columnas', familia: F.cb, requiere: [{ fecha: 1 }, { categoria: 1 }], Componente: Columnas,
    opciones: (b) => ({ agrupar: b.fecha ? 'mes' : b.agrupar, funcion: sumaOConteo(b) }),
    calcular: (r, c, o, hoy) => (o.agrupar === 'mes' ? conMeses(calcMeses(r, c, o, hoy)) : conTotal(calcCategorias(r, c, o))) },
  'columnas-apiladas': { nombre: 'Columnas apiladas', familia: F.cb, requiere: { estado: 1, fecha: 1 }, Componente: ColumnasApiladas,
    opciones: () => ({ funcion: 'conteo', meses: 12 }), calcular: (r, c, o, hoy) => conMatriz(calcMatriz(r, c, o, hoy)) },
  'columnas-100': { nombre: 'Columnas 100 %', familia: F.cb, requiere: { estado: 1, fecha: 1 }, Componente: (p) => <ColumnasApiladas {...p} normalizar />,
    opciones: () => ({ funcion: 'conteo', meses: 12 }), calcular: (r, c, o, hoy) => conMatriz(calcMatriz(r, c, o, hoy)) },
  barras: { nombre: 'Barras horizontales', familia: F.cb, requiere: { categoria: 1 }, Componente: Barras,
    opciones: (b) => ({ funcion: sumaOConteo(b) }), calcular: (r, c, o) => conTotal(calcCategorias(r, c, o)) },
  'barras-apiladas': { nombre: 'Barras apiladas', familia: F.cb, requiere: [{ estado: 1, texto: 1 }, { estado: 1, fecha: 1 }], Componente: BarrasApiladas,
    opciones: (b) => ({ filas: b.texto || 'mes', funcion: 'conteo', meses: 6 }), calcular: (r, c, o, hoy) => conMatriz(calcMatriz(r, c, o, hoy, o.filas, o.top || 6)) },
  'barra-100': { nombre: 'Barra 100 %', familia: F.cb, requiere: { categoria: 1 }, Componente: Barra100,
    opciones: () => ({ funcion: 'conteo' }), calcular: (r, c, o) => conTotal(calcCategorias(r, c, o, 6)) },
  linea: { nombre: 'Línea', familia: F.la, requiere: { fecha: 1 }, Componente: Linea,
    opciones: (b) => ({ funcion: sumaOConteo(b) }), calcular: (r, c, o, hoy) => conMeses(calcMeses(r, c, o, hoy)) },
  'linea-area': { nombre: 'Línea con área', familia: F.la, requiere: { fecha: 1 }, Componente: (p) => <Linea {...p} area />,
    opciones: () => ({ funcion: 'conteo' }), calcular: (r, c, o, hoy) => conMeses(calcMeses(r, c, o, hoy)) },
  'area-apilada': { nombre: 'Área apilada', familia: F.la, requiere: { estado: 1, fecha: 1 }, Componente: AreaApilada,
    opciones: () => ({ funcion: 'conteo', meses: 12 }), calcular: (r, c, o, hoy) => conMatriz(calcMatriz(r, c, o, hoy)) },
  'linea-tendencia': { nombre: 'Línea con tendencia', familia: F.la, requiere: { fecha: 1 }, Componente: (p) => <Linea {...p} tendencia />,
    opciones: (b) => ({ funcion: sumaOConteo(b), ventana: 3 }),
    calcular: (r, c, o, hoy) => {
      const d = conMeses(calcMeses(r, c, o, hoy))
      if (typeof d === 'string') return d
      const tl = E.tendenciaLineal(d.items.map((i) => i.valor))
      const v = Math.max(1, Math.floor(o.ventana || 3))
      const t = `${tl.pendiente >= 0 ? '+' : '−'}${fmt(d.tipo, Math.abs(tl.pendiente))}/mes`
      return { ...d, ventana: v, pie: `${d.pie} · tendencia ${t}${tl.r2 !== null ? ` (r² ${fmt('numero', tl.r2)})` : ''}`,
        leyenda: [{ id: 'l:valor', nombre: d.que, color: ACENTO }, { id: 'l:mm', nombre: `Media móvil ${v} m`, color: COLORES[5] }, { id: 'l:tend', nombre: `Tendencia ${t}`, color: COLORES[2], raya: true }] }
    } },
  dona: { nombre: 'Dona', familia: F.ci, requiere: { categoria: 1 }, Componente: (p) => <Circular {...p} dona />,
    opciones: () => ({ funcion: 'conteo' }), calcular: (r, c, o) => conTotal(calcCategorias(r, c, o)) },
  pastel: { nombre: 'Pastel', familia: F.ci, requiere: { categoria: 1 }, Componente: Circular,
    opciones: (b) => ({ funcion: sumaOConteo(b) }), calcular: (r, c, o) => conTotal(calcCategorias(r, c, o)) },
  anillos: { nombre: 'Anillos concéntricos', familia: F.ci, requiere: { categoria: 1 }, Componente: Anillos,
    opciones: () => ({ funcion: 'conteo' }), calcular: (r, c, o) => conTotal(calcCategorias(r, c, o, 7)) },
  medidor: { nombre: 'Medidor', familia: F.ci, requiere: { estado: 1 }, Componente: Medidor,
    opciones: () => ({ objetivo: null }), calcular: (r, c, o) => calcMedidor(r, c, o) },
  meta: { nombre: 'Anillo de meta', familia: F.ci, requiere: { fecha: 1 }, Componente: Meta,
    opciones: (b) => ({ funcion: sumaOConteo(b), meta: null }), calcular: (r, c, o, hoy) => calcMeta(r, c, o, hoy) },
  embudo: { nombre: 'Embudo', familia: F.fl, requiere: { estado: 1 }, Componente: Embudo,
    opciones: () => ({ modo: 'acumulado', excluir: [] }), calcular: (r, c, o) => calcEmbudo(r, c, o) },
  arbol: { nombre: 'Mapa de árbol', familia: F.fl, requiere: { categoria: 1 }, Componente: Arbol,
    opciones: (b) => ({ agrupar: b.texto || b.estado, funcion: sumaOConteo(b), top: 12 }), calcular: (r, c, o) => conTotal(calcCategorias(r, c, o, 12)) },
  radar: { nombre: 'Radar', familia: F.fl, requiere: { estado3: 1 }, Componente: Radar,
    opciones: (b, campos) => ({ agrupar: campos.find(CLASES.estado3)?.id, funcion: 'conteo' }),
    calcular: (r, c, o) => { const d = conTotal(calcCategorias(r, c, o)); return typeof d === 'string' ? d : d.items.length < 3 ? 'El radar necesita 3 categorías o más' : { ...d, entero: fnDe(o) === 'conteo' } } },
  dispersion: { nombre: 'Dispersión', familia: F.di, requiere: [{ medida: 2 }, { medida: 1, fecha: 1 }], Componente: Dispersion,
    opciones: (b) => ({ x: b.valor2 || b.fecha, y: b.valor }), calcular: (r, c, o) => calcDispersion(r, c, o) },
  burbujas: { nombre: 'Burbujas', familia: F.di, requiere: { categoria: 1, medida: 1 }, Componente: Burbujas,
    opciones: () => ({}), calcular: (r, c, o) => calcBurbujas(r, c, o) },
  histograma: { nombre: 'Histograma', familia: F.di, requiere: { medida: 1 }, Componente: Histograma,
    opciones: () => ({ bins: null }), calcular: (r, c, o) => calcHistograma(r, c, o) },
  caja: { nombre: 'Caja y bigotes', familia: F.di, requiere: { medida: 1 }, Componente: Caja,
    opciones: (b) => ({ agrupar: b.estado || null }), calcular: (r, c, o) => calcCaja(r, c, o) },
  calendario: { nombre: 'Calendario de calor', familia: F.ti, requiere: { fecha: 1 }, Componente: Calendario,
    opciones: () => ({ semanas: 16, funcion: 'conteo' }), calcular: (r, c, o, hoy) => calcCalendario(r, c, o, hoy) },
  cascada: { nombre: 'Cascada', familia: F.ti, requiere: { fecha: 1 }, Componente: Cascada,
    opciones: (b) => ({ funcion: sumaOConteo(b), meses: 12 }), calcular: (r, c, o, hoy) => calcCascada(r, c, o, hoy) },
  kpi: { nombre: 'KPI con tendencia', familia: F.ti, requiere: { fecha: 1 }, Componente: Kpi,
    opciones: (b) => ({ funcion: sumaOConteo(b) }), calcular: (r, c, o, hoy) => calcKpi(r, c, o, hoy) },
  posiciones: { nombre: 'Tabla de posiciones', familia: F.re, requiere: { texto: 1 }, Componente: Posiciones,
    opciones: (b) => ({ agrupar: b.texto, funcion: sumaOConteo(b), top: 5 }), calcular: (r, c, o) => calcPosiciones(r, c, o) },
  estadisticas: { nombre: 'Estadísticas', familia: F.re, requiere: { medida: 1 }, Componente: Estadisticas,
    opciones: () => ({}), calcular: (r, c, o) => calcEstadisticas(r, c, o) },
}

/** Opciones que el gráfico elegiría solo para estos campos. */
export function opcionesPorDefecto(tipo, campos = []) {
  const b = base(campos)
  return { ...b, ...(GRAFICOS[tipo]?.opciones?.(b, campos) || {}) }
}

/** Tipos que se pueden dibujar con los campos de una sección, con sus opciones por defecto. */
export function compatibles(campos = []) {
  return Object.entries(GRAFICOS).filter(([, g]) => cumple(g.requiere, campos))
    .map(([id, g]) => ({ id, nombre: g.nombre, familia: g.familia, requiere: g.requiere, opciones: opcionesPorDefecto(id, campos) }))
}

// ── Medida, interacción y contenedor ────────────────────────────────────────────────────────────────
/** Mide el contenedor en píxeles de layout (clientWidth/Height: no les afectan las transformaciones de las animaciones). */
function useMedida() {
  const ref = useRef(null)
  const [t, setT] = useState({ w: 0, h: 0 })
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return undefined
    const medir = () => { const w = el.clientWidth; const h = el.clientHeight; setT((p) => (p.w === w && p.h === h ? p : { w, h })) }
    medir()
    if (typeof ResizeObserver === 'undefined') { window.addEventListener('resize', medir); return () => window.removeEventListener('resize', medir) }
    const ro = new ResizeObserver(medir)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return [ref, t]
}

/**
 * Dibuja un gráfico del catálogo con los registros de una sección.
 * @param {string} tipo       id del catálogo GRAFICOS (p. ej. 'dona', 'linea-tendencia')
 * @param {object} seccion    la sección (se usa su título en textos accesibles)
 * @param {Array}  campos     campos de la sección [{ id, nombre, tipo, opciones? }]
 * @param {Array}  registros  [{ id, valores }]
 * @param {object} opciones   sobrescriben las elegidas solas: agrupar, estado, fecha, valor, x, y, texto, funcion, meses, meta,
 *                            objetivo, top, ventana, bins, semanas, modo, excluir, filas, pie (false = sin pie de gráfico)
 */
export function Grafico({ tipo, seccion, campos = [], registros = [], opciones = {} }) {
  const def = GRAFICOS[tipo]
  const animar = useContext(AnimarContext) && !sinMovimiento()
  const vel = useContext(VelContext)
  // La figura se mide solo para decidir si cabe el pie; se dibuja con la medida real del lienzo (lo que queda).
  // Así no hay bucle: el lienzo nunca recibe un alto calculado a partir de sí mismo.
  const [ref, { w: W, h: H }] = useMedida()
  const [lienzo, { w, h }] = useMedida()
  const [tip, setTip] = useState(null)
  const uid = useId().replace(/[^a-zA-Z0-9_-]/g, '')
  const claveOp = JSON.stringify(opciones || {})
  const o = useMemo(() => ({ ...opcionesPorDefecto(tipo, campos), ...Object.fromEntries(Object.entries(opciones || {}).filter(([, v]) => v !== undefined)) }), [tipo, campos, claveOp]) // eslint-disable-line react-hooks/exhaustive-deps
  const d = useMemo(() => {
    if (!def) return `No existe el gráfico «${tipo}»`
    if (!cumple(def.requiere, campos)) return FALTA
    if (!registros?.length) return SIN_DATOS
    try { return def.calcular(registros, campos, o, new Date()) } catch (e) { console.error(`[graficos] ${tipo}:`, e); return 'No se pudo calcular este gráfico' } // eslint-disable-line no-console
  }, [def, tipo, campos, registros, o])
  const pieTxt = typeof d === 'object' && o.pie !== false ? d.pie : null
  const conPie = !!pieTxt && H >= 150 && W >= 200
  const mostrar = (e, id, titulo, filas) => {
    const r = lienzo.current?.getBoundingClientRect()
    if (!r) return
    setTip({ id, titulo, filas, x: e.clientX - r.left, y: e.clientY - r.top })
  }
  const ix = {
    activo: tip?.id ?? null,
    p: (id, titulo, filas) => ({
      onPointerEnter: (e) => mostrar(e, id, titulo, filas),
      onPointerMove: (e) => mostrar(e, id, titulo, filas),
      onClick: (e) => mostrar(e, id, titulo, filas),
      onPointerLeave: () => setTip((t) => (t?.id === id ? null : t)),
    }),
    /** ' gr-on' si alguno de los ids está activo, ' gr-off' si hay otro activo, '' si no hay nada activo. */
    c: (...ids) => (tip ? (ids.includes(tip.id) ? ' gr-on' : ' gr-off') : ''),
  }
  const C = def?.Componente
  const vacio = typeof d === 'string'
  const html = tipo === 'kpi' || tipo === 'posiciones' || tipo === 'estadisticas'
  return (
    <figure ref={ref} className={`gr gr-t-${tipo}${vacio ? ' gr-es-vacio' : ''}`} data-animar={animar ? '' : undefined} style={{ '--vel': vel }}
      aria-label={`${def?.nombre || tipo}${seccion?.titulo ? ` · ${seccion.titulo}` : ''}`}>
      <div className={`gr-lienzo${html ? ' gr-html' : ''}`} ref={lienzo} onPointerLeave={() => setTip(null)}>
        {vacio && <p className="gr-vacio">{d}</p>}
        {!vacio && C && w >= 60 && h >= 36 && <C w={w} h={h} d={d} o={o} ix={ix} uid={uid} />}
        {tip && !vacio && (
          <div className="gr-tip" role="status" style={{ left: tip.x, top: tip.y, transform: `translate(${tip.x > w * 0.55 ? 'calc(-100% - 12px)' : '12px'}, ${tip.y > h * 0.5 ? 'calc(-100% - 10px)' : '12px'})` }}>
            <b>{tip.titulo}</b>
            {tip.filas.map(([k, v, c], i) => <span key={i}>{c ? <i style={{ background: c }} /> : null}{k}{v !== '' && <em>{v}</em>}</span>)}
          </div>
        )}
      </div>
      {conPie && <figcaption className="gr-pie" title={pieTxt}>{pieTxt}</figcaption>}
    </figure>
  )
}

// ── Página de prueba ──────────────────────────────────────────────────────────────────────────────
const TAMANOS = { chico: { w: 220, h: 140, nombre: 'Chico 220×140' }, mediano: { w: 340, h: 250, nombre: 'Mediano 340×250' }, grande: { w: 520, h: 360, nombre: 'Grande 520×360' } }

/**
 * Rejilla con TODOS los gráficos compatibles con una sección de la plantilla (por defecto, la que tiene más campos).
 * Props opcionales: seccionId, animar (true), vel (la del contexto), tema ('oscuro' | 'claro': envuelve en el marco .mc del CRM),
 * tamano inicial de las tarjetas ('chico' 220×140 | 'mediano' 340×250 | 'grande' 520×360).
 */
export function GaleriaGraficos({ plantilla, datos, seccionId, animar = true, vel, tema, tamano = 'mediano' }) {
  const velCtx = useContext(VelContext)
  const porId = Object.fromEntries((plantilla?.secciones || []).map((s) => [s.id, s]))
  const conCampos = (plantilla?.secciones || []).filter((s) => camposDe(s, porId).length && !s.fuente)
  const masCampos = [...conCampos].sort((a, b) => camposDe(b, porId).length - camposDe(a, porId).length
    || compatibles(camposDe(b, porId)).length - compatibles(camposDe(a, porId)).length)[0]
  const [elegida, setElegida] = useState(null)
  const [tam, setTam] = useState(TAMANOS[tamano] ? tamano : 'mediano')
  const [vuelta, setVuelta] = useState(0)
  const seccion = porId[elegida || seccionId] || masCampos
  if (!seccion) return <p className="gr-vacio">Esta plantilla no tiene secciones con campos.</p>
  const campos = camposDe(seccion, porId)
  const registros = datos ? registrosDe(seccion, datos) : []
  const lista = compatibles(campos)
  const t = TAMANOS[tam]
  const contenido = (
    <AnimarContext.Provider value={animar}>
      <VelContext.Provider value={vel ?? velCtx}>
        <div className="gr-galeria" style={{ '--vel': vel ?? velCtx, '--gr-col': `${t.w}px`, '--gr-alto': `${t.h}px` }}>
          <header className="gr-galeria-cab">
            <div>
              <h1>Gráficos · {seccion.titulo}</h1>
              <p>{lista.length} tipos compatibles con sus campos ({campos.map((c) => `${c.nombre}: ${c.tipo}`).join(', ')}) · {registros.length.toLocaleString('es')} registros</p>
            </div>
            <div className="gr-galeria-ctl">
              <label>Sección
                <select value={seccion.id} onChange={(e) => { setElegida(e.target.value); setVuelta((v) => v + 1) }}>
                  {conCampos.map((s) => <option key={s.id} value={s.id}>{s.titulo} ({camposDe(s, porId).length} campos)</option>)}
                </select>
              </label>
              <span role="group" aria-label="Tamaño de bloque">
                {Object.entries(TAMANOS).map(([k, v]) => <button key={k} type="button" className={tam === k ? 'on' : ''} aria-pressed={tam === k} onClick={() => setTam(k)}>{v.nombre}</button>)}
              </span>
              <button type="button" onClick={() => setVuelta((v) => v + 1)}>↻ Repetir animación</button>
            </div>
          </header>
          <div className="gr-rejilla-galeria" key={`${seccion.id}-${vuelta}`}>
            {lista.map((g, i) => (
              <section key={g.id} className="pl-bloque gr-tarjeta" style={{ '--i': tope(i, 30) }}>
                <h2 title={`${g.familia} · requiere ${JSON.stringify(g.requiere)}`}>{g.nombre}</h2>
                <Grafico tipo={g.id} seccion={seccion} campos={campos} registros={registros} opciones={g.opciones} />
              </section>
            ))}
          </div>
        </div>
      </VelContext.Provider>
    </AnimarContext.Provider>
  )
  return tema ? <div className="mc gr-galeria-marco" data-tema={tema} data-estilo="vivo">{contenido}</div> : contenido
}

export default Grafico
