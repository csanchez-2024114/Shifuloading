import { CLAVE_USUARIO, HAY_SERVIDOR } from './config'
import { ErrorApi, pedir, pedirArchivo, token } from './http'
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
  /** ¿Ya hay una cuenta con este correo? (primer paso del inicio de sesión; sin servidor no hay cuentas y se considera que no). */
  async correoExiste(correo) {
    if (!HAY_SERVIDOR) return false
    return !!(await pedir('POST', '/auth/email-exists', { email: correo }, { publico: true })).exists
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
  /** La siguiente pregunta del cuestionario, escrita por la IA según lo contestado: { modo, pregunta, rubro }. Sin servidor o sin IA, modo 'base' (siguen las preguntas fijas). */
  siguientePregunta: (datos) => (HAY_SERVIDOR ? pedir('POST', '/crm/siguiente-pregunta', datos) : Promise.resolve({ modo: 'base', pregunta: null, rubro: null })),

  contactosCrear: (filas, canal, texto) => (HAY_SERVIDOR ? pedir('POST', '/crm/contactos', { filas, canal, texto }) : simulado.crm.contactosCrear(filas, canal, texto)),
  contactosActualizar: (id, cambios) => (HAY_SERVIDOR ? pedir('PATCH', `/crm/contactos/${id}`, cambios) : simulado.crm.contactosActualizar(id, cambios)),
  contactosEliminar: (id) => (HAY_SERVIDOR ? pedir('DELETE', `/crm/contactos/${id}`) : simulado.crm.contactosEliminar(id)),
  /** Registros de una sección propia (los valores van por id de campo). */
  /** Importa varias filas (de un Excel, por ejemplo) a una sección: [{ idCampo: valor }]. Devuelve el CRM y `importacion: { agregadas, omitidas }`. */
  registrosImportar: (listaId, filas, lote) => (HAY_SERVIDOR ? pedir('POST', `/crm/listas/${listaId}/registros/lote`, { filas, lote }) : simulado.crm.sinServidor()),
  /** Quita una importación entera (todos sus registros). No se puede deshacer. */
  importacionQuitar: (listaId, loteId) => (HAY_SERVIDOR ? pedir('DELETE', `/crm/listas/${listaId}/importaciones/${loteId}`) : simulado.crm.sinServidor()),
  /** Quita TODO lo importado en una sección (lo escrito a mano se queda). No se puede deshacer. */
  importacionesQuitarTodas: (listaId) => (HAY_SERVIDOR ? pedir('DELETE', `/crm/listas/${listaId}/importaciones`) : simulado.crm.sinServidor()),
  /** Borra TODOS los registros de una sección (la sección y sus campos se quedan). No se puede deshacer. */
  registrosVaciar: (listaId) => (HAY_SERVIDOR ? pedir('DELETE', `/crm/listas/${listaId}/registros`) : simulado.crm.sinServidor()),
  registrosActualizar: (listaId, id, valores) => (HAY_SERVIDOR ? pedir('PATCH', `/crm/listas/${listaId}/registros/${id}`, { valores }) : simulado.crm.registrosActualizar(listaId, id, valores)),
  registrosCrear: (listaId, valores) => (HAY_SERVIDOR ? pedir('POST', `/crm/listas/${listaId}/registros`, { valores }) : simulado.crm.registrosCrear(listaId, valores)),
  registrosEliminar: (listaId, id) => (HAY_SERVIDOR ? pedir('DELETE', `/crm/listas/${listaId}/registros/${id}`) : simulado.crm.registrosEliminar(listaId, id)),
  tareasCrear: (t, vence, hora) => (HAY_SERVIDOR ? pedir('POST', '/crm/tareas', { t, ...(vence ? { vence } : {}), ...(hora ? { hora } : {}) }) : simulado.crm.tareasCrear(t)),
  /** Cambia el texto, la fecha ("" se la quita) o la hora de una tarea. */
  tareasActualizar: (id, cambios) => (HAY_SERVIDOR ? pedir('PATCH', `/crm/tareas/${id}`, cambios) : simulado.crm.tareasActualizar(id, cambios)),
  tareasMover: (id, destino) => (HAY_SERVIDOR ? pedir('PATCH', `/crm/tareas/${id}`, { columna: destino }) : simulado.crm.tareasMover(id, destino)),
  tareasEliminar: (id) => (HAY_SERVIDOR ? pedir('DELETE', `/crm/tareas/${id}`) : simulado.crm.tareasEliminar(id)),
  automatizacionFijar: (id, on) => (HAY_SERVIDOR ? pedir('PUT', `/crm/automatizaciones/${id}`, { on }) : simulado.crm.automatizacionFijar(id, on)),
  seccionRenombrar: (id, nombre, anterior) => (HAY_SERVIDOR ? pedir('PUT', `/crm/secciones/${id}`, { nombre }) : simulado.crm.seccionRenombrar(id, nombre, anterior)),
  /* Deshacer (D61, contratos §3). El CRM ya trae sus puntos en `crm.puntos`; esto los pide solos: { puntos: [{n, antesDe, hora, cambio}] }. */
  puntos: () => (HAY_SERVIDOR ? pedir('GET', '/crm/puntos') : simulado.crm.puntos()),
  /** Deshace el punto `n` (sin n, el último): solo lo que ese cambio tocó. Devuelve el CRM y `deshacer: { texto, deshechos }`. */
  deshacer: (n) => (HAY_SERVIDOR ? pedir('POST', '/crm/deshacer', n == null ? {} : { n }) : simulado.crm.deshacer(n)),
  /** Quita los registros de ejemplo (`ejemplo: true`) de todo el CRM; lo de la persona se queda. Se puede deshacer. */
  quitarEjemplos: () => (HAY_SERVIDOR ? pedir('POST', '/crm/registros/ejemplos/quitar', {}) : simulado.crm.quitarEjemplos()),
  /** El logo del negocio (`crm.marca.logo_id`): { id, imagen } con la imagen como data URL. El simulado no guarda logos. */
  logo: (id) => (HAY_SERVIDOR ? pedir('GET', `/crm/logo/${encodeURIComponent(id)}`) : Promise.reject(new ErrorApi(404, 'Ese logo no existe.'))),
  /** Un archivo que preparó Shifu por el chat (`descargas` de la respuesta): { blob, nombre }. Solo con servidor. */
  descarga: (id) => pedirArchivo(`/crm/descargas/${encodeURIComponent(id)}`),
  /** El CRM completo para bajar: formato `excel` o `respaldo` (JSON). Solo con servidor. */
  exportar: (formato) => pedirArchivo(`/crm/exportar?formato=${encodeURIComponent(formato)}`),
}

