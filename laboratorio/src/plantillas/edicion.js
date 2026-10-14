/* El cerco de la edición por IA: las ÚNICAS operaciones que Shifu puede hacer sobre la pantalla de inicio.
 * Funciones puras (sin React, sin API): reciben el estado y devuelven el nuevo estado o un error legible.
 * Las usa el servidor del laboratorio (servidor/chat.js) al ejecutar las herramientas del modelo, y nada más las cambia.
 * Lo que el modelo pide fuera de esto (una vista que no existe, un campo equivocado) se rechaza aquí, no se dibuja mal. */
import { VISTAS, revisarVista, camposDe } from './validar.js'
import { compatibles, GRAFICOS } from './graficos.jsx'

export const ANCHOS_COL = [3, 4, 6, 8, 12]
export const ALTO_MAX = 4
const VISTAS_INICIO = ['kpis', 'tablero', 'agenda', 'vencimientos', 'grafico', 'tabla']
// id nuevo e irrepetible: si se reusara el de un bloque quitado, la animación lo confundiría con el viejo.
const nuevoUid = () => `n${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`
const ajustarAncho = (a) => ANCHOS_COL.reduce((m, x) => (Math.abs(x - a) < Math.abs(m - a) ? x : m), 6)

/** Los rangos que dibuja un bloque de vencimientos (la misma regla que la vista en vistas.jsx). */
export const rangosDe = (opciones = {}) => opciones.rangos
  || [{ desde: null, hasta: -1 }, { desde: 0, hasta: 7 }, ...((opciones.dias || 30) > 7 ? [{ desde: 8, hasta: opciones.dias || 30 }] : [])]

function seccionDe(plantilla, id) { return plantilla.secciones.find((s) => s.id === id || s.titulo.toLowerCase() === String(id || '').toLowerCase()) }
function bloqueDe(estado, uid) { return estado.bloques.find((b) => b.uid === uid) }

/** Dónde cae de verdad cada bloque en la rejilla (12 columnas, acomodo "dense" como el CSS): lo calcula el código,
 * para que Shifu no diga "a la derecha" si quedó abajo a la izquierda. Devuelve { uid: {fila, col, lado} }. */
export function ubicar(bloques) {
  const ocupado = [] // ocupado[fila][col]
  const libre = (f, c, w, h) => { for (let y = f; y < f + h; y++) for (let x = c; x < c + w; x++) if (ocupado[y]?.[x]) return false; return c + w <= 12 }
  const out = {}
  for (const b of bloques) {
    const w = b.ancho || 6, h = b.vista === 'kpis' ? 1 : b.alto || 1
    let f = 0, c = 0
    for (;; f++) { c = [...Array(13 - w).keys()].find((x) => libre(f, x, w, h)); if (c !== undefined) break }
    for (let y = f; y < f + h; y++) { ocupado[y] ||= []; for (let x = c; x < c + w; x++) ocupado[y][x] = true }
    const centro = c + w / 2
    out[b.uid] = { fila: f + 1, lado: w === 12 ? 'ancho completo' : centro <= 4.5 ? 'izquierda' : centro >= 7.5 ? 'derecha' : 'centro' }
  }
  return out
}
const ubicacion = (u) => (u ? `fila ${u.fila}, ${u.lado}` : '')

