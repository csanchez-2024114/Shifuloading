/* Dónde va la ventana del chat (lista 31, PLAN_MAESTRO §2 Pantalla): sigue siendo una ventana, pero no tapa la sección.
 * - «lado»: pegada a la derecha; la página se corre para dejarle su columna (por defecto).
 * - «libre»: donde la persona la soltó al arrastrarla por la cabecera. Siempre dentro de la pantalla.
 * Se recuerda en el navegador. Solo aplica en pantallas anchas (≥ ANCHO_VENTANA); en tablet angosta es una hoja abajo y en
 * celular su propia pantalla (chat-ventana.css). Funciones puras salvo leer/guardar. */

const CLAVE = 'shifu_chat_pos'
export const ANCHO_VENTANA = 980
export const AL_LADO = Object.freeze({ modo: 'lado' })
const IMAN = 72 // px: soltada así de cerca del borde derecho, vuelve a pegarse al lado
const MARGEN = 8

const entre = (v, min, max) => Math.min(Math.max(v, min), Math.max(min, max))

/** La posición guardada (o «lado» si no hay o no sirve). */
export function leerPos(almacen = globalThis.localStorage) {
  try {
    const p = JSON.parse(almacen?.getItem(CLAVE))
    return p?.modo === 'libre' && Number.isFinite(p.x) && Number.isFinite(p.y) ? { modo: 'libre', x: Math.round(p.x), y: Math.round(p.y) } : AL_LADO
  } catch { return AL_LADO }
}

export function guardarPos(pos, almacen = globalThis.localStorage) {
  try { almacen?.setItem(CLAVE, JSON.stringify(pos.modo === 'libre' ? { modo: 'libre', x: pos.x, y: pos.y } : { modo: 'lado' })) } catch { /* sin almacenamiento */ }
}

/** Una esquina (x, y) que deja la ventana entera dentro de la pantalla. */
export function dentro({ x, y }, { ancho, alto }, pantalla) {
  return { x: Math.round(entre(x, MARGEN, pantalla.ancho - ancho - MARGEN)), y: Math.round(entre(y, MARGEN, pantalla.alto - Math.min(alto, pantalla.alto - 2 * MARGEN) - MARGEN)) }
}

/** Dónde queda al soltarla: pegada al lado si quedó cerca del borde derecho; si no, libre y dentro de la pantalla. */
export function alSoltar(esquina, tamano, pantalla) {
  if (esquina.x + tamano.ancho >= pantalla.ancho - IMAN) return AL_LADO
  return { modo: 'libre', ...dentro(esquina, tamano, pantalla) }
}
