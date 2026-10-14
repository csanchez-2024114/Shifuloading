/* Catálogo cerrado de vistas de las plantillas (las mismas claves que `VISTAS` en validar.js).
 * Cada vista recibe { seccion, campos, registros, opciones, datos } y SOLO dibuja: nunca llama a la API y todo número
 * que muestra lo cuenta de los registros (nada escrito a mano). */
import { createContext, useContext, useEffect, useRef, useState } from 'react'
import { isoDia } from './datosEjemplo'

/** true cuando el estilo es animado ("vivo"): los números cuentan desde 0, las tablas se ordenan y el tablero se arrastra. */
export const AnimarContext = createContext(false)
const sinMovimiento = () => typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

/** Número que sube desde 0 hasta su valor real (solo en estilos animados). El valor final es siempre el contado. */
function Numero({ v, fmt = (x) => x.toLocaleString('es') }) {
  const animar = useContext(AnimarContext) && !sinMovimiento()
  const [n, setN] = useState(animar ? 0 : v)
  useEffect(() => {
    if (!animar) { setN(v); return }
    let raf; const t0 = performance.now(); const dur = 900
    const paso = (t) => { const k = Math.min(1, (t - t0) / dur); setN(Math.round(v * (1 - (1 - k) ** 3))); if (k < 1) raf = requestAnimationFrame(paso) }
    raf = requestAnimationFrame(paso)
    return () => cancelAnimationFrame(raf)
  }, [v, animar])
  return fmt(n)
}

const MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
const DIAS = ['dom', 'lun', 'mar', 'mié', 'jue', 'vie', 'sáb']
const COLORES = ['#7c5cff', '#22d3a6', '#f5a623', '#f0587a', '#5b6bff', '#3fb8ff', '#b06cff']
const POR_PAGINA = 25
const MAX_TARJETAS = 6

const hoyIso = () => isoDia(new Date())
const diasHasta = (iso) => Math.round((new Date(`${iso}T00:00:00`) - new Date(`${hoyIso()}T00:00:00`)) / 86400000)
const fechaCorta = (iso) => { const [a, m, d] = iso.split('-').map(Number); return `${d} ${MESES[m - 1]}${a !== new Date().getFullYear() ? ` ${a}` : ''}` }
export const ver = (tipo, v) => (v === undefined || v === null || v === '' ? '—'
  : tipo === 'fecha' ? fechaCorta(v) : tipo === 'dinero' ? `Q ${Number(v).toLocaleString('es')}` : tipo === 'numero' ? Number(v).toLocaleString('es') : String(v))
const campo = (campos, id) => campos.find((c) => c.id === id)
const plural = (n, uno, varios) => `${n.toLocaleString('es')} ${n === 1 ? uno : varios}`

function Vacio({ seccion }) {
  return (
    <div className="mc-vacio-grande pl-vacio">
      <b>Todavía no hay registros en {seccion.titulo}</b>
      <p>Cuando agregues el primero aparecerá aquí. Puedes pedírselo a Shifu en el chat o usar el botón Agregar.</p>
    </div>
  )
}

