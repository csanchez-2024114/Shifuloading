/* Catálogo cerrado de vistas de las plantillas (las mismas claves que `VISTAS` en validar.js).
 * Cada vista recibe { seccion, campos, registros, opciones, datos } y SOLO dibuja: nunca llama a la API y todo número
 * que muestra lo cuenta de los registros (nada escrito a mano). */
import { isoDia } from './datosEjemplo'

const MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
const DIAS = ['dom', 'lun', 'mar', 'mié', 'jue', 'vie', 'sáb']
const COLORES = ['#7c5cff', '#22d3a6', '#f5a623', '#f0587a', '#5b6bff', '#3fb8ff', '#b06cff']
const MAX_FILAS = 50
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
  if (!registros.length) return <Vacio seccion={seccion} />
  const filas = registros.slice(0, MAX_FILAS)
  return (
    <div className="pl-tabla" role="table" aria-label={seccion.titulo}>
      <div className="pl-tabla-fila pl-tabla-cab" role="row" style={{ '--n': campos.length }}>{campos.map((c) => <span key={c.id} role="columnheader">{c.nombre}</span>)}</div>
      {filas.map((r) => (
        <div key={r.id} className="pl-tabla-fila" role="row" style={{ '--n': campos.length }}>
          {campos.map((c) => (
            <span key={c.id} role="cell" data-etiqueta={c.nombre}>
              {c.tipo === 'estado' ? <em className="pl-pildora" style={{ '--c': COLORES[c.opciones.indexOf(r.valores[c.id]) % COLORES.length] }}>{ver(c.tipo, r.valores[c.id])}</em> : ver(c.tipo, r.valores[c.id])}
            </span>
          ))}
        </div>
      ))}
      {registros.length > MAX_FILAS && <p className="pl-mas">y {plural(registros.length - MAX_FILAS, 'registro más', 'registros más')}</p>}
    </div>
  )
}

function Kpis({ campos, registros, opciones = {} }) {
  const tarjetas = [{ t: 'En total', v: registros.length.toLocaleString('es') }]
  if (opciones.hoy) tarjetas.push({ t: 'Hoy', v: registros.filter((r) => r.valores[opciones.hoy] === hoyIso()).length })
  if (opciones.vencen) {
    const d = opciones.dias || 7
    const dias = registros.map((r) => r.valores[opciones.vencen]).filter(Boolean).map(diasHasta)
    tarjetas.push({ t: `Vencen en ${d} días`, v: dias.filter((x) => x >= 0 && x <= d).length, clase: 'aviso' })
    tarjetas.push({ t: 'Vencidas', v: dias.filter((x) => x < 0).length, clase: 'alerta' })
  }
  if (opciones.suma) tarjetas.push({ t: `Total ${campo(campos, opciones.suma)?.nombre.toLowerCase()}`, v: ver('dinero', registros.reduce((s, r) => s + (Number(r.valores[opciones.suma]) || 0), 0)) })
  if (opciones.por) {
    const c = campo(campos, opciones.por)
    for (const op of c.opciones) tarjetas.push({ t: op, v: registros.filter((r) => r.valores[opciones.por] === op).length })
  }
  return (
    <div className="pl-kpis">
      {tarjetas.map((k) => <div key={k.t} className={k.clase || ''}><small>{k.t}</small><strong>{k.v}</strong></div>)}
    </div>
  )
}

function Tablero({ seccion, campos, registros, opciones }) {
  const c = campo(campos, opciones.por)
  const tituloDe = (r) => ver('texto', r.valores[opciones.titulo] ?? Object.values(r.valores)[0])
  const det = opciones.detalle && campo(campos, opciones.detalle)
  return (
    <div className="pl-tablero" role="list" aria-label={`${seccion.titulo} por ${c.nombre.toLowerCase()}`}>
      {c.opciones.map((op, i) => {
        const de = registros.filter((r) => r.valores[opciones.por] === op)
        return (
          <section key={op} className="pl-col" role="listitem" style={{ '--c': COLORES[i % COLORES.length] }}>
            <h3><span>{op}</span><i>{de.length}</i></h3>
            {de.slice(0, MAX_TARJETAS).map((r) => (
              <article key={r.id} className="pl-tarjeta"><b>{tituloDe(r)}</b>{det && <small>{ver(det.tipo, r.valores[det.id])}</small>}</article>
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
          <section key={iso} className={`pl-dia${i === 0 ? ' hoy' : ''}`}>
            <h3><span>{i === 0 ? 'Hoy' : DIAS[d.getDay()]}</span> <b>{d.getDate()} {MESES[d.getMonth()]}</b><i>{citas.length || ''}</i></h3>
            {citas.slice(0, 8).map((r) => (
              <article key={r.id} className="pl-cita">
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
  const conDia = registros.filter((r) => r.valores[opciones.fecha]).map((r) => ({ r, d: diasHasta(r.valores[opciones.fecha]) })).sort((a, b) => a.d - b.d)
  const grupos = [
    { t: 'Vencidos', clase: 'alerta', items: conDia.filter((x) => x.d < 0) },
    { t: 'Próximos 7 días', clase: 'aviso', items: conDia.filter((x) => x.d >= 0 && x.d <= 7) },
    { t: `De 8 a ${lim} días`, clase: '', items: conDia.filter((x) => x.d > 7 && x.d <= lim) },
  ]
  if (!registros.length) return <Vacio seccion={seccion} />
  const det = opciones.detalle && campo(campos, opciones.detalle)
  return (
    <div className="pl-venc">
      {grupos.map((g) => (
        <section key={g.t} className={`pl-venc-grupo ${g.clase}`}>
          <h3>{g.t}<i>{g.items.length}</i></h3>
          <ul>
            {g.items.slice(0, 8).map(({ r, d }) => (
              <li key={r.id}>
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
    return (
      <figure className="pl-grafica">
        <svg viewBox="0 0 480 180" role="img" aria-label={`Altas por mes en ${seccion.titulo}`}>
          <polyline points={pts} fill="none" stroke="#22d3a6" strokeWidth="3" strokeLinejoin="round" />
          {valores.map((v, i) => <g key={i}><circle cx={20 + i * 40} cy={150 - (v / max) * 120} r="4" fill="#22d3a6" /><text x={20 + i * 40} y="172" textAnchor="middle">{MESES[meses[i].getMonth()]}</text></g>)}
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
          {datos.map((d) => { const ini = acum; acum += d.v / total; return <circle key={d.op} r="45" cx="60" cy="60" fill="none" stroke={d.color} strokeWidth="18" pathLength="1" strokeDasharray={`${d.v / total} 1`} strokeDashoffset={-ini} transform="rotate(-90 60 60)" /> })}
          <text x="60" y="66" textAnchor="middle" className="pl-dona-n">{registros.length}</text>
        </svg>
        <ul>{datos.map((d) => <li key={d.op}><i style={{ background: d.color }} />{d.op}<b>{fmt(d.v)}</b></li>)}</ul>
      </figure>
    )
  }
  const max = Math.max(1, ...datos.map((d) => d.v))
  return (
    <figure className="pl-grafica pl-barras">
      {datos.map((d) => (
        <div key={d.op}><span>{d.op}</span><i><b style={{ width: `${(d.v / max) * 100}%`, background: d.color }} /></i><em>{fmt(d.v)}</em></div>
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
