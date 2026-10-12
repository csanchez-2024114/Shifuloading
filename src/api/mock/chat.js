import { ETAPAS, IDS_SECCION, COLUMNAS, tituloSeccion } from '../../crm/secciones'
import * as P from './pura'

/* Cerebro del chat del servidor simulado: entiende frases sencillas en español para agregar, modificar y eliminar.
 * El servidor real lo reemplaza con la IA de Shifu; el contrato de entrada y salida (ver API.md) es el mismo. */

const norm = (s) => s.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').trim()
const capitaliza = (s) => s.trim().replace(/\s+/g, ' ').replace(/(^|\s)(\p{L})/gu, (_, a, b) => a + b.toUpperCase())

/** Devuelve { crm, respuesta, vista?, pendiente? }. `pendiente` es una confirmación que el cliente devuelve en el siguiente mensaje. */
export function responder(crm, crudo, pendiente) {
  let s = crm
  const texto = crudo.trim()
  const t = norm(texto)
  const rubro = s.brief?.rubro
  const titulo = (id) => tituloSeccion(rubro, id, s.secciones)
  const salida = (respuesta, extra = {}) => ({ crm: s, respuesta, ...extra })

  const buscarContacto = (q) => { const k = norm(q); return k ? s.contactos.find((c) => norm(c.n).includes(k)) : undefined }
  const buscarSeccion = (q) => { const k = norm(q); return k ? IDS_SECCION.find((id) => norm(titulo(id)).includes(k) || k.includes(norm(titulo(id)))) : undefined }
  const buscarEtapa = (q) => { const k = norm(q); return ETAPAS.find((e) => norm(e) === k || k.includes(norm(e).split(' ').pop())) }
  const buscarTarea = (q) => { const k = norm(q); for (const [col] of COLUMNAS) { const x = s.tareas[col].find((y) => norm(y.t).includes(k)); if (x) return x } return null }

  if (pendiente) {
    if (/^(si|claro|dale|confirmo|ok|adelante|borralo|eliminalo)/.test(t)) {
      if (pendiente.tipo === 'contacto') { const c = s.contactos.find((x) => x.id === pendiente.id); s = P.contactosEliminar(s, pendiente.id); return salida(`Listo, eliminé a ${c?.n || 'ese contacto'} de tu CRM.`) }
      const x = COLUMNAS.flatMap(([col]) => s.tareas[col]).find((y) => y.id === pendiente.id)
      s = P.tareasEliminar(s, pendiente.id)
      return salida(`Listo, eliminé la tarea “${x?.t || ''}”.`)
    }
    return salida('Perfecto, no borré nada. 👍')
  }

  if (/(import|excel|notas|csv|hoja de calculo|sheets|archivo)/.test(t)) return salida('Claro. Te llevé a “Importar datos”: pega ahí tus notas o las celdas de tu Excel y yo las ordeno como contactos.', { vista: 'importar' })

  let m = t.match(/^(activa|enciende|prende|desactiva|apaga)r?\s+(?:la\s+|el\s+|las\s+|los\s+)?(.+)$/)
  if (m) {
    const k = norm(m[2]).split(' ').filter((w) => w.length > 3)
    const a = s.automatizaciones.find((x) => k.some((w) => norm(x.t).includes(w.slice(0, 6))))
    if (!a) return salida(`No encontré esa automatización. Tienes: ${s.automatizaciones.map((x) => x.t.toLowerCase()).join(', ')}.`)
    const quiere = /^(activa|enciende|prende)/.test(m[1])
    s = P.automatizacionFijar(s, a.id, quiere)
    return salida(`${quiere ? 'Activé' : 'Apagué'} “${a.t}”.`, { vista: 'automatizaciones' })
  }

  m = texto.match(/^(?:renombra|renombrar|cambia(?:r)?(?:\s+el\s+nombre\s+de)?|mueve|pasa|modifica|actualiza|pon)\s+(?:la\s+secci[oó]n\s+|secci[oó]n\s+|la\s+etapa\s+de\s+|a\s+)?(.+?)\s+(?:a|por|como)\s+(.+)$/i)
  if (m) {
    const [, x, y] = m
    const sec = buscarSeccion(x)
    if (sec && !buscarContacto(x)) {
      const nuevo = capitaliza(y).slice(0, 28)
      s = P.seccionRenombrar(s, sec, nuevo, titulo(sec))
      return salida(`Hecho: ahora la sección se llama “${nuevo}”.`)
    }
    const c = buscarContacto(x)
    if (c) {
      const et = buscarEtapa(y)
      if (et) { s = P.contactosActualizar(s, c.id, { etapa: et, dias: 0 }, `${c.n} pasó a “${et}”`); return salida(`Listo: ${c.n} ahora está en “${et}”.`, { vista: 'contactos' }) }
      const nuevo = capitaliza(y).slice(0, 40)
      s = P.contactosActualizar(s, c.id, { n: nuevo }, `${c.n} ahora se llama ${nuevo}`)
      return salida(`Listo, cambié el nombre de ${c.n} a ${nuevo}.`, { vista: 'contactos' })
    }
    return salida(`No encontré “${x}” ni como sección ni como contacto. ¿Me das el nombre tal como aparece?`)
  }

  m = texto.match(/^(?:elimina(?:r)?|borra(?:r)?|quita(?:r)?|saca(?:r)?|remueve)\s+(?:a\s+|al\s+|el\s+|la\s+)?(.+)$/i)
  if (m) {
    const tarea = m[1].match(/^tarea\s*:?\s*(.+)$/i)
    if (tarea) {
      const x = buscarTarea(tarea[1])
      if (!x) return salida(`No encontré la tarea “${tarea[1]}”.`)
      return salida(`¿Seguro que quieres eliminar la tarea “${x.t}”? Responde “sí” para confirmar.`, { pendiente: { tipo: 'tarea', id: x.id } })
    }
    const c = buscarContacto(m[1].replace(/^(contacto|cliente|paciente|alumno|comprador|interesado|cuenta)\s+/i, ''))
    if (!c) return salida(`No encuentro a “${m[1]}”. Escríbelo como aparece en tu lista.`)
    return salida(`¿Seguro que quieres eliminar a ${c.n}? Responde “sí” para confirmar.`, { pendiente: { tipo: 'contacto', id: c.id } })
  }

  m = texto.match(/^(?:agrega(?:r)?|a[ñn]ade|a[ñn]adir|crea(?:r)?|registra(?:r)?|anota(?:r)?|suma(?:r)?|nuevo|nueva)\s+(.+)$/i)
  if (m) {
    const tarea = m[1].match(/^(?:la\s+|una\s+)?tarea\s*:?\s*(.+)$/i)
    if (tarea) {
      const nombre = tarea[1].trim().replace(/^./, (c) => c.toUpperCase()).slice(0, 60)
      s = P.tareasCrear(s, nombre)
      return salida(`Anoté la tarea “${nombre}” en “Por hacer”.`, { vista: 'desarrollo' })
    }
    const nombre = capitaliza(m[1].replace(/^(?:a\s+|al\s+|un\s+|una\s+|el\s+|la\s+)?(?:contacto|cliente|paciente|alumno|comprador|interesado|cuenta|prospecto)?\s*(?:llamad[oa]\s+)?/i, '')).slice(0, 40)
    if (nombre.length < 2) return salida('¿Cómo se llama? Por ejemplo: “Agrega a Laura Gómez”.')
    if (buscarContacto(nombre)?.n.toLowerCase() === nombre.toLowerCase()) return salida(`${nombre} ya está en tu lista.`)
    s = P.contactosCrear(s, [{ n: nombre }], 'Chat con Shifu')
    return salida(`Listo, agregué a ${nombre} en “${titulo('contactos')}”, en la etapa “Nuevo”.`, { vista: 'contactos' })
  }

  if (/^(hola|buenas|hey|ayuda|que puedes)/.test(t)) return salida('Puedo agregar contactos y tareas, cambiarlos de etapa o de nombre, renombrar secciones, activar automatizaciones y eliminar lo que ya no uses (siempre te pido confirmación).')
  return salida('Aún no entendí eso. Prueba con: “Agrega a Laura Gómez”, “Renombra Cobros a Facturación”, “Mueve a Ana Morales a Cliente”, “Activa los recordatorios” o “Elimina a Luis Pérez”.')
}
