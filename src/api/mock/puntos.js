/* Puntos de deshacer del servidor simulado (D61, contratos §3), solo con VITE_CRM_DISENO=1 y sin servidor: cada cambio que
 * hace la persona (a mano o por el chat simulado) deja un punto con la foto de ANTES de solo lo que cambió, y «deshacer»
 * devuelve solo eso. Imita a `puntos.py` (frente D): selectivo por categoría (en el simulado: «estructura» y «datos», por
 * sección), los últimos 30 y en cadena si un pedido posterior tocó lo mismo (eso se dice). Lo que NO imita: las 3 vías de
 * `revertirDatos` (aquí una sección vuelve entera a su foto, por eso se deshace en cadena todo lo que la tocó después).
 * Se carga aparte (import dinámico) y guarda sus fotos en el navegador, junto al CRM simulado. */
import { ErrorApi } from '../http'
import { nuevoId } from './pura'

const CLAVE = 'shifu_crm_puntos'
const MAX = 30
const NOMBRE = { bloques: 'los bloques del inicio', marca: 'los colores y la marca', estructura: 'las secciones y campos', datos: 'los registros' }

const leer = () => { try { return JSON.parse(localStorage.getItem(CLAVE)) || { n: 0, puntos: [] } } catch { return { n: 0, puntos: [] } } }
const guardar = (x) => { try { localStorage.setItem(CLAVE, JSON.stringify(x)) } catch { /* sin almacenamiento */ } }
export const olvidar = () => { try { localStorage.removeItem(CLAVE) } catch { /* sin almacenamiento */ } }

const igual = (a, b) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null)
const SIN_REGISTROS = ({ registros: _r, importaciones: _i, ...meta }) => meta

/** Los registros de cada sección como se guardan en el simulado: contactos, tareas (por columna) y cada lista. */
function datosDe(s) {
  const out = { contactos: { contactos: s.contactos || [], totalContactos: s.totalContactos ?? 0 }, desarrollo: s.tareas || {} }
  for (const l of s.listas || []) out[l.id] = { registros: l.registros || [], importaciones: l.importaciones || [] }
  return out
}
const estructuraDe = (s) => ({ secciones: s.secciones || {}, ocultas: s.ocultas || [], etapas: s.etapas ?? null, camposContacto: s.camposContacto ?? null, listas: (s.listas || []).map(SIN_REGISTROS) })

/** Los puntos para la pantalla (§4: los últimos 30, sin foto). */
export const vista = () => leer().puntos.map(({ foto: _f, ...p }) => p)

/** Mide qué cambió de `antes` a `despues` y, si algo cambió, guarda el punto con la foto de antes de solo eso. */
export function anotar(antes, despues, texto) {
  if (!antes || !despues || antes === despues) return
  const foto = {}
  const cambio = []
  if (!igual(estructuraDe(antes), estructuraDe(despues))) { foto.estructura = estructuraDe(antes); cambio.push('estructura') }
  const a = datosDe(antes), d = datosDe(despues)
  const datos = {}
  for (const sec of new Set([...Object.keys(a), ...Object.keys(d)])) if (!igual(a[sec], d[sec])) datos[sec] = a[sec] ?? null
  if (Object.keys(datos).length) { foto.datos = datos; cambio.push('datos') }
  if (!cambio.length) return
  const x = leer()
  x.n += 1
  x.puntos = [...x.puntos, { n: x.n, antesDe: String(texto || 'un cambio').slice(0, 80), hora: new Date().toISOString(), cambio, foto }].slice(-MAX)
  guardar(x)
}

/** Lo que toca un punto: sus categorías y, en datos, cada sección. */
const cosas = (p) => [...p.cambio.filter((c) => c !== 'datos'), ...Object.keys(p.foto.datos || {}).map((s) => `datos:${s}`)]

