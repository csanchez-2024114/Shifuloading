import { HAY_SERVIDOR } from './config'
import { ErrorApi, pedir, token } from './http'
import * as simulado from './mock/servidor'

/* Único punto por el que la interfaz habla con los datos. La interfaz nunca toca localStorage ni fetch para esto:
 * todo pasa por aquí. Cada función tiene dos caminos, el servidor real (rutas descritas en API.md) o el simulado.
 * Todas las funciones del CRM devuelven el CRM completo y actualizado, para que la pantalla solo lo reemplace. */

export { ErrorApi }

export const auth = {
  /** Primer paso del inicio de sesión. Devuelve { existe } y, si el correo ya tiene cuenta, { token }. */
  async continuarConCorreo(correo) {
    if (!HAY_SERVIDOR) return simulado.auth.continuarConCorreo(correo)
    const r = await pedir('POST', '/auth/correo', { correo })
    if (r?.token) token.guardar(r.token)
    return r
  },
  cerrarSesion() { token.borrar() },
}

export const crm = {
  /** El CRM de la persona, o null si todavía no creó uno. */
  async obtener() {
    if (!HAY_SERVIDOR) return simulado.crm.obtener()
    try { return await pedir('GET', '/crm') } catch (e) { if (e.estado === 404) return null; throw e }
  },
  /** Crea el CRM a partir de las respuestas del cuestionario. */
  crearDesdeBrief: (brief) => (HAY_SERVIDOR ? pedir('POST', '/crm', { brief }) : simulado.crm.crearDesdeBrief(brief)),
  reiniciar: () => (HAY_SERVIDOR ? pedir('DELETE', '/crm') : simulado.crm.reiniciar()),

  contactosCrear: (filas, canal, texto) => (HAY_SERVIDOR ? pedir('POST', '/crm/contactos', { filas, canal, texto }) : simulado.crm.contactosCrear(filas, canal, texto)),
  contactosActualizar: (id, cambios) => (HAY_SERVIDOR ? pedir('PATCH', `/crm/contactos/${id}`, cambios) : simulado.crm.contactosActualizar(id, cambios)),
  contactosEliminar: (id) => (HAY_SERVIDOR ? pedir('DELETE', `/crm/contactos/${id}`) : simulado.crm.contactosEliminar(id)),
  tareasCrear: (t) => (HAY_SERVIDOR ? pedir('POST', '/crm/tareas', { t }) : simulado.crm.tareasCrear(t)),
  tareasMover: (id, destino) => (HAY_SERVIDOR ? pedir('PATCH', `/crm/tareas/${id}`, { columna: destino }) : simulado.crm.tareasMover(id, destino)),
  tareasEliminar: (id) => (HAY_SERVIDOR ? pedir('DELETE', `/crm/tareas/${id}`) : simulado.crm.tareasEliminar(id)),
  automatizacionFijar: (id, on) => (HAY_SERVIDOR ? pedir('PUT', `/crm/automatizaciones/${id}`, { on }) : simulado.crm.automatizacionFijar(id, on)),
  seccionRenombrar: (id, nombre, anterior) => (HAY_SERVIDOR ? pedir('PUT', `/crm/secciones/${id}`, { nombre }) : simulado.crm.seccionRenombrar(id, nombre, anterior)),
}

export const chat = {
  /** Mensaje para Shifu. Devuelve { respuesta, crm, vista?, pendiente? }; `pendiente` se reenvía en el siguiente mensaje para confirmar un borrado. */
  enviar: (texto, contexto) => (HAY_SERVIDOR ? pedir('POST', '/crm/chat', { texto, contexto }) : simulado.chat.enviar(texto, contexto)),
}
