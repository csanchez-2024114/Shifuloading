import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import Logo from '../components/Logo'
import { CLAVE, PREGUNTAS, etiqueta, recomendar } from '../brief/preguntas'
import '../brief.css'

/* Cuestionario de bienvenida: una pregunta por pantalla, con emojis, tarjetas para tocar y transiciones suaves.
 * Guarda lo respondido en el navegador (más adelante se conecta al servidor). Atajos: Enter continúa, 1-9 elige, ← vuelve. */

const TOTAL = PREGUNTAS.length

const leer = () => {
  try { return JSON.parse(localStorage.getItem(CLAVE)) || null } catch { return null }
}
const guardar = (d) => { try { localStorage.setItem(CLAVE, JSON.stringify(d)) } catch { /* sin almacenamiento: se sigue sin guardar */ } }

const vacio = (v) => v === undefined || v === null || (typeof v === 'string' && !v.trim()) || (Array.isArray(v) && v.length === 0)

function valido(q, r) {
  if (!q.requerido) return true
  const v = r[q.id]
  if (q.tipo === 'texto') return typeof v === 'string' && v.trim().length >= 2
  if (q.tipo === 'ubicacion') return !vacio(v?.pais)
  return !vacio(v)
}

function Opcion({ op, n, activa, bloqueada, multiple, onClick }) {
  return (
    <button type="button" role={multiple ? 'checkbox' : 'radio'} aria-checked={activa} disabled={bloqueada}
      className={`op ${activa ? 'op-on' : ''} ${bloqueada ? 'op-off' : ''}`} onClick={onClick}>
      <span className="op-e" aria-hidden="true">{op.e}</span>
      <span className="op-t">{op.t}</span>
      {op.d && <small>{op.d}</small>}
      <i className="op-ok" aria-hidden="true">✓</i>
      {n <= 9 && <kbd aria-hidden="true">{n}</kbd>}
    </button>
  )
}

function Confeti() {
  const piezas = useMemo(() => Array.from({ length: 44 }, (_, i) => ({
    i, x: Math.random() * 100, d: 2.6 + Math.random() * 2.4, r: Math.random() * 720 - 360, t: Math.random() * 0.9,
    c: ['#22d3a6', '#7c5cff', '#ffffff', '#5b6bff', '#ffd27a'][i % 5], w: 6 + Math.random() * 6,
  })), [])
  return (
    <div className="confeti" aria-hidden="true">
      {piezas.map((p) => <span key={p.i} style={{ left: `${p.x}%`, background: p.c, width: p.w, height: p.w * 1.6, animationDuration: `${p.d}s`, animationDelay: `${p.t}s`, '--giro': `${p.r}deg` }} />)}
    </div>
  )
}

function Final({ resp, onEditar, onReiniciar }) {
  const recs = useMemo(() => recomendar(resp), [resp])
  const [aviso, setAviso] = useState('')
  const resumen = [
    resp.rubro && ['🛍️', etiqueta('rubro', resp.rubro)],
    resp.ubicacion?.pais && ['🌎', etiqueta('ubicacion', resp.ubicacion.pais)],
    ...(resp.canales || []).map((c) => ['📣', etiqueta('canales', c)]),
    ...(resp.objetivos || []).map((c) => ['🎯', etiqueta('objetivos', c)]),
  ].filter(Boolean)

  return (
    <section className="final entra-der">
      <Confeti />
      <div className="emoji" aria-hidden="true">🎉</div>
      <h1>¡Listo{resp.nombre ? `, ${resp.nombre}` : ''}! Ya conocemos tu negocio.</h1>
      <p className="sub">Con lo que nos contaste, este es tu <b>plan de arranque</b>. Lo puedes cambiar cuando quieras.</p>
      {resumen.length > 0 && <div className="resumen">{resumen.map(([e, t], k) => <span key={k}>{e} {t}</span>)}</div>}

      <ol className="recs">
        {recs.map((r, k) => (
          <li key={r.titulo} className="rec" style={{ animationDelay: `${0.25 + k * 0.12}s` }}>
            <span className="rec-e" aria-hidden="true">{r.emoji}</span>
            <div className="rec-cuerpo">
              <b>{r.titulo}</b>
              <p>{r.texto}</p>
              <small>✓ {r.porque}</small>
            </div>
            <button type="button" className="rec-btn" onClick={() => setAviso('Esta función se conectará cuando Shifu tenga su servidor. ¡Ya quedó anotada en tu plan!')}>{r.boton}</button>
          </li>
        ))}
      </ol>
      {aviso && <p className="aviso" role="status">💡 {aviso}</p>}

      <div className="acciones acciones-final">
        <Link to="/panel" className="btn-pildora btn-grande">Entrar a Shifu</Link>
        <button type="button" className="brief-atras" onClick={onEditar}>Cambiar mis respuestas</button>
        <button type="button" className="brief-atras" onClick={onReiniciar}>Empezar de nuevo</button>
      </div>
    </section>
  )
}