/** Lo que el modelo ve de la pantalla: bloques actuales y, por sección, sus campos y las vistas que admite. */
export function describirPantalla(plantilla, estado) {
  const porId = Object.fromEntries(plantilla.secciones.map((s) => [s.id, s]))
  return {
    plantilla: plantilla.nombre,
    rejilla: 'Inicio en 12 columnas. ancho ∈ [3,4,6,8,12] (3 = cuatro por fila, 12 = ancho completo). alto ∈ 1..4 filas. Todo debe caber en una pantalla: más bloques = bloques más bajos.',
    bloques: estado.bloques.map((b, i) => ({ id: b.uid, posicion: i + 1, donde_se_ve: ubicacion(ubicar(estado.bloques)[b.uid]), vista: b.vista, seccion: b.seccion, titulo_seccion: porId[b.seccion]?.titulo, opciones: b.opciones, ancho: b.ancho, alto: b.alto,
      // Los grupos que la persona VE ahora (los por defecto no viven en opciones): sin esto el modelo no sabe qué conservar.
      ...(b.vista === 'vencimientos' ? { grupos_actuales: rangosDe(b.opciones).map((r) => (r.desde === null ? 'Vencidos {vencidos:true}' : `De ${r.desde} a ${r.hasta} días {desde:${r.desde},hasta:${r.hasta}}`)) } : {}) })),
    secciones: plantilla.secciones.filter((s) => s.campos || s.fuente).map((s) => ({ id: s.id, titulo: s.titulo,
      campos: camposDe(s, porId).map((c) => ({ id: c.id, nombre: c.nombre, tipo: c.tipo, ...(c.opciones ? { opciones: c.opciones } : {}) })),
      // Qué gráficos se pueden dibujar con ESTA sección (lo decide el código, no el modelo).
      graficos_posibles: compatibles(camposDe(s, porId)).map((g) => `${g.id} (${g.nombre})`) })),
    vistas: Object.fromEntries(VISTAS_INICIO.map((v) => [v, { requiere: VISTAS[v].requiere, opcional: Object.keys(VISTAS[v].opcional || {}) }])),
    grafico: 'vista "grafico" con opciones {tipo: <id de graficos_posibles>} y opcionalmente {funcion: conteo|suma|promedio|mediana|minimo|maximo|moda|desviacion, valor: campo numérico, agrupar: campo o "mes", meta, top}. La vieja "grafica" (barras/dona/linea) sigue existiendo en bloques que ya la tienen.',
  }
}

/** Ejecuta UNA operación. Devuelve { estado, ok, resultado } — resultado es el texto que lee el modelo. */
export function ejecutar(plantilla, estado, nombre, args = {}, contexto = {}) {
  const r = ejecutarSin(plantilla, estado, nombre, args, contexto)
  if (!r.ok || !r.estado.bloques) return r
  // Cada resultado dice dónde quedó TODO de verdad: el modelo describe eso, no lo que supone.
  const u = ubicar(r.estado.bloques)
  return { ...r, resultado: `${r.resultado} Así se ve ahora: ${r.estado.bloques.map((b) => `${b.uid} (${b.vista}) → ${ubicacion(u[b.uid])}`).join('; ')}.` }
}

