/* Meter, editar, borrar y consultar datos POR CHAT (D50: no hay edición manual; elegir piezas solo sirve para señalar).
 * El modelo copia lo que dijo la persona; el CÓDIGO entiende cada valor (valores.js), encuentra el registro, valida y lo
 * guarda en estado.datos, encima de los registros de ejemplo (aplicarDatos):
 *   { nuevos: {fuente: [{id, valores}]}, cambios: {fuente: {id: {campo: valor}}}, borrados: {fuente: [id]}, n }
 * fuente = la sección dueña de los datos (una pestaña con `fuente` muestra los de otra). Si un valor no se entiende o dos
 * registros coinciden, no adivina: devuelve ERROR con lo que hay que preguntar. Contar, sumar y filtrar lo hace el código. */
import { datosEjemplo, sinEjemplos, extenderDatos, aplicarDatos, isoDia } from './datosEjemplo.js'
import { parseFecha, parseNumero, parseHora, parsePeriodo, opcionDe, campoTitulo, buscarRegistro, fechaLarga } from './valores.js'
import { regionDe } from './regional.js'

const sinAcentos = (t) => String(t ?? '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').trim()
const clave = (t) => sinAcentos(t).replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '')
const MAX_LISTA = 10

/** Los registros que ve la persona AHORA (los mismos que dibuja la pantalla): ejemplos + lo que Shifu agregó + lo suyo.
 * muestra = { nivel, ejemplos, pais } de la pantalla: cuántos ejemplos hay, si ya se borraron y cómo se escriben los montos. */
export function datosActuales(plantillaBase, estado = {}, muestra = {}) {
  const nivel = muestra.nivel || 'pocos'
  let base = datosEjemplo(plantillaBase, nivel)
  if (muestra.ejemplos === false) base = sinEjemplos(base)
  const est = estado.estructura || {}
  return aplicarDatos(extenderDatos(base, plantillaBase, est, nivel), estado.datos, est.mapeoEstado)
}

function mostrar(c, v, fmt) {
  if (v === undefined || v === null || v === '') return '—'
  if (c.tipo === 'fecha') return fechaLarga(v)
  if (c.tipo === 'dinero') return fmt.dinero(Number(v))
  if (c.tipo === 'numero') return fmt.numero(Number(v))
  return String(v)
}
const tituloDe = (r, ct) => r.valores[ct.id] || '(sin nombre)'
/** Un registro en una línea, con su id al final (para que el modelo lo nombre sin ambigüedad; nunca se le dice a la persona). */
const describir = (r, campos, fmt, ct) => `${tituloDe(r, ct)} — ${campos.filter((c) => c !== ct).map((c) => `${c.nombre}: ${mostrar(c, r.valores[c.id], fmt)}`).join(' · ')} (id ${r.id})`

function campoPorClave(campos, k) {
  return campos.find((c) => c.id === k) || campos.find((c) => sinAcentos(c.nombre) === sinAcentos(k)) || campos.find((c) => clave(c.id) === clave(k) || clave(c.nombre) === clave(k))
}

