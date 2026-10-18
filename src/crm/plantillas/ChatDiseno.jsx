/* Lo del sistema de diseño (D61) dentro del chat de Shifu de CrmPage, sobre el campo de texto:
 * - las piezas elegidas en el lienzo (van con el siguiente mensaje; las toma CrmPage con `tomarSeleccion`);
 * - «Quitar ejemplos» mientras el CRM tenga registros de ejemplo (D56: son datos, por eso se confirma);
 * - «Cambios»: los últimos puntos de deshacer (§3/§4: crm.puntos) con «Deshacer» en cada uno y «Deshacer lo último».
 * Todo cambio va por `aplicar` de CrmPage (setCrm + aviso si falla): aquí no se guarda nada por cuenta propia. */
import { useEffect, useMemo, useState } from 'react'
import { LuChevronDown, LuChevronUp, LuHistory, LuUndo2, LuX } from 'react-icons/lu'
import { crm as api } from '../../api'
import { soltarPiezas, usePiezas } from './seleccion'
import { contarEjemplos } from './desdeCrm'
import './chat-diseno.css'

const NOMBRE = { bloques: 'diseño', marca: 'marca', estructura: 'secciones', datos: 'registros' }
const A_MANO = 'A mano: '

/** La hora de un punto. El servidor la manda en UTC y a veces sin zona (Mongo): sin zona se lee como UTC, no como local. */
function cuando(hora, ahora = Date.now()) {
  if (!hora) return ''
  const t = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(hora) ? hora : `${hora}Z`)
  if (Number.isNaN(t.getTime())) return ''
  const min = Math.round((ahora - t.getTime()) / 60000)
  if (min < 1) return 'hace un momento'
  if (min < 60) return `hace ${min} min`
  const hh = t.toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit' })
  return new Date(ahora).toDateString() === t.toDateString() ? `hoy, ${hh}` : `${t.toLocaleDateString('es', { day: 'numeric', month: 'short' })}, ${hh}`
}
const texto = (p) => (p.antesDe?.startsWith(A_MANO) ? p.antesDe.slice(A_MANO.length) : p.antesDe) || 'Un cambio'
const origen = (p) => (p.antesDe?.startsWith(A_MANO) ? 'A mano' : 'Pedido a Shifu')

export default function ChatDiseno({ crm, aplicar }) {
  const piezas = usePiezas()
  // Los puntos vienen con el CRM (§4). Si una respuesta no los trae (el chat, por ejemplo), se piden solos.
  const [sueltos, setSueltos] = useState(null)
  useEffect(() => {
    if (crm.puntos) return undefined
    let vivo = true
    api.puntos().then((r) => { if (vivo) setSueltos(r.puntos || []) }).catch(() => { /* sin puntos: no se muestra la lista */ })
    return () => { vivo = false }
  }, [crm])
  const puntos = useMemo(() => [...(crm.puntos || sueltos || [])].sort((a, b) => b.n - a.n), [crm.puntos, sueltos])
  const ejemplos = useMemo(() => contarEjemplos(crm), [crm])

  const [abierta, setAbierta] = useState(false)
  const [ocupado, setOcupado] = useState(false)
  const [hecho, setHecho] = useState('') // lo que dijo el servidor al deshacer (qué volvió y qué se deshizo en cadena)
  const [confirmar, setConfirmar] = useState(false)
  useEffect(() => { if (!puntos.length) setAbierta(false) }, [puntos.length])
  useEffect(() => { if (!ejemplos) setConfirmar(false) }, [ejemplos])

  const deshacer = async (n) => {
    if (ocupado) return
    setOcupado(true)
    let dicho = ''
    const ok = await aplicar(async () => {
      const { deshacer: r, ...nuevo } = await api.deshacer(n)
      dicho = r?.texto || 'Listo, lo deshice.'
      return nuevo
    })
    setOcupado(false)
    if (ok) { setHecho(dicho); setAbierta(false) }
  }
  const quitarEjemplos = async () => {
    if (ocupado) return
    setOcupado(true)
    const ok = await aplicar(() => api.quitarEjemplos())
    setOcupado(false)
    setConfirmar(false)
    if (ok) setHecho(`Quité ${ejemplos} ${ejemplos === 1 ? 'registro' : 'registros'} de ejemplo. Si te arrepientes, lo deshaces en «Cambios».`)
  }

  const ultimo = puntos[0]
  return (
    <div className="mcd">
      {abierta && puntos.length > 0 && (
        <div className="mcd-lista" role="region" aria-label="Cambios que se pueden deshacer">
          <header><b>Cambios</b><small>Deshacer uno devuelve solo lo que ese cambio tocó.</small>
            <button type="button" onClick={() => setAbierta(false)} aria-label="Cerrar los cambios"><LuX /></button></header>
          <ol>
            {puntos.map((p) => (
              <li key={p.n}>
                <div><span className="mcd-que">{texto(p)}</span>
                  <small>{origen(p)} · {cuando(p.hora)}{p.cambio?.length ? ` · ${p.cambio.map((c) => NOMBRE[c] || c).join(', ')}` : ''}</small></div>
                <button type="button" disabled={ocupado} onClick={() => deshacer(p.n)} aria-label={`Deshacer: ${texto(p)}`}>Deshacer</button>
              </li>
            ))}
          </ol>
        </div>
      )}
      {hecho && (
        <div className="mcd-hecho" role="status"><LuUndo2 aria-hidden="true" /><span>{hecho}</span>
          <button type="button" onClick={() => setHecho('')} aria-label="Cerrar el aviso"><LuX /></button></div>
      )}
      {ejemplos > 0 && (
        <div className={`mcd-ejemplos${confirmar ? ' confirmando' : ''}`} role={confirmar ? 'alertdialog' : 'note'} aria-label="Datos de ejemplo">
          {confirmar
            ? <><span>¿Borro los {ejemplos} registros de ejemplo? Lo tuyo se queda, y se puede deshacer.</span>
                <button type="button" onClick={() => setConfirmar(false)} disabled={ocupado}>No</button>
                <button type="button" className="si" onClick={quitarEjemplos} disabled={ocupado}>Sí, quitar</button></>
            : <><span>Tu CRM tiene <b>{ejemplos} {ejemplos === 1 ? 'registro' : 'registros'} de ejemplo</b>.</span>
                <button type="button" onClick={() => setConfirmar(true)} disabled={ocupado}>Quitar ejemplos</button></>}
        </div>
      )}
      {piezas.length > 0 && (
        <div className="mc-adjunto mcd-piezas" role="status">
          <span className="lab-piezas">Elegiste: {piezas.map((x) => <i key={`${x.tipo}${x.id}`}>{x.nombre || x.tipo}</i>)}</span>
          <span>Dile a Shifu qué hacer con lo que elegiste.</span>
          <button type="button" onClick={soltarPiezas} aria-label="Quitar lo elegido"><LuX /></button>
        </div>
      )}
      {puntos.length > 0 && (
        <div className="mcd-barra">
          <button type="button" className="mcd-ver" onClick={() => setAbierta(!abierta)} aria-expanded={abierta}>
            <LuHistory aria-hidden="true" /> Cambios <em>{puntos.length}</em>{abierta ? <LuChevronDown aria-hidden="true" /> : <LuChevronUp aria-hidden="true" />}</button>
          <button type="button" className="mcd-ultimo" disabled={ocupado} onClick={() => deshacer()} title={`Deshacer: ${texto(ultimo)}`}>
            <LuUndo2 aria-hidden="true" /> Deshacer lo último</button>
        </div>
      )}
    </div>
  )
}
