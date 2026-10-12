/* Operaciones sobre el CRM (agregar, cambiar, quitar). Son funciones puras: reciben el CRM y devuelven el CRM nuevo.
 * Las usan el servidor simulado y su chat; el servidor real hará lo mismo del lado del servidor. */

let n = Date.now()
export const nuevoId = () => { n += 1; return `m${n}` }

const registrar = (s, e, t) => ({ ...s, eventos: [{ id: nuevoId(), e, t, h: 'ahora' }, ...s.eventos].slice(0, 30) })

export function contactosCrear(s, filas, canal, texto) {
  const nuevos = filas.map((f) => ({ id: nuevoId(), n: f.n, det: f.det, canal: f.canal || canal, etapa: 'Nuevo', dueno: 'Tú', dias: 0 }))
  const t = texto || (nuevos.length === 1 ? `Agregaste a ${nuevos[0].n}` : `Agregaste ${nuevos.length} contactos`)
  return registrar({ ...s, contactos: [...nuevos, ...s.contactos], totalContactos: s.totalContactos + nuevos.length }, '➕', t)
}

export function contactosActualizar(s, id, cambios, texto) {
  const c = s.contactos.find((x) => x.id === id)
  if (!c) return s
  return registrar({ ...s, contactos: s.contactos.map((x) => (x.id === id ? { ...x, ...cambios } : x)) }, '🔁', texto || `Actualizaste a ${c.n}`)
}

export function contactosEliminar(s, id) {
  const c = s.contactos.find((x) => x.id === id)
  if (!c) return s
  return registrar({ ...s, contactos: s.contactos.filter((x) => x.id !== id), totalContactos: s.totalContactos - 1 }, '🗑️', `Eliminaste a ${c.n}`)
}

export function tareasCrear(s, t) {
  return registrar({ ...s, tareas: { ...s.tareas, porHacer: [...s.tareas.porHacer, { id: nuevoId(), t }] } }, '✅', `Agregaste la tarea “${t}”`)
}

export function tareasMover(s, id, destino) {
  for (const col of Object.keys(s.tareas)) {
    const x = s.tareas[col].find((y) => y.id === id)
    if (x && col !== destino) return { ...s, tareas: { ...s.tareas, [col]: s.tareas[col].filter((y) => y.id !== id), [destino]: [...s.tareas[destino], x] } }
  }
  return s
}

export function tareasEliminar(s, id) {
  for (const col of Object.keys(s.tareas)) {
    const x = s.tareas[col].find((y) => y.id === id)
    if (x) return registrar({ ...s, tareas: { ...s.tareas, [col]: s.tareas[col].filter((y) => y.id !== id) } }, '🗑️', `Eliminaste la tarea “${x.t}”`)
  }
  return s
}

export function automatizacionFijar(s, id, on) {
  const a = s.automatizaciones.find((x) => x.id === id)
  if (!a || a.on === on) return s
  return registrar({ ...s, automatizaciones: s.automatizaciones.map((x) => (x.id === id ? { ...x, on } : x)) }, on ? '⚡' : '⏸️', `${on ? 'Activaste' : 'Apagaste'}: ${a.t}`)
}

export function seccionRenombrar(s, id, nombre, anterior) {
  return registrar({ ...s, secciones: { ...s.secciones, [id]: nombre } }, '✏️', `Renombraste “${anterior}” a “${nombre}”`)
}