function ejecutarSin(plantilla, estado, nombre, args = {}, contexto = {}) {
  const porId = Object.fromEntries(plantilla.secciones.map((s) => [s.id, s]))
  const no = (resultado) => ({ estado, ok: false, resultado: `ERROR: ${resultado}` })
  const si = (nuevo, resultado) => ({ estado: nuevo, ok: true, resultado })
  const conBloques = (bloques) => ({ ...estado, bloques })
  switch (nombre) {
    case 'quitar_bloque': {
      const b = bloqueDe(estado, args.bloque); if (!b) return no(`no existe el bloque «${args.bloque}». Usa los id de "bloques".`)
      // Quitar es lo único que borra algo de la pantalla: solo si la persona lo pidió en este mensaje. Si no, se le pregunta.
      if (!contexto.pideQuitar) return no(`la persona NO pidió quitar nada en este mensaje. No quites el bloque ${b.uid}: si crees que conviene, pregúntale primero.`)
      return si(conBloques(estado.bloques.filter((x) => x !== b)), `Quitado el bloque ${b.uid} (${b.vista} de ${porId[b.seccion]?.titulo}).`)
    }
    case 'agregar_bloque': case 'cambiar_visual': {
      const viejo = nombre === 'cambiar_visual' ? bloqueDe(estado, args.bloque) : null
      if (nombre === 'cambiar_visual' && !viejo) return no(`no existe el bloque «${args.bloque}».`)
      // Cambiar un bloque que NO es gráfica (resumen, tablero, lista…) por otra cosa es quitarlo: solo si lo pidieron.
      if (viejo && !['grafica', 'grafico'].includes(viejo.vista) && args.vista !== viejo.vista && !contexto.pideQuitar)
        return no(`el bloque ${viejo.uid} es ${viejo.vista}: reemplazarlo lo quitaría y la persona no lo pidió. Agrega un bloque nuevo, o pregúntale si quiere reemplazarlo.`)
      const s = seccionDe(plantilla, args.seccion || viejo?.seccion); if (!s) return no(`la sección «${args.seccion}» no existe. Secciones: ${plantilla.secciones.filter((x) => x.campos || x.fuente).map((x) => x.id).join(', ')}.`)
      if (!VISTAS_INICIO.includes(args.vista)) return no(`la vista «${args.vista}» no existe en el inicio. Vistas posibles: ${VISTAS_INICIO.join(', ')}.`)
      const opciones = args.opciones || {}
      const errores = revisarVista(args.vista, opciones, camposDe(s, porId), `«${s.titulo}»`)
      if (args.vista === 'grafico') {
        const posibles = compatibles(camposDe(s, porId)).map((g) => g.id)
        if (!GRAFICOS[opciones.tipo]) errores.push(`el gráfico «${opciones.tipo}» no existe. Con ${s.titulo} se pueden: ${posibles.join(', ')}.`)
        else if (!posibles.includes(opciones.tipo)) errores.push(`«${GRAFICOS[opciones.tipo].nombre}» no se puede dibujar con los campos de ${s.titulo}. Posibles: ${posibles.join(', ')}.`)
        for (const k of ['valor', 'agrupar', 'estado', 'fecha', 'texto', 'x', 'y']) if (opciones[k] && opciones[k] !== 'mes' && !camposDe(s, porId).some((c) => c.id === opciones[k])) errores.push(`«${k}» apunta al campo «${opciones[k]}», que no existe en ${s.titulo}.`)
      }
      if (errores.length) return no(errores.join(' '))
      const b = { ...(viejo || {}), uid: viejo?.uid || nuevoUid(estado), seccion: s.id, vista: args.vista, opciones,
        ancho: ajustarAncho(Number(args.ancho) || viejo?.ancho || (['kpis', 'tablero', 'agenda'].includes(args.vista) ? 12 : 6)),
        alto: Math.max(1, Math.min(ALTO_MAX, Number(args.alto) || viejo?.alto || (args.vista === 'kpis' ? 1 : 2))) }
      if (viejo) return si(conBloques(estado.bloques.map((x) => (x === viejo ? b : x))), `El bloque ${b.uid} ahora es ${b.vista} de ${s.titulo}.`)
      const pos = Math.max(0, Math.min(estado.bloques.length, (Number(args.posicion) || estado.bloques.length + 1) - 1))
      const bs = [...estado.bloques]; bs.splice(pos, 0, b)
      return si(conBloques(bs), `Agregado el bloque ${b.uid}: ${b.vista} de ${s.titulo}, ancho ${b.ancho}, alto ${b.alto}, posición ${pos + 1}.`)
    }
    case 'cambiar_tamano': {
      const b = bloqueDe(estado, args.bloque); if (!b) return no(`no existe el bloque «${args.bloque}».`)
      const ancho = args.ancho != null ? ajustarAncho(Number(args.ancho)) : b.ancho
      const alto = args.alto != null ? Math.max(1, Math.min(ALTO_MAX, Number(args.alto))) : b.alto
      if (b.vista === 'kpis' && alto !== b.alto) return no('el resumen (kpis) siempre mide una fila; solo se le puede cambiar el ancho.')
      return si(conBloques(estado.bloques.map((x) => (x === b ? { ...b, ancho, alto } : x))), `Bloque ${b.uid}: ancho ${ancho}, alto ${alto}.`)
    }
    case 'mover_bloque': {
      const b = bloqueDe(estado, args.bloque); if (!b) return no(`no existe el bloque «${args.bloque}».`)
      const resto = estado.bloques.filter((x) => x !== b)
      const pos = Math.max(0, Math.min(resto.length, (Number(args.posicion) || 1) - 1)); resto.splice(pos, 0, b)
      return si(conBloques(resto), `Bloque ${b.uid} movido a la posición ${pos + 1}.`)
    }
    case 'cambiar_rangos': {
      const b = bloqueDe(estado, args.bloque); if (!b) return no(`no existe el bloque «${args.bloque}».`)
      if (b.vista !== 'vencimientos') return no(`el bloque ${b.uid} es ${b.vista}; los rangos solo existen en vencimientos.`)
      const rangos = (args.rangos || []).map((r) => ({ desde: r.vencidos ? null : Number(r.desde), hasta: r.vencidos ? -1 : Number(r.hasta) }))
      if (!rangos.length || rangos.length > 5) return no('da entre 1 y 5 rangos.')
      for (const r of rangos) if (r.desde !== null && !(Number.isFinite(r.desde) && Number.isFinite(r.hasta) && r.hasta >= r.desde && r.desde >= 0 && r.hasta <= 365)) return no('cada rango es {desde, hasta} en días (0 a 365, hasta ≥ desde), o {vencidos: true}.')
      return si(conBloques(estado.bloques.map((x) => (x === b ? { ...b, opciones: { ...b.opciones, rangos } } : x))),
        `Rangos del bloque ${b.uid}: ${rangos.map((r) => (r.desde === null ? 'Vencidos' : `${r.desde}-${r.hasta} días`)).join(', ')}.`)
    }
    case 'abrir_seccion': {
      const s = seccionDe(plantilla, args.seccion); if (!s && args.seccion !== 'inicio') return no(`la sección «${args.seccion}» no existe.`)
      return si({ ...estado, vista: s ? s.id : 'inicio' }, `Abierta la sección ${s ? s.titulo : 'Inicio'}.`)
    }
    default: return no(`la herramienta «${nombre}» no existe.`)
  }
}

