/* Sugerencias del laboratorio adaptadas al CRM de la API (carga aparte: importa gráficos). */
import { sugerenciasPara } from '@lab/plantillas/sugerencias.js'
import { desdeCrm } from './desdeCrm.js'

/** Devuelve [[etiqueta, texto], …] o null si no se pudo armar el contexto. */
export function ideasDe(crm, vista, turno, titulos) {
  try {
    const { plantilla, datos, bloques, marca } = desdeCrm(crm, { titulos })
    return sugerenciasPara({ plantilla, bloques, marca, toma: crm.toma, vista, datos, turno })
  } catch {
    return null
  }
}
