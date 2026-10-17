/* Vistas extra del catálogo (herramientas que la persona pide por chat). Mismo contrato que vistas.jsx: solo dibuja, sin API. */
import { useContext, useMemo, useState } from 'react'
import { isoDia } from './datosEjemplo'
import { region } from './regional'
import { FichaContext, ver } from './vistas'
import './vistas-extra.css'

const MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
const MESES_LARGO = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
const DIAS_SEM = ['lun', 'mar', 'mié', 'jue', 'vie', 'sáb', 'dom']
const COLORES = ['#7c5cff', '#22d3a6', '#f5a623', '#f0587a', '#5b6bff', '#3fb8ff', '#b06cff']
const MAX_TARJETAS = 30
const MAX_FILAS_MATRIZ = 12

const hoyIso = () => isoDia(new Date())
const diasHasta = (iso) => Math.round((new Date(`${iso}T00:00:00`) - new Date(`${hoyIso()}T00:00:00`)) / 86400000)
const diasDesde = (iso) => Math.round((new Date(`${hoyIso()}T00:00:00`) - new Date(`${iso}T00:00:00`)) / 86400000)

const campo = (campos, id) => campos.find((c) => c.id === id)

/** Igual que en vistas.jsx: abre la ficha del registro al clic o Enter/Espacio. */
function abrible(abrir, seccion, r) {
  if (!abrir) return {}
  const ir = (e) => abrir(seccion.id, r.id, e.currentTarget)
  return {
    role: 'button',
    tabIndex: 0,
    'data-abre': '',
    onClick: ir,
    onKeyDown: (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); ir(e) } },
  }
}

function Vacio({ seccion }) {
  return (
    <div className="mc-vacio-grande pl-vacio">
      <b>Todavía no hay registros en {seccion.titulo}</b>
      <p>Cuando agregues el primero aparecerá aquí. Puedes pedírselo a Shifu en el chat o usar el botón Agregar.</p>
    </div>
  )
}

function tituloDe(seccion, campos, opciones, r) {
  const ct = seccion.tarjeta?.campos?.map((id) => campo(campos, id)).filter(Boolean)
  const id = ct?.[0]?.id ?? opciones.titulo ?? campos[0]?.id
  return ver('texto', r.valores[id] ?? Object.values(r.valores)[0])
}

function filtrarRegistros(registros, filtro) {
  if (!filtro?.campo) return registros
  return registros.filter((r) => String(r.valores[filtro.campo]) === String(filtro.igual))
}

function parseMes(opciones) {
  const s = opciones.mes
  if (s && /^\d{4}-\d{2}$/.test(s)) {
    const [y, m] = s.split('-').map(Number)
    return { y, m }
  }
  const h = new Date()
  return { y: h.getFullYear(), m: h.getMonth() + 1 }
}

function celdasMes(y, m) {
  const primero = new Date(y, m - 1, 1)
  const ultimo = new Date(y, m, 0).getDate()
  const offset = (primero.getDay() + 6) % 7 // lunes = 0
  const celdas = []
  for (let i = 0; i < offset; i++) celdas.push({ dia: null })
  for (let d = 1; d <= ultimo; d++) celdas.push({ dia: d, iso: `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}` })
  while (celdas.length % 7 !== 0) celdas.push({ dia: null })
  return celdas
}

