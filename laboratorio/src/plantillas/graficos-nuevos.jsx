/* Repertorio ampliado del catálogo de gráficos (16 tipos). Mismas reglas que graficos.jsx:
 * todo calculado de los registros, textos medidos (lo que no cabe no se dibuja), rellenos suavizados con contraste medido,
 * comparaciones mensuales justas (mismos días) y una animación con firma por familia.
 * Exporta NUEVOS: { id: { nombre, familia (clave corta de F), requiere, Componente, opciones, calcular, html? } }. */
import * as E from './estadistica'
import {
  anchoTexto, anchoVal, cortar, cajaTexto, choca, cabeEn, sinChoques, usePintura, useOrden, tope, escala, ticks, fEje, plano, Rejilla, EjeX,
  planLeyenda, areaCon, Leyenda, punto, sector, Cuenta, Svg, etiquetasCirculo, nivelesCalor, cajaEnSector, SEPARADOR, rotularSector, Placa, anchoPlaca, ALTO_PLACA, altoTexto, partirNombre,
} from './graficos-base'
import {
  ACENTO, sumaDe, fechaCorta, fechaLarga, campoDe, fnDe, medirDe, tipoDe, queMide, nombre, FALTA, SIN_DATOS, calcCategorias, calcMeses,
  compararTramos, conTotal, conMeses, sumaOConteo, colorDe,
} from './graficos-calculos'

const { COLORES, fmt, fmtPct, fmtCorto } = E
const DIAS = ['lun', 'mar', 'mié', 'jue', 'vie', 'sáb', 'dom']
const flecha = (v) => (v === null ? '—' : v > 0 ? `▲ ${fmtPct(v)}` : v < 0 ? `▼ ${fmtPct(-v)}` : '= 0 %')
const claseVar = (v) => (v === null ? 'neutro' : v > 0 ? 'sube' : v < 0 ? 'baja' : 'neutro')
/** Texto de valor: completo si cabe en `max`, si no compacto. */
const valorQueCabe = (tipo, v, max) => (anchoVal(fmt(tipo, v)) <= max ? fmt(tipo, v) : fmtCorto(tipo, v))

/** Reparte etiquetas en vertical (y ya ordenadas por la posición ideal) sin que se encimen dentro de [arriba, abajo]. */
function repartirVertical(ys, arriba, abajo, paso = 15) {
  const out = ys.map((y) => Math.max(arriba, Math.min(abajo, y)))
  for (let i = 1; i < out.length; i++) out[i] = Math.max(out[i], out[i - 1] + paso)
  if (out.length && out[out.length - 1] > abajo) {
    out[out.length - 1] = abajo
    for (let i = out.length - 2; i >= 0; i--) out[i] = Math.min(out[i], out[i + 1] - paso)
  }
  return out[0] === undefined || out[0] >= arriba - 0.5 ? out : null // null = no caben todas
}

// ── 1. Paleta (lollipop) ──────────────────────────────────────────────────────────────────────────
function Paleta({ w, h, d, ix }) {
  const pin = usePintura(); const ord = useOrden()
  const items = [...d.items].sort((a, b) => b.valor - a.valor)
  const { tipo, total } = d
  const n = items.length
  const conEtq = w >= 150
  const izq = conEtq ? Math.min(w * 0.36, Math.max(...items.map((i) => anchoTexto(i.etiqueta))) + 12) : 6
  const textos = items.map((i) => valorQueCabe(tipo, i.valor, w * 0.2))
  const der = w >= 170 ? Math.max(...textos.map(anchoVal)) + 16 : 8
  const x0 = izq; const x1 = Math.max(x0 + 10, w - der)
  const fila = (h - 4) / n
  const conTexto = fila >= 15
  const r = Math.max(2.5, Math.min(6, fila * 0.28))
  const x = escala(0, Math.max(1e-9, ...items.map((i) => i.valor)), x0, x1)
  return (
    <Svg w={w} h={h} aria={`${d.pie}: ${items.map((i, k) => `${i.etiqueta} ${textos[k]}`).join(', ')}`}>
      <line className="gr-eje-v" x1={x0} x2={x0} y1={2} y2={h - 2} />
      <g className="gr-marcas">
        {items.map((it, i) => {
          const yc = 2 + fila * (i + 0.5)
          const xv = x(Math.max(0, it.valor))
          const etq = conEtq && conTexto ? cortar(it.etiqueta, izq - 14) : ''
          return (
            <g key={it.id} className={`gr-m${ix.c(it.id)}`} {...ix.p(it.id, it.larga, [[d.que, fmt(tipo, it.valor), pin.col(it.color)], ['Del total', fmtPct(E.porcentajeDelTotal(it.valor, total))], ['Registros', fmt('numero', it.n)]])}>
              <rect className="gr-hit" x="0" y={yc - fila / 2} width={w} height={fila} />
              <line className="gr-tallo gr-a-tallo" x1={x0} x2={xv} y1={yc} y2={yc} style={{ stroke: pin.col(it.color), '--o': ord(i, n) }} />
              <circle className="gr-a-pop" cx={xv} cy={yc} r={r} style={{ fill: pin.col(it.color), stroke: pin.sup, strokeWidth: 2, '--o': ord(i, n) + 5 }} />
              {etq && <text x={x0 - 8} y={yc} dy="0.35em" textAnchor="end">{etq}</text>}
              {der > 8 && conTexto && <text className="gr-valor gr-aparece" x={xv + r + 6} y={yc} dy="0.35em" style={{ '--o': ord(i, n) + 6 }}>{textos[i]}</text>}
            </g>
          )
        })}
      </g>
    </Svg>
  )
}

// ── 2. Puntos por categoría (strip plot) ──────────────────────────────────────────────────────────
function calcPuntos(regs, campos, o) {
  const c = campoDe(campos, o.agrupar); const cv = campoDe(campos, o.valor)
  if (!c || !cv) return FALTA
  const filas = E.agrupar(regs, c, { top: c.tipo === 'texto' ? 6 : undefined }).map((g, i) => {
    const xs = g.registros.map((r) => ({ id: String(r.id), v: E.num(r.valores?.[cv.id]) })).filter((p) => p.v !== null)
    return { id: g.clave, etiqueta: g.etiqueta, color: colorDe(g, i), xs, med: E.mediana(xs.map((p) => p.v)), n: xs.length }
  }).filter((f) => f.n)
  if (!filas.length) return SIN_DATOS
  const todos = filas.flatMap((f) => f.xs.map((p) => p.v))
  return { filas, tipo: cv.tipo, min: Math.min(0, ...todos), max: Math.max(...todos), pie: `Cada punto es un registro: ${cv.nombre.toLowerCase()} por ${c.nombre.toLowerCase()} · raya = mediana` }
}
function Puntos({ w, h, d, ix }) {
  const pin = usePintura()
  const { filas, tipo } = d
  const n = filas.length
  const conEtq = w >= 170
  const izq = conEtq ? Math.min(w * 0.3, Math.max(...filas.map((f) => anchoTexto(f.etiqueta))) + 12) : 6
  const conX = h >= 90
  const y0 = h - (conX ? 20 : 4)
  const fila = (y0 - 4) / n
  const tk = ticks(d.min, d.max, Math.max(2, Math.min(5, Math.floor((w - izq) / 80))))
  const X = escala(tk[0], tk[tk.length - 1], izq + 6, w - 10)
  const r = filas.reduce((s, f) => s + f.n, 0) > 150 ? 2.5 : 3.5
  // Etiquetas del eje X sin encimarse (de derecha a izquierda).
  const xs = []
  if (conX) { let limite = w; for (let i = tk.length - 1; i >= 0; i--) { const t = fEje(tipo)(tk[i]); const a = anchoTexto(t); const x0 = Math.max(1, Math.min(w - 1 - a, X(tk[i]) - a / 2)); if (x0 + a <= limite - 6) { xs.push({ t, x0, i }); limite = x0 } } }
  return (
    <Svg w={w} h={h} aria={d.pie}>
      <g className="gr-rejilla" aria-hidden="true">
        {tk.map((v, i) => <line key={i} x1={X(v)} x2={X(v)} y1={4} y2={y0} />)}
        {xs.map(({ t, x0, i }) => <text key={i} x={x0} y={y0 + 14}>{t}</text>)}
      </g>
      <g className="gr-marcas">
        {filas.map((f, i) => {
          const yc = 4 + fila * (i + 0.5)
          const amp = Math.max(0, fila * 0.3 - r)
          const etq = conEtq && fila >= 15 ? cortar(f.etiqueta, izq - 14) : ''
          return (
            <g key={f.id} className={`gr-m${ix.c(f.id)}`} {...ix.p(f.id, f.etiqueta, [['Registros', fmt('numero', f.n), pin.col(f.color)], ['Mediana', fmt(tipo, f.med)], ['Mínimo', fmt(tipo, E.minimo(f.xs.map((p) => p.v)))], ['Máximo', fmt(tipo, E.maximo(f.xs.map((p) => p.v)))]])}>
              <rect className="gr-hit" x="0" y={yc - fila / 2} width={w} height={fila} />
              {f.xs.map((p, j) => {
                const jit = ((((j * 2654435761) >>> 0) % 1000) / 1000 - 0.5) * 2 * amp // vaivén determinista
                return <circle key={p.id} className="gr-a-llueve" cx={X(p.v)} cy={yc + jit} r={r} style={{ fill: pin.col(f.color), fillOpacity: 0.55, '--o': tope(i * 3 + (j % 9), 40) }} />
              })}
              <line className="gr-mediana gr-aparece" x1={X(f.med)} x2={X(f.med)} y1={yc - Math.max(5, fila * 0.34)} y2={yc + Math.max(5, fila * 0.34)} style={{ '--o': 30 }} />
              {etq && <text x={izq - 8} y={yc} dy="0.35em" textAnchor="end">{etq}</text>}
            </g>
          )
        })}
      </g>
    </Svg>
  )
}

