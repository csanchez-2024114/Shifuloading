/* Configuración regional del CRM: país → idioma, moneda y formatos. UNA sola fuente para todas las vistas y gráficos.
 * En el CRM real sale de la configuración de la persona (el cuestionario ya pregunta `ubicacion.pais`); el chat también
 * podrá cambiarla. Todo el formato pasa por Intl, así cada país sale como lo escribe su gente (verificado con Node):
 *   GT  Q 11,600.50 · 1,250   ·  MX $11,600.50 · 1,250  ·  CO $ 11.601 (sin decimales) · 1.250
 *   ES  11.600,50 € · 1250    ·  US $11,600.50          ·  Otro: US$ con es-419 */
export const PAISES = {
  gt: { nombre: 'Guatemala', locale: 'es-GT', moneda: 'GTQ' },
  mx: { nombre: 'México', locale: 'es-MX', moneda: 'MXN' },
  co: { nombre: 'Colombia', locale: 'es-CO', moneda: 'COP' },
  es: { nombre: 'España', locale: 'es-ES', moneda: 'EUR' },
  us: { nombre: 'Estados Unidos', locale: 'es-US', moneda: 'USD' },
  otro: { nombre: 'Otro país', locale: 'es-419', moneda: 'USD' },
}

function crear(pais) {
  const p = PAISES[pais] || PAISES.gt
  const dinero = new Intl.NumberFormat(p.locale, { style: 'currency', currency: p.moneda })
  const decimalesMoneda = dinero.resolvedOptions().maximumFractionDigits
  const dineroSinCentavos = new Intl.NumberFormat(p.locale, { style: 'currency', currency: p.moneda, maximumFractionDigits: 0, minimumFractionDigits: 0 })
  const numero = new Intl.NumberFormat(p.locale, { maximumFractionDigits: 2 })
  // Cortos en español para todos ("241.8 mil", "1.2 M"): Intl compacto da "K"/"k" según el país y confunde.
  const uno = new Intl.NumberFormat(p.locale, { maximumFractionDigits: 1 })
  const escala = (n) => { const a = Math.abs(n); return a >= 1e6 ? `${uno.format(n / 1e6)} M` : a >= 1e3 ? `${uno.format(n / 1e3)} mil` : uno.format(n) }
  // Dónde va el símbolo y con qué espacio, tal como lo pone ese país ("Q 1", "$1", "1 €").
  const partes = dineroSinCentavos.formatToParts(1)
  const iNum = partes.findIndex((x) => x.type === 'integer')
  const antes = partes.slice(0, iNum).map((x) => x.value).join(''), despues = partes.slice(iNum + 1).map((x) => x.value).join('')
  const pct = new Intl.NumberFormat(p.locale, { style: 'percent', maximumFractionDigits: 1 })
  const fecha = new Intl.DateTimeFormat(p.locale, { day: 'numeric', month: 'short' })
  const fechaAnio = new Intl.DateTimeFormat(p.locale, { day: 'numeric', month: 'short', year: 'numeric' })
  const hora = new Intl.DateTimeFormat(p.locale, { hour: 'numeric', minute: '2-digit' })
  return {
    pais, ...p,
    /** Monto con su moneda. Montos enteros sin ",00" (en tablas y tarjetas se lee mejor "Q 1,250" que "Q 1,250.00"). */
    dinero: (n) => (Number.isInteger(Math.round(n * 100) / 100) && decimalesMoneda > 0 ? dineroSinCentavos : dinero).format(n),
    dineroCorto: (n) => `${n < 0 ? '−' : ''}${antes}${escala(Math.abs(n))}${despues}`,
    numero: (n) => numero.format(n),
    numeroCorto: (n) => escala(n),
    pct: (f) => pct.format(f),
    fecha: (iso) => { const d = new Date(`${iso}T00:00:00`); return (d.getFullYear() === new Date().getFullYear() ? fecha : fechaAnio).format(d).replace('.', '') },
    // Un valor que no es hora (dato mal escrito) se muestra tal cual en vez de tumbar la pantalla.
    hora: (hhmm) => { const [h, m] = String(hhmm).split(':').map(Number); if (!Number.isFinite(h) || h < 0 || h > 23) return String(hhmm ?? ''); const d = new Date(); d.setHours(h, m || 0, 0, 0); return hora.format(d) },
  }
}

let actual = crear('gt')
/** El formato de la región activa. Lo fija PlantillaCRM con la configuración de la persona antes de dibujar. */
export const region = () => actual
export function fijarRegion(pais) { if (actual.pais !== pais) actual = crear(pais) }
