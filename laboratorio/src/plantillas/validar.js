/* El cerco de las plantillas: qué vistas existen y qué exige cada una. Función pura, sin pantalla ni API.
 * Una plantilla (o un cambio que proponga la IA) que no lo cumple se rechaza con un mensaje legible, en vez de dibujarse mal. */

export const TIPOS_CAMPO = ['texto', 'numero', 'dinero', 'fecha', 'hora', 'estado']

// vista → opciones que pide y de qué tipo debe ser el campo al que apuntan. `datos: false` = no usa registros de una sección.
export const VISTAS = {
  tabla: { requiere: {}, opcional: { filtro: null, orden: null, limite: null } },
  kpis: { requiere: {}, opcional: { por: ['estado'], suma: ['dinero', 'numero'], vencen: ['fecha'], hoy: ['fecha'], estado: ['estado'], excluir: null } },
  tablero: { requiere: { por: ['estado'] }, opcional: { titulo: null, detalle: null } },
  agenda: { requiere: { fecha: ['fecha'] }, opcional: { hora: ['hora'], titulo: null, detalle: null } },
  vencimientos: { requiere: { fecha: ['fecha'] }, opcional: { titulo: null, detalle: null, estado: ['estado'], excluir: null } },
  grafica: { requiere: {}, opcional: { por: ['estado'], fecha: ['fecha'], suma: ['dinero', 'numero'] } },
  // Catálogo grande (graficos.jsx): el tipo y sus campos los revisa compatibles() al editar.
  grafico: { requiere: {}, libre: true },
  // Herramientas que la persona puede pedir (D49; las dibuja vistas-extra.jsx). 'libre' = valor que no es un campo.
  calendario_mes: { requiere: { fecha: ['fecha'] }, opcional: { titulo: null, estado: ['estado'], mes: 'libre' } },
  tablero_dinero: { requiere: { por: ['estado'], suma: ['dinero', 'numero'] }, opcional: { titulo: null, detalle: null, dias_en: ['fecha'] } },
  cifra: { requiere: {}, opcional: { funcion: 'libre', valor: ['dinero', 'numero'], filtro: 'libre', meta: 'libre', fecha: ['fecha'], periodo: 'libre', ayuda: 'libre' } },
  atencion: { requiere: { fecha: ['fecha'] }, opcional: { estado: ['estado'], excluir: 'libre' } },
  franjas: { requiere: { fecha: ['fecha'] }, opcional: { estado: ['estado'], titulo: null, detalle: null, urgentes: 'libre' } },
  matriz: { requiere: { filas: ['texto'], columnas: ['estado'] }, opcional: {} },
  feed: { datos: false },
  equipo: { datos: false },
  interruptores: { datos: false },
}

/** Devuelve la lista de errores (vacía = la plantilla es válida). */
export function validarPlantilla(p) {
  const errores = []
  if (!p?.id || !p?.nombre) errores.push('La plantilla necesita id y nombre.')
  const secciones = p?.secciones || []
  const porId = Object.fromEntries(secciones.map((s) => [s.id, s]))
  const ids = new Set()
  for (const s of secciones) {
    if (ids.has(s.id)) errores.push(`Hay dos secciones con el id «${s.id}».`)
    ids.add(s.id)
    for (const c of s.campos || []) {
      if (!TIPOS_CAMPO.includes(c.tipo)) errores.push(`«${s.titulo}»: el campo «${c.nombre}» tiene un tipo desconocido (${c.tipo}).`)
      if (c.tipo === 'estado' && !(c.opciones?.length >= 2)) errores.push(`«${s.titulo}»: el campo de estado «${c.nombre}» necesita al menos 2 opciones.`)
    }
    errores.push(...revisarVista(s.vista, s.opciones, camposDe(s, porId), `«${s.titulo}»`))
  }
  for (const [i, w] of (p?.inicio || []).entries()) {
    const s = porId[w.seccion]
    if (!s) { errores.push(`Inicio, bloque ${i + 1}: la sección «${w.seccion}» no existe.`); continue }
    errores.push(...revisarVista(w.vista, w.opciones, camposDe(s, porId), `Inicio, bloque ${i + 1} (${w.vista} de «${s.titulo}»)`))
  }
  return errores
}

/** Una sección con `fuente` muestra los registros de otra: usa los campos de esa otra. */
export const camposDe = (s, porId) => (s.fuente ? porId[s.fuente]?.campos : s.campos) || []

/** Opciones que apuntan a UN campo: si el modelo manda una lista de un solo id (["monto"]), se toma ese id (calculable).
 * Medido: «suma: ["monto"]» daba «el campo monto no existe» y el modelo terminaba creando campos que ya había. */
export function normalizarOpciones(vista, opciones = {}) {
  const def = VISTAS[vista]; if (!def || def.libre || !opciones) return opciones
  const deCampo = { ...def.requiere, ...Object.fromEntries(Object.entries(def.opcional || {}).filter(([, t]) => t !== 'libre' && t !== null)) }
  const out = { ...opciones }
  for (const op of Object.keys(deCampo)) if (Array.isArray(out[op]) && out[op].length === 1 && typeof out[op][0] === 'string') out[op] = out[op][0]
  return out
}

export function revisarVista(vista, opciones = {}, campos, donde) {
  const def = VISTAS[vista]
  if (!def) return [`${donde}: la vista «${vista}» no está en el catálogo (${Object.keys(VISTAS).join(', ')}).`]
  if (def.datos === false || def.libre) return []
  const errores = []
  const tipoDe = (id) => campos.find((c) => c.id === id)?.tipo
  for (const [op, tipos] of Object.entries(def.requiere)) {
    if (!opciones?.[op]) { errores.push(`${donde}: la vista «${vista}» necesita la opción «${op}».`); continue }
    if (Array.isArray(opciones[op])) errores.push(`${donde}: «${op}» debe ser el id de UN campo (texto), no una lista.`)
    else if (!tipoDe(opciones[op])) errores.push(`${donde}: «${op}» apunta al campo «${opciones[op]}», que no existe.`)
    else if (tipos && !tipos.includes(tipoDe(opciones[op]))) errores.push(`${donde}: «${op}» debe ser un campo de tipo ${tipos.join(' o ')}, y «${opciones[op]}» es ${tipoDe(opciones[op])}.`)
  }
  for (const [op, tipos] of Object.entries(def.opcional || {})) {
    if (tipos === 'libre' || !opciones?.[op] || typeof opciones[op] !== 'string' || ['dias', 'excluir', 'orden'].includes(op)) continue
    if (!tipoDe(opciones[op])) errores.push(`${donde}: «${op}» apunta al campo «${opciones[op]}», que no existe.`)
    else if (tipos && !tipos.includes(tipoDe(opciones[op]))) errores.push(`${donde}: «${op}» debe ser un campo de tipo ${tipos.join(' o ')}.`)
  }
  for (const op of Object.keys(opciones || {})) {
    if (!(op in def.requiere) && !(op in (def.opcional || {})) && op !== 'dias' && op !== 'tipo') errores.push(`${donde}: la vista «${vista}» no tiene la opción «${op}».`)
  }
  return errores
}