// ── 3. Bala contra meta (bullet) ──────────────────────────────────────────────────────────────────
function calcBala(regs, campos, o, hoy) {
  const m = calcMeses(regs, campos, { ...o, meses: 12 }, hoy)
  if (typeof m === 'string') return m
  const { tipo, tramo } = m
  const completos = m.items.slice(0, -1).map((i) => i.valor)
  const prom = E.promedio(completos) ?? 0
  const max = E.maximo(completos) ?? 0
  const fija = E.num(o.meta)
  const meta = fija !== null && fija > 0 ? fija : max > 0 ? max : null // sin meses completos con datos no se inventa una meta
  if (!meta && !tramo.actual && !tramo.anterior) return 'Sin meses completos con datos'
  const mejor = m.items.slice(0, -1).reduce((b, it) => (it.valor > (b?.valor ?? -Infinity) ? it : b), null)
  const diasMes = new Date(hoy.getFullYear(), hoy.getMonth() + 1, 0).getDate()
  return { tipo, que: m.que, prom, max, meta, origen: fija !== null && fija > 0 ? 'fijada a mano' : `mejor mes completo (${mejor?.larga || '—'})`,
    esperado: meta ? meta * (tramo.t.dias / diasMes) : null, dias: tramo.t.dias, diasMes,
    filas: [{ id: 'act', etiqueta: tramo.t.actual.etiqueta, valor: tramo.actual, actual: true }, { id: 'ant', etiqueta: tramo.t.anterior.etiqueta, valor: tramo.anterior }],
    pie: `${m.que} a hoy vs meta del mes · bandas: promedio y máximo mensual` }
}
function Bala({ w, h, d, ix }) {
  const pin = usePintura()
  const { filas, tipo } = d
  const conLey = h >= 120 && w >= 240
  const altoLey = conLey ? 20 : 0
  const conEtq = w >= 190
  const izq = conEtq ? Math.max(...filas.map((f) => anchoTexto(f.etiqueta))) + 12 : 4
  const textos = filas.map((f) => fmtCorto(tipo, f.valor))
  const der = w >= 200 ? Math.max(...textos.map(anchoVal)) + 10 : 4
  const x0 = izq; const x1 = Math.max(x0 + 20, w - der)
  const tope_ = Math.max(1e-9, d.meta || 0, d.max, ...filas.map((f) => f.valor)) * 1.04
  const X = escala(0, tope_, x0, x1)
  const fila = (h - altoLey - 4) / filas.length
  const bandaH = Math.max(8, Math.min(30, fila * 0.62))
  const barraH = Math.max(4, bandaH * 0.38)
  const banda1 = E.mezclar(pin.gris, pin.sup, pin.oscuro ? 0.3 : 0.22)
  const banda2 = E.mezclar(pin.gris, pin.sup, pin.oscuro ? 0.16 : 0.11)
  const metaTxt = d.meta ? `meta ${fmtCorto(tipo, d.meta)}` : 'sin meta: aún no hay meses completos'; const espTxt = `esperado a hoy ${fmtCorto(tipo, d.esperado)}`
  const cajaMeta = cajaTexto(14, h - 9, anchoTexto(metaTxt), 'start'); const xEsp = 14 + cajaMeta.w + 22
  const conEsp = conLey && d.meta && xEsp + anchoTexto(espTxt) <= w - 2
  return (
    <Svg w={w} h={h} aria={`${d.pie}: ${filas.map((f, i) => `${f.etiqueta} ${textos[i]}`).join(', ')}, ${d.meta ? `meta ${fmt(tipo, d.meta)}` : 'sin meta'}`}>
      <g className="gr-marcas">
        {filas.map((f, i) => {
          const yc = 2 + fila * (i + 0.5)
          const col = f.actual ? pin.acento : pin.gris
          return (
            <g key={f.id} className={`gr-m${ix.c(f.id)}`} {...ix.p(f.id, f.actual ? `${f.etiqueta} (mes en curso)` : `${f.etiqueta} (mismos días)`, [[d.que, fmt(tipo, f.valor), col], ['Meta del mes', fmt(tipo, d.meta)], ['Esperado a hoy', `${fmt(tipo, d.esperado)} (día ${d.dias} de ${d.diasMes})`], ['Avance', fmtPct(d.meta ? f.valor / d.meta : null)], ['Promedio mensual', fmt(tipo, d.prom)], ['Meta =', d.origen]])}>
              <rect className="gr-hit" x="0" y={yc - fila / 2} width={w} height={fila} />
              <g className="gr-aparece" style={{ '--o': i }}>
                <rect x={x0} y={yc - bandaH / 2} width={Math.max(0, X(d.max) - x0)} height={bandaH} rx="3" style={{ fill: banda2 }} />
                <rect x={x0} y={yc - bandaH / 2} width={Math.max(0, X(d.prom) - x0)} height={bandaH} rx="3" style={{ fill: banda1 }} />
              </g>
              <rect className="gr-a-barra" x={x0} y={yc - barraH / 2} width={Math.max(f.valor > 0 ? 1.5 : 0, X(f.valor) - x0)} height={barraH} rx={barraH / 2} style={{ fill: col, '--o': i + 2 }} />
              {d.meta && <line className="gr-meta-l gr-a-cae" x1={X(d.meta)} x2={X(d.meta)} y1={yc - bandaH / 2 - 3} y2={yc + bandaH / 2 + 3} style={{ '--o': 6 }} />}
              {f.actual && d.meta && <line className="gr-esperado gr-aparece" x1={X(d.esperado)} x2={X(d.esperado)} y1={yc - bandaH / 2 - 3} y2={yc + bandaH / 2 + 3} style={{ '--o': 8 }} />}
              {conEtq && fila >= 15 && <text x={x0 - 8} y={yc} dy="0.35em" textAnchor="end" className={f.actual ? 'gr-fuerte' : undefined}>{f.etiqueta}</text>}
              {der > 4 && fila >= 15 && <text className="gr-valor gr-aparece" x={w - 2} y={yc} dy="0.35em" textAnchor="end" style={{ '--o': 4 + i }}>{textos[i]}</text>}
            </g>
          )
        })}
      </g>
      {conLey && (
        <g className="gr-aparece gr-ley-bala" style={{ '--o': 10 }}>
          {d.meta && <line className="gr-meta-l" x1={6} x2={6} y1={h - 15} y2={h - 3} />}
          <text x={14} y={h - 9} dy="0.35em">{metaTxt}</text>
          {conEsp && <><line className="gr-esperado" x1={xEsp - 8} x2={xEsp - 8} y1={h - 15} y2={h - 3} /><text x={xEsp} y={h - 9} dy="0.35em">{espTxt}</text></>}
        </g>
      )}
    </Svg>
  )
}

// ── 4. Waffle 10 × 10 ─────────────────────────────────────────────────────────────────────────────
function Waffle({ w, h, d, ix, uid }) {
  const pin = usePintura()
  const variante = useOrden()(0, 3)
  const items = d.items.filter((i) => i.valor > 0)
  const cuentas = E.repartir100(items.map((i) => i.valor))
  const leyDe = (conRefs) => items.map((it, k) => ({ id: it.id, nombre: it.etiqueta, color: it.color, suave: true, ref: conRefs ? k + 1 : undefined, refId: conRefs ? `${uid}-lr${k}` : undefined, valor: `${cuentas[k]} %`, filas: [[d.que, fmt(d.tipo, it.valor), pin.col(it.color)], ['Del total', fmtPct(it.valor / d.total)]] }))
  const medir = (lista) => {
    const ley = planLeyenda(w, h, lista)
    const a = areaCon(ley, w, h)
    const lado = Math.max(20, Math.min(a.w, a.h) - 4)
    const gap = Math.max(1.5, lado / 10 * 0.12)
    return { ley, a, lado, gap, s: (lado - 9 * gap) / 10 }
  }
  // Las casillas no llevan texto; si son grandes, la primera de cada categoría lleva su número, repetido en la leyenda.
  const cabePlaca = (m) => m.ley.lado && m.s - 2 >= Math.max(ALTO_PLACA, anchoPlaca(items.length))
  let conRefs = false; let m = medir(leyDe(false))
  if (cabePlaca(m)) { const m2 = medir(leyDe(true)); if (cabePlaca(m2)) { m = m2; conRefs = true } }
  const { ley, a, lado, gap, s } = m
  const leyItems = leyDe(conRefs)
  const x0 = (a.w - lado) / 2; const y0 = (a.h - lado) / 2
  const celdas = []
  items.forEach((it, k) => { for (let j = 0; j < cuentas[k]; j++) celdas.push(it) })
  const primera = new Map(); celdas.forEach((it, i) => { if (!primera.has(it.id)) primera.set(it.id, i) })
  const orden = (fila, col) => (variante === 1 ? fila * 10 + (fila % 2 ? 9 - col : col) : variante === 2 ? (fila + col) * 4 : fila * 10 + col)
  return (
    <Svg w={w} h={h} aria={`${d.pie}: ${items.map((it, k) => `${it.etiqueta} ${cuentas[k]} %`).join(', ')}`}>
      <g className="gr-marcas">
        {Array.from({ length: 100 }, (_, i) => {
          const fila = Math.floor(i / 10); const col = i % 10
          const it = celdas[i]
          const x = x0 + col * (s + gap); const y = y0 + fila * (s + gap)
          const k = it ? items.indexOf(it) : -1
          return (
            <g key={i} className={`gr-a-casilla${it ? ix.c(it.id) : ''}`} style={{ '--o': orden(fila, col) }}
              {...(it ? ix.p(it.id, it.larga, [[d.que, fmt(d.tipo, it.valor), pin.col(it.color)], ['Del total', fmtPct(it.valor / d.total)], ['Casillas', `${cuentas[k]} de 100`]]) : {})}>
              <rect className="gr-celda" x={x} y={y} width={s} height={s} rx={Math.min(3, s / 4)} style={{ fill: it ? pin.relleno(it.color) : undefined }} />
              {conRefs && it && primera.get(it.id) === i && <Placa n={k + 1} x={x + s / 2} y={y + s / 2} fondo={pin.relleno(it.color)} id={`${uid}-wp${k}`} pin={pin} />}
            </g>
          )
        })}
      </g>
      <Leyenda plan={ley} w={w} h={h} ix={ix} items={leyItems} />
    </Svg>
  )
}