/** Esquemas de las herramientas para el modelo (formato OpenAI). */
export const HERRAMIENTAS = [
  ['quitar_bloque', 'Quita un bloque del inicio.', { bloque: { type: 'string', description: 'id del bloque, ej. b2' } }, ['bloque']],
  ['agregar_bloque', 'Agrega un bloque al inicio con una vista del catálogo sobre una sección.', {
    seccion: { type: 'string' }, vista: { type: 'string', enum: VISTAS_INICIO }, opciones: { type: 'object', description: 'opciones de la vista: ids de campos (ver "vistas" y "secciones"). Para grafico: {tipo: uno de graficos_posibles de esa sección, ...}' , additionalProperties: true },
    ancho: { type: 'integer', enum: ANCHOS_COL }, alto: { type: 'integer', minimum: 1, maximum: ALTO_MAX }, posicion: { type: 'integer', minimum: 1 } }, ['seccion', 'vista']],
  ['cambiar_visual', 'Cambia la vista o sus opciones de un bloque existente (mantiene su lugar y tamaño).', {
    bloque: { type: 'string' }, vista: { type: 'string', enum: VISTAS_INICIO }, opciones: { type: 'object', additionalProperties: true }, seccion: { type: 'string' } }, ['bloque', 'vista']],
  ['cambiar_tamano', 'Cambia el ancho (columnas de 12) y/o el alto (filas) de un bloque.', { bloque: { type: 'string' }, ancho: { type: 'integer', enum: ANCHOS_COL }, alto: { type: 'integer', minimum: 1, maximum: ALTO_MAX } }, ['bloque']],
  ['mover_bloque', 'Cambia el orden: pone el bloque en esa posición (1 = primero). Para que algo quede a la derecha de otro, va justo después y la suma de anchos de la fila debe ser ≤ 12.', { bloque: { type: 'string' }, posicion: { type: 'integer', minimum: 1 } }, ['bloque', 'posicion']],
  ['cambiar_rangos', 'Define los grupos de un bloque de vencimientos. Reemplaza TODOS los rangos: incluye los que se quedan.', {
    bloque: { type: 'string' }, rangos: { type: 'array', items: { type: 'object', properties: { vencidos: { type: 'boolean' }, desde: { type: 'integer' }, hasta: { type: 'integer' } } } } }, ['bloque', 'rangos']],
  ['abrir_seccion', 'Muestra una sección del menú (o "inicio").', { seccion: { type: 'string' } }, ['seccion']],
].map(([name, description, properties, required]) => ({ type: 'function', function: { name, description, parameters: { type: 'object', properties, required } } }))
