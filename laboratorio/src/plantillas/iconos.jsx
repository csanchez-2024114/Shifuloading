/* Íconos de las pestañas desde el catálogo (D32, errores 4 y 11 del recorrido): el CÓDIGO elige el ícono por el título
 * de la sección (se calcula, no lo adivina el modelo). «Membresías» → membresía, «Agenda y citas» → agenda, «Inventario»
 * → inventario. Si ningún concepto coincide, queda el ícono genérico de su vista. Por ahora solo la familia base
 * (Lucide): cambiar de familia o estilo es branding y queda para después (D44). Solo se incluyen los íconos del catálogo. */
import { useEffect, useState } from 'react'

// El mapa concepto → ícono se carga en un trozo aparte (no pesa en la carga inicial); mientras, se ve el genérico.
let ICONOS = null; let promesa = null
export const cargarIconos = () => (ICONOS ? Promise.resolve(ICONOS) : (promesa ||= import('./catalogos/iconos-lu').then((m) => (ICONOS = m.LU))))

const sinAcentos = (t) => String(t || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '')
// Sinónimos (datos, no reglas): palabras de títulos que nombran un concepto con otra palabra.
const SINONIMOS = { clienta: 'cliente', socio: 'miembro', socia: 'miembro', alumna: 'alumno', paciente: 'paciente', huespedes: 'huesped', ordenes: 'orden', nomina: 'nomina', inscripcion: 'matricula', mascota: 'mascota', producto: 'producto' }
// Palabras que no dicen de qué trata la sección.
const VACIAS = new Set(['de', 'del', 'la', 'las', 'el', 'los', 'y', 'e', 'o', 'mis', 'mi', 'por', 'para', 'con', 'en', 'activos', 'activas', 'nuevos', 'nuevas'])
const singular = (w) => (w.endsWith('es') && w.length > 4 ? [w.slice(0, -2), w.slice(0, -1)] : w.endsWith('s') && w.length > 3 ? [w.slice(0, -1)] : [])

/** Concepto del catálogo que mejor nombra un título (o null). Gana la palabra que aparece primero en el título. */
export function conceptoPara(titulo) {
  if (!ICONOS) return null
  const CONCEPTOS = Object.keys(ICONOS)
  const palabras = sinAcentos(titulo).split(/[^a-z0-9ñ]+/).filter((w) => w && !VACIAS.has(w))
  const frase = palabras.join('-')
  if (ICONOS[frase]) return frase
  for (const w of palabras) {
    for (const c of [w, ...singular(w)]) { if (ICONOS[c]) return c; if (SINONIMOS[c] && ICONOS[SINONIMOS[c]]) return SINONIMOS[c] }
    // Prefijo largo: «facturación» → factura, «cotizaciones» → cotizacion.
    const pre = w.length >= 6 && CONCEPTOS.find((k) => !k.includes('-') && k.length >= 5 && (w.startsWith(k) || k.startsWith(w)))
    if (pre) return pre
  }
  return null
}

/** Ícono de una sección: el del catálogo según su título, o `Generico` si no hay coincidencia. */
export function IconoSeccion({ titulo, Generico, ...props }) {
  const [, setListo] = useState(!!ICONOS)
  useEffect(() => { if (!ICONOS) cargarIconos().then(() => setListo(true)) }, [])
  const c = conceptoPara(titulo)
  const I = (c && ICONOS[c]) || Generico
  return <I {...props} />
}