function Calendario({ seccion, campos, registros, opciones }) {
  const abrir = useContext(FichaContext)
  const inicial = parseMes(opciones)
  const [vista, setVista] = useState(inicial)
  const { y, m } = vista
  const cEstado = opciones.estado && campo(campos, opciones.estado)

  const conFecha = registros.filter((r) => r.valores[opciones.fecha])
  const sinFecha = registros.length - conFecha.length
  // Los hooks van antes de cualquier return (si no, React se rompe al pasar de 0 a N registros).
  const porDia = useMemo(() => {
    const map = {}
    for (const r of registros) {
      const iso = r.valores[opciones.fecha]
      if (!iso) continue
      if (!map[iso]) map[iso] = []
      map[iso].push(r)
    }
    return map
  }, [registros, opciones.fecha])
  if (!registros.length) return <Vacio seccion={seccion} />

  const celdas = celdasMes(y, m)
  const hoy = hoyIso()
  const mesAnt = () => setVista((v) => (v.m === 1 ? { y: v.y - 1, m: 12 } : { y: v.y, m: v.m - 1 }))
  const mesSig = () => setVista((v) => (v.m === 12 ? { y: v.y + 1, m: 1 } : { y: v.y, m: v.m + 1 }))
  const irHoy = () => { const n = new Date(); setVista({ y: n.getFullYear(), m: n.getMonth() + 1 }) }

  const colorEstado = (r) => {
    if (!cEstado) return COLORES[0]
    const i = cEstado.opciones.indexOf(r.valores[opciones.estado])
    return COLORES[i % COLORES.length]
  }

  const diasConDatos = celdas.filter((c) => c.iso && porDia[c.iso]?.length).map((c) => ({ ...c, items: porDia[c.iso] }))

  return (
    <div className="pl-vx-cal pl-vx-marco" aria-label={`Calendario de ${seccion.titulo}`}>
      <div className="pl-vx-cal-cab">
        <b>{MESES_LARGO[m - 1]} {y}</b>
        <div className="pl-vx-cal-nav">
          <button type="button" onClick={mesAnt} aria-label="Mes anterior">‹</button>
          <button type="button" className="hoy" onClick={irHoy}>Hoy</button>
          <button type="button" onClick={mesSig} aria-label="Mes siguiente">›</button>
        </div>
      </div>
      <div className="pl-vx-scroll">
        <div className="pl-vx-cal-rejilla">
          {DIAS_SEM.map((d) => <span key={d} className="pl-vx-cal-dow">{d}</span>)}
          {celdas.map((c, i) => {
            if (!c.iso) return <div key={`e-${i}`} className="pl-vx-cal-celda fuera" aria-hidden="true" />
            const items = porDia[c.iso] || []
            const extra = items.length - 3
            return (
              <div key={c.iso} className={`pl-vx-cal-celda${c.iso === hoy ? ' hoy' : ''}`}>
                <em>{c.dia}</em>
                <ul>
                  {items.slice(0, 3).map((r) => (
                    <li key={r.id} title={tituloDe(seccion, campos, opciones, r)} {...abrible(abrir, seccion, r)}>
                      {cEstado && <i style={{ background: colorEstado(r) }} aria-hidden="true" />}
                      {tituloDe(seccion, campos, opciones, r)}
                    </li>
                  ))}
                  {extra > 0 && <li className="pl-mas" style={{ background: 'transparent', cursor: 'default' }}>+{extra}</li>}
                </ul>
              </div>
            )
          })}
        </div>
        <div className="pl-vx-cal-lista">
          {diasConDatos.map((d) => (
            <section key={d.iso}>
              <h4>{d.dia} {MESES[m - 1]}</h4>
              <ul>
                {d.items.slice(0, 15).map((r) => (
                  <li key={r.id} title={tituloDe(seccion, campos, opciones, r)} {...abrible(abrir, seccion, r)}>
                    {tituloDe(seccion, campos, opciones, r)}
                  </li>
                ))}
                {d.items.length > 15 && <li className="pl-mas">+{d.items.length - 15} más</li>}
              </ul>
            </section>
          ))}
          {!diasConDatos.length && <p className="pl-mas">Sin citas este mes</p>}
        </div>
      </div>
      {sinFecha > 0 && <p className="pl-vx-cal-aviso" title={`${region().numero(sinFecha)} registros sin fecha no aparecen`}>{region().numero(sinFecha)} registros sin fecha no aparecen</p>}
    </div>
  )
}

function TableroDinero({ seccion, campos, registros, opciones }) {
  const abrir = useContext(FichaContext)
  const c = campo(campos, opciones.por)
  const ct = seccion.tarjeta?.campos?.map((id) => campo(campos, id)).filter(Boolean)
  const dets = ct ? ct.slice(1) : [opciones.detalle && campo(campos, opciones.detalle)].filter(Boolean)
  if (!registros.length) return <Vacio seccion={seccion} />
  if (!c) return <div className="pl-vacio mc-vacio-grande"><b>Falta el campo de estado</b></div>

  const claseDias = (d) => (d >= 30 ? 'alerta' : d >= 20 ? 'aviso' : '')

  return (
    <div className="pl-tablero pl-vx-marco" role="list" aria-label={`${seccion.titulo} por ${c.nombre.toLowerCase()}`}>
      {c.opciones.map((op, i) => {
        const de = registros.filter((r) => r.valores[opciones.por] === op)
        const total = de.reduce((s, r) => s + (Number(r.valores[opciones.suma]) || 0), 0)
        return (
          <section key={op} className="pl-col" role="listitem" style={{ '--c': COLORES[i % COLORES.length], '--i': i }}>
            <h3>
              <span title={op}>{op}</span>
              <i>{de.length}</i>
            </h3>
            <span className="pl-vx-td-total" title={ver('dinero', total)}>{ver('dinero', total)}</span>
            {de.slice(0, MAX_TARJETAS).map((r, k) => {
              const diasEn = opciones.dias_en && r.valores[opciones.dias_en] ? diasDesde(r.valores[opciones.dias_en]) : null
              return (
                <article key={r.id} className="pl-tarjeta" style={{ '--i': k }} {...abrible(abrir, seccion, r)}>
                  <b title={tituloDe(seccion, campos, opciones, r)}>{tituloDe(seccion, campos, opciones, r)}</b>
                  {dets.map((d) => <small key={d.id} title={String(ver(d.tipo, r.valores[d.id]))}>{ver(d.tipo, r.valores[d.id])}</small>)}
                  {diasEn !== null && <span className={`pl-vx-td-dias ${claseDias(diasEn)}`}>{region().numero(diasEn)} d en etapa</span>}
                </article>
              )
            })}
            {de.length > MAX_TARJETAS && <p className="pl-mas">+{de.length - MAX_TARJETAS} más</p>}
            {!de.length && <p className="pl-mas">Nada aquí</p>}
          </section>
        )
      })}
    </div>
  )
}

