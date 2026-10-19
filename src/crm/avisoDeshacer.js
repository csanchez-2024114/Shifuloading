/* Qué se le dice a la persona antes de borrar a mano (lista 40). Las rutas del servidor dejan un punto de deshacer en los dos
 * modos, pero solo el sistema de diseño (VITE_CRM_DISENO=1) tiene cómo usarlo: «Cambios» y «Deshacer» en el chat. En el modo
 * clásico no hay botón ni el chat sabe deshacer: decir «no se puede deshacer» negaba el punto guardado y decir «se puede»
 * prometería algo que esta pantalla no hace. Se dice exactamente lo que hay. */
export const DISENO = import.meta.env?.VITE_CRM_DISENO === '1'

export const avisoDeshacer = (diseno = DISENO) => (diseno ? 'Si te arrepientes, lo deshaces en «Cambios», en el chat.' : 'Desde esta pantalla no se puede deshacer.')
