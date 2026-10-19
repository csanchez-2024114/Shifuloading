/* El buscador de arriba (lista 36): busca en TODAS las secciones que la persona tiene en el menú, no solo en contactos.
 * Función pura: recibe el CRM de la API y las secciones visibles ([{ id, t }] del menú) y devuelve los resultados por sección.
 * Lo que está oculto no se busca (no está a la vista); las vistas sin registros (Inicio, Ajustes…) tampoco. */
import { COLUMNAS } from './secciones.js'

const norm = (s) => String(s ?? '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').trim()
const lleno = (v) => v !== undefined && v !== null && String(v).trim() !== ''
const verValor = (v) => (Array.isArray(v) ? v.join(', ') : String(v))

export const MIN_LETRAS = 2

/** Cada registro de una sección como { id, titulo, detalle, textos: [[nombreCampo, valor]] }. */
function registrosDe(crm, id) {
  if (id === 'contactos') {
    const nombres = Object.fromEntries((crm.camposContacto || []).map((c) => [c.id, c.nombre]))
    return (crm.contactos || []).map((c) => ({
      id: c.id, titulo: c.n, detalle: c.det || c.etapa || '',
      textos: [['Nombre', c.n], ['Teléfono o correo', c.det], ['Canal', c.canal], ['Etapa', c.etapa], ['Responsable', c.dueno],
        ...Object.entries(c.extra || {}).map(([k, v]) => [nombres[k] || k, v])],
    }))
  }
  if (id === 'desarrollo') {
    return COLUMNAS.flatMap(([col, estado]) => (crm.tareas?.[col] || []).map((t) => ({
      id: t.id, titulo: t.t, detalle: [estado, t.vence, t.hora].filter(Boolean).join(' · '),
      textos: [['Tarea', t.t], ['Contacto', t.contacto], ['Vence', t.vence]],
    })))
  }
  const lista = (crm.listas || []).find((l) => l.id === id)
  if (!lista) return []
  const campos = lista.campos || []
  return (lista.registros || []).map((r) => {
    const valores = r.valores || {}
    const titulo = campos.map((c) => valores[c.id]).find(lleno)
    return { id: r.id, titulo: lleno(titulo) ? verValor(titulo) : 'Registro sin nombre', detalle: '', textos: campos.map((c) => [c.nombre, valores[c.id]]) }
  })
}

/**
 * Busca `texto` en las secciones visibles. Devuelve [{ id, titulo, total, resultados: [{ id, titulo, detalle }] }], en el orden
 * del menú y solo las secciones con algo; cada una con como mucho `porSeccion` resultados (`total` dice cuántos hubo).
 * Con menos de MIN_LETRAS letras no busca (devuelve []).
 */
export function buscarEnCrm(crm, secciones, texto, porSeccion = 5) {
  const q = norm(texto)
  if (q.length < MIN_LETRAS || !crm) return []
  const out = []
  for (const s of secciones || []) {
    const hallados = []
    for (const r of registrosDe(crm, s.id)) {
      const campo = r.textos.find(([, v]) => lleno(v) && norm(verValor(v)).includes(q))
      if (!campo) continue
      // Si lo que coincidió no es el nombre del registro, se dice dónde: «Marca: HP».
      const enTitulo = norm(r.titulo).includes(q)
      hallados.push({ id: r.id, titulo: r.titulo, detalle: enTitulo ? r.detalle : `${campo[0]}: ${verValor(campo[1])}` })
    }
    if (hallados.length) out.push({ id: s.id, titulo: s.t, total: hallados.length, resultados: hallados.slice(0, porSeccion) })
  }
  return out
}