/** Lo que dijo la persona → valores guardables, campo por campo. En editar, un valor vacío deja el campo vacío. */
function leerValores(sec, campos, regs, valores, { vaciar = false, hoy } = {}) {
  const listos = {}, errores = []
  for (const [k, v0] of Object.entries(valores || {})) {
    const c = campoPorClave(campos, k)
    if (!c) { errores.push(`«${k}» no es un campo de ${sec.titulo} (sus campos: ${campos.map((x) => x.nombre).join(', ')}). Si quiere guardar ese dato, pregúntale si agregas el campo.`); continue }
    const v = typeof v0 === 'string' ? v0.trim() : v0
    if (v === '' || v === null || v === undefined) { if (vaciar) listos[c.id] = ''; continue }
    if (c.tipo === 'fecha') { const f = parseFecha(v, hoy); if (f) listos[c.id] = f; else errores.push(`no entendí la fecha «${v}» para ${c.nombre}: pregúntale cuál es (por ejemplo «30 de octubre»).`) }
    else if (c.tipo === 'numero' || c.tipo === 'dinero') { const n = parseNumero(v); if (n !== null) listos[c.id] = n; else errores.push(`«${v}» no es un número para ${c.nombre}.`) }
    else if (c.tipo === 'hora') { const h = parseHora(v); if (h) listos[c.id] = h; else errores.push(`no entendí la hora «${v}» para ${c.nombre} (por ejemplo «9:30» o «3 de la tarde»).`) }
    else if (c.tipo === 'estado') { const o = opcionDe(c, v); if (o) listos[c.id] = o; else errores.push(`«${v}» no es una opción de ${c.nombre} (opciones: ${c.opciones.join(', ')}). Pregúntale cuál, o si quiere agregar esa opción.`) }
    else {
      // Si ese texto ya existe escrito de otra forma («mensual» y «Mensual»), se usa el que ya está: así se agrupa igual.
      const t = String(v).slice(0, 120)
      listos[c.id] = [...(c.ejemplos || []), ...regs.map((r) => r.valores[c.id])].find((x) => typeof x === 'string' && x !== t && sinAcentos(x) === sinAcentos(t)) || t
    }
  }
  return { listos, errores }
}

/** ¿A qué registro se refiere? Si son varios o ninguno, el error dice qué preguntar (nunca adivina). */
function encontrar(sec, campos, regs, consulta, fmt) {
  const ct = campoTitulo(sec, campos)
  const b = buscarRegistro(regs, sec, campos, String(consulta ?? ''))
  if (b.registro) return { r: b.registro }
  if (b.candidatos) return { error: `hay ${b.candidatos.length} registros en ${sec.titulo} que coinciden con «${consulta}»: ${b.candidatos.slice(0, 5).map((x) => describir(x, campos, fmt, ct)).join(' | ')}${b.candidatos.length > 5 ? ' | …' : ''}. No cambies nada: pregúntale cuál (por un dato que los distinga).` }
  const palabras = sinAcentos(consulta).split(/\s+/).filter((w) => w.length > 2)
  const parecidos = [...new Set(regs.filter((x) => palabras.some((w) => sinAcentos(x.valores[ct.id]).includes(w))).map((x) => tituloDe(x, ct)))].slice(0, 3)
  return { error: `no encontré «${consulta}» en ${sec.titulo} (tiene ${regs.length} registros).${parecidos.length ? ` Se parecen: ${parecidos.join(', ')}. Pregúntale si es alguno.` : ' Pregúntale cómo se llama exactamente o si quiere agregarlo.'}` }
}

export const HERR_DATOS = new Set(['agregar_registro', 'editar_registro', 'borrar_registro'])

/** Agregar, editar o borrar UN registro. ctx = { sec (dueña de los datos), campos, regs (los que ve ahora), f, estado, args, muestra }.
 * Devuelve { estado, ok, resultado, etiqueta } — etiqueta = el cambio dicho en simple para la línea «Cambios:» del chat. */
