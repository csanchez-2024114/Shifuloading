/* Graba los fixtures dorados de la toma de diseño (edicion.js: prepararTurnoToma, las herramientas de la ficha, senalTomaTrasVuelta,
 * resumenDeToma, tarjetaToma y construirDesdeFicha) para el port a Python (backend/app/crm/toma.py). Sin IA: cada guion llama las
 * herramientas con los argumentos que mandaría el modelo (los de laboratorio/pruebas/banco_toma.py y casos de borde).
 * Date se fija (los uid de construirDesdeFicha salen de Date.now) y un plugin de prueba guarda los bloques ANTES de acomodar.
 * Uso (desde la raíz del repo): node laboratorio/servidor/grabar-toma.mjs */
import { createServer } from 'vite'
import { writeFileSync } from 'node:fs'

const FIJO = Date.UTC(2026, 9, 16, 18, 0, 0)
const DateReal = Date
globalThis.Date = class extends DateReal {
  constructor(...a) { if (a.length) super(...a); else super(FIJO) }
  static now() { return FIJO }
}
// Solo para grabar: deja a la vista los bloques que construirDesdeFicha le pasa a acomodar (no cambia lo que hace).
const espia = { name: 'espia-acomodar', enforce: 'pre', transform(code, id) {
  if (!id.endsWith('/plantillas/edicion.js')) return null
  const viejo = "bloques: acomodar(bloques), marca, vista: 'inicio'"
  if (!code.includes(viejo)) throw new Error('grabar-toma: cambió construirDesdeFicha, revisa el espía')
  return code.replace(viejo, "bloques: (globalThis.__antesDeAcomodar = bloques, acomodar(bloques)), marca, vista: 'inicio'")
} }
const v = await createServer({ configFile: 'laboratorio/vite.config.js', plugins: [espia], server: { middlewareMode: true, hmr: false }, logLevel: 'error' })
const ed = await v.ssrLoadModule('/src/plantillas/edicion.js')
const { plantillaPorId } = await v.ssrLoadModule('/src/plantillas/semillas.js')
const { compatibles, opcionesPorDefecto, GRAFICOS } = await v.ssrLoadModule('/src/plantillas/graficos.jsx')
const { VISTAS, camposDe } = await v.ssrLoadModule('/src/plantillas/validar.js')
const { FUENTES } = await v.ssrLoadModule('/src/plantillas/marca.js')