function poner(s, cosa, foto) {
  if (cosa === 'estructura') {
    const e = foto.estructura
    const regs = new Map((s.listas || []).map((l) => [l.id, { registros: l.registros, importaciones: l.importaciones }]))
    return { ...s, secciones: e.secciones, ocultas: e.ocultas, ...(e.etapas ? { etapas: e.etapas } : {}), ...(e.camposContacto ? { camposContacto: e.camposContacto } : {}),
      listas: e.listas.map((m) => ({ ...m, ...(regs.get(m.id) || { registros: [], importaciones: [] }) })) }
  }
  const sec = cosa.slice('datos:'.length)
  const v = foto.datos[sec]
  if (sec === 'contactos') return { ...s, contactos: v?.contactos || [], totalContactos: v?.totalContactos ?? 0 }
  if (sec === 'desarrollo') return { ...s, tareas: v || { porHacer: [], enCurso: [], hecho: [] } }
  if (!(s.listas || []).some((l) => l.id === sec)) return s // la sección ya no está (y su estructura no vuelve con este punto)
  return { ...s, listas: s.listas.map((l) => (l.id === sec ? { ...l, registros: v?.registros || [], importaciones: v?.importaciones || [] } : l)) }
}

/** Deshace el punto `n` (o el último). Devuelve { crm, texto, deshechos } como la ruta /crm/deshacer. */
export function deshacer(s, n) {
  const x = leer()
  const lista = [...x.puntos].sort((a, b) => a.n - b.n)
  if (!lista.length) throw new ErrorApi(404, 'No hay nada que deshacer.')
  const p = n == null ? lista[lista.length - 1] : lista.find((y) => y.n === n)
  if (!p) throw new ErrorApi(404, `No hay un pedido ${n} para deshacer.`)
  // En cadena: un pedido posterior que tocó algo de lo que vuelve también se deshace (si no, se perdería en silencio).
  const desde = new Map(cosas(p).map((c) => [c, p]))
  const grupo = [p]
  for (const y of lista.filter((z) => z.n > p.n)) {
    const cy = cosas(y)
    if (!cy.some((c) => desde.has(c))) continue
    grupo.push(y)
    for (const c of cy) if (!desde.has(c)) desde.set(c, y)
  }
  // Primero la estructura (las secciones tienen que existir), luego los datos.
  let out = s
  if (desde.has('estructura')) out = poner(out, 'estructura', desde.get('estructura').foto)
  for (const [c, y] of desde) if (c !== 'estructura') out = poner(out, c, y.foto)
  const fuera = new Set(grupo.map((y) => y.n))
  guardar({ ...x, puntos: x.puntos.filter((y) => !fuera.has(y.n)) })
  const tambien = grupo.slice(1).map((y) => `«${y.antesDe}»`).join(', ')
  const texto = `Deshecho el pedido ${p.n} «${p.antesDe}» (${p.cambio.map((c) => NOMBRE[c]).join(' y ')} quedaron como antes).`
    + (tambien ? ` También se deshizo ${tambien} porque cambiaba lo mismo.` : '') + ' Lo demás quedó igual.'
  out = { ...out, eventos: [{ id: nuevoId(), e: '↩️', t: `Deshiciste «${p.antesDe}»`, h: 'ahora' }, ...(out.eventos || [])].slice(0, 30) }
  return { crm: out, texto, deshechos: [...fuera].sort((a, b) => a - b) }
}

/** Quita los registros de ejemplo (`ejemplo: true`) de las listas, los contactos y las tareas. Lo de la persona se queda. */
export function quitarEjemplos(s) {
  let quitados = 0
  const listas = (s.listas || []).map((l) => { const r = l.registros.filter((x) => !x.ejemplo); quitados += l.registros.length - r.length; return r.length === l.registros.length ? l : { ...l, registros: r } })
  const contactos = (s.contactos || []).filter((c) => !c.ejemplo)
  const menos = (s.contactos || []).length - contactos.length
  quitados += menos
  const tareas = Object.fromEntries(Object.entries(s.tareas || {}).map(([col, ts]) => { const r = ts.filter((t) => !t.ejemplo); quitados += ts.length - r.length; return [col, r] }))
  if (!quitados) throw new ErrorApi(404, 'No hay registros de ejemplo que quitar.')
  return { ...s, listas, contactos, totalContactos: Math.max(0, (s.totalContactos ?? 0) - menos), tareas,
    eventos: [{ id: nuevoId(), e: '🧹', t: `Quitaste ${quitados} ${quitados === 1 ? 'registro' : 'registros'} de ejemplo`, h: 'ahora' }, ...(s.eventos || [])].slice(0, 30) }
}
