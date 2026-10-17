/* Chat de Shifu en el laboratorio: el MISMO diseño que ChatShifu del CRM (CrmPage.jsx: burbuja, panel, mascota, cámara,
 * sugerencias), copiado aquí para no tocar el CRM base. La diferencia: habla con /api/lab/chat, que edita la pantalla
 * de inicio del laboratorio. Es la ÚNICA forma de cambiar el diseño: no hay botones manuales. */
import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { LuCamera, LuPaperclip, LuSend, LuX } from 'react-icons/lu'
import ShifuAvatar from '@base/components/ShifuAvatar'
import TextoChat from '@base/components/TextoChat'
import { capturarRegion, imagenDeArchivo, SelectorCaptura } from '@base/components/CapturaPantalla'
import { sugerenciasPara } from './sugerencias'
import { capturarRegionLab, piezasEnRegion } from './captura'
import { tarjetaToma } from './edicion.js'

let n = 0
/** Colores dominantes de una imagen, MEDIDOS (no adivinados): se agrupan los píxeles visibles y se devuelven los hex más presentes. */
function paletaDe(url) {
  return new Promise((ok) => {
    const img = new Image(); img.crossOrigin = 'anonymous'
    img.onload = () => {
      const c = document.createElement('canvas'); const w = 80, h = Math.max(1, Math.round(80 * img.height / img.width)); c.width = w; c.height = h
      const x = c.getContext('2d'); x.drawImage(img, 0, 0, w, h); const d = x.getImageData(0, 0, w, h).data
      const cub = {}
      for (let i = 0; i < d.length; i += 4) {
        if (d[i + 3] < 128) continue
        const [r, g, b] = [d[i], d[i + 1], d[i + 2]], max = Math.max(r, g, b), min = Math.min(r, g, b)
        if (max > 242 && min > 242) continue // casi blanco: fondo
        const k = `${r >> 4},${g >> 4},${b >> 4}`; (cub[k] ||= { n: 0, r: 0, g: 0, b: 0 }); cub[k].n++; cub[k].r += r; cub[k].g += g; cub[k].b += b
      }
      const hex = (v) => Math.round(v).toString(16).padStart(2, '0')
      ok(Object.values(cub).sort((a, b) => b.n - a.n).slice(0, 6).map((q) => `#${hex(q.r / q.n)}${hex(q.g / q.n)}${hex(q.b / q.n)}`))
    }
    img.onerror = () => ok([]); img.src = url
  })
}
const mensaje = (de, t, imagen) => ({ id: `m${++n}`, de, t, imagen })
const SUGERENCIAS = [
  ['Diseño', 'Haz la gráfica más chica y ponla a la derecha'],
  ['Vencimientos', 'Quita "De 8 a 30" y pon "De 1 a 45"'],
  ['Agregar', 'Agrega una dona por estado'],
  ['Marca', 'Pon mis colores: azul #1E40AF y naranja #F97316, letra Poppins'],
  ['Toma', 'Diséñame un inicio nuevo para controlar mis cobros'],
  ['Crear', 'Quiero llevar el inventario con cantidad, mínimo y proveedor'],
  ['Enlace', 'Toma los colores de mi web https://www.spotify.com'],
  ['Gráficas', '¿Qué gráficas puedo poner?'],
]

/** Guion de la demo del flujo completo (modo "Demo IA" del laboratorio): pedidos reales a la IA real, uno tras otro. */
export const GUION = [
  'Hola, ¿qué puedes hacer?',
  'Pon mis colores: azul #1E40AF y naranja #F97316, letra Poppins para todo',
  'Quiero llevar el inventario de productos con su cantidad, mínimo, costo y proveedor, y ver en el inicio cuáles se están acabando',
  'Agrega un embudo de los estados',
  'Haz la gráfica de embudo más chica y ponla a la derecha',
  'Pon un gráfico de velas japonesas',
  'Agrega un campo de cumpleaños a la primera sección',
  'Quita la sección de inventario',
]

