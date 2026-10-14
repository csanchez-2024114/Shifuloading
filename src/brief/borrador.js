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
/** El cuestionario YA terminado (o null). Un borrador a medias, o uno que quedó de otra persona, no sirve para crear un CRM. */
export const borradorTerminado = () => {
  const b = leerBorrador()
  return b && b.fin && b.resp ? b : null
}
export const borrarBorrador = () => {
  try { localStorage.removeItem(CLAVE) } catch { /* sin almacenamiento */ }
}
