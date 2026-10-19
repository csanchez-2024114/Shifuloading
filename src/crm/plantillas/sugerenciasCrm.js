/* Sugerencias del laboratorio adaptadas al CRM de la API (carga aparte: importa gráficos). */
import { sugerenciasPara } from '@lab/plantillas/sugerencias.js'
import { desdeCrm } from './desdeCrm.js'

/** Devuelve [[etiqueta, texto], …] (como mucho `cuantas`) o null si no se pudo armar el contexto.
 * Solo sobre lo que la persona tiene a la vista (lista 34 y PLAN_MAESTRO §2): en el inicio, sus piezas; en una pestaña con
 * lienzo propio, las de esa pestaña; en las demás, ninguna pieza (las ideas son de esa sección). */
export function ideasDe(crm, vista, turno, titulos, cuantas = 3) {
  try {
    const { plantilla, datos, bloques, paginas, marca, logoId } = desdeCrm(crm, { titulos })
    const visibles = vista === 'inicio' ? bloques : (paginas[vista] || [])
    return sugerenciasPara({ plantilla, bloques, visibles, marca: { ...marca, ...(logoId ? { logo: logoId } : {}) }, toma: crm.toma, vista, datos, turno, cuantas })
  } catch {
    return null
  }
}
