/* Regla de asignación (D23): con las respuestas del cuestionario se elige la plantilla de base. La decide el CÓDIGO
 * (rápida, predecible y explicable); la IA solo la cambia si la persona pide otra cosa.
 * Puntaje por plantilla según sus metadatos `asignacion`: rubro +3, ciclo +2, cada objetivo +1, y palabras de "qué vendes"
 * que aparecen en sus ejemplos de negocio +2. Devuelve las 3 mejores con el porqué en palabras. */
import { PLANTILLAS } from './semillas'

const norm = (t) => String(t || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '')
const palabras = (t) => norm(t).split(/[^a-zñ]+/).filter((w) => w.length > 3)

export function asignar({ rubro, ciclo, objetivos = [], queVendes = '' } = {}) {
  const pv = new Set(palabras(queVendes))
  const res = PLANTILLAS.filter((p) => p.asignacion).map((p) => {
    const a = p.asignacion, por = []
    let pts = 0
    if (a.rubros.includes(rubro)) { pts += 3; por.push('tu rubro') }
    if (a.ciclos.includes(ciclo)) { pts += 2; por.push('tu forma de vender') }
    const obj = objetivos.filter((o) => a.objetivos?.includes(o)); if (obj.length) { pts += obj.length; por.push(`${obj.length} de tus objetivos`) }
    const coincide = [...pv].filter((w) => palabras([p.nombre, p.para, ...a.negocios].join(' ')).includes(w))
    if (coincide.length) { pts += 2 * Math.min(2, coincide.length); por.push(`lo que vendes («${coincide.slice(0, 2).join('», «')}»)`) }
    return { id: p.id, nombre: p.nombre, puntos: pts, porque: por }
  }).sort((x, y) => y.puntos - x.puntos)
  const top = res.slice(0, 3)
  // D6: si no hay una clara ganadora (empate o puntaje bajo), se muestran opciones en vez de adivinar.
  const ambiguo = !top.length || top[0].puntos < 3 || (top[1] && top[1].puntos === top[0].puntos)
  return { recomendada: top[0], opciones: top, ambiguo }
}