export function ejecutarDato(nombre, { sec, campos, regs, f, estado, args, muestra = {}, hoy = new Date() }) {
  const fmt = regionDe(muestra.pais)
  const ct = campoTitulo(sec, campos)
  const no = (t) => ({ estado, ok: false, resultado: `ERROR: ${t}` })
  const si = (datos, resultado, etiqueta) => ({ estado: { ...estado, datos }, ok: true, resultado, etiqueta })
  const d = estado.datos || {}, propios = d.nuevos?.[f] || []
  switch (nombre) {
    case 'agregar_registro': {
      const { listos, errores } = leerValores(sec, campos, regs, args.valores, { hoy })
      if (!listos[ct.id] && !errores.length) errores.push(`falta ${ct.nombre}: es lo que identifica al registro. Pregúntaselo.`)
      if (errores.length) return no(errores.join(' '))
      // Un estado sin decir: la primera opción (sin estado no se vería en el tablero). Se dice.
      const porDefecto = campos.filter((c) => c.tipo === 'estado' && listos[c.id] === undefined && c.opciones?.length).map((c) => { listos[c.id] = c.opciones[0]; return `${c.nombre}: ${c.opciones[0]}` })
      const n = (d.n || 0) + 1, reg = { id: `${f}-p${n}`, valores: listos }
      const vacios = campos.filter((c) => listos[c.id] === undefined).map((c) => c.nombre)
      const mismos = regs.filter((r) => sinAcentos(r.valores[ct.id]) === sinAcentos(listos[ct.id])).length
      return si({ ...d, n, nuevos: { ...(d.nuevos || {}), [f]: [...propios, reg] } },
        `Agregado a ${sec.titulo}: ${describir(reg, campos, fmt, ct)}.${porDefecto.length ? ` ${porDefecto.join(', ')} por defecto (dilo).` : ''}`
        + `${vacios.length ? ` Sin llenar: ${vacios.join(', ')} (dilo y ofrece completarlo; no lo inventes).` : ''}`
        + `${mismos ? ` AVISO: ya había ${mismos === 1 ? 'otro registro' : `${mismos} registros`} «${listos[ct.id]}» en ${sec.titulo}; díselo en una línea por si quería cambiar el que ya existe.` : ''} Ahora hay ${regs.length + 1} en ${sec.titulo}.`,
        `agregó «${listos[ct.id]}» a ${sec.titulo}`)
    }
    case 'editar_registro': {
      const e = encontrar(sec, campos, regs, args.registro, fmt); if (e.error) return no(e.error)
      if (!Object.keys(args.valores || {}).length) return no('falta qué cambiar (valores).')
      const { listos, errores } = leerValores(sec, campos, regs, args.valores, { vaciar: true, hoy })
      if (errores.length) return no(errores.join(' '))
      if (listos[ct.id] === '') return no(`un registro no puede quedar sin ${ct.nombre}.`)
      const nombreAntes = tituloDe(e.r, ct)
      const cambiados = campos.filter((c) => listos[c.id] !== undefined && listos[c.id] !== (e.r.valores[c.id] ?? ''))
      if (!cambiados.length) return { estado, ok: true, resultado: `«${nombreAntes}» ya tenía eso (${Object.keys(listos).map((id) => { const c = campos.find((x) => x.id === id); return `${c.nombre}: ${mostrar(c, listos[id], fmt)}` }).join(' · ')}): no cambió nada. Díselo.`, etiqueta: null }
      const cambio = Object.fromEntries(cambiados.map((c) => [c.id, listos[c.id]]))
      // Lo que agregó la persona se cambia en su lugar; un ejemplo guarda solo lo que cambió.
      const datos = propios.some((x) => x.id === e.r.id)
        ? { ...d, nuevos: { ...d.nuevos, [f]: propios.map((x) => (x.id === e.r.id ? { ...x, valores: { ...x.valores, ...cambio } } : x)) } }
        : { ...d, cambios: { ...(d.cambios || {}), [f]: { ...(d.cambios?.[f] || {}), [e.r.id]: { ...(d.cambios?.[f]?.[e.r.id] || {}), ...cambio } } } }
      return si(datos, `Cambiado «${nombreAntes}» en ${sec.titulo}: ${cambiados.map((c) => `${c.nombre}: ${mostrar(c, e.r.valores[c.id], fmt)} → ${mostrar(c, listos[c.id], fmt)}`).join(' · ')}.`,
        `cambió «${nombreAntes}»: ${cambiados.map((c) => `${c.nombre} → ${mostrar(c, listos[c.id], fmt)}`).join(', ')}`)
    }
    case 'borrar_registro': {
      const e = encontrar(sec, campos, regs, args.registro, fmt); if (e.error) return no(e.error)
      const datos = propios.some((x) => x.id === e.r.id)
        ? { ...d, nuevos: { ...d.nuevos, [f]: propios.filter((x) => x.id !== e.r.id) } }
        : { ...d, borrados: { ...(d.borrados || {}), [f]: [...(d.borrados?.[f] || []), e.r.id] } }
      return si(datos, `Borrado de ${sec.titulo}: ${describir(e.r, campos, fmt, ct)}. Se puede deshacer. Quedan ${regs.length - 1}.`, `borró «${tituloDe(e.r, ct)}» de ${sec.titulo}`)
    }
    default: return no(`la herramienta «${nombre}» no existe.`)
  }
}