const E = { bloques: [{ uid: 'b0', vista: 'kpis', seccion: 'miembros', opciones: { por: 'estado' }, ancho: 12, alto: 1 }] }
const H = (nombre, args = {}, extra = {}) => ({ paso: 'herramienta', nombre, args, ...extra })
const P = (texto) => ({ paso: 'preparar', texto })
const S = { paso: 'senal' }, R = { paso: 'resumen' }, C = { paso: 'construir' }
const GUIONES = [
  ['banco: pedir, anotar, cambiar y confirmar', 'membresias', [
    P('Diséñame un inicio nuevo para controlar mis pagos'), H('anotar_bloque', { que: 'resumen', seccion: 'Pagos' }),
    H('anotar_bloque', { que: 'grafica', seccion: 'Miembros', grafico: 'dona' }), S, R,
    P('No, mejor barras en vez de dona'), H('quitar_de_ficha', { numero: 2 }), H('anotar_bloque', { que: 'grafica', seccion: 'miembros', grafico: 'barras' }), S, R,
    P('Sí'), C, R]],
  // «rediseñar» no lo abre el código (solo «rediseña»): en el banco la abre el modelo con abrir_toma.
  ['banco: abandonar sin cambiar nada', 'membresias', [P('Quiero rediseñar mi inicio'), R, H('abrir_toma', {}), R, P('mejor olvídalo, déjalo como está'), R,
    H('cerrar_toma', {}, { texto: 'mejor olvídalo, déjalo como está' })]],
  ['banco: varias cosas en un mensaje', 'membresias', [P('diséñame un inicio con una lista de pagos, un tablero de miembros por estado y lo que vence'),
    H('anotar_bloque', { que: 'lista', seccion: 'pagos' }), H('anotar_bloque', { que: 'tablero', seccion: 'Miembros' }), H('anotar_bloque', { que: 'por_vencer', seccion: 'Vencimientos' }),
    S, R, P('dale'), C]],
  ['banco: digresión en medio de la toma', 'membresias', [P('Diséñame un inicio nuevo para mis miembros'), S,
    P('oye, ¿qué hora es en Guatemala?'), H('anotar_nota', { texto: 'pregunta la hora' }, { digresion: true }), H('anotar_ficha', { campo: 'objetivo', valor: 'la hora' }, { digresion: true }),
    H('anotar_bloque', { que: 'agenda', seccion: 'pagos' }, { digresion: true }), H('agregar_bloque', { seccion: 'miembros', vista: 'tabla' }), H('cambiar_marca', { primario: '#ff0000' }, { digresion: true }), S, R]],
  ['banco: pedido vago abre la ficha sin piezas', 'membresias', [P('Diséñame un inicio nuevo para mis miembros'), S, R]],
  ['banco: cambio puntual no abre la toma', 'membresias', [P('haz el resumen más chico'), R, H('anotar_bloque', { que: 'resumen', seccion: 'miembros' }), H('anotar_nota', { texto: 'x' }),
    H('quitar_de_ficha', { numero: 1 }), H('anotar_ficha', { campo: 'objetivo', valor: 'x' }), S]],
  ['bordes de anotar_bloque y quitar_de_ficha', 'membresias', [H('abrir_toma', { objetivo: 'ver cobros y vencimientos de mis miembros' }), H('abrir_toma', {}), S,
    H('anotar_bloque', { que: 'tablero', seccion: 'pagos' }), H('anotar_bloque', { que: 'agenda', seccion: 'Pagos' }), H('anotar_bloque', { que: 'algo', seccion: 'pagos' }),
    H('anotar_bloque', { que: 'lista', seccion: 'Proveedores' }), H('anotar_bloque', { que: 'lista' }), H('anotar_bloque', { que: 'grafica', seccion: 'pagos', grafico: 'dona' }),
    H('anotar_bloque', { que: 'grafica', seccion: 'pagos' }), H('anotar_bloque', { que: 'resumen', seccion: 'Miembros' }), H('anotar_bloque', { que: 'por_vencer', seccion: 'miembros' }),
    H('anotar_bloque', { que: 'grafica', seccion: 'vencimientos' }), H('anotar_bloque', { que: 'lista', seccion: 'Historial' }),
    H('quitar_de_ficha', { numero: 9 }), H('quitar_de_ficha', { numero: 0 }), H('quitar_de_ficha', { numero: '2' }), H('quitar_de_ficha', {}), S, R, C]],
  ['bordes de anotar_ficha, notas y marca', 'membresias', [H('anotar_ficha', { campo: 'objetivo', valor: 'x' }), H('abrir_toma', {}), S,
    H('anotar_ficha', { campo: 'objetivo', valor: '   ' }), H('anotar_ficha', { campo: 'objetivo', valor: 'controlar pagos' }), H('anotar_ficha', { campo: 'seccion', valor: 'Pagos' }),
    H('anotar_ficha', { campo: 'seccion', valor: 'pagos' }), H('anotar_ficha', { campo: 'seccion', valor: 'Bodega' }),
    H('anotar_ficha', { campo: 'bloque', valor: { vista: 'tablero', seccion: 'Miembros', opciones: { por: 'estado' }, tamano: { ancho: 8 } } }),
    H('anotar_ficha', { campo: 'bloque', valor: { vista: 'tablero', seccion: 'miembros', opciones: {} } }),
    H('anotar_ficha', { campo: 'bloque', valor: { vista: 'mapa', seccion: 'miembros' } }),
    H('anotar_ficha', { campo: 'bloque', valor: { vista: 'grafico', seccion: 'miembros', opciones: {} } }),
    H('anotar_ficha', { campo: 'bloque', valor: { vista: 'grafico', seccion: 'pagos', opciones: { tipo: 'dona' } } }),
    H('anotar_ficha', { campo: 'bloque', valor: { vista: 'grafico', seccion: 'miembros', opciones: { tipo: 'dona' }, tamano: { ancho: 4, alto: 3 } } }),
    H('anotar_ficha', { campo: 'bloque', valor: { vista: 'tabla', seccion: 'pagos', tamano: { ancho: 5 } } }),
    H('anotar_ficha', { campo: 'bloque', valor: { vista: 'tabla', seccion: 'pagos', tamano: { alto: 7 } } }),
    H('anotar_ficha', { campo: 'bloque', valor: { vista: 'agenda', seccion: 'Proveedores' } }),
    H('anotar_ficha', { campo: 'bloque', valor: 'una tabla' }),
    H('anotar_ficha', { campo: 'marca_primario', valor: '1e40af' }), H('anotar_ficha', { campo: 'marca_secundario', valor: '#F59E0B' }),
    H('anotar_ficha', { campo: 'marca_primario', valor: 'azul' }), H('anotar_ficha', { campo: 'tipografia', valor: 'Poppins' }), H('anotar_ficha', { campo: 'tipografia', valor: 'Comic Sans' }),
    H('anotar_ficha', { campo: 'restriccion', valor: 'nada de rojo' }), H('anotar_ficha', { campo: 'restriccion', valor: '' }), H('anotar_ficha', { campo: 'color', valor: 'x' }),
    H('anotar_ficha', {}), H('anotar_nota', { texto: '  ' }), H('anotar_nota', { texto: 'quizá una agenda después' }),
    H('cerrar_toma', {}, { texto: 'sigue' }), S, R, P('y también una agenda'), R, P('Perfecto, adelante'), C, R]],
  ['confirmando: ajuste agregando y un sí con coma', 'membresias', [P('arma mi nuevo inicio'), H('anotar_bloque', { que: 'resumen', seccion: 'pagos' }), S, R,
    P('cambia: prefiero también la lista de pagos'), S, H('anotar_bloque', { que: 'lista', seccion: 'pagos' }), S, R, P('ok, gracias'), C]],
  ['gimnasio: resumen con suma y un solo medio a lo ancho', 'gimnasio', [P('Rediseña mi inicio para ver mis membresías'), H('anotar_bloque', { que: 'resumen', seccion: 'Membresías' }),
    H('anotar_bloque', { que: 'agenda', seccion: 'clases' }), H('anotar_bloque', { que: 'grafica', seccion: 'membresias' }), H('anotar_bloque', { que: 'por_vencer', seccion: 'membresias' }),
    H('anotar_bloque', { que: 'lista', seccion: 'visitas y prueba' }), S, R, P('sí'), C]],
]

