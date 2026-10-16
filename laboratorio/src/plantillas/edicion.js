/* El cerco de la edición por IA: las ÚNICAS operaciones que Shifu puede hacer sobre la pantalla de inicio.
 * Funciones puras (sin React, sin API): reciben el estado y devuelven el nuevo estado o un error legible.
 * Las usa el servidor del laboratorio (servidor/chat.js) al ejecutar las herramientas del modelo, y nada más las cambia.
 * Lo que el modelo pide fuera de esto (una vista que no existe, un campo equivocado) se rechaza aquí, no se dibuja mal. */
import { VISTAS, revisarVista, camposDe, validarPlantilla, TIPOS_CAMPO } from './validar.js'
import { compatibles, GRAFICOS, opcionesPorDefecto } from './graficos.jsx'
import { FUENTES, esHex, tokensDeMarca, revisarLogo } from './marca.js'

/** Biblioteca de pestañas (D30, nivel 2): secciones listas (cobros, inventario…) que pasan servidor/calidad-pestanas.mjs. */
export const PESTANAS = Object.fromEntries(Object.values(import.meta.glob('./biblioteca-pestanas/*.js', { eager: true })).map((m) => m.default).filter(Boolean).map((p) => [p.id, p]))

export const ANCHOS_COL = [3, 4, 6, 8, 12]
export const ALTO_MAX = 4
const VISTAS_INICIO = ['kpis', 'tablero', 'agenda', 'vencimientos', 'grafico', 'tabla']
// id nuevo e irrepetible: si se reusara el de un bloque quitado, la animación lo confundiría con el viejo.
const nuevoUid = () => `n${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`
const ajustarAncho = (a) => ANCHOS_COL.reduce((m, x) => (Math.abs(x - a) < Math.abs(m - a) ? x : m), 6)

/** Los rangos que dibuja un bloque de vencimientos (la misma regla que la vista en vistas.jsx). */
export const rangosDe = (opciones = {}) => opciones.rangos
  || [{ desde: null, hasta: -1 }, { desde: 0, hasta: 7 }, ...((opciones.dias || 30) > 7 ? [{ desde: 8, hasta: opciones.dias || 30 }] : [])]

// Acepta el id, el título o el título escrito de otra forma ("inventario productos limpieza" → inventario_productos_limpiez…).
function seccionDe(plantilla, id) {
  const q = slug(id)
  return plantilla.secciones.find((s) => s.id === id || s.titulo.toLowerCase() === String(id || '').toLowerCase())
    || plantilla.secciones.find((s) => slug(s.titulo) === q || s.id === q.slice(0, 30) || (q.length > 5 && (s.id.startsWith(q.slice(0, 25)) || q.startsWith(s.id))))
}
function bloqueDe(estado, uid) { return estado.bloques.find((b) => b.uid === uid) }

/** Dónde cae de verdad cada bloque en la rejilla (12 columnas, acomodo "dense" como el CSS): lo calcula el código,
 * para que Shifu no diga "a la derecha" si quedó abajo a la izquierda. Devuelve { uid: {fila, col, lado} }. */
export function ubicar(bloques) {
  const out = {}
  for (const [uid, p] of Object.entries(colocar(bloques).pos)) {
    const centro = p.c + p.w / 2
    out[uid] = { fila: p.f + 1, lado: p.w === 12 ? 'ancho completo' : centro <= 4.5 ? 'izquierda' : centro >= 7.5 ? 'derecha' : 'centro' }
  }
  return out
}

/** Simula el acomodo "dense" del CSS: { pos: {uid: {f, c, w, h}}, celdas: celdas[fila][col] = uid | undefined }. */
function colocar(bloques) {
  const celdas = []
  const libre = (f, c, w, h) => { for (let y = f; y < f + h; y++) for (let x = c; x < c + w; x++) if (celdas[y]?.[x]) return false; return c + w <= 12 }
  const pos = {}
  for (const b of bloques) {
    const w = Math.max(1, Math.min(12, b.ancho || 6)), h = b.vista === 'kpis' ? 1 : b.alto || 1
    let f = 0, c = 0
    for (;; f++) { c = [...Array(13 - w).keys()].find((x) => libre(f, x, w, h)); if (c !== undefined) break }
    for (let y = f; y < f + h; y++) { celdas[y] ||= []; for (let x = c; x < c + w; x++) celdas[y][x] = b.uid }
    pos[b.uid] = { f, c, w, h }
  }
  return { pos, celdas }
}

/** Acomodo automático (D38): tapa los huecos que dejan los cambios. Lo calcula el código, nunca el modelo.
 * Cada hueco lo llena el bloque vecino: el de la IZQUIERDA se ensancha (si todas sus filas tienen ese espacio libre) o,
 * si no, el de ARRIBA crece una fila hacia abajo. Los bloques en `fijos` (los que la persona acaba de redimensionar)
 * no se tocan, para no deshacer lo que pidió. No cambia el orden ni quita nada. */
export function acomodar(bloques, fijos = new Set()) {
  let bs = bloques.map((b) => ({ ...b }))
  const imposibles = new Set()
  for (let vuelta = 0; vuelta < 40; vuelta++) {
    const { pos, celdas } = colocar(bs)
    let hueco = null
    for (let f = 0; f < celdas.length && !hueco; f++) for (let c = 0; c < 12; c++) if (!celdas[f]?.[c] && !imposibles.has(`${f},${c}`)) { hueco = { f, c }; break }
    if (!hueco) break
    const { f, c } = hueco
    let largo = 0; while (c + largo < 12 && !celdas[f]?.[c + largo]) largo++
    const izq = c > 0 && celdas[f]?.[c - 1], arriba = f > 0 && celdas[f - 1]?.[c]
    const libreEn = (y, x0, n) => { for (let x = x0; x < x0 + n; x++) if (celdas[y]?.[x]) return false; return true }
    let hecho = false
    if (izq && !fijos.has(izq)) {
      const p = pos[izq]
      if ([...Array(p.h).keys()].every((dy) => libreEn(p.f + dy, c, largo))) { bs = bs.map((b) => (b.uid === izq ? { ...b, ancho: p.w + largo } : b)); hecho = true }
    }
    if (!hecho && arriba && !fijos.has(arriba)) {
      const p = pos[arriba], b = bs.find((x) => x.uid === arriba)
      if (b.vista !== 'kpis' && p.h < ALTO_MAX && p.f + p.h === f && libreEn(f, p.c, p.w)) { bs = bs.map((x) => (x.uid === arriba ? { ...x, alto: p.h + 1 } : x)); hecho = true }
    }
    if (!hecho) imposibles.add(`${f},${c}`)
  }
  return bs
}
const ubicacion = (u) => (u ? `fila ${u.fila}, ${u.lado}` : '')

const slug = (t) => String(t || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '').slice(0, 30) || 'x'

/** Lo que Shifu cambió DENTRO de una sección (D28): campos quitados o renombrados, opciones de un estado, y cómo se ven
 * su ficha y su tarjeta del tablero. Los datos nunca se borran: un campo quitado solo deja de mostrarse. */
function ajustarSeccion(x, e) {
  if (!x.campos) return x
  const quitados = e.camposQuitados?.[x.id] || [], nombres = e.nombresCampo?.[x.id] || {}, opciones = e.opcionesEstado?.[x.id] || {}
  return { ...x,
    campos: x.campos.filter((c) => !quitados.includes(c.id)).map((c) => ({ ...c, ...(nombres[c.id] ? { nombre: nombres[c.id] } : {}), ...(opciones[c.id] ? { opciones: opciones[c.id] } : {}) })),
    ...(e.ficha?.[x.id] ? { ficha: e.ficha[x.id] } : {}), ...(e.tarjeta?.[x.id] ? { tarjeta: e.tarjeta[x.id] } : {}) }
}

/** Cómo se ve la ficha de un registro: la que definió la persona o, por defecto, todos sus campos en un grupo. */
export function fichaDe(seccion, campos) {
  const ids = new Set(campos.map((c) => c.id))
  const f = seccion.ficha
  const grupos = (f?.grupos || [{ titulo: 'Datos', campos: campos.map((c) => c.id) }]).map((g) => ({ ...g, campos: g.campos.filter((id) => ids.has(id)) })).filter((g) => g.campos.length)
  return { grupos, relacionados: f?.relacionados ?? true, linea_tiempo: f?.linea_tiempo ?? true }
}

/** La plantilla tal como la ve la persona: la base + lo que Shifu le cambió a la estructura (secciones nuevas, campos
 * agregados, secciones ocultas o renombradas). La usan la pantalla, el validador y el modelo: una sola verdad. */