// ── 5. Rosa polar ─────────────────────────────────────────────────────────────────────────────────
function Rosa({ w, h, d, ix, uid }) {
  const pin = usePintura(); const ord = useOrden()
  const { items, tipo, total } = d
  const n = items.length
  const max = Math.max(1e-9, ...items.map((i) => i.valor))
  const paso = (2 * Math.PI) / n
  // Primero se intenta con los nombres alrededor (radio máximo que los deja adentro); si no caben, leyenda.
  const lim = { x: 1, y: 1, w: w - 2, h: h - 2 }
  const textos = items.map((i) => cortar(i.etiqueta, Math.min(100, w * 0.28)))
  const cajas = (R, cx, cy) => items.map((_, i) => {
    const am = paso * (i + 0.5); const s = Math.sin(am); const c = -Math.cos(am)
    const [x, y] = punto(cx, cy, R + 8, am)
    const ancla = s > 0.3 ? 'start' : s < -0.3 ? 'end' : 'middle'
    const yy = y + (c < -0.5 ? -4 : c > 0.5 ? 4 : 0)
    return { x, y: yy, ancla, caja: cajaTexto(x, yy, anchoTexto(textos[i]), ancla) }
  })
  let modo = null; let R = 0; let cx = w / 2; let cy = h / 2; let ley = { lado: null }
  const Rmax = Math.min(w, h) / 2 - 6
  if (w >= 200 && h >= 130) {
    let lo = Rmax * 0.45; let hi = Rmax
    const ok = (r) => cajas(r, cx, cy).every((e, i) => !textos[i] || cabeEn(e.caja, lim))
    if (ok(lo)) { for (let k = 0; k < 16; k++) { const m = (lo + hi) / 2; if (ok(m)) lo = m; else hi = m } R = lo; modo = 'nombres' }
  }
  const leyItems = items.map((it) => ({ id: it.id, nombre: it.etiqueta, color: it.color, suave: true, valor: fmtCorto(tipo, it.valor), filas: [[d.que, fmt(tipo, it.valor), pin.col(it.color)]] }))
  if (!modo) { ley = planLeyenda(w, h, leyItems); const a = areaCon(ley, w, h); cx = a.w / 2; cy = a.h / 2; R = Math.max(12, Math.min(a.w, a.h) / 2 - 4) }
  const etq = modo ? cajas(R, cx, cy) : []
  const okEtq = modo ? sinChoques(etq.map((e, i) => ({ id: i, caja: e.caja, prio: items[i].valor })), lim) : new Set()
  const origen = { transformOrigin: `${cx}px ${cy}px` }
  const rDe = (v) => R * Math.sqrt(Math.max(0, v) / max) // área ∝ valor
  return (
    <Svg w={w} h={h} aria={`${d.pie}: ${items.map((i) => `${i.etiqueta} ${fmt(tipo, i.valor)}`).join(', ')}`}>
      <g className="gr-rejilla" aria-hidden="true">
        {[0.25, 0.5, 0.75, 1].map((k) => <circle key={k} cx={cx} cy={cy} r={rDe(max * k)} />)}
      </g>
      <g className="gr-marcas">
        {items.map((it, i) => {
          const fondo = pin.relleno(it.color)
          const r = rDe(it.valor)
          return (
            <g key={it.id} className={`gr-m${ix.c(it.id)}`} {...ix.p(it.id, it.larga, [[d.que, fmt(tipo, it.valor), pin.col(it.color)], ['Del total', fmtPct(E.porcentajeDelTotal(it.valor, total))]])}>
              <path className="gr-hit" d={sector(cx, cy, 0, R, paso * i, paso * (i + 1))} />
              {r > 0.5 && <path id={`${uid}-r${i}`} className="gr-forma gr-a-petalo" d={sector(cx, cy, 0, r, paso * i, paso * (i + 1))} style={{ fill: fondo, stroke: pin.sup, strokeWidth: SEPARADOR, strokeLinejoin: 'round', ...origen, '--o': ord(i, n) }} />}
              {okEtq.has(i) && <text className="gr-aparece" x={etq[i].x} y={etq[i].y} dy="0.35em" textAnchor={etq[i].ancla} style={{ '--o': n + 2 }}>{textos[i]}</text>}
            </g>
          )
        })}
      </g>
      {!modo && <Leyenda plan={ley} w={w} h={h} ix={ix} items={leyItems} />}
    </Svg>
  )
}

// ── 6. Sol (sunburst de 2 niveles: estado → texto) ────────────────────────────────────────────────
function calcSol(regs, campos, o) {
  const ce = campoDe(campos, o.estado); const ct = campoDe(campos, o.texto)
  if (!ce || !ct) return FALTA
  const m = medirDe(o); const f = fnDe(o)
  const grupos = E.agrupar(regs, ce).map((g, i) => ({
    id: g.clave, etiqueta: g.etiqueta, color: colorDe(g, i), valor: E.resumir(g.registros, m, f) ?? 0, n: g.registros.length,
    hijos: E.agrupar(g.registros, ct, { top: 4 }).map((h) => ({ id: `${g.clave}›${h.clave}`, etiqueta: h.etiqueta, valor: E.resumir(h.registros, m, f) ?? 0, n: h.registros.length })).filter((h) => h.valor > 0),
  })).filter((g) => g.valor > 0)
  const total = sumaDe(grupos.map((g) => g.valor))
  if (!(total > 0)) return SIN_DATOS
  return { grupos, total, tipo: tipoDe(o, campos), que: queMide(o, campos), pie: `${queMide(o, campos)}: ${ce.nombre.toLowerCase()} (centro) → ${ct.nombre.toLowerCase()} (afuera, 3 principales + otros)` }
}
/** Texto de un tramo de anillo (horizontal o radial) con nombre en 11 px y valor en 12 px. */
function TextoSector({ e, forma, color, o }) {
  return (
    <text className="gr-dentro gr-aparece" data-forma={forma} x={e.x} y={e.y} dy="0.35em" textAnchor="middle" transform={e.giro ? `rotate(${e.giro.toFixed(2)} ${e.x.toFixed(2)} ${e.y.toFixed(2)})` : undefined} style={{ fill: color, '--o': o }}>
      {e.nombre && <tspan>{e.nombre}{e.valor ? ' · ' : ''}</tspan>}{e.valor && <tspan className="gr-valor" style={{ fill: color }}>{e.valor}</tspan>}
    </text>
  )
}
function Sol({ w, h, d, ix, uid }) {
  const pin = usePintura(); const ord = useOrden()
  const { grupos, total, tipo } = d
  const leyItems = grupos.map((g) => ({ id: g.id, nombre: g.etiqueta, color: g.color, suave: true, valor: fmtPct(g.valor / total), filas: [[d.que, fmt(tipo, g.valor), pin.col(g.color)]] }))
  const ley = planLeyenda(w, h, leyItems)
  const a = areaCon(ley, w, h)
  const R = Math.max(16, Math.min(a.w, a.h) / 2 - 4)
  const cx = a.w / 2; const cy = a.h / 2
  const r0 = R * 0.3; const r1 = R * 0.64
  const origen = { transformOrigin: `${cx}px ${cy}px` }
  let acum = 0
  const partes = grupos.map((g, i) => { const f = g.valor / total; const a0 = acum * 2 * Math.PI; acum += f; return { it: g, i, f, a0, a1: acum * 2 * Math.PI } })
  // Anillo interno: el % (horizontal o radial). Anillo externo: nombre · %, nombre corto (≥ 6 letras) · % o solo el %.
  const etqIn = partes.map((p) => rotularSector({ cx, cy, r0, r1, a0: p.a0, a1: p.a1, opciones: [{ valor: fmtPct(p.f) }] }))
  const largoExt = R - (r1 + 1) - 6
  const etqExt = partes.map((p) => {
    let ac = p.a0
    return p.it.hijos.map((x) => {
      const b0 = ac; const b1 = ac + (x.valor / p.it.valor) * (p.a1 - p.a0); ac = b1
      const pct = fmtPct(x.valor / total)
      const corto = partirNombre(x.etiqueta, largoExt - anchoTexto(' · ') - anchoVal(pct), 1)
      return rotularSector({ cx, cy, r0: r1 + 1, r1: R, a0: b0, a1: b1, opciones: [{ nombre: x.etiqueta, valor: pct }, corto && !corto.completo ? { nombre: corto.lineas[0], valor: pct } : null, { valor: pct }] })
    })
  })
  const TONOS = [0.82, 0.62, 0.46, 0.34]
  const totalTxt = fmtCorto(tipo, total)
  let tam = Math.round(Math.max(12, Math.min(22, r0 * 0.5)))
  while (tam > 12 && anchoTexto(totalTxt, tam, 600) > r0 * 1.6) tam--
  const conCentro = r0 >= 18 && anchoTexto(totalTxt, tam, 600) <= r0 * 1.7
  return (
    <Svg w={w} h={h} aria={`${d.pie}: ${grupos.map((g) => `${g.etiqueta} ${fmt(tipo, g.valor)} (${g.hijos.map((x) => `${x.etiqueta} ${fmt(tipo, x.valor)}`).join(', ')})`).join('; ')}`}>
      <g className="gr-marcas gr-a-giro" style={origen}>
        {partes.map(({ it: g, i, f, a0, a1 }) => {
          const fondo = pin.relleno(g.color)
          let ac2 = a0
          return (
            <g key={g.id}>
              <path id={`${uid}-s${i}`} className={`gr-forma gr-a-gajo gr-m${ix.c(g.id)}`} d={sector(cx, cy, r0, r1, a0, a1)} style={{ fill: fondo, stroke: pin.sup, strokeWidth: grupos.length > 1 ? SEPARADOR : 0, ...origen, '--o': ord(i, grupos.length) }}
                {...ix.p(g.id, g.etiqueta, [[d.que, fmt(tipo, g.valor), pin.col(g.color)], ['Del total', fmtPct(f)], ...g.hijos.map((x) => [x.etiqueta, fmt(tipo, x.valor)])])} />
              {g.hijos.map((x, k) => {
                const b0 = ac2; const b1 = ac2 + (x.valor / g.valor) * (a1 - a0); ac2 = b1
                const fh = pin.relleno(g.color, TONOS[k % TONOS.length])
                return <path key={x.id} id={`${uid}-sx${i}-${k}`} className={`gr-a-gajo gr-m${ix.c(x.id, g.id)}`} d={sector(cx, cy, r1 + 1, R, b0, b1)} style={{ fill: fh, stroke: pin.sup, strokeWidth: SEPARADOR, ...origen, '--o': ord(i, grupos.length) + 4 + k }}
                  {...ix.p(x.id, `${g.etiqueta} › ${x.etiqueta}`, [[d.que, fmt(tipo, x.valor), fh], [`De ${g.etiqueta}`, fmtPct(x.valor / g.valor)], ['Del total', fmtPct(x.valor / total)], ['Registros', fmt('numero', x.n)]])} />
              })}
            </g>
          )
        })}
      </g>
      <g pointerEvents="none">
        {etqIn.map((e, i) => e && <TextoSector key={`i${i}`} e={e} forma={`${uid}-s${i}`} color={pin.texto(pin.relleno(partes[i].it.color))} o={10 + i} />)}
        {etqExt.map((fila, i) => fila.map((e, k) => e && <TextoSector key={`e${i}-${k}`} e={e} forma={`${uid}-sx${i}-${k}`} color={pin.texto(pin.relleno(partes[i].it.color, TONOS[k % TONOS.length]))} o={14 + i} />))}
        {conCentro && <text x={cx} y={cy} dy="0.35em" textAnchor="middle" className="gr-grande" style={{ fontSize: tam }}><Cuenta v={total} f={(x) => fmtCorto(tipo, x)} /></text>}
      </g>
      <Leyenda plan={ley} w={w} h={h} ix={ix} items={leyItems} />
    </Svg>
  )
}

