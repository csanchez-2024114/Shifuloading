/* Catálogo PURO de gráficos (D61): qué tipos existen, qué campos pide cada uno y qué opciones elige solo. Sin React, sin DOM,
 * sin imports y sin funciones dentro del catálogo: todo es dato, para que se pueda exportar tal cual a JSON
 * (servidor/exportar-catalogos.mjs → nucleo/src/assistant/packs/crm/catalogos/graficos.json) y reproducir en Python con las mismas reglas.
 * graficos.jsx le suma a cada tipo su dibujo (Componente) y su cálculo (calcular); el comportamiento es idéntico al de antes.
 *
 * CATALOGO[id] = { nombre, familia, requiere, opciones, html? }  (el ORDEN de las claves es el orden de compatibles())
 *  - familia: nombre largo de la familia (F).
 *  - requiere: { clase: n } o lista de alternativas [{ clase: n }, …] (basta con cumplir una). Ver CLASES y cumple().
 *  - opciones: { clave: expresión } = opciones por defecto. Ver valorDe() para las formas de una expresión.
 *  - html: true = se dibuja con HTML (no SVG).
 *
 * Reglas de compatibles(campos) (las mismas que hay que portar, verificadas con fixtures):
 *  1. Clases de campo (CLASES): estado (tipo 'estado'), estado3 (estado con 3 o más opciones), fecha, hora,
 *     medida (tipo 'numero' o 'dinero'), texto, categoria (estado o texto). Una clase desconocida no la cumple ningún campo.
 *  2. cumple(requiere, campos): requiere se vuelve lista (un objeto = una alternativa); hay que cumplir AL MENOS UNA
 *     alternativa, y una alternativa se cumple si para CADA clase hay al menos n campos de esa clase ({} se cumple siempre;
 *     una lista vacía, nunca).
 *  3. base(campos): campos que se eligen solos → estado (1.er estado), fecha y fecha2 (1.a y 2.a fecha), hora (1.a hora),
 *     valor y valor2 (1.a y 2.a medida, con TODOS los 'dinero' antes que los 'numero'), texto (1.er texto) y
 *     agrupar (estado si hay, si no texto). Lo que no existe queda sin definir (no se escribe en el resultado).
 *  4. opcionesPorDefecto(tipo, campos) = { ...base(campos), ...opciones del tipo evaluadas }: una opción del tipo que
 *     evalúa «sin definir» TAPA la de base (la clave desaparece del resultado); un null explícito se queda como null.
 *     Tipo desconocido → solo base(campos).
 *  5. compatibles(campos) = los tipos del catálogo, EN SU ORDEN, que cumplen requiere, cada uno como
 *     { id, nombre, familia, requiere, opciones: opcionesPorDefecto(id, campos) }. */

export const F = { cb: 'Columnas y barras', la: 'Líneas y áreas', ci: 'Circulares', fl: 'Flujo y jerarquía', di: 'Distribución y correlación', ti: 'Tiempo', re: 'Resúmenes' }

/** Clases de campo que puede pedir un gráfico en `requiere`. */
export const CLASES = {
  estado: (c) => c.tipo === 'estado',
  estado3: (c) => c.tipo === 'estado' && (c.opciones?.length || 0) >= 3, // estado con 3 o más opciones (radar)
  fecha: (c) => c.tipo === 'fecha',
  hora: (c) => c.tipo === 'hora',
  medida: (c) => c.tipo === 'numero' || c.tipo === 'dinero',
  texto: (c) => c.tipo === 'texto',
  categoria: (c) => c.tipo === 'estado' || c.tipo === 'texto',
}
/** `requiere` es un objeto { clase: cantidad } o una lista de alternativas (basta con cumplir una). */
export const cumple = (requiere, campos) => [].concat(requiere).some((alt) => Object.entries(alt).every(([cl, n]) => campos.filter(CLASES[cl] || (() => false)).length >= n))

/** Campos que se eligen solos: el primer estado, la primera (y segunda) fecha, la primera hora, la primera medida
 *  (dinero antes que número) y el primer texto. */
export function base(campos) {
  const de = (cl) => campos.filter(CLASES[cl])
  const medidas = [...campos.filter((c) => c.tipo === 'dinero'), ...campos.filter((c) => c.tipo === 'numero')]
  const estado = de('estado')[0]?.id
  const texto = de('texto')[0]?.id
  return { estado, fecha: de('fecha')[0]?.id, fecha2: de('fecha')[1]?.id, hora: de('hora')[0]?.id, valor: medidas[0]?.id, valor2: medidas[1]?.id, texto, agrupar: estado || texto }
}
export const sumaOConteo = (b) => (b.valor ? 'suma' : 'conteo')

/**
 * Valor de una expresión de `opciones` con b = base(campos). Formas (todo es JSON):
 *  - { primero: [k1, k2, …], si_no? } → el primer b[k] con valor (como `b.k1 || b.k2`); si ninguno, `si_no` evaluado
 *    (sin `si_no` = sin definir).
 *  - { si: k, entonces, si_no }       → `entonces` si b[k] tiene valor, si no `si_no` (ambos son expresiones).
 *  - { clase: c }                     → id del primer campo de la clase c (sin definir si no hay).
 *  - cualquier otro valor (texto, número, null, lista) es literal; las listas se copian.
 */