function rangoPeriodo(periodo, fechaRef) {
  const d = fechaRef ? new Date(`${fechaRef}T00:00:00`) : new Date()
  d.setHours(0, 0, 0, 0)
  if (periodo === 'semana') {
    const dow = (d.getDay() + 6) % 7
    const ini = new Date(d); ini.setDate(d.getDate() - dow)
    const fin = new Date(ini); fin.setDate(ini.getDate() + 6)
    const antIni = new Date(ini); antIni.setDate(ini.getDate() - 7)
    const antFin = new Date(ini); antFin.setDate(ini.getDate() - 1)
    return { ini: isoDia(ini), fin: isoDia(fin), antIni: isoDia(antIni), antFin: isoDia(antFin) }
  }
  const ini = new Date(d.getFullYear(), d.getMonth(), 1)
  const fin = new Date(d.getFullYear(), d.getMonth() + 1, 0)
  const antIni = new Date(d.getFullYear(), d.getMonth() - 1, 1)
  const antFin = new Date(d.getFullYear(), d.getMonth(), 0)
  return { ini: isoDia(ini), fin: isoDia(fin), antIni: isoDia(antIni), antFin: isoDia(antFin) }
}

function enRango(iso, desde, hasta) {
  if (!iso) return false
  return iso >= desde && iso <= hasta
}

function calcMetrica(registros, opciones, campos) {
  const base = filtrarRegistros(registros, opciones.filtro)
  const fn = opciones.funcion || 'conteo'
  if (fn === 'conteo') return base.length
  const vals = base.map((r) => Number(r.valores[opciones.valor]) || 0)
  if (fn === 'suma') return vals.reduce((a, b) => a + b, 0)
  if (fn === 'promedio') return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : 0
  return base.length
}

function Cifra({ seccion, campos, registros, opciones }) {
  const fn = opciones.funcion || 'conteo'
  const cValor = opciones.valor && campo(campos, opciones.valor)
  const fmt = (v) => {
    if (fn === 'conteo') return region().numero(v)
    if (cValor?.tipo === 'dinero') return ver('dinero', v)
    return ver('numero', v)
  }

  // Con fecha, la cifra es la del periodo actual (la misma que se compara con el anterior); sin fecha, la de todo.
  let valor = calcMetrica(registros, opciones, campos)
  let tendencia = null
  if (opciones.fecha) {
    const { ini, fin, antIni, antFin } = rangoPeriodo(opciones.periodo || 'mes', hoyIso())
    const actual = registros.filter((r) => enRango(r.valores[opciones.fecha], ini, fin))
    const anterior = registros.filter((r) => enRango(r.valores[opciones.fecha], antIni, antFin))
    const va = calcMetrica(actual, opciones, campos)
    valor = va
    const vb = calcMetrica(anterior, opciones, campos)
    if (vb > 0) {
      const pct = Math.round(((va - vb) / vb) * 100)
      tendencia = { pct, sube: pct >= 0 }
    } else if (va > 0) tendencia = { pct: 100, sube: true }
  }

  const meta = Number(opciones.meta)
  const pctMeta = meta > 0 ? Math.min(100, (valor / meta) * 100) : null
  const colorMeta = pctMeta === null ? null : pctMeta >= 100 ? '#22d3a6' : pctMeta >= 50 ? 'var(--tx3)' : '#f0587a'

  const etiqueta = `${fn === 'conteo' ? 'Total' : `${fn === 'promedio' ? 'Promedio de' : 'Total de'} ${(cValor?.nombre || '').toLowerCase()}`}${opciones.fecha ? (opciones.periodo === 'semana' ? ' · esta semana' : ' · este mes') : ''}`

  if (!registros.length && fn === 'conteo') return <Vacio seccion={seccion} />

  return (
    <div className="pl-vx-cifra pl-vx-marco">
      <div className="pl-vx-cifra-cab">
        <small title={etiqueta}>{etiqueta}</small>
        {opciones.ayuda && <span className="pl-vx-cifra-ayuda" title={opciones.ayuda}>?</span>}
      </div>
      <div className="pl-vx-cifra-num" title={fmt(valor)}>{fmt(valor)}</div>
      {tendencia && (
        <div className={`pl-vx-cifra-trend ${tendencia.sube ? 'sube' : 'baja'}`}>
          {tendencia.sube ? '▲' : '▼'} {region().numero(Math.abs(tendencia.pct))}%
        </div>
      )}
      {pctMeta !== null && (
        <div className="pl-vx-cifra-meta" title={`${region().numero(Math.round(pctMeta))}% de la meta`}>
          <i style={{ width: `${pctMeta}%`, '--c': colorMeta }} />
        </div>
      )}
    </div>
  )
}

