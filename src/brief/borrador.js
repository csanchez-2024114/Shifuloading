import { CLAVE } from './preguntas'

/* Borrador del cuestionario: lo que la persona lleva contestado, para que pueda cerrar la página y seguir después.
 * Es un asunto de la pantalla (no del servidor): se guarda en el navegador. Al terminar, las respuestas viajan al servidor con
 * `crm.crearDesdeBrief` (ver src/api). Forma: { idx, resp, fin }. */

export const leerBorrador = () => {
  try { return JSON.parse(localStorage.getItem(CLAVE)) || null } catch { return null }
}
export const guardarBorrador = (d) => {
  try { localStorage.setItem(CLAVE, JSON.stringify(d)) } catch { /* sin almacenamiento: se sigue sin guardar */ }
}
export const borrarBorrador = () => {
  try { localStorage.removeItem(CLAVE) } catch { /* sin almacenamiento */ }
}
