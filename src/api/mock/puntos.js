/* Puntos de deshacer del servidor simulado (D61, contratos §3), solo con VITE_CRM_DISENO=1 y sin servidor: cada cambio que
 * hace la persona (a mano o por el chat simulado) deja un punto con la foto de ANTES de solo lo que cambió, y «deshacer»
 * devuelve solo eso. Imita a `puntos.py` (frente D): selectivo por categoría (en el simulado: «estructura» y «datos», por
 * sección), los últimos 30; en datos, a 3 vías por registro y campo (como `revertirDatos`): solo lo de ese pedido, y si un
 * pedido posterior tocó lo mismo, se deshacen en cadena y se dice. La estructura vuelve por foto.
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

/* Los registros de una sección como lista plana con id (las tareas llevan su columna), y de vuelta a como se guarda. */
const registros = (sec, v) => (sec === 'desarrollo' ? Object.entries(v || {}).flatMap(([columna, ts]) => ts.map((t) => ({ ...t, columna })))
  : sec === 'contactos' ? v?.contactos || [] : v?.registros || [])
function armar(sec, lista, actual) {
  if (sec === 'contactos') return { contactos: lista, totalContactos: Math.max(0, (actual?.totalContactos ?? 0) + lista.length - (actual?.contactos || []).length) }
  if (sec === 'desarrollo') {
    const out = Object.fromEntries(Object.keys(actual || { porHacer: 0, enCurso: 0, hecho: 0 }).map((c) => [c, []]))
    for (const { columna, ...t } of lista) (out[columna] ||= []).push(t)
    return out
  }
  return { ...actual, registros: lista }
}

/** `revertirDatos` en chico: deshace en `actual` solo lo que cambió de `antes` a `despues` (que exista cada registro y cada
 * campo). null si un cambio posterior tocó lo mismo (entonces se deshace en cadena). */
function tresVias(sec, antes, despues, actual) {
  if (sec !== 'contactos' && sec !== 'desarrollo' && !igual(antes?.importaciones, despues?.importaciones)) return null
  const A = registros(sec, antes), D = new Map(registros(sec, despues).map((r) => [r.id, r]))
  const mA = new Map(A.map((r) => [r.id, r]))
  let out = registros(sec, actual).map((r) => ({ ...r }))
  const enOut = () => new Map(out.map((r) => [r.id, r]))
  for (const id of new Set([...mA.keys(), ...D.keys()])) {
    const a = mA.get(id), d = D.get(id), c = enOut().get(id)
    if (igual(a, d)) continue
    if (!a) { if (!c) continue; if (!igual(c, d)) return null; out = out.filter((r) => r.id !== id); continue } // lo creó este pedido
    if (!d) { // lo borró este pedido: vuelve a su lugar
      if (c) return null
      const previo = A.slice(0, A.indexOf(a)).reverse().find((r) => enOut().has(r.id))
      const k = previo ? out.findIndex((r) => r.id === previo.id) + 1 : 0
      out.splice(k, 0, { ...a }); continue
    }
    if (!c) return null // lo cambió este pedido y después alguien lo borró
    for (const f of new Set([...Object.keys(a), ...Object.keys(d)])) {
      if (igual(a[f], d[f])) continue
      if (!igual(c[f], d[f])) return null
      if (a[f] === undefined) delete c[f]; else c[f] = a[f]
    }
  }
  return armar(sec, out, actual)
}

function poner(s, cosa, foto) {
  if (cosa === 'estructura') {
    const e = foto.estructura
    const regs = new Map((s.listas || []).map((l) => [l.id, { registros: l.registros, importaciones: l.importaciones }]))
    return { ...s, secciones: e.secciones, ocultas: e.ocultas, ...(e.etapas ? { etapas: e.etapas } : {}), ...(e.camposContacto ? { camposContacto: e.camposContacto } : {}),
      listas: e.listas.map((m) => ({ ...m, ...(regs.get(m.id) || { registros: [], importaciones: [] }) })) }
  }
  return ponerDatos(s, cosa.slice('datos:'.length), foto.datos[cosa.slice('datos:'.length)])
}
function ponerDatos(s, sec, v) {
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
  const posteriores = lista.filter((z) => z.n > p.n)
  const actual = datosDe(s)
  // 1. Los datos de ESTE punto, a 3 vías por sección. `despues` = la sección justo después de este punto: la foto del
  //    siguiente punto que la tocó o, si ninguno, como está ahora.
  const tres = new Map(), despuesDe = new Map()
  for (const [sec, antesSec] of Object.entries(p.foto.datos || {})) {
    despuesDe.set(sec, posteriores.find((y) => y.foto.datos && sec in y.foto.datos)?.foto.datos[sec] ?? actual[sec])
    const r = tresVias(sec, antesSec, despuesDe.get(sec), actual[sec])
    if (r) tres.set(sec, r)
  }
  // 2. Lo demás vuelve por foto, y en cadena los posteriores que lo tocaron (si no, se perdería en silencio).
  const desde = new Map(cosas(p).filter((c) => !tres.has(c.slice('datos:'.length))).map((c) => [c, p]))
  const grupo = [p]
  for (let cambio = true; cambio;) {
    cambio = false
    for (const y of posteriores) {
      if (grupo.includes(y)) continue
      const cy = cosas(y)
      if (!cy.some((c) => desde.has(c) && y.n > desde.get(c).n)) continue
      grupo.push(y); cambio = true
      for (const c of cy) {
        const sec = c.startsWith('datos:') ? c.slice('datos:'.length) : null
        if (sec && tres.has(sec)) { tres.delete(sec); desde.set(c, p) } // esa sección ya no puede ir a 3 vías: vuelve por la foto de este punto
        if (!desde.has(c)) desde.set(c, y)
      }
    }
  }
  // 3. Primero la estructura (las secciones tienen que existir), luego los datos.
  let out = s
  if (desde.has('estructura')) out = poner(out, 'estructura', desde.get('estructura').foto)
  for (const [c, y] of desde) if (c !== 'estructura') out = poner(out, c, y.foto)
  for (const [sec, v] of tres) out = ponerDatos(out, sec, v)
  // 4. Las fotos de los que se quedan olvidan lo deshecho a 3 vías (si después se deshace uno, no revive lo ya deshecho).
  const fuera = new Set(grupo.map((y) => y.n))
  const quedan = x.puntos.filter((y) => !fuera.has(y.n)).map((y) => {
    if (y.n < p.n) return y
    const datos = { ...(y.foto.datos || {}) }
    for (const sec of tres.keys()) if (sec in datos) { const r = tresVias(sec, p.foto.datos[sec], despuesDe.get(sec), datos[sec]); if (r) datos[sec] = r }
    return y.foto.datos ? { ...y, foto: { ...y.foto, datos } } : y
  })
  guardar({ ...x, puntos: quedan })
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
