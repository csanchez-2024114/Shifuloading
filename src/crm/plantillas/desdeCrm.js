/* Adaptador del sistema de diseño (D61): el `crm` que devuelve la API (ver backend/doc/crm/CONTRATOS_DISENO.md §1, §2 y §4)
 * → la forma que dibujan las piezas del laboratorio: { plantilla, datos, bloques, paginas, marca }.
 * Función pura: no llama a la API ni guarda nada. Lo que no cumple el cerco (una vista que no existe o que apunta a un campo
 * que no está) no se dibuja mal: la sección cae a su tabla y el bloque se deja fuera, y se anota en `avisos`.
 * También va el camino de vuelta para escribir: valores de la ficha → lo que esperan las rutas de contactos y tareas. */
import { revisarVista, TIPOS_CAMPO } from '@lab/plantillas/validar.js'
import { COLUMNAS, ETAPAS } from '../secciones.js'

export const ID_CONTACTOS = 'contactos'
export const ID_TAREAS = 'desarrollo'
const ANCHOS = [3, 4, 6, 8, 12]
const ANCHO_COMPLETO = ['kpis', 'tablero', 'agenda']

/** Un campo de la API como lo entiende el laboratorio: «lista» es alias de «estado» (§1); un tipo desconocido se ve como texto. */
function campoDe(c, opcionesEstado = {}) {
  const tipo = c.tipo === 'lista' ? 'estado' : TIPOS_CAMPO.includes(c.tipo) ? c.tipo : 'texto'
  return { id: c.id, nombre: c.nombre, tipo, ...(tipo === 'estado' ? { opciones: opcionesEstado[c.id] || c.opciones || [] } : {}) }
}

/** Solo lo que tiene valor: así «—» sale igual en todas las vistas y la ficha no muestra textos vacíos. */
const conValor = (o) => Object.fromEntries(Object.entries(o).filter(([, v]) => v !== undefined && v !== null && v !== ''))

/** Bloque con su uid y su tamaño (los del contrato o los de partida, como conTamano del laboratorio). */
const bloqueDe = (b, i, prefijo) => ({ ...b, uid: b.uid || `${prefijo}${i}`, opciones: b.opciones || {},
  ancho: ANCHOS.includes(b.ancho) ? b.ancho : ANCHO_COMPLETO.includes(b.vista) ? 12 : 6,
  alto: b.vista === 'kpis' ? 1 : Math.max(1, Math.min(4, Number(b.alto) || 2)) })

/** Las secciones virtuales de Carlos (§2) más cada lista como sección general. `titulos` = los nombres del menú de CrmPage. */
function seccionesDe(crm, titulos = {}) {
  const ocultas = crm.ocultas || []
  const out = []
  if (!ocultas.includes(ID_CONTACTOS)) {
    out.push({
      id: ID_CONTACTOS, titulo: titulos[ID_CONTACTOS] || 'Contactos', grupo: 0, icono: 'usuarios', vista: 'tabla', opciones: {}, virtual: 'contactos',
      campos: [
        { id: 'nombre', nombre: 'Nombre', tipo: 'texto' }, { id: 'detalle', nombre: 'Teléfono o correo', tipo: 'texto' },
        { id: 'canal', nombre: 'Canal', tipo: 'texto' }, { id: 'etapa', nombre: 'Etapa', tipo: 'estado', opciones: crm.etapas?.length ? crm.etapas : ETAPAS },
        { id: 'responsable', nombre: 'Responsable', tipo: 'texto' },
        ...(crm.camposContacto || []).map((c) => campoDe(c)),
      ],
    })
  }
  if (!ocultas.includes(ID_TAREAS)) {
    out.push({
      id: ID_TAREAS, titulo: titulos[ID_TAREAS] || 'Tareas', grupo: 0, icono: 'tablero', vista: 'tablero', opciones: { por: 'estado', titulo: 'tarea' }, virtual: 'tareas',
      campos: [
        { id: 'tarea', nombre: 'Tarea', tipo: 'texto' }, { id: 'vence', nombre: 'Vence', tipo: 'fecha' }, { id: 'hora', nombre: 'Hora', tipo: 'hora' },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: COLUMNAS.map(([, t]) => t) },
      ],
    })
  }
  for (const l of crm.listas || []) {
    out.push({
      id: l.id, titulo: l.nombre, grupo: [0, 1, 2].includes(l.grupo) ? l.grupo : 0, icono: l.icono || 'tabla',
      vista: l.vista || 'tabla', opciones: l.opciones || {}, virtual: null,
      campos: (l.campos || []).map((c) => campoDe(c, l.opcionesEstado)),
      ...(l.ficha ? { ficha: l.ficha } : {}), ...(l.tarjeta ? { tarjeta: l.tarjeta } : {}), ...(l.origen ? { origen: l.origen } : {}),
    })
  }
  return out
}

/** Registros de cada sección como los esperan las vistas: { secId: [{ id, valores, ejemplo? }] }. */
function registrosDe(crm, secciones) {
  const hay = new Set(secciones.map((s) => s.id))
  const registros = {}
  if (hay.has(ID_CONTACTOS)) {
    registros[ID_CONTACTOS] = (crm.contactos || []).map((c) => ({ id: c.id,
      valores: conValor({ nombre: c.n, detalle: c.det, canal: c.canal, etapa: c.etapa, responsable: c.dueno, ...(c.extra || {}) }) }))
  }
  if (hay.has(ID_TAREAS)) {
    registros[ID_TAREAS] = COLUMNAS.flatMap(([col, estado]) => (crm.tareas?.[col] || []).map((t) => ({ id: t.id,
      valores: conValor({ tarea: t.t, vence: t.vence, hora: t.hora, estado }) })))
  }
  for (const l of crm.listas || []) {
    registros[l.id] = (l.registros || []).map((r) => ({ id: r.id, valores: r.valores || {}, ...(r.ejemplo ? { ejemplo: true } : {}) }))
  }
  return registros
}