const tomaDe = (e) => JSON.parse(JSON.stringify(e.toma ?? null))
const guiones = []
for (const [nombre, pid, pasos] of GUIONES) {
  const p = plantillaPorId(pid)
  let estado = JSON.parse(JSON.stringify(E))
  const salidas = []
  for (const paso of pasos) {
    if (paso.paso === 'preparar') {
      const r = ed.prepararTurnoToma(estado, paso.texto); estado = r.estado
      salidas.push({ aviso: r.aviso, digresion: r.digresion, construir: !!r.construir, toma: tomaDe(estado) })
    } else if (paso.paso === 'herramienta') {
      const { bloques, ...sin } = estado // sin bloques: ejecutar no agrega «Así se ve ahora…» (eso es del lienzo, no de la toma)
      const r = ed.ejecutar(p, sin, paso.nombre, paso.args, { texto: paso.texto ?? '', digresion: !!paso.digresion }); estado = { ...r.estado, bloques }
      salidas.push({ ok: r.ok, resultado: r.resultado, toma: tomaDe(estado) })
    } else if (paso.paso === 'senal') {
      const s = ed.senalTomaTrasVuelta(p, estado)
      salidas.push({ senal: s, toma: tomaDe(estado) })
    } else if (paso.paso === 'resumen') {
      salidas.push({ resumen: ed.resumenDeToma(p, estado), tarjeta: ed.tarjetaToma(p, estado), faltantes: ed.faltantesToma(p, estado), contexto: ed.describirPantalla(p, estado).toma })
    } else if (paso.paso === 'construir') {
      globalThis.__antesDeAcomodar = null
      const r = ed.construirDesdeFicha(p, estado); estado = r.estado
      salidas.push({ errores: r.errores, antes_de_acomodar: globalThis.__antesDeAcomodar, inicio: estado.bloques, marca: estado.marca ?? null, toma: tomaDe(estado) })
    }
  }
  const efectiva = ed.plantillaEfectiva(p, {})
  guiones.push({ caso: nombre, plantilla: pid, pasos, salidas })
}
// El catálogo que el CRM le inyecta a toma.py: secciones (plantilla efectiva) y, por sección, los gráficos posibles y sus opciones.
const catalogo = {}
for (const pid of new Set(GUIONES.map((g) => g[1]))) {
  const ef = ed.plantillaEfectiva(plantillaPorId(pid), {})
  const porId = Object.fromEntries(ef.secciones.map((s) => [s.id, s]))
  const graficos = {}
  for (const s of ef.secciones) {
    const campos = camposDe(s, porId)
    graficos[s.id] = compatibles(campos).map((g) => ({ id: g.id, nombre: g.nombre, opciones_por_defecto: opcionesPorDefecto(g.id, campos) }))
  }
  catalogo[pid] = { secciones: ef.secciones.map(({ pagina, ...s }) => s), compatibles: graficos }
}
const extra = { vistas: VISTAS, graficos: Object.fromEntries(Object.entries(GRAFICOS).map(([id, g]) => [id, { nombre: g.nombre }])), fuentes: Object.keys(FUENTES),
  inicio_inicial: E.bloques, herramientas: ed.HERRAMIENTAS.filter((h) => ['abrir_toma', 'anotar_bloque', 'quitar_de_ficha', 'anotar_ficha', 'anotar_nota', 'cerrar_toma'].includes(h.function.name)),
  bloqueadas: [...ed.HERRAMIENTAS_BLOQUEADAS_EN_TOMA], uid_base: Date.now().toString(36) }
writeFileSync('backend/test/crm/fixtures/lab/toma_guiones.json', JSON.stringify(guiones, null, 1))
writeFileSync('backend/test/crm/fixtures/lab/toma_catalogo.json', JSON.stringify({ ...extra, plantillas: catalogo }, null, 1))
console.log(`${guiones.length} guiones · ${guiones.reduce((n, g) => n + g.pasos.length, 0)} pasos`)
await v.close()