function Tabla({ seccion, campos, registros }) {
  const animar = useContext(AnimarContext)
  const [orden, setOrden] = useState(null) // { id, dir: 1 | -1 }
  const [busca, setBusca] = useState('')
  const [pagina, setPagina] = useState(0)
  if (!registros.length) return <Vacio seccion={seccion} />
  // Con mucha data la tabla nunca crece sin fin: se busca, se pagina y el cuerpo tiene alto máximo con scroll propio.
  const q = busca.trim().toLowerCase()
  const filtradas = q ? registros.filter((r) => campos.some((c) => String(ver(c.tipo, r.valores[c.id])).toLowerCase().includes(q))) : registros
  const ordenadas = orden ? [...filtradas].sort((a, b) => {
    const x = a.valores[orden.id], y = b.valores[orden.id]
    return (typeof x === 'number' && typeof y === 'number' ? x - y : String(x ?? '').localeCompare(String(y ?? ''), 'es')) * orden.dir
  }) : filtradas
  const paginas = Math.max(1, Math.ceil(ordenadas.length / POR_PAGINA))
  const pag = Math.min(pagina, paginas - 1)
  const filas = ordenadas.slice(pag * POR_PAGINA, (pag + 1) * POR_PAGINA)
  const ordenar = (id) => setOrden((o) => (o?.id === id ? (o.dir === 1 ? { id, dir: -1 } : null) : { id, dir: 1 }))
  return (
    <div className="pl-tabla-marco">
    {registros.length > POR_PAGINA && (
      <div className="pl-tabla-barra">
        <input type="search" placeholder={`Buscar en ${registros.length.toLocaleString('es')} registros…`} value={busca} onChange={(e) => { setBusca(e.target.value); setPagina(0) }} aria-label={`Buscar en ${seccion.titulo}`} />
        <span>{ordenadas.length ? `${(pag * POR_PAGINA + 1).toLocaleString('es')}–${(pag * POR_PAGINA + filas.length).toLocaleString('es')} de ${ordenadas.length.toLocaleString('es')}` : 'Sin resultados'}</span>
        <button type="button" disabled={pag === 0} onClick={() => setPagina(pag - 1)} aria-label="Página anterior">‹</button>
        <button type="button" disabled={pag >= paginas - 1} onClick={() => setPagina(pag + 1)} aria-label="Página siguiente">›</button>
      </div>
    )}
    <div className="pl-tabla" role="table" aria-label={seccion.titulo}>
      <div className="pl-tabla-fila pl-tabla-cab" role="row" style={{ '--n': campos.length }}>
        {campos.map((c) => (
          <span key={c.id} role="columnheader" aria-sort={orden?.id === c.id ? (orden.dir === 1 ? 'ascending' : 'descending') : undefined}>
            {animar ? <button type="button" className="pl-ordenar" onClick={() => ordenar(c.id)}>{c.nombre}<i aria-hidden="true">{orden?.id === c.id ? (orden.dir === 1 ? '↑' : '↓') : '↕'}</i></button> : c.nombre}
          </span>
        ))}
      </div>
      {filas.map((r, i) => (
        <div key={`${pag}-${r.id}`} className="pl-tabla-fila" role="row" style={{ '--n': campos.length, '--i': Math.min(i, 14) }}>
          {campos.map((c) => (
            <span key={c.id} role="cell" data-etiqueta={c.nombre}>
              {c.tipo === 'estado' ? <em className="pl-pildora" style={{ '--c': COLORES[c.opciones.indexOf(r.valores[c.id]) % COLORES.length] }}>{ver(c.tipo, r.valores[c.id])}</em> : ver(c.tipo, r.valores[c.id])}
            </span>
          ))}
        </div>
      ))}
      {!filas.length && <p className="pl-mas">Nada coincide con «{busca}»</p>}
    </div>
    </div>
  )
}

function Kpis({ campos, registros, opciones = {} }) {
  const tarjetas = [{ t: 'En total', v: registros.length, clase: 'total' }]
  if (opciones.hoy) tarjetas.push({ t: 'Hoy', v: registros.filter((r) => r.valores[opciones.hoy] === hoyIso()).length })
  if (opciones.vencen) {
    const d = opciones.dias || 7
    const vivos = opciones.estado && opciones.excluir ? registros.filter((r) => !opciones.excluir.includes(r.valores[opciones.estado])) : registros
    const dias = vivos.map((r) => r.valores[opciones.vencen]).filter(Boolean).map(diasHasta)
    tarjetas.push({ t: `Vencen en ${d} días`, v: dias.filter((x) => x >= 0 && x <= d).length, clase: 'aviso' })
    tarjetas.push({ t: 'Vencidas', v: dias.filter((x) => x < 0).length, clase: 'alerta' })
  }
  if (opciones.suma) tarjetas.push({ t: `Total ${campo(campos, opciones.suma)?.nombre.toLowerCase()}`, v: registros.reduce((s, r) => s + (Number(r.valores[opciones.suma]) || 0), 0), fmt: (x) => ver('dinero', x) })
  if (opciones.por) {
    const c = campo(campos, opciones.por)
    c.opciones.forEach((op, i) => {
      const v = registros.filter((r) => r.valores[opciones.por] === op).length
      // `p` = parte del total (calculada): alimenta la barrita de proporción del estilo animado.
      tarjetas.push({ t: op, v, p: registros.length ? v / registros.length : 0, color: COLORES[i % COLORES.length] })
    })
  }
  return (
    <div className="pl-kpis">
      {tarjetas.map((k, i) => (
        <div key={k.t} className={k.clase || ''} style={{ '--i': i, ...(k.color ? { '--c': k.color } : {}), ...(k.p !== undefined ? { '--p': k.p } : {}) }}>
          <small>{k.t}</small><strong><Numero v={k.v} fmt={k.fmt} /></strong>
          {k.p !== undefined && <span className="pl-kpi-parte" aria-hidden="true"><b /></span>}
        </div>
      ))}
    </div>
  )
}

