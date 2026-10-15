import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import Logo from '../components/Logo'
import { auth, crm as apiCrm } from '../api'
import { PREGUNTAS } from '../brief/preguntas'
import { guardarBorrador, leerBorrador } from '../brief/borrador'
import '../brief.css'

/* Cuestionario de bienvenida: una pregunta por pantalla, con emojis, tarjetas para tocar y transiciones suaves.
 * Guarda lo respondido en el navegador (más adelante se conecta al servidor). Atajos: Enter continúa, 1-9 elige, ← vuelve. */

/* Las preguntas fijas, con las que la IA agrega después de «dolor», cuando ya sabe de qué trata el negocio. */
const I_DOLOR = PREGUNTAS.findIndex((p) => p.id === 'dolor')
const construir = (extra) => [...PREGUNTAS.slice(0, I_DOLOR + 1), ...extra, ...PREGUNTAS.slice(I_DOLOR + 1)]
/* Si cambia algo de esto, las preguntas de la IA ya no corresponden y se piden de nuevo. */
const claveDe = (r) => JSON.stringify([r.rubro, r.que_vendes, r.dolor, r.problemas, r.objetivos, r.canales, r.ciclo, r.equipo, r.herramientas])
const adaptar = (p) => ({ id: p.id, capitulo: 'Para conocer tu negocio', emoji: p.emoji || '🧩', tipo: p.tipo, titulo: p.titulo, sub: p.sub, opciones: p.opciones || [], requerido: false })
const respuestaDe = (p, v) => {
  if (p.tipo === 'parrafo') return String(v || '').trim().slice(0, 300)
  const lista = Array.isArray(v) ? v : v ? [v] : []
  return lista.map((x) => p.opciones.find((o) => o.v === x)?.t).filter(Boolean).join(', ').slice(0, 300)
}

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

export default function BriefPage() {
  const guardado = useMemo(leerBorrador, [])
  const [extra, setExtra] = useState(() => guardado?.extra || [])
  const [extraDe, setExtraDe] = useState(() => guardado?.extraDe || '')
  const [pensando, setPensando] = useState(false)
  const lista = useMemo(() => construir(extra), [extra])
  const TOTAL = lista.length
  const [idx, setIdx] = useState(guardado && !guardado.fin ? Math.min(guardado.idx || 0, TOTAL - 1) : 0)
  const [resp, setResp] = useState(guardado?.resp || {})
  const [fin, setFin] = useState(false)
  const nav = useNavigate()
  const [dir, setDir] = useState('der')
  const temporizador = useRef(null)
  const pantalla = useRef(null)

  const q = lista[idx]
  const pct = fin ? 100 : (idx / TOTAL) * 100

  useEffect(() => { guardarBorrador({ idx, resp, fin, extra, extraDe }) }, [idx, resp, fin, extra, extraDe])
  // Al terminar, Shifu arma el CRM: se pasa a la pantalla de carga y de ahí al CRM. Con servidor y sin cuenta, antes se crea la cuenta.
  useEffect(() => { if (fin) nav(auth.haySesion() ? '/mi-crm' : '/registro', { state: { cargar: true } }) }, [fin, nav])
  useEffect(() => () => clearTimeout(temporizador.current), [])
  useEffect(() => { pantalla.current?.focus({ preventScroll: true }) }, [idx, fin])

  const poner = (id, v) => setResp((r) => ({ ...r, [id]: v }))
  // Las actualizaciones que dependen del valor anterior van como función, para que dos toques seguidos no se pisen.
  const cambiar = (id, fn) => setResp((r) => ({ ...r, [id]: fn(r[id]) }))
  const ir = (n, d) => { clearTimeout(temporizador.current); setDir(d); setIdx(n) }
  // Al terminar se guardan, con palabras, las respuestas a las preguntas que hizo la IA: con ellas se arma el CRM.
  const terminar = () => {
    setResp((r) => ({ ...r, seguimiento: extra.map((p) => ({ pregunta: p.titulo, respuesta: respuestaDe(p, r[p.id]) })).filter((s) => s.respuesta) }))
    setDir('der'); setFin(true)
  }
  // Con lo que ya contó (sobre todo qué vende), la IA escribe las preguntas propias de ese negocio. Si tarda o falla, se sigue con las fijas.
  const pedirSeguimiento = async () => {
    setPensando(true)
    const clave = claveDe(resp)
    let preguntas = []
    try {
      const r = await Promise.race([apiCrm.seguimiento(resp), new Promise((_, no) => setTimeout(() => no(new Error('tarde')), 20000))])
      preguntas = (r?.preguntas || []).map(adaptar)
    } catch { /* sin preguntas extra */ }
    setExtra(preguntas); setExtraDe(clave); setPensando(false); ir(idx + 1, 'der')
  }
  const siguiente = () => {
    if (pensando) return
    if (q.id === 'dolor' && claveDe(resp) !== extraDe) { pedirSeguimiento(); return }
    if (idx >= TOTAL - 1) terminar(); else ir(idx + 1, 'der')
  }
  const atras = () => { if (idx > 0) ir(idx - 1, 'izq') }
  const puede = valido(q, resp)

  const elegirUna = (v) => {
    poner(q.id, v)
    if (q.tipo === 'una') {
      clearTimeout(temporizador.current)
      temporizador.current = setTimeout(() => { if (idx >= TOTAL - 1) terminar(); else ir(idx + 1, 'der') }, 360)
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

  // Quien ya terminó el cuestionario va directo a su CRM; para rehacerlo está "Repetir cuestionario" dentro del CRM.
  if (guardado?.fin && !fin) return <Navigate to="/mi-crm" replace />

  return (
    <div className="brief">
      <div className="brief-fondo" aria-hidden="true"><i className="orbe o1" /><i className="orbe o2" /><i className="orbe o3" /></div>
      <div className="brief-prog" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(pct)}><i style={{ width: `${pct}%` }} /></div>

      <header className="brief-cab">
        <Link to="/" aria-label="Shifu"><Logo height={26} color="#14211d" /></Link>
        {!fin && <span className="brief-paso" aria-live="polite">{idx + 1} de {TOTAL}</span>}
      </header>

      <main className="brief-main">
        {!fin && pensando && (
          <section className="pantalla foco entra-der brief-pensando" role="status" aria-live="polite">
            <div className="emoji" aria-hidden="true">✨</div>
            <h1>Shifu está pensando qué más preguntarte</h1>
            <p className="sub">Para armar un CRM distinto al de cualquier otro negocio, quiere conocer mejor el tuyo.</p>
            <p className="brief-puntos" aria-hidden="true"><i /><i /><i /></p>
          </section>
        )}
        {!fin && !pensando && (
          <section key={idx} ref={pantalla} tabIndex={-1} className={`pantalla foco entra-${dir}`} aria-labelledby="brief-titulo">
            <span className="chip-cap">{q.capitulo}</span>
            {q.id === 'nombre'
              ? <img className="emoji emoji-mascota" src="/img/shifu-cuerpo.webp" alt="Shifu te da la bienvenida" width="140" height="142" />
              : <div className="emoji" aria-hidden="true">{q.emoji}</div>}
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
                !q.requerido && <button type="button" className="brief-omitir-q" onClick={siguiente}>{idx === TOTAL - 1 ? 'Omitir y crear mi CRM' : 'Omitir pregunta'}</button>
              ) : (
                <>
                  <button type="button" className="btn-pildora btn-grande brief-seguir" disabled={!puede} onClick={siguiente}>
                    {idx === TOTAL - 1 ? 'Crear mi CRM' : !q.requerido && vaVacia ? 'Omitir' : 'Continuar'}
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