function Atencion({ seccion, campos, registros, opciones }) {
  const abrir = useContext(FichaContext)
  const vivos = opciones.estado && opciones.excluir
    ? registros.filter((r) => !opciones.excluir.includes(r.valores[opciones.estado]))
    : registros
  if (!registros.length) return <Vacio seccion={seccion} />

  const conDia = vivos
    .filter((r) => r.valores[opciones.fecha])
    .map((r) => ({ r, d: diasHasta(r.valores[opciones.fecha]) }))
    .sort((a, b) => a.d - b.d)

  const vencidos = conDia.filter((x) => x.d < 0).length
  const en7 = conDia.filter((x) => x.d >= 0 && x.d <= 7).length
  const en30 = conDia.filter((x) => x.d >= 0 && x.d <= 30).length
  const urgentes = conDia.slice(0, 5)

  return (
    <div className="pl-vx-atencion pl-vx-marco">
      <div className="pl-vx-atencion-kpis">
        <div className="alerta"><small>Vencidos</small><strong>{region().numero(vencidos)}</strong></div>
        <div className="aviso"><small>Vencen en 7 días</small><strong>{region().numero(en7)}</strong></div>
        <div><small>Vencen en 30 días</small><strong>{region().numero(en30)}</strong></div>
      </div>
      <div className="pl-vx-scroll">
        <ul>
          {urgentes.map(({ r, d }) => (
            <li key={r.id} {...abrible(abrir, seccion, r)}>
              <span title={tituloDe(seccion, campos, opciones, r)}>{tituloDe(seccion, campos, opciones, r)}</span>
              <em>{d < 0 ? `hace ${region().numero(-d)} d` : d === 0 ? 'hoy' : `en ${region().numero(d)} d`}</em>
            </li>
          ))}
          {!urgentes.length && <li className="pl-mas" style={{ justifyContent: 'center' }}>Nada urgente</li>}
        </ul>
      </div>
    </div>
  )
}

const FRANJAS_DEF = [
  { id: 'ahora', titulo: 'Atender ahora', clase: 'urgente' },
  { id: 'vencidos', titulo: 'Vencidos', clase: 'vencido' },
  { id: 'hoy', titulo: 'Hoy y mañana', clase: 'hoy' },
  { id: 's7', titulo: 'Próximos 7 días', clase: '' },
  { id: 'mas', titulo: 'Más adelante', clase: '' },
  { id: 'sin', titulo: 'Sin fecha', clase: '' },
]

function clasificarFranja(r, opciones) {
  const iso = r.valores[opciones.fecha]
  const est = opciones.estado ? r.valores[opciones.estado] : null
  const urgentes = opciones.urgentes || []
  const d = iso ? diasHasta(iso) : null
  if (!iso) return 'sin'
  if (urgentes.includes(est) && d <= 0) return 'ahora'
  if (d < 0) return 'vencidos'
  if (d <= 1) return 'hoy'
  if (d <= 7) return 's7'
  return 'mas'
}

