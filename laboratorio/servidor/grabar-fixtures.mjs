/* Fixtures dorados (D61, contrato §6): casos de las funciones puras del laboratorio con su resultado EXACTO, para que el
 * port a Python se compare contra lo mismo. Sin IA ni red.
 * Uso (desde la raíz del repo): node laboratorio/servidor/grabar-fixtures.mjs [carpeta]
 *   carpeta por defecto: nucleo/tests/crm/fixtures/lab
 * Formato de cada <funcion>.json: [ { caso, entrada: { …argumentos por nombre }, salida } ], un caso por línea.
 * Argumentos (los nombres de los parámetros en JS):
 *  - parseFecha {texto, hoy} · parsePeriodo {texto, hoy}: `hoy` = 'AAAA-MM-DD' (fecha LOCAL; casi siempre 2026-10-16)
 *  - parseNumero {texto} (texto puede ser número) · parseHora {texto} · fechaLarga {isoTexto} (puede ser null)
 *  - opcionDe {campo, valor} · buscarRegistro {registros, seccion, campos, consulta}
 *  - acomodar {bloques, fijos: [uid]} · compatibles {campos} · afirmaCambio {texto} · revertirDatos {antes, despues, actual}
 * Determinista: zona horaria UTC, `hoy` siempre explícito y azar con semilla fija (no depende del día en que se corre).
 * Los casos de laboratorio/pruebas/*.test.mjs van primero (caso «prueba: …»); después, los generados. */
process.env.TZ = 'UTC'
const { createServer } = await import('vite')
const { mkdirSync, writeFileSync } = await import('node:fs')
const { join, resolve } = await import('node:path')
const { fileURLToPath } = await import('node:url')

const LAB = fileURLToPath(new URL('..', import.meta.url))
const RAIZ = resolve(LAB, '..')
const destino = resolve(process.argv[2] || join(RAIZ, 'nucleo/tests/crm/fixtures/lab'))
const HOY = '2026-10-16' // viernes
const fecha = (iso) => { const [y, m, d] = iso.split('-').map(Number); return new Date(y, m - 1, d) }
let semilla = 7
const azar = () => ((semilla = (semilla * 1103515245 + 12345) % 2147483648) / 2147483648)
const elegir = (xs) => xs[Math.floor(azar() * xs.length)]
const entre = (a, b) => a + Math.floor(azar() * (b - a + 1))