// ── 7. Mapa de calor día de la semana × hora ──────────────────────────────────────────────────────
function calcCalorHora(regs, campos, o) {
  const cf = campoDe(campos, o.fecha); const chh = campoDe(campos, o.hora)
  if (!cf || !chh) return FALTA
  const mapa = E.agruparPorDiaHora(regs, cf.id, chh.id)
  if (!mapa.size) return 'Sin registros con fecha y hora'
  const hs = [...mapa.keys()].map((k) => Number(k.split('-')[1]))
  const h0 = Math.min(...hs); const h1 = Math.max(...hs)
  const horas = Array.from({ length: h1 - h0 + 1 }, (_, i) => h0 + i)
  const celdas = []
  for (let dd = 0; dd < 7; dd++) for (const hh of horas) { const rs = mapa.get(`${dd}-${hh}`) || []; celdas.push({ id: `${dd}-${hh}`, d: dd, h: hh, v: E.resumir(rs, medirDe(o), fnDe(o)) ?? 0, n: rs.length }) }
  const n = sumaDe([...mapa.values()].map((x) => x.length))
  return { horas, celdas, max: Math.max(1e-9, ...celdas.map((c) => c.v)), tipo: tipoDe(o, campos), que: queMide(o, campos), pie: `${queMide(o, campos)} por día de la semana y hora · ${n} registros con ${cf.nombre.toLowerCase()} y ${chh.nombre.toLowerCase()}` }
}
function CalorHora({ w, h, d, ix, uid }) {
  const pin = usePintura()
  const variante = useOrden()(0, 3)
  const { horas, celdas } = d
  const conDias = w >= 150
  const izq = conDias ? 30 : 2
  const conHoras = h >= 80
  const arriba = conHoras ? 18 : 2
  const gap = 2
  const cols = horas.length
  const s = Math.max(3, Math.min((w - izq - 2) / cols - gap, (h - arriba - 2) / 7 - gap, 40))
  const x0 = izq + Math.max(0, (w - izq - cols * (s + gap)) / 2)
  const y0 = arriba
  const COL = nivelesCalor(pin)
  const nivel = (v) => (v <= 0 ? 0 : Math.max(1, Math.ceil((v / d.max) * 4)))
  // Horas arriba: de izquierda a derecha, sin encimarse.
  const hOk = []
  if (conHoras) { let limite = -Infinity; horas.forEach((hh, i) => { const t = `${hh} h`; const a = anchoTexto(t); const xc = x0 + i * (s + gap) + s / 2; const xa = Math.max(1, Math.min(w - 1 - a, xc - a / 2)); if (xa >= limite + 6) { hOk.push({ t, xa, i }); limite = xa + a } }) }
  const orden = (dd, i) => (variante === 1 ? i * 2 + dd : variante === 2 ? (6 - dd) + i : dd + i)
  return (
    <Svg w={w} h={h} aria={d.pie}>
      {hOk.map(({ t, xa, i }) => <text key={i} x={xa} y={9} dy="0.35em" className="gr-sutil">{t}</text>)}
      {conDias && s + gap >= 14 && DIAS.map((t, dd) => <text key={t} x={x0 - 6} y={y0 + dd * (s + gap) + s / 2} dy="0.35em" textAnchor="end" className="gr-sutil">{t}</text>)}
      <g className="gr-marcas">
        {celdas.map((c) => {
          const i = horas.indexOf(c.h)
          const lv = nivel(c.v)
          const x = x0 + i * (s + gap); const y = y0 + c.d * (s + gap)
          const t = fmtCorto(d.tipo, c.v)
          const id = `${uid}-h${c.id}`
          const conTxt = lv && s >= 20 && anchoTexto(t, 11, 600) + 6 <= s
          return (
            <g key={c.id} className={`gr-a-casilla${ix.c(c.id)}`} style={{ '--o': orden(c.d, i) }} {...ix.p(c.id, `${DIAS[c.d]} · ${c.h}:00–${c.h}:59`, [[d.que, fmt(d.tipo, c.v), lv ? COL[lv] : undefined], ['Registros', fmt('numero', c.n)]])}>
              <rect id={id} className="gr-celda gr-forma" x={x} y={y} width={s} height={s} rx={Math.min(4, s / 5)} style={{ fill: lv ? COL[lv] : undefined }} />
              {conTxt && <text className="gr-fuerte gr-dentro" data-forma={id} x={x + s / 2} y={y + s / 2} dy="0.35em" textAnchor="middle" style={{ fill: pin.texto(COL[lv]) }} pointerEvents="none">{t}</text>}
            </g>
          )
        })}
      </g>
    </Svg>
  )
}

// ── 8. Escalones (step) ───────────────────────────────────────────────────────────────────────────
function Escalones({ w, h, d, ix, uid }) {
  const pin = usePintura(); const ord = useOrden()
  const { items, tipo } = d
  const n = items.length
  const vals = items.map((i) => i.valor)
  const p = plano(w, h, { max: Math.max(0, ...vals), f: fEje(tipo), entero: d.entero, arriba: 12 })
  const banda = p.ancho / n
  const xa = (i) => p.x0 + banda * i
  const tramo = (desde, hasta) => {
    let s = ''
    for (let i = desde; i < hasta; i++) s += `${i === desde ? 'M' : 'L'}${xa(i).toFixed(1)},${p.y(vals[i]).toFixed(1)} L${xa(i + 1).toFixed(1)},${p.y(vals[i]).toFixed(1)} `
    return s.trim()
  }
  const parcial = items[n - 1]?.parcial && n > 1
  const linea = tramo(0, parcial ? n - 1 : n)
  const resto = parcial ? `M${xa(n - 1).toFixed(1)},${p.y(vals[n - 2]).toFixed(1)} L${xa(n - 1).toFixed(1)},${p.y(vals[n - 1]).toFixed(1)} L${xa(n).toFixed(1)},${p.y(vals[n - 1]).toFixed(1)}` : ''
  const area = `${tramo(0, n)} L${xa(n).toFixed(1)},${p.y0} L${xa(0).toFixed(1)},${p.y0} Z`
  const gid = `gr-esc-${uid}`; const cid = `gr-escb-${uid}`
  const ac = pin.acento
  return (
    <Svg w={w} h={h} aria={`${d.pie}: ${items.map((i) => `${i.larga} ${fmt(tipo, i.valor)}`).join(', ')}`}>
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1"><stop offset="0" style={{ stopColor: ac, stopOpacity: pin.oscuro ? 0.26 : 0.2 }} /><stop offset="1" style={{ stopColor: ac, stopOpacity: 0.02 }} /></linearGradient>
        <clipPath id={cid}><rect className="gr-a-barrido" x={p.x0 - 2} y={0} width={p.ancho + 4} height={h} /></clipPath>
      </defs>
      <Rejilla p={p} />
      <path className="gr-area" clipPath={`url(#${cid})`} d={area} style={{ fill: `url(#${gid})` }} />
      <path className="gr-traza gr-linea gr-escalon" d={linea} pathLength="1" style={{ stroke: ac }} />
      {resto && <path className="gr-linea gr-parcial-l gr-aparece" d={resto} style={{ stroke: ac, '--o': 14 }} />}
      <g className="gr-marcas">
        {items.map((it, i) => (
          <g key={it.id} className={`gr-m${ix.c(it.id)}`} {...ix.p(it.id, it.larga, [[d.que, fmt(tipo, it.valor), ac], ...(it.parcial ? [['Mes en curso', 'incompleto'], [d.tramo.texto, d.tramo.var === null ? '—' : fmtPct(d.tramo.var, true)]] : i > 0 ? [['Cambio', `${fmtPct(E.variacion(it.valor, vals[i - 1]), true)}`]] : [])])}>
            <rect className="gr-hit" x={xa(i)} y={p.y1} width={banda} height={p.alto} />
            {banda >= 14 && <line className="gr-tope gr-a-pop" x1={xa(i) + banda * 0.5 - 3} x2={xa(i) + banda * 0.5 + 3} y1={p.y(it.valor)} y2={p.y(it.valor)} style={{ stroke: ac, '--o': ord(i, n) + 4 }} />}
          </g>
        ))}
      </g>
      <EjeX p={p} items={items.map((it, i) => ({ x: xa(i) + banda / 2, t: it.etiqueta }))} />
    </Svg>
  )
}

