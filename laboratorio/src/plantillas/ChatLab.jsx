/* Chat de Shifu en el laboratorio: el MISMO diseño que ChatShifu del CRM (CrmPage.jsx: burbuja, panel, mascota, cámara,
 * sugerencias), copiado aquí para no tocar el CRM base. La diferencia: habla con /api/lab/chat, que edita la pantalla
 * de inicio del laboratorio. Es la ÚNICA forma de cambiar el diseño: no hay botones manuales. */
import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { LuCamera, LuSend, LuX } from 'react-icons/lu'
import ShifuAvatar from '@base/components/ShifuAvatar'
import TextoChat from '@base/components/TextoChat'
import { capturarRegion, imagenDeArchivo, SelectorCaptura } from '@base/components/CapturaPantalla'

let n = 0
const mensaje = (de, t, imagen) => ({ id: `m${++n}`, de, t, imagen })
const SUGERENCIAS = [
  ['Diseño', 'Haz la gráfica más chica y ponla a la derecha'],
  ['Vencimientos', 'Quita "De 8 a 30" y pon "De 1 a 45"'],
  ['Agregar', 'Agrega una dona por estado'],
  ['Orden', 'Pon el resumen al final'],
]

export default function ChatLab({ tema, plantilla, estadoActual, onEstado, seccionActual, onAbierto }) {
  const [abierto, setAbierto] = useState(true)
  useEffect(() => { onAbierto?.(abierto) }, [abierto]) // eslint-disable-line react-hooks/exhaustive-deps
  const [mensajes, setMensajes] = useState(() => [mensaje('shifu', `Hola 👋 Soy Shifu. Esta es la pantalla de **${plantilla.nombre}**. Dime qué quieres ver distinto: quitar, agregar, agrandar, achicar o mover cualquier bloque.`)])
  const [escribiendo, setEscribiendo] = useState(false)
  const [txt, setTxt] = useState('')
  const [imagen, setImagen] = useState(null)
  const [eligiendo, setEligiendo] = useState(false)
  const [capturando, setCapturando] = useState(false)
  const [errorImg, setErrorImg] = useState('')
  const fin = useRef(null)
  const campo = useRef(null)
  useEffect(() => { fin.current?.scrollIntoView?.({ block: 'end' }) }, [mensajes, escribiendo, abierto])

  const enviar = async (texto, img) => {
    const t = (texto || '').trim()
    if ((!t && !img) || escribiendo) return
    setMensajes((l) => [...l, mensaje('yo', t, img?.url)]); setTxt(''); setImagen(null); setErrorImg('')
    setEscribiendo(true)
    try {
      const historial = mensajes.slice(-12).filter((m) => m.t).map((m) => ({ de: m.de, t: m.t.slice(0, 500) }))
      const r = await fetch('/api/lab/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ plantilla: plantilla.id, estado: estadoActual(), texto: t, historial, imagen: img?.url, seccion: seccionActual }) })
      const d = await r.json()
      if (!r.ok) throw new Error(d.error || r.status)
      if (d.cambios?.length) onEstado(d.estado)
      // Para revisar en el laboratorio: qué herramientas corrieron de verdad (lo que dice vs lo que hizo).
      console.info('[chat-lab]', { cambios: d.cambios, fallos: d.fallos })
      setMensajes((l) => [...l, mensaje('shifu', d.respuesta)])
    } catch {
      setMensajes((l) => [...l, mensaje('shifu', 'No pude conectarme. Revisa que el laboratorio esté corriendo e inténtalo de nuevo.')])
    } finally { setEscribiendo(false) }
  }
  const elegida = async (region) => {
    setEligiendo(false); setCapturando(true); setErrorImg('')
    await new Promise((r) => setTimeout(r, 60))
    try { setImagen(await capturarRegion(region)) } catch { setErrorImg('No pude tomar la captura. Inténtalo de nuevo o pega una imagen.') }
    setCapturando(false); setTimeout(() => campo.current?.focus(), 0)
  }
  const pegar = async (e) => {
    const archivo = [...(e.clipboardData?.files || [])].find((f) => f.type.startsWith('image/'))
    if (!archivo) return
    e.preventDefault()
    try { setImagen(await imagenDeArchivo(archivo)); setErrorImg('') } catch { setErrorImg('No pude usar esa imagen.') }
  }

  return createPortal(
    <div className="mc-chat" data-tema={tema}>
      {abierto && (
        <section className="mc-chat-panel" aria-label="Chat con Shifu" hidden={eligiendo || capturando}>
          <header><ShifuAvatar size={34} /><div><b>Shifu</b><small>Edita el diseño de tu inicio</small></div>
            <button type="button" onClick={() => setAbierto(false)} aria-label="Cerrar el chat"><LuX /></button></header>
          <div className="mc-chat-msgs" role="log" aria-live="polite">
            {mensajes.map((m) => (
              <div key={m.id} className={`cb ${m.de}`}>{m.de === 'shifu' && <ShifuAvatar size={26} />}
                <div className="cb-t">{m.imagen && <img className="cb-img" src={m.imagen} alt="Captura enviada a Shifu" />}{m.de === 'shifu' ? <TextoChat texto={m.t} /> : m.t}</div></div>
            ))}
            {escribiendo && <div className="cb shifu"><ShifuAvatar size={26} /><p className="puntos" aria-label="Shifu está escribiendo"><i /><i /><i /></p></div>}
            <div ref={fin} />
          </div>
          <div className="mc-chat-sug" aria-label="Ideas">
            {SUGERENCIAS.map(([p, s]) => <button key={s} type="button" disabled={escribiendo} onClick={() => enviar(s)}><em>{p}</em>{s}</button>)}
          </div>
          {(imagen || errorImg) && (
            <div className="mc-adjunto" role="status">
              {imagen && <img src={imagen.url} alt="Captura lista para enviar" />}
              <span>{imagen ? 'Captura lista. Cuéntale a Shifu qué quieres cambiar ahí.' : errorImg}</span>
              <button type="button" onClick={() => { setImagen(null); setErrorImg('') }} aria-label="Quitar la captura"><LuX /></button>
            </div>
          )}
          <form onSubmit={(e) => { e.preventDefault(); enviar(txt, imagen) }}>
            <button type="button" className="mc-chat-cam" onClick={() => setEligiendo(true)} disabled={escribiendo} aria-label="Capturar una parte de la pantalla" title="Capturar una parte de la pantalla"><LuCamera /></button>
            <input ref={campo} value={txt} onChange={(e) => setTxt(e.target.value)} onPaste={pegar} placeholder={imagen ? 'Qué quieres cambiar aquí…' : 'Escribe, captura o pega una imagen…'} aria-label="Mensaje para Shifu" maxLength={600} />
            <button type="submit" disabled={(!txt.trim() && !imagen) || escribiendo} aria-label="Enviar"><LuSend /></button>
          </form>
        </section>
      )}
      <button type="button" className={`mc-chat-btn ${abierto ? 'abierto' : ''}`} onClick={() => setAbierto(!abierto)} aria-expanded={abierto} aria-label={abierto ? 'Cerrar el chat con Shifu' : 'Abrir el chat con Shifu'} hidden={eligiendo || capturando}>
        {abierto ? <LuX /> : <><ShifuAvatar size={46} /><i className="punto" /></>}
      </button>
      {eligiendo && <SelectorCaptura onElegir={elegida} onCancelar={() => setEligiendo(false)} />}
      {capturando && <div className="mc-captura mc-captura-espera" role="status">Tomando la captura…</div>}
    </div>,
    document.body,
  )
}