export function plantillaEfectiva(plantilla, estado = {}) {
  const e = estado.estructura || {}
  const base = plantilla.secciones.filter((x) => !(e.ocultas || []).includes(x.id)).map((x) => ajustarSeccion({ ...x,
    ...(e.titulos?.[x.id] ? { titulo: e.titulos[x.id] } : {}),
    ...(x.campos && e.campos?.[x.id] ? { campos: [...x.campos, ...e.campos[x.id]] } : {}) }, e))
  const nuevas = (e.secciones || []).filter((x) => !(e.ocultas || []).includes(x.id)).map((x) => ajustarSeccion({ ...x, campos: [...x.campos, ...(e.campos?.[x.id] || [])], ...(e.titulos?.[x.id] ? { titulo: e.titulos[x.id] } : {}) }, e))
  const i = base.findIndex((x) => x.grupo > 0)
  return { ...plantilla, secciones: i < 0 ? [...base, ...nuevas] : [...base.slice(0, i), ...nuevas, ...base.slice(i)] }
}

/** Toma de requerimientos de diseño (estilo Alan): la ficha vive en el estado, no en el prompt. */
export const HERRAMIENTAS_BLOQUEADAS_EN_TOMA = new Set([
  'agregar_bloque', 'cambiar_visual', 'cambiar_tamano', 'mover_bloque', 'quitar_bloque', 'cambiar_rangos',
  'cambiar_marca', 'usar_logo', 'restablecer_marca', 'crear_seccion', 'agregar_campo', 'renombrar_seccion', 'quitar_seccion',
  'cambiar_ficha', 'cambiar_tarjeta', 'quitar_campo', 'renombrar_campo', 'cambiar_opciones_estado',
])
const GRAF_ALIAS = { barras: 'barras', barra: 'barras', columnas: 'columnas', dona: 'dona', pastel: 'pastel', linea: 'linea', 'línea': 'linea' }
const NOMBRE_VISTA = { kpis: 'resumen con cifras', tablero: 'tablero por etapas', agenda: 'agenda', vencimientos: 'por vencer', grafico: 'gráfica', tabla: 'lista' }
const PREGUNTA_FALTA = {
  objetivo: '¿Para qué quieres esta pantalla de inicio? (por ejemplo controlar ventas, ver cobros, seguir clientes…)',
  secciones: '¿Qué partes de tu negocio quieres ver ahí? (ventas, clientes, inventario, lo que uses a diario…)',
  bloques: '¿Qué quieres ver en tu inicio y de qué parte? (por ejemplo: un resumen de pagos, una gráfica de los estados de tus miembros, la lista de lo que vence…)',
}

/** Construye el inicio DESDE LA FICHA confirmada, por código (sin el modelo): reemplaza los bloques, acomoda tamaños
 * (resumen, tablero y agenda a lo ancho; lo demás a media fila; si queda uno solo en su fila, a lo ancho) y aplica la marca. */
export function construirDesdeFicha(plantillaBase, estado) {
  const f = estado.toma.ficha
  const ANCHO = ['kpis', 'tablero', 'agenda']
  const medios = f.bloques.filter((b) => !ANCHO.includes(b.vista))
  const ultimoMedio = medios.length % 2 ? medios[medios.length - 1] : null
  const base = Date.now().toString(36)
  const bloques = f.bloques.map((b, i) => ({ uid: `f${base}${i}`, seccion: b.seccion, vista: b.vista, opciones: b.opciones || {},
    ancho: b.tamano?.ancho || (ANCHO.includes(b.vista) || b === ultimoMedio ? 12 : 6), alto: b.vista === 'kpis' ? 1 : b.tamano?.alto || 2 }))
  const m = f.marca || {}
  const marca = { ...(estado.marca || {}), ...(esHex(m.primario) ? { primario: m.primario } : {}), ...(esHex(m.secundario) ? { secundario: m.secundario } : {}),
    ...(m.tipografia && FUENTES[m.tipografia] ? { fuenteTitulos: m.tipografia, fuenteTexto: m.tipografia } : {}) }
  const nuevo = { ...estado, bloques, marca, vista: 'inicio', toma: tomaVacia() }
  const errores = validarPlantilla({ ...plantillaEfectiva(plantillaBase, nuevo), inicio: bloques })
  return { estado: errores.length ? estado : nuevo, errores }
}

export function tomaVacia() {
  return { activa: false, fase: 'juntando', ficha: { objetivo: '', secciones: [], bloques: [], marca: {}, restricciones: [] }, notas: [], preguntadas: [], rechazo: false }
}

export function asegurarToma(estado) {
  if (!estado.toma) return { ...estado, toma: tomaVacia() }
  return estado
}

/** Obligatorios de la ficha antes de confirmar. */
export function faltantesToma(plantillaBase, estado) {
  const f = estado.toma?.ficha
  if (!estado.toma?.activa || !f) return []
  const out = []
  if (!String(f.objetivo || '').trim()) out.push({ campo: 'objetivo', pregunta: PREGUNTA_FALTA.objetivo })
  if (!f.bloques?.length) out.push({ campo: 'bloques', pregunta: PREGUNTA_FALTA.bloques })
  return out
}