// ── 9. Combo: columnas por mes + línea acumulada ──────────────────────────────────────────────────
function Combo({ w, h, d, ix }) {
  const pin = usePintura(); const ord = useOrden()
  const { items, tipo } = d
  const n = items.length
  const vals = items.map((i) => i.valor)
  const acum = E.acumulado(vals)
  const tkD = ticks(0, Math.max(...acum), h < 130 ? 2 : 4, d.entero)
  const textosD = tkD.map(fEje(tipo))
  const der = w >= 220 && h >= 90 ? Math.max(...textosD.map((t) => anchoTexto(t))) + 10 : 6
  const conLey = h >= 150 && w >= 220
  const p = plano(w, h - (conLey ? 20 : 0), { max: Math.max(0, ...vals), f: fEje(tipo), entero: d.entero, arriba: 12, der })
  const YD = escala(tkD[0], tkD[tkD.length - 1], p.y0, p.y1)
  const banda = p.ancho / n
  const bw = Math.max(2, Math.min(40, banda * 0.6))
  const X = (i) => p.x0 + banda * (i + 0.5)
  const linea = acum.map((v, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)},${YD(v).toFixed(1)}`).join(' ')
  const cLinea = COLORES[2]
  const etqD = der > 6 ? tkD.map((v, i) => ({ id: i, t: textosD[i], y: YD(v), caja: cajaTexto(w - 2, YD(v), anchoTexto(textosD[i]), 'end'), prio: i === tkD.length - 1 ? 9 : i })) : []
  const okD = sinChoques(etqD, { x: 0, y: 0, w, h }, p.conY ? p.tk.map((v, i) => cajaTexto(p.x0 - 6, p.y(v), anchoTexto(p.textos[i]), 'end')) : [])
  const yl = h - 9
  return (
    <Svg w={w} h={h} aria={`${d.pie}: ${items.map((it, i) => `${it.larga} ${fmt(tipo, it.valor)} (acumulado ${fmt(tipo, acum[i])})`).join(', ')}`}>
      <Rejilla p={p} />
      <g className="gr-rejilla" aria-hidden="true">{etqD.filter((e) => okD.has(e.id)).map((e) => <text key={e.id} x={w - 2} y={e.y} dy="0.35em" textAnchor="end" style={{ fill: pin.col(cLinea) }}>{e.t}</text>)}</g>
      <g className="gr-marcas">
        {items.map((it, i) => {
          const ya = p.y(Math.max(0, it.valor))
          return (
            <g key={it.id} className={`gr-m${ix.c(it.id)}`} {...ix.p(it.id, it.larga, [[d.que, fmt(tipo, it.valor), pin.acento], ['Acumulado', fmt(tipo, acum[i]), cLinea], ...(it.parcial ? [['Mes en curso', 'incompleto']] : [])])}>
              <rect className="gr-hit" x={p.x0 + banda * i} y={p.y1} width={banda} height={p.alto} />
              <rect className={`gr-a-col${it.parcial ? ' gr-parcial' : ''}`} x={X(i) - bw / 2} y={ya} width={bw} height={Math.max(it.valor ? 1 : 0, p.y0 - ya)} rx={Math.min(3, bw / 4)} style={{ fill: pin.relleno(ACENTO, it.parcial ? 0.6 : 1), stroke: pin.acento, '--o': ord(i, n) }} />
            </g>
          )
        })}
      </g>
      <path className="gr-traza gr-linea" d={linea} pathLength="1" style={{ stroke: cLinea, '--i': 8 }} />
      {banda >= 10 && acum.map((v, i) => <circle key={i} className="gr-a-pop" cx={X(i)} cy={YD(v)} r="2.6" style={{ fill: pin.sup, stroke: cLinea, strokeWidth: 1.8, '--o': 10 + ord(i, n) }} pointerEvents="none" />)}
      <EjeX p={p} items={items.map((it, i) => ({ x: X(i), t: it.etiqueta }))} />
      {conLey && (
        <g className="gr-aparece" style={{ '--o': 12 }}>
          <rect x={2} y={yl - 5} width="10" height="10" rx="3" style={{ fill: pin.relleno(ACENTO), stroke: pin.acento }} />
          <text x={17} y={yl} dy="0.35em">Por mes</text>
          <line x1={78} x2={92} y1={yl} y2={yl} className="gr-linea" style={{ stroke: cLinea }} />
          <text x={97} y={yl} dy="0.35em">Acumulado (eje derecho)</text>
        </g>
      )}
    </Svg>
  )
}

// ── 10. Pareto ────────────────────────────────────────────────────────────────────────────────────
function calcPareto(regs, campos, o) {
  const d = conTotal(calcCategorias(regs, campos, o, 10))
  if (typeof d === 'string') return d
  const fijos = d.items.filter((i) => i.clave === E.SIN_DATO || i.clave === 'Otros')
  const items = [...d.items.filter((i) => !fijos.includes(i)).sort((a, b) => b.valor - a.valor), ...fijos]
  const cum = E.acumulado(items.map((i) => i.valor)).map((v) => v / d.total)
  const corte = cum.findIndex((c) => c >= 0.8)
  return { ...d, items, cum, corte, pie: `${d.que} por ${d.campo.nombre.toLowerCase()}, de mayor a menor · línea = % acumulado · ${corte + 1} de ${items.length} suman el 80 %` }
}
function Pareto({ w, h, d, ix }) {
  const pin = usePintura(); const ord = useOrden()
  const { items, tipo, cum, corte } = d
  const n = items.length
  const der = w >= 220 && h >= 90 ? anchoTexto('100 %') + 10 : 6
  const p = plano(w, h, { max: Math.max(0, ...items.map((i) => i.valor)), f: fEje(tipo), entero: d.entero, arriba: 12, der })
  const YP = escala(0, 1, p.y0, p.y1)
  const banda = p.ancho / n
  const bw = Math.max(2, Math.min(44, banda * 0.66))
  const X = (i) => p.x0 + banda * (i + 0.5)
  const linea = cum.map((c, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)},${YP(c).toFixed(1)}`).join(' ')
  const cL = COLORES[3]
  const pctEje = der > 6 ? [0, 0.5, 1].map((v) => ({ id: v, t: fmtPct(v), y: YP(v), caja: cajaTexto(w - 2, YP(v), anchoTexto(fmtPct(v)), 'end'), prio: v })) : []
  const okP = sinChoques(pctEje, { x: 0, y: 0, w, h })
  const t80 = '80 %'
  return (
    <Svg w={w} h={h} aria={`${d.pie}: ${items.map((it, i) => `${it.etiqueta} ${fmt(tipo, it.valor)} (acumulado ${fmtPct(cum[i])})`).join(', ')}`}>
      <Rejilla p={p} />
      <g className="gr-rejilla" aria-hidden="true">
        {pctEje.filter((e) => okP.has(e.id)).map((e) => <text key={e.id} x={w - 2} y={e.y} dy="0.35em" textAnchor="end">{e.t}</text>)}
        <line className="gr-ochenta" x1={p.x0} x2={p.x1} y1={YP(0.8)} y2={YP(0.8)} />
      </g>
      <g className="gr-marcas">
        {items.map((it, i) => {
          const ya = p.y(Math.max(0, it.valor))
          const vital = i <= corte
          return (
            <g key={it.id} className={`gr-m${ix.c(it.id)}`} {...ix.p(it.id, it.larga, [[d.que, fmt(tipo, it.valor), pin.col(it.color)], ['Del total', fmtPct(it.valor / d.total)], ['Acumulado', fmtPct(cum[i]), cL], ...(vital ? [['', 'dentro del 80 %']] : [])])}>
              <rect className="gr-hit" x={p.x0 + banda * i} y={p.y1} width={banda} height={p.alto} />
              <rect className="gr-a-col" x={X(i) - bw / 2} y={ya} width={bw} height={Math.max(it.valor ? 1 : 0, p.y0 - ya)} rx={Math.min(3, bw / 4)} style={{ fill: pin.relleno(ACENTO, vital ? 1 : 0.5), stroke: vital ? pin.acento : 'none', '--o': ord(i, n) }} />
            </g>
          )
        })}
      </g>
      <path className="gr-traza gr-linea" d={linea} pathLength="1" style={{ stroke: cL, '--i': 8 }} />
      {banda >= 10 && cum.map((c, i) => <circle key={i} className="gr-a-pop" cx={X(i)} cy={YP(c)} r="2.6" style={{ fill: pin.sup, stroke: cL, strokeWidth: 1.8, '--o': 10 + i }} pointerEvents="none" />)}
      {der > 6 && p.alto >= 60 && !okP.has(0.5) && <text className="gr-sutil" x={w - 2} y={YP(0.8)} dy="0.35em" textAnchor="end">{t80}</text>}
      <EjeX p={p} items={items.map((it, i) => ({ x: X(i), t: it.etiqueta }))} />
    </Svg>
  )
}