/** Lee los datos para responder una pregunta: el CÓDIGO filtra, cuenta y suma (el modelo solo repite). Nunca cambia nada. */
export function consultar({ sec, campos, regs, args = {}, muestra = {}, hoy = new Date() }) {
  const fmt = regionDe(muestra.pais)
  const ct = campoTitulo(sec, campos)
  const filtros = []
  let lista = regs
  if (args.buscar) {
    const b = buscarRegistro(regs, sec, campos, String(args.buscar))
    if (b.ninguno) return `En ${sec.titulo} no hay ningún registro que coincida con «${args.buscar}» (tiene ${regs.length}). Díselo; no inventes.`
    lista = b.registro ? [b.registro] : b.candidatos; filtros.push(`que coinciden con «${args.buscar}»`)
  }
  const porFecha = (c, cuando) => {
    const p = parsePeriodo(cuando, hoy)
    if (!p) return `ERROR: no entendí el periodo «${cuando}». Se entiende: hoy, esta semana, la semana pasada, este mes, el mes pasado, los próximos 7 días, los últimos 30 días, vencidos, octubre, del 1 al 15 de octubre, una fecha.`
    lista = lista.filter((r) => { const v = r.valores[c.id]; return v && (!p.desde || v >= p.desde) && (!p.hasta || v <= p.hasta) })
    filtros.push(`${c.nombre} ${p.desde && p.hasta ? (p.desde === p.hasta ? `el ${fechaLarga(p.desde)}` : `del ${fechaLarga(p.desde)} al ${fechaLarga(p.hasta)}`) : p.hasta ? `hasta el ${fechaLarga(p.hasta)}` : `desde el ${fechaLarga(p.desde)}`}`)
    return null
  }
  for (const [k, v] of Object.entries(args.filtros || {})) {
    const c = campoPorClave(campos, k)
    if (!c) return `ERROR: «${k}» no es un campo de ${sec.titulo}. Campos: ${campos.map((x) => `${x.id} (${x.nombre})`).join(', ')}.`
    if (c.tipo === 'estado') { const o = opcionDe(c, v); if (!o) return `ERROR: «${v}» no es una opción de ${c.nombre} (opciones: ${c.opciones.join(', ')}).`; lista = lista.filter((r) => r.valores[c.id] === o); filtros.push(`${c.nombre}: ${o}`) }
    else if (c.tipo === 'fecha') { const err = porFecha(c, v); if (err) return err }
    else if (c.tipo === 'numero' || c.tipo === 'dinero') { const n = parseNumero(v); if (n === null) return `ERROR: «${v}» no es un número.`; lista = lista.filter((r) => Number(r.valores[c.id]) === n); filtros.push(`${c.nombre}: ${mostrar(c, n, fmt)}`) }
    else { const q = sinAcentos(v); lista = lista.filter((r) => sinAcentos(r.valores[c.id]).includes(q)); filtros.push(`${c.nombre} con «${v}»`) }
  }
  if (args.periodo?.cuando) {
    const fechas = campos.filter((c) => c.tipo === 'fecha')
    const c = args.periodo.campo ? campoPorClave(campos, args.periodo.campo) : fechas.length === 1 ? fechas[0] : null
    if (!c || c.tipo !== 'fecha') return `ERROR: ¿por cuál fecha? ${sec.titulo} tiene: ${fechas.map((x) => `${x.id} (${x.nombre})`).join(', ') || 'ninguna fecha'}. Pon periodo.campo.`
    const err = porFecha(c, args.periodo.cuando); if (err) return err
  }
  let suma = ''
  if (args.sumar) {
    const c = campoPorClave(campos, args.sumar), sumables = campos.filter((x) => ['numero', 'dinero'].includes(x.tipo))
    if (!c || !sumables.includes(c)) return `ERROR: «${args.sumar}» no se puede sumar en ${sec.titulo}. Se pueden sumar: ${sumables.map((x) => `${x.id} (${x.nombre})`).join(', ') || 'nada (no tiene números)'}.`
    suma = ` Suma de ${c.nombre}: ${mostrar(c, lista.reduce((t, r) => t + (Number(r.valores[c.id]) || 0), 0), fmt)}.`
  }
  const muestraTxt = lista.length ? ` ${lista.length > MAX_LISTA ? `Los primeros ${MAX_LISTA}` : 'Son'}: ${lista.slice(0, MAX_LISTA).map((r) => describir(r, campos, fmt, ct)).join(' | ')}.` : ''
  return `Hoy es ${fechaLarga(isoDia(hoy))}. En ${sec.titulo}${filtros.length ? ` (${filtros.join('; ')})` : ''}: ${lista.length} de ${regs.length} ${regs.length === 1 ? 'registro' : 'registros'}.${suma}${muestraTxt} Responde SOLO con estos números y datos (sin decir ids).`
}

