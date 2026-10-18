/* Datos a mano de las secciones propias en el servidor simulado (solo con VITE_CRM_DISENO=1, D61): agregar, cambiar y
 * quitar registros de una lista y cambiar una tarea. Funciones puras como las de pura.js: reciben el CRM y devuelven el nuevo.
 * Validan lo mínimo (números en campos de número o dinero); la validación de verdad es la del servidor (estructura.py). */
import { ErrorApi } from '../http'
import { nuevoId } from './pura'

const registrar = (s, e, t) => ({ ...s, eventos: [{ id: nuevoId(), e, t, h: 'ahora' }, ...s.eventos].slice(0, 30) })
const listaDe = (s, id) => { const l = (s.listas || []).find((x) => x.id === id); if (!l) throw new ErrorApi(404, 'Esa sección ya no existe.'); return l }
const conLista = (s, l) => ({ ...s, listas: s.listas.map((x) => (x.id === l.id ? l : x)) })

/** El valor como se guarda según el tipo del campo; null = vacío (se quita). */
function aValor(campo, v) {
  if (v === undefined || v === null || String(v).trim() === '') return null
  if (['numero', 'dinero'].includes(campo.tipo)) {
    const n = Number(String(v).replace(/[^\d.,-]/g, '').replace(/,/g, ''))
    if (!Number.isFinite(n)) throw new ErrorApi(422, `«${campo.nombre}» debe ser un número.`)
    return n
  }
  if (['estado', 'lista'].includes(campo.tipo) && campo.opciones?.length && !campo.opciones.includes(String(v))) throw new ErrorApi(422, `«${campo.nombre}» debe ser una de: ${campo.opciones.join(', ')}.`)
  return String(v).trim()
}
function valoresDe(l, valores) {
  const out = {}
  for (const c of l.campos) if (c.id in valores) out[c.id] = aValor(c, valores[c.id])
  return out
}
const sinVacios = (o) => Object.fromEntries(Object.entries(o).filter(([, v]) => v !== null))
const resumen = (l, r) => String(l.campos.map((c) => r.valores[c.id]).find((v) => v !== undefined && v !== null && v !== '') ?? 'un registro')

export function registroCrear(s, listaId, valores) {
  const l = listaDe(s, listaId)
  const v = sinVacios(valoresDe(l, valores || {}))
  if (!Object.keys(v).length) throw new ErrorApi(422, 'Escribe al menos un valor.')
  const r = { id: nuevoId(), valores: v }
  return registrar(conLista(s, { ...l, registros: [...l.registros, r] }), '➕', `Agregaste “${resumen(l, r)}” a ${l.nombre}`)
}

export function registroActualizar(s, listaId, id, valores) {
  const l = listaDe(s, listaId)
  const r = l.registros.find((x) => x.id === id)
  if (!r) throw new ErrorApi(404, 'Ese registro ya no existe.')
  const nuevo = { ...r, valores: sinVacios({ ...r.valores, ...valoresDe(l, valores || {}) }) }
  return registrar(conLista(s, { ...l, registros: l.registros.map((x) => (x.id === id ? nuevo : x)) }), '🔁', `Cambiaste “${resumen(l, nuevo)}” en ${l.nombre}`)
}

export function registroEliminar(s, listaId, id) {
  const l = listaDe(s, listaId)
  const r = l.registros.find((x) => x.id === id)
  if (!r) return s
  return registrar(conLista(s, { ...l, registros: l.registros.filter((x) => x.id !== id) }), '🗑️', `Eliminaste “${resumen(l, r)}” de ${l.nombre}`)
}

/** Cambia el texto, la fecha ("" se la quita) o la hora de una tarea. */
export function tareasActualizar(s, id, cambios) {
  for (const col of Object.keys(s.tareas)) {
    const x = s.tareas[col].find((y) => y.id === id)
    if (!x) continue
    if ('t' in cambios && !String(cambios.t || '').trim()) throw new ErrorApi(422, 'Escribe qué hay que hacer.')
    const y = { ...x, ...('t' in cambios ? { t: String(cambios.t).trim() } : {}) }
    for (const k of ['vence', 'hora']) if (k in cambios) { if (cambios[k]) y[k] = cambios[k]; else delete y[k] }
    return registrar({ ...s, tareas: { ...s.tareas, [col]: s.tareas[col].map((z) => (z.id === id ? y : z)) } }, '🔁', `Cambiaste la tarea “${y.t}”`)
  }
  throw new ErrorApi(404, 'Esa tarea ya no existe.')
}
