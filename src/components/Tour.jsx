import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import ShifuAvatar from './ShifuAvatar'
import '../tour.css'

/* Recorrido guiado: Shifu ilumina una parte de la pantalla y explica para qué sirve. Cada paso es
 * { id, objetivo?, lado?, titulo, texto (JSX), boton?, mascota? }. `objetivo` es el valor de data-tour del elemento a iluminar;
 * un paso sin objetivo se muestra al centro. Los pasos cuyo objetivo no está en pantalla se saltan solos. */

const MARGEN = 16
const RELLENO = 8

/** Dónde poner la tarjeta, junto al elemento iluminado y siempre dentro de la pantalla. En pantallas chicas va abajo, como una hoja. */
function lugar(caja, lado, ancho, alto) {
  const vw = window.innerWidth
  const vh = window.innerHeight
  if (vw <= 700) return { left: 12, right: 12, bottom: 12 }
  if (!caja) return { left: Math.max(12, (vw - ancho) / 2), top: Math.max(12, (vh - alto) / 2) }
  let left
  let top
  if (lado === 'derecha') { left = caja.x + caja.w + RELLENO + MARGEN; top = caja.y + caja.h / 2 - alto / 2 }
  else if (lado === 'izquierda') { left = caja.x - RELLENO - MARGEN - ancho; top = caja.y + caja.h / 2 - alto / 2 }
  else if (lado === 'arriba') { left = caja.x + caja.w / 2 - ancho / 2; top = caja.y - RELLENO - MARGEN - alto }
  else { left = caja.x + caja.w / 2 - ancho / 2; top = caja.y + caja.h + RELLENO + MARGEN }
  return { left: Math.min(Math.max(12, left), vw - ancho - 12), top: Math.min(Math.max(12, top), vh - alto - 12) }
}

export default function Tour({ pasos: todos, onFin, tema }) {
  const [pasos, setPasos] = useState(null)
  const [i, setI] = useState(0)
  const [caja, setCaja] = useState(null)
  const [alto, setAlto] = useState(260)
  const tarjeta = useRef(null)
  const siguienteBtn = useRef(null)

  // Se conservan solo los pasos cuyo objetivo está en pantalla (por ejemplo, "Importar" solo existe dentro de una pestaña).
  // Se espera un instante para que la pantalla termine de dibujarse.
  useEffect(() => {
    const t = setTimeout(() => setPasos(todos.filter((p) => !p.objetivo || document.querySelector(`[data-tour="${p.objetivo}"]`))), 250)
    return () => clearTimeout(t)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const paso = pasos?.[i]
  const ultimo = pasos ? i === pasos.length - 1 : false

  // Medir el elemento iluminado (y volver a medir si se mueve o cambia el tamaño de la ventana).
  useEffect(() => {
    if (!paso) return undefined
    const el = paso.objetivo ? document.querySelector(`[data-tour="${paso.objetivo}"]`) : null
    if (!el) { setCaja(null); return undefined }
    el.scrollIntoView?.({ block: 'nearest', inline: 'nearest' })
    const medir = () => { const r = el.getBoundingClientRect(); setCaja({ x: r.left, y: r.top, w: r.width, h: r.height }) }
    medir()
    const t = setTimeout(medir, 300)
    window.addEventListener('resize', medir)
    window.addEventListener('scroll', medir, true)
    return () => { clearTimeout(t); window.removeEventListener('resize', medir); window.removeEventListener('scroll', medir, true) }
  }, [paso])

  useLayoutEffect(() => { if (tarjeta.current) setAlto(tarjeta.current.offsetHeight) }, [paso, caja])
  useEffect(() => { siguienteBtn.current?.focus({ preventScroll: true }) }, [paso])

  const siguiente = () => (ultimo ? onFin() : setI((n) => n + 1))
  const atras = () => setI((n) => Math.max(0, n - 1))
  useEffect(() => {
    const f = (e) => {
      if (e.key === 'Escape') { e.preventDefault(); onFin() }
      else if (e.key === 'ArrowRight') { e.preventDefault(); siguiente() }
      else if (e.key === 'ArrowLeft') { e.preventDefault(); atras() }
    }
    window.addEventListener('keydown', f)
    return () => window.removeEventListener('keydown', f)
  })

  const ancho = Math.min(paso?.mascota ? 440 : 420, window.innerWidth - 24)
  const estilo = useMemo(() => (paso ? lugar(caja, paso.lado, ancho, alto) : {}), [paso, caja, ancho, alto])
  if (!paso) return null

  // Va en la raíz de la página (no dentro del CRM) para quedar por encima de todo, incluido el botón de Shifu.
  return createPortal(
    <div className="tour-raiz" data-tema={tema}>
    <div className="tour-capa" role="dialog" aria-modal="true" aria-label="Recorrido de bienvenida">
      {caja
        ? <div className="tour-foco" style={{ left: caja.x - RELLENO, top: caja.y - RELLENO, width: caja.w + RELLENO * 2, height: caja.h + RELLENO * 2 }} aria-hidden="true" />
        : <div className="tour-velo" aria-hidden="true" />}
      <section ref={tarjeta} className={`tour-tarjeta ${paso.mascota ? 'tour-grande' : ''}`} style={{ ...estilo, width: ancho }} aria-live="polite">
        {paso.mascota
          ? <img className="tour-mascota" src="/img/shifu-cuerpo.webp" alt="Shifu" width="120" height="122" />
          : <header><ShifuAvatar size={38} /><span>Shifu te cuenta</span></header>}
        <h2>{paso.titulo}</h2>
        <div className="tour-texto">{paso.texto}</div>
        <footer>
          <div className="tour-puntos" aria-label={`Paso ${i + 1} de ${pasos.length}`}>{pasos.map((p, k) => <i key={p.id} className={k === i ? 'on' : k < i ? 'hecho' : ''} />)}</div>
          <div className="tour-botones">
            {!ultimo && <button type="button" className="tour-saltar" onClick={onFin}>Saltar</button>}
            {i > 0 && <button type="button" className="tour-atras" onClick={atras}>Atrás</button>}
            <button ref={siguienteBtn} type="button" className="tour-sig" onClick={siguiente}>{paso.boton || (ultimo ? '¡Empezar!' : 'Siguiente')}</button>
          </div>
        </footer>
      </section>
    </div>
    </div>,
    document.body,
  )
}