function Tablero({ seccion, campos, registros, opciones }) {
  const animar = useContext(AnimarContext)
  // Movimientos locales del laboratorio (arrastrar una tarjeta a otra columna). En el CRM real esto sería una operación validada.
  const [movidos, setMovidos] = useState({})
  const [sobre, setSobre] = useState(null)
  const arrastrado = useRef(null)
  const estadoDe = (r) => movidos[r.id] ?? r.valores[opciones.por]
  const c = campo(campos, opciones.por)
  const tituloDe = (r) => ver('texto', r.valores[opciones.titulo] ?? Object.values(r.valores)[0])
  const det = opciones.detalle && campo(campos, opciones.detalle)
  return (
    <div className="pl-tablero" role="list" aria-label={`${seccion.titulo} por ${c.nombre.toLowerCase()}`}>
      {c.opciones.map((op, i) => {
        const de = registros.filter((r) => estadoDe(r) === op)
        const soltar = animar ? {
          onDragOver: (e) => { e.preventDefault(); setSobre(op) },
          onDragLeave: () => setSobre((s) => (s === op ? null : s)),
          onDrop: (e) => { e.preventDefault(); setSobre(null); const id = arrastrado.current; if (id) setMovidos((m) => ({ ...m, [id]: op })) },
        } : {}
        return (
          <section key={op} className={`pl-col${sobre === op ? ' sobre' : ''}`} role="listitem" style={{ '--c': COLORES[i % COLORES.length], '--i': i }} {...soltar}>
            <h3><span>{op}</span><i key={de.length}>{de.length}</i></h3>
            {de.slice(0, MAX_TARJETAS).map((r, k) => (
              <article key={r.id} className={`pl-tarjeta${movidos[r.id] ? ' movida' : ''}`} style={{ '--i': k }} draggable={animar}
                onDragStart={animar ? (e) => { arrastrado.current = r.id; e.dataTransfer.effectAllowed = 'move'; e.currentTarget.classList.add('arrastrando') } : undefined}
                onDragEnd={animar ? (e) => e.currentTarget.classList.remove('arrastrando') : undefined}>
                <b>{tituloDe(r)}</b>{det && <small>{ver(det.tipo, r.valores[det.id])}</small>}
              </article>
            ))}
            {de.length > MAX_TARJETAS && <p className="pl-mas">+{de.length - MAX_TARJETAS} más</p>}
            {!de.length && <p className="pl-mas">Nada aquí</p>}
          </section>
        )
      })}
    </div>
  )
}

function Agenda({ seccion, campos, registros, opciones }) {
  const n = opciones.dias || 7
  const base = new Date(); base.setHours(0, 0, 0, 0)
  const dias = Array.from({ length: n }, (_, i) => { const d = new Date(base); d.setDate(d.getDate() + i); return d })
  const det = opciones.detalle && campo(campos, opciones.detalle)
  return (
    <div className="pl-agenda" style={{ '--n': n }} aria-label={`${seccion.titulo}: próximos ${n} días`}>
      {dias.map((d, i) => {
        const iso = isoDia(d)
        const citas = registros.filter((r) => r.valores[opciones.fecha] === iso).sort((a, b) => String(a.valores[opciones.hora] || '').localeCompare(String(b.valores[opciones.hora] || '')))
        return (
          <section key={iso} className={`pl-dia${i === 0 ? ' hoy' : ''}`} style={{ '--i': i }}>
            <h3><span>{i === 0 ? 'Hoy' : DIAS[d.getDay()]}</span> <b>{d.getDate()} {MESES[d.getMonth()]}</b><i>{citas.length || ''}</i></h3>
            {citas.slice(0, 8).map((r, k) => (
              <article key={r.id} className="pl-cita" style={{ '--i': k }}>
                {opciones.hora && <time>{r.valores[opciones.hora] || '—'}</time>}
                <span><b>{ver('texto', r.valores[opciones.titulo])}</b>{det && <small>{ver(det.tipo, r.valores[det.id])}</small>}</span>
              </article>
            ))}
            {citas.length > 8 && <p className="pl-mas">+{citas.length - 8} más</p>}
            {!citas.length && <p className="pl-mas">Libre</p>}
          </section>
        )
      })}
    </div>
  )
}

