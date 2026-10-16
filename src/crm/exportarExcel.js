/* Descarga el CRM como un libro de Excel: una hoja por cada pestaña que la persona tiene ACTIVA en su menú (con el nombre que ella ve).
 * Lo que está oculto (por ejemplo Clientes o Pendientes, que nacen ocultos) no se incluye.
 * Se arma aquí, en el navegador, con lo que la persona tiene en pantalla: siempre es lo más reciente, sin pedirle nada al servidor. */

const COLUMNAS_TAREAS = [['porHacer', 'Por hacer'], ['enCurso', 'En curso'], ['hecho', 'Hecho']]
const ENCABEZADO = { fontWeight: 'bold', backgroundColor: '#1F6F5B', textColor: '#FFFFFF' }

/** Excel no admite en el nombre de una hoja \ / ? * [ ] : ni más de 31 letras, y no puede haber dos iguales. */
function nombreDeHoja(nombre, usados) {
  const base = (String(nombre || 'Hoja').replace(/[\\/?*[\]:]/g, ' ').replace(/\s+/g, ' ').trim() || 'Hoja').slice(0, 31)
  let n = base
  for (let i = 2; usados.has(n.toLowerCase()); i++) n = `${base.slice(0, 31 - String(i).length - 1)} ${i}`
  usados.add(n.toLowerCase())
  return n
}

const fechaDe = (iso) => {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(iso || ''))
  return m ? new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]))) : null
}

/** Una celda con el formato que le toca a su tipo: números como números y fechas como fechas (no como texto). */
const ESDINERO = /precio|monto|total|costo|valor|pago|deuda|saldo|ganancia|sueldo|salario|importe|\bq\b|\$/i
function celda(tipo, valor, nombre) {
  if (valor === undefined || valor === null || valor === '') return null
  // Números como números (los precios y montos con dos decimales) para que en Excel se puedan sumar y ordenar.
  if (tipo === 'numero' && Number.isFinite(Number(valor))) return { value: Number(valor), type: Number, format: ESDINERO.test(nombre || '') ? '#,##0.00' : '#,##0.##' }
  if (tipo === 'fecha') { const d = fechaDe(valor); if (d) return { value: d, type: Date, format: 'dd/mm/yyyy' } }
  return { value: String(valor), type: String }
}

const encabezados = (titulos) => titulos.map((t) => ({ value: t, ...ENCABEZADO }))
const anchos = (titulos, filas) => titulos.map((t, i) => ({ width: Math.min(48, Math.max(12, String(t).length + 4, ...filas.slice(0, 80).map((f) => String(f[i]?.value ?? '').length + 2))) }))

/** Arma las hojas del libro a partir del CRM que muestra la pantalla. `titulos` = los nombres que la persona ve en su menú ({ contactos, desarrollo }). Devuelve [] si no hay ninguna pestaña que descargar. */
export function hojasDelCrm(crm, titulos = {}) {
  const usados = new Set()
  const ocultas = new Set(crm.ocultas || [])
  const hojas = []
  const agregar = (nombre, titulos, filas) => hojas.push({ sheet: nombreDeHoja(nombre, usados), data: [encabezados(titulos), ...filas], columns: anchos(titulos, filas), stickyRowsCount: 1 })

  if (!ocultas.has('contactos')) {
    const extra = crm.camposContacto || []
    agregar(titulos.contactos || 'Clientes', ['Nombre', 'Teléfono o correo', 'Canal', 'Etapa', 'Responsable', ...extra.map((c) => c.nombre), 'Días sin contacto'],
      crm.contactos.map((c) => [celda('texto', c.n), celda('texto', c.det), celda('texto', c.canal), celda('texto', c.etapa), celda('texto', c.dueno),
        ...extra.map((e) => celda(e.tipo, c.extra?.[e.id], e.nombre)), celda('numero', c.dias, 'Días')]))
  }
  for (const l of crm.listas || []) {
    agregar(l.nombre, l.campos.map((c) => c.nombre), l.registros.map((r) => l.campos.map((c) => celda(c.tipo, r.valores[c.id], c.nombre))))
  }
  const tareas = COLUMNAS_TAREAS.flatMap(([k, estado]) => (crm.tareas?.[k] || []).map((x) => [celda('texto', x.t), celda('texto', estado), celda('fecha', x.vence), celda('texto', x.hora), celda('texto', x.contacto)]))
  if (!ocultas.has('desarrollo')) agregar(titulos.desarrollo || 'Pendientes', ['Tarea', 'Estado', 'Fecha', 'Hora', 'Cliente'], tareas)
  return hojas
}

const hoy = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}` }

/** Genera el .xlsx y lo manda a descargar. Devuelve false si no había nada que descargar. */
export async function descargarExcel(crm, negocio, titulos) {
  const hojas = hojasDelCrm(crm, titulos)
  if (!hojas.length) return false
  const { default: escribir } = await import('write-excel-file/browser')
  const nombre = `${String(negocio || 'Mi CRM').replace(/[\\/:*?"<>|]/g, ' ').replace(/\s+/g, ' ').trim()} - ${hoy()}.xlsx`
  await escribir(hojas).toFile(nombre)
  return true
}
