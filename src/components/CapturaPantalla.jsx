import { useEffect, useRef, useState } from 'react'

/* Captura de pantalla dentro de la propia página, para mandársela a Shifu junto con lo que se quiere hacer
 * (como cuando se toma una captura de algo y se dice "quiero esto de aquí").
 * Funciona sin permisos del navegador: la imagen se dibuja a partir de lo que hay en pantalla. */

const ANCHO_MAX = 1400

/** Dibuja la región `{ x, y, ancho, alto }` (en coordenadas de la ventana) y devuelve una imagen JPEG en texto (data URL). */
export async function capturarRegion(r) {
  const { default: html2canvas } = await import('html2canvas')
  const lienzo = await html2canvas(document.body, {
    x: r.x + window.scrollX, y: r.y + window.scrollY, width: r.ancho, height: r.alto,
    scale: Math.min(2, window.devicePixelRatio || 1), useCORS: true, logging: false,
    // El propio chat y el selector no salen en la captura: se quiere ver lo que hay debajo.
    ignoreElements: (el) => !!el.closest?.('.mc-chat, .mc-captura'),
    // La copia de la página reinicia las animaciones de entrada (y saldría transparente): se apagan solo en la copia.
    onclone: (doc) => {
      const estilo = doc.createElement('style')
      estilo.textContent = '*, *::before, *::after { animation: none !important; transition: none !important; }'
      doc.head.appendChild(estilo)
    },
  })
  let salida = lienzo
  if (lienzo.width > ANCHO_MAX) {
    salida = document.createElement('canvas')
    salida.width = ANCHO_MAX
    salida.height = Math.round((lienzo.height * ANCHO_MAX) / lienzo.width)
    salida.getContext('2d').drawImage(lienzo, 0, 0, salida.width, salida.height)
  }
  return { url: salida.toDataURL('image/jpeg', 0.88), ancho: salida.width, alto: salida.height }
}

/** Convierte una imagen pegada o subida (archivo) en el mismo formato que una captura. */
export function imagenDeArchivo(archivo) {
  return new Promise((resolver, rechazar) => {
    if (!archivo?.type?.startsWith('image/')) { rechazar(new Error('No es una imagen')); return }
    const lector = new FileReader()
    lector.onerror = () => rechazar(new Error('No se pudo leer'))
    lector.onload = () => {
      const img = new Image()
      img.onerror = () => rechazar(new Error('No se pudo abrir'))
      img.onload = () => {
        const f = Math.min(1, ANCHO_MAX / img.width)
        const c = document.createElement('canvas')
        c.width = Math.round(img.width * f); c.height = Math.round(img.height * f)
        c.getContext('2d').drawImage(img, 0, 0, c.width, c.height)
        resolver({ url: c.toDataURL('image/jpeg', 0.88), ancho: c.width, alto: c.height })
      }
      img.src = String(lector.result)
    }
    lector.readAsDataURL(archivo)
  })
}

/** Capa que cubre la página: se arrastra para elegir qué parte captura Shifu. Esc cancela; Enter captura toda la pantalla visible. */
export function SelectorCaptura({ onElegir, onCancelar }) {
  const [caja, setCaja] = useState(null)
  const inicio = useRef(null)
  const pantallaCompleta = () => onElegir({ x: 0, y: 0, ancho: window.innerWidth, alto: window.innerHeight })

  useEffect(() => {
    const f = (e) => {
      if (e.key === 'Escape') { e.preventDefault(); onCancelar() }
      else if (e.key === 'Enter') { e.preventDefault(); pantallaCompleta() }
    }
    window.addEventListener('keydown', f)
    return () => window.removeEventListener('keydown', f)
  })

  const rect = (a, b) => ({ x: Math.min(a.x, b.x), y: Math.min(a.y, b.y), ancho: Math.abs(a.x - b.x), alto: Math.abs(a.y - b.y) })
  const bajar = (e) => {
    if (e.target.closest('.mc-captura-barra')) return
    try { e.currentTarget.setPointerCapture(e.pointerId) } catch { /* sin puntero activo: se sigue con los eventos normales */ }
    inicio.current = { x: e.clientX, y: e.clientY }
    setCaja({ x: e.clientX, y: e.clientY, ancho: 0, alto: 0 })
  }
  const mover = (e) => { if (inicio.current) setCaja(rect(inicio.current, { x: e.clientX, y: e.clientY })) }
  const subir = (e) => {
    if (!inicio.current) return
    const r = rect(inicio.current, { x: e.clientX, y: e.clientY })
    inicio.current = null
    if (r.ancho < 16 || r.alto < 16) { setCaja(null); return } // un toque suelto no es una selección
    onElegir(r)
  }

  return (
    <div className="mc-captura" role="dialog" aria-modal="true" aria-label="Elegir qué parte de la pantalla capturar"
      onPointerDown={bajar} onPointerMove={mover} onPointerUp={subir} onPointerCancel={() => { inicio.current = null; setCaja(null) }}>
      {caja && caja.ancho > 0 && <div className="mc-captura-caja" style={{ left: caja.x, top: caja.y, width: caja.ancho, height: caja.alto }}><span>{Math.round(caja.ancho)} × {Math.round(caja.alto)}</span></div>}
      <div className="mc-captura-barra">
        <b>Arrastra para elegir qué quieres que vea Shifu</b>
        <button type="button" onClick={pantallaCompleta}>Toda la pantalla</button>
        <button type="button" className="sec" onClick={onCancelar}>Cancelar</button>
        <small>Esc cancela · Enter captura todo</small>
      </div>
    </div>
  )
}