function Vencimientos({ seccion, campos, registros, opciones }) {
  const lim = opciones.dias || 30
  // Lo ya terminado (entregado, cancelado) no está "por vencer": se excluye por su estado.
  const vivos = opciones.estado && opciones.excluir ? registros.filter((r) => !opciones.excluir.includes(r.valores[opciones.estado])) : registros
  const conDia = vivos.filter((r) => r.valores[opciones.fecha]).map((r) => ({ r, d: diasHasta(r.valores[opciones.fecha]) })).sort((a, b) => a.d - b.d)
  const grupos = [
    { t: 'Vencidos', clase: 'alerta', c: '#f0587a', items: conDia.filter((x) => x.d < 0) },
    { t: 'Próximos 7 días', clase: 'aviso', c: '#f5a623', items: conDia.filter((x) => x.d >= 0 && x.d <= 7) },
    { t: `De 8 a ${lim} días`, clase: 'tranquilo', c: '#22d3a6', items: conDia.filter((x) => x.d > 7 && x.d <= lim) },
  ]
  if (!registros.length) return <Vacio seccion={seccion} />
  const det = opciones.detalle && campo(campos, opciones.detalle)
  return (
    <div className="pl-venc">
      {grupos.map((g, gi) => (
        <section key={g.t} className={`pl-venc-grupo ${g.clase}`} style={{ '--c': g.c, '--i': gi }}>
          <h3><span>{g.t}</span><i>{g.items.length}</i></h3>
          <ul>
            {g.items.slice(0, 8).map(({ r, d }, k) => (
              <li key={r.id} style={{ '--i': k }}>
                <span><b>{ver('texto', r.valores[opciones.titulo])}</b>{det && <small>{ver(det.tipo, r.valores[det.id])}</small>}</span>
                <em>{d < 0 ? `hace ${-d} d` : d === 0 ? 'hoy' : `en ${d} d`}</em>
              </li>
            ))}
            {g.items.length > 8 && <li className="pl-mas">+{g.items.length - 8} más</li>}
            {!g.items.length && <li className="pl-mas">Nada</li>}
          </ul>
        </section>
      ))}
    </div>
  )
}

