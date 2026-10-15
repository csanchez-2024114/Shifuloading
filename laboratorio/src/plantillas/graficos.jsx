/* Catálogo de gráficos del CRM ("todas las de Excel" + estadística), en SVG propio y sin dependencias.
 * Reglas:
 *  - Todo número sale de los registros (estadistica.js). Nada escrito a mano.
 *  - Cada gráfico mide su contenedor (ResizeObserver) y dibuja en PÍXELES REALES (viewBox = tamaño medido).
 *    Tipografía fija: etiquetas 11 px/500, valores 12 px/600 tabulares, número protagonista grande 600.
 *  - Textos medidos de verdad (canvas): lo que no cabe o choca con otro texto NO se dibuja (queda en leyenda o tooltip).
 *    Nunca texto cortado a la mitad dentro de una forma ni encimado.
 *  - Rellenos grandes suavizados con la superficie real (misma paleta) y texto encima con el color de MÁS contraste (≥ 4,5).
 *  - Comparaciones mensuales justas: el mes en curso (incompleto) se compara contra los MISMOS días del mes anterior.
 *  - Animación de entrada lenta con firma por familia (CSS con var(--vel)); variante al azar por montaje; nada con
 *    prefers-reduced-motion.
 *  - Sin registros → «Sin datos todavía». Nunca NaN ni un SVG roto.
 * API (idéntica):
 *  - <Grafico tipo seccion campos registros opciones />
 *  - compatibles(campos) → [{ id, nombre, familia, requiere, opciones }]
 *  - opcionesPorDefecto(tipo, campos) → opciones que elegiría solo
 *  - GRAFICOS, CLASES
 *  - <GaleriaGraficos plantilla datos /> (página de prueba) */