/** Los avisos de la persona (campana): los que dejan las automatizaciones y el resto de la plataforma. */
export const avisos = {
  listar: () => (HAY_SERVIDOR ? pedir('GET', '/me/notifications?limit=15') : Promise.resolve({ notifications: [], unread_count: 0 })),
  leer: (id) => (HAY_SERVIDOR ? pedir('PATCH', `/me/notifications/${id}/read`) : Promise.resolve()),
  leerTodos: () => (HAY_SERVIDOR ? pedir('PATCH', '/me/notifications/mark-all-read') : Promise.resolve()),
}

export const chat = {
  /** La conversación guardada en el servidor y, si hace rato que no hablan, un saludo que retoma lo último. */
  historial: () => (HAY_SERVIDOR ? pedir('GET', '/crm/chat/historial') : Promise.resolve({ mensajes: [], saludo: null })),
  /** Borra el historial y todo lo que Shifu recuerda de la persona. */
  olvidar: () => (HAY_SERVIDOR ? pedir('DELETE', '/crm/chat') : Promise.resolve()),
  /** Mensaje para Shifu. Devuelve { respuesta, crm, vista?, pendiente?, descargas? } (`descargas`: archivos que pidió, [{ id, nombre, formato }]); `pendiente` se reenvía en el siguiente mensaje para confirmar un borrado. */
  enviar: (texto, contexto) => (HAY_SERVIDOR ? pedir('POST', '/crm/chat', { texto, contexto }) : simulado.chat.enviar(texto, contexto)),
}
