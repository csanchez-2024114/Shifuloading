/* Filtro de calidad de plantillas (lo corre cualquier agente antes de entregar una plantilla, y nosotros al integrar).
 * Uso (desde la raíz de Shifuloading):  node laboratorio/servidor/calidad.mjs [archivo-o-id ...]
 * Sin argumentos revisa TODAS (semillas + biblioteca). Sale con código 1 si alguna falla.
 * Usa el mismo código que la pantalla (validar.js, edicion.js, graficos.jsx, datosEjemplo.js) vía Vite: una sola fuente. */
import { createServer } from 'vite'
import { basename } from 'node:path'

const RUBROS = ['servicios', 'agencia', 'comercio', 'salud', 'educacion', 'tecnologia', 'inmobiliaria', 'otro']
const CICLOS = ['cotizacion', 'rapida', 'recurrente', 'mezcla']
const OBJETIVOS = ['seguimientos', 'contactos', 'ia', 'reportes', 'cotizaciones', 'equipo', 'integraciones']
// Bordes de palabra con letras Unicode: \b de JS no ve la ñ ni los acentos ("Dueño" no es "due").
const INGLES = /(?<!\p{L})(status|name|date|amount|price|customer|client|lead|deal|pipeline|email|phone|notes?|owner|due|created)(?!\p{L})/iu
const VISTAS_INICIO = ['kpis', 'tablero', 'agenda', 'vencimientos', 'grafico', 'grafica', 'tabla']