/** Esquemas para el modelo (mismo formato que HERRAMIENTAS de edicion.js). */
export const HERRAMIENTAS_DATOS = [
  ['agregar_registro', 'Agrega UN registro (un cliente, un pago, una cita…) a una sección con los datos que dijo la persona. Copia cada valor TAL COMO lo dijo («30 de octubre», «Q1,200», «3 de la tarde»): el código lo entiende y lo valida. No inventes lo que no dijo: queda vacío.', {
    seccion: { type: 'string' }, valores: { type: 'object', description: 'campo (id o nombre) → valor como lo dijo la persona' } }, ['seccion', 'valores']],
  ['editar_registro', 'Cambia datos de UN registro que ya existe. registro = cómo lo nombró la persona («Ana López») o su id. Pasa solo los campos que cambian.', {
    seccion: { type: 'string' }, registro: { type: 'string' }, valores: { type: 'object', description: 'campo → valor nuevo como lo dijo; "" para dejarlo vacío' } }, ['seccion', 'registro', 'valores']],
  ['borrar_registro', 'Borra UN registro que la persona pidió borrar (se puede deshacer).', { seccion: { type: 'string' }, registro: { type: 'string' } }, ['seccion', 'registro']],
  // Medido: con «¿cuándo vence Ana?» y «vencidos» como ejemplos, «quiero VER los vencimientos en un calendario» se confundía
  // con consultar (el calendario bajó de 16/16 a ~10/16). La frontera va en la descripción: responder EN EL CHAT ≠ ver en pantalla.
  ['consultar_datos', 'Responde EN EL CHAT una pregunta sobre sus datos («¿cuántos clientes activos tengo?», «¿cuánto me pagaron este mes?», «¿qué teléfono tiene Ana?»). El código filtra, cuenta y suma. No cambia la pantalla: para VER algo en pantalla se agrega una pieza.', {
    seccion: { type: 'string' }, buscar: { type: 'string', description: 'nombre o texto de un registro' },
    filtros: { type: 'object', description: 'campo → valor (estado: Activa; plan: Mensual)' },
    periodo: { type: 'object', properties: { campo: { type: 'string', description: 'campo de fecha' }, cuando: { type: 'string', description: 'como lo dijo: «este mes», «esta semana», «los próximos 7 días»' } } },
    sumar: { type: 'string', description: 'campo de número o dinero a sumar' } }, ['seccion']],
]
