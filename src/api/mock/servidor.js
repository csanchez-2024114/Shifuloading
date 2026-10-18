import { ErrorApi } from '../http'
import { borrar, guardar, leer } from './almacen'
import { responder } from './chat'
import { generar } from './datos'
import * as P from './pura'
import * as R from './registros'

/* Servidor simulado: responde igual que lo hará el servidor real (mismas funciones, mismas formas de respuesta),
 * pero guarda todo en el navegador. Se usa mientras no haya VITE_API_URL. */

const actual = () => {
  const s = leer()
  if (!s) throw new ErrorApi(404, 'Aún no tienes un CRM')
  return s
}
const pausa = (ms) => new Promise((r) => setTimeout(r, ms))
// Sistema de diseño (D61): con VITE_CRM_DISENO=1 el CRM simulado trae los campos del esquema 2 y sus listas se pueden llenar a mano.
const DISENO = import.meta.env.VITE_CRM_DISENO === '1'
const conDiseno = async (s) => { if (!DISENO || !s || s.esquema === 2) return s; const x = (await import('./diseno.js')).conDiseno(s); guardar(x); return x }
// Puntos de deshacer (§3): con la bandera, cada cambio deja su punto y el CRM sale con `puntos` (§4). Sin la bandera, nada cambia.
const puntos = () => import('./puntos.js')
const conPuntos = async (s) => (DISENO && s ? { ...s, puntos: (await puntos()).vista() } : s)
/** Aplica un cambio al CRM guardado. `que` (texto, o función del CRM de antes que lo da) describe lo hecho a mano, como en las rutas del servidor. */
const cambiar = async (fn, que) => {
  const antes = actual()
  const s = fn(antes)
  guardar(s)
  if (!DISENO) return s
  if (que) (await puntos()).anotar(antes, s, `A mano: ${typeof que === 'function' ? que(antes) : que}`)
  return conPuntos(s)
}
const contacto = (id) => (s) => s.contactos.find((c) => c.id === id)?.n || 'un contacto'
const seccion = (id) => (s) => (s.listas || []).find((l) => l.id === id)?.nombre || 'una sección'
const tarea = (id) => (s) => Object.values(s.tareas || {}).flat().find((t) => t.id === id)?.t || 'una tarea'

export const auth = {
  /* El correo no existe todavía: se manda a crear su CRM. */
  continuarConCorreo: async () => ({ existe: false }),
  /* Sin servidor no hay cuentas: entrar siempre "funciona". */
  iniciarSesion: async () => ({ nombre: '', apellido: '', correo: '' }),
}

export const crm = {
  obtener: async () => (DISENO ? conPuntos(await conDiseno(leer())) : leer()),
  crearDesdeBrief: async (brief) => { const s = generar(brief); guardar(s); if (!DISENO) return s; (await puntos()).olvidar(); return conPuntos(await conDiseno(s)) },
  reiniciar: async () => { borrar(); if (DISENO) (await puntos()).olvidar() },
  /* Las secciones propias, los campos y las etapas propias necesitan el servidor (la IA decide la estructura). */
  sinServidor: async () => { throw new ErrorApi(501, 'Esto necesita el servidor de Shifu: conéctalo con VITE_API_URL.') },

  contactosCrear: (filas, canal, texto) => cambiar((s) => P.contactosCrear(s, filas, canal, texto), filas.length === 1 ? `agregó a ${filas[0].n}` : `agregó ${filas.length} contactos`),
  contactosActualizar: (id, cambios) => cambiar((s) => P.contactosActualizar(s, id, cambios), (s) => `editó a ${contacto(id)(s)}`),
  contactosEliminar: (id) => cambiar((s) => P.contactosEliminar(s, id), (s) => `eliminó a ${contacto(id)(s)}`),
  tareasCrear: (t) => cambiar((s) => P.tareasCrear(s, t), `agregó la tarea «${t}»`),
  tareasMover: (id, destino) => cambiar((s) => P.tareasMover(s, id, destino), (s) => `movió la tarea «${tarea(id)(s)}»`),
  tareasEliminar: (id) => cambiar((s) => P.tareasEliminar(s, id), (s) => `eliminó la tarea «${tarea(id)(s)}»`),
  automatizacionFijar: (id, on) => cambiar((s) => P.automatizacionFijar(s, id, on)),
  seccionRenombrar: (id, nombre, anterior) => cambiar((s) => P.seccionRenombrar(s, id, nombre, anterior), `renombró una sección a «${nombre}»`),
  registrosCrear: (listaId, valores) => (DISENO ? cambiar((s) => R.registroCrear(s, listaId, valores), (s) => `agregó un registro a ${seccion(listaId)(s)}`) : crm.sinServidor()),
  registrosActualizar: (listaId, id, valores) => (DISENO ? cambiar((s) => R.registroActualizar(s, listaId, id, valores), (s) => `editó un registro de ${seccion(listaId)(s)}`) : crm.sinServidor()),
  registrosEliminar: (listaId, id) => (DISENO ? cambiar((s) => R.registroEliminar(s, listaId, id), (s) => `eliminó un registro de ${seccion(listaId)(s)}`) : crm.sinServidor()),
  tareasActualizar: (id, cambios) => (DISENO ? cambiar((s) => R.tareasActualizar(s, id, cambios), (s) => `cambió la tarea «${tarea(id)(s)}»`) : crm.sinServidor()),
  // Deshacer y quitar ejemplos (§3): solo con la bandera, como las rutas /crm/puntos, /crm/deshacer y /crm/registros/ejemplos/quitar.
  puntos: async () => (DISENO ? { puntos: (await puntos()).vista() } : crm.sinServidor()),
  deshacer: async (n) => {
    if (!DISENO) return crm.sinServidor()
    const r = (await puntos()).deshacer(actual(), n)
    guardar(r.crm)
    return { ...(await conPuntos(r.crm)), deshacer: { texto: r.texto, deshechos: r.deshechos } }
  },
  quitarEjemplos: async () => (DISENO ? cambiar((await puntos()).quitarEjemplos, 'quitó los ejemplos') : crm.sinServidor()),
}

export const chat = {
  enviar: async (texto, contexto) => {
    const sinTexto = !texto.trim()
    const antes = actual()
    const r = sinTexto ? { crm: antes, respuesta: '' } : responder(antes, texto, contexto?.pendiente)
    // Sin la IA conectada no se puede leer la imagen: se recibe, se avisa y se actúa solo con lo que la persona escribió.
    if (contexto?.imagen) {
      const donde = contexto.seccion ? ` de “${contexto.seccion}”` : ''
      r.respuesta = sinTexto
        ? `📸 Recibí tu captura${donde}. ¿Qué quieres que haga con eso? Por ejemplo: “agrega una tarea para revisar esto”.`
        : `📸 Recibí tu captura${donde}. ${r.respuesta}`
    }
    guardar(r.crm)
    await pausa(550)
    if (!DISENO) return r
    // Lo que cambió el chat también deja su punto, con el pedido como «antes de» (como el agente del servidor).
    if (texto.trim()) (await puntos()).anotar(antes, r.crm, texto.trim())
    return { ...r, crm: await conPuntos(r.crm) }
  },
}