// ── 11. Línea de tiempo (Gantt) ───────────────────────────────────────────────────────────────────
function calcGantt(regs, campos, o, hoy) {
  const ci = campoDe(campos, o.fecha); const cfin = campoDe(campos, o.fecha2)
  if (!ci || !cfin) return FALTA
  const ct = campoDe(campos, o.texto); const ce = campoDe(campos, o.estado)
  const hoy0 = new Date(hoy.getFullYear(), hoy.getMonth(), hoy.getDate()).getTime()
  let invertidos = 0; let sinFecha = 0
  const barras = []
  for (const r of regs) {
    const a = r.valores?.[ci.id]; const b = r.valores?.[cfin.id]
    if (!E.esFechaIso(a) || !E.esFechaIso(b)) { sinFecha++; continue }
    const ini = E.deIso(a).getTime(); const fin = E.deIso(b).getTime()
    if (fin < ini) { invertidos++; continue }
    const idx = ce ? ce.opciones.indexOf(r.valores?.[ce.id]) : -1
    barras.push({ id: String(r.id), etiqueta: ct ? String(r.valores?.[ct.id] ?? '—') : `Registro ${r.id}`, ini, fin, estado: ce ? (idx >= 0 ? ce.opciones[idx] : E.SIN_DATO) : null, color: idx >= 0 ? COLORES[idx % COLORES.length] : ACENTO })
  }
  if (!barras.length) return invertidos ? `Sin fechas válidas: ${invertidos} con ${cfin.nombre.toLowerCase()} antes de ${ci.nombre.toLowerCase()}` : SIN_DATOS
  // Primero las que están en curso, luego las próximas (por inicio) y al final las terminadas (la más reciente primero).
  const rango = (x) => (x.ini <= hoy0 && x.fin >= hoy0 ? 0 : x.ini > hoy0 ? 1 : 2)
  barras.sort((x, y) => rango(x) - rango(y) || (rango(x) === 2 ? y.fin - x.fin : x.ini - y.ini))
  const avisos = [invertidos ? `${invertidos} con ${cfin.nombre.toLowerCase()} antes de ${ci.nombre.toLowerCase()} no se muestran` : '', sinFecha ? `${sinFecha} sin fechas` : ''].filter(Boolean)
  return { barras, hoy: hoy0, ni: ci.nombre, nf: cfin.nombre, ne: ce?.nombre, total: barras.length,
    pie: `De ${ci.nombre.toLowerCase()} a ${cfin.nombre.toLowerCase()} · en curso primero${avisos.length ? ` · ${avisos.join(' · ')}` : ''}` }
}
function Gantt({ w, h, d, ix }) {
  const pin = usePintura()
  const conX = h >= 80
  const abajo = conX ? 20 : 2
  const filaMin = 17
  const caben = Math.max(1, Math.floor((h - abajo - 4) / filaMin))
  const ver = d.barras.slice(0, caben).sort((a, b) => a.ini - b.ini)
  const n = ver.length
  const fila = Math.min(30, (h - abajo - 4) / n)
  const conEtq = w >= 240
  const izq = conEtq ? Math.min(w * 0.32, Math.max(...ver.map((b) => anchoTexto(b.etiqueta))) + 12) : 4
  const t0 = Math.min(...ver.map((b) => b.ini)); const t1 = Math.max(...ver.map((b) => b.fin), t0 + 864e5)
  const margen = (t1 - t0) * 0.03
  const X = escala(t0 - margen, t1 + margen, izq + 2, w - 6)
  const bh = Math.max(4, Math.min(16, fila * 0.6))
  const y0 = h - abajo
  // Fechas del eje: 2–5 marcas parejas que no se enciman.
  const nT = Math.max(2, Math.min(5, Math.floor((w - izq) / 80)))
  const marcas = Array.from({ length: nT }, (_, i) => t0 + ((t1 - t0) * i) / (nT - 1))
  const fx = []
  if (conX) { let limite = -Infinity; for (const t of marcas) { const s = fechaCorta(new Date(t)); const a = anchoTexto(s); const x0 = Math.max(izq, Math.min(w - 1 - a, X(t) - a / 2)); if (x0 >= limite + 8) { fx.push({ s, x0, t }); limite = x0 + a } } }
  const conHoy = d.hoy >= t0 - margen && d.hoy <= t1 + margen
  return (
    <Svg w={w} h={h} aria={`${d.pie}: ${ver.map((b) => `${b.etiqueta} ${fechaCorta(new Date(b.ini))}–${fechaCorta(new Date(b.fin))}`).join(', ')}`}>
      <g className="gr-rejilla" aria-hidden="true">
        {marcas.map((t, i) => <line key={i} x1={X(t)} x2={X(t)} y1={2} y2={y0} />)}
        {fx.map(({ s, x0, t }) => <text key={t} x={x0} y={y0 + 14}>{s}</text>)}
      </g>
      {conHoy && <line className="gr-hoy-l gr-aparece" x1={X(d.hoy)} x2={X(d.hoy)} y1={2} y2={y0} style={{ '--o': n + 2 }} />}
      <g className="gr-marcas">
        {ver.map((b, i) => {
          const yc = 2 + fila * (i + 0.5)
          const xa = X(b.ini); const xb = Math.max(xa + 3, X(b.fin))
          const etq = conEtq && fila >= 15 ? cortar(b.etiqueta, izq - 14) : ''
          const dias = Math.round((b.fin - b.ini) / 864e5) + 1
          return (
            <g key={b.id} className={`gr-m${ix.c(b.id)}`} {...ix.p(b.id, b.etiqueta, [[d.ni, fechaLarga(new Date(b.ini)), pin.col(b.color)], [d.nf, fechaLarga(new Date(b.fin))], ['Duración', `${dias} ${dias === 1 ? 'día' : 'días'}`], ...(b.estado ? [[d.ne, b.estado]] : [])])}>
              <rect className="gr-hit" x="0" y={yc - fila / 2} width={w} height={fila} />
              <rect className="gr-a-gantt" x={xa} y={yc - bh / 2} width={xb - xa} height={bh} rx={Math.min(4, bh / 2)} style={{ fill: pin.relleno(b.color), stroke: pin.col(b.color), '--o': i }} />
              {etq && <text x={izq - 8} y={yc} dy="0.35em" textAnchor="end">{etq}</text>}
            </g>
          )
        })}
      </g>
    </Svg>
  )
}

// ── 12. Pendiente: mismos días del mes anterior → mes en curso, por categoría ────────────────────
function calcPendiente(regs, campos, o, hoy) {
  const c = campoDe(campos, o.agrupar); const cf = campoDe(campos, o.fecha)
  if (!c || !cf) return FALTA
  const t = E.tramosComparables(hoy)
  const grupos = E.agrupar(regs, c, { top: c.tipo === 'texto' ? 6 : undefined })
  const items = grupos.map((g, i) => {
    const tr = compararTramos(g.registros, cf.id, o, hoy)
    return { id: g.clave, etiqueta: g.etiqueta, color: colorDe(g, i), a: tr.anterior, b: tr.actual, var: tr.var }
  }).filter((x) => x.a || x.b)
  if (!items.length) return `Sin registros entre ${t.anterior.etiqueta} ni ${t.actual.etiqueta}`
  return { items, t, tipo: tipoDe(o, campos), que: queMide(o, campos), pie: `${queMide(o, campos)} por ${c.nombre.toLowerCase()}: ${t.anterior.etiqueta} → ${t.actual.etiqueta} (mismos días)` }
}
function Pendiente({ w, h, d, ix }) {
  const pin = usePintura(); const ord = useOrden()
  const { items, tipo, t } = d
  const conCab = h >= 90
  const arriba = conCab ? 26 : 8; const abajo = 8
  const tA = items.map((x) => fmtCorto(tipo, x.a))
  const tB = items.map((x) => fmtCorto(tipo, x.b))
  const izq = Math.max(...tA.map(anchoVal), anchoTexto(t.anterior.etiqueta) / 2) + 12
  const conNombres = w >= 260
  const nomMax = conNombres ? Math.min(w * 0.3, Math.max(...items.map((x) => anchoTexto(x.etiqueta)))) : 0
  const der = Math.max(...tB.map(anchoVal)) + (conNombres ? nomMax + 6 : 0) + 12
  const xa = izq; const xb = Math.max(xa + 40, w - der)
  const max = Math.max(1e-9, ...items.flatMap((x) => [x.a, x.b]))
  const Y = escala(0, max, h - abajo, arriba)
  // Etiquetas a cada lado repartidas sin encimarse; si no caben todas, se quitan las de menor valor y se reintenta.
  const lado = (vals) => {
    let quedan = items.map((_, i) => i)
    while (quedan.length) {
      const ord_ = [...quedan].sort((i, j) => Y(vals[i]) - Y(vals[j]))
      const ys = repartirVertical(ord_.map((i) => Y(vals[i])), arriba, h - abajo, 15)
      if (ys) return new Map(ord_.map((i, k) => [i, ys[k]]))
      const menor = quedan.reduce((m, i) => (vals[i] < vals[m] ? i : m), quedan[0])
      quedan = quedan.filter((i) => i !== menor)
    }
    return new Map()
  }
  const yA = lado(items.map((x) => x.a)); const yB = lado(items.map((x) => x.b))
  const n = items.length
  return (
    <Svg w={w} h={h} aria={`${d.pie}: ${items.map((x, i) => `${x.etiqueta} ${tA[i]} → ${tB[i]}`).join(', ')}`}>
      <g className="gr-rejilla" aria-hidden="true">
        <line x1={xa} x2={xa} y1={arriba - 4} y2={h - abajo} />
        <line x1={xb} x2={xb} y1={arriba - 4} y2={h - abajo} />
        {conCab && <><text x={xa} y={9} dy="0.35em" textAnchor="middle" className="gr-fuerte">{t.anterior.etiqueta}</text><text x={xb} y={9} dy="0.35em" textAnchor="middle" className="gr-fuerte">{t.actual.etiqueta}</text></>}
      </g>
      <g className="gr-marcas">
        {items.map((x, i) => {
          const c = pin.col(x.color)
          return (
            <g key={x.id} className={`gr-m${ix.c(x.id)}`} {...ix.p(x.id, x.etiqueta, [[t.anterior.etiqueta, fmt(tipo, x.a)], [t.actual.etiqueta, fmt(tipo, x.b), c], ['Variación (mismos días)', x.var === null ? '—' : fmtPct(x.var, true)]])}>
              <line className="gr-hit-l" x1={xa} y1={Y(x.a)} x2={xb} y2={Y(x.b)} />
              <path className="gr-traza gr-linea gr-pend" d={`M${xa},${Y(x.a).toFixed(1)} L${xb},${Y(x.b).toFixed(1)}`} pathLength="1" style={{ stroke: c, '--i': ord(i, n) }} />
              <circle className="gr-a-pop" cx={xa} cy={Y(x.a)} r="4" style={{ fill: c, stroke: pin.sup, strokeWidth: 2, '--o': ord(i, n) }} />
              <circle className="gr-a-pop" cx={xb} cy={Y(x.b)} r="4" style={{ fill: c, stroke: pin.sup, strokeWidth: 2, '--o': ord(i, n) + 8 }} />
              {yA.has(i) && <text className="gr-valor gr-aparece" x={xa - 9} y={yA.get(i)} dy="0.35em" textAnchor="end" style={{ '--o': 10 }}>{tA[i]}</text>}
              {yB.has(i) && <text className="gr-aparece" x={xb + 9} y={yB.get(i)} dy="0.35em" style={{ '--o': 12 }}><tspan className="gr-valor">{tB[i]}</tspan>{conNombres && <tspan dx="6">{cortar(x.etiqueta, nomMax)}</tspan>}</text>}
            </g>
          )
        })}
      </g>
    </Svg>
  )
}