/** Guion de la toma de diseño (demo=toma): pedir diseño → decir qué ver → cambiar algo → confirmar. */
export const GUION_TOMA = [
  'Diséñame un inicio nuevo para controlar mis cobros',
  'Quiero un resumen de pagos y una dona de los estados',
  'No, mejor barras en vez de dona',
  'Sí',
]

/** Fila de ideas que se desplaza: flechas ‹ ›, rueda del mouse (vertical → horizontal) y desvanecido en los bordes. */
function Sugerencias({ deshabilitado, onElegir, ideas = SUGERENCIAS }) {
  const fila = useRef(null)
  const [bordes, setBordes] = useState({ ini: true, fin: false })
  const medir = () => { const f = fila.current; if (f) setBordes({ ini: f.scrollLeft < 4, fin: f.scrollLeft + f.clientWidth >= f.scrollWidth - 4 }) }
  useEffect(() => { medir(); fila.current?.scrollTo({ left: 0 }) }, [ideas]) // eslint-disable-line react-hooks/exhaustive-deps
  const mover = (d) => { fila.current?.scrollBy({ left: d * 220 }); setTimeout(medir, 350) }
  return (
    <div className="lab-sug">
      <button type="button" onClick={() => mover(-1)} disabled={bordes.ini} aria-label="Ideas anteriores">‹</button>
      <div ref={fila} className="mc-chat-sug" aria-label="Ideas" onScroll={medir} onWheel={(e) => { if (Math.abs(e.deltaY) > Math.abs(e.deltaX)) { e.currentTarget.scrollLeft += e.deltaY } }}>
        {ideas.map(([p, s]) => <button key={s} type="button" disabled={deshabilitado} onClick={() => onElegir(s)}><em>{p}</em>{s}</button>)}
      </div>
      <button type="button" onClick={() => mover(1)} disabled={bordes.fin} aria-label="Más ideas">›</button>
    </div>
  )
}

