import { CLAVE_USUARIO, HAY_SERVIDOR } from './config'
import { ErrorApi, pedir, token } from './http'
import * as simulado from './mock/servidor'

/* Único punto por el que la interfaz habla con los datos. La interfaz nunca toca localStorage ni fetch para esto:
 * todo pasa por aquí. Cada función tiene dos caminos, el servidor real (rutas descritas en API.md) o el simulado.
 * Todas las funciones del CRM devuelven el CRM completo y actualizado, para que la pantalla solo lo reemplace. */

export { ErrorApi, HAY_SERVIDOR }

const leerUsuario = () => { try { return JSON.parse(localStorage.getItem(CLAVE_USUARIO)) || null } catch { return null } }
const guardarUsuario = (u) => { try { localStorage.setItem(CLAVE_USUARIO, JSON.stringify(u)) } catch { /* sin almacenamiento */ } }

/** Guarda la sesión que devuelve el servidor al entrar o registrarse: { user, access_token, refresh_token }. */
function abrirSesion(r) {
  token.guardar({ acceso: r.access_token, refresco: r.refresh_token })
  guardarUsuario({ nombre: r.user?.name || '', apellido: r.user?.last_name || '', correo: r.user?.email || '' })
  return leerUsuario()
}

export const auth = {
  /** ¿Hay una sesión abierta? Sin servidor no hay cuentas, así que siempre se considera que sí. */
  haySesion: () => !HAY_SERVIDOR || !!token.acceso() || !!token.refresco(),
  /** La persona con sesión: { nombre, apellido, correo } o null. */
  usuario: leerUsuario,
  /** Entrar con correo y contraseña. */
  async iniciarSesion({ correo, clave }) {
    if (!HAY_SERVIDOR) return simulado.auth.iniciarSesion()
    return abrirSesion(await pedir('POST', '/auth/login', { email: correo, password: clave }, { publico: true }))
  },
  /** Crear la cuenta (queda con la sesión abierta). */
  async registrar({ nombre, apellido, correo, clave }) {
    if (!HAY_SERVIDOR) return simulado.auth.iniciarSesion()
    return abrirSesion(await pedir('POST', '/auth/register', { name: nombre, last_name: apellido, email: correo, password: clave }, { publico: true }))
  },
  /** Primer paso del inicio de sesión en el servidor simulado (que no tiene contraseñas). */
  continuarConCorreo: (correo) => simulado.auth.continuarConCorreo(correo),
  /** Cierra la sesión aquí y en el servidor (si el servidor falla, igual se cierra aquí). */
  async cerrarSesion() {
    const r = token.refresco()
    if (HAY_SERVIDOR && r) { try { await pedir('POST', '/auth/logout', { refresh_token: r }) } catch { /* ya se cierra igual */ } }
    token.borrar()
    try { localStorage.removeItem(CLAVE_USUARIO) } catch { /* sin almacenamiento */ }
  },
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
  /** Preguntas que la IA hace según lo que la persona ya contó de su negocio (sin servidor no hay: se sigue con las fijas). */
  seguimiento: (brief) => (HAY_SERVIDOR ? pedir('POST', '/crm/seguimiento', { brief }) : Promise.resolve({ preguntas: [], modo: 'base' })),

  contactosCrear: (filas, canal, texto) => (HAY_SERVIDOR ? pedir('POST', '/crm/contactos', { filas, canal, texto }) : simulado.crm.contactosCrear(filas, canal, texto)),
  contactosActualizar: (id, cambios) => (HAY_SERVIDOR ? pedir('PATCH', `/crm/contactos/${id}`, cambios) : simulado.crm.contactosActualizar(id, cambios)),
  contactosEliminar: (id) => (HAY_SERVIDOR ? pedir('DELETE', `/crm/contactos/${id}`) : simulado.crm.contactosEliminar(id)),
  /** Registros de una sección propia (los valores van por id de campo). */
  registrosCrear: (listaId, valores) => (HAY_SERVIDOR ? pedir('POST', `/crm/listas/${listaId}/registros`, { valores }) : simulado.crm.sinServidor()),
  registrosEliminar: (listaId, id) => (HAY_SERVIDOR ? pedir('DELETE', `/crm/listas/${listaId}/registros/${id}`) : simulado.crm.sinServidor()),
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