function Grafica({ seccion, campos, registros, opciones }) {
  if (!registros.length) return <Vacio seccion={seccion} />
  const tipo = opciones.tipo || 'barras'
  if (tipo === 'linea') {
    const ahora = new Date()
    const meses = Array.from({ length: 12 }, (_, i) => new Date(ahora.getFullYear(), ahora.getMonth() - 11 + i, 1))
    const valores = meses.map((m) => registros.filter((r) => { const v = r.valores[opciones.fecha]; return v && Number(v.slice(0, 4)) === m.getFullYear() && Number(v.slice(5, 7)) === m.getMonth() + 1 }).length)
    const max = Math.max(1, ...valores)
    const pts = valores.map((v, i) => `${20 + i * 40},${150 - (v / max) * 120}`).join(' ')
    const gid = `pl-area-${seccion.id}`
    return (
      <figure className="pl-grafica pl-linea">
        <svg viewBox="0 0 480 180" role="img" aria-label={`Altas por mes en ${seccion.titulo}`}>
          <defs><linearGradient id={gid} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="var(--acento, #22d3a6)" stopOpacity=".35" /><stop offset="1" stopColor="var(--acento, #22d3a6)" stopOpacity="0" /></linearGradient></defs>
          <polygon className="pl-area" points={`20,150 ${pts} ${20 + 11 * 40},150`} fill={`url(#${gid})`} />
          <polyline points={pts} pathLength="1" fill="none" stroke="var(--acento, #22d3a6)" strokeWidth="3" strokeLinejoin="round" strokeLinecap="round" />
          {valores.map((v, i) => (
            <g key={i} className="pl-punto" style={{ '--i': i }}>
              <circle cx={20 + i * 40} cy={150 - (v / max) * 120} r="4" fill="var(--acento, #22d3a6)"><title>{`${MESES[meses[i].getMonth()]}: ${v}`}</title></circle>
              <text x={20 + i * 40} y="172" textAnchor="middle">{MESES[meses[i].getMonth()]}</text>
            </g>
          ))}
        </svg>
        <figcaption>Altas por mes · {campo(campos, opciones.fecha)?.nombre}</figcaption>
      </figure>
    )
  }
  const c = campo(campos, opciones.por)
  const datos = c.opciones.map((op, i) => ({ op, color: COLORES[i % COLORES.length],
    v: registros.filter((r) => r.valores[opciones.por] === op).reduce((s, r) => s + (opciones.suma ? Number(r.valores[opciones.suma]) || 0 : 1), 0) }))
  const total = datos.reduce((s, d) => s + d.v, 0) || 1
  const fmt = (v) => (opciones.suma ? ver('dinero', v) : v.toLocaleString('es'))
  if (tipo === 'dona') {
    let acum = 0
    return (
      <figure className="pl-grafica pl-dona">
        <svg viewBox="0 0 120 120" role="img" aria-label={`${seccion.titulo} por ${c.nombre.toLowerCase()}`}>
          {datos.map((d, i) => { const ini = acum; acum += d.v / total; return <circle key={d.op} r="45" cx="60" cy="60" fill="none" stroke={d.color} strokeWidth="18" pathLength="1" strokeDasharray={`${d.v / total} 1`} strokeDashoffset={-ini} transform="rotate(-90 60 60)" style={{ '--i': i, '--d': d.v / total }}><title>{`${d.op}: ${fmt(d.v)}`}</title></circle> })}
          <text x="60" y="66" textAnchor="middle" className="pl-dona-n"><Numero v={registros.length} /></text>
        </svg>
        <ul>{datos.map((d, i) => <li key={d.op} style={{ '--i': i }}><i style={{ background: d.color }} />{d.op}<b><Numero v={d.v} fmt={fmt} /></b></li>)}</ul>
      </figure>
    )
  }
  const max = Math.max(1, ...datos.map((d) => d.v))
  return (
    <figure className="pl-grafica pl-barras">
      {datos.map((d, i) => (
        <div key={d.op} style={{ '--i': i }}><span>{d.op}</span><i><b style={{ width: `${(d.v / max) * 100}%`, background: d.color, '--c': d.color }} /></i><em><Numero v={d.v} fmt={fmt} /></em></div>
      ))}
      <figcaption>{opciones.suma ? `${campo(campos, opciones.suma)?.nombre} por ${c.nombre.toLowerCase()}` : `Cantidad por ${c.nombre.toLowerCase()}`}</figcaption>
    </figure>
  )
}

const Feed = ({ datos }) => <ol className="mc-feed">{datos.eventos.map((e) => <li key={e.id}><span aria-hidden="true">{e.e}</span><b>{e.t}</b><small>{e.h}</small></li>)}</ol>

const Equipo = ({ datos }) => (
  <div className="mc-equipo">
    {datos.equipo.map((v, k) => (
      <div key={v} className="mc-persona"><span className="mc-av grande" style={{ background: COLORES[k % COLORES.length] }}>{v[0]}</span><b>{v}</b><small>{k === 0 ? 'Administración' : 'Ventas'}</small></div>
    ))}
    {datos.equipo.length === 1 && <div className="mc-persona invita"><span aria-hidden="true">＋</span><b>Invita a tu equipo</b><small>Reparte el trabajo cuando crezcas</small></div>}
  </div>
)

const Interruptores = ({ datos }) => (
  <ul className="mc-autos">
    {datos.automatizaciones.map((a) => (
      <li key={a.id} className={a.on ? 'on' : ''}>
        <div><span className="mc-pilar">{a.pilar}</span><b>{a.t}</b><small>{a.d}</small></div>
        <span role="switch" aria-checked={a.on} aria-label={a.t} className="mc-switch"><i /></span>
      </li>
    ))}
  </ul>
)

export const COMPONENTES = { tabla: Tabla, kpis: Kpis, tablero: Tablero, agenda: Agenda, vencimientos: Vencimientos, grafica: Grafica, feed: Feed, equipo: Equipo, interruptores: Interruptores }