/**
 * El CRM de la API → lo que dibujan las piezas del laboratorio.
 * `acomodar(bloques)` = cómo se tapan los huecos de la rejilla (la pantalla pasa el de edicion.js).
 * Devuelve { plantilla: {id, nombre, para, inicio, secciones}, datos: {registros, eventos, equipo, automatizaciones},
 *            bloques (del inicio), paginas ({secId: [Bloque]}), marca, porId, avisos: [texto] }.
 */
export function desdeCrm(crm, { titulos = {}, acomodar = (bs) => bs } = {}) {
  const avisos = []
  const secciones = seccionesDe(crm || {}, titulos)
  const porId = Object.fromEntries(secciones.map((s) => [s.id, s]))
  // La vista de cada sección pasa el cerco; si no, su tabla de siempre (nunca se dibuja mal).
  for (const s of secciones) {
    const err = revisarVista(s.vista, s.opciones, s.campos, `«${s.titulo}»`)
    if (err.length) { avisos.push(...err); s.vista = 'tabla'; s.opciones = {} }
  }
  // Un bloque de una sección que no existe (o está oculta) o que no pasa el cerco se deja fuera.
  const validos = (lista, prefijo, donde) => (Array.isArray(lista) ? lista : []).map((b, i) => bloqueDe(b, i, prefijo)).filter((b) => {
    const s = porId[b.seccion]
    if (!s) { avisos.push(`${donde}: la sección «${b.seccion}» no existe.`); return false }
    const err = revisarVista(b.vista, b.opciones, s.campos, `${donde} (${b.vista} de «${s.titulo}»)`)
    if (err.length) { avisos.push(...err); return false }
    return true
  })
  // `acomodar` (el de edicion.js en la pantalla) tapa los huecos de la rejilla; aquí, por defecto, se dejan como vienen.
  const bloques = acomodar(validos(crm?.inicio, 'b', 'Inicio'))
  const paginas = {}
  for (const [sid, lista] of Object.entries(crm?.paginas || {})) {
    if (!porId[sid]) { avisos.push(`Página «${sid}»: la sección no existe.`); continue }
    paginas[sid] = acomodar(validos(lista, `p_${sid}_`, `Pestaña «${porId[sid].titulo}»`))
    porId[sid].pagina = paginas[sid] // como plantillaEfectiva del laboratorio: la pestaña con lienzo propio
  }
  const plantilla = { id: crm?.plantilla?.id || 'crm', nombre: crm?.brief?.nombre || 'Mi CRM', para: '', inicio: bloques, secciones }
  const datos = {
    registros: registrosDe(crm || {}, secciones),
    eventos: crm?.eventos || [], equipo: crm?.vendedores || ['Tú'], automatizaciones: crm?.automatizaciones || [],
  }
  // El logo llega como `logo_id` (§1): la imagen se lee aparte (GET /crm/logo/{id}, LogoNegocio). La marca de las piezas no lo lleva.
  const { logo_id: logoId, ...marca } = crm?.marca || {}
  return { plantilla, datos, bloques, paginas, marca, logoId: logoId || null, porId, avisos }
}

/** ¿Hay algo del sistema de diseño en este CRM? (para mostrar «Inicio» en el menú). */
export const tieneInicio = (crm) => Array.isArray(crm?.inicio)

/** Cuántos registros de ejemplo (`ejemplo: true`, sembrados por la plantilla) hay en todo el CRM. */
export function contarEjemplos(crm) {
  const listas = (crm?.listas || []).reduce((n, l) => n + (l.registros || []).filter((r) => r.ejemplo).length, 0)
  const contactos = (crm?.contactos || []).filter((c) => c.ejemplo).length
  const tareas = Object.values(crm?.tareas || {}).flat().filter((t) => t.ejemplo).length
  return listas + contactos + tareas
}

/** Valores de la ficha de un contacto → cambios para contactosActualizar / la fila de contactosCrear.
 * `extraActual` = los campos propios que ya tiene: se mandan todos juntos para no perder ninguno. */
export function contactoDesdeValores(valores, extraActual = {}) {
  const base = { nombre: 'n', detalle: 'det', canal: 'canal', etapa: 'etapa', responsable: 'dueno' }
  const out = {}
  const extra = {}
  for (const [k, v] of Object.entries(valores)) {
    if (base[k]) out[base[k]] = v
    else extra[k] = v
  }
  if (Object.keys(extra).length) out.extra = { ...extraActual, ...extra }
  return out
}

/** Valores de la ficha de una tarea → { cambios para tareasActualizar ({t, vence, hora}), columna destino o null }. */
export function tareaDesdeValores(valores) {
  const cambios = {}
  if ('tarea' in valores) cambios.t = valores.tarea
  if ('vence' in valores) cambios.vence = valores.vence || ''
  if ('hora' in valores) cambios.hora = valores.hora || ''
  const columna = 'estado' in valores ? (COLUMNAS.find(([, t]) => t === valores.estado)?.[0] ?? null) : null
  return { cambios, columna }
}