function Franjas({ seccion, campos, registros, opciones }) {
  const abrir = useContext(FichaContext)
  const [abiertas, setAbiertas] = useState(() => new Set(['ahora', 'vencidos', 'hoy']))
  const det = opciones.detalle && campo(campos, opciones.detalle)
  if (!registros.length) return <Vacio seccion={seccion} />

  const grupos = Object.fromEntries(FRANJAS_DEF.map((f) => [f.id, []]))
  for (const r of registros) grupos[clasificarFranja(r, opciones)].push(r)

  let n = 0
  const toggle = (id) => setAbiertas((s) => {
    const t = new Set(s)
    if (t.has(id)) t.delete(id); else t.add(id)
    return t
  })

  return (
    <div className="pl-vx-franjas pl-vx-scroll">
      {FRANJAS_DEF.map((f) => {
        const items = grupos[f.id]
        const abierta = abiertas.has(f.id)
        return (
          <div key={f.id} className={`pl-vx-franja ${f.clase}${abierta ? ' abierta' : ''}`}>
            <button type="button" className="pl-vx-franja-cab" onClick={() => toggle(f.id)} aria-expanded={abierta}>
              <span title={f.titulo}>{f.titulo}</span>
              <i>{items.length}</i>
            </button>
            <ul>
              {items.slice(0, 40).map((r) => {
                n += 1
                const num = n
                const iso = r.valores[opciones.fecha]
                const d = iso ? diasHasta(iso) : null
                return (
                  <li key={r.id} {...abrible(abrir, seccion, r)}>
                    <b>{region().numero(num)}</b>
                    <span title={tituloDe(seccion, campos, opciones, r)}>{tituloDe(seccion, campos, opciones, r)}</span>
                    <em>{det ? ver(det.tipo, r.valores[det.id]) : (d === null ? '—' : d < 0 ? `${region().numero(-d)} d` : d === 0 ? 'hoy' : `${region().numero(d)} d`)}</em>
                  </li>
                )
              })}
              {items.length > 40 && <li className="pl-mas">+{items.length - 40} más</li>}
            </ul>
          </div>
        )
      })}
    </div>
  )
}

function Matriz({ seccion, campos, registros, opciones }) {
  const cFilas = campo(campos, opciones.filas)
  const cCols = campo(campos, opciones.columnas)
  if (!registros.length) return <Vacio seccion={seccion} />
  if (!cFilas || !cCols) return <div className="pl-vacio mc-vacio-grande"><b>Faltan campos de filas o columnas</b></div>

  const filasVals = [...new Set(registros.map((r) => String(r.valores[opciones.filas] || '—')).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'es'))
  const cols = cCols.opciones
  const conteos = {}
  let maxFila = 0
  for (const fv of filasVals) {
    conteos[fv] = {}
    let sumFila = 0
    for (const col of cols) {
      const n = registros.filter((r) => String(r.valores[opciones.filas]) === fv && r.valores[opciones.columnas] === col).length
      conteos[fv][col] = n
      sumFila += n
    }
    maxFila = Math.max(maxFila, sumFila)
  }
  const totCol = Object.fromEntries(cols.map((col) => [col, filasVals.reduce((s, fv) => s + (conteos[fv][col] || 0), 0)]))
  const visibles = filasVals.slice(0, MAX_FILAS_MATRIZ)
  const extra = filasVals.length - visibles.length

  return (
    <div className="pl-vx-matriz pl-vx-marco">
      <table>
        <thead>
          <tr>
            <th className="fila">{cFilas.nombre}</th>
            {cols.map((col, i) => (
              <th key={col} title={col} style={{ '--c': COLORES[i % COLORES.length] }}>
                {col}
                <span className="pct">{region().numero(totCol[col])}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {visibles.map((fv) => {
            const sumFila = cols.reduce((s, col) => s + (conteos[fv][col] || 0), 0)
            const pct = maxFila ? Math.round((sumFila / maxFila) * 100) : 0
            return (
              <tr key={fv}>
                <td className="fila" title={fv}>
                  {fv}
                  <span className="pct">{region().numero(pct)}%</span>
                </td>
                {cols.map((col) => (
                  <td key={col} title={`${fv} · ${col}: ${conteos[fv][col]}`}>
                    <b>{region().numero(conteos[fv][col] || 0)}</b>
                  </td>
                ))}
              </tr>
            )
          })}
        </tbody>
      </table>
      {extra > 0 && <p className="pl-mas">+{region().numero(extra)} filas más</p>}
    </div>
  )
}

// Qué pide cada vista (requiere/opcional) vive en validar.js → VISTAS: una sola fuente para el cerco.
export const COMPONENTES_EXTRA = {
  calendario_mes: Calendario,
  tablero_dinero: TableroDinero,
  cifra: Cifra,
  atencion: Atencion,
  franjas: Franjas,
  matriz: Matriz,
}