const s = await createServer({ configFile: 'laboratorio/vite.config.js', server: { middlewareMode: true, hmr: false }, logLevel: 'error' })
try {
  const { PLANTILLAS } = await s.ssrLoadModule('/src/plantillas/semillas.js')
  const { validarPlantilla, camposDe } = await s.ssrLoadModule('/src/plantillas/validar.js')
  const { ubicar } = await s.ssrLoadModule('/src/plantillas/edicion.js')
  const { compatibles, opcionesPorDefecto } = await s.ssrLoadModule('/src/plantillas/graficos.jsx')
  const { datosEjemplo, registrosDe } = await s.ssrLoadModule('/src/plantillas/datosEjemplo.js')

  const pedidas = process.argv.slice(2).map((a) => basename(a).replace(/\.js$/, ''))
  const lista = pedidas.length ? PLANTILLAS.filter((p) => pedidas.includes(p.id)) : PLANTILLAS
  const faltan = pedidas.filter((id) => !PLANTILLAS.some((p) => p.id === id))
  let fallan = 0
  for (const id of faltan) { fallan++; console.log(`✗ ${id}\n   - no se encontró (¿el archivo exporta default con id igual al nombre del archivo?)`) }

  const firma = (p) => (p.inicio || []).map((w) => `${w.vista}:${w.opciones?.tipo || ''}:${w.ancho || ''}x${w.alto || ''}`).join('|')
  const formas = (p) => (p.inicio || []).map((w) => `${w.vista}${w.ancho || ''}x${w.alto || ''}`).join('|')
  for (const p of lista) {
    const e = [...validarPlantilla(p)]
    const porId = Object.fromEntries(p.secciones.map((x) => [x.id, x]))
    const esBiblio = !!p.asignacion
    // Metadatos de asignación (D23: con ellos se elige la plantilla según el cuestionario)
    if (esBiblio) {
      const a = p.asignacion
      if (!a.rubros?.length || a.rubros.some((r) => !RUBROS.includes(r))) e.push(`asignacion.rubros debe usar solo: ${RUBROS.join(', ')}`)
      if (!a.ciclos?.length || a.ciclos.some((r) => !CICLOS.includes(r))) e.push(`asignacion.ciclos debe usar solo: ${CICLOS.join(', ')}`)
      if (a.objetivos?.some((r) => !OBJETIVOS.includes(r))) e.push(`asignacion.objetivos debe usar solo: ${OBJETIVOS.join(', ')}`)
      if (!a.negocios?.length || a.negocios.length < 3) e.push('asignacion.negocios: al menos 3 ejemplos de negocios reales para los que sirve')
    }
    if (!p.para || p.para.length < 20) e.push('"para" debe describir en una frase para quién es')
    // Inicio: entre 3 y 6 bloques, vistas del inicio, al menos un gráfico del catálogo, y que quepa en UNA pantalla
    const ini = p.inicio || []
    if (ini.length < (esBiblio ? 3 : 2) || ini.length > 6) e.push(`el inicio tiene ${ini.length} bloques; debe tener entre 3 y 6`)
    for (const w of ini) if (!VISTAS_INICIO.includes(w.vista)) e.push(`bloque de inicio con vista «${w.vista}» no permitida en el inicio`)
    if (esBiblio && !ini.some((w) => w.vista === 'grafico')) e.push('el inicio debe tener al menos un bloque "grafico" del catálogo')
    for (const w of ini.filter((x) => x.vista === 'grafico')) {
      const s2 = porId[w.seccion]; if (!s2) continue
      const ok = compatibles(camposDe(s2, porId)).map((g) => g.id)
      if (!ok.includes(w.opciones?.tipo)) e.push(`gráfico «${w.opciones?.tipo}» no es compatible con «${s2.titulo}» (posibles: ${ok.join(', ')})`)
    }
    // Gráficas por tiempo: los datos de ejemplo deben cubrir 3+ meses, si no la gráfica sale casi vacía (un solo mes).
    const POR_MES = ['columnas', 'linea', 'linea-area', 'linea-tendencia', 'area-apilada', 'columnas-apiladas', 'columnas-100', 'cascada', 'kpi', 'combo', 'escalones', 'multiples', 'pendiente', 'meta', 'bala', 'dos-kpis', 'calendario']
    for (const w of ini.filter((x) => x.vista === 'grafico' && POR_MES.includes(x.opciones?.tipo))) {
      const s2 = porId[w.seccion]; if (!s2) continue
      const op = { ...opcionesPorDefecto(w.opciones.tipo, camposDe(s2, porId)), ...w.opciones }
      const idF = op.fecha || (op.agrupar === 'mes' ? op.fecha : null) || camposDe(s2, porId).find((c) => c.tipo === 'fecha')?.id
      const cF = camposDe(s2, porId).find((c) => c.id === idF); if (!cF) continue
      const r = cF.rango || { alta: [-330, 0], vence: [-12, 45] }[cF.id] || [-60, 30]
      if (r[1] - r[0] < 90 && !(w.opciones.tipo === 'calendario' && r[1] - r[0] >= 28)) e.push(`el gráfico «${w.opciones.tipo}» agrupa por tiempo con «${cF.nombre}», pero sus datos de ejemplo solo cubren ${r[1] - r[0]} días: usa otra fecha con rango de 90+ días (por ejemplo la fecha de alta o de pago) o otro tipo de gráfico`)
    }
    const tam = ini.map((w, i) => ({ uid: `b${i}`, vista: w.vista, ancho: w.ancho || (['kpis', 'tablero', 'agenda'].includes(w.vista) ? 12 : 6), alto: w.vista === 'kpis' ? 1 : w.alto || 2 }))
    for (const w of tam) if (![3, 4, 6, 8, 12].includes(w.ancho) || w.alto < 1 || w.alto > 4) e.push(`bloque ${w.uid}: ancho ${w.ancho} / alto ${w.alto} fuera de lo permitido`)
    const filas = Math.max(0, ...Object.entries(ubicar(tam)).map(([uid, u]) => u.fila + (tam.find((t) => t.uid === uid).alto) - 1))
    if (filas > 5) e.push(`el inicio ocupa ${filas} filas; máximo 5 para que quepa en una pantalla (achica o junta bloques)`)
    const huecos = 12 * filas - tam.reduce((t, w) => t + w.ancho * w.alto, 0)
    if (esBiblio && huecos > 6) e.push(`el inicio deja ${huecos} celdas vacías en la rejilla; acomoda anchos para que no queden huecos`)
    if (PLANTILLAS.some((o) => o !== p && o.nombre.trim().toLowerCase() === p.nombre.trim().toLowerCase())) e.push(`ya existe otra plantilla llamada «${p.nombre}»: no dupliques, mejora la existente`)
    if (esBiblio) {
      const iguales = PLANTILLAS.filter((o) => o !== p && o.asignacion && formas(o) === formas(p)).map((o) => o.id)
      if (iguales.length >= 2) e.push(`el acomodo del inicio es idéntico al de ${iguales.slice(0, 4).join(', ')}${iguales.length > 4 ? '…' : ''}: diseña el inicio según lo que ESTE negocio mira a diario (otras vistas, anchos y orden)`)
    }
    // Secciones y campos
    const propias = p.secciones.filter((x) => x.campos)
    if (esBiblio && propias.length < 3) e.push('debe tener al menos 3 secciones con campos')
    if (!propias.some((x) => x.campos.some((c) => c.tipo === 'estado' && c.opciones.length >= 3))) e.push('ninguna sección tiene un campo "estado" con 3+ opciones (sin él no hay tablero ni conteos útiles)')
    for (const x of propias) {
      if (x.campos.length > 8) e.push(`«${x.titulo}» tiene ${x.campos.length} campos; máximo 8`)
      const ids = x.campos.map((c) => c.id); if (new Set(ids).size !== ids.length) e.push(`«${x.titulo}» repite ids de campo`)
      for (const c of x.campos) {
        if (INGLES.test(c.nombre) || INGLES.test(x.titulo)) e.push(`«${x.titulo}»: «${c.nombre}» parece inglés; todo en español`)
        if (c.tipo === 'texto' && !c.ejemplos && !['nombre', 'telefono', 'cliente', 'empresa'].includes(c.id) && esBiblio) e.push(`«${x.titulo}.${c.nombre}» (texto) necesita "ejemplos" realistas (5+ valores)`)
        if (c.ejemplos && c.ejemplos.length < 5) e.push(`«${x.titulo}.${c.nombre}»: "ejemplos" necesita 5 o más valores`)
      }
    }
    // Datos de ejemplo: se generan sin errores y cada gráfico del inicio tiene algo que mostrar con 220 registros
    try {
      const d = datosEjemplo(p, 'muchos')
      for (const w of ini) { const s2 = porId[w.seccion]; if (s2 && (s2.campos || s2.fuente) && !registrosDe(s2, d).length) e.push(`la sección «${s2.titulo}» no genera datos de ejemplo`) }
    } catch (err) { e.push(`datos de ejemplo fallan: ${err.message}`) }
    if (e.length) { fallan++; console.log(`✗ ${p.id}\n${[...new Set(e)].map((x) => `   - ${x}`).join('\n')}`) } else console.log(`✓ ${p.id}  (${ini.length} bloques, ${filas} filas, ${propias.length} secciones)`)
  }
  console.log(`\n${lista.length - fallan + faltan.length}/${lista.length + faltan.length} pasan el filtro de calidad.`)
  process.exitCode = fallan ? 1 : 0
} finally { await s.close() }