// ── 13. Media dona ────────────────────────────────────────────────────────────────────────────────
function MediaDona({ w, h, d, ix, uid }) {
  const pin = usePintura(); const ord = useOrden()
  const { items, tipo, total } = d
  const leyItems = items.map((it) => ({ id: it.id, nombre: it.etiqueta, color: it.color, suave: true, valor: fmtPct(E.porcentajeDelTotal(it.valor, total)), filas: [[d.que, fmt(tipo, it.valor), pin.col(it.color)]] }))
  const ley = planLeyenda(w, h, leyItems)
  const a = areaCon(ley, w, h)
  const R = Math.max(14, Math.min(a.w / 2 - 4, a.h - 8))
  const cx = a.w / 2; const cy = Math.min(a.h - 4, (a.h + R) / 2)
  const grosor = Math.max(8, R * 0.36)
  const r0 = R - grosor
  let acum = 0
  const partes = items.filter((it) => it.valor > 0).map((it, i) => { const f = it.valor / total; const a0 = -Math.PI / 2 + acum * Math.PI; acum += f; return { it, i, f, a0, a1: -Math.PI / 2 + acum * Math.PI } })
  const etq = etiquetasCirculo({ partes, cx, cy, r0, R, a, fuera: false })
  const origen = { transformOrigin: `${cx}px ${cy}px` }
  const totalTxt = fmt(tipo, total)
  let tam = Math.round(Math.max(13, Math.min(30, r0 * 0.45)))
  while (tam > 12 && anchoTexto(totalTxt, tam, 600) > r0 * 1.7) tam--
  const centro = anchoTexto(totalTxt, tam, 600) <= r0 * 1.7 ? totalTxt : fmtCorto(tipo, total)
  const conCentro = r0 >= 24 && anchoTexto(centro, tam, 600) <= r0 * 1.8
  return (
    <Svg w={w} h={h} aria={`${d.pie}: ${items.map((i) => `${i.etiqueta} ${fmtPct(E.porcentajeDelTotal(i.valor, total))}`).join(', ')}`}>
      <path className="gr-pista-f" d={sector(cx, cy, r0, R, -Math.PI / 2, Math.PI / 2)} />
      <g className="gr-marcas gr-a-abanico" style={origen}>
        {partes.map(({ it, i, f, a0, a1 }) => (
          <path key={it.id} id={`${uid}-m${i}`} className={`gr-forma gr-a-gajo gr-m${ix.c(it.id)}`} d={sector(cx, cy, r0, R, a0, a1)}
            style={{ fill: pin.relleno(it.color), stroke: pin.sup, strokeWidth: partes.length > 1 ? SEPARADOR : 0, strokeLinejoin: 'round', ...origen, '--o': ord(i, partes.length) }}
            {...ix.p(it.id, it.larga, [[d.que, fmt(tipo, it.valor), pin.col(it.color)], ['Del total', fmtPct(f)], ['Registros', fmt('numero', it.n)]])} />
        ))}
      </g>
      <g pointerEvents="none">
        {etq.filter((e) => e.modo === 'dentro').map((e) => <text key={e.it.id} className="gr-valor gr-dentro gr-aparece" data-forma={`${uid}-m${e.i}`} x={e.x} y={e.y} dy="0.35em" textAnchor="middle" style={{ fill: pin.texto(pin.relleno(e.it.color)), '--o': 8 + e.i }}>{e.t}</text>)}
        {conCentro && <text x={cx} y={cy - tam * 0.45} dy="0.35em" textAnchor="middle" className="gr-grande" style={{ fontSize: tam }}><Cuenta v={total} f={(x) => (centro === totalTxt ? fmt(tipo, x) : fmtCorto(tipo, x))} /></text>}
      </g>
      <Leyenda plan={ley} w={w} h={h} ix={ix} items={leyItems} />
    </Svg>
  )
}

// ── 14. Barras de progreso (parte del total) ──────────────────────────────────────────────────────
function Progreso({ w, h, d, ix }) {
  const pin = usePintura(); const ord = useOrden()
  const { items, tipo, total } = d
  const n = items.length
  const fila = (h - 2) / n
  const doble = fila >= 30 // etiqueta y % arriba, barra abajo; si no, todo en una línea
  return (
    <Svg w={w} h={h} aria={`${d.pie}: ${items.map((i) => `${i.etiqueta} ${fmtPct(E.porcentajeDelTotal(i.valor, total))}`).join(', ')}`}>
      <g className="gr-marcas">
        {items.map((it, i) => {
          const f = E.porcentajeDelTotal(it.valor, total)
          const pct = fmtPct(f)
          const y = 1 + fila * i
          const val = `${fmtCorto(tipo, it.valor)} · ${pct}`
          const derTxt = anchoVal(val) + anchoTexto(it.etiqueta) + 12 <= w ? val : pct
          let bx; let bw; let by; let etq
          if (doble) { bx = 0; bw = w; by = y + fila - 9; etq = cortar(it.etiqueta, w - anchoVal(derTxt) - 12) } else {
            const izq = fila >= 15 && w >= 200 ? Math.min(w * 0.34, Math.max(...items.map((x) => anchoTexto(x.etiqueta))) + 10) : 0
            const derW = fila >= 15 && w >= 160 ? anchoVal(pct) + 8 : 0
            bx = izq; bw = Math.max(10, w - izq - derW); by = y + fila / 2 - 3; etq = izq ? cortar(it.etiqueta, izq - 10) : ''
          }
          const yt = doble ? y + 9 : y + fila / 2
          return (
            <g key={it.id} className={`gr-m${ix.c(it.id)}`} {...ix.p(it.id, it.larga, [[d.que, fmt(tipo, it.valor), pin.col(it.color)], ['Del total', pct], ['Registros', fmt('numero', it.n)]])}>
              <rect className="gr-hit" x="0" y={y} width={w} height={fila} />
              <rect className="gr-pista" x={bx} y={by} width={bw} height="6" rx="3" />
              <rect className="gr-a-barra" x={bx} y={by} width={Math.max(f > 0 ? 3 : 0, bw * f)} height="6" rx="3" style={{ fill: pin.col(it.color), '--o': ord(i, n) }} />
              {etq && <text className="gr-aparece" x={doble ? 0 : bx - 8} y={yt} dy="0.35em" textAnchor={doble ? 'start' : 'end'} style={{ '--o': ord(i, n) }}>{etq}</text>}
              {(doble || (fila >= 15 && w >= 160)) && <text className="gr-valor gr-aparece" x={w} y={yt} dy="0.35em" textAnchor="end" style={{ '--o': ord(i, n) + 2 }}>{doble ? derTxt : pct}</text>}
            </g>
          )
        })}
      </g>
    </Svg>
  )
}

