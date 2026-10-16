/* Elegir piezas para editarlas con Shifu (D39), sin captura:
 * - PC: doble clic en un bloque del inicio o en una pestaña del menú → queda elegido y pasa al chat.
 * - Celular y tablet (táctil): mantener presionado un bloque entra en "modo selección" (como elegir fotos en la galería);
 *   cada toque suma o quita; la barra de abajo dice cuántos van y "Editar con Shifu" los pasa al chat.
 * Lo elegido viaja como `piezas` (el mismo formato que la captura: {tipo, id, nombre}), así el servidor y la IA ya lo
 * entienden. Se comunica con el chat por un evento del navegador ('lab-piezas'), sin acoplar componentes. */
import { useEffect, useRef, useState } from 'react'

const PRESION_MS = 480
const piezaDe = (el) => {
  if (el.dataset.bloque) return { tipo: 'bloque', id: el.dataset.bloque, nombre: el.querySelector('h2')?.textContent || '' }
  return { tipo: 'pestaña', id: el.dataset.seccion || '', nombre: el.textContent.trim() }
}
const SELECTOR = '.pl-inicio > [data-bloque], .mc-menu li button[data-seccion]'
/** Pasa piezas al chat (lo escucha ChatLab). */
export const mandarAlChat = (piezas) => window.dispatchEvent(new CustomEvent('lab-piezas', { detail: piezas }))

export function useSeleccion(raiz) {
  const [elegidas, setElegidas] = useState([]) // [{tipo, id, nombre}]
  const [modo, setModo] = useState(false) // modo selección táctil
  // La lista vive también en una referencia que se actualiza al instante: dos dobles clics seguidos no se pisan.
  const lista = useRef([]); const ref = useRef({ modo }); ref.current = { modo }
  const fijar = (l) => { lista.current = l; setElegidas(l) }
  const alternar = (p) => { const l = lista.current; fijar(l.some((x) => x.tipo === p.tipo && x.id === p.id) ? l.filter((x) => !(x.tipo === p.tipo && x.id === p.id)) : [...l, p]) }

  useEffect(() => {
    const el = raiz.current; if (!el) return undefined
    let timer = null, inicio = null, presionado = null
    const objetivo = (e) => e.target.closest?.(SELECTOR)
    // PC: doble clic → elegir y mandar al chat de una vez (sumándose a lo que ya estaba elegido).
    const doble = (e) => {
      const t = objetivo(e); if (!t || e.pointerType === 'touch') return
      e.preventDefault(); window.getSelection?.()?.removeAllRanges()
      const p = piezaDe(t); const ya = lista.current
      const nuevas = ya.some((x) => x.tipo === p.tipo && x.id === p.id) ? ya : [...ya, p]
      fijar(nuevas); mandarAlChat(nuevas)
    }
    // Táctil: mantener presionado entra al modo; en modo, cada toque suma o quita (y no abre nada).
    const baja = (e) => {
      if (e.pointerType === 'mouse') return
      const t = objetivo(e); if (!t) return
      inicio = { x: e.clientX, y: e.clientY }; presionado = t
      timer = setTimeout(() => { timer = null; navigator.vibrate?.(12); setModo(true); alternar(piezaDe(t)) }, PRESION_MS)
    }
    const mueve = (e) => { if (timer && inicio && Math.hypot(e.clientX - inicio.x, e.clientY - inicio.y) > 10) { clearTimeout(timer); timer = null } }
    const sube = () => { if (timer) { clearTimeout(timer); timer = null } }
    const clic = (e) => {
      if (!ref.current.modo) return
      const t = objetivo(e); if (!t) return // la barra y lo demás funcionan normal
      e.preventDefault(); e.stopPropagation()
      if (t && t !== presionado) alternar(piezaDe(t))
      presionado = null
    }
    const menu = (e) => { if (objetivo(e) && e.pointerType !== 'mouse') e.preventDefault() } // sin menú contextual al mantener presionado
    el.addEventListener('dblclick', doble); el.addEventListener('pointerdown', baja); el.addEventListener('pointermove', mueve)
    el.addEventListener('pointerup', sube); el.addEventListener('pointercancel', sube); el.addEventListener('click', clic, true); el.addEventListener('contextmenu', menu)
    return () => { el.removeEventListener('dblclick', doble); el.removeEventListener('pointerdown', baja); el.removeEventListener('pointermove', mueve); el.removeEventListener('pointerup', sube); el.removeEventListener('pointercancel', sube); el.removeEventListener('click', clic, true); el.removeEventListener('contextmenu', menu) }
  }, [raiz])

  // Marca visual de lo elegido (atributo en el DOM: no re-dibuja las piezas).
  useEffect(() => {
    const el = raiz.current; if (!el) return
    for (const n of el.querySelectorAll('[data-elegido]')) n.removeAttribute('data-elegido')
    for (const p of elegidas) {
      const n = p.tipo === 'bloque' ? el.querySelector(`[data-bloque="${CSS.escape(p.id)}"]`) : el.querySelector(`.mc-menu button[data-seccion="${CSS.escape(p.id)}"]`)
      n?.setAttribute('data-elegido', '')
    }
  })
  // Cuando el chat usa o descarta la selección, se limpia aquí también.
  useEffect(() => {
    const limpiar = () => { fijar([]); setModo(false) }
    window.addEventListener('lab-piezas-usadas', limpiar); return () => window.removeEventListener('lab-piezas-usadas', limpiar)
  }, [])

  const barra = modo ? (
    <div className="pl-sel-barra" role="toolbar" aria-label="Piezas elegidas">
      <span>{elegidas.length ? `${elegidas.length} elegid${elegidas.length === 1 ? 'a' : 'as'}` : 'Toca las piezas'}</span>
      <button type="button" onClick={() => { setModo(false); fijar([]) }}>Cancelar</button>
      <button type="button" className="si" disabled={!elegidas.length} onClick={() => { mandarAlChat(elegidas); setModo(false) }}>Editar con Shifu</button>
    </div>
  ) : null
  return { elegidas, modo, barra }
}