export function valorDe(x, b, campos) {
  if (Array.isArray(x)) return [...x]
  if (x === null || typeof x !== 'object') return x
  if ('primero' in x) { for (const k of x.primero) if (b[k]) return b[k]; return valorDe(x.si_no, b, campos) }
  if ('si' in x) return valorDe(b[x.si] ? x.entonces : x.si_no, b, campos)
  if ('clase' in x) return campos.find(CLASES[x.clase] || (() => false))?.id
  return x
}
/** Las opciones de un tipo ya evaluadas (sin mezclar con base). */
export const evaluarOpciones = (opciones, b, campos) => Object.fromEntries(Object.entries(opciones || {}).map(([k, x]) => [k, valorDe(x, b, campos)]))

// Expresiones que se repiten.
const de = (...ks) => ({ primero: ks })
const SUMA_O_CONTEO = { si: 'valor', entonces: 'suma', si_no: 'conteo' } // = sumaOConteo(b)
const POR_CAT = de('estado', 'texto') // b.estado || b.texto
const POR_TEXTO = de('texto', 'estado') // b.texto || b.estado

export const CATALOGO = {
  columnas: { nombre: 'Columnas', familia: F.cb, requiere: [{ fecha: 1 }, { categoria: 1 }], opciones: { agrupar: { si: 'fecha', entonces: 'mes', si_no: de('agrupar') }, funcion: SUMA_O_CONTEO } },
  'columnas-apiladas': { nombre: 'Columnas apiladas', familia: F.cb, requiere: { estado: 1, fecha: 1 }, opciones: { funcion: 'conteo', meses: 12 } },
  'columnas-100': { nombre: 'Columnas 100 %', familia: F.cb, requiere: { estado: 1, fecha: 1 }, opciones: { funcion: 'conteo', meses: 12 } },
  barras: { nombre: 'Barras horizontales', familia: F.cb, requiere: { categoria: 1 }, opciones: { funcion: SUMA_O_CONTEO } },
  'barras-apiladas': { nombre: 'Barras apiladas', familia: F.cb, requiere: [{ estado: 1, texto: 1 }, { estado: 1, fecha: 1 }], opciones: { filas: { primero: ['texto'], si_no: 'mes' }, funcion: 'conteo', meses: 6 } },
  'barra-100': { nombre: 'Barra 100 %', familia: F.cb, requiere: { categoria: 1 }, opciones: { funcion: 'conteo' } },
  linea: { nombre: 'Línea', familia: F.la, requiere: { fecha: 1 }, opciones: { funcion: SUMA_O_CONTEO } },
  'linea-area': { nombre: 'Línea con área', familia: F.la, requiere: { fecha: 1 }, opciones: { funcion: 'conteo' } },
  'area-apilada': { nombre: 'Área apilada', familia: F.la, requiere: { estado: 1, fecha: 1 }, opciones: { funcion: 'conteo', meses: 12 } },
  'linea-tendencia': { nombre: 'Línea con tendencia', familia: F.la, requiere: { fecha: 1 }, opciones: { funcion: SUMA_O_CONTEO, ventana: 3 } },
  dona: { nombre: 'Dona', familia: F.ci, requiere: { categoria: 1 }, opciones: { funcion: 'conteo' } },
  pastel: { nombre: 'Pastel', familia: F.ci, requiere: { categoria: 1 }, opciones: { funcion: SUMA_O_CONTEO } },
  anillos: { nombre: 'Anillos concéntricos', familia: F.ci, requiere: { categoria: 1 }, opciones: { funcion: 'conteo' } },
  medidor: { nombre: 'Medidor', familia: F.ci, requiere: { estado: 1 }, opciones: { objetivo: null } },
  meta: { nombre: 'Anillo de meta', familia: F.ci, requiere: { fecha: 1 }, opciones: { funcion: SUMA_O_CONTEO, meta: null } },
  embudo: { nombre: 'Embudo', familia: F.fl, requiere: { estado: 1 }, opciones: { modo: 'acumulado', excluir: [] } },
  arbol: { nombre: 'Mapa de árbol', familia: F.fl, requiere: { categoria: 1 }, opciones: { agrupar: POR_TEXTO, funcion: SUMA_O_CONTEO, top: 12 } },
  radar: { nombre: 'Radar', familia: F.fl, requiere: { estado3: 1 }, opciones: { agrupar: { clase: 'estado3' }, funcion: 'conteo' } },
  dispersion: { nombre: 'Dispersión', familia: F.di, requiere: [{ medida: 2 }, { medida: 1, fecha: 1 }], opciones: { x: de('valor2', 'fecha'), y: de('valor') } },
  burbujas: { nombre: 'Burbujas', familia: F.di, requiere: { categoria: 1, medida: 1 }, opciones: {} },
  histograma: { nombre: 'Histograma', familia: F.di, requiere: { medida: 1 }, opciones: { bins: null } },
  caja: { nombre: 'Caja y bigotes', familia: F.di, requiere: { medida: 1 }, opciones: { agrupar: { primero: ['estado'], si_no: null } } },
  calendario: { nombre: 'Mapa de calor por día', familia: F.ti, requiere: { fecha: 1 }, opciones: { semanas: 16, funcion: 'conteo' } },
  cascada: { nombre: 'Cascada', familia: F.ti, requiere: { fecha: 1 }, opciones: { funcion: SUMA_O_CONTEO, meses: 12 } },
  kpi: { nombre: 'KPI con tendencia', familia: F.ti, requiere: { fecha: 1 }, html: true, opciones: { funcion: SUMA_O_CONTEO } },
  posiciones: { nombre: 'Tabla de posiciones', familia: F.re, requiere: { texto: 1 }, html: true, opciones: { agrupar: de('texto'), funcion: SUMA_O_CONTEO, top: 5 } },
  estadisticas: { nombre: 'Estadísticas', familia: F.re, requiere: { medida: 1 }, html: true, opciones: {} },
  // Repertorio ampliado (graficos-nuevos.jsx dibuja estos 16).
  paleta: { nombre: 'Paleta (lollipop)', familia: F.cb, requiere: { categoria: 1 }, opciones: { agrupar: POR_TEXTO, funcion: SUMA_O_CONTEO, top: 8 } },
  combo: { nombre: 'Columnas + acumulado', familia: F.cb, requiere: { fecha: 1 }, opciones: { funcion: SUMA_O_CONTEO, meses: 12 } },
  pareto: { nombre: 'Pareto', familia: F.cb, requiere: { categoria: 1 }, opciones: { agrupar: POR_TEXTO, funcion: SUMA_O_CONTEO, top: 10 } },
  escalones: { nombre: 'Escalones', familia: F.la, requiere: { fecha: 1 }, opciones: { funcion: SUMA_O_CONTEO } },
  pendiente: { nombre: 'Pendiente (mes anterior → actual)', familia: F.la, requiere: { fecha: 1, categoria: 1 }, opciones: { agrupar: POR_CAT, funcion: SUMA_O_CONTEO } },
  multiples: { nombre: 'Múltiplos pequeños', familia: F.la, requiere: { fecha: 1, categoria: 1 }, opciones: { agrupar: POR_CAT, funcion: SUMA_O_CONTEO, meses: 12 } },
  waffle: { nombre: 'Waffle 10 × 10', familia: F.ci, requiere: { categoria: 1 }, opciones: { agrupar: de('agrupar'), funcion: 'conteo' } },
  rosa: { nombre: 'Rosa polar', familia: F.ci, requiere: { categoria: 1 }, opciones: { agrupar: POR_CAT, funcion: SUMA_O_CONTEO } },
  'media-dona': { nombre: 'Media dona', familia: F.ci, requiere: { categoria: 1 }, opciones: { agrupar: de('agrupar'), funcion: 'conteo' } },
  sol: { nombre: 'Sol (2 niveles)', familia: F.fl, requiere: { estado: 1, texto: 1 }, opciones: { estado: de('estado'), texto: de('texto'), funcion: SUMA_O_CONTEO } },
  puntos: { nombre: 'Puntos por categoría', familia: F.di, requiere: { categoria: 1, medida: 1 }, opciones: { agrupar: POR_CAT, valor: de('valor') } },
  'calor-hora': { nombre: 'Calor día × hora', familia: F.ti, requiere: { fecha: 1, hora: 1 }, opciones: { fecha: de('fecha'), hora: de('hora'), funcion: 'conteo' } },
  gantt: { nombre: 'Línea de tiempo', familia: F.ti, requiere: { fecha: 2 }, opciones: { fecha: de('fecha'), fecha2: de('fecha2'), texto: de('texto'), estado: de('estado') } },
  bala: { nombre: 'Bala contra meta', familia: F.re, requiere: { fecha: 1 }, opciones: { funcion: SUMA_O_CONTEO, meta: null } },
  progreso: { nombre: 'Barras de progreso', familia: F.re, requiere: { categoria: 1 }, opciones: { agrupar: de('agrupar'), funcion: SUMA_O_CONTEO } },
  'dos-kpis': { nombre: 'Dos KPIs', familia: F.re, requiere: { fecha: 1, medida: 1 }, html: true, opciones: { valor: de('valor') } },
}

/** Opciones que el gráfico elegiría solo para estos campos. */
export function opcionesPorDefecto(tipo, campos = []) {
  const b = base(campos)
  return { ...b, ...(CATALOGO[tipo] ? evaluarOpciones(CATALOGO[tipo].opciones, b, campos) : {}) }
}

/** Tipos que se pueden dibujar con los campos de una sección, con sus opciones por defecto. */
export function compatibles(campos = []) {
  return Object.entries(CATALOGO).filter(([, g]) => cumple(g.requiere, campos))
    .map(([id, g]) => ({ id, nombre: g.nombre, familia: g.familia, requiere: g.requiere, opciones: opcionesPorDefecto(id, campos) }))
}
