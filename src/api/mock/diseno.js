/* El CRM simulado con los campos del esquema 2 (D61, contratos §1 y §4), solo con VITE_CRM_DISENO=1 y sin servidor:
 * secciones, piezas de inicio, lienzo de una pestaña y marca sacados de una plantilla del laboratorio (Membresías) con sus
 * datos de ejemplo (marcados `ejemplo`), para ver y desarrollar la pantalla sin el backend. Se carga aparte (import dinámico). */
import { plantillaPorId } from '@lab/plantillas/semillas.js'
import { datosEjemplo } from '@lab/plantillas/datosEjemplo.js'

const PLANTILLA = 'membresias'
const id = (x) => `l_${x}` // las secciones de una plantilla llevan el prefijo l_ (§1)

/** Agrega al CRM simulado lo del esquema 2. No toca lo de Carlos (contactos, tareas, sus listas): solo suma. */
export function conDiseno(s) {
  const p = plantillaPorId(PLANTILLA)
  const d = datosEjemplo(p, 'pocos')
  const propias = p.secciones.filter((x) => x.campos?.length && !x.fuente)
  const listas = propias.map((x) => ({
    id: id(x.id), nombre: x.titulo, tipo: null,
    campos: x.campos.map((c) => ({ id: c.id, nombre: c.nombre, tipo: c.tipo, ...(c.opciones ? { opciones: c.opciones } : {}) })),
    registros: (d.registros[x.id] || []).map((r) => ({ id: id(r.id), valores: r.valores, ejemplo: true })),
    importaciones: [], vista: x.vista, opciones: x.opciones || {}, icono: x.icono, grupo: x.grupo,
    ...(x.ficha ? { ficha: x.ficha } : {}), ...(x.tarjeta ? { tarjeta: x.tarjeta } : {}), origen: p.id,
  }))
  // La sección «Vencimientos» de la plantilla solo mira los registros de Miembros (fuente): en el CRM es una pieza del
  // lienzo propio de Miembros, junto a una gráfica y su tabla de siempre (§1 paginas).
  const venc = p.secciones.find((x) => x.fuente === 'miembros')
  const paginas = { [id('miembros')]: [
    ...(venc ? [{ uid: 'p_m0', vista: 'vencimientos', seccion: id('miembros'), opciones: venc.opciones, ancho: 6, alto: 2 }] : []),
    { uid: 'p_m1', vista: 'grafico', seccion: id('miembros'), opciones: { tipo: 'dona' }, ancho: 6, alto: 2 },
    { uid: 'p_m2', vista: 'tabla', seccion: id('miembros'), opciones: {}, ancho: 12, alto: 3 },
  ] }
  const inicio = [
    ...p.inicio.map((w, i) => ({ uid: `b${i}`, ...w, seccion: id(w.seccion) })),
    // Una pieza de una sección virtual (§2): las tareas de Carlos en tablero.
    { uid: 'b_tareas', vista: 'tablero', seccion: 'desarrollo', opciones: { por: 'estado', titulo: 'tarea' }, ancho: 12, alto: 2 },
  ]
  const ya = new Set((s.listas || []).map((l) => l.id))
  return {
    ...s, esquema: 2,
    plantilla: { id: p.id, origen: 'asignar', porque: ['Servidor simulado: plantilla del laboratorio'] },
    inicio, paginas, marca: { primario: '#3fb8ff' }, toma: null, puntos: [],
    listas: [...(s.listas || []), ...listas.filter((l) => !ya.has(l.id))],
  }
}
