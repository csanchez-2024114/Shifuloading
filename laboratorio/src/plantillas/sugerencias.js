/* Ideas del chat que dependen de lo que la persona TIENE y está MIRANDO (sin modelos: reglas del código sobre su CRM).
 * Mira la pestaña abierta, las secciones y sus campos, los bloques del inicio, cuántos datos hay, la marca y la ficha
 * de diseño. Cambian con el tiempo: cada mensaje o cambio de pestaña rota cuáles se muestran. */
import { compatibles, GRAFICOS } from './graficos.jsx'
import { camposDe } from './validar.js'

const tituloVista = { kpis: 'el resumen', tablero: 'el tablero', agenda: 'la agenda', vencimientos: 'lo que vence', tabla: 'la lista', grafico: 'la gráfica', grafica: 'la gráfica' }

/** Devuelve [[etiqueta, texto], …] (máx. `cuantas`), rotadas con `turno` para que no sean siempre las mismas. */
export function sugerenciasPara({ plantilla, bloques = [], marca = {}, toma, vista = 'inicio', datos, turno = 0, cuantas = 7 }) {
  const porId = Object.fromEntries(plantilla.secciones.map((s) => [s.id, s]))
  const conDatos = plantilla.secciones.filter((s) => s.campos || s.fuente)
  const n = (s) => (datos?.registros?.[s.fuente || s.id] || []).length
  const ideas = []
  const add = (prio, etq, txt) => ideas.push({ prio, etq, txt })

  // 1) Ficha de diseño abierta: lo que sirve para completarla o confirmarla.
  if (toma?.activa && toma.fase !== 'construida') {
    const yaHay = new Set((toma.ficha?.bloques || []).map((b) => b.seccion))
    for (const s of conDatos.filter((x) => !yaHay.has(x.id)).slice(0, 2)) add(10, 'Ficha', `Agrega un resumen de ${s.titulo.toLowerCase()}`)
    if (toma.fase === 'confirmando') { add(11, 'Ficha', 'Sí, ármalo así'); add(9, 'Ficha', 'Mejor con barras en vez de dona') }
    add(5, 'Ficha', 'Olvídalo, déjalo como está')
  }

  // 2) La pestaña que está mirando.
  const actual = porId[vista]
  if (actual && (actual.campos || actual.fuente)) {
    const campos = camposDe(actual, porId)
    const estado = campos.find((c) => c.tipo === 'estado'), fecha = campos.find((c) => c.tipo === 'fecha'), dinero = campos.find((c) => c.tipo === 'dinero')
    const t = actual.titulo.toLowerCase()
    if (!bloques.some((b) => b.seccion === actual.id)) add(8, actual.titulo, `Pon un resumen de ${t} en el inicio`)
    if (estado && actual.vista !== 'tablero') add(7, actual.titulo, `Muéstrame ${t} como tablero por ${estado.nombre.toLowerCase()}`)
    if (fecha) add(6, actual.titulo, `Pon en el inicio lo que vence de ${t}`)
    if (dinero && estado) add(6, actual.titulo, `Una gráfica de ${dinero.nombre.toLowerCase()} por ${estado.nombre.toLowerCase()}`)
    if (campos.length < 8) add(4, actual.titulo, `Agrega un campo de notas a ${t}`)
  }

  // 3) Lo que hay en su inicio.
  for (const b of bloques) {
    const s = porId[b.seccion]; if (!s) continue
    const t = s.titulo.toLowerCase()
    if (b.vista === 'grafico' || b.vista === 'grafica') {
      const otros = compatibles(camposDe(s, porId)).map((g) => g.id).filter((g) => g !== b.opciones?.tipo && ['barras', 'dona', 'columnas', 'linea-area', 'embudo', 'arbol', 'radar'].includes(g))
      if (otros.length) add(5, 'Gráfica', `Cambia la gráfica de ${t} por ${GRAFICOS[otros[turno % otros.length]].nombre.toLowerCase()}`)
      if ((b.ancho || 6) >= 6) add(3, 'Diseño', `Haz la gráfica de ${t} más chica y ponla a la derecha`)
    }
    if (b.vista === 'vencimientos') add(4, 'Vencimientos', `En ${tituloVista.vencimientos} de ${t}, pon un grupo "de 1 a 15 días"`)
  }
  if (bloques.length >= 6) add(4, 'Diseño', 'Acomoda el inicio para que todo quepa mejor')
  if (bloques.length <= 2) add(6, 'Diseño', 'Diséñame un inicio nuevo con lo más importante de mi negocio')

  // 4) Sus datos: secciones con muchos registros que no se ven en el inicio, o vacías.
  for (const s of conDatos) {
    if (n(s) >= 20 && !bloques.some((b) => b.seccion === s.id)) add(6, 'Datos', `Tengo muchos ${s.titulo.toLowerCase()}: ponlos en el inicio`)
    if (datos && n(s) === 0) add(2, 'Datos', `Pon una lista de ${s.titulo.toLowerCase()} en el inicio`)
  }

  // 5) Marca y lo que todavía no usa.
  if (!marca.primario) add(5, 'Marca', 'Pon los colores de mi marca (pega tu web o tu logo)')
  else if (!marca.logo) add(5, 'Marca', 'Agrega mi logo (adjúntalo con el clip)')
  add(1, 'Ayuda', '¿Qué gráficas puedo poner con mis datos?')

  // Orden por prioridad, sin repetidos, rotando las de igual prioridad según el turno.
  const unicas = [...new Map(ideas.map((i) => [i.txt, i])).values()]
  unicas.sort((a, b) => b.prio - a.prio || ((a.txt.length + turno) % 7) - ((b.txt.length + turno) % 7))
  const top = unicas.slice(0, cuantas + 3)
  const desfase = turno % Math.max(1, top.length - cuantas + 1)
  return top.slice(desfase, desfase + cuantas).map((i) => [i.etq, i.txt])
}