// ── 15. Múltiplos pequeños (una mini línea por categoría, misma escala) ───────────────────────────
function calcMultiples(regs, campos, o, hoy) {
  const c = campoDe(campos, o.agrupar); const cf = campoDe(campos, o.fecha)
  if (!c || !cf) return FALTA
  const grupos = E.agrupar(regs, c, { top: c.tipo === 'texto' ? 6 : undefined })
  const meses = E.agruparPorMes([], cf.id, o.meses || 12, hoy)
  const paneles = grupos.map((g, i) => {
    const vals = E.agruparPorMes(g.registros, cf.id, o.meses || 12, hoy).map((m) => E.resumir(m.registros, medirDe(o), fnDe(o)) ?? 0)
    return { id: g.clave, etiqueta: g.etiqueta, color: colorDe(g, i), vals, total: sumaDe(vals) }
  }).filter((p) => p.total > 0).sort((a, b) => b.total - a.total).slice(0, 6)
  if (!paneles.length) return 'Sin datos en los últimos meses'
  return { paneles, meses, max: Math.max(1e-9, ...paneles.flatMap((p) => p.vals)), tipo: tipoDe(o, campos), que: queMide(o, campos),
    pie: `${queMide(o, campos)} por mes de ${cf.nombre.toLowerCase()} y ${c.nombre.toLowerCase()} · misma escala · total de ${meses.length} meses` }
}
function Multiples({ w, h, d, ix, uid }) {
  const pin = usePintura()
  const { paneles, meses, tipo } = d
  let cols = Math.max(1, Math.min(3, Math.floor(w / 120), paneles.length))
  let filas = Math.ceil(paneles.length / cols)
  while (filas > 1 && h / filas < 54 && cols < Math.min(paneles.length, Math.floor(w / 90))) { cols++; filas = Math.ceil(paneles.length / cols) }
  const caben = Math.max(1, cols * Math.max(1, Math.floor(h / 44)))
  const ver = paneles.slice(0, caben)
  filas = Math.ceil(ver.length / cols)
  const gx = 10; const gy = 8
  const pw = (w - (cols - 1) * gx) / cols; const ph = (h - (filas - 1) * gy) / filas
  const n = meses.length
  return (
    <Svg w={w} h={h} aria={`${d.pie}: ${ver.map((p) => `${p.etiqueta} ${fmt(tipo, p.total)}`).join(', ')}`}>
      {ver.map((p, k) => {
        const x0 = (k % cols) * (pw + gx); const y0 = Math.floor(k / cols) * (ph + gy)
        const cab = 16
        const X = escala(0, n - 1, x0 + 3, x0 + pw - 3)
        const Y = escala(0, d.max, y0 + ph - 3, y0 + cab + 3)
        const linea = p.vals.slice(0, -1).map((v, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)},${Y(v).toFixed(1)}`).join(' ')
        const resto = n > 1 ? `M${X(n - 2).toFixed(1)},${Y(p.vals[n - 2]).toFixed(1)} L${X(n - 1).toFixed(1)},${Y(p.vals[n - 1]).toFixed(1)}` : ''
        const area = `${p.vals.map((v, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)},${Y(v).toFixed(1)}`).join(' ')} L${X(n - 1).toFixed(1)},${y0 + ph - 3} L${X(0).toFixed(1)},${y0 + ph - 3} Z`
        const tv = fmtCorto(tipo, p.total)
        const tit = cortar(p.etiqueta, pw - anchoVal(tv) - 10)
        const c = pin.col(p.color)
        return (
          <g key={p.id} className={`gr-m gr-panel${ix.c(p.id)}`} {...ix.p(p.id, p.etiqueta, [[`Total ${n} meses`, fmt(tipo, p.total), c], ...meses.slice(-3).map((m, i) => [m.larga + (i === 2 ? ' (en curso)' : ''), fmt(tipo, p.vals[n - 3 + i])])])}>
            <rect className="gr-panel-f" x={x0} y={y0} width={pw} height={ph} rx="8" />
            {ph >= 40 && tit && <text x={x0 + 2} y={y0 + 8} dy="0.35em">{tit}</text>}
            {ph >= 40 && <text className="gr-valor" x={x0 + pw - 2} y={y0 + 8} dy="0.35em" textAnchor="end">{tv}</text>}
            <path className="gr-area gr-a-area" d={area} style={{ fill: pin.relleno(p.color, 0.42), '--o': k }} />
            <path className="gr-traza gr-linea gr-fina" d={linea} pathLength="1" style={{ stroke: c, '--i': k * 2 }} />
            {resto && <path className="gr-linea gr-fina gr-parcial-l gr-aparece" d={resto} style={{ stroke: c, '--o': 12 + k }} />}
          </g>
        )
      })}
    </Svg>
  )
}

// ── 16. Dos KPIs lado a lado (mismos días) ────────────────────────────────────────────────────────
function calcDosKpis(regs, campos, o, hoy) {
  const cf = campoDe(campos, o.fecha); const cv = campoDe(campos, o.valor)
  if (!cf || !cv) return FALTA
  const a = compararTramos(regs, cf.id, { funcion: 'conteo' }, hoy)
  const b = compararTramos(regs, cf.id, { valor: cv.id, funcion: 'suma' }, hoy)
  return { t: a.t, kpis: [{ id: 'k1', etiqueta: 'Cantidad', tipo: 'numero', ...a }, { id: 'k2', etiqueta: `Total de ${cv.nombre.toLowerCase()}`, tipo: cv.tipo, ...b }],
    pie: `${a.texto} (mismos días) · por ${cf.nombre.toLowerCase()}` }
}
function DosKpis({ w, h, d, ix }) {
  const pin = usePintura()
  const fila = w >= 300
  const anchoT = fila ? (w - 12) / 2 : w
  const altoT = fila ? h : (h - 10) / 2
  const tam = Math.round(Math.max(16, Math.min(34, anchoT / 6.5, altoT / 3)))
  const conBarras = altoT >= tam + 70
  return (
    <div className={`gr-dos${fila ? ' gr-dos-fila' : ''}`}>
      {d.kpis.map((k, i) => {
        const max = Math.max(1e-9, k.actual, k.anterior)
        const txt = anchoTexto(fmt(k.tipo, k.actual), tam, 600) <= anchoT - 8 ? fmt(k.tipo, k.actual) : fmtCorto(k.tipo, k.actual)
        return (
          <div key={k.id} className={`gr-dos-k gr-fila gr-m${ix.c(k.id)}`} style={{ '--i': i }} {...ix.p(k.id, k.etiqueta, [[k.t.actual.etiqueta, fmt(k.tipo, k.actual), pin.acento], [k.t.anterior.etiqueta, fmt(k.tipo, k.anterior), pin.gris], ['Variación (mismos días)', k.var === null ? '—' : fmtPct(k.var, true)]])}>
            <small>{k.etiqueta}</small>
            <strong style={{ fontSize: tam }}><Cuenta v={k.actual} f={(x) => (txt === fmt(k.tipo, k.actual) ? fmt(k.tipo, x) : fmtCorto(k.tipo, x))} /></strong>
            <span className={`gr-var ${claseVar(k.var)}`}><b>{k.var === null ? (k.anterior === 0 && k.actual > 0 ? '▲ nuevo' : '—') : flecha(k.var)}</b><i>{k.t.actual.etiqueta} vs {k.t.anterior.etiqueta}</i></span>
            {conBarras && (
              <span className="gr-dos-barras" aria-hidden="true">
                <i style={{ '--f': k.actual / max, background: pin.acento }} className="gr-crece-h" />
                <i style={{ '--f': k.anterior / max, background: E.mezclar(pin.gris, pin.sup, 0.7) }} className="gr-crece-h" />
              </span>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ── Catálogo nuevo ────────────────────────────────────────────────────────────────────────────────
const porCat = (b) => b.estado || b.texto
export const NUEVOS = {
  paleta: { nombre: 'Paleta (lollipop)', familia: 'cb', requiere: { categoria: 1 }, Componente: Paleta,
    opciones: (b) => ({ agrupar: b.texto || b.estado, funcion: sumaOConteo(b), top: 8 }), calcular: (r, c, o) => conTotal(calcCategorias(r, c, o, 8)) },
  combo: { nombre: 'Columnas + acumulado', familia: 'cb', requiere: { fecha: 1 }, Componente: Combo,
    opciones: (b) => ({ funcion: sumaOConteo(b), meses: 12 }), calcular: (r, c, o, hoy) => { const d = conMeses(calcMeses(r, c, o, hoy)); return typeof d === 'string' ? d : { ...d, pie: `${d.pie} · línea = acumulado` } } },
  pareto: { nombre: 'Pareto', familia: 'cb', requiere: { categoria: 1 }, Componente: Pareto,
    opciones: (b) => ({ agrupar: b.texto || b.estado, funcion: sumaOConteo(b), top: 10 }), calcular: (r, c, o) => calcPareto(r, c, o) },
  escalones: { nombre: 'Escalones', familia: 'la', requiere: { fecha: 1 }, Componente: Escalones,
    opciones: (b) => ({ funcion: sumaOConteo(b) }), calcular: (r, c, o, hoy) => conMeses(calcMeses(r, c, o, hoy)) },
  pendiente: { nombre: 'Pendiente (mes anterior → actual)', familia: 'la', requiere: { fecha: 1, categoria: 1 }, Componente: Pendiente,
    opciones: (b) => ({ agrupar: porCat(b), funcion: sumaOConteo(b) }), calcular: (r, c, o, hoy) => calcPendiente(r, c, o, hoy) },
  multiples: { nombre: 'Múltiplos pequeños', familia: 'la', requiere: { fecha: 1, categoria: 1 }, Componente: Multiples,
    opciones: (b) => ({ agrupar: porCat(b), funcion: sumaOConteo(b), meses: 12 }), calcular: (r, c, o, hoy) => calcMultiples(r, c, o, hoy) },
  waffle: { nombre: 'Waffle 10 × 10', familia: 'ci', requiere: { categoria: 1 }, Componente: Waffle,
    opciones: (b) => ({ agrupar: b.agrupar, funcion: 'conteo' }), calcular: (r, c, o) => conTotal(calcCategorias(r, c, o, 6)) },
  rosa: { nombre: 'Rosa polar', familia: 'ci', requiere: { categoria: 1 }, Componente: Rosa,
    opciones: (b) => ({ agrupar: porCat(b), funcion: sumaOConteo(b) }), calcular: (r, c, o) => conTotal(calcCategorias(r, c, o, 8)) },
  'media-dona': { nombre: 'Media dona', familia: 'ci', requiere: { categoria: 1 }, Componente: MediaDona,
    opciones: (b) => ({ agrupar: b.agrupar, funcion: 'conteo' }), calcular: (r, c, o) => conTotal(calcCategorias(r, c, o, 6)) },
  sol: { nombre: 'Sol (2 niveles)', familia: 'fl', requiere: { estado: 1, texto: 1 }, Componente: Sol,
    opciones: (b) => ({ estado: b.estado, texto: b.texto, funcion: sumaOConteo(b) }), calcular: (r, c, o) => calcSol(r, c, o) },
  puntos: { nombre: 'Puntos por categoría', familia: 'di', requiere: { categoria: 1, medida: 1 }, Componente: Puntos,
    opciones: (b) => ({ agrupar: porCat(b), valor: b.valor }), calcular: (r, c, o) => calcPuntos(r, c, o) },
  'calor-hora': { nombre: 'Calor día × hora', familia: 'ti', requiere: { fecha: 1, hora: 1 }, Componente: CalorHora,
    opciones: (b) => ({ fecha: b.fecha, hora: b.hora, funcion: 'conteo' }), calcular: (r, c, o) => calcCalorHora(r, c, o) },
  gantt: { nombre: 'Línea de tiempo', familia: 'ti', requiere: { fecha: 2 }, Componente: Gantt,
    opciones: (b) => ({ fecha: b.fecha, fecha2: b.fecha2, texto: b.texto, estado: b.estado }), calcular: (r, c, o, hoy) => calcGantt(r, c, o, hoy) },
  bala: { nombre: 'Bala contra meta', familia: 're', requiere: { fecha: 1 }, Componente: Bala,
    opciones: (b) => ({ funcion: sumaOConteo(b), meta: null }), calcular: (r, c, o, hoy) => calcBala(r, c, o, hoy) },
  progreso: { nombre: 'Barras de progreso', familia: 're', requiere: { categoria: 1 }, Componente: Progreso,
    opciones: (b) => ({ agrupar: b.agrupar, funcion: sumaOConteo(b) }), calcular: (r, c, o) => conTotal(calcCategorias(r, c, o, 8)) },
  'dos-kpis': { nombre: 'Dos KPIs', familia: 're', requiere: { fecha: 1, medida: 1 }, Componente: DosKpis, html: true,
    opciones: (b) => ({ valor: b.valor }), calcular: (r, c, o, hoy) => calcDosKpis(r, c, o, hoy) },
}
export { nombre, choca, cajaEnSector }