/** Resumen en palabras (sin ids técnicos) para la confirmación. */
export function resumenDeToma(plantillaBase, estado) {
  const plantilla = plantillaEfectiva(plantillaBase, estado)
  const porId = Object.fromEntries(plantilla.secciones.map((s) => [s.id, s]))
  const f = estado.toma?.ficha || {}
  const lineas = []
  if (f.objetivo) lineas.push(`Vas a tener un inicio para ${f.objetivo}.`)
  const secs = (f.secciones || []).map((id) => porId[id]?.titulo || id).filter(Boolean)
  if (secs.length) lineas.push(`Partes del menú que importan: ${secs.join(', ')}.`)
  for (const [n, b] of (f.bloques || []).entries()) {
    const tit = porId[b.seccion]?.titulo || 'una sección'
    let det = NOMBRE_VISTA[b.vista] || b.vista
    if (b.vista === 'grafico' && b.opciones?.tipo) det = `${GRAFICOS[b.opciones.tipo]?.nombre || 'gráfica'} en ${tit}`
    else det = `${det} de ${tit}`
    if (b.tamano?.ancho || b.tamano?.alto) det += ` (${b.tamano.ancho ? `ancho ${b.tamano.ancho}` : ''}${b.tamano.ancho && b.tamano.alto ? ', ' : ''}${b.tamano.alto ? `alto ${b.tamano.alto}` : ''})`.replace(/\(\s*,/,'(')
    lineas.push(`${n + 1}. ${det}`)
  }
  const m = f.marca || {}
  const marca = [m.primario && `color principal ${m.primario}`, m.secundario && `acento ${m.secundario}`, m.tipografia && `letra ${m.tipografia}`].filter(Boolean)
  if (marca.length) lineas.push(`Marca: ${marca.join(', ')}.`)
  if (f.restricciones?.length) lineas.push(`Restricciones: ${f.restricciones.join('; ')}.`)
  if (estado.toma?.notas?.length) lineas.push(`Notas: ${estado.toma.notas.join('; ')}.`)
  return lineas.join(' ') || 'Aún no hay nada en la ficha.'
}

/** Lo que ve el chat (tarjeta compacta): campos llenos o pendientes, sin ids. */
export function tarjetaToma(plantillaBase, estado) {
  const plantilla = plantillaEfectiva(plantillaBase, estado)
  const porId = Object.fromEntries(plantilla.secciones.map((s) => [s.id, s]))
  const f = estado.toma?.ficha || {}
  const falta = new Set(faltantesToma(plantillaBase, estado).map((x) => x.campo))
  const filas = [
    { etiqueta: 'Objetivo', texto: f.objetivo || '—', pendiente: falta.has('objetivo') },
    { etiqueta: 'Secciones', texto: (f.secciones || []).map((id) => porId[id]?.titulo || id).join(', ') || '—', pendiente: falta.has('secciones') },
    { etiqueta: 'Bloques en inicio', texto: (f.bloques || []).map((b) => `${NOMBRE_VISTA[b.vista] || b.vista} (${porId[b.seccion]?.titulo || '?'})`).join(' · ') || '—', pendiente: falta.has('bloques') },
  ]
  const m = f.marca || {}
  const marcaTxt = [m.primario, m.secundario, m.tipografia].filter(Boolean).join(' · ')
  if (marcaTxt || f.restricciones?.length) filas.push({ etiqueta: 'Marca / extras', texto: [marcaTxt, ...(f.restricciones || [])].filter(Boolean).join(' · ') || '—', pendiente: false })
  return { fase: estado.toma?.fase, filas, notas: estado.toma?.notas || [] }
}

/** Sí/no y ajustes en confirmación; digresión detectada por código (sin otro modelo). */
// Pedido de DISEÑAR o REHACER una pantalla completa (no un cambio puntual): lo detecta el código, no el modelo.
const PIDE_DISENO = /(?<!\p{L})(dis[eé][ñn]a(me|r)?|redis[eé][ñn]a|rehaz|rehacer|arma(me)?\s+(un|mi|el)\s+(nuevo\s+)?(inicio|crm|tablero|pantalla)|(un|mi)\s+inicio\s+nuevo|nuevo\s+inicio|empecemos\s+de\s+cero)(?!\p{L})/iu
const ABANDONA = /(?<!\p{L})(olv[ií]d(a|alo|ate)|d[eé]jalo(\s+as[ií]|\s+como\s+est[aá])?|ya\s+no\s+(quiero|lo\s+hagas)|mejor\s+no|cancela(lo)?|dejemos\s+eso)(?!\p{L})/iu

export function prepararTurnoToma(estado, texto) {
  let e = asegurarToma(estado)
  if (!e.toma.activa && PIDE_DISENO.test(texto)) {
    // Se abre por código: el modelo solo llena la ficha con lo que dijo la persona.
    // Objetivo = lo que viene después de "para …" ("diséñame un inicio para controlar mis cobros" → "controlar mis cobros"), sin lo que ya son bloques.
    const obj = (String(texto).match(/\bpara\s+([^:.;]+)/i)?.[1] || '').trim().slice(0, 120)
    e = { ...e, toma: { ...tomaVacia(), activa: true, fase: 'juntando', ficha: { ...tomaVacia().ficha, objetivo: obj } } }
    return { estado: e, aviso: 'El código abrió la ficha de diseño con este pedido (no llames abrir_toma). NO toques la pantalla: anota con anotar_ficha SOLO lo que la persona dijo en este mensaje (bloques: qué ver y de qué sección; marca si la dijo) y luego haz la pregunta de FALTA.', digresion: false }
  }
  const t = e.toma
  if (!t.activa) return { estado: e, aviso: null, digresion: false }
  if (ABANDONA.test(texto)) {
    return { estado: { ...e, toma: tomaVacia() }, aviso: 'La persona abandonó la ficha: el código ya la cerró. Dile en una línea que quedó todo como estaba (la pantalla NO cambió) y no toques nada.', digresion: true }
  }
  const digresion = /¿?\s*qué hora|qué hora es|cuántas? son|clima|tiempo hace|temperatura/i.test(texto)
  let aviso = null
  if (t.fase === 'confirmando') {
    if (/^\s*(s[ií]|si|dale|ok|claro|confirmo|hazlo|perfecto|adelante)(?:\s|[.!,]|$)/iu.test(texto)) {
      return { estado: e, aviso: null, digresion: false, construir: true }
    } else if (/\b(no|mejor|cambia|cambiar|en vez|prefiero)\b/i.test(texto)) {
      t.fase = 'juntando'
      t.rechazo = true
      // (el pedido de ajuste no se guarda como nota: se aplica con quitar_de_ficha/anotar_bloque)
      aviso = 'La persona pidió un ajuste. Si es reemplazar algo («mejor X en vez de Y»): quitar_de_ficha del bloque Y y anotar_bloque con X, las dos en este turno. Si es agregar: anotar_bloque. Usa solo lo que dijo en ESTE mensaje.'
    }
  }
  return { estado: e, aviso, digresion }
}

function pistaToma(plantillaBase, estado, mutar = false) {
  const t = estado.toma
  if (!t?.activa || t.fase === 'construida') return null
  const falt = faltantesToma(plantillaBase, estado)
  if (t.fase === 'juntando') {
    if (!falt.length) {
      if (mutar && !t.rechazo) t.fase = 'confirmando'
      if (t.rechazo) return `Ajuste pendiente: anota con anotar_ficha lo que pidieron y vuelve a resumir cuando esté claro.`
      return `RESUMEN (muéstralo en palabras sencillas y pregunta «¿Lo armo así?»):\n${resumenDeToma(plantillaBase, estado)}`
    }
    const f = falt[0]
    if (mutar && !t.preguntadas.includes(f.campo)) t.preguntadas.push(f.campo)
    return `FALTA: ${f.campo} — pregunta sugerida: ${f.pregunta}`
  }
  if (t.fase === 'confirmando') {
    return `RESUMEN (muéstralo y pregunta «¿Lo armo así?»):\n${resumenDeToma(plantillaBase, estado)}`
  }
  return null
}

/** Tras herramientas en un turno: una sola pista (FALTA o RESUMEN); puede avanzar la fase. */
export function senalTomaTrasVuelta(plantillaBase, estado) {
  return pistaToma(plantillaBase, estado, true)
}

function instruccionTomaEnContexto(plantillaBase, estado) {
  const t = estado.toma
  if (!t?.activa) return null
  if (t.fase === 'construida') return 'La ficha ya está confirmada: aplica el diseño con las herramientas de pantalla según estado.toma.ficha.'
  return pistaToma(plantillaBase, estado, false)
}

function validarValorFicha(plantilla, campo, valor) {
  const porId = Object.fromEntries(plantilla.secciones.map((s) => [s.id, s]))
  const mal = (error) => ({ ok: false, error })
  const bien = (value) => ({ ok: true, value })
  switch (campo) {
    case 'objetivo': {
      const t = String(valor || '').trim()
      if (!t) return mal('el objetivo no puede estar vacío.')
      return bien(t.slice(0, 200))
    }
    case 'seccion': {
      const s = seccionDe(plantilla, valor)
      if (!s) return mal(`la sección «${valor}» no existe. Secciones: ${plantilla.secciones.filter((x) => x.campos || x.fuente).map((x) => x.titulo).join(', ')}.`)
      return bien(s.id)
    }
    case 'bloque': {
      const b = valor || {}
      const s = seccionDe(plantilla, b.seccion)
      if (!s) return mal(`la sección «${b.seccion}» no existe.`)
      if (!VISTAS_INICIO.includes(b.vista)) return mal(`vista «${b.vista}» no válida; usa: ${VISTAS_INICIO.join(', ')}.`)
      const op = b.opciones || {}
      if (b.vista === 'grafico') {
        const posibles = compatibles(camposDe(s, porId)).map((g) => g.id)
        if (!op.tipo || !GRAFICOS[op.tipo]) return mal(`falta opciones.tipo de gráfico válido (posibles con ${s.titulo}: ${posibles.join(', ')}).`)
        if (!posibles.includes(op.tipo)) return mal(`«${GRAFICOS[op.tipo].nombre}» no se puede con ${s.titulo}.`)
      } else {
        const errs = revisarVista(b.vista, op, camposDe(s, porId), `«${s.titulo}»`)
        if (errs.length) return mal(errs.join(' '))
      }
      if (b.tamano) {
        if (b.tamano.ancho != null && !ANCHOS_COL.includes(Number(b.tamano.ancho))) return mal(`ancho debe ser uno de ${ANCHOS_COL.join(', ')}.`)
        if (b.tamano.alto != null && (b.tamano.alto < 1 || b.tamano.alto > ALTO_MAX)) return mal(`alto entre 1 y ${ALTO_MAX}.`)
      }
      return bien({ ...b, seccion: s.id })
    }
    case 'marca_primario': case 'marca_secundario': {
      const h = String(valor || '').trim()
      if (!esHex(h)) return mal('debe ser un color hex como #1E40AF.')
      return bien(h.startsWith('#') ? h : `#${h}`)
    }
    case 'tipografia': {
      const fnt = String(valor || '').trim()
      if (!FUENTES[fnt]) return mal(`tipografía «${fnt}» no disponible (${Object.keys(FUENTES).join(', ')}).`)
      return bien(fnt)
    }
    case 'restriccion': {
      const t = String(valor || '').trim()
      if (!t) return mal('la restricción no puede estar vacía.')
      return bien(t.slice(0, 120))
    }
    default:
      return mal(`campo «${campo}» no reconocido (objetivo, seccion, bloque, marca_primario, marca_secundario, tipografia, restriccion).`)
  }
}

/** Lo que el modelo ve de la pantalla: bloques actuales y, por sección, sus campos y las vistas que admite. */
export function describirPantalla(plantillaBase, estado) {
  const plantilla = plantillaEfectiva(plantillaBase, estado)
  const porId = Object.fromEntries(plantilla.secciones.map((s) => [s.id, s]))
  const tomaCtx = estado.toma?.activa ? {
    activa: true,
    fase: estado.toma.fase,
    ficha: estado.toma.ficha,
    notas: estado.toma.notas,
    faltantes: faltantesToma(plantillaBase, estado).map((x) => x.campo),
    instruccion_turno: instruccionTomaEnContexto(plantillaBase, estado),
  } : { activa: false }
  return {
    plantilla: plantilla.nombre,
    // Lo que se puede deshacer: cada pedido que cambió algo, con lo que dijo la persona y qué cambió (medido por el código).
    pedidos_anteriores: (estado.puntos || []).map((p) => ({ pedido: p.n, dijo: p.antes_de, cambio: p.cambio || ['bloques', 'marca', 'estructura'], hora: p.hora })),
    marca: { ...(estado.marca || {}), logo: estado.marca?.logo ? '(tiene logo)' : '(sin logo)', fuentes_permitidas: Object.keys(FUENTES), nota: 'Branding: cualquier color (hex) de fondo, superficie, texto, principal y secundario, y tipografía de títulos y de texto. El código ajusta lo que no se lea.' },
    rejilla: 'Inicio en 12 columnas. ancho ∈ [3,4,6,8,12] (3 = cuatro por fila, 12 = ancho completo). alto ∈ 1..4 filas. Todo debe caber en una pantalla: más bloques = bloques más bajos.',
    bloques: estado.bloques.map((b, i) => ({ id: b.uid, posicion: i + 1, donde_se_ve: ubicacion(ubicar(estado.bloques)[b.uid]), vista: b.vista, seccion: b.seccion, titulo_seccion: porId[b.seccion]?.titulo, opciones: b.opciones, ancho: b.ancho, alto: b.alto,
      // Los grupos que la persona VE ahora (los por defecto no viven en opciones): sin esto el modelo no sabe qué conservar.
      ...(b.vista === 'vencimientos' ? { grupos_actuales: rangosDe(b.opciones).map((r) => (r.desde === null ? 'Vencidos {vencidos:true}' : `De ${r.desde} a ${r.hasta} días {desde:${r.desde},hasta:${r.hasta}}`)) } : {}) })),
    secciones: plantilla.secciones.filter((s) => s.campos || s.fuente).map((s) => ({ id: s.id, titulo: s.titulo,
      campos: camposDe(s, porId).map((c) => ({ id: c.id, nombre: c.nombre, tipo: c.tipo, ...(c.opciones ? { opciones: c.opciones } : {}) })),
      ficha: fichaDe(s, camposDe(s, porId)), ...(s.tarjeta ? { tarjeta: s.tarjeta.campos } : {}),
      // Qué gráficos se pueden dibujar con ESTA sección (lo decide el código, no el modelo).
      graficos_posibles: compatibles(camposDe(s, porId)).map((g) => `${g.id} (${g.nombre})`) })),
    vistas: Object.fromEntries(VISTAS_INICIO.map((v) => [v, { requiere: VISTAS[v].requiere, opcional: Object.keys(VISTAS[v].opcional || {}) }])),
    grafico: 'vista "grafico" con opciones {tipo: <id de graficos_posibles>} y opcionalmente {funcion: conteo|suma|promedio|mediana|minimo|maximo|moda|desviacion, valor: campo numérico, agrupar: campo o "mes", meta, top}. La vieja "grafica" (barras/dona/linea) sigue existiendo en bloques que ya la tienen.',
    toma: tomaCtx,
    // Pestañas listas de la biblioteca (para crear_seccion con «desde»): id y cómo la suele pedir la gente.
    pestanas_base: Object.values(PESTANAS).map((p) => `${p.id} (${p.palabras.slice(0, 2).join(', ')})`),
  }
}

/** Ejecuta UNA operación. Devuelve { estado, ok, resultado } — resultado es el texto que lee el modelo. */
export function ejecutar(plantilla, estado, nombre, args = {}, contexto = {}) {
  const r0 = ejecutarSin(plantilla, estado, nombre, args, contexto)
  if (!r0.ok || !r0.estado.bloques) return r0
  // Acomodo automático tras cada cambio de bloques; lo que la persona acaba de redimensionar queda como lo pidió.
  // Solo lo redimensionado a pedido queda fijo; al agregar, el modelo siempre manda un ancho y eso dejaba huecos.
  const fijos = new Set(nombre === 'cambiar_tamano' ? [args.bloque] : [])
  let r = r0
  if (r0.estado.bloques !== estado.bloques) {
    const acomodados = acomodar(r0.estado.bloques, fijos)
    const tocados = acomodados.filter((b, i) => b.ancho !== r0.estado.bloques[i].ancho || b.alto !== r0.estado.bloques[i].alto).map((b) => b.uid)
    // Hecho calculado, no instrucción: el modelo sabe que el acomodo ya ocurrió (antes «compensaba» achicando otro bloque).
    r = { ...r0, estado: { ...r0.estado, bloques: acomodados }, resultado: tocados.length ? `${r0.resultado} El código ya acomodó solo ${tocados.join(', ')} para que no quede hueco.` : r0.resultado }
  }
  // Cada resultado dice dónde quedó TODO de verdad: el modelo describe eso, no lo que supone.
  const u = ubicar(r.estado.bloques)
  return { ...r, resultado: `${r.resultado} Así se ve ahora: ${r.estado.bloques.map((b) => `${b.uid} (${b.vista}) → ${ubicacion(u[b.uid])}`).join('; ')}.` }
}

function ejecutarSin(plantillaBase, estado, nombre, args = {}, contexto = {}) {
  estado = asegurarToma(estado)
  const plantilla = plantillaEfectiva(plantillaBase, estado)
  const est = estado.estructura || {}
  const porId = Object.fromEntries(plantilla.secciones.map((s) => [s.id, s]))
  const no = (resultado) => ({ estado, ok: false, resultado: `ERROR: ${resultado}` })
  const si = (nuevo, resultado) => ({ estado: nuevo, ok: true, resultado })
  const tomaAbierta = estado.toma.activa && ['juntando', 'confirmando'].includes(estado.toma.fase)
  if (tomaAbierta && HERRAMIENTAS_BLOQUEADAS_EN_TOMA.has(nombre) && !contexto.digresion) {
    return no('primero termina y confirma la ficha de diseño (o ciérrala con cerrar_toma si ya no quieren diseñar).')
  }
  if (tomaAbierta && contexto.digresion && ['anotar_ficha', 'anotar_nota'].includes(nombre)) {
    return no('es una digresión: responde la charla y no anotes nada de este mensaje en la ficha.')
  }
  // Cambio de estructura: se valida la plantilla COMPLETA resultante; si algo queda inválido, no se aplica.
  const conEstructura = (nueva, resultado) => {
    const errores = validarPlantilla(plantillaEfectiva(plantillaBase, { ...estado, estructura: nueva }))
    return errores.length ? no(errores.join(' ')) : si({ ...estado, estructura: nueva }, resultado)
  }
  const conBloques = (bloques) => ({ ...estado, bloques })
  switch (nombre) {
    case 'quitar_bloque': {
      const b = bloqueDe(estado, args.bloque); if (!b) return no(`no existe el bloque «${args.bloque}». Usa los id de "bloques".`)
      // Quitar es lo único que borra algo de la pantalla: solo si la persona lo pidió en este mensaje. Si no, se le pregunta.
      // (sin candado por palabras: es reversible con los puntos de guardado internos)
      return si(conBloques(estado.bloques.filter((x) => x !== b)), `Quitado el bloque ${b.uid} (${b.vista} de ${porId[b.seccion]?.titulo}).`)
    }
    case 'agregar_bloque': case 'cambiar_visual': {
      const viejo = nombre === 'cambiar_visual' ? bloqueDe(estado, args.bloque) : null
      if (nombre === 'cambiar_visual' && !viejo) return no(`no existe el bloque «${args.bloque}».`)
      // Cambiar un bloque que NO es gráfica (resumen, tablero, lista…) por otra cosa es quitarlo: solo si lo pidieron.
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
      const dias = rangos.filter((r) => r.desde !== null).sort((x, y) => x.desde - y.desde)
      const pisados = dias.slice(1).map((r, i) => (r.desde <= dias[i].hasta ? `${dias[i].desde}-${dias[i].hasta} y ${r.desde}-${r.hasta}` : null)).filter(Boolean)
      return si(conBloques(estado.bloques.map((x) => (x === b ? { ...b, opciones: { ...b.opciones, rangos } } : x))),
        `Rangos del bloque ${b.uid}: ${rangos.map((r) => (r.desde === null ? 'Vencidos' : `${r.desde}-${r.hasta} días`)).join(', ')}.`
        + (pisados.length ? ` AVISO: se pisan (${pisados.join('; ')}): quien vence en esos días aparece en los dos grupos. Díselo a la persona en una línea y ofrece ajustarlo.` : ''))
    }
    case 'cambiar_marca': {
      const m = { ...(estado.marca || {}) }
      for (const k of ['primario', 'secundario', 'fondo', 'superficie', 'texto']) {
        if (args[k] === null || args[k] === '') delete m[k]
        else if (args[k] !== undefined) { if (!esHex(args[k])) return no(`«${k}» debe ser un color hexadecimal como #1E40AF (llegó «${args[k]}»).`); m[k] = args[k].startsWith('#') ? args[k] : `#${args[k]}` }
      }
      for (const k of ['fuenteTitulos', 'fuenteTexto']) {
        if (args[k] === null || args[k] === '') delete m[k]
        else if (args[k] !== undefined) { if (!FUENTES[args[k]]) return no(`la tipografía «${args[k]}» no está disponible. Disponibles: ${Object.keys(FUENTES).join(', ')}.`); m[k] = args[k] }
      }
      if (args.nombre !== undefined) m.nombre = String(args.nombre).slice(0, 40)
      // El código prueba la marca en los dos temas y dice qué tuvo que ajustar para que se lea.
      const ajustes = [...tokensDeMarca(m, 'claro').ajustes, ...tokensDeMarca(m, 'oscuro').ajustes]
      return si({ ...estado, marca: m }, `Marca aplicada: ${Object.entries(m).filter(([k]) => k !== 'logo').map(([k, v]) => `${k} ${v}`).join(', ') || 'base de Shifu'}.` + (ajustes.length ? ` AJUSTES para que se lea: ${ajustes.join('; ')}. Díselo en una línea.` : ''))
    }
    case 'usar_logo': {
      const err = revisarLogo(contexto.imagen)
      if (err) return no(err)
      return si({ ...estado, marca: { ...(estado.marca || {}), logo: contexto.imagen } }, 'Logo puesto en el encabezado. En tema oscuro, si el logo es oscuro, se muestra una versión clara automática.')
    }
    case 'restablecer_marca':
      // (sin candado por palabras: es reversible con los puntos de guardado internos)
      return si({ ...estado, marca: {} }, 'Volvió el diseño base de Shifu (colores, fondos y tipografía originales, sin logo).')
    case 'crear_seccion': {
      // Desde la biblioteca: campos, vista y piezas ya probados (la IA no inventa campos cuando existe la pestaña).
      const base = args.desde ? PESTANAS[args.desde] : null
      if (args.desde && !base) return no(`no hay una pestaña base «${args.desde}». Las que hay: ${Object.keys(PESTANAS).join(', ')}. O créala con sus campos sin «desde».`)
      if (base) { args = { ...args, titulo: args.titulo || base.seccion.titulo, vista: base.seccion.vista, opciones: base.seccion.opciones, campos: base.seccion.campos } }
      const titulo = String(args.titulo || '').trim().slice(0, 28); if (!titulo) return no('falta el título de la sección.')
      if (plantilla.secciones.some((x) => x.titulo.toLowerCase() === titulo.toLowerCase())) return no(`ya existe una sección «${titulo}»: úsala o agrégale campos en vez de duplicarla.`)
      const campos = (args.campos || []).slice(0, 8).map((c) => ({ id: base ? c.id : slug(c.nombre), nombre: String(c.nombre).slice(0, 24), tipo: c.tipo, ...(c.opciones ? { opciones: c.opciones.slice(0, 7).map(String) } : {}), ...(c.ejemplos ? { ejemplos: c.ejemplos.slice(0, 12).map(String) } : {}), ...(c.rango ? { rango: c.rango } : {}) }))
      if (!campos.length) return no('una sección necesita al menos un campo.')
      const bad = campos.find((c) => !TIPOS_CAMPO.includes(c.tipo)); if (bad) return no(`el campo «${bad.nombre}» tiene tipo «${bad.tipo}»; tipos posibles: ${TIPOS_CAMPO.join(', ')}.`)
      let id = slug(titulo); while (plantilla.secciones.some((x) => x.id === id)) id += '_2'
      const vista = ['tabla', 'tablero', 'agenda', 'vencimientos'].includes(args.vista) ? args.vista : 'tabla'
      const secc = { id, titulo, grupo: args.grupo === 1 ? 1 : 0, icono: base?.seccion.icono || { tablero: 'tablero', agenda: 'calendario', vencimientos: 'reloj' }[vista] || 'tabla', vista, ...(args.opciones ? { opciones: args.opciones } : {}), campos }
      const r = conEstructura({ ...est, secciones: [...(est.secciones || []), secc] }, `Sección «${titulo}» creada (id ${id})${base ? ` desde la pestaña base «${base.id}»` : ''} con ${campos.length} campos: ${campos.map((c) => `${c.nombre} (${c.tipo})`).join(', ')}. Vista: ${vista}.`)
      if (!r.ok) return r
      if (!base || !args.con_piezas) return { ...r, resultado: `${r.resultado} Puedes ponerla en el inicio con agregar_bloque${base ? ' o creándola con con_piezas' : ''}.` }
      // Sus piezas sugeridas van al inicio (el acomodo automático tapa los huecos).
      const nuevas = base.piezas.map((w) => ({ ...w, uid: nuevoUid(), seccion: id, ancho: w.ancho || (['kpis', 'tablero', 'agenda'].includes(w.vista) ? 12 : 6), alto: w.vista === 'kpis' ? 1 : w.alto || 2 }))
      return { ...r, estado: { ...r.estado, bloques: [...r.estado.bloques, ...nuevas] }, resultado: `${r.resultado} En el inicio se agregaron ${nuevas.length} bloques: ${nuevas.map((b) => `${b.uid} (${b.vista === 'grafico' ? `gráfico ${b.opciones.tipo}` : b.vista})`).join(', ')}.` }
    }
    case 'agregar_campo': {
      const sec = seccionDe(plantilla, args.seccion); if (!sec?.campos) return no(`la sección «${args.seccion}» no existe o no tiene campos.`)
      if (!TIPOS_CAMPO.includes(args.tipo)) return no(`tipo «${args.tipo}» no existe (${TIPOS_CAMPO.join(', ')}).`)
      const c = { id: slug(args.nombre), nombre: String(args.nombre).slice(0, 24), tipo: args.tipo, ...(args.opciones ? { opciones: args.opciones.slice(0, 7).map(String) } : {}), ...(args.ejemplos ? { ejemplos: args.ejemplos.slice(0, 12).map(String) } : {}) }
      if (sec.campos.some((x) => x.id === c.id || x.nombre.toLowerCase() === c.nombre.toLowerCase())) return no(`«${sec.titulo}» ya tiene el campo «${c.nombre}».`)
      if (sec.campos.length >= 8) return no(`«${sec.titulo}» ya tiene 8 campos (el máximo).`)
      return conEstructura({ ...est, campos: { ...(est.campos || {}), [sec.id]: [...(est.campos?.[sec.id] || []), c] } }, `Campo «${c.nombre}» (${c.tipo}) agregado a «${sec.titulo}».`)
    }
    case 'renombrar_seccion': {
      const sec = seccionDe(plantilla, args.seccion); if (!sec) return no(`la sección «${args.seccion}» no existe.`)
      const titulo = String(args.titulo || '').trim().slice(0, 28); if (!titulo) return no('falta el nuevo nombre.')
      return conEstructura({ ...est, titulos: { ...(est.titulos || {}), [sec.id]: titulo } }, `«${sec.titulo}» ahora se llama «${titulo}».`)
    }
    case 'quitar_seccion': {
      const sec = seccionDe(plantilla, args.seccion); if (!sec) return no(`la sección «${args.seccion}» no existe.`)
      // (sin candado por palabras: es reversible con los puntos de guardado internos)
      const r = conEstructura({ ...est, ocultas: [...(est.ocultas || []), sec.id] }, `Sección «${sec.titulo}» quitada del menú (sus datos se conservan; se puede volver a mostrar). También se quitaron sus bloques del inicio.`)
      return r.ok ? { ...r, estado: { ...r.estado, bloques: r.estado.bloques.filter((b) => b.seccion !== sec.id) } } : r
    }
    // ── Ficha, tarjeta y campos (D28): todo editable por chat; el código cuida que nada quede huérfano ──
    case 'cambiar_ficha': {
      const sec = seccionDe(plantilla, args.seccion); if (!sec?.campos && !sec?.fuente) return no(`la sección «${args.seccion}» no existe o no tiene registros.`)
      const campos = camposDe(sec, porId), ids = new Set(campos.map((c) => c.id))
      const grupos = (args.grupos || []).map((g) => ({ titulo: String(g.titulo || 'Datos').slice(0, 28), campos: (g.campos || []).map(String) }))
      if (!grupos.length) return no('la ficha necesita al menos un grupo con campos.')
      const malos = grupos.flatMap((g) => g.campos).filter((id) => !ids.has(id))
      if (malos.length) return no(`estos campos no existen en ${sec.titulo}: ${malos.join(', ')}. Campos: ${campos.map((c) => `${c.id} (${c.nombre})`).join(', ')}.`)
      const usados = grupos.flatMap((g) => g.campos); const repetido = usados.find((id, i) => usados.indexOf(id) !== i)
      if (repetido) return no(`el campo «${repetido}» aparece en dos grupos: cada campo va en un solo grupo.`)
      const ficha = { grupos, relacionados: args.relacionados ?? true, linea_tiempo: args.linea_tiempo ?? true }
      const fuera = campos.filter((c) => !usados.includes(c.id)).map((c) => c.nombre)
      return conEstructura({ ...est, ficha: { ...(est.ficha || {}), [sec.id]: ficha } }, `Ficha de ${sec.titulo}: ${grupos.map((g) => `«${g.titulo}» (${g.campos.map((id) => campos.find((c) => c.id === id).nombre).join(', ')})`).join(' · ')}${fuera.length ? `. No se muestran: ${fuera.join(', ')}` : ''}. Relacionados: ${ficha.relacionados ? 'sí' : 'no'}. Línea de tiempo: ${ficha.linea_tiempo ? 'sí' : 'no'}.`)
    }
    case 'cambiar_tarjeta': {
      const sec = seccionDe(plantilla, args.seccion); if (!sec?.campos && !sec?.fuente) return no(`la sección «${args.seccion}» no existe o no tiene registros.`)
      const campos = camposDe(sec, porId), ids = (args.campos || []).map(String)
      if (!ids.length || ids.length > 4) return no('la tarjeta lleva de 1 a 4 campos (el primero es el título).')
      const malos = ids.filter((id) => !campos.some((c) => c.id === id)); if (malos.length) return no(`estos campos no existen en ${sec.titulo}: ${malos.join(', ')}.`)
      return conEstructura({ ...est, tarjeta: { ...(est.tarjeta || {}), [sec.id]: { campos: ids } } }, `Las tarjetas de ${sec.titulo} ahora muestran: ${ids.map((id) => campos.find((c) => c.id === id).nombre).join(', ')} (el primero como título).`)
    }
    case 'quitar_campo': {
      const sec = seccionDe(plantilla, args.seccion); if (!sec?.campos) return no(`la sección «${args.seccion}» no existe o no tiene campos propios.`)
      const c = sec.campos.find((x) => x.id === args.campo); if (!c) return no(`«${sec.titulo}» no tiene el campo «${args.campo}». Campos: ${sec.campos.map((x) => x.id).join(', ')}.`)
      if (sec.campos.length <= 1) return no(`«${sec.titulo}» se quedaría sin campos.`)
      const enBloques = (estado.bloques || []).filter((b) => b.seccion === sec.id && JSON.stringify(b.opciones || {}).includes(`"${c.id}"`))
      if (enBloques.length) return no(`el campo «${c.nombre}» lo usan estos bloques del inicio: ${enBloques.map((b) => `${b.uid} (${b.vista})`).join(', ')}. Cámbialos o quítalos primero (con permiso de la persona).`)
      const limpiar = (obj) => obj?.[sec.id] ? { ...obj, [sec.id]: { ...obj[sec.id], ...(obj[sec.id].campos ? { campos: obj[sec.id].campos.filter((x) => x !== c.id) } : {}), ...(obj[sec.id].grupos ? { grupos: obj[sec.id].grupos.map((g) => ({ ...g, campos: g.campos.filter((x) => x !== c.id) })) } : {}) } } : obj
      return conEstructura({ ...est, camposQuitados: { ...(est.camposQuitados || {}), [sec.id]: [...(est.camposQuitados?.[sec.id] || []), c.id] }, ficha: limpiar(est.ficha), tarjeta: limpiar(est.tarjeta) },
        `Campo «${c.nombre}» quitado de «${sec.titulo}» (sus datos se conservan; se puede volver a mostrar).`)
    }
    case 'renombrar_campo': {
      const sec = seccionDe(plantilla, args.seccion); if (!sec?.campos) return no(`la sección «${args.seccion}» no existe o no tiene campos propios.`)
      const c = sec.campos.find((x) => x.id === args.campo); if (!c) return no(`«${sec.titulo}» no tiene el campo «${args.campo}». Campos: ${sec.campos.map((x) => x.id).join(', ')}.`)
      const nombre = String(args.nombre || '').trim().slice(0, 24); if (!nombre) return no('falta el nuevo nombre.')
      if (sec.campos.some((x) => x !== c && x.nombre.toLowerCase() === nombre.toLowerCase())) return no(`«${sec.titulo}» ya tiene un campo «${nombre}».`)
      return conEstructura({ ...est, nombresCampo: { ...(est.nombresCampo || {}), [sec.id]: { ...(est.nombresCampo?.[sec.id] || {}), [c.id]: nombre } } }, `El campo «${c.nombre}» de «${sec.titulo}» ahora se llama «${nombre}».`)
    }
    case 'cambiar_opciones_estado': {
      const sec = seccionDe(plantilla, args.seccion); if (!sec?.campos) return no(`la sección «${args.seccion}» no existe o no tiene campos propios.`)
      const c = sec.campos.find((x) => x.id === args.campo); if (!c || c.tipo !== 'estado') return no(`«${args.campo}» no es un campo de estado de «${sec.titulo}». Estados: ${sec.campos.filter((x) => x.tipo === 'estado').map((x) => x.id).join(', ') || 'ninguno'}.`)
      const opciones = [...new Set((args.opciones || []).map((o) => String(o).trim().slice(0, 24)).filter(Boolean))]
      if (opciones.length < 2 || opciones.length > 8) return no('un estado lleva de 2 a 8 opciones.')
      const renombrar = Object.fromEntries(Object.entries(args.renombrar || {}).filter(([v, n]) => c.opciones.includes(v) && opciones.includes(n)))
      // Ninguna opción desaparece sin destino: los registros que la tenían pasan a la renombrada o a `pasar_a`.
      const sinDestino = c.opciones.filter((o) => !opciones.includes(o) && !renombrar[o])
      if (sinDestino.length && !opciones.includes(args.pasar_a)) return no(`las opciones ${sinDestino.map((o) => `«${o}»`).join(', ')} desaparecerían y sus registros quedarían sin estado. Di a cuál pasan con pasar_a (una de: ${opciones.join(', ')}) o usa renombrar {vieja: nueva}.`)
      const mapa = { ...(est.mapeoEstado?.[sec.id]?.[c.id] || {}), ...renombrar, ...Object.fromEntries(sinDestino.map((o) => [o, args.pasar_a])) }
      return conEstructura({ ...est, opcionesEstado: { ...(est.opcionesEstado || {}), [sec.id]: { ...(est.opcionesEstado?.[sec.id] || {}), [c.id]: opciones } }, mapeoEstado: { ...(est.mapeoEstado || {}), [sec.id]: { ...(est.mapeoEstado?.[sec.id] || {}), [c.id]: mapa } } },
        `«${c.nombre}» de «${sec.titulo}» ahora tiene: ${opciones.join(', ')}.${Object.keys(mapa).length ? ` Los registros pasan así: ${Object.entries(mapa).map(([v, n]) => `${v} → ${n}`).join(', ')}.` : ''}`)
    }
    case 'abrir_seccion': {
      const s = seccionDe(plantilla, args.seccion); if (!s && args.seccion !== 'inicio') return no(`la sección «${args.seccion}» no existe.`)
      return si({ ...estado, vista: s ? s.id : 'inicio' }, `Abierta la sección ${s ? s.titulo : 'Inicio'}.`)
    }
    case 'abrir_toma': {
      if (estado.toma.activa && ['juntando', 'confirmando'].includes(estado.toma.fase)) {
        return si(estado, 'La toma de diseño ya está abierta: sigue con anotar_ficha, no vuelvas a abrir.')
      }
      const t = { ...tomaVacia(), activa: true, fase: 'juntando' }
      if (args.objetivo) t.ficha.objetivo = String(args.objetivo).slice(0, 200)
      return si({ ...estado, toma: t }, 'Toma de diseño abierta. Anota solo lo que la persona dijo en este mensaje con anotar_ficha; ideas dudosas van en anotar_nota.')
    }
    case 'cerrar_toma':
      // Abandonar la ficha lo decide la persona, no el modelo (si no, el modelo la cierra para construir directo).
      if (!ABANDONA.test(contexto.texto || '')) return no('la persona no pidió dejar el diseño: sigue con la ficha (anota lo que pidió) y no la cierres.')
      return si({ ...estado, toma: tomaVacia() }, 'Toma de diseño cerrada. La pantalla no cambió por la ficha.')
    case 'anotar_nota': {
      if (!estado.toma.activa) return no('no hay una toma de diseño abierta.')
      const n = String(args.texto || '').trim().slice(0, 240)
      if (!n) return no('falta el texto de la nota.')
      const t = { ...estado.toma, notas: [...estado.toma.notas, n] }
      return si({ ...estado, toma: t }, 'Nota guardada (no es un dato confirmado de la ficha).')
    }
    case 'anotar_bloque': {
      // La IA dice en simple QUÉ ver y DE QUÉ parte; el código lo traduce al bloque técnico con valores razonables.
      if (!estado.toma.activa) return no('no hay una ficha de diseño abierta.')
      if (estado.toma.fase === 'construida') return no('la ficha ya está confirmada.')
      const sec = seccionDe(plantilla, args.seccion); if (!sec || !(sec.campos || sec.fuente)) return no(`no encuentro «${args.seccion}». Partes: ${plantilla.secciones.filter((x) => x.campos || x.fuente).map((x) => x.titulo).join(', ')}.`)
      const campos = camposDe(sec, Object.fromEntries(plantilla.secciones.map((x) => [x.id, x])))
      const estadoC = campos.find((c) => c.tipo === 'estado'), fecha = campos.find((c) => c.tipo === 'fecha'), dinero = campos.find((c) => ['dinero', 'numero'].includes(c.tipo)), texto = campos.find((c) => c.tipo === 'texto')
      const posibles = compatibles(campos).map((g) => g.id)
      let bloque
      switch (args.que) {
        case 'resumen': bloque = { vista: 'kpis', seccion: sec.id, opciones: { ...(estadoC ? { por: estadoC.id } : {}), ...(dinero?.tipo === 'dinero' ? { suma: dinero.id } : {}) } }; break
        case 'grafica': {
          const pedido = args.grafico && posibles.includes(args.grafico) ? args.grafico : null
          if (args.grafico && !pedido) return no(`«${args.grafico}» no se puede con ${sec.titulo}. Posibles: ${posibles.join(', ')}.`)
          const tipo = pedido || (estadoC && posibles.includes('dona') ? 'dona' : posibles[0])
          bloque = { vista: 'grafico', seccion: sec.id, opciones: { ...opcionesPorDefecto(tipo, campos), tipo } }; break
        }
        case 'lista': bloque = { vista: 'tabla', seccion: sec.id, opciones: {} }; break
        case 'tablero': if (!estadoC) return no(`${sec.titulo} no tiene un campo de estado para armar un tablero.`); bloque = { vista: 'tablero', seccion: sec.id, opciones: { por: estadoC.id, ...(texto ? { titulo: texto.id } : {}) } }; break
        case 'por_vencer': if (!fecha) return no(`${sec.titulo} no tiene fechas.`); bloque = { vista: 'vencimientos', seccion: sec.id, opciones: { fecha: fecha.id, ...(texto ? { titulo: texto.id } : {}), dias: 30 } }; break
        case 'agenda': if (!fecha) return no(`${sec.titulo} no tiene fechas.`); bloque = { vista: 'agenda', seccion: sec.id, opciones: { fecha: fecha.id, ...(texto ? { titulo: texto.id } : {}), dias: 7 } }; break
        default: return no('«que» debe ser: resumen, grafica, lista, tablero, por_vencer o agenda.')
      }
      const err = revisarVista(bloque.vista, bloque.opciones, campos, `«${sec.titulo}»`); if (err.length) return no(err.join(' '))
      const ficha = { ...estado.toma.ficha, bloques: [...estado.toma.ficha.bloques, bloque], secciones: [...new Set([...estado.toma.ficha.secciones, sec.id])] }
      const t = { ...estado.toma, ficha, fase: estado.toma.fase === 'confirmando' ? 'juntando' : estado.toma.fase, rechazo: false }
      return si({ ...estado, toma: t }, `Anotado en la ficha: ${args.que}${bloque.opciones.tipo ? ` (${GRAFICOS[bloque.opciones.tipo]?.nombre})` : ''} de ${sec.titulo}.`)
    }
    case 'quitar_de_ficha': {
      if (!estado.toma.activa) return no('no hay una ficha abierta.')
      const i = Number(args.numero) - 1; const bs = [...estado.toma.ficha.bloques]
      if (!(i >= 0 && i < bs.length)) return no(`la ficha tiene ${bs.length} bloques (numera desde 1).`)
      bs.splice(i, 1)
      return si({ ...estado, toma: { ...estado.toma, ficha: { ...estado.toma.ficha, bloques: bs }, fase: 'juntando', rechazo: false } }, `Quitado el bloque ${i + 1} de la ficha. Si la persona pidió algo EN SU LUGAR, anótalo AHORA con anotar_bloque.`)
    }
    case 'anotar_ficha': {
      if (!estado.toma.activa) return no('no hay una toma de diseño abierta.')
      if (estado.toma.fase === 'construida') return no('la ficha ya está confirmada: aplica el diseño con las herramientas de pantalla.')
      const campo = String(args.campo || '').trim()
      const val = validarValorFicha(plantilla, campo, args.valor)
      if (!val.ok) return no(val.error)
      const ficha = { ...estado.toma.ficha, marca: { ...estado.toma.ficha.marca }, restricciones: [...(estado.toma.ficha.restricciones || [])], secciones: [...(estado.toma.ficha.secciones || [])], bloques: [...(estado.toma.ficha.bloques || [])] }
      if (campo === 'objetivo') ficha.objetivo = val.value
      else if (campo === 'seccion' && !ficha.secciones.includes(val.value)) ficha.secciones.push(val.value)
      else if (campo === 'bloque') { ficha.bloques.push(val.value); if (val.value.seccion && !ficha.secciones.includes(val.value.seccion)) ficha.secciones.push(val.value.seccion) } // la sección sale del bloque
      else if (campo === 'marca_primario') ficha.marca.primario = val.value
      else if (campo === 'marca_secundario') ficha.marca.secundario = val.value
      else if (campo === 'tipografia') ficha.marca.tipografia = val.value
      else if (campo === 'restriccion') ficha.restricciones.push(val.value)
      return si({ ...estado, toma: { ...estado.toma, ficha, rechazo: false } }, `Ficha actualizada (${campo}).`)
    }
    default: return no(`la herramienta «${nombre}» no existe.`)
  }
}

/** Esquemas de las herramientas para el modelo (formato OpenAI). */
export const HERRAMIENTAS = [
  ['quitar_bloque', 'Quita un bloque del inicio.', { bloque: { type: 'string', description: 'id del bloque, ej. b2' } }, ['bloque']],
  ['agregar_bloque', 'Agrega un bloque al inicio con una vista del catálogo sobre una sección.', {
    seccion: { type: 'string' }, vista: { type: 'string', enum: VISTAS_INICIO }, opciones: { type: 'object', description: 'opciones de la vista: ids de campos (ver "vistas" y "secciones"). Para grafico: {tipo: uno de graficos_posibles de esa sección, ...}. Para tabla: {filtro: {campo, menorOIgual: número o id de otro campo | mayorOIgual | igual}, orden: {campo, dir: asc|desc}, limite}' , additionalProperties: true },
    ancho: { type: 'integer', enum: ANCHOS_COL }, alto: { type: 'integer', minimum: 1, maximum: ALTO_MAX }, posicion: { type: 'integer', minimum: 1 } }, ['seccion', 'vista']],
  ['cambiar_visual', 'Cambia la vista o sus opciones de un bloque existente (mantiene su lugar y tamaño).', {
    bloque: { type: 'string' }, vista: { type: 'string', enum: VISTAS_INICIO }, opciones: { type: 'object', additionalProperties: true }, seccion: { type: 'string' } }, ['bloque', 'vista']],
  ['cambiar_tamano', 'Cambia el ancho (columnas de 12) y/o el alto (filas) de un bloque, SOLO cuando la persona pidió cambiar ese tamaño. No la uses para acomodar después de quitar o agregar: el código tapa los huecos solo (acomodo automático).', { bloque: { type: 'string' }, ancho: { type: 'integer', enum: ANCHOS_COL }, alto: { type: 'integer', minimum: 1, maximum: ALTO_MAX } }, ['bloque']],
  ['mover_bloque', 'Cambia el orden: pone el bloque en esa posición (1 = primero). Para que algo quede a la derecha de otro, va justo después y la suma de anchos de la fila debe ser ≤ 12.', { bloque: { type: 'string' }, posicion: { type: 'integer', minimum: 1 } }, ['bloque', 'posicion']],
  ['cambiar_rangos', 'Define los grupos de un bloque de vencimientos. Reemplaza TODOS los rangos: incluye los que se quedan.', {
    bloque: { type: 'string' }, rangos: { type: 'array', items: { type: 'object', properties: { vencidos: { type: 'boolean' }, desde: { type: 'integer' }, hasta: { type: 'integer' } } } } }, ['bloque', 'rangos']],
  ['abrir_seccion', 'Muestra una sección del menú (o "inicio").', { seccion: { type: 'string' } }, ['seccion']],
  ['cambiar_marca', 'Cambia el branding del CRM: colores en hex (primario = color de marca principal, secundario, fondo, superficie = tarjetas, texto), tipografías y nombre. Solo manda lo que cambia; "" para volver al de base en ese punto.', {
    primario: { type: 'string' }, secundario: { type: 'string' }, fondo: { type: 'string' }, superficie: { type: 'string' }, texto: { type: 'string' },
    fuenteTitulos: { type: 'string', enum: Object.keys(FUENTES) }, fuenteTexto: { type: 'string', enum: Object.keys(FUENTES) }, nombre: { type: 'string' } }, []],
  ['usar_logo', 'Pone como logo del negocio la imagen que la persona adjuntó EN ESTE mensaje (SVG/PNG/WebP con fondo transparente).', {}, []],
  ['crear_seccion', 'Crea una sección NUEVA en el menú. Si lo que pide está en "pestanas_base", usa desde = ese id (trae campos, vista y piezas probados; no pases campos) y con_piezas = true si quiere verla también en el inicio. Si no está, pásale sus campos (máx. 8). Úsala cuando la persona quiere llevar algo que hoy no existe (inventario, cobros, proveedores, lo que sea). Para tablero/vencimientos/agenda pasa opciones (por: id campo estado / fecha: id campo fecha…); los id de campo son el nombre en minúsculas sin acentos con _ .', {
    desde: { type: 'string', description: 'id de pestanas_base' }, con_piezas: { type: 'boolean' },
    titulo: { type: 'string' }, vista: { type: 'string', enum: ['tabla', 'tablero', 'agenda', 'vencimientos'] }, opciones: { type: 'object', additionalProperties: true }, grupo: { type: 'integer', enum: [0, 1] },
    campos: { type: 'array', items: { type: 'object', properties: { nombre: { type: 'string' }, tipo: { type: 'string', enum: ['texto', 'numero', 'dinero', 'fecha', 'hora', 'estado'] }, opciones: { type: 'array', items: { type: 'string' } }, ejemplos: { type: 'array', items: { type: 'string' } } }, required: ['nombre', 'tipo'] } } }, []],
  ['agregar_campo', 'Agrega un campo a una sección existente.', { seccion: { type: 'string' }, nombre: { type: 'string' }, tipo: { type: 'string', enum: ['texto', 'numero', 'dinero', 'fecha', 'hora', 'estado'] }, opciones: { type: 'array', items: { type: 'string' } }, ejemplos: { type: 'array', items: { type: 'string' } } }, ['seccion', 'nombre', 'tipo']],
  ['cambiar_ficha', 'Define cómo se ve la FICHA de un registro (lo que se abre al tocar un cliente, una cita, un pedido…): grupos con título y los campos de cada uno, en orden. Campos que no pongas no se muestran. relacionados = mostrar lo de otras secciones ligado a este registro; linea_tiempo = sus fechas en orden.', {
    seccion: { type: 'string' }, grupos: { type: 'array', items: { type: 'object', properties: { titulo: { type: 'string' }, campos: { type: 'array', items: { type: 'string' }, description: 'ids de campos' } }, required: ['titulo', 'campos'] } },
    relacionados: { type: 'boolean' }, linea_tiempo: { type: 'boolean' } }, ['seccion', 'grupos']],
  ['cambiar_tarjeta', 'Elige qué campos muestran las TARJETAS del tablero de una sección (1 a 4; el primero es el título).', { seccion: { type: 'string' }, campos: { type: 'array', items: { type: 'string' } } }, ['seccion', 'campos']],
  ['quitar_campo', 'Deja de mostrar un campo de una sección (sus datos se conservan). Solo si la persona lo pidió.', { seccion: { type: 'string' }, campo: { type: 'string', description: 'id del campo' } }, ['seccion', 'campo']],
  ['renombrar_campo', 'Cambia el nombre visible de un campo.', { seccion: { type: 'string' }, campo: { type: 'string' }, nombre: { type: 'string' } }, ['seccion', 'campo', 'nombre']],
  ['cambiar_opciones_estado', 'Cambia las opciones de un campo de estado (agregar, quitar, renombrar o reordenar etapas). Pasa la lista COMPLETA nueva. Si una opción desaparece, di a dónde pasan sus registros: renombrar {vieja: nueva} o pasar_a.', {
    seccion: { type: 'string' }, campo: { type: 'string' }, opciones: { type: 'array', items: { type: 'string' } }, renombrar: { type: 'object', additionalProperties: { type: 'string' } }, pasar_a: { type: 'string' } }, ['seccion', 'campo', 'opciones']],
  ['renombrar_seccion', 'Cambia el nombre de una sección.', { seccion: { type: 'string' }, titulo: { type: 'string' } }, ['seccion', 'titulo']],
  ['quitar_seccion', 'Quita una sección del menú (y sus bloques del inicio). Solo si la persona lo pidió.', { seccion: { type: 'string' } }, ['seccion']],
  ['deshacer', 'Anula UN pedido anterior de la persona (ver pedidos_anteriores: qué dijo y qué cambió). El código revierte solo lo que ese pedido cambió y conserva lo demás. Úsalo para "eso no", "como estaba antes", "deshaz lo del color", "deshaz también X". Nunca lo uses sin que la persona lo pida.', { pedido: { type: 'integer', minimum: 1, description: 'número de pedidos_anteriores' } }, ['pedido']],
  ['restablecer_marca', 'Vuelve al diseño base de Shifu (quita colores, tipografías y logo propios).', {}, []],
  ['abrir_toma', 'Abre la toma de requerimientos cuando la persona pide DISEÑAR o REHACER la pantalla de inicio o un CRM completo. NO uses esto para cambios puntuales (mover, achicar, un solo bloque): esos van directo con las herramientas de pantalla.', {
    objetivo: { type: 'string', description: 'solo si lo dijo en este mensaje' } }, []],
  ['anotar_bloque', 'FICHA DE DISEÑO: anota UN bloque que la persona pidió en ESTE mensaje, dicho en simple. que = resumen | grafica | lista | tablero | por_vencer | agenda; seccion = la parte del menú (nombre). grafico = tipo opcional SOLO si lo nombró (dona, barras, columnas, linea…). Llama una vez por cada cosa que pidió. No preguntes detalles técnicos: el código elige lo razonable.', {
    que: { type: 'string', enum: ['resumen', 'grafica', 'lista', 'tablero', 'por_vencer', 'agenda'] }, seccion: { type: 'string' }, grafico: { type: 'string' } }, ['que', 'seccion']],
  ['quitar_de_ficha', 'Quita de la ficha el bloque número N (como aparece en el resumen) cuando la persona lo pide.', { numero: { type: 'integer', minimum: 1 } }, ['numero']],
  ['anotar_ficha', 'Anota en la ficha de diseño UN dato que la persona dijo explícitamente en ESTE mensaje (nunca inventes ni completes). Si dudas, usa anotar_nota. Campos: objetivo, seccion, bloque {vista, seccion, opciones?, tamano?}, marca_primario, marca_secundario, tipografia, restriccion.', {
    campo: { type: 'string' }, valor: { description: 'string u objeto según el campo' } }, ['campo', 'valor']],
  ['anotar_nota', 'Guarda una idea o duda que la persona mencionó pero que no es un dato firme de la ficha.', { texto: { type: 'string' } }, ['texto']],
  ['cerrar_toma', 'Cierra la toma si la persona abandona el diseño o ya no quiere seguir con la ficha.', {}, []],
].map(([name, description, properties, required]) => ({ type: 'function', function: { name, description, parameters: { type: 'object', properties, required } } }))