import { useContext, useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { AnimarContext, VelContext } from './vistas'
import * as E from './estadistica'
import { registrosDe } from './datosEjemplo'
import { camposDe } from './validar'
import {
  anchoTexto, anchoVal, cortar, cajaTexto, choca, cabeEn, sinChoques, usePintura, leerPintura, PinturaContext, VarianteContext,
  useOrden, tope, escala, ticks, fEje, plano, Rejilla, EjeX, planLeyenda, filasAbajo, areaCon, Leyenda, porSerie, claseSerie,
  punto, sector, Cuenta, Svg, sinMovimiento, olvidarAnchos, etiquetasCirculo, nivelesCalor, SEPARADOR, altoTexto,
} from './graficos-base'
import {
  ACENTO, GRIS, sumaDe, fechaCorta, fechaLarga, CLASES, cumple, base, campoDe, fnDe, medirDe, tipoDe, queMide, nombre, FALTA, SIN_DATOS,
  calcCategorias, calcMeses, calcMatriz, conTotal, conMeses, conMatriz, sumaOConteo, colorDe,
} from './graficos-calculos'
import { NUEVOS } from './graficos-nuevos'
import '@base/crm.css'
import '@base/crm-extra.css'
import './graficos.css'

export { CLASES }
const { COLORES, fmt, fmtPct, fmtCorto } = E
const VERDE = COLORES[1]
const ROJO = COLORES[3]
const deMarca = (c) => (c === COLORES[0] ? ACENTO : c) // la serie «principal» usa el acento de la plantilla

/** Filas de tooltip del mes en curso: incompleto, comparado contra los mismos días del mes anterior. */
const filasTramo = (tr, tipo) => (tr ? [['Mes en curso', 'incompleto'], [tr.t.actual.etiqueta, fmt(tipo, tr.actual)], [tr.t.anterior.etiqueta, fmt(tipo, tr.anterior)],
  ['Variación (mismos días)', tr.var === null ? '—' : fmtPct(tr.var, true)]] : [])

// ── Columnas y barras ─────────────────────────────────────────────────────────────────────────────
function Columnas({ w, h, d, ix }) {
  const pin = usePintura(); const ord = useOrden()
  const { items, tipo } = d
  const n = items.length
  const vals = items.map((i) => i.valor)
  const p = plano(w, h, { min: Math.min(0, ...vals), max: Math.max(0, ...vals), f: fEje(tipo), entero: d.entero, arriba: 20 })
  const banda = p.ancho / n
  const bw = Math.max(2, Math.min(56, banda * 0.66))
  const total = sumaDe(vals)
  const xc = (i) => p.x0 + banda * (i + 0.5)
  const etq = p.alto >= 70 ? items.map((it, i) => {
    let t = fmt(tipo, it.valor)
    if (anchoVal(t) > banda - 4) t = fmtCorto(tipo, it.valor)
    const y = it.valor < 0 ? p.y(it.valor) + 10 : p.y(Math.max(0, it.valor)) - 10
    return { id: it.id, t, y, x: xc(i), caja: cajaTexto(xc(i), y, anchoVal(t), 'middle', 12), prio: Math.abs(it.valor) }
  }) : []
  const ok = sinChoques(etq.filter((e) => e.prio > 0), { x: 0, y: 0, w, h: p.y0 + 1 }) // los ceros no se rotulan: la columna vacía ya lo dice
  return (
    <Svg w={w} h={h} aria={`${d.pie}: ${items.map((i) => `${i.larga} ${fmt(tipo, i.valor)}`).join(', ')}`}>
      <Rejilla p={p} />
      <g className="gr-marcas">
        {items.map((it, i) => {
          const ya = p.y(Math.max(0, it.valor)); const yb = p.y(Math.min(0, it.valor))
          const c = deMarca(it.color)
          return (
            <g key={it.id} className={`gr-m${ix.c(it.id)}`} {...ix.p(it.id, it.larga, [[d.que, fmt(tipo, it.valor), pin.col(c)], ['Del total', fmtPct(E.porcentajeDelTotal(it.valor, total))], ['Registros', fmt('numero', it.n)], ...(it.parcial ? filasTramo(d.tramo, tipo) : [])])}>
              <rect className="gr-hit" x={p.x0 + banda * i} y={p.y1} width={banda} height={p.alto} />
              <rect className={`${it.valor < 0 ? 'gr-a-col-neg' : 'gr-a-col'}${it.parcial ? ' gr-parcial' : ''}`} x={xc(i) - bw / 2} y={ya} width={bw} height={Math.max(it.valor ? 1 : 0, yb - ya)} rx={Math.min(4, bw / 4)}
                style={{ fill: pin.relleno(c, it.parcial ? 0.6 : 1), stroke: pin.col(c), '--o': ord(i, n) }} />
            </g>
          )
        })}
      </g>
      <g className="gr-valores" pointerEvents="none">
        {etq.filter((e) => ok.has(e.id)).map((e, i) => <text key={e.id} className="gr-valor gr-aparece" x={e.x} y={e.y} dy="0.35em" textAnchor="middle" style={{ '--o': ord(i, n) }}>{e.t}</text>)}
      </g>
      <EjeX p={p} items={items.map((it, i) => ({ x: xc(i), t: it.etiqueta }))} />
    </Svg>
  )
}

function ColumnasApiladas({ w, h, d, ix, uid, normalizar }) {
  const pin = usePintura(); const ord = useOrden()
  const { cats, series, m, tipo } = d
  const totales = m.map((fila) => sumaDe(fila))
  const totalSerie = series.map((_, k) => sumaDe(m.map((fila) => fila[k])))
  const leyItems = series.map((s, k) => ({ ...s, suave: true, valor: normalizar ? '' : fmtCorto(tipo, totalSerie[k]), filas: [['Total', fmt(tipo, totalSerie[k]), pin.col(s.color)]] }))
  const ley = planLeyenda(w, h, leyItems)
  const a = areaCon(ley, w, h)
  const f = normalizar ? (v) => fmtPct(v) : fEje(tipo)
  const p = plano(a.w, a.h, { max: normalizar ? 1 : Math.max(0, ...totales), f, entero: !normalizar && d.entero })
  const n = cats.length
  const banda = p.ancho / n
  const bw = Math.max(2, Math.min(48, banda * 0.66))
  return (
    <Svg w={w} h={h} aria={`${d.pie}${normalizar ? ' (100 %)' : ''}`}>
      <Rejilla p={p} />
      <g className="gr-marcas">
        {cats.map((c, i) => {
          let acum = 0
          const xc = p.x0 + banda * (i + 0.5)
          const filas = series.map((s, k) => [s.nombre, `${fmt(tipo, m[i][k])}${totales[i] ? ` · ${fmtPct(m[i][k] / totales[i])}` : ''}`, pin.col(s.color)]).filter((_, k) => m[i][k])
          return (
            <g key={c.id} className={`gr-m${porSerie(ix) ? '' : ix.c(c.id)}`} {...ix.p(c.id, c.larga, [...filas, ['Total', fmt(tipo, totales[i])]])}>
              <rect className="gr-hit" x={p.x0 + banda * i} y={p.y1} width={banda} height={p.alto} />
              <g className="gr-a-col" style={{ '--o': ord(i, n) }}>
                {series.map((s, k) => {
                  const v = normalizar ? (totales[i] ? m[i][k] / totales[i] : 0) : m[i][k]
                  if (!v) return null
                  const y0 = p.y(acum); acum += v; const y1 = p.y(acum)
                  const fondo = pin.relleno(s.color)
                  const pct = normalizar ? fmtPct(v) : ''
                  const id = `${uid}-c${i}-${k}`
                  const cabe = normalizar && y0 - y1 >= 18 && bw >= anchoTexto(pct, 11, 600) + 8
                  return (
                    <g key={s.id} className={`gr-seg${claseSerie(ix, s.id)}`}>
                      <rect id={id} className="gr-forma" x={xc - bw / 2} y={y1} width={bw} height={Math.max(0.5, y0 - y1)} style={{ fill: fondo, stroke: pin.sup, strokeWidth: SEPARADOR }} />
                      {cabe && <text className="gr-dentro gr-chico" data-forma={id} x={xc} y={(y0 + y1) / 2} dy="0.35em" textAnchor="middle" style={{ fill: pin.texto(fondo) }} pointerEvents="none">{pct}</text>}
                    </g>
                  )
                })}
              </g>
            </g>
          )
        })}
      </g>
      <EjeX p={p} items={cats.map((c, i) => ({ x: p.x0 + banda * (i + 0.5), t: c.etiqueta }))} />
      <Leyenda plan={ley} w={w} h={h} ix={ix} items={leyItems} />
    </Svg>
  )
}

/** Filas horizontales con etiqueta a la izquierda y valor a la derecha. Si no caben todas, se adelgazan. */
function Barras({ w, h, d, ix }) {
  const pin = usePintura(); const ord = useOrden()
  const { items, tipo, total } = d
  const n = items.length
  const conEtq = w >= 150
  const izq = conEtq ? Math.min(w * 0.36, Math.max(...items.map((i) => anchoTexto(i.etiqueta))) + 12) : 4
  const largos = items.map((i) => fmt(tipo, i.valor))
  const textos = Math.max(...largos.map(anchoVal)) > w * 0.22 ? items.map((i) => fmtCorto(tipo, i.valor)) : largos
  const conValor = w >= 170
  const der = conValor ? Math.max(...textos.map(anchoVal)) + 10 : 4
  const x0 = izq; const x1 = Math.max(x0 + 10, w - der)
  const fila = (h - 6) / n
  const bh = Math.max(2, Math.min(24, fila * 0.62))
  const conTexto = fila >= 15
  const max = Math.max(1e-9, ...items.map((i) => i.valor))
  const x = escala(0, max, x0, x1)
  return (
    <Svg w={w} h={h} aria={`${d.pie}: ${items.map((i, k) => `${i.etiqueta} ${largos[k]}`).join(', ')}`}>
      <g className="gr-marcas">
        {items.map((it, i) => {
          const yc = 3 + fila * (i + 0.5)
          const largo = Math.max(it.valor > 0 ? 1.5 : 0, x(Math.max(0, it.valor)) - x0)
          const etq = conEtq && conTexto ? cortar(it.etiqueta, izq - 14) : ''
          return (
            <g key={it.id} className={`gr-m${ix.c(it.id)}`} {...ix.p(it.id, it.larga, [[d.que, largos[i], pin.col(it.color)], ['Del total', fmtPct(E.porcentajeDelTotal(it.valor, total))], ['Registros', fmt('numero', it.n)]])}>
              <rect className="gr-hit" x="0" y={yc - fila / 2} width={w} height={fila} />
              <rect className="gr-pista" x={x0} y={yc - bh / 2} width={x1 - x0} height={bh} rx={Math.min(5, bh / 2)} />
              <rect className="gr-a-barra" x={x0} y={yc - bh / 2} width={largo} height={bh} rx={Math.min(5, bh / 2)} style={{ fill: pin.relleno(it.color), stroke: pin.col(it.color), '--o': ord(i, n) }} />
              {etq && <text x={x0 - 8} y={yc} dy="0.35em" textAnchor="end">{etq}</text>}
              {conValor && conTexto && <text className="gr-valor gr-aparece" x={x0 + largo + 6} y={yc} dy="0.35em" style={{ '--o': ord(i, n) }}>{textos[i]}</text>}
            </g>
          )
        })}
      </g>
    </Svg>
  )
}

function BarrasApiladas({ w, h, d, ix }) {
  const pin = usePintura(); const ord = useOrden()
  const { cats, series, m, tipo } = d
  const totales = m.map((fila) => sumaDe(fila))
  const totalSerie = series.map((_, k) => sumaDe(m.map((fila) => fila[k])))
  const leyItems = series.map((s, k) => ({ ...s, suave: true, filas: [['Total', fmt(tipo, totalSerie[k]), pin.col(s.color)]] }))
  const ley = planLeyenda(w, h, leyItems)
  const a = areaCon(ley, w, h)
  const conEtq = a.w >= 150
  const izq = conEtq ? Math.min(a.w * 0.34, Math.max(...cats.map((c) => anchoTexto(c.etiqueta))) + 12) : 4
  const tTot = totales.map((t) => fmtCorto(tipo, t))
  const der = a.w >= 170 ? Math.max(...tTot.map(anchoVal)) + 10 : 4
  const x0 = izq; const x1 = Math.max(x0 + 10, a.w - der)
  const n = cats.length
  const fila = (a.h - 6) / n
  const bh = Math.max(2, Math.min(24, fila * 0.62))
  const max = Math.max(1e-9, ...totales)
  const x = escala(0, max, x0, x1)
  return (
    <Svg w={w} h={h} aria={d.pie}>
      <g className="gr-marcas">
        {cats.map((c, i) => {
          const yc = 3 + fila * (i + 0.5)
          let acum = 0
          const filas = series.map((s, k) => [s.nombre, `${fmt(tipo, m[i][k])}${totales[i] ? ` · ${fmtPct(m[i][k] / totales[i])}` : ''}`, pin.col(s.color)]).filter((_, k) => m[i][k])
          const etq = conEtq && fila >= 15 ? cortar(c.etiqueta, izq - 14) : ''
          return (
            <g key={c.id} className={`gr-m${porSerie(ix) ? '' : ix.c(c.id)}`} {...ix.p(c.id, c.larga, [...filas, ['Total', fmt(tipo, totales[i])]])}>
              <rect className="gr-hit" x="0" y={yc - fila / 2} width={a.w} height={fila} />
              <g className="gr-a-barra" style={{ '--o': ord(i, n) }}>
                {series.map((s, k) => {
                  const v = m[i][k]
                  if (!v) return null
                  const xa = x(acum); acum += v; const xb = x(acum)
                  return <rect key={s.id} className={`gr-seg${claseSerie(ix, s.id)}`} x={xa} y={yc - bh / 2} width={Math.max(0.5, xb - xa)} height={bh} style={{ fill: pin.relleno(s.color), stroke: pin.sup, strokeWidth: SEPARADOR }} />
                })}
              </g>
              {etq && <text x={x0 - 8} y={yc} dy="0.35em" textAnchor="end">{etq}</text>}
              {a.w >= 170 && fila >= 15 && <text className="gr-valor gr-aparece" x={x(totales[i]) + 6} y={yc} dy="0.35em" style={{ '--o': ord(i, n) }}>{tTot[i]}</text>}
            </g>
          )
        })}
      </g>
      <Leyenda plan={ley} w={w} h={h} ix={ix} items={leyItems} />
    </Svg>
  )
}

/** Una sola barra 100 % con las partes del total. El % va dentro solo si cabe; si no, en la leyenda. */
function Barra100({ w, h, d, ix, uid }) {
  const pin = usePintura()
  const { items, tipo, total } = d
  const conPartes = items.filter((i) => i.valor > 0)
  const leyItems = items.map((i) => ({ id: i.id, nombre: i.etiqueta, color: i.color, suave: true, valor: fmtPct(E.porcentajeDelTotal(i.valor, total)), filas: [[d.que, fmt(tipo, i.valor), pin.col(i.color)]] }))
  const altoLey = filasAbajo(w, leyItems) * 18 + 6
  const ley = h - altoLey >= 34 ? { lado: 'abajo', alto: altoLey } : { lado: null }
  const enLinea = ley.lado ? ley.alto : 0
  const bh = Math.max(14, Math.min(48, (h - enLinea) * 0.4))
  const yb = Math.max(4, (h - enLinea - bh) / 2)
  const x0 = 2; const x1 = w - 2
  const clip = `gr-b100-${uid}`
  let acum = 0
  return (
    <Svg w={w} h={h} aria={`${d.pie}: ${items.map((i) => `${i.etiqueta} ${fmtPct(E.porcentajeDelTotal(i.valor, total))}`).join(', ')}`}>
      <defs><clipPath id={clip}><rect x={x0} y={yb} width={x1 - x0} height={bh} rx={Math.min(10, bh / 2)} /></clipPath></defs>
      <rect className="gr-pista" x={x0} y={yb} width={x1 - x0} height={bh} rx={Math.min(10, bh / 2)} />
      <g className="gr-marcas" clipPath={`url(#${clip})`}>
        {conPartes.map((it, i) => {
          const f = it.valor / total
          const xa = x0 + (x1 - x0) * acum; acum += f; const ancho = (x1 - x0) * f
          const pct = fmtPct(f)
          const fondo = pin.relleno(it.color)
          const id = `${uid}-b${i}`
          // Cabe si el texto entra en lo VISIBLE del segmento: menos la separación, el aire y, solo en los
          // extremos, lo que la punta redondeada recorta a la altura del texto. (2 px de aire por lado; el ancho del % se mide exacto.)
          const rx = Math.min(10, bh / 2)
          const medioT = altoTexto(12) / 2
          const dy = Math.max(0, medioT - (bh / 2 - rx))
          const punta = i === 0 || i === conPartes.length - 1 ? rx - Math.sqrt(Math.max(0, rx * rx - dy * dy)) : 0
          const cabe = bh >= altoTexto(12) + 4 && ancho - (conPartes.length > 1 ? SEPARADOR : 0) - 4 - 2 * punta >= anchoVal(pct)
          return (
            <g key={it.id} className={`gr-m${ix.c(it.id)}`} {...ix.p(it.id, it.larga, [[d.que, fmt(tipo, it.valor), pin.col(it.color)], ['Del total', pct]])}>
              <rect id={id} className="gr-forma gr-a-barra" x={xa} y={yb} width={Math.max(0.5, ancho)} height={bh} style={{ fill: fondo, stroke: pin.sup, strokeWidth: conPartes.length > 1 ? SEPARADOR : 0, '--o': i }} />
              {cabe && <text className="gr-valor gr-dentro gr-aparece" data-forma={id} x={xa + ancho / 2 + (i === 0 ? punta / 2 : i === conPartes.length - 1 ? -punta / 2 : 0)} y={yb + bh / 2} dy="0.35em" textAnchor="middle" style={{ fill: pin.texto(fondo), '--o': i + 2 }} pointerEvents="none">{pct}</text>}
            </g>
          )
        })}
      </g>
      <Leyenda plan={ley} w={w} h={h} ix={ix} items={leyItems} />
    </Svg>
  )
}

// ── Líneas y áreas ────────────────────────────────────────────────────────────────────────────────
/** Línea por mes. Variantes: con área degradada, o con recta de tendencia + media móvil. El mes en curso va punteado. */
function Linea({ w, h, d, ix, uid, area, tendencia }) {
  const pin = usePintura(); const ord = useOrden()
  const { items, tipo } = d
  const vals = items.map((i) => i.valor)
  const n = vals.length
  const tl = tendencia ? E.tendenciaLineal(vals) : null
  const mm = tendencia ? E.mediaMovil(vals, d.ventana || 3) : []
  const ley = tendencia ? planLeyenda(w, h, d.leyenda) : { lado: null }
  const a = areaCon(ley, w, h)
  const extra = tendencia ? [tl.en(0), tl.en(n - 1), ...mm.filter((x) => x !== null)] : []
  const p = plano(a.w, a.h, { min: Math.min(0, ...extra), max: Math.max(0, ...vals, ...extra), f: fEje(tipo), entero: d.entero, arriba: 12 })
  const banda = p.ancho / n
  const X = (i) => p.x0 + banda * (i + 0.5)
  const ruta = (xs, desde = 0) => xs.map((v, i) => `${i ? 'L' : 'M'}${X(i + desde).toFixed(1)},${p.y(v).toFixed(1)}`).join(' ')
  const parcial = items[n - 1]?.parcial && n > 1
  const linea = ruta(parcial ? vals.slice(0, -1) : vals)
  const resto = parcial ? ruta(vals.slice(-2), n - 2) : ''
  const todo = ruta(vals)
  const relleno = `${todo} L${X(n - 1).toFixed(1)},${p.y0} L${X(0).toFixed(1)},${p.y0} Z`
  const mmPath = mm.map((v, i) => (v === null ? null : [X(i), p.y(v)])).filter(Boolean).map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ')
  const gid = `gr-deg-${uid}`; const cid = `gr-barr-${uid}`
  const activo = items.findIndex((it) => it.id === ix.activo)
  const r = Math.max(2, Math.min(4, banda / 5))
  const ac = pin.acento
  return (
    <Svg w={w} h={h} aria={`${d.pie}: ${items.map((i) => `${i.larga} ${fmt(tipo, i.valor)}`).join(', ')}`}>
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1"><stop offset="0" style={{ stopColor: ac, stopOpacity: pin.oscuro ? 0.34 : 0.26 }} /><stop offset="1" style={{ stopColor: ac, stopOpacity: 0 }} /></linearGradient>
        <clipPath id={cid}><rect className="gr-a-barrido" x={p.x0 - 4} y={0} width={p.ancho + 8} height={h} /></clipPath>
      </defs>
      <Rejilla p={p} />
      {(area || tendencia) && <path className="gr-area" clipPath={`url(#${cid})`} d={relleno} style={{ fill: `url(#${gid})`, ...(tendencia ? { opacity: 0.45 } : {}) }} />}
      {activo >= 0 && <line className="gr-guia" x1={X(activo)} x2={X(activo)} y1={p.y1} y2={p.y0} />}
      <path className="gr-traza gr-linea" d={linea} pathLength="1" style={{ stroke: ac }} />
      {resto && <path className="gr-linea gr-parcial-l gr-aparece" d={resto} style={{ stroke: ac, '--o': 14 }} />}
      {tendencia && mmPath && <path className="gr-traza gr-linea gr-mm" d={mmPath} pathLength="1" style={{ stroke: COLORES[5], '--i': 6 }} />}
      {tendencia && <line className="gr-aparece gr-tendencia" x1={X(0)} y1={p.y(tl.en(0))} x2={X(n - 1)} y2={p.y(tl.en(n - 1))} style={{ stroke: COLORES[2], '--o': 16 }} />}
      <g className="gr-marcas">
        {items.map((it, i) => (
          <g key={it.id} {...ix.p(it.id, it.larga, [[d.que, fmt(tipo, it.valor), ac],
            ...(tendencia ? [[`Media móvil ${d.ventana || 3} m`, fmt(tipo, mm[i]), COLORES[5]], ['Tendencia', fmt(tipo, tl.en(i)), COLORES[2]]] : []),
            ...(it.parcial ? filasTramo(d.tramo, tipo) : i > 0 ? [['vs mes anterior', fmtPct(E.variacion(it.valor, vals[i - 1]), true)]] : [])])}>
            <rect className="gr-hit" x={p.x0 + banda * i} y={p.y1} width={banda} height={p.alto} />
            {banda >= 9 && <circle className="gr-punto gr-a-pop" cx={X(i)} cy={p.y(it.valor)} r={r} style={{ fill: it.parcial ? 'none' : pin.sup, stroke: ac, strokeDasharray: it.parcial ? '2 1.5' : undefined, '--o': ord(i, n) }} />}
          </g>
        ))}
        {activo >= 0 && <circle className="gr-punto-on" cx={X(activo)} cy={p.y(vals[activo])} r={r + 2.5} style={{ fill: ac, stroke: pin.sup }} />}
      </g>
      <EjeX p={p} items={items.map((it, i) => ({ x: X(i), t: it.etiqueta }))} />
      {tendencia && <Leyenda plan={ley} w={w} h={h} ix={ix} items={d.leyenda} />}
    </Svg>
  )
}

function AreaApilada({ w, h, d, ix, uid }) {
  const pin = usePintura()
  const { cats, series, m, tipo } = d
  const totales = m.map((fila) => sumaDe(fila))
  const leyItems = series.map((s, k) => ({ ...s, suave: true, filas: [['Total', fmt(tipo, sumaDe(m.map((f) => f[k]))), pin.col(s.color)]] }))
  const ley = planLeyenda(w, h, leyItems)
  const a = areaCon(ley, w, h)
  const p = plano(a.w, a.h, { max: Math.max(0, ...totales), f: fEje(tipo), entero: d.entero, arriba: 12 })
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
  const cid = `gr-barr-${uid}`
  return (
    <Svg w={w} h={h} aria={d.pie}>
      <defs><clipPath id={cid}><rect className="gr-a-barrido" x={p.x0 - 4} y={0} width={p.ancho + 8} height={h} /></clipPath></defs>
      <Rejilla p={p} />
      <g className="gr-capas" clipPath={`url(#${cid})`}>
        {capas.filter((c) => !c.vacia).map(({ s, k, d: path, borde }) => (
          <g key={s.id} className={`gr-capa gr-a-area${claseSerie(ix, s.id)}`} style={{ '--o': k }}>
            <path className="gr-area" d={path} style={{ fill: pin.relleno(s.color) }} />
            <path className="gr-borde" d={borde} style={{ stroke: pin.col(s.color) }} />
          </g>
        ))}
      </g>
      {activo >= 0 && <line className="gr-guia" x1={X(activo)} x2={X(activo)} y1={p.y1} y2={p.y0} />}
      <g className="gr-marcas">
        {cats.map((c, i) => (
          <rect key={c.id} className="gr-hit" x={p.x0 + banda * i} y={p.y1} width={banda} height={p.alto}
            {...ix.p(c.id, c.larga, [...series.map((s, k) => [s.nombre, fmt(tipo, m[i][k]), pin.col(s.color)]).filter((_, k) => m[i][k]), ['Total', fmt(tipo, totales[i])]])} />
        ))}
      </g>
      <EjeX p={p} items={cats.map((c, i) => ({ x: X(i), t: c.etiqueta }))} />
      <Leyenda plan={ley} w={w} h={h} ix={ix} items={leyItems} />
    </Svg>
  )
}

// ── Circulares ────────────────────────────────────────────────────────────────────────────────────
/** Dona y pastel: gajos (paths) con relleno suave y 2 px de separación con la superficie. */
function Circular({ w, h, d, ix, uid, dona }) {
  const pin = usePintura(); const ord = useOrden()
  const { items, tipo, total } = d
  const leyItems = items.map((it) => ({ id: it.id, nombre: it.etiqueta, color: it.color, suave: true, valor: fmtPct(E.porcentajeDelTotal(it.valor, total)), filas: [[d.que, fmt(tipo, it.valor), pin.col(it.color)], ['Del total', fmtPct(E.porcentajeDelTotal(it.valor, total))]] }))
  const ley = planLeyenda(w, h, leyItems)
  const a = areaCon(ley, w, h)
  const cx = a.w / 2; const cy = a.h / 2
  let acum = 0
  const partes = items.filter((it) => it.valor > 0).map((it, i) => { const f = it.valor / total; const a0 = acum * 2 * Math.PI; acum += f; return { it, i, f, a0, a1: acum * 2 * Math.PI } })
  const R0 = Math.max(12, Math.min(a.w, a.h) / 2 - 6)
  const grosor = (R) => (dona ? Math.max(6, R * 0.36) : R)
  let R = R0
  let etq = etiquetasCirculo({ partes, cx, cy, r0: dona ? R - grosor(R) : 0, R, a, fuera: false })
  if (!dona && etq.some((e) => !e.modo)) {
    // Algún % no cabe dentro: si hay aire a los lados, el pastel se achica un poco y esos % van afuera con línea guía.
    const R2 = Math.min(R0, a.w / 2 - 62, a.h / 2 - 10)
    if (R2 >= 42) { R = R2; etq = etiquetasCirculo({ partes, cx, cy, r0: 0, R, a, fuera: true }) }
  }
  const r0 = dona ? R - grosor(R) : 0
  const sep = partes.length > 1 ? SEPARADOR : 0
  const origen = { transformOrigin: `${cx}px ${cy}px` }
  // Centro de la dona: total que cuenta, a un tamaño que cabe en el hueco.
  const totalTxt = fmt(tipo, total)
  let tam = Math.round(Math.max(13, Math.min(28, r0 * 0.42)))
  while (tam > 12 && anchoTexto(totalTxt, tam, 600) > r0 * 1.6) tam--
  const centro = anchoTexto(totalTxt, tam, 600) <= r0 * 1.6 ? totalTxt : fmtCorto(tipo, total)
  const conCentro = dona && r0 >= 22 && anchoTexto(centro, tam, 600) <= r0 * 1.7
  const sub = tipo === 'numero' && d.que === 'Cantidad' ? 'en total' : d.que.toLowerCase()
  const conSub = conCentro && r0 >= 40 && anchoTexto(sub) <= r0 * 1.5
  return (
    <Svg w={w} h={h} aria={`${d.pie}: ${items.map((i) => `${i.etiqueta} ${fmt(tipo, i.valor)} (${fmtPct(E.porcentajeDelTotal(i.valor, total))})`).join(', ')}`}>
      <g className="gr-marcas gr-a-giro" style={origen}>
        {partes.map(({ it, i, f, a0, a1 }) => {
          const fondo = pin.relleno(it.color)
          return (
            <path key={it.id} id={`${uid}-g${i}`} className={`gr-forma gr-gajo gr-a-gajo gr-m${ix.c(it.id)}`} d={sector(cx, cy, r0, R, a0, a1)} fillRule="evenodd"
              style={{ fill: fondo, stroke: pin.sup, strokeWidth: sep, strokeLinejoin: 'round', '--o': ord(i, partes.length), ...origen }}
              {...ix.p(it.id, it.larga, [[d.que, fmt(tipo, it.valor), pin.col(it.color)], ['Del total', fmtPct(f)], ['Registros', fmt('numero', it.n)]])} />
          )
        })}
      </g>
      <g pointerEvents="none">
        {etq.filter((e) => e.modo === 'dentro').map((e) => (
          <text key={e.it.id} className="gr-valor gr-dentro gr-aparece" data-forma={`${uid}-g${e.i}`} x={e.x} y={e.y} dy="0.35em" textAnchor="middle" style={{ fill: pin.texto(pin.relleno(e.it.color)), '--o': 8 + e.i }}>{e.t}</text>
        ))}
        {etq.filter((e) => e.modo === 'fuera').map((e) => {
          const [px, py] = punto(cx, cy, R + 2, e.am)
          return (
            <g key={e.it.id} className="gr-aparece" style={{ '--o': 10 + e.i }}>
              <polyline className="gr-guia-etq" points={`${px.toFixed(1)},${py.toFixed(1)} ${e.ex.toFixed(1)},${e.ty.toFixed(1)} ${(e.tx + (e.der ? -3 : 3)).toFixed(1)},${e.ty.toFixed(1)}`} style={{ stroke: pin.col(e.it.color) }} />
              <text className="gr-valor" x={e.tx} y={e.ty} dy="0.35em" textAnchor={e.der ? 'start' : 'end'}>{e.t}</text>
            </g>
          )
        })}
        {conCentro && (
          <g className="gr-centro-t">
            <text x={cx} y={conSub ? cy - 7 : cy} dy="0.35em" textAnchor="middle" className="gr-grande" style={{ fontSize: tam }}><Cuenta v={total} f={(x) => (centro === totalTxt ? fmt(tipo, x) : fmtCorto(tipo, x))} /></text>
            {conSub && <text x={cx} y={cy + tam / 2 + 6} dy="0.35em" textAnchor="middle">{sub}</text>}
          </g>
        )}
      </g>
      <Leyenda plan={ley} w={w} h={h} ix={ix} items={leyItems} />
    </Svg>
  )
}

/** Anillos concéntricos (barras radiales): cada categoría es un anillo; el más grande llega a 3/4 de vuelta. */
function Anillos({ w, h, d, ix }) {
  const pin = usePintura(); const ord = useOrden()
  const items = d.items.slice(0, 7)
  const { tipo, total } = d
  const leyItems = items.map((it) => ({ id: it.id, nombre: it.etiqueta, color: it.color, suave: true, valor: fmtCorto(tipo, it.valor), filas: [[d.que, fmt(tipo, it.valor), pin.col(it.color)]] }))
  const ley = planLeyenda(w, h, leyItems)
  const a = areaCon(ley, w, h)
  const R = Math.max(14, Math.min(a.w, a.h) / 2 - 4)
  const cx = a.w / 2; const cy = a.h / 2
  const r0 = R * 0.24
  const n = items.length
  const paso = (R - r0) / n
  const sw = Math.max(2, paso * 0.7)
  const max = Math.max(1e-9, ...items.map((i) => i.valor))
  return (
    <Svg w={w} h={h} aria={`${d.pie}: ${items.map((i) => `${i.etiqueta} ${fmt(tipo, i.valor)}`).join(', ')}`}>
      <g className="gr-marcas">
        {items.map((it, k) => {
          const r = R - paso * (k + 0.5)
          const C = 2 * Math.PI * r
          const f = (it.valor / max) * 0.75
          const t = paso >= 15 && r >= 36 ? cortar(`${it.etiqueta} · ${fmtCorto(tipo, it.valor)}`, Math.min(cx - 6, r * 1.5)) : ''
          return (
            <g key={it.id} className={`gr-m${ix.c(it.id)}`} {...ix.p(it.id, it.larga, [[d.que, fmt(tipo, it.valor), pin.col(it.color)], ['Del total', fmtPct(E.porcentajeDelTotal(it.valor, total))]])}>
              <circle className="gr-pista-c" cx={cx} cy={cy} r={r} transform={`rotate(-90 ${cx} ${cy})`} strokeDasharray={`${0.75 * C} ${C}`} style={{ strokeWidth: sw }} />
              {f > 0 && <circle className="gr-arco gr-a-arco" cx={cx} cy={cy} r={r} transform={`rotate(-90 ${cx} ${cy})`} strokeDasharray={`${f * C} ${C}`} strokeLinecap="round" style={{ stroke: pin.relleno(it.color), strokeWidth: sw, '--sw': `${sw}px`, '--o': ord(k, n) }} />}
              {t && <text x={cx - 8} y={cy - r} dy="0.35em" textAnchor="end" className="gr-aparece" style={{ '--o': k + 4 }}>{t}</text>}
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
  const pin = usePintura()
  const textoAbajo = h >= 110 ? 34 : 18
  const R = Math.max(14, Math.min(w / 2 - 10, h - textoAbajo - 8))
  const cx = w / 2; const cy = Math.max(R + 6, (h - textoAbajo + R) / 2 + 2)
  const sw = Math.max(5, R * 0.22)
  const r = R - sw / 2
  const arco = `M${cx - r},${cy} A${r},${r} 0 0 1 ${cx + r},${cy}`
  const f = Math.max(0, Math.min(1, d.f))
  const ang = Math.PI * (1 - f)
  const grande = `${(Math.round(d.f * 1000) / 10).toLocaleString('es')} %`
  let tam = Math.round(Math.max(13, Math.min(30, R * 0.36)))
  while (tam > 12 && anchoTexto(grande, tam, 600) > r * 1.5) tam--
  const objetivo = cortar(d.objetivo, Math.max(40, Math.min(w - 8, R >= 84 ? r * 1.2 : w - 8)))
  return (
    <Svg w={w} h={h} aria={`${d.objetivo}: ${fmtPct(d.f)} del total (${d.n} de ${d.total})`}>
      <path className="gr-pista-c" d={arco} style={{ strokeWidth: sw }} />
      <g className="gr-marcas" {...ix.p('medidor', d.objetivo, [['Registros', `${fmt('numero', d.n)} de ${fmt('numero', d.total)}`, pin.col(d.color)], ['Del total', fmtPct(d.f)]])}>
        {f > 0 && <path className={`gr-arco gr-a-arco gr-m${ix.c('medidor')}`} d={arco} pathLength="1" strokeDasharray={`${f} 1`} style={{ stroke: pin.relleno(d.color), strokeWidth: sw, strokeLinecap: 'round', '--sw': `${sw}px` }} />}
        {R >= 40 && <circle className="gr-a-pop" cx={cx + Math.cos(ang) * r} cy={cy - Math.sin(ang) * r} r={sw * 0.3} style={{ fill: pin.col(d.color), stroke: pin.sup, strokeWidth: 2, '--o': 12 }} />}
      </g>
      <text x={cx} y={cy - (R >= 50 ? 6 : 2)} textAnchor="middle" className="gr-grande" style={{ fontSize: tam }}><Cuenta v={d.f * 100} f={(x) => `${(Math.round(x * 10) / 10).toLocaleString('es')} %`} /></text>
      {R >= 84 && cy + sw / 2 + 17 <= h && <><text x={cx - r} y={cy + sw / 2 + 14} textAnchor="middle" className="gr-sutil">0 %</text><text x={cx + r} y={cy + sw / 2 + 14} textAnchor="middle" className="gr-sutil">100 %</text></>}
      {objetivo && <text x={cx} y={cy + 16} textAnchor="middle">{objetivo}</text>}
      {h >= 110 && <text x={cx} y={cy + 31} textAnchor="middle" className="gr-sutil">{cortar(`${fmt('numero', d.n)} de ${fmt('numero', d.total)} registros`, w - 8)}</text>}
    </Svg>
  )
}

/** Anillo de meta: lo que va del mes en curso (hasta hoy) contra la meta, con la marca de «lo esperado a esta fecha». */
function Meta({ w, h, d, ix }) {
  const pin = usePintura()
  const R = Math.max(14, Math.min(w, h) / 2 - 6)
  const cx = w / 2; const cy = h / 2
  const sw = Math.max(6, R * 0.2)
  const r = R - sw / 2
  const f = d.meta ? d.valor / d.meta : 0
  const C = 2 * Math.PI * r
  const ff = Math.max(0, Math.min(1, f))
  const color = f >= 1 ? VERDE : ACENTO
  const [ex1, ey1] = punto(cx, cy, R + 1, d.esperado * 2 * Math.PI)
  const [ex2, ey2] = punto(cx, cy, R - sw - 1, d.esperado * 2 * Math.PI)
  const pctTxt = `${Math.round(f * 100).toLocaleString('es')} %`
  let tam = Math.round(Math.max(13, Math.min(30, r * 0.4)))
  while (tam > 12 && anchoTexto(pctTxt, tam, 600) > (r - sw / 2) * 1.6) tam--
  const linea2 = `${fmtCorto(d.tipo, d.valor)} de ${fmtCorto(d.tipo, d.meta)}`
  const con2 = R >= 50 && anchoTexto(linea2) <= (r - sw / 2) * 1.7
  const linea3 = f >= 1 ? '¡meta cumplida!' : `al ${d.dias} de ${d.mes}`
  const con3 = R >= 64 && anchoTexto(linea3) <= (r - sw / 2) * 1.5
  return (
    <Svg w={w} h={h} aria={`${d.etiqueta}: ${fmt(d.tipo, d.valor)} de ${fmt(d.tipo, d.meta)} (${fmtPct(f)})`}>
      <circle className="gr-pista-c" cx={cx} cy={cy} r={r} style={{ strokeWidth: sw }} />
      <g className="gr-marcas" {...ix.p('meta', d.etiqueta, [['Lleva', fmt(d.tipo, d.valor), pin.col(color)], ['Meta del mes', fmt(d.tipo, d.meta)], ['Avance', fmtPct(f)], ['Esperado a hoy', `${fmtPct(d.esperado)} (día ${d.dias} de ${d.diasMes})`], ['Meta =', d.origen]])}>
        <circle className="gr-pista-c gr-hit-c" cx={cx} cy={cy} r={r} style={{ strokeWidth: sw, opacity: 0 }} />
        {ff > 0 && <circle className={`gr-arco gr-a-arco gr-m${ix.c('meta')}`} cx={cx} cy={cy} r={r} transform={`rotate(-90 ${cx} ${cy})`} strokeDasharray={`${ff * C} ${C}`} strokeLinecap="round" style={{ stroke: pin.relleno(color), strokeWidth: sw, '--sw': `${sw}px` }} />}
        {R >= 34 && <line className="gr-esperado gr-aparece" x1={ex1} y1={ey1} x2={ex2} y2={ey2} style={{ '--o': 12 }} />}
      </g>
      <g pointerEvents="none">
        <text x={cx} y={con2 ? cy - 6 : cy} dy="0.35em" textAnchor="middle" className="gr-grande" style={{ fontSize: tam }}><Cuenta v={f * 100} f={(x) => `${Math.round(x).toLocaleString('es')} %`} /></text>
        {con2 && <text x={cx} y={cy + tam / 2 + 6} dy="0.35em" textAnchor="middle" className="gr-valor">{linea2}</text>}
        {con3 && <text x={cx} y={cy + tam / 2 + 22} dy="0.35em" textAnchor="middle" className="gr-sutil">{linea3}</text>}
      </g>
    </Svg>
  )
}

// ── Flujo y jerarquía ─────────────────────────────────────────────────────────────────────────────
/** Embudo: etapas del estado (en el orden de sus opciones) con el % que pasa de una a la siguiente. */
function Embudo({ w, h, d, ix, uid }) {
  const pin = usePintura(); const ord = useOrden()
  const { items } = d
  const max = Math.max(1e-9, ...items.map((i) => i.valor))
  const n = items.length
  const pasos = items.map((it) => (it.paso === null ? '' : `↓ ${fmtPct(it.paso)}`))
  const anchoPaso = Math.max(0, ...pasos.map((t) => anchoTexto(t, 11, 600)))
  const fila = (h - 4) / n
  const conPaso = w >= 260 && fila >= 16
  const colPaso = conPaso ? anchoPaso + 12 : 0
  const anchoMax = w - 8 - colPaso
  const cx = 4 + anchoMax / 2
  const bh = Math.max(3, fila * (fila >= 30 ? 0.62 : 0.78))
  const anchoDe = (v) => Math.max(4, (v / max) * anchoMax)
  return (
    <Svg w={w} h={h} aria={`${d.pie}: ${items.map((i) => `${i.etiqueta} ${i.valor}`).join(', ')}`}>
      <g className="gr-marcas">
        {items.map((it, i) => {
          const y = 2 + fila * i + (fila - bh) / 2
          const ancho = anchoDe(it.valor)
          const sig = items[i + 1]
          const fondo = pin.relleno(it.color)
          const id = `${uid}-e${i}`
          // Texto: dentro si cabe; si no, al lado (antes de la columna de pasos); si no, solo el número dentro; si no, nada.
          const largo = `${it.etiqueta} · ${fmt('numero', it.valor)}`
          const corto = fmt('numero', it.valor)
          let txt = null
          if (bh >= 15) {
            if (anchoTexto(largo, 11, 600) + 14 <= ancho) txt = { t: largo, x: cx, ancla: 'middle', dentro: true }
            else if (cx + ancho / 2 + 8 + anchoTexto(largo, 11, 600) <= w - colPaso - 4) txt = { t: largo, x: cx + ancho / 2 + 8, ancla: 'start', dentro: false }
            else if (anchoTexto(corto, 11, 600) + 10 <= ancho) txt = { t: corto, x: cx, ancla: 'middle', dentro: true }
          }
          return (
            <g key={it.id} className={`gr-m${ix.c(it.id)}`} {...ix.p(it.id, it.etiqueta, [[d.modo === 'acumulado' ? 'Llegaron a esta etapa' : 'En esta etapa', fmt('numero', it.valor), pin.col(it.color)],
              ...(d.modo === 'acumulado' ? [['Están en ella ahora', fmt('numero', it.actual)]] : []),
              ...(i > 0 ? [[`Pasan desde ${items[i - 1].etiqueta}`, fmtPct(it.paso)]] : []), ['Del inicio', fmtPct(E.porcentajeDelTotal(it.valor, items[0].valor))]])}>
              <rect className="gr-hit" x="0" y={2 + fila * i} width={w} height={fila} />
              <g className="gr-a-cae" style={{ '--o': ord(i, n) }}>
                {sig && fila - bh >= 4 && <polygon className="gr-union" points={`${cx - ancho / 2},${y + bh} ${cx + ancho / 2},${y + bh} ${cx + anchoDe(sig.valor) / 2},${y + fila} ${cx - anchoDe(sig.valor) / 2},${y + fila}`} style={{ fill: pin.col(it.color) }} />}
                <rect id={id} className="gr-forma" x={cx - ancho / 2} y={y} width={ancho} height={bh} rx={Math.min(6, bh / 3)} style={{ fill: fondo, stroke: pin.col(it.color) }} />
                {txt && <text className={`gr-fuerte${txt.dentro ? ' gr-dentro' : ''}`} data-forma={txt.dentro ? id : undefined} x={txt.x} y={y + bh / 2} dy="0.35em" textAnchor={txt.ancla} style={txt.dentro ? { fill: pin.texto(fondo) } : undefined} pointerEvents="none">{txt.t}</text>}
              </g>
              {conPaso && i > 0 && <text className="gr-paso gr-aparece" x={w - 4} y={2 + fila * i} dy="0.35em" textAnchor="end" style={{ '--o': ord(i, n) + 3 }}>{pasos[i]}</text>}
            </g>
          )
        })}
      </g>
    </Svg>
  )
}

/** Treemap «squarified» (Bruls et al.): rectángulos lo más cuadrados posible, área ∝ valor. */
export function squarify(items, x, y, w, h) {
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
 * Etiqueta de un recuadro, de más a menos: nombre en 1 renglón + valor·%, nombre + %, nombre en 2 renglones (por palabras)
 * + valor·% o %, nombre truncado con «…» (≥ 6 caracteres) + %, solo %, nada (queda el tooltip). Todo medido.
 * Devuelve { nombre: [renglones], valor } o null.
 */
function etiquetaRecuadro(cw, ch, nombreTxt, valorTxt, pct) {
  const util = cw - 16
  const alto = (renglones, conValor) => 17 + (renglones - 1) * 15 + (conValor ? 16 : 0) + 9 // centro del último + medio texto + aire
  const vp = `${valorTxt} · ${pct}`
  const p1 = partirNombre(nombreTxt, util, 1)
  const p2 = partirNombre(nombreTxt, util, 2)
  const opciones = []
  if (p1?.completo) opciones.push({ n: p1.lineas, v: vp }, { n: p1.lineas, v: pct })
  if (p2?.completo) opciones.push({ n: p2.lineas, v: vp }, { n: p2.lineas, v: pct })
  if (p2 && !p2.completo) opciones.push({ n: p2.lineas, v: pct })
  if (p1 && !p1.completo) opciones.push({ n: p1.lineas, v: pct })
  for (const o of opciones) if (ch >= alto(o.n.length, true) && util >= anchoVal(o.v)) return { nombre: o.n, valor: o.v }
  if (ch >= 24 && cw - 14 >= anchoVal(pct)) return { nombre: [], valor: pct }
  return null
}
function Arbol({ w, h, d, ix, uid }) {
  const pin = usePintura()
  const variante = useOrden()(0, 3) // 0, 1 o 2 según la variante de este montaje
  const { tipo, total } = d
  const items = d.items.filter((i) => i.valor > 0).sort((a, b) => b.valor - a.valor)
  const celdas = squarify(items, 0, 0, w, h)
  // Orden del mosaico: en diagonal (0), del más grande al más chico (1) o en diagonal inversa (2).
  const rango = celdas.map((c, i) => [variante === 1 ? i : variante === 2 ? -(c.x + c.y) : c.x + c.y, i]).sort((a, b) => a[0] - b[0]).map(([, i]) => i)
  const ordenDe = new Map(rango.map((i, k) => [i, k]))
  return (
    <Svg w={w} h={h} aria={`${d.pie}: ${items.map((i) => `${i.etiqueta} ${fmt(tipo, i.valor)}`).join(', ')}`}>
      <g className="gr-marcas">
        {celdas.map(({ it, x, y, w: cw, h: ch }, i) => {
          const pct = fmtPct(it.valor / total)
          const fondo = pin.relleno(it.color)
          const id = `${uid}-t${i}`
          const etq = etiquetaRecuadro(cw, ch, it.etiqueta, fmtCorto(tipo, it.valor), pct)
          const tx = pin.texto(fondo)
          return (
            <g key={it.id} className={`gr-m${ix.c(it.id)}`} {...ix.p(it.id, it.larga, [[d.que, fmt(tipo, it.valor), pin.col(it.color)], ['Del total', pct], ['Registros', fmt('numero', it.n)]])}>
              <g className="gr-a-mosaico" style={{ '--o': ordenDe.get(i) }}>
                <rect id={id} className="gr-forma" x={x + 1.5} y={y + 1.5} width={Math.max(0, cw - 3)} height={Math.max(0, ch - 3)} rx={Math.min(8, cw / 4, ch / 4)} style={{ fill: fondo, stroke: pin.col(it.color) }} />
                {etq && etq.nombre.map((t, k) => <text key={k} className="gr-dentro" data-forma={id} x={x + 9} y={y + 17 + k * 15} dy="0.35em" style={{ fill: tx }} pointerEvents="none">{t}</text>)}
                {etq && <text className="gr-valor gr-dentro" data-forma={id} x={x + (etq.nombre.length ? 9 : 8)} y={etq.nombre.length ? y + 17 + (etq.nombre.length - 1) * 15 + 16 : y + 14} dy="0.35em" style={{ fill: tx }} pointerEvents="none">{etq.valor}</text>}
              </g>
            </g>
          )
        })}
      </g>
    </Svg>
  )
}

/** Radar: el radio se ajusta para usar todo el espacio con las etiquetas completas adentro (búsqueda binaria). */
function Radar({ w, h, d, ix }) {
  const pin = usePintura(); const ord = useOrden()
  const { items, tipo } = d
  const n = items.length
  const cx = w / 2; const cy = h / 2
  const ang = (i) => (i * 2 * Math.PI) / n
  const textos = items.map((it) => cortar(it.etiqueta, Math.min(110, w * 0.3)))
  const lim = { x: 1, y: 1, w: w - 2, h: h - 2 }
  const cajasCon = (R) => items.map((_, i) => {
    const s = Math.sin(ang(i)); const c = -Math.cos(ang(i))
    const [x, y] = punto(cx, cy, R + 8, ang(i))
    const ancla = s > 0.3 ? 'start' : s < -0.3 ? 'end' : 'middle'
    const yy = y + (c < -0.5 ? -4 : c > 0.5 ? 4 : 0)
    return { x, y: yy, ancla, caja: cajaTexto(x, yy, anchoTexto(textos[i]), ancla) }
  })
  const Rmax = Math.max(12, Math.min(w, h) / 2 - 6)
  const caben = (R) => cajasCon(R).every((e, i) => !textos[i] || cabeEn(e.caja, lim))
  let R = Rmax
  let conEtq = w >= 180 && h >= 120
  if (conEtq) {
    let lo = Rmax * 0.4; let hi = Rmax
    if (!caben(lo)) conEtq = false
    else { for (let k = 0; k < 18; k++) { const m = (lo + hi) / 2; if (caben(m)) lo = m; else hi = m } R = lo }
  }
  const etq = conEtq ? cajasCon(R) : []
  const ok = conEtq ? sinChoques(etq.map((e, i) => ({ id: i, caja: e.caja, prio: items[i].valor })), lim) : new Set()
  const tk = ticks(0, Math.max(0, ...items.map((i) => i.valor)), R >= 90 ? 4 : 2, d.entero)
  const max = tk[tk.length - 1] || 1
  const pt = (i, v) => punto(cx, cy, R * (v / max), ang(i))
  const poly = items.map((it, i) => pt(i, it.valor).map((z) => z.toFixed(1)).join(',')).join(' ')
  const origen = { transformOrigin: `${cx}px ${cy}px` }
  const conTk = R >= 60 && R / (tk.length - 1) >= 16
  return (
    <Svg w={w} h={h} aria={`${d.pie}: ${items.map((i) => `${i.etiqueta} ${fmt(tipo, i.valor)}`).join(', ')}`}>
      <g className="gr-rejilla" aria-hidden="true">
        {tk.slice(1).map((v, k) => <polygon key={v} className="gr-a-expande" points={items.map((_, i) => pt(i, v).join(',')).join(' ')} style={{ ...origen, '--o': k }} />)}
        {items.map((it, i) => { const [x, y] = pt(i, max); return <line key={it.id} x1={cx} y1={cy} x2={x} y2={y} /> })}
        {conTk && tk.slice(1).map((v) => <text key={v} x={cx + 4} y={cy - R * (v / max)} dy="0.9em" className="gr-sutil">{fEje(tipo)(v)}</text>)}
      </g>
      <polygon className="gr-radar gr-a-expande" points={poly} style={{ fill: pin.acento, stroke: pin.acento, ...origen, '--o': tk.length + 1 }} />
      <g className="gr-marcas">
        {items.map((it, i) => {
          const [x, y] = pt(i, it.valor)
          return (
            <g key={it.id} className={`gr-m${ix.c(it.id)}`} {...ix.p(it.id, it.larga, [[d.que, fmt(tipo, it.valor), pin.col(it.color)], ['Del total', fmtPct(E.porcentajeDelTotal(it.valor, d.total))]])}>
              <circle className="gr-hit" cx={x} cy={y} r="12" />
              <circle className="gr-punto gr-a-pop" cx={x} cy={y} r={ix.activo === it.id ? 6 : 4} style={{ fill: pin.col(it.color), stroke: pin.sup, '--o': ord(i, n) + tk.length + 3 }} />
              {ok.has(i) && <text className="gr-aparece" x={etq[i].x} y={etq[i].y} dy="0.35em" textAnchor={etq[i].ancla} style={{ '--o': tk.length + 4 }}>{textos[i]}</text>}
            </g>
          )
        })}
      </g>
    </Svg>
  )
}

// ── Distribución y correlación ────────────────────────────────────────────────────────────────────
/** Ejes numéricos libres (dispersión y burbujas). */
export function ejesXY(w, h, { xmin, xmax, ymin, ymax, fx, fy, xFecha }) {
  const ty = ticks(ymin, ymax, h < 130 ? 2 : 4)
  const textosY = ty.map(fy)
  const necesita = Math.max(...textosY.map((t) => anchoTexto(t))) + 10
  const conY = w >= 170 && h >= 80 && necesita <= w * 0.4
  const izq = conY ? necesita : 6
  const conX = h >= 70
  const x0 = izq; const x1 = w - 12; const y1 = 10; const y0 = h - (conX ? 20 : 8)
  let tx
  if (xFecha) {
    const n = Math.max(2, Math.min(5, Math.floor((x1 - x0) / 70)))
    tx = Array.from({ length: n }, (_, i) => xmin + ((xmax - xmin) * i) / (n - 1))
  } else tx = ticks(xmin, xmax, Math.max(2, Math.min(5, Math.floor((x1 - x0) / 70))))
  const X = escala(xFecha ? xmin : tx[0], xFecha ? (xmax > xmin ? xmax : xmin + 1) : tx[tx.length - 1], x0, x1)
  const Y = escala(ty[0], ty[ty.length - 1], y0, y1)
  return { w, x0, x1, y0, y1, X, Y, tx, ty, textosY, conY, conX, fx }
}
export function RejillaXY({ e }) {
  // Etiquetas X: se aceptan de la última a la primera sin encimarse ni salir del SVG.
  const xs = []
  if (e.conX) {
    let limite = e.w - 1
    for (let i = e.tx.length - 1; i >= 0; i--) {
      const t = e.fx(e.tx[i]); const a = anchoTexto(t)
      const x0 = Math.max(e.conY ? e.x0 - 2 : 1, Math.min(e.w - 1 - a, e.X(e.tx[i]) - a / 2))
      if (x0 + a > limite - 6) continue
      xs.push({ i, t, x0 }); limite = x0
    }
  }
  return (
    <g className="gr-rejilla" aria-hidden="true">
      {e.ty.map((v, i) => <g key={`y${i}`}><line x1={e.x0} x2={e.x1} y1={e.Y(v)} y2={e.Y(v)} />{e.conY && <text x={e.x0 - 6} y={e.Y(v)} dy="0.35em" textAnchor="end">{e.textosY[i]}</text>}</g>)}
      {xs.map(({ i, t, x0 }) => <text key={`x${i}`} x={x0} y={e.y0 + 14}>{t}</text>)}
    </g>
  )
}

function Dispersion({ w, h, d, ix, uid }) {
  const pin = usePintura()
  const { puntos } = d
  const xs = puntos.map((p) => p.x); const ys = puntos.map((p) => p.y)
  const ley = d.series.length > 1 ? planLeyenda(w, h, d.series) : { lado: null }
  const a = areaCon(ley, w, h)
  const e = ejesXY(a.w, a.h, { xmin: Math.min(...xs), xmax: Math.max(...xs), ymin: Math.min(0, ...ys), ymax: Math.max(0, ...ys), fx: d.fx, fy: d.fyEje, xFecha: d.xFecha })
  const tl = d.tl
  const xa = Math.min(...xs); const xb = Math.max(...xs)
  const r = puntos.length > 120 ? 3 : 4
  return (
    <Svg w={w} h={h} aria={d.pie}>
      <defs><clipPath id={`gr-clip-${uid}`}><rect x={e.x0} y={e.y1} width={Math.max(0, e.x1 - e.x0)} height={Math.max(0, e.y0 - e.y1)} /></clipPath></defs>
      <RejillaXY e={e} />
      {tl.n >= 2 && xb > xa && <line className="gr-tendencia gr-aparece" clipPath={`url(#gr-clip-${uid})`} x1={e.X(xa)} y1={e.Y(tl.en(d.xFecha ? xa / 864e5 : xa))} x2={e.X(xb)} y2={e.Y(tl.en(d.xFecha ? xb / 864e5 : xb))} style={{ stroke: COLORES[2], '--o': 18 }} />}
      <g className="gr-marcas">
        {puntos.map((pt, i) => (
          <circle key={pt.id} className={`gr-punto gr-a-pop gr-m${ix.c(pt.id, pt.serie)}`} cx={e.X(pt.x)} cy={e.Y(pt.y)} r={ix.activo === pt.id ? r + 2.5 : r}
            style={{ fill: pin.col(pt.color), fillOpacity: 0.7, stroke: pin.col(pt.color), '--o': tope(Math.floor(i / 6)) }}
            {...ix.p(pt.id, pt.titulo, [[d.nx, d.fx(pt.x, true)], [d.ny, d.fy(pt.y), pin.col(pt.color)], ...(pt.serieNombre ? [[d.ne, pt.serieNombre, pin.col(pt.color)]] : [])])} />
        ))}
      </g>
      {ley.lado && <Leyenda plan={ley} w={w} h={h} ix={ix} items={d.series} />}
    </Svg>
  )
}

function Burbujas({ w, h, d, ix, uid }) {
  const pin = usePintura(); const ord = useOrden()
  const { items, tipo } = d
  const e = ejesXY(w, h, { xmin: 0, xmax: Math.max(...items.map((i) => i.n)) * 1.15, ymin: 0, ymax: Math.max(...items.map((i) => i.prom)) * 1.18, fx: (v) => fmt('numero', v), fy: fEje(tipo) })
  const maxS = Math.max(1e-9, ...items.map((i) => i.suma))
  const rMax = Math.max(6, Math.min(e.x1 - e.x0, e.y0 - e.y1) / 6.5)
  const orden = [...items].sort((a, b) => b.suma - a.suma).map((it) => ({ it, r: Math.max(4, rMax * Math.sqrt(Math.max(0, it.suma) / maxS)), x: e.X(it.n), y: e.Y(it.prom) }))
  // Etiqueta solo si su caja cabe en su burbuja y no toca ninguna otra burbuja ni otra etiqueta.
  const puestas = []
  const etq = orden.map((b, i) => {
    const t = b.it.etiqueta
    const caja = cajaTexto(b.x, b.y, anchoTexto(t), 'middle')
    const enCirculo = (c, x, y, r) => [[c.x, c.y], [c.x + c.w, c.y], [c.x, c.y + c.h], [c.x + c.w, c.y + c.h]].every(([px, py]) => Math.hypot(px - x, py - y) <= r - 2)
    const tocaCirc = (c, o) => { const nx = Math.max(c.x, Math.min(o.x, c.x + c.w)); const ny = Math.max(c.y, Math.min(o.y, c.y + c.h)); return Math.hypot(nx - o.x, ny - o.y) < o.r + 1 }
    const ok = b.r >= 14 && enCirculo(caja, b.x, b.y, b.r) && !orden.some((o, j) => j !== i && tocaCirc(caja, o)) && !puestas.some((c) => choca(c, caja, 2))
    if (ok) puestas.push(caja)
    return ok ? t : null
  })
  return (
    <Svg w={w} h={h} aria={d.pie}>
      <RejillaXY e={e} />
      <g className="gr-marcas">
        {orden.map(({ it, r, x, y }, i) => {
          const fondo = pin.relleno(it.color)
          const id = `${uid}-u${i}`
          return (
            <g key={it.id} className={`gr-m${ix.c(it.id)}`} {...ix.p(it.id, it.etiqueta, [['Registros', fmt('numero', it.n)], [`Promedio de ${d.nv}`, fmt(tipo, it.prom), pin.col(it.color)], [`Total de ${d.nv}`, fmt(tipo, it.suma)]])}>
              <circle id={id} className="gr-forma gr-burbuja gr-a-pop" cx={x} cy={y} r={r} style={{ fill: fondo, stroke: pin.col(it.color), '--o': ord(i, orden.length) }} />
              {etq[i] && <text className="gr-dentro gr-aparece" data-forma={id} x={x} y={y} dy="0.35em" textAnchor="middle" style={{ fill: pin.texto(fondo), '--o': ord(i, orden.length) + 4 }} pointerEvents="none">{etq[i]}</text>}
            </g>
          )
        })}
      </g>
    </Svg>
  )
}

function Histograma({ w, h, d, ix }) {
  const pin = usePintura(); const ord = useOrden()
  const { bins, tipo, prom, med } = d
  const una = bins.length === 1
  const conMarcas = !una && w >= 220 && h >= 120
  const p = plano(w, h, { max: Math.max(...bins.map((b) => b.conteo)), f: (v) => fmt('numero', v), entero: true, arriba: conMarcas ? 24 : 10 })
  const banda = p.ancho / bins.length
  const X = escala(bins[0].desde, bins[bins.length - 1].hasta, p.x0, p.x1)
  const fx = fEje(tipo)
  const etiquetas = bins.map((b, i) => ({ x: p.x0 + banda * i + (una ? banda / 2 : 0), t: fx(b.desde) }))
  // «promedio» y «mediana» en la franja de arriba; si chocan, se muestra solo el promedio (los dos valores están en el pie).
  const marcas = [['promedio', prom, COLORES[2]], ['mediana', med, COLORES[5]]].map(([t, v, c]) => {
    const der = X(v) > (p.x0 + p.x1) / 2
    const x = X(v) + (der ? -5 : 5)
    return { t, v, c, x, ancla: der ? 'end' : 'start', caja: cajaTexto(x, 11, anchoTexto(t, 11, 600), der ? 'end' : 'start') }
  })
  const okM = sinChoques(marcas.map((m, i) => ({ id: i, caja: m.caja, prio: 2 - i })), { x: 0, y: 0, w, h })
  const ac = pin.acento
  return (
    <Svg w={w} h={h} aria={`${d.pie}: ${bins.map((b) => `${fmt(tipo, b.desde)}–${fmt(tipo, b.hasta)}: ${b.conteo}`).join(', ')}`}>
      <Rejilla p={p} />
      <g className="gr-marcas">
        {bins.map((b, i) => {
          const id = `b${i}`
          const ya = p.y(b.conteo)
          return (
            <g key={id} className={`gr-m${ix.c(id)}`} {...ix.p(id, `${fmt(tipo, b.desde)} – ${fmt(tipo, b.hasta)}`, [['Registros', fmt('numero', b.conteo), ac], ['Del total', fmtPct(E.porcentajeDelTotal(b.conteo, d.n))]])}>
              <rect className="gr-hit" x={p.x0 + banda * i} y={p.y1} width={banda} height={p.alto} />
              <rect className="gr-a-col" x={p.x0 + banda * i + 1} y={ya} width={Math.max(1, banda - 2)} height={Math.max(b.conteo ? 1 : 0, p.y0 - ya)} rx="2" style={{ fill: pin.relleno(ac), stroke: ac, '--o': ord(i, bins.length) }} />
            </g>
          )
        })}
      </g>
      {conMarcas && marcas.map((m, k) => (
        <g key={m.t} className="gr-aparece" style={{ '--o': 16 + k }} pointerEvents="none">
          <line className="gr-marca-v" x1={X(m.v)} x2={X(m.v)} y1={okM.has(k) ? 18 : p.y1} y2={p.y0} style={{ stroke: m.c }} />
          {okM.has(k) && <text x={m.x} y={11} dy="0.35em" textAnchor={m.ancla} className="gr-fuerte">{m.t}</text>}
        </g>
      ))}
      {p.conX && <EjeX p={p} items={etiquetas} />}
    </Svg>
  )
}

function Caja({ w, h, d, ix }) {
  const pin = usePintura(); const ord = useOrden()
  const { cajas, tipo } = d
  const conCaja = cajas.filter((c) => c.q)
  const p = plano(w, h, { min: Math.min(0, ...conCaja.map((c) => c.q.min)), max: Math.max(...conCaja.map((c) => c.q.max)), f: fEje(tipo), etiquetas: cajas.length > 1 })
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
          const col = pin.col(c.color)
          return (
            <g key={c.id} className={`gr-m${ix.c(c.id)}`} {...ix.p(c.id, c.etiqueta, [['Máximo', fmt(tipo, q.max)], ['Q3 (75 %)', fmt(tipo, q.q3)], ['Mediana', fmt(tipo, q.mediana), col], ['Q1 (25 %)', fmt(tipo, q.q1)], ['Mínimo', fmt(tipo, q.min)], ['Registros', fmt('numero', q.n)]])}>
              <rect className="gr-hit" x={p.x0 + banda * i} y={p.y1} width={banda} height={p.alto} />
              <g className="gr-a-caja" style={{ '--o': ord(i, cajas.length) }}>
                <line className="gr-bigote" x1={xc} x2={xc} y1={p.y(q.max)} y2={p.y(q.q3)} style={{ stroke: col }} />
                <line className="gr-bigote" x1={xc} x2={xc} y1={p.y(q.q1)} y2={p.y(q.min)} style={{ stroke: col }} />
                <line className="gr-bigote" x1={xc - bw / 4} x2={xc + bw / 4} y1={p.y(q.max)} y2={p.y(q.max)} style={{ stroke: col }} />
                <line className="gr-bigote" x1={xc - bw / 4} x2={xc + bw / 4} y1={p.y(q.min)} y2={p.y(q.min)} style={{ stroke: col }} />
                <rect className="gr-caja" x={xc - bw / 2} y={p.y(q.q3)} width={bw} height={Math.max(1, p.y(q.q1) - p.y(q.q3))} rx="3" style={{ fill: pin.relleno(c.color), stroke: col }} />
                <line className="gr-mediana" x1={xc - bw / 2} x2={xc + bw / 2} y1={p.y(q.mediana)} y2={p.y(q.mediana)} style={{ stroke: pin.texto(pin.relleno(c.color)) }} />
              </g>
            </g>
          )
        })}
      </g>
      <EjeX p={p} items={cajas.length > 1 ? cajas.map((c, i) => ({ x: p.x0 + banda * (i + 0.5), t: c.etiqueta })) : []} />
    </Svg>
  )
}

// ── Tiempo ────────────────────────────────────────────────────────────────────────────────────────
/** Calendario de calor estilo GitHub: columnas = semanas (lunes a domingo). Se llena casilla por casilla en diagonal. */
function Calendario({ w, h, d, ix }) {
  const pin = usePintura()
  const variante = useOrden()(0, 3)
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
  const COL = nivelesCalor(pin)
  // Meses arriba: de derecha a izquierda, sin encimarse.
  const meses = []
  celdas.forEach((c, i) => { if (i % 7 === 0) { const col = i / 7; const m = c.fecha.getMonth(); if (!meses.length || meses[meses.length - 1].m !== m) meses.push({ m, col }) } })
  const mesesOk = []
  let limite = w
  for (const mm of [...meses].reverse()) { const x = x0 + mm.col * (s + gap); const a = anchoTexto(E.MESES[mm.m]); if (x + a <= limite - 4 && x >= 0) { mesesOk.push(mm); limite = x } }
  const orden = (col, fila) => (variante === 1 ? col : variante === 2 ? cols - 1 - col + fila : col + fila)
  return (
    <Svg w={w} h={h} aria={`${d.pie}: ${d.totalTexto}`}>
      {conMeses && mesesOk.map(({ m, col }) => <text key={`${m}-${col}`} x={x0 + col * (s + gap)} y={y0 - 8} dy="0.35em" className="gr-sutil">{E.MESES[m]}</text>)}
      {conDias && [0, 2, 4].map((r) => <text key={r} x={x0 - 6} y={y0 + r * (s + gap) + s / 2} dy="0.35em" textAnchor="end" className="gr-sutil">{['lun', 'mar', 'mié', 'jue', 'vie', 'sáb', 'dom'][r]}</text>)}
      <g className="gr-marcas">
        {celdas.map((c, i) => {
          const col = Math.floor(i / 7); const fila = i % 7
          const lv = nivel(c.v)
          return (
            <rect key={c.iso} className={`gr-celda gr-a-casilla${c.futuro ? ' gr-futuro' : ''}${c.hoy ? ' gr-hoy' : ''}${ix.c(c.iso)}`} x={x0 + col * (s + gap)} y={y0 + fila * (s + gap)} width={s} height={s} rx={Math.min(3, s / 4)}
              style={{ fill: lv ? COL[lv] : undefined, '--o': orden(col, fila) }}
              {...ix.p(c.iso, fechaLarga(c.fecha), [[d.que, fmt(d.tipo, c.v), lv ? COL[lv] : undefined], ...(c.futuro ? [['', 'día por venir']] : [])])} />
          )
        })}
      </g>
      {conLey && (
        <g className="gr-aparece" style={{ '--o': 30 }} transform={`translate(${w - 100},${h - 9})`}>
          <text x="-4" dy="0.35em" textAnchor="end" className="gr-sutil">Menos</text>
          {COL.map((c, k) => <rect key={k} className="gr-celda" x={k * 14} y="-5.5" width="11" height="11" rx="2.5" style={{ fill: c || undefined }} />)}
          <text x={5 * 14 + 2} dy="0.35em" className="gr-sutil">Más</text>
        </g>
      )}
    </Svg>
  )
}

/** Cascada (meses COMPLETOS): valor del primer mes, cambio de cada mes contra el anterior y valor final. Se arma en cadena. */
function Cascada({ w, h, d, ix }) {
  const pin = usePintura()
  const { barras, tipo } = d
  const niveles = barras.flatMap((b) => [b.desde, b.hasta])
  const p = plano(w, h, { min: Math.min(0, ...niveles), max: Math.max(0, ...niveles), f: fEje(tipo), entero: d.entero, arriba: 20 })
  const n = barras.length
  const banda = p.ancho / n
  const bw = Math.max(2, Math.min(44, banda * 0.62))
  const xc = (i) => p.x0 + banda * (i + 0.5)
  const etq = p.alto >= 80 ? barras.map((b, i) => {
    const y = p.y(Math.max(b.desde, b.hasta)) - 10
    return { id: b.id, t: b.corto, x: xc(i), y, caja: cajaTexto(xc(i), y, anchoVal(b.corto), 'middle', 12), prio: (b.tipo === 'total' ? 1e12 : 0) + Math.abs(b.hasta - b.desde) }
  }) : []
  const ok = sinChoques(etq.filter((e) => e.prio > 0), { x: 0, y: 0, w, h: p.y0 + 1 }, [], 3)
  return (
    <Svg w={w} h={h} aria={`${d.pie}: ${barras.map((b) => `${b.larga} ${b.texto}`).join(', ')}`}>
      <Rejilla p={p} />
      <g className="gr-marcas">
        {barras.map((b, i) => {
          const ya = p.y(Math.max(b.desde, b.hasta)); const yb = p.y(Math.min(b.desde, b.hasta))
          const color = b.tipo === 'total' ? ACENTO : b.hasta >= b.desde ? VERDE : ROJO
          const sig = barras[i + 1]
          return (
            <g key={b.id} className={`gr-m${ix.c(b.id)}`} {...ix.p(b.id, b.larga, b.tipo === 'total' ? [[d.que, fmt(tipo, b.hasta), pin.col(color)]] : [['Cambio', b.texto, pin.col(color)], ['Antes', fmt(tipo, b.desde)], ['Después', fmt(tipo, b.hasta)], ['Variación', fmtPct(E.variacion(b.hasta, b.desde), true)]])}>
              <rect className="gr-hit" x={p.x0 + banda * i} y={p.y1} width={banda} height={p.alto} />
              <rect className={b.hasta >= b.desde ? 'gr-a-cadena' : 'gr-a-cadena-baja'} x={xc(i) - bw / 2} y={ya} width={bw} height={Math.max(1, yb - ya)} rx="2.5" style={{ fill: pin.relleno(color), stroke: pin.col(color), '--o': i }} />
              {sig && <line className="gr-conector gr-aparece" x1={xc(i) + bw / 2} x2={xc(i) + banda - bw / 2} y1={p.y(b.hasta)} y2={p.y(b.hasta)} style={{ '--o': i + 1 }} />}
            </g>
          )
        })}
      </g>
      <g pointerEvents="none">
        {etq.filter((e) => ok.has(e.id)).map((e, i) => <text key={e.id} className="gr-valor gr-aparece" x={e.x} y={e.y} dy="0.35em" textAnchor="middle" style={{ '--o': i + 2 }}>{e.t}</text>)}
      </g>
      <EjeX p={p} items={barras.map((b, i) => ({ x: xc(i), t: b.etiqueta }))} />
    </Svg>
  )
}

/** KPI: lo que va del mes en curso contra LOS MISMOS DÍAS del mes anterior, y sparkline de 12 meses (el último, punteado). */
function Kpi({ w, h, d, ix, uid }) {
  const pin = usePintura()
  const fila = w >= 360 && h < 170
  const tam = Math.round(Math.max(18, Math.min(40, w / 7, h / (fila ? 2.6 : 3.4))))
  const sw = fila ? Math.round(w * 0.42) : w - 4
  const sh = fila ? h - 20 : Math.max(0, h - tam - 58)
  const conSpark = sh >= 22 && sw >= 60
  const vals = d.items.map((i) => i.valor)
  const max = Math.max(1e-9, ...vals); const min = Math.min(0, ...vals)
  const X = escala(0, Math.max(1, vals.length - 1), 4, sw - 4)
  const Y = escala(min, max, sh - 4, 4)
  const ruta = (xs, desde = 0) => xs.map((v, i) => `${i ? 'L' : 'M'}${X(i + desde).toFixed(1)},${Y(v).toFixed(1)}`).join(' ')
  const linea = ruta(vals.slice(0, -1))
  const resto = vals.length > 1 ? ruta(vals.slice(-2), vals.length - 2) : ''
  const gid = `gr-kdeg-${uid}`
  const v = d.var
  const clase = v === null ? 'neutro' : v > 0 ? 'sube' : v < 0 ? 'baja' : 'neutro'
  const activo = d.items.findIndex((it) => it.id === ix.activo)
  const ac = pin.acento
  return (
    <div className={`gr-kpi${fila ? ' gr-kpi-fila' : ''}`}>
      <div className="gr-kpi-txt">
        <small>{d.etiqueta}</small>
        <strong style={{ fontSize: tam }}><Cuenta v={d.actual} f={(x) => (w < 200 ? fmtCorto(d.tipo, x) : fmt(d.tipo, x))} /></strong>
        <span className={`gr-var ${clase}`}>
          <b>{v === null ? (d.anterior === 0 && d.actual > 0 ? '▲ nuevo' : '—') : v > 0 ? `▲ ${fmtPct(v)}` : v < 0 ? `▼ ${fmtPct(-v)}` : '= 0 %'}</b>
          {w >= 200 && <i> vs {d.tramoAnterior} ({fmtCorto(d.tipo, d.anterior)})</i>}
        </span>
      </div>
      {conSpark && (
        <svg className="gr-svg gr-spark" width={sw} height={sh} viewBox={`0 0 ${sw} ${sh}`} role="img" aria-label={`Últimos ${vals.length} meses: ${d.items.map((i) => `${i.larga} ${fmt(d.tipo, i.valor)}`).join(', ')}`}>
          <defs><linearGradient id={gid} x1="0" y1="0" x2="0" y2="1"><stop offset="0" style={{ stopColor: ac, stopOpacity: 0.28 }} /><stop offset="1" style={{ stopColor: ac, stopOpacity: 0 }} /></linearGradient></defs>
          <path className="gr-area gr-a-area" d={`${ruta(vals)} L${X(vals.length - 1)},${sh} L${X(0)},${sh} Z`} style={{ fill: `url(#${gid})` }} />
          <path className="gr-traza gr-linea" d={linea} pathLength="1" style={{ stroke: ac }} />
          {resto && <path className="gr-linea gr-parcial-l gr-aparece" d={resto} style={{ stroke: ac, '--o': 14 }} />}
          <circle className="gr-punto gr-a-pop" cx={X(vals.length - 1)} cy={Y(vals[vals.length - 1])} r="3.5" style={{ fill: pin.sup, stroke: ac, strokeDasharray: '2 1.5', '--o': 16 }} />
          {activo >= 0 && <circle cx={X(activo)} cy={Y(vals[activo])} r="4" style={{ fill: ac }} />}
          {d.items.map((it, i) => <rect key={it.id} className="gr-hit" x={X(i) - sw / vals.length / 2} y="0" width={sw / vals.length} height={sh} {...ix.p(it.id, it.larga, [[d.que, fmt(d.tipo, it.valor), ac], ...(it.parcial ? [['Mes en curso', 'incompleto']] : [])])} />)}
        </svg>
      )}
    </div>
  )
}

// ── Resúmenes ─────────────────────────────────────────────────────────────────────────────────────
/** Tabla de posiciones: top N por un campo texto, con barra relativa al primero. */
function Posiciones({ h, d, ix }) {
  const pin = usePintura()
  const { items, tipo, total } = d
  const max = Math.max(1e-9, ...items.map((i) => i.valor))
  const compacta = h < items.length * 42
  return (
    <ol className={`gr-pos${compacta ? ' compacta' : ''}${h < items.length * 29 ? ' desborda' : ''}`} aria-label={d.pie}>
      {items.map((it, i) => (
        <li key={it.id} className={`gr-m gr-fila${ix.c(it.id)}`} style={{ '--i': i }} {...ix.p(it.id, it.etiqueta, [[d.que, fmt(tipo, it.valor), pin.acento], ['Del total', fmtPct(E.porcentajeDelTotal(it.valor, total))], ['Registros', fmt('numero', it.n)]])}>
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
  const pin = usePintura()
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
  // Si ni el valor compacto cabe en la casilla (14 px), una columna menos.
  const casilla = (c) => (w - (c - 1) * 6) / c - 20
  const anchoMin = Math.max(...[s.promedio, s.mediana, s.min, s.max, s.desv, s.suma].map((v) => anchoTexto(fmtCorto(tipo, v), 14, 600)))
  while (cols > 1 && cols <= 3 && anchoMin > casilla(cols)) cols--
  const lista = h < Math.ceil(6 / cols) * 46
  const largo = Math.max(...[s.promedio, s.mediana, s.min, s.max, s.desv, s.suma].map((v) => anchoVal(fmt(tipo, v)))) + 78
  if (lista) cols = Math.max(1, Math.min(3, Math.floor((w + 14) / (largo + 14))))
  const desborda = lista && h < Math.ceil(6 / cols) * 17
  const anchoCasilla = (w - (cols - 1) * 6) / cols - 20
  const valTxt = (v) => (anchoTexto(fmt(tipo, v), 14, 600) <= anchoCasilla ? fmt(tipo, v) : fmtCorto(tipo, v))
  const conTira = !lista && h >= Math.ceil(6 / cols) * 46 + 42 && s.q && s.max > s.min
  const X = s.q ? escala(s.min, s.max > s.min ? s.max : s.min + 1, 8, w - 8) : null
  const ac = pin.acento
  return (
    <div className={`gr-stats${lista ? ' lista' : ''}${desborda ? ' desborda' : ''}`} style={{ '--cols': cols }}>
      <div className="gr-stats-rej">
        {tiles.map(([t, v, ayuda], i) => (
          <div key={t} className={`gr-stat gr-m gr-fila${ix.c(t)}`} style={{ '--i': i }} {...ix.p(t, t, [[ayuda, '']])}>
            <small>{t}</small><strong><Cuenta v={v} f={(x) => (valTxt(v) === fmt(tipo, v) ? fmt(tipo, x) : fmtCorto(tipo, x))} /></strong>
          </div>
        ))}
      </div>
      {conTira && (
        <svg className="gr-svg gr-tira gr-aparece" style={{ '--o': 8 }} width={w} height="34" viewBox={`0 0 ${w} 34`} role="img" aria-label={`Distribución: Q1 ${fmt(tipo, s.q.q1)}, mediana ${fmt(tipo, s.q.mediana)}, Q3 ${fmt(tipo, s.q.q3)}`}>
          <line className="gr-bigote" x1={X(s.min)} x2={X(s.max)} y1="10" y2="10" style={{ stroke: ac }} />
          <rect className="gr-caja" x={X(s.q.q1)} y="3" width={Math.max(1, X(s.q.q3) - X(s.q.q1))} height="14" rx="3" style={{ fill: pin.relleno(ac), stroke: ac }} />
          <line className="gr-mediana" x1={X(s.q.mediana)} x2={X(s.q.mediana)} y1="3" y2="17" style={{ stroke: pin.texto(pin.relleno(ac)) }} />
          {(() => {
            const a = fEje(tipo)(s.min); const b = fEje(tipo)(s.max)
            const cajas = [cajaTexto(X(s.min), 29, anchoTexto(a), 'start', 11, false), cajaTexto(X(s.max), 29, anchoTexto(b), 'end', 11, false)]
            const conMed = w >= 300 && !cajas.some((c) => choca(c, cajaTexto(X(s.q.mediana), 29, anchoTexto('mediana'), 'middle', 11, false), 4))
            return <>
              {!choca(cajas[0], cajas[1], 4) && <text x={X(s.min)} y="29" className="gr-sutil">{a}</text>}
              <text x={X(s.max)} y="29" textAnchor="end" className="gr-sutil">{b}</text>
              {conMed && <text x={X(s.q.mediana)} y="29" textAnchor="middle" className="gr-sutil">mediana</text>}
            </>
          })()}
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

/** Fin del último mes COMPLETO (el día anterior al 1 del mes en curso). */
const finMesAnterior = (hoy) => new Date(hoy.getFullYear(), hoy.getMonth(), 0)

function calcCascada(regs, campos, o, hoy) {
  const m = calcMeses(regs, campos, o, finMesAnterior(hoy)) // solo meses completos: el mes en curso no se compara
  if (typeof m === 'string') return m
  const { tipo } = m
  const items = m.items.map((it) => ({ ...it, parcial: false }))
  if (!items.some((i) => i.valor)) return SIN_DATOS
  const signo = (x) => `${x > 0 ? '+' : x < 0 ? '−' : ''}${fmtCorto(tipo, Math.abs(x))}`
  const signoLargo = (x) => `${x > 0 ? '+' : x < 0 ? '−' : ''}${fmt(tipo, Math.abs(x))}`
  const barras = [{ id: 'inicio', tipo: 'total', etiqueta: items[0].etiqueta, larga: `${items[0].larga} (inicio)`, desde: 0, hasta: items[0].valor, texto: fmt(tipo, items[0].valor), corto: fmtCorto(tipo, items[0].valor) }]
  for (let i = 1; i < items.length; i++) {
    const dlt = items[i].valor - items[i - 1].valor
    barras.push({ id: items[i].id, tipo: 'cambio', etiqueta: items[i].etiqueta, larga: `${items[i].larga} vs ${items[i - 1].larga}`, desde: items[i - 1].valor, hasta: items[i].valor, texto: signoLargo(dlt), corto: signo(dlt) })
  }
  const ult = items[items.length - 1]
  barras.push({ id: 'fin', tipo: 'total', etiqueta: 'Final', larga: `${ult.larga} (final)`, desde: 0, hasta: ult.valor, texto: fmt(tipo, ult.valor), corto: fmtCorto(tipo, ult.valor) })
  return { barras, tipo, que: m.que, entero: m.entero, pie: `Meses completos · ${m.que}: cambio mes a mes por ${nombre(campos, o.fecha)} · ${items[0].larga} – ${ult.larga}` }
}

function calcKpi(regs, campos, o, hoy) {
  const m = calcMeses(regs, campos, { ...o, meses: o.meses || 12 }, hoy)
  if (typeof m === 'string') return m
  const { items, tipo, tramo } = m
  return { items, tipo, que: m.que, actual: tramo.actual, anterior: tramo.anterior, var: tramo.var, tramoAnterior: tramo.t.anterior.etiqueta,
    etiqueta: `${m.que} · ${tramo.t.actual.etiqueta}`,
    pie: `${tramo.texto}: mismos días, mes en curso vs anterior · ${m.que.toLowerCase()} por mes de ${nombre(campos, o.fecha)}` }
}

function calcMeta(regs, campos, o, hoy) {
  const m = calcMeses(regs, campos, { ...o, meses: 12 }, hoy)
  if (typeof m === 'string') return m
  const { items, tipo, tramo } = m
  const previos = items.slice(0, -1) // meses completos
  const fija = E.num(o.meta)
  let meta; let origen
  if (fija !== null && fija > 0) { meta = fija; origen = 'fijada a mano' } else {
    const mejor = previos.reduce((b, it) => (it.valor > (b?.valor ?? -Infinity) ? it : b), null)
    if (!mejor || !(mejor.valor > 0)) return 'Sin meta: aún no hay meses anteriores con datos'
    meta = mejor.valor; origen = `tu mejor mes completo (${mejor.larga})`
  }
  const diasMes = new Date(hoy.getFullYear(), hoy.getMonth() + 1, 0).getDate()
  return { valor: tramo.actual, meta, tipo, origen, dias: tramo.t.dias, diasMes, esperado: tramo.t.dias / diasMes, mes: tramo.t.actual.mes, etiqueta: `${tramo.t.actual.etiqueta} (mes en curso)`,
    pie: `${m.que} del ${tramo.t.actual.etiqueta} vs meta (${fija !== null && fija > 0 ? 'fijada' : 'mejor mes'}) · marca = esperado a hoy` }
}

function calcMedidor(regs, campos, o) {
  const ce = campoDe(campos, o.estado)
  if (!ce) return FALTA
  const grupos = E.agrupar(regs, ce).filter((g) => g.indice >= 0)
  const total = regs.length
  if (!total) return SIN_DATOS
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
  const fx = xFecha ? (v) => fechaCorta(new Date(v)) : (v, largo) => (largo ? fmt(cx.tipo, v) : fmtCorto(cx.tipo, v))
  const unidad = xFecha ? 'por día' : `por cada 1 de ${cx.nombre.toLowerCase()}`
  return { puntos, tl, xFecha, series, fx, fy: (v) => fmt(cy.tipo, v), fyEje: fEje(cy.tipo), nx: cx.nombre, ny: cy.nombre, ne: ce?.nombre,
    pie: `${cy.nombre} vs ${cx.nombre.toLowerCase()} · ${puntos.length} registros${tl.n >= 2 ? ` · tendencia ${tl.pendiente >= 0 ? '+' : '−'}${fmt(cy.tipo, Math.abs(tl.pendiente))} ${unidad}${tl.r2 !== null ? ` (r² ${fmt('numero', tl.r2)})` : ''}` : ''}` }
}

function calcBurbujas(regs, campos, o) {
  const c = campoDe(campos, o.agrupar); const cv = campoDe(campos, o.valor)
  if (!c || !cv) return FALTA
  const items = E.agrupar(regs, c, { top: c.tipo === 'texto' ? 10 : undefined }).map((g, i) => {
    const xs = g.registros.map((r) => r.valores?.[cv.id])
    return { id: g.clave, etiqueta: g.etiqueta, n: g.registros.length, prom: E.promedio(xs), suma: E.suma(xs), color: colorDe(g, i) }
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
  const cajas = grupos.map((g, i) => ({ id: g.clave, etiqueta: g.etiqueta, q: E.cuartiles(g.registros.map((r) => r.valores?.[cv.id])), color: colorDe(g, i) }))
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

// ── Catálogo ──────────────────────────────────────────────────────────────────────────────────────
export const F = { cb: 'Columnas y barras', la: 'Líneas y áreas', ci: 'Circulares', fl: 'Flujo y jerarquía', di: 'Distribución y correlación', ti: 'Tiempo', re: 'Resúmenes' }

/**
 * GRAFICOS[id] = { nombre, familia, requiere, Componente, calcular, opciones, html? }
 *  - requiere: { clase: n } o lista de alternativas. Clases: estado, estado3 (≥3 opciones), fecha, hora, medida (numero|dinero),
 *    texto, categoria (estado|texto).
 *  - opciones(b, campos): opciones por defecto (b = campos elegidos solos: estado, fecha, fecha2, hora, valor, valor2, texto, agrupar).
 *  - calcular(registros, campos, o, hoy): objeto para dibujar, o texto = estado vacío.
 *  - html: se dibuja con HTML (no SVG).
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
      const t = `${tl.pendiente >= 0 ? '+' : '−'}${fmtCorto(d.tipo, Math.abs(tl.pendiente))}/mes`
      return { ...d, ventana: v, pie: `${d.pieCorto} · tendencia ${t}${tl.r2 !== null ? `, r² ${fmt('numero', tl.r2)}` : ''}`,
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
  kpi: { nombre: 'KPI con tendencia', familia: F.ti, requiere: { fecha: 1 }, Componente: Kpi, html: true,
    opciones: (b) => ({ funcion: sumaOConteo(b) }), calcular: (r, c, o, hoy) => calcKpi(r, c, o, hoy) },
  posiciones: { nombre: 'Tabla de posiciones', familia: F.re, requiere: { texto: 1 }, Componente: Posiciones, html: true,
    opciones: (b) => ({ agrupar: b.texto, funcion: sumaOConteo(b), top: 5 }), calcular: (r, c, o) => calcPosiciones(r, c, o) },
  estadisticas: { nombre: 'Estadísticas', familia: F.re, requiere: { medida: 1 }, Componente: Estadisticas, html: true,
    opciones: () => ({}), calcular: (r, c, o) => calcEstadisticas(r, c, o) },
  ...Object.fromEntries(Object.entries(NUEVOS).map(([id, g]) => [id, { ...g, familia: F[g.familia] || g.familia }])),
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

/** Superficie, acento y gris reales (del DOM). Se vuelven a leer al cambiar el tamaño, el tema o al cargar la fuente. */
function usePinturaDe(ref, w, h) {
  const [pin, setPin] = useState(null)
  const [fuentes, setFuentes] = useState(0)
  useEffect(() => {
    let vivo = true
    if (document.fonts && document.fonts.status !== 'loaded') document.fonts.ready.then(() => { if (vivo) { olvidarAnchos(); setFuentes((x) => x + 1) } })
    const tema = ref.current?.closest('[data-tema]')
    const mo = tema && typeof MutationObserver !== 'undefined' ? new MutationObserver(() => setFuentes((x) => x + 1)) : null
    mo?.observe(tema, { attributes: true, attributeFilter: ['data-tema', 'style', 'class'] })
    return () => { vivo = false; mo?.disconnect() }
  }, [ref])
  useLayoutEffect(() => {
    const p = leerPintura(ref.current)
    setPin((a) => (a && a.sup === p.sup && a.acento === p.acento && a.gris === p.gris ? a : p))
  }, [ref, w, h, fuentes])
  return [pin, fuentes]
}

/**
 * Tooltip en <body> (posición absoluta de página): ninguna tarjeta con overflow lo recorta. Se mide y se mantiene
 * dentro de la ventana; si no cabe a la derecha/abajo del puntero, se voltea. Lleva copiadas las variables del tema.
 */
function Tip({ tip, vars }) {
  const ref = useRef(null)
  const [pos, setPos] = useState(null)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const w = el.offsetWidth; const h = el.offsetHeight
    const vw = document.documentElement.clientWidth; const vh = window.innerHeight
    let x = tip.cx + 14; if (x + w > vw - 4) x = tip.cx - 14 - w
    let y = tip.cy + 14; if (y + h > vh - 4) y = tip.cy - 12 - h
    x = Math.max(4, Math.min(vw - 4 - w, x)); y = Math.max(4, Math.min(vh - 4 - h, y))
    setPos((p) => (p && p.x === x + window.scrollX && p.y === y + window.scrollY ? p : { x: x + window.scrollX, y: y + window.scrollY }))
  }, [tip.cx, tip.cy, tip.id])
  return createPortal(
    <div ref={ref} className="gr-tip" role="status" style={{ ...vars, left: pos ? pos.x : 0, top: pos ? pos.y : 0, visibility: pos ? 'visible' : 'hidden' }}>
      <b>{tip.titulo}</b>
      {tip.filas.map(([k, v, c], i) => <span key={i}>{c ? <i style={{ background: c }} /> : null}{k}{v !== '' && <em>{v}</em>}</span>)}
    </div>,
    document.body,
  )
}

/**
 * Dibuja un gráfico del catálogo con los registros de una sección.
 * @param {string} tipo       id del catálogo GRAFICOS (p. ej. 'dona', 'linea-tendencia')
 * @param {object} seccion    la sección (se usa su título en textos accesibles)
 * @param {Array}  campos     campos de la sección [{ id, nombre, tipo, opciones? }]
 * @param {Array}  registros  [{ id, valores }]
 * @param {object} opciones   sobrescriben las elegidas solas: agrupar, estado, fecha, fecha2, hora, valor, x, y, texto, funcion,
 *                            meses, meta, objetivo, top, ventana, bins, semanas, modo, excluir, filas, pie (false = sin pie)
 */
export function Grafico({ tipo, seccion, campos = [], registros = [], opciones = {} }) {
  const def = GRAFICOS[tipo]
  const animar = useContext(AnimarContext) && !sinMovimiento()
  const vel = useContext(VelContext)
  const [ref, { w: W, h: H }] = useMedida()
  const [lienzo, { w, h }] = useMedida()
  const [pin, fuentes] = usePinturaDe(ref, w, h)
  const [variante] = useState(() => Math.floor(Math.random() * 3)) // firma de la familia, con 3 órdenes posibles por montaje
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
    setTip({ id, titulo, filas, cx: e.clientX, cy: e.clientY })
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
  return (
    <figure ref={ref} className={`gr gr-t-${tipo}${vacio ? ' gr-es-vacio' : ''}`} data-animar={animar ? '' : undefined} data-var={variante} style={{ '--vel': vel }}
      aria-label={`${def?.nombre || tipo}${seccion?.titulo ? ` · ${seccion.titulo}` : ''}`}>
      <div className={`gr-lienzo${def?.html ? ' gr-html' : ''}`} ref={lienzo} onPointerLeave={() => setTip(null)}>
        {vacio && <p className="gr-vacio">{d}</p>}
        {!vacio && C && pin && w >= 60 && h >= 36 && (
          <PinturaContext.Provider value={pin}>
            <VarianteContext.Provider value={variante}>
              <C w={w} h={h} d={d} o={o} ix={ix} uid={uid} />
            </VarianteContext.Provider>
          </PinturaContext.Provider>
        )}
        {tip && !vacio && pin && <Tip tip={tip} vars={pin.vars} />}
      </div>
      {conPie && <figcaption className="gr-pie" title={pieTxt}>{pieTxt}</figcaption>}
    </figure>
  )
}

// ── Página de prueba ──────────────────────────────────────────────────────────────────────────────
const TAMANOS = { chico: { w: 220, h: 140, nombre: 'Chico 220×140' }, mediano: { w: 340, h: 250, nombre: 'Mediano 340×250' }, grande: { w: 520, h: 360, nombre: 'Grande 520×360' } }
const deUrl = (k) => (typeof window !== 'undefined' ? new URLSearchParams(window.location.search).get(k) : null)

/**
 * Rejilla con TODOS los gráficos compatibles con una sección de la plantilla (por defecto, la que tiene más campos).
 * Props opcionales: seccionId, animar (true), vel (la del contexto), tema ('oscuro' | 'claro': envuelve en el marco .mc del CRM),
 * tamano inicial ('chico' 220×140 | 'mediano' 340×250 | 'grande' 520×360). Sin props, también lee ?tam= y ?seccion= de la URL.
 */
export function GaleriaGraficos({ plantilla, datos, seccionId, animar = true, vel, tema, tamano }) {
  const velCtx = useContext(VelContext)
  const porId = Object.fromEntries((plantilla?.secciones || []).map((s) => [s.id, s]))
  const conCampos = (plantilla?.secciones || []).filter((s) => camposDe(s, porId).length && !s.fuente)
  const masCampos = [...conCampos].sort((a, b) => camposDe(b, porId).length - camposDe(a, porId).length
    || compatibles(camposDe(b, porId)).length - compatibles(camposDe(a, porId)).length)[0]
  const [elegida, setElegida] = useState(null)
  const tamIni = tamano || deUrl('tam')
  const [tam, setTam] = useState(TAMANOS[tamIni] ? tamIni : 'mediano')
  const [vuelta, setVuelta] = useState(0)
  const seccion = porId[elegida || seccionId || deUrl('seccion')] || masCampos
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
              <section key={g.id} className="pl-bloque gr-tarjeta" data-tipo={g.id} style={{ '--i': tope(i, 30) }}>
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
