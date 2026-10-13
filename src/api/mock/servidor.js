import { ErrorApi } from '../http'
import { borrar, guardar, leer } from './almacen'
import { responder } from './chat'
import { generar } from './datos'
import * as P from './pura'

/* Servidor simulado: responde igual que lo hará el servidor real (mismas funciones, mismas formas de respuesta),
 * pero guarda todo en el navegador. Se usa mientras no haya VITE_API_URL. */

const actual = () => {
  const s = leer()
  if (!s) throw new ErrorApi(404, 'Aún no tienes un CRM')
  return s
}
const cambiar = async (fn) => { const s = fn(actual()); guardar(s); return s }
const pausa = (ms) => new Promise((r) => setTimeout(r, ms))

export const auth = {
  /* El correo no existe todavía: se manda a crear su CRM. */
  continuarConCorreo: async () => ({ existe: false }),
  /* Sin servidor no hay cuentas: entrar siempre "funciona". */
  iniciarSesion: async () => ({ nombre: '', apellido: '', correo: '' }),
}

export const crm = {
  obtener: async () => leer(),
  crearDesdeBrief: async (brief) => { const s = generar(brief); guardar(s); return s },
  reiniciar: async () => { borrar() },
  /* Las secciones propias, los campos y las etapas propias necesitan el servidor (la IA decide la estructura). */
  sinServidor: async () => { throw new ErrorApi(501, 'Esto necesita el servidor de Shifu: conéctalo con VITE_API_URL.') },

  contactosCrear: (filas, canal, texto) => cambiar((s) => P.contactosCrear(s, filas, canal, texto)),
  contactosActualizar: (id, cambios) => cambiar((s) => P.contactosActualizar(s, id, cambios)),
  contactosEliminar: (id) => cambiar((s) => P.contactosEliminar(s, id)),
  tareasCrear: (t) => cambiar((s) => P.tareasCrear(s, t)),
  tareasMover: (id, destino) => cambiar((s) => P.tareasMover(s, id, destino)),
  tareasEliminar: (id) => cambiar((s) => P.tareasEliminar(s, id)),
  automatizacionFijar: (id, on) => cambiar((s) => P.automatizacionFijar(s, id, on)),
  seccionRenombrar: (id, nombre, anterior) => cambiar((s) => P.seccionRenombrar(s, id, nombre, anterior)),
}

export const chat = {
  enviar: async (texto, contexto) => {
    const sinTexto = !texto.trim()
    const r = sinTexto ? { crm: actual(), respuesta: '' } : responder(actual(), texto, contexto?.pendiente)
    // Sin la IA conectada no se puede leer la imagen: se recibe, se avisa y se actúa solo con lo que la persona escribió.
    if (contexto?.imagen) {
      const donde = contexto.seccion ? ` de “${contexto.seccion}”` : ''
      r.respuesta = sinTexto
        ? `📸 Recibí tu captura${donde}. ¿Qué quieres que haga con eso? Por ejemplo: “agrega una tarea para revisar esto”.`
        : `📸 Recibí tu captura${donde}. ${r.respuesta}`
    }
    guardar(r.crm)
    await pausa(550)
    return r
  },
}