export default function ChatLab({ tema, plantilla, estadoActual, onEstado, seccionActual, onAbierto, guion, contexto }) {
  const [abierto, setAbierto] = useState(true)
  useEffect(() => { onAbierto?.(abierto) }, [abierto]) // eslint-disable-line react-hooks/exhaustive-deps
  const [mensajes, setMensajes] = useState(() => [mensaje('shifu', `Hola 👋 Soy Shifu. Este es tu CRM: dime qué quieres ver distinto y lo cambio. Puedo agregar, quitar, agrandar, achicar o mover cualquier pieza, en el inicio o en cualquier pestaña.`)])
  const [escribiendo, setEscribiendo] = useState(false)
  const [txt, setTxt] = useState('')
  const [imagen, setImagen] = useState(null)
  const [eligiendo, setEligiendo] = useState(false)
  const [capturando, setCapturando] = useState(false)
  const [errorImg, setErrorImg] = useState('')
  const fin = useRef(null)
  // Siempre el estado MÁS RECIENTE de la pantalla (no el de cuando se armó este render): si no, un pedido que sale justo
  // después de otro (o en la demo) mandaría una foto vieja y borraría el cambio anterior.
  const estadoRef = useRef(estadoActual); estadoRef.current = estadoActual
  const campo = useRef(null)
  useEffect(() => { fin.current?.scrollIntoView?.({ block: 'end' }) }, [mensajes, escribiendo, abierto])
  // Demo: manda el siguiente pedido del guion cuando Shifu termina de contestar (con una pausa para ver el cambio).
  const [paso, setPaso] = useState(0)
  useEffect(() => {
    if (!guion || escribiendo || paso >= guion.length) return undefined
    const t = setTimeout(() => { setPaso((x) => x + 1); enviar(guion[paso]) }, paso === 0 ? 1500 : 4500)
    return () => clearTimeout(t)
  }, [guion, escribiendo, paso]) // eslint-disable-line react-hooks/exhaustive-deps

  const enviar = async (texto, img) => {
    const t = (texto || '').trim()
    if ((!t && !img) || escribiendo) return
    if (img && !img.url && !img.pdf && !img.piezas?.length) return
    setMensajes((l) => [...l, mensaje('yo', (img?.piezas?.length && !img.url ? `[${img.piezas.map((x) => x.nombre || x.tipo).join(', ')}] ` : '') + (t || (img?.pdf ? `📄 ${img.nombre}` : '')), img?.url)]); setTxt(''); setImagen(null); setErrorImg('')
    if (img?.piezas?.length) soltarPiezas()
    setEscribiendo(true)
    try {
      const historial = mensajes.slice(-12).filter((m) => m.t).map((m) => ({ de: m.de, t: m.t.slice(0, 500) }))
      const paleta = img?.url && !img?.piezas ? await paletaDe(img.url) : null // de una captura del propio CRM no se miden colores de marca
      const r = await fetch('/api/lab/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ plantilla: plantilla.id, estado: estadoRef.current(), texto: t || (img?.pdf ? 'Te paso este PDF.' : 'Te paso esta imagen.'), historial, imagen: img?.url || undefined, archivo: img?.pdf, paleta, seleccion: img?.piezas, seccion: seccionActual }) })
      const d = await r.json()
      if (!r.ok) throw new Error(d.error || r.status)
      if (d.estado) onEstado(d.estado)
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
    // Qué contenedores quedaron dentro del recuadro (con su id): se calcula ANTES de dibujar, con las posiciones reales.
    const piezas = piezasEnRegion(region)
    try { setImagen({ ...(await capturarRegionLab(region)), piezas }) } catch (e) { console.error('[captura]', e); setImagen({ url: null, piezas }); setErrorImg(piezas.length ? 'No pude dibujar la imagen, pero sé qué elegiste.' : 'No pude tomar la captura. Inténtalo de nuevo o pega una imagen.') }
    setCapturando(false); setTimeout(() => campo.current?.focus(), 0)
  }
  const pegar = async (e) => {
    const archivo = [...(e.clipboardData?.files || [])].find((f) => f.type.startsWith('image/'))
    if (!archivo) return
    e.preventDefault()
    await adjuntar(archivo)
  }
  // Un logo (SVG/PNG/WebP) viaja tal cual, con su transparencia; el resto se convierte como en el CRM base (JPG liviano).
  const adjuntar = async (archivo) => {
    try {
      if (archivo.type === 'application/pdf') {
        if (archivo.size > 8_000_000) { setErrorImg('El PDF pesa más de 8 MB.'); return }
        const url = await new Promise((ok, mal) => { const r = new FileReader(); r.onload = () => ok(String(r.result)); r.onerror = mal; r.readAsDataURL(archivo) })
        setImagen({ url: null, pdf: url, nombre: archivo.name }); setErrorImg(''); return
      }
      if (['image/svg+xml', 'image/png', 'image/webp'].includes(archivo.type) && archivo.size <= 1_500_000) {
        const url = await new Promise((ok, mal) => { const r = new FileReader(); r.onload = () => ok(String(r.result)); r.onerror = mal; r.readAsDataURL(archivo) })
        setImagen({ url })
      } else setImagen(await imagenDeArchivo(archivo))
      setErrorImg('')
    } catch { setErrorImg('No pude usar esa imagen.') }
  }
  const archivoRef = useRef(null)
  // Piezas elegidas con doble clic o manteniendo presionado (seleccion.jsx): llegan como si fueran de una captura, sin imagen.
  useEffect(() => {
    const llegan = (e) => { setImagen({ url: null, piezas: e.detail }); setErrorImg(''); setAbierto(true); setTimeout(() => campo.current?.focus(), 50) }
    window.addEventListener('lab-piezas', llegan); return () => window.removeEventListener('lab-piezas', llegan)
  }, [])
  const soltarPiezas = () => window.dispatchEvent(new Event('lab-piezas-usadas'))
  const ficha = estadoActual()?.toma?.activa ? tarjetaToma(plantilla, estadoActual()) : null

  return createPortal(
    <div className="mc-chat" data-tema={tema}>
      {abierto && (
        <section className="mc-chat-panel" aria-label="Chat con Shifu" hidden={eligiendo || capturando}>
          <header><ShifuAvatar size={34} /><div><b>Shifu</b><small>{guion ? `Demo: pedido ${Math.min(paso, guion.length)} de ${guion.length}` : 'Edita el diseño de tu inicio'}</small></div>
            <button type="button" onClick={() => setAbierto(false)} aria-label="Cerrar el chat"><LuX /></button></header>
          <div className="mc-chat-msgs" role="log" aria-live="polite">
            {mensajes.map((m) => (
              <div key={m.id} className={`cb ${m.de}`}>{m.de === 'shifu' && <ShifuAvatar size={26} />}
                <div className="cb-t">{m.imagen && <img className="cb-img" src={m.imagen} alt="Captura enviada a Shifu" />}{m.de === 'shifu' ? <TextoChat texto={m.t} /> : m.t}</div></div>
            ))}
            {escribiendo && <div className="cb shifu"><ShifuAvatar size={26} /><p className="puntos" aria-label="Shifu está escribiendo"><i /><i /><i /></p></div>}
            <div ref={fin} />
          </div>
          <Sugerencias deshabilitado={escribiendo} onElegir={(t) => enviar(t)} ideas={contexto ? sugerenciasPara({ ...contexto, turno: mensajes.length }) : SUGERENCIAS} />
          {(imagen || errorImg) && (
            <div className="mc-adjunto" role="status">
              {imagen?.url && <img src={imagen.url} alt="Captura lista para enviar" />}{imagen?.pdf && <span>📄 {imagen.nombre}</span>}{imagen?.piezas?.length > 0 && <span className="lab-piezas">Elegiste: {imagen.piezas.map((x) => <i key={`${x.tipo}${x.id}${x.nombre}`}>{x.nombre || x.tipo}</i>)}</span>}
              <span>{imagen?.piezas?.length ? 'Dile a Shifu qué hacer con lo que elegiste.' : imagen ? 'Captura lista. Cuéntale a Shifu qué quieres cambiar ahí.' : errorImg}</span>
              <button type="button" onClick={() => { if (imagen?.piezas?.length) soltarPiezas(); setImagen(null); setErrorImg('') }} aria-label="Quitar la captura"><LuX /></button>
            </div>
          )}
          {ficha && (
            <div className="mc-chat-ficha" role="status" aria-label="Ficha de diseño">
              <strong>Ficha de diseño</strong>
              <small>{ficha.fase === 'confirmando' ? 'Revisión' : ficha.fase === 'construida' ? 'Construyendo…' : 'En curso'}</small>
              <ul>{ficha.filas.map((r) => <li key={r.etiqueta} className={r.pendiente ? 'pend' : 'ok'}><span>{r.etiqueta}</span>{r.texto}</li>)}</ul>
              {ficha.notas.length && <p className="mc-chat-ficha-notas">Notas: {ficha.notas.slice(-2).join(' · ')}</p>}
            </div>
          )}
          <form onSubmit={(e) => { e.preventDefault(); enviar(txt, imagen) }}>
            <button type="button" className="mc-chat-cam" onClick={() => setEligiendo(true)} disabled={escribiendo} aria-label="Capturar una parte de la pantalla" title="Capturar una parte de la pantalla"><LuCamera /></button>
            <button type="button" className="mc-chat-cam" onClick={() => archivoRef.current?.click()} disabled={escribiendo} aria-label="Adjuntar una imagen o tu logo" title="Adjuntar una imagen o tu logo (SVG o PNG)"><LuPaperclip /></button>
            <input ref={archivoRef} type="file" accept="image/svg+xml,image/png,image/webp,image/jpeg,application/pdf" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) adjuntar(f); e.target.value = '' }} />
            <input ref={campo} value={txt} onChange={(e) => setTxt(e.target.value)} onPaste={pegar} placeholder={imagen ? 'Qué quieres cambiar aquí…' : 'Escribe, captura o pega una imagen…'} aria-label="Mensaje para Shifu" maxLength={2000} />
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
