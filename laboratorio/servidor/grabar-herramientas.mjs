/* Paridad de las herramientas de diseño (frente C2): corre `ejecutar` de edicion.js sobre escenarios tomados de los bancos
 * (banco2.py, banco_pestanas.py, banco_ficha.py) y graba entradas y salidas para que test_herramientas_paridad.py corra lo mismo con
 * edicion.py sobre el documento equivalente y compare el TEXTO del resultado y cómo quedan bloques, pestañas, marca y secciones.
 * Uso (desde la raíz del repo): node laboratorio/servidor/grabar-herramientas.mjs [carpeta]
 *   carpeta por defecto: nucleo/tests/crm/fixtures/lab
 * Escribe herramientas_casos.json y herramientas_esquemas.json (HERRAMIENTAS, leer_enlace y herramientasPara de chat.js).
 * Sin IA ni red. Los uid nuevos salen de Date.now()+azar: la prueba los normaliza. */
import { createServer } from 'vite'
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const LAB = fileURLToPath(new URL('..', import.meta.url))
const destino = resolve(process.argv[2] || join(LAB, '..', 'nucleo/tests/crm/fixtures/lab'))
const vite = await createServer({ configFile: join(LAB, 'vite.config.js'), server: { middlewareMode: true, hmr: false }, logLevel: 'error' })
try {
  const ed = await vite.ssrLoadModule('/src/plantillas/edicion.js')
  const { plantillaPorId } = await vite.ssrLoadModule('/src/plantillas/semillas.js')
  // En el CRM no hay secciones con `fuente` (cada sección tiene sus registros): se quita la de membresías para comparar igual.
  const plantilla = (id) => { const p = plantillaPorId(id); return { ...p, secciones: p.secciones.filter((s) => !s.fuente) } }

  // ── Estados de los bancos ──
  const E2 = { vista: 'inicio', bloques: [{ uid: 'b0', vista: 'kpis', seccion: 'miembros', opciones: { por: 'estado' }, ancho: 12, alto: 1 },
    { uid: 'b1', vista: 'vencimientos', seccion: 'miembros', opciones: { fecha: 'vence', titulo: 'nombre', dias: 30 }, ancho: 6, alto: 2 },
    { uid: 'b2', vista: 'grafica', seccion: 'miembros', opciones: { tipo: 'linea', fecha: 'alta' }, ancho: 6, alto: 2 }] }
  const BP = [{ uid: 'b0', vista: 'kpis', seccion: 'miembros', opciones: { por: 'estado' }, ancho: 12, alto: 1 },
    { uid: 'b1', vista: 'vencimientos', seccion: 'miembros', opciones: { fecha: 'vence', titulo: 'nombre', dias: 30 }, ancho: 12, alto: 2 }]
  const EP = (vista = 'inicio', paginas) => ({ vista, bloques: BP, ...(paginas ? { estructura: { paginas } } : {}) })
  const PAG = { miembros: [{ uid: 'p_miembros', seccion: 'miembros', vista: 'tabla', opciones: {}, ancho: 12, alto: 3 },
    { uid: 'pz1', seccion: 'miembros', vista: 'grafico', opciones: { tipo: 'dona' }, ancho: 6, alto: 2 }] }
  const PNG = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
  const TOMA = { activa: true, fase: 'juntando', ficha: { objetivo: '', secciones: [], bloques: [], marca: {}, restricciones: [] }, notas: [], preguntadas: [], rechazo: false }

  // Escenario = estado inicial + pasos [nombre, args, contexto?] que se encadenan (cada paso parte del estado del anterior).
  const ESC = [
    // banco2: marca
    ['marca: colores y letra', E2, [['cambiar_marca', { primario: '#16A34A', secundario: '#7C3AED', fuenteTitulos: 'Nunito', fuenteTexto: 'Nunito' }]]],
    ['marca: hex inválido', E2, [['cambiar_marca', { primario: 'verde' }]]],
    ['marca: tipografía que no hay', E2, [['cambiar_marca', { fuenteTexto: 'Comic Sans' }]]],
    ['marca: ajustes de contraste', E2, [['cambiar_marca', { fondo: '#ffffff', texto: '#eeeeee', primario: 'ffff00', nombre: 'Gimnasio Sol' }]]],
    ['marca: quitar un color y restablecer', E2, [['cambiar_marca', { primario: '#16A34A', fondo: '#101010' }], ['cambiar_marca', { fondo: '' }], ['restablecer_marca', {}]]],
    ['logo: png, jpg y sin imagen', E2, [['usar_logo', {}, { imagen: 'data:image/jpeg;base64,/9j/' }], ['usar_logo', {}, {}], ['usar_logo', {}, { imagen: PNG }]]],
    // banco2: estructura
    ['crear sección con campos', E2, [['crear_seccion', { titulo: 'Cobros', campos: [{ nombre: 'Miembro', tipo: 'texto' }, { nombre: 'Monto', tipo: 'dinero' }, { nombre: 'Fecha', tipo: 'fecha' }, { nombre: 'Pagado', tipo: 'estado', opciones: ['Sí', 'No'] }] }, { texto: 'quiero llevar cobros de cada miembro con monto, fecha y si ya pagó' }]]],
    ['crear sección desde la biblioteca con piezas', E2, [['crear_seccion', { desde: 'inventario', con_piezas: true }]]],
    ['crear sección desde la biblioteca sin piezas', E2, [['crear_seccion', { desde: 'cobros', titulo: 'Mensualidades' }]]],
    ['crear sección: base que no hay, repetida, sin campos, tipo malo, estado sin opciones', E2, [
      ['crear_seccion', { desde: 'nada' }], ['crear_seccion', { titulo: 'Miembros', campos: [{ nombre: 'Nombre', tipo: 'texto' }] }], ['crear_seccion', { titulo: 'Gastos' }],
      ['crear_seccion', { titulo: 'Gastos', campos: [{ nombre: 'Color', tipo: 'color' }] }], ['crear_seccion', { titulo: 'Gastos', campos: [{ nombre: 'Tipo', tipo: 'estado' }] }]]],
    ['crear sección tablero y ponerla en el inicio', E2, [['crear_seccion', { titulo: 'Clases', vista: 'tablero', opciones: { por: 'estado' }, campos: [{ nombre: 'Clase', tipo: 'texto' }, { nombre: 'Estado', tipo: 'estado', opciones: ['Abierta', 'Llena'] }] }],
      ['agregar_bloque', { seccion: 'clases', vista: 'tablero', opciones: { por: 'estado', titulo: 'clase' } }]]],
    ['agregar campo', E2, [['agregar_campo', { seccion: 'miembros', nombre: 'Teléfono', tipo: 'texto' }, { texto: 'agrega a miembros un campo de teléfono' }]]],
    ['agregar campo con el nombre literal', E2, [['agregar_campo', { seccion: 'Miembros', nombre: 'cumpleanos', tipo: 'fecha' }, { texto: 'agrega el cumpleaños de cada miembro' }]]],
    ['agregar campo: tipo malo, repetido, estado sin opciones, sección sin campos', E2, [['agregar_campo', { seccion: 'miembros', nombre: 'Color', tipo: 'color' }],
      ['agregar_campo', { seccion: 'miembros', nombre: 'Plan', tipo: 'texto' }], ['agregar_campo', { seccion: 'miembros', nombre: 'Nivel', tipo: 'estado' }], ['agregar_campo', { seccion: 'actividad', nombre: 'X', tipo: 'texto' }]]],
    ['agregar campos hasta el máximo', E2, [['agregar_campo', { seccion: 'miembros', nombre: 'Teléfono', tipo: 'texto' }], ['agregar_campo', { seccion: 'miembros', nombre: 'Correo', tipo: 'texto' }],
      ['agregar_campo', { seccion: 'miembros', nombre: 'Saldo', tipo: 'dinero' }], ['agregar_campo', { seccion: 'miembros', nombre: 'Nota', tipo: 'texto' }]]],
    ['renombrar sección', E2, [['renombrar_seccion', { seccion: 'miembros', titulo: 'Socios' }], ['renombrar_seccion', { seccion: 'nada', titulo: 'X' }], ['renombrar_seccion', { seccion: 'pagos', titulo: '  ' }]]],
    ['quitar sección', E2, [['quitar_seccion', { seccion: 'pagos' }], ['quitar_seccion', { seccion: 'nada' }]]],
    ['quitar la sección de las piezas del inicio', E2, [['quitar_seccion', { seccion: 'Miembros' }]]],
    // banco2: bloques
    ['agregar una dona chiquita', E2, [['agregar_bloque', { seccion: 'miembros', vista: 'grafico', opciones: { tipo: 'dona' }, ancho: 4 }]]],
    ['agregar: gráfico que no existe, que no se puede, vista que no hay, sección que no hay', E2, [['agregar_bloque', { seccion: 'miembros', vista: 'grafico', opciones: { tipo: 'velas' } }],
      ['agregar_bloque', { seccion: 'pagos', vista: 'grafico', opciones: { tipo: 'dona' } }], ['agregar_bloque', { seccion: 'miembros', vista: 'radar' }], ['agregar_bloque', { seccion: 'clientes', vista: 'tabla' }],
      ['agregar_bloque', { seccion: 'miembros', vista: 'grafico', opciones: { tipo: 'columnas', valor: 'precio' } }], ['agregar_bloque', { seccion: 'miembros', vista: 'tablero', opciones: { por: 'plan' } }]]],
    ['agregar: lista de un solo id se normaliza', E2, [['agregar_bloque', { seccion: 'pagos', vista: 'kpis', opciones: { suma: ['monto'] }, posicion: 2 }]]],
    ['pieza repetida (D55) y con «sí»', E2, [['agregar_bloque', { seccion: 'miembros', vista: 'kpis', opciones: { por: 'estado' } }],
      ['agregar_bloque', { seccion: 'miembros', vista: 'kpis', opciones: { por: 'estado' } }, { confirmado: true }]]],
    ['la gráfica a la izquierda', E2, [['mover_bloque', { bloque: 'b2', posicion: 1 }], ['cambiar_tamano', { bloque: 'b2', ancho: 4 }]]],
    ['tamaños: resumen más alto, bloque que no hay, alto fuera de rango', E2, [['cambiar_tamano', { bloque: 'b0', alto: 2 }], ['cambiar_tamano', { bloque: 'b9', ancho: 4 }], ['cambiar_tamano', { bloque: 'b1', alto: 9, ancho: 5 }]]],
    ['quitar la lista de vencimientos y la gráfica', E2, [['quitar_bloque', { bloque: 'b1' }], ['quitar_bloque', { bloque: 'b2' }], ['quitar_bloque', { bloque: 'b2' }]]],
    ['cambiar la vista de un bloque', E2, [['cambiar_visual', { bloque: 'b2', vista: 'grafico', opciones: { tipo: 'columnas' } }], ['cambiar_visual', { bloque: 'b9', vista: 'tabla' }]]],
    ['rangos de vencimientos', E2, [['cambiar_rangos', { bloque: 'b1', rangos: [{ vencidos: true }, { desde: 0, hasta: 7 }, { desde: 5, hasta: 30 }] }],
      ['cambiar_rangos', { bloque: 'b0', rangos: [{ desde: 0, hasta: 7 }] }], ['cambiar_rangos', { bloque: 'b1', rangos: [] }], ['cambiar_rangos', { bloque: 'b1', rangos: [{ desde: 10, hasta: 2 }] }],
      ['cambiar_rangos', { bloque: 'b1', rangos: [{ desde: 0, hasta: 15 }, { desde: 16, hasta: 60 }] }]]],
    ['navegar', E2, [['abrir_seccion', { seccion: 'pagos' }], ['abrir_seccion', { seccion: 'Historial' }], ['abrir_seccion', { seccion: 'nada' }], ['abrir_seccion', { seccion: 'inicio' }]]],
    // banco_pestanas
    ['calendario en el inicio', EP(), [['agregar_bloque', { seccion: 'miembros', vista: 'calendario_mes', opciones: { fecha: 'vence', titulo: 'nombre' } }]]],
    ['cifra con meta', EP(), [['agregar_bloque', { seccion: 'miembros', vista: 'cifra', opciones: { funcion: 'conteo', meta: 300 } }]]],
    ['tablero con montos en pagos (no tiene estado)', EP(), [['agregar_bloque', { seccion: 'pagos', vista: 'tablero_dinero', opciones: { suma: 'monto' } }]]],
    ['pieza en la pestaña que está mirando', EP('miembros'), [['agregar_bloque', { vista: 'kpis', opciones: { por: 'estado' } }]]],
    ['pieza en otra pestaña nombrándola', EP(), [['agregar_bloque', { pestana: 'pagos', vista: 'grafico', opciones: { tipo: 'columnas' } }]]],
    ['quitar lo elegido dentro de una pestaña', EP('miembros', PAG), [['quitar_bloque', { bloque: 'pz1' }]]],
    ['cambiar la vista base de una pestaña', EP('miembros'), [['cambiar_visual', { bloque: 'p_miembros', vista: 'tablero', opciones: { por: 'estado' } }]]],
    ['mirando una pestaña: el inicio pide pestana=inicio', EP('miembros'), [['cambiar_visual', { bloque: 'b0', vista: 'tabla' }], ['agregar_bloque', { pestana: 'inicio', vista: 'tabla', seccion: 'pagos' }]]],
    ['pestañas que no existen o no admiten piezas', EP(), [['agregar_bloque', { pestana: 'nada', vista: 'tabla', seccion: 'miembros' }], ['agregar_bloque', { pestana: 'actividad', vista: 'tabla', seccion: 'miembros' }]]],
    ['tamaño en la pestaña y acomodo', EP('inicio', PAG), [['cambiar_tamano', { bloque: 'p_miembros', ancho: 6 }], ['mover_bloque', { bloque: 'pz1', posicion: 1 }]]],
    // banco_ficha
    ['ficha con grupo Fechas', E2, [['cambiar_ficha', { seccion: 'miembros', grupos: [{ titulo: 'Principal', campos: ['plan', 'estado'] }, { titulo: 'Fechas', campos: ['alta', 'vence'] }] }]]],
    ['ficha sin relacionados; errores', E2, [['cambiar_ficha', { seccion: 'miembros', grupos: [{ titulo: 'Datos', campos: ['nombre', 'plan'] }], relacionados: false }],
      ['cambiar_ficha', { seccion: 'miembros', grupos: [{ titulo: 'A', campos: ['nombre', 'telefono'] }] }], ['cambiar_ficha', { seccion: 'miembros', grupos: [{ titulo: 'A', campos: ['nombre'] }, { titulo: 'B', campos: ['nombre'] }] }],
      ['cambiar_ficha', { seccion: 'miembros', grupos: [] }]]],
    ['tarjetas', E2, [['cambiar_tarjeta', { seccion: 'miembros', campos: ['nombre', 'plan'] }], ['cambiar_tarjeta', { seccion: 'miembros', campos: ['nombre', 'plan', 'alta', 'vence', 'estado'] }],
      ['cambiar_tarjeta', { seccion: 'miembros', campos: ['nombre', 'color'] }]]],
    ['renombrar campo', E2, [['renombrar_campo', { seccion: 'miembros', campo: 'vence', nombre: 'Fecha de vencimiento' }], ['renombrar_campo', { seccion: 'miembros', campo: 'plan', nombre: 'nombre' }],
      ['renombrar_campo', { seccion: 'miembros', campo: 'telefono', nombre: 'Tel' }]]],
    ['estado: agregar Congelada', E2, [['cambiar_opciones_estado', { seccion: 'miembros', campo: 'estado', opciones: ['Activa', 'Pausada', 'Cancelada', 'Congelada'] }]]],
    ['estado: quitar Pausada con destino; sin destino; renombrar', E2, [['cambiar_opciones_estado', { seccion: 'miembros', campo: 'estado', opciones: ['Activa', 'Cancelada'] }],
      ['cambiar_opciones_estado', { seccion: 'miembros', campo: 'estado', opciones: ['Activa', 'Cancelada'], pasar_a: 'Activa' }],
      ['cambiar_opciones_estado', { seccion: 'miembros', campo: 'estado', opciones: ['Activa', 'Baja'], renombrar: { Cancelada: 'Baja' } }],
      ['cambiar_opciones_estado', { seccion: 'miembros', campo: 'plan', opciones: ['A', 'B'] }], ['cambiar_opciones_estado', { seccion: 'miembros', campo: 'estado', opciones: ['Activa'] }]]],
    ['quitar el campo alta (lo usa la gráfica)', E2, [['quitar_campo', { seccion: 'miembros', campo: 'alta' }], ['quitar_campo', { seccion: 'miembros', campo: 'nada' }]]],
    ['quitar un campo libre', E2, [['cambiar_ficha', { seccion: 'miembros', grupos: [{ titulo: 'Datos', campos: ['nombre', 'plan'] }] }], ['cambiar_tarjeta', { seccion: 'miembros', campos: ['nombre', 'plan'] }],
      ['quitar_campo', { seccion: 'miembros', campo: 'plan' }]]],
    // toma
    ['con la ficha de diseño abierta', { ...E2, toma: TOMA }, [['agregar_bloque', { seccion: 'miembros', vista: 'tabla' }], ['cambiar_marca', { primario: '#16A34A' }], ['abrir_seccion', { seccion: 'pagos' }]]],
    ['abrir la toma', E2, [['abrir_toma', { objetivo: 'controlar mis cobros' }], ['anotar_bloque', { que: 'resumen', seccion: 'miembros' }], ['cerrar_toma', {}, { texto: 'olvídalo' }]]],
    ['herramienta que no existe', E2, [['pintar', {}]]],
  ]

  const casos = []
  for (const [caso, inicial, pasos] of ESC) {
    const p = plantilla('membresias')
    let estado = structuredClone(inicial)
    const salidas = []
    for (const [nombre, args, contexto = {}] of pasos) {
      const r = ed.ejecutar(p, estado, nombre, structuredClone(args), contexto)
      estado = r.estado
      const ef = ed.plantillaEfectiva(p, estado)
      salidas.push({ ok: r.ok, resultado: r.resultado, etiqueta: r.ok ? ed.etiquetaCambio({ herramienta: nombre, args }) : null, vista: estado.vista || 'inicio',
        bloques: estado.bloques, paginas: estado.estructura?.paginas || {}, marca: estado.marca || {},
        secciones: ef.secciones.filter((s) => s.campos).map((s) => ({ id: s.id, titulo: s.titulo, campos: s.campos.map((c) => ({ id: c.id, nombre: c.nombre, tipo: c.tipo, ...(c.opciones ? { opciones: c.opciones } : {}) })),
          vista: s.vista, opciones: s.opciones || {}, ...(s.ficha ? { ficha: s.ficha } : {}), ...(s.tarjeta ? { tarjeta: s.tarjeta } : {}) })),
        ...(salidas.length === pasos.length - 1 ? { describir: ed.describirPantalla(p, estado) } : {}) })
    }
    casos.push({ caso, plantilla: 'membresias', estado: inicial, pasos: pasos.map(([nombre, args, contexto = {}]) => ({ nombre, args, contexto })), salidas })
  }

  // Esquemas: HERRAMIENTAS de edicion.js y, de chat.js, leer_enlace y el filtro herramientasPara (se evalúan sus líneas tal cual).
  const chat = readFileSync(join(LAB, 'servidor/chat.js'), 'utf8')
  const linea = (n) => chat.split('\n').find((l) => l.startsWith(`const ${n} =`))
  const { HERR_ENLACE, herramientasPara } = new Function(`${linea('HERR_ENLACE')}\n${linea('SOLO_EN_TOMA')}\n${linea('herramientasPara')}\nreturn { HERR_ENLACE, herramientasPara }`)()
  const nombres = (hs) => hs.map((h) => h.function.name)
  const esquemas = { HERRAMIENTAS: ed.HERRAMIENTAS, HERR_ENLACE, para: [
    { toma: false, imagen: false, nombres: nombres(herramientasPara(ed, {}, null)) }, { toma: false, imagen: true, nombres: nombres(herramientasPara(ed, {}, 'data:image/png;base64,x')) },
    { toma: true, imagen: false, nombres: nombres(herramientasPara(ed, { toma: { activa: true } }, null)) }, { toma: true, imagen: true, nombres: nombres(herramientasPara(ed, { toma: { activa: true } }, 'x')) }] }

  mkdirSync(destino, { recursive: true })
  writeFileSync(join(destino, 'herramientas_casos.json'), `${JSON.stringify(casos)}\n`)
  writeFileSync(join(destino, 'herramientas_esquemas.json'), `${JSON.stringify(esquemas, null, 1)}\n`)
  console.log(`herramientas_casos: ${casos.length} escenarios, ${casos.reduce((n, c) => n + c.pasos.length, 0)} llamadas · esquemas: ${ed.HERRAMIENTAS.length}`)
} finally {
  await vite.close()
}