const vite = await createServer({ configFile: join(LAB, 'vite.config.js'), server: { middlewareMode: true, hmr: false }, logLevel: 'error' })
try {
  const V = await vite.ssrLoadModule('/src/plantillas/valores.js')
  const { afirmaCambio } = await vite.ssrLoadModule('/servidor/afirma.js')
  const { acomodar, ejecutar, revertirDatos } = await vite.ssrLoadModule('/src/plantillas/edicion.js')
  const { compatibles } = await vite.ssrLoadModule('/src/plantillas/graficos-catalogo.js')
  const { PLANTILLAS, plantillaPorId } = await vite.ssrLoadModule('/src/plantillas/semillas.js')
  const { PESTANAS } = await vite.ssrLoadModule('/src/plantillas/edicion.js')
  const { camposDe } = await vite.ssrLoadModule('/src/plantillas/validar.js')

  const salida = {}
  /** Agrega un caso. `fn` recibe la entrada (la de JSON) y devuelve el resultado; se graba tal cual lo da JSON. */
  const grabar = (nombre, fn) => {
    const casos = (salida[nombre] ||= []); const vistos = new Set()
    return (caso, entrada) => {
      const clave = JSON.stringify(entrada); if (vistos.has(clave)) return; vistos.add(clave)
      const r = fn(structuredClone(entrada))
      casos.push({ caso, entrada, salida: r === undefined ? null : JSON.parse(JSON.stringify(r)) })
    }
  }

  // ── parseFecha ──────────────────────────────────────────────────────────────────────────────────
  const pf = grabar('parseFecha', (e) => V.parseFecha(e.texto, fecha(e.hoy)))
  const PRUEBA_F = ['2026-10-30', '30/10/2026', '30-10-26', '30/10', 'el 30 de octubre', '30 de octubre de 2027', '30 oct', 'oct 30', 'hoy', 'mañana', 'pasado mañana',
    'ayer', 'en 5 días', 'dentro de dos semanas', 'en un mes', 'hace 3 días', 'el viernes', 'el próximo jueves', 'el lunes', '31/02/2026', 'cuando pueda', '',
    '15 de octubre del próximo año', '15 de octubre del año que viene', '1 de marzo de este año', '3 de enero del año pasado', 'en un año',
    'un mes desde hoy', 'hoy + 1 mes', 'hoy+30 días', '30 días a partir de hoy', 'dentro de 2 semanas desde hoy']
  for (const t of PRUEBA_F) pf(`prueba: «${t}»`, { texto: t, hoy: HOY })
  const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
  const DIAS = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo', 'miercoles', 'sabado']
  const UNIDADES = ['día', 'días', 'semana', 'semanas', 'mes', 'meses', 'año', 'años']
  const relativas = () => {
    const ts = ['hoy', 'Hoy', 'mañana', 'manana', 'pasado mañana', 'ayer', 'HOY']
    for (const n of [0, 1, 2, 3, 5, 7, 10, 14, 15, 20, 21, 28, 29, 30, 31, 45, 60, 90, 365]) ts.push(`en ${n} días`, `dentro de ${n} dias`, `hace ${n} días`, `hoy + ${n} días`, `${n} días a partir de hoy`)
    for (const n of [1, 2, 3, 4, 6, 8, 12]) ts.push(`en ${n} semanas`, `hace ${n} semanas`, `en ${n} meses`, `dentro de ${n} meses`, `hoy+${n} meses`, `${n} meses desde hoy`)
    for (const n of [1, 2, 3]) ts.push(`en ${n} años`, `${n} años después de hoy`)
    for (const w of ['un', 'una', 'dos', 'tres']) for (const u of UNIDADES) ts.push(`en ${w} ${u}`, `hace ${w} ${u}`, `${w} ${u} contando desde hoy`)
    for (const d of DIAS) ts.push(d, `el ${d}`, `este ${d}`, `próximo ${d}`, `el próximo ${d}`, `el proximo ${d}`, d.toUpperCase())
    return ts
  }
  for (const t of relativas()) pf(`relativa «${t}»`, { texto: t, hoy: HOY })
  for (const [i, m] of MESES.entries()) {
    for (const d of [1, 2, 9, 15, 28, 29, 30, 31]) {
      for (const t of [`${d} de ${m}`, `el ${d} de ${m}`, `${d} ${m}`, `${d} ${m.slice(0, 3)}`, `${m} ${d}`, `${m.slice(0, 3)} ${d}`, `${d} de ${m} de 2027`, `${d} de ${m} del 2025`,
        `${m} ${d}, 2028`, `${d}/${i + 1}`, `${d}/${i + 1}/2027`, `${d}-${i + 1}-27`, `${d}.${i + 1}.2026`, `2026-${String(i + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`,
        `${d} de ${m} del próximo año`, `${d} de ${m} del año pasado`, `${d} de ${m} de este año`, `${d} de ${m} del año entrante`, `${d} de ${m} del siguiente año`]) pf(`día y mes «${t}»`, { texto: t, hoy: HOY })
    }
  }
  for (const t of ['cuando pueda', 'el', 'la', 'mañana temprano', '32 de enero', 'oct', '2026-13-01', '2026-02-29', '2024-02-29', '29/02/2024', '29/02/25', '0/10', '10/0',
    'el 30', 'de octubre', 'mes que viene', 'próxima semana', 'el fin de semana', 'en 2 horas', 'hace 1 mes', 'en -3 días', '  30 de octubre  ', 'El 30 De Octubre', '30 DE OCTUBRE',
    'sept 15', 'setiembre 15', '15 de set', 'mar 3', '3 mar', 'jun 31', '1/1/1999', '31-12-99', '2026-1-5', '2026/10/30', 'mañana a las 3', null]) pf(`raro «${t}»`, { texto: t, hoy: HOY })
  // Otros «hoy»: fin de mes (setMonth de JS se desborda: 31 ene + 1 mes = 3 mar), bisiesto y fin de año.
  for (const h of ['2026-01-31', '2026-02-28', '2024-02-29', '2026-12-31', '2027-03-31', '2026-10-18', '2026-10-19']) {
    for (const t of ['hoy', 'mañana', 'ayer', 'pasado mañana', 'en un mes', 'en 2 meses', 'en un año', 'en 1 semana', 'hace 2 semanas', 'en 30 días', 'el lunes', 'el domingo', 'el viernes', 'el sábado',
      '30/10', '29 de febrero', '15 de enero del próximo año', '1 de marzo del año pasado', 'un mes desde hoy', 'hoy + 13 meses', '31 dic', 'enero 1']) pf(`hoy ${h} «${t}»`, { texto: t, hoy: h })
  }

  // ── parsePeriodo ────────────────────────────────────────────────────────────────────────────────
  const pp = grabar('parsePeriodo', (e) => V.parsePeriodo(e.texto, fecha(e.hoy)))
  for (const t of ['hoy', 'esta semana', 'la semana pasada', 'la próxima semana', 'este mes', 'el mes pasado', 'el próximo mes', 'este año', 'los últimos 30 días', 'los próximos 7 días',
    'vencidos', 'octubre', 'en febrero', 'diciembre de 2025', 'del 1 al 15 de octubre', 'del 3 de octubre al 2 de noviembre', 'el 30 de octubre', 'cuando llueva', 'del 15 al 1 de octubre']) pp(`prueba: «${t}»`, { texto: t, hoy: HOY })
  const PERIODOS = ['hoy', 'mañana', 'ayer', 'esta semana', 'semana actual', 'semana pasada', 'anterior semana', 'proxima semana', 'semana que viene', 'siguiente semana', 'este mes', 'mes actual',
    'mes pasado', 'anterior mes', 'proximo mes', 'mes que viene', 'siguiente mes', 'este año', 'año actual', 'año pasado', 'el año pasado', 'vencidos', 'vencidas', 'vencido', 'ya vencidos',
    'atrasados', 'atrasada', 'durante esta semana', 'para el próximo mes', 'en este mes', 'de este año', 'los últimos 7 días', 'las últimas 2 semanas', 'los ultimos una semana', 'últimos tres días',
    'los próximos 30 días', 'las próximas 2 semanas', 'siguientes 10 dias', 'próximos un día', 'del 1 al 31 de diciembre', 'del 10 al 20 de marzo de 2027', 'desde el 5 hasta el 9 de mayo',
    '1 al 15 de octubre', 'del 1 a 15 de octubre', 'del 30 al 31 de febrero', 'del hoy al viernes', 'desde hoy hasta el 30 de octubre', 'del lunes al viernes', 'del 1/10 al 15/10', 'del 30/10 al 1/10',
    'desde mañana hasta en 2 semanas', 'mayo', 'mayo de 2027', 'mayo del 2025', 'may', 'sept', 'septiembre', 'setiembre', 'dic 2026', 'el 3', 'nunca', '', 'en 5 días', 'el viernes', '30/10']
  for (const t of PERIODOS) pp(`periodo «${t}»`, { texto: t, hoy: HOY })
  for (const m of MESES) pp(`mes «${m}»`, { texto: m, hoy: HOY })
  for (const h of ['2026-01-01', '2026-01-31', '2026-03-01', '2024-02-29', '2026-12-31', '2026-10-18', '2026-10-19']) {
    for (const t of ['hoy', 'esta semana', 'la semana pasada', 'la próxima semana', 'este mes', 'el mes pasado', 'el próximo mes', 'este año', 'el año pasado', 'los últimos 30 días',
      'los próximos 7 días', 'vencidos', 'febrero', 'del 1 al 15 de enero']) pp(`hoy ${h} «${t}»`, { texto: t, hoy: h })
  }

  // ── parseNumero ─────────────────────────────────────────────────────────────────────────────────
  const pn = grabar('parseNumero', (e) => V.parseNumero(e.texto))
  for (const t of ['Q1,200.50', '1.200,50', '$ 300', '500 quetzales', '12,5', '1,200', '1,200,000', '1.200.000', '3.5', 45, 'nada']) pn(`prueba: «${t}»`, { texto: t })
  for (const t of [0, -2, 3.14, 1e6, 0.1, '0', '-15', '-1,5', '-1.200,50', '1.234.567,89', '1,234,567.89', '0.5', ',5', '.5', '5.', '5,', '1,2,3', '1.2.3', '12,34', '123,456', '1234,567', '12,345',
    '1,23', 'Q 12', 'USD 1,000', '1 000', '1 000,50', 'mil', '', null, '  7  ', 'Q-50', '50-', '5-5', '--5', '1e3', '₡2.500', '€3,99', '2,500.', '0,001', '0.001', '1.000', '10.000', '100.000,5',
    'quince', 'q', '$', '%50', '50%', '3 1/2', '1,5,5.5', '9.99.9']) pn(`número «${t}»`, { texto: t })
  for (let i = 0; i < 150; i++) { // montos al azar escritos de varias formas
    const ent = entre(0, 2500000), dec = entre(0, 99), miles = String(ent).replace(/\B(?=(\d{3})+(?!\d))/g, ',')
    const t = elegir([`${ent}`, `${miles}`, `${miles}.${String(dec).padStart(2, '0')}`, `${miles.replace(/,/g, '.')},${String(dec).padStart(2, '0')}`, `Q${miles}`, `$ ${ent}.${dec}`, `${ent},${dec}`])
    pn(`al azar «${t}»`, { texto: t })
  }

  // ── parseHora ───────────────────────────────────────────────────────────────────────────────────
  const ph = grabar('parseHora', (e) => V.parseHora(e.texto))
  for (const t of ['9am', '9:30', '15:00', '3 pm', '3 de la tarde', '8 de la noche', '12 am', 'mediodía', '25:00', 'tarde']) ph(`prueba: «${t}»`, { texto: t })
  for (let h = 0; h <= 24; h++) for (const mm of ['00', '05', '30', '59', '60']) for (const t of [`${h}:${mm}`, `${String(h).padStart(2, '0')}:${mm}`]) ph(`hora «${t}»`, { texto: t })
  for (let h = 0; h <= 13; h++) {
    for (const s of ['', 'am', ' am', 'pm', ' pm', 'a.m.', ' a. m.', 'p.m.', ' p. m.', ' de la mañana', ' de la manana', ' de la tarde', ' de la noche', 'h', ' hrs', ' hr', 'AM', ' PM'])
      for (const t of [`${h}${s}`, `${h}:15${s}`]) ph(`hora «${t}»`, { texto: t })
  }
  for (const t of ['mediodia', 'Mediodía', 'medianoche', '', null, 'a las 3', '3 y media', '9.30', '9h30', '930', '09:3', ':30', '3pm!', '15:00 hrs', '12 pm', '12:30 am', '0 pm', 'las 9']) ph(`rara «${t}»`, { texto: t })

  // ── opcionDe ────────────────────────────────────────────────────────────────────────────────────
  const od = grabar('opcionDe', (e) => V.opcionDe(e.campo, e.valor))
  const est = { opciones: ['Activa', 'Pausada', 'Cancelada'] }
  od('prueba: sin mayúsculas ni acentos', { campo: est, valor: 'pausada' }); od('prueba: no existe', { campo: est, valor: 'Congelada' })
  const todasSecciones = [...PLANTILLAS.flatMap((p) => p.secciones.map((s) => [p.id, s, camposDe(s, Object.fromEntries(p.secciones.map((x) => [x.id, x])))])),
    ...Object.values(PESTANAS).map((p) => [`pestana-${p.id}`, { ...p.seccion, id: p.id }, p.seccion.campos || []])]
  const listas = new Map()
  for (const [, , campos] of todasSecciones) for (const c of campos) if (c.tipo === 'estado' && c.opciones) listas.set(JSON.stringify(c.opciones), c.opciones)
  const quitarAcentos = (t) => t.normalize('NFD').replace(/[\u0300-\u036f]/g, '')
  for (const ops of listas.values()) {
    const campo = { opciones: ops }
    for (const o of ops) { od(`«${o}» en minúsculas sin acentos`, { campo, valor: quitarAcentos(o).toLowerCase() }); od(`«${o}» en mayúsculas con espacios`, { campo, valor: `  ${o.toUpperCase()} ` }) }
    od(`opción inexistente en ${ops.join('/')}`, { campo, valor: 'Otra cosa' })
  }
  for (const v of ['', null, 'activa ', 'ACTIVA', 'activá', 'Activ', 'Activas']) od(`borde «${v}»`, { campo: est, valor: v })
  od('campo sin opciones', { campo: {}, valor: 'Activa' }); od('opción con eñe', { campo: { opciones: ['Diseño', 'Año nuevo'] }, valor: 'diseno' })

  // ── fechaLarga ──────────────────────────────────────────────────────────────────────────────────
  const fl = grabar('fechaLarga', (e) => V.fechaLarga(e.isoTexto))
  fl('prueba: 30 de octubre', { isoTexto: '2026-10-30' }); fl('prueba: 5 de enero', { isoTexto: '2026-01-05' })
  for (let d = fecha('2026-01-01'); d <= fecha('2026-12-31'); d.setDate(d.getDate() + 1)) { const iso = d.toISOString().slice(0, 10); fl(`día ${iso}`, { isoTexto: iso }) }
  for (const t of ['2024-02-29', '1999-12-31', '2026-13-45', '2026-1-5', '2026/10/30', '2026-10-30T10:00', ' 2026-10-30', 'mañana', '', null, '0000-00-00']) fl(`borde «${t}»`, { isoTexto: t })

  // ── buscarRegistro ──────────────────────────────────────────────────────────────────────────────
  const br = grabar('buscarRegistro', (e) => V.buscarRegistro(e.registros, e.seccion, e.campos, e.consulta))
  {
    const sec = { id: 'miembros' }, campos = [{ id: 'nombre', tipo: 'texto' }, { id: 'plan', tipo: 'texto' }, { id: 'estado', tipo: 'estado' }]
    const R = [{ id: 'a', valores: { nombre: 'Ana López', plan: 'Mensual' } }, { id: 'b', valores: { nombre: 'Ana Martínez', plan: 'Anual' } }, { id: 'c', valores: { nombre: 'Carlos Pérez', plan: 'Mensual' } }]
    for (const q of ['ana lopez', 'Ana', 'Pérez', 'b', 'Rosa Gómez']) br(`prueba: «${q}»`, { registros: R, seccion: sec, campos, consulta: q })
  }
  const NOMBRES = ['Ana', 'Ana María', 'Carlos', 'José', 'María', 'Luis', 'Rosa', 'Andrés', 'Sofía', 'Pedro', 'Lucía', 'Juan', 'Juana', 'Mario', 'Marina']
  const APELLIDOS = ['López', 'Martínez', 'Pérez', 'Gómez', 'García', 'Hernández', 'Ramírez', 'Morales', 'Castillo', 'Lopera']
  const conTexto = todasSecciones.filter(([, , c]) => c.some((x) => x.tipo === 'texto')).filter((_, i) => i % 6 === 0)
  for (const [pid, s, campos] of conTexto) {
    const textos = campos.filter((c) => !['estado', 'fecha', 'hora', 'numero', 'dinero'].includes(c.tipo))
    const regs = Array.from({ length: entre(3, 9) }, (_, i) => ({ id: `${s.id}-${i}`, valores: Object.fromEntries(campos.map((c) => [c.id,
      c.tipo === 'texto' ? (c === textos[0] ? `${elegir(NOMBRES)} ${elegir(APELLIDOS)}` : (c.ejemplos ? elegir(c.ejemplos) : `${elegir(APELLIDOS)} ${entre(1, 99)}`))
        : c.tipo === 'estado' ? elegir(c.opciones || ['x']) : c.tipo === 'numero' || c.tipo === 'dinero' ? entre(1, 5000) : c.tipo === 'fecha' ? `2026-${String(entre(1, 12)).padStart(2, '0')}-${String(entre(1, 28)).padStart(2, '0')}` : '09:00']).filter(() => azar() > 0.08)) }))
    const seccion = { id: s.id, ...(s.tarjeta ? { tarjeta: s.tarjeta } : {}) }
    const qs = new Set([regs[0].id, 'no-existe', '', '   ', 'Zacarías Quiñónez'])
    for (const r of regs.slice(0, 4)) {
      const n = String(r.valores[textos[0].id] || ''); if (!n) continue
      const [a, b] = n.split(' ')
      qs.add(n); qs.add(quitarAcentos(n).toLowerCase()); qs.add(a); qs.add(b); qs.add(b?.slice(0, 4)); qs.add(`${a.slice(0, 3)} ${b}`); qs.add(n.toUpperCase())
      const otro = textos[1] && r.valores[textos[1].id]; if (otro) { qs.add(String(otro)); qs.add(`${a} ${String(otro).split(' ')[0]}`) }
    }
    for (const q of qs) if (q !== undefined) br(`${pid}/${s.id} «${q}»`, { registros: regs, seccion, campos, consulta: q })
  }
  br('tarjeta elige el campo del nombre', { registros: [{ id: 'x1', valores: { codigo: 'A-1', cliente: 'Ana López' } }, { id: 'x2', valores: { codigo: 'A-2', cliente: 'Ana Pérez' } }],
    seccion: { id: 's', tarjeta: { campos: ['cliente'] } }, campos: [{ id: 'codigo', tipo: 'texto' }, { id: 'cliente', tipo: 'texto' }], consulta: 'ana lopez' })
  br('sin campos de texto', { registros: [{ id: 'n1', valores: { monto: 5 } }], seccion: { id: 's' }, campos: [{ id: 'monto', tipo: 'numero' }], consulta: '5' })

  // ── acomodar ────────────────────────────────────────────────────────────────────────────────────
  const ac = grabar('acomodar', (e) => acomodar(e.bloques, new Set(e.fijos || [])))
  const B = (uid, ancho, alto = 2, vista = 'grafico') => ({ uid, ancho, alto, vista, seccion: 's', opciones: {} })
  ac('prueba: sin huecos no cambia nada', { bloques: [B('a', 12, 1, 'kpis'), B('b', 6), B('c', 6)], fijos: [] })
  ac('prueba: 8 + 3', { bloques: [B('a', 8), B('b', 3)], fijos: [] })
  ac('prueba: 4 + 4', { bloques: [B('a', 4), B('b', 4)], fijos: [] })
  ac('prueba: 6 + 6 + 6', { bloques: [B('a', 6), B('b', 6), B('c', 6)], fijos: [] })
  ac('prueba: 8×2 + 4×1', { bloques: [B('a', 8, 2), B('b', 4, 1)], fijos: [] })
  ac('prueba: kpis no crece de alto', { bloques: [B('k', 8, 1, 'kpis'), B('a', 4, 2)], fijos: [] })
  ac('prueba: fijo no se toca', { bloques: [B('a', 4), B('b', 8)], fijos: ['a'] })
  ac('prueba: orden', { bloques: [B('a', 3), B('b', 8), B('c', 3, 1), B('d', 6)], fijos: [] })
  ac('prueba: ubicar 6 + 6', { bloques: [B('a', 6), B('b', 6)], fijos: [] })
  ac('fijo: true en el bloque', { bloques: [{ ...B('a', 4), fijo: true }, B('b', 4)], fijos: [] })
  ac('vacío', { bloques: [], fijos: [] })
  for (const id of ['embudo', 'agenda', 'pedidos', 'membresias', 'proyectos', 'simple', ...PLANTILLAS.slice(6).map((p) => p.id)]) {
    const p = plantillaPorId(id)
    const bloques = p.inicio.map((b, i) => ({ ...b, uid: `b${i + 1}`, ancho: b.ancho || (['kpis', 'tablero', 'agenda'].includes(b.vista) ? 12 : 6), alto: b.alto || (b.vista === 'kpis' ? 1 : 2) }))
    ac(`${id}: inicio completo`, { bloques, fijos: [] })
    for (const b of bloques) ac(`${id}: sin ${b.uid} (${b.vista})`, { bloques: bloques.filter((x) => x !== b), fijos: [] })
  }
  for (let i = 0; i < 500; i++) { // como la medida de acomodar.test.mjs
    const n = 2 + Math.floor(azar() * 6)
    ac(`al azar ${i + 1}`, { bloques: Array.from({ length: n }, (_, j) => B(`r${j}`, [3, 4, 6, 8, 12][Math.floor(azar() * 5)], 1 + Math.floor(azar() * 3))), fijos: [] })
  }
  for (let i = 0; i < 150; i++) { // con kpis, fijos y altos hasta 4
    const n = 2 + Math.floor(azar() * 7)
    const bs = Array.from({ length: n }, (_, j) => (azar() < 0.15 ? B(`k${j}`, elegir([6, 8, 12]), 1, 'kpis') : B(`r${j}`, elegir([3, 4, 6, 8, 12]), entre(1, 4), elegir(['grafico', 'tabla', 'agenda']))))
    ac(`al azar con fijos ${i + 1}`, { bloques: bs, fijos: bs.filter(() => azar() < 0.25).map((b) => b.uid) })
  }

  // ── compatibles ─────────────────────────────────────────────────────────────────────────────────
  const co = grabar('compatibles', (e) => compatibles(e.campos))
  for (const p of PLANTILLAS) { const porId = Object.fromEntries(p.secciones.map((s) => [s.id, s])); for (const s of p.secciones) co(`plantilla ${p.id}/${s.id}`, { campos: camposDe(s, porId) }) }
  for (const p of Object.values(PESTANAS).sort((a, b) => (a.id < b.id ? -1 : 1))) co(`pestaña ${p.id}`, { campos: p.seccion.campos || [] })
  const TIPOS = ['texto', 'numero', 'dinero', 'fecha', 'hora', 'estado', 'estado', 'lista', 'otro']
  for (let i = 0; i < 300; i++) {
    const campos = Array.from({ length: entre(0, 8) }, (_, j) => { const tipo = elegir(TIPOS); return { id: `c${j}`, nombre: `Campo ${j}`, tipo, ...(tipo === 'estado' || tipo === 'lista' ? { opciones: ['A', 'B', 'C', 'D', 'E'].slice(0, entre(0, 5)) } : {}) } })
    co(`al azar ${i + 1}`, { campos })
  }
  co('estado sin opciones', { campos: [{ id: 'e', tipo: 'estado' }] })

  // ── afirmaCambio ────────────────────────────────────────────────────────────────────────────────
  const af = grabar('afirmaCambio', (e) => afirmaCambio(e.texto))
  for (const t of ['Agregué a Juan Pérez con plan mensual.', 'Listo, puse el tema oscuro.', 'Creé la sección Cobros y la puse en el inicio. ¿Quieres algo más?',
    'Hice la gráfica más grande y la moví arriba.', 'Borré a Ana Gómez de las membresías.', 'Cambié el estado de Ana a Pausada; no pude poner la fecha.',
    'Lista la tabla de clases.', 'Ya renombré la pestaña a Cobranza', 'Tienes 2 miembros activos y no hay monto registrado para ellos. ¿Quieres que agregue el monto para Juan?',
    'Para registrar ese pago necesito que exista una sección de cobros. ¿Quieres que cree la sección "cobros"?',
    'No hice ningún cambio, solo consulté datos para responderte.', 'Todavía no lo agregué: dime la fecha exacta.',
    'No hay opción para exportar a Excel. ¿Quieres que te muestre la tabla de miembros?', 'Nadie vence este mes en membresías.',
    '¿Lo pongo arriba de todo?', 'Puedo agregar un bloque con la tabla, ¿lo agrego al inicio?', 'Este mes te pagaron un total de Q31,120.',
    'Si quieres, la creo para que puedas registrar pagos']) af(`prueba: «${t}»`, { texto: t })
  const VERBOS = ['agregué', 'quité', 'cambié', 'moví', 'achiqué', 'agrandé', 'puse', 'creé', 'hice', 'listo', 'lista', 'ajusté', 'reemplacé', 'renombré', 'borré']
  const NO_VERBOS = ['agregue', 'quite', 'cambie', 'movi', 'puso', 'cree', 'hizo', 'listos', 'listado', 'ajuste', 'borre', 'agregaré', 'pondré', 'agregar', 'cambiar']
  const cap = (w) => w.charAt(0).toUpperCase() + w.slice(1)
  for (const v of VERBOS) {
    for (const t of [`${cap(v)} lo que pediste.`, `Ya ${v} la sección.`, `${v.toUpperCase()} EL BLOQUE.`, `¿${cap(v)} bien la sección?`, `No ${v} nada.`, `Todavía no ${v} la tabla.`,
      `Aún no lo ${v}.`, `Nunca ${v} eso.`, `Sin que ${v} nada, todo sigue igual.`, `No pude, pero ${v} otra cosa.`, `Te cuento: ${v} la marca.`, `Primero miré los datos; ${v} el campo.`,
      `Lo ${v}`, `¿Quieres que lo ${v}?`, `Si quieres lo ${v}, ¿te parece?`, `${cap(v)}!`, `En resumen\n${v} todo`, `Re${v} la tabla.`, `${v}s la tabla.`, `No me pediste nada y no ${v}.`,
      `La tabla ya está ${v}.`, `Puedo decir que ${v} algo.`])
      af(`verbo «${v}»: «${t.replace(/\n/g, ' ')}»`, { texto: t })
  }
  for (const v of NO_VERBOS) for (const t of [`${cap(v)} la sección.`, `Puedo ${v} la tabla.`, `¿Quieres que ${v} la sección?`]) af(`no verbo «${v}»: «${t}»`, { texto: t })
  for (const t of ['', null, '¿?', '...', 'Listo.', 'Listo?', '¿Listo?', 'No, listo.', 'no listo', 'Está lista la tabla.', 'Lista de clases: Yoga, Box.', 'Agregué.', 'agregué', 'AGREGUÉ',
    'Hice; no hice.', 'No lo hice: lo hice.', 'Ni lo agregué ni lo borré.', 'Sin cambios: puse nada.', 'Nada cambió. ¿Agregué algo? No.']) af(`borde «${t}»`, { texto: t })

  // ── revertirDatos ───────────────────────────────────────────────────────────────────────────────
  const rd = grabar('revertirDatos', (e) => revertirDatos(e.antes, e.despues, e.actual))
  {
    // Escenario de registros.test.mjs: alta de Rosa, cambio de plan y borrado de Carlos (código puro, sin fechas).
    const p = plantillaPorId('membresias'), c = { muestra: { nivel: 'pocos', ejemplos: true, pais: 'gt' }, confirmado: true }, E = { bloques: [] }
    const e1 = ejecutar(p, E, 'agregar_registro', { seccion: 'miembros', valores: { nombre: 'Rosa Gómez', plan: 'Mensual' } }, c).estado
    const e2 = ejecutar(p, e1, 'editar_registro', { seccion: 'miembros', registro: 'Rosa Gómez', valores: { plan: 'Anual' } }, c).estado
    const e3 = ejecutar(p, e2, 'borrar_registro', { seccion: 'miembros', registro: 'Carlos Pérez' }, c).estado
    rd('prueba: deshacer el cambio de Rosa sin revivir a Carlos', { antes: e1.datos, despues: e2.datos, actual: e3.datos })
    rd('prueba: deshacer el borrado (el último)', { antes: e2.datos, despues: e3.datos, actual: e3.datos })
    rd('prueba: deshacer el alta tocada después → choca', { antes: E.datos || {}, despues: e1.datos, actual: e3.datos })
    const foto3 = revertirDatos(e1.datos, e2.datos, e2.datos).datos, r = revertirDatos(e1.datos, e2.datos, e3.datos).datos
    rd('prueba: cadena, ajustar la foto', { antes: e1.datos, despues: e2.datos, actual: e2.datos })
    rd('prueba: cadena, deshacer el siguiente', { antes: foto3, despues: r, actual: r })
  }
  // Deltas al azar: tres estados seguidos (pedidos 1 y 2) y las tres preguntas de deshacer.
  const SECS_ = ['miembros', 'pagos', 'clases'], CAMPOS_ = ['nombre', 'plan', 'estado', 'monto', 'vence']
  const valor = (k) => (k === 'monto' ? entre(1, 900) : k === 'vence' ? `2026-${String(entre(1, 12)).padStart(2, '0')}-${String(entre(1, 28)).padStart(2, '0')}` : k === 'estado' ? elegir(['Activa', 'Pausada', 'Cancelada']) : `${elegir(NOMBRES)} ${entre(1, 9)}`)
  // estrecho = pocas secciones, ids y campos: los dos pedidos tocan lo mismo seguido (para que haya choques).
  const paso = (d0, estrecho = false) => {
    const SECS = estrecho ? ['miembros'] : SECS_, CAMPOS = estrecho ? ['plan', 'estado'] : CAMPOS_, ids = estrecho ? 1 : 5
    const d = structuredClone(d0); d.nuevos ||= {}; d.cambios ||= {}; d.borrados ||= {}
    for (let k = entre(1, 3); k > 0; k--) {
      const f = elegir(SECS), op = elegir(estrecho ? ['nuevo', 'editar', 'editar', 'cambio', 'cambio', 'cambio', 'borrar'] : ['nuevo', 'nuevo', 'editar', 'cambio', 'cambio', 'borrar', 'borrarNuevo'])
      const propios = d.nuevos[f] || []
      if (op === 'nuevo') { d.n = (d.n || 0) + 1; (d.nuevos[f] ||= []).push({ id: `${f}-p${d.n}`, valores: Object.fromEntries(CAMPOS.filter(() => azar() < 0.6).map((c) => [c, valor(c)])) }) }
      if (op === 'editar' && propios.length) { const r = elegir(propios); const c = elegir(CAMPOS); r.valores[c] = valor(c) }
      if (op === 'cambio') { const id = `${f}-${entre(0, ids)}`; const c = elegir(CAMPOS); ((d.cambios[f] ||= {})[id] ||= {})[c] = valor(c) }
      if (op === 'borrar') { const id = `${f}-${entre(0, ids)}`; if (!(d.borrados[f] || []).includes(id)) (d.borrados[f] ||= []).push(id) }
      if (op === 'borrarNuevo' && propios.length) { const r = elegir(propios); d.nuevos[f] = propios.filter((x) => x !== r); if (!d.nuevos[f].length) delete d.nuevos[f] }
    }
    for (const g of ['nuevos', 'cambios', 'borrados']) if (!Object.keys(d[g]).length) delete d[g]
    return d
  }
  for (let i = 0; i < 200; i++) {
    const d0 = azar() < 0.2 ? {} : paso({}), d1 = paso(d0), d2 = azar() < 0.3 ? d1 : paso(d1)
    rd(`al azar ${i + 1}: deshacer el pedido 1 con el 2 encima`, { antes: d0, despues: d1, actual: d2 })
    rd(`al azar ${i + 1}: deshacer el pedido 2 (el último)`, { antes: d1, despues: d2, actual: d2 })
    rd(`al azar ${i + 1}: deshacer el pedido 1 solo`, { antes: d0, despues: d1, actual: d1 })
  }
  for (let i = 0; i < 100; i++) {
    const d0 = paso({}, true), d1 = paso(d0, true), d2 = paso(d1, true)
    rd(`al azar estrecho ${i + 1}: deshacer el pedido 1 con el 2 encima`, { antes: d0, despues: d1, actual: d2 })
    rd(`al azar estrecho ${i + 1}: deshacer el pedido 2 (el último)`, { antes: d1, despues: d2, actual: d2 })
  }
  rd('todo vacío', { antes: {}, despues: {}, actual: {} })

  mkdirSync(destino, { recursive: true })
  const resumen = []
  for (const [nombre, casos] of Object.entries(salida)) {
    writeFileSync(join(destino, `${nombre}.json`), `[\n${casos.map((c) => JSON.stringify(c)).join(',\n')}\n]\n`)
    resumen.push(`${nombre} ${casos.length}`)
  }
  console.log(`Fixtures en ${destino}: ${resumen.join(' · ')}`)
} finally {
  await vite.close()
}