export default function BriefPage() {
  const guardado = useMemo(leer, [])
  const [idx, setIdx] = useState(guardado && !guardado.fin ? Math.min(guardado.idx || 0, TOTAL - 1) : 0)
  const [resp, setResp] = useState(guardado?.resp || {})
  const [fin, setFin] = useState(!!guardado?.fin)
  const [dir, setDir] = useState('der')
  const temporizador = useRef(null)
  const pantalla = useRef(null)

  const q = PREGUNTAS[idx]
  const pct = fin ? 100 : (idx / TOTAL) * 100

  useEffect(() => { guardar({ idx, resp, fin }) }, [idx, resp, fin])
  useEffect(() => () => clearTimeout(temporizador.current), [])
  useEffect(() => { pantalla.current?.focus({ preventScroll: true }) }, [idx, fin])

  const poner = (id, v) => setResp((r) => ({ ...r, [id]: v }))
  // Las actualizaciones que dependen del valor anterior van como función, para que dos toques seguidos no se pisen.
  const cambiar = (id, fn) => setResp((r) => ({ ...r, [id]: fn(r[id]) }))
  const ir = (n, d) => { clearTimeout(temporizador.current); setDir(d); setIdx(n) }
  const siguiente = () => { if (idx >= TOTAL - 1) { setDir('der'); setFin(true) } else ir(idx + 1, 'der') }
  const atras = () => { if (idx > 0) ir(idx - 1, 'izq') }
  const puede = valido(q, resp)

  const elegirUna = (v) => {
    poner(q.id, v)
    if (q.tipo === 'una') {
      clearTimeout(temporizador.current)
      temporizador.current = setTimeout(() => { if (idx >= TOTAL - 1) { setDir('der'); setFin(true) } else ir(idx + 1, 'der') }, 360)
    }
  }
  const alternar = (v) => cambiar(q.id, (prev) => {
    const act = prev || []
    if (act.includes(v)) return act.filter((x) => x !== v)
    if (q.max && act.length >= q.max) return act
    return [...act, v]
  })
  const ponerPais = (v) => cambiar(q.id, (prev) => ({ ...(prev || {}), pais: v }))
  const ponerCiudad = (v) => cambiar(q.id, (prev) => ({ ...(prev || {}), ciudad: v }))

  // Atajos de teclado
  useEffect(() => {
    if (fin) return undefined
    const f = (e) => {
      const escribiendo = ['INPUT', 'TEXTAREA'].includes(e.target.tagName)
      if (e.key === 'Enter') {
        if (e.target.tagName === 'TEXTAREA' && !(e.ctrlKey || e.metaKey)) return
        if (e.target.tagName === 'BUTTON' && !e.target.classList.contains('brief-seguir')) return
        e.preventDefault(); if (puede) siguiente()
      } else if (!escribiendo && e.key === 'ArrowLeft') { e.preventDefault(); atras() }
      else if (!escribiendo && q.opciones && /^[1-9]$/.test(e.key)) {
        const op = q.opciones[Number(e.key) - 1]
        if (op) { e.preventDefault(); if (q.tipo === 'varias') alternar(op.v); else if (q.tipo === 'ubicacion') ponerPais(op.v); else elegirUna(op.v) }
      }
    }
    window.addEventListener('keydown', f)
    return () => window.removeEventListener('keydown', f)
  })

  const titulo = typeof q.titulo === 'function' ? q.titulo(resp) : q.titulo
  const seleccion = resp[q.id]
  const hayMax = q.tipo === 'varias' && q.max && (seleccion || []).length >= q.max
  const vaVacia = vacio(q.tipo === 'ubicacion' ? seleccion?.pais : seleccion)
  const autoAvanza = q.tipo === 'una'

  return (
    <div className="brief">
      <div className="brief-fondo" aria-hidden="true"><i className="orbe o1" /><i className="orbe o2" /><i className="orbe o3" /></div>
      <div className="brief-prog" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(pct)}><i style={{ width: `${pct}%` }} /></div>

      <header className="brief-cab">
        <Link to="/" aria-label="Shifu"><Logo height={26} /></Link>
        {!fin && <span className="brief-paso" aria-live="polite">{idx + 1} de {TOTAL}</span>}
        {!fin && <Link to="/" className="brief-omitir">Omitir por ahora</Link>}
      </header>

      <main className="brief-main">
        {fin ? (
          <div ref={pantalla} tabIndex={-1} className="foco">
            <Final resp={resp} onEditar={() => { setFin(false); setDir('izq'); setIdx(0) }}
              onReiniciar={() => { setResp({}); setFin(false); setDir('izq'); setIdx(0) }} />
          </div>
        ) : (
          <section key={idx} ref={pantalla} tabIndex={-1} className={`pantalla foco entra-${dir}`} aria-labelledby="brief-titulo">
            <span className="chip-cap">{q.capitulo}</span>
            <div className="emoji" aria-hidden="true">{q.emoji}</div>
            <h1 id="brief-titulo">{titulo}</h1>
            <p className="sub">{q.sub}</p>

            {q.tipo === 'texto' && (
              <input className="campo" type="text" autoFocus maxLength={60} placeholder={q.placeholder} value={seleccion || ''} aria-label={q.capitulo}
                onChange={(e) => poner(q.id, e.target.value)} />
            )}

            {q.tipo === 'parrafo' && (
              <textarea className="campo campo-parrafo" autoFocus rows={3} maxLength={300} placeholder={q.placeholder} value={seleccion || ''}
                onChange={(e) => poner(q.id, e.target.value)} />
            )}

            {(q.tipo === 'una' || q.tipo === 'varias' || q.tipo === 'ubicacion') && (
              <div className={`ops ${q.opciones.length <= 3 ? 'ops-pocas' : ''}`} role={q.tipo === 'varias' ? 'group' : 'radiogroup'}>
                {q.opciones.map((op, k) => {
                  const activa = q.tipo === 'varias' ? (seleccion || []).includes(op.v) : q.tipo === 'ubicacion' ? seleccion?.pais === op.v : seleccion === op.v
                  return (
                    <Opcion key={op.v} op={op} n={k + 1} activa={activa} multiple={q.tipo === 'varias'}
                      bloqueada={hayMax && !activa}
                      onClick={() => (q.tipo === 'varias' ? alternar(op.v) : q.tipo === 'ubicacion' ? ponerPais(op.v) : elegirUna(op.v))} />
                  )
                })}
              </div>
            )}

            {q.tipo === 'ubicacion' && (
              <input className="campo campo-chico" type="text" maxLength={50} placeholder="Ciudad (opcional)" value={seleccion?.ciudad || ''} aria-label="Ciudad"
                onChange={(e) => ponerCiudad(e.target.value)} />
            )}

            {q.tipo === 'varias' && q.max && <p className="contador">{(seleccion || []).length} de {q.max} elegidas{hayMax ? ' · quita una para cambiar' : ''}</p>}

            <div className="acciones">
              {idx > 0 && <button type="button" className="brief-atras" onClick={atras}>← Atrás</button>}
              {autoAvanza ? (
                /* En las de una sola respuesta, tocar una tarjeta ya avanza: no hace falta botón, solo la salida de "omitir". */
                !q.requerido && <button type="button" className="brief-omitir-q" onClick={siguiente}>{idx === TOTAL - 1 ? 'Omitir y ver mi plan' : 'Omitir pregunta'}</button>
              ) : (
                <>
                  <button type="button" className="btn-pildora btn-grande brief-seguir" disabled={!puede} onClick={siguiente}>
                    {idx === TOTAL - 1 ? 'Ver mi plan' : !q.requerido && vaVacia ? 'Omitir' : 'Continuar'}
                  </button>
                  <span className="atajo">o presiona <kbd>Enter ↵</kbd></span>
                </>
              )}
            </div>
          </section>
        )}
      </main>
    </div>
  )
}
