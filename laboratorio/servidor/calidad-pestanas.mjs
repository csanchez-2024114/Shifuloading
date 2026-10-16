/* Filtro de calidad de la biblioteca de PESTAÑAS (D30, nivel 2): secciones listas para usar (cobros, inventario,
 * proveedores…) con sus campos y las piezas que mejor las muestran. La IA parte de ellas al crear una sección, en vez de
 * inventar campos. Usa el mismo código que la pantalla (validar.js, graficos.jsx) vía Vite.
 * Uso (desde la raíz de Shifuloading): node laboratorio/servidor/calidad-pestanas.mjs [id ...]   (sin ids: todas) */
import { createServer } from 'vite'
import { readdirSync } from 'node:fs'

const ICONOS = ['usuarios', 'calendario', 'caja', 'tarjeta', 'tablero', 'tabla', 'actividad', 'equipo', 'rayo', 'documento', 'camion', 'reloj']
const VISTAS_SECCION = ['tabla', 'tablero', 'agenda', 'vencimientos']
const VISTAS_PIEZA = ['kpis', 'tablero', 'agenda', 'vencimientos', 'grafico', 'tabla']
const INGLES = /(?<!\p{L})(status|name|date|amount|price|customer|client|lead|deal|pipeline|email|phone|notes?|owner|due|created)(?!\p{L})/iu
const SIN_EJEMPLOS = ['nombre', 'telefono', 'cliente', 'empresa', 'correo', 'miembro', 'paciente', 'contacto', 'responsable', 'proveedor']

const s = await createServer({ configFile: 'laboratorio/vite.config.js', server: { middlewareMode: true, hmr: false }, logLevel: 'error' })
try {
  const { validarPlantilla, camposDe } = await s.ssrLoadModule('/src/plantillas/validar.js')
  const { compatibles } = await s.ssrLoadModule('/src/plantillas/graficos.jsx')
  const dir = 'laboratorio/src/plantillas/biblioteca-pestanas'
  const todos = readdirSync(dir).filter((f) => f.endsWith('.js')).map((f) => f.replace(/\.js$/, ''))
  const pedidas = process.argv.slice(2)
  let fallan = 0; const titulos = new Map()
  for (const id of pedidas.length ? pedidas : todos) {
    const e = []
    let p
    try { p = (await s.ssrLoadModule(`/src/plantillas/biblioteca-pestanas/${id}.js`)).default } catch (err) { e.push(`no se pudo cargar: ${err.message.slice(0, 160)}`) }
    if (p) {
      if (p.id !== id) e.push(`el id «${p.id}» debe ser igual al nombre del archivo «${id}»`)
      if (!p.para || p.para.length < 20) e.push('"para" debe decir en una frase para qué sirve esta pestaña')
      if (!Array.isArray(p.palabras) || p.palabras.length < 3) e.push('"palabras": al menos 3 formas en que la gente la pide (sinónimos, en minúsculas)')
      const sec = { ...p.seccion, id }
      if (!sec.titulo || sec.titulo.length > 22) e.push('seccion.titulo: corto (máx. 22 letras)')
      if (!ICONOS.includes(sec.icono)) e.push(`seccion.icono debe ser uno de: ${ICONOS.join(', ')}`)
      if (!VISTAS_SECCION.includes(sec.vista)) e.push(`seccion.vista debe ser: ${VISTAS_SECCION.join(', ')}`)
      const campos = sec.campos || []
      if (campos.length < 3 || campos.length > 8) e.push(`tiene ${campos.length} campos; entre 3 y 8`)
      for (const c of campos) {
        if (!/^[a-z][a-z0-9_]*$/.test(c.id || '')) e.push(`campo «${c.nombre}»: id en minúsculas sin acentos (con _)`)
        if (INGLES.test(c.nombre)) e.push(`campo «${c.nombre}» en inglés: todo en español`)
        if (c.tipo === 'estado' && !(c.opciones?.length >= 3 && c.opciones.length <= 7)) e.push(`estado «${c.nombre}»: 3 a 7 opciones en orden de avance`)
        if (c.tipo === 'texto' && !SIN_EJEMPLOS.includes(c.id) && !(c.ejemplos?.length >= 5)) e.push(`texto «${c.nombre}»: 5+ ejemplos realistas`)
      }
      if (titulos.has(sec.titulo?.toLowerCase())) e.push(`ya existe otra pestaña «${sec.titulo}» (${titulos.get(sec.titulo.toLowerCase())})`)
      titulos.set(sec.titulo?.toLowerCase(), id)
      // Piezas: las mismas reglas del inicio, validadas con el código de la pantalla.
      const piezas = p.piezas || []
      if (piezas.length < 2 || piezas.length > 4) e.push(`piezas: entre 2 y 4 (tiene ${piezas.length})`)
      if (!piezas.some((w) => w.vista === 'grafico')) e.push('al menos una pieza "grafico"')
      for (const w of piezas) if (!VISTAS_PIEZA.includes(w.vista)) e.push(`pieza con vista «${w.vista}» no permitida`)
      const plantilla = { id: `p-${id}`, nombre: id, secciones: [sec], inicio: piezas.map((w) => ({ ...w, seccion: id })) }
      e.push(...validarPlantilla(plantilla))
      const posibles = compatibles(camposDe(sec, { [id]: sec })).map((g) => g.id)
      for (const w of piezas.filter((x) => x.vista === 'grafico')) if (!posibles.includes(w.opciones?.tipo)) e.push(`gráfico «${w.opciones?.tipo}» no es compatible con estos campos (posibles: ${posibles.join(', ')})`)
    }
    if (e.length) { fallan++; console.log(`✗ ${id}\n${[...new Set(e)].map((x) => `   - ${x}`).join('\n')}`) } else console.log(`✓ ${id}`)
  }
  console.log(`\n${(pedidas.length || todos.length) - fallan}/${pedidas.length || todos.length} pestañas pasan`)
  process.exitCode = fallan ? 1 : 0
} finally { await s.close() }
