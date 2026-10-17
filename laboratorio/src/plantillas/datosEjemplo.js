/* Datos de ejemplo SOLO para el laboratorio. Deterministas (misma semilla, mismos datos) y con fechas relativas a hoy,
 * así la agenda y los vencimientos siempre tienen algo que mostrar. Nunca se usan en el CRM real. */

export const NIVELES = { vacio: 0, pocos: 8, muchos: 220 }

function azar(semilla) {
  let a = semilla >>> 0
  return () => { a = (a + 0x6d2b79f5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296 }
}
const hash = (s) => [...s].reduce((h, c) => Math.imul(h ^ c.charCodeAt(0), 16777619), 2166136261)

const NOMBRES = ['Ana López', 'Carlos Pérez', 'María José Castillo', 'Luis Hernández', 'Sofía Ramírez', 'Diego Morales', 'Valentina Cruz',
  'Jorge Méndez', 'Camila Ortiz', 'Andrés Rivera', 'Lucía Fernández', 'Pablo Gómez', 'Daniela Reyes', 'Fernando Ruiz', 'Gabriela Torres',
  'Ricardo Vásquez Aldana de la Peña', 'Isabel Juárez', 'Héctor Paz', 'Natalia Soto', 'Emilio Barrios']
// Con 220 registros y 20 nombres, cada nombre salía ~11 veces: «cambia el plan de Ana López» nunca sabría cuál. El campo
// «nombre» (quien es el registro) lleva un nombre ÚNICO: los 20 de arriba y después combinaciones de nombre y dos apellidos.
const PILA = ['Ana', 'Carlos', 'María', 'Luis', 'Sofía', 'Diego', 'Valentina', 'Jorge', 'Camila', 'Andrés', 'Lucía', 'Pablo', 'Daniela', 'Fernando', 'Gabriela', 'Ricardo', 'Isabel', 'Héctor', 'Natalia', 'Emilio']
const APELLIDOS = ['García', 'Rodríguez', 'Martínez', 'Sánchez', 'Ramírez', 'Flores', 'Castillo', 'Morales', 'Ortiz', 'Silva', 'Rojas', 'Vargas', 'Mejía', 'Aguilar', 'Herrera', 'Medina', 'Castro', 'Guzmán', 'Navarro', 'Ríos']
const nombreUnico = (i) => { if (i < NOMBRES.length) return NOMBRES[i]; const k = i - NOMBRES.length, g = Math.floor(k / 20); return `${PILA[k % 20]} ${APELLIDOS[g % 20]} ${APELLIDOS[(k + 7 * g + 3) % 20]}` }
const EMPRESAS = ['Café Luna', 'Dental Sonrisa', 'Grupo Andino', 'Estudio Norte', 'Panadería La Espiga', 'TecnoSur', 'Inmobiliaria Roble', 'Moda Ixchel']
const COSAS = {
  producto: ['Pastel de chocolate', 'Pan de muerto (docena)', 'Cheesecake de fresa', 'Café de altura 1 lb', 'Galletas de mantequilla', 'Pastel de bodas 3 pisos'],
  servicio: ['Masaje relajante', 'Facial hidratante', 'Limpieza dental', 'Paquete parejas', 'Consulta de valoración', 'Ortodoncia (control)'],
  paquete: ['10 masajes', 'Facial mensual', 'Tratamiento ortodoncia', 'Plan detox 4 semanas'],
  plan: ['Mensual', 'Trimestral', 'Anual', 'Estudiante'],
  proyecto: ['Rediseño de marca', 'Campaña Día de la Madre', 'Sitio web corporativo', 'Manejo de redes (octubre)', 'App de pedidos'],
  campana: ['Anuncios Instagram', 'Promo 2x1', 'Lanzamiento producto', 'Black Friday', 'Remarketing'],
  tarea: ['Llamar a proveedor', 'Enviar propuesta', 'Revisar inventario', 'Publicar en redes', 'Cobrar factura pendiente'],
  nota: ['Pidió factura', 'Prefiere WhatsApp', 'Volver a llamar el lunes', 'Interesada en el paquete anual'],
}
const RANGO_FECHA = { entrega: [-3, 10], fecha: [-2, 9], vence: [-12, 45], cuando: [-5, 15], fin: [-3, 30], alta: [-330, 0] }

const hoy = () => { const d = new Date(); d.setHours(0, 0, 0, 0); return d }
export const isoDia = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
const masDias = (n) => { const d = hoy(); d.setDate(d.getDate() + n); return isoDia(d) }

function valor(campo, r, i = 0, n = NOMBRES.length) {
  const ent = (a, b) => Math.floor(a + r() * (b - a + 1))
  const de = (lista) => lista[Math.floor(r() * lista.length)]
  switch (campo.tipo) {
    case 'estado': return de(campo.opciones)
    case 'fecha': { const [a, b] = campo.rango || RANGO_FECHA[campo.id] || [-60, 30]; return masDias(ent(a, b)) }
    case 'hora': return `${String(ent(9, 18)).padStart(2, '0')}:${r() < 0.5 ? '00' : '30'}`
    case 'numero': return campo.rango ? ent(...campo.rango) : ent(1, 60)
    case 'dinero': return campo.rango ? Math.round(ent(...campo.rango) / 10) * 10 : ent(15, 900) * 10
    default:
      if (campo.ejemplos?.length) return de(campo.ejemplos)
      if (COSAS[campo.id]) return de(COSAS[campo.id])
      if (campo.id === 'telefono') return `+502 ${ent(3000, 5999)} ${ent(1000, 9999)}`
      if (campo.id === 'empresa') return de(EMPRESAS)
      // r() se consume igual que antes: así el resto de los valores de ejemplo no cambia.
      if (campo.id === 'nombre') { r(); return nombreUnico(i) }
      // Quien aparece en otra sección (el miembro de un pago, el cliente de una cita) es alguien que existe.
      return NOMBRES[Math.floor(r() * Math.min(Math.max(n, 1), NOMBRES.length))]
  }
}

/** Datos para una plantilla y un nivel: { registros: {seccionId: [{id, valores}]}, eventos, equipo, automatizaciones }. */
export function datosEjemplo(plantilla, nivel = 'pocos') {
  const n = NIVELES[nivel] ?? NIVELES.pocos
  const r = azar(hash(`${plantilla.id}:${nivel}`))
  const registros = {}
  for (const s of plantilla.secciones) {
    if (!s.campos?.length || s.fuente) continue
    registros[s.id] = Array.from({ length: n }, (_, i) => {
      const valores = Object.fromEntries(s.campos.map((c) => [c.id, valor(c, r, i, n)]))
      // Coherencia: una campaña termina DESPUÉS de empezar (antes salían 44 con fin < inicio y la línea de tiempo no los dibujaba).
      // Solo si los dos son FECHAS (en Turnos «inicio» y «fin» son horas: tratarlas como fecha daba «NaN-NaN-NaN»).
      const esFecha = (id) => s.campos.some((c) => c.id === id && c.tipo === 'fecha')
      if (esFecha('inicio') && esFecha('fin') && valores.inicio && valores.fin && valores.fin < valores.inicio) {
        const d = new Date(`${valores.inicio}T00:00:00`); d.setDate(d.getDate() + 3 + Math.floor(r() * 28)); valores.fin = isoDia(d)
      }
      // Marcado como ejemplo: «Borrar ejemplos» quita SOLO estos y nunca un registro real (riesgo visto en Airtable).
      return { id: `${s.id}-${i}`, ejemplo: true, valores }
    })
  }
  const eventos = n === 0 ? [{ id: 'e0', e: '🤖', t: 'Shifu creó tu CRM', h: 'ahora' }]
    : Array.from({ length: Math.min(n, 12) }, (_, i) => ({ id: `e${i}`, e: ['➕', '🔁', '📅', '💬', '✅'][i % 5], t: `${['Agregaste a', 'Actualizaste a', 'Agendaste a', 'Escribiste a', 'Cerraste con'][i % 5]} ${NOMBRES[i % NOMBRES.length]}`, h: i === 0 ? 'hace 5 min' : `hace ${i} h` }))
  const equipo = n === 0 ? ['Tú'] : ['Tú', 'Andrea', 'Kevin', 'Rosa'].slice(0, n > 50 ? 4 : 2)
  const automatizaciones = [
    { id: 'recordatorios', pilar: 'Estructura', t: 'Recordatorios de seguimiento', d: 'Te avisa cuando alguien lleva 3 días sin respuesta.', on: true },
    { id: 'bienvenida', pilar: 'Estructura', t: 'Bienvenida por WhatsApp', d: 'Responde al instante el primer mensaje.', on: n > 0 },
    { id: 'resumen', pilar: 'Medición y equipo', t: 'Resumen semanal', d: 'Cada lunes, cuánto vendiste y qué falta.', on: false },
  ]
  return { registros, eventos, equipo, automatizaciones }
}

/** Registros que ve una sección (las secciones con `fuente` muestran los de otra). */
export const registrosDe = (s, datos) => datos.registros[s.fuente || s.id] || []

/** Quita SOLO los registros marcados como ejemplo; los reales quedan intactos. */
// También el historial y el equipo de ejemplo: tras borrar los ejemplos seguían «Agregaste a Ana López, hace 5 min» y
// compañeros que no existen (prueba de cliente). Lo único verdadero es que Shifu armó el CRM.
export const sinEjemplos = (datos) => (datos ? { ...datos, registros: Object.fromEntries(Object.entries(datos.registros).map(([k, rs]) => [k, rs.filter((r) => !r.ejemplo)])),
  eventos: [{ id: 'e0', e: '🤖', t: 'Shifu creó tu CRM', h: 'hoy' }], equipo: ['Tú'] } : datos)

/** Datos de ejemplo para lo que Shifu agregó: cada sección nueva y cada campo nuevo tiene su propia semilla, así los
 * datos que ya estaban no cambian al agregar algo (no "saltan" los números). Sin ejemplos (nivel vacío) no se inventa nada. */
export function extenderDatos(datos, base, est, nivel) {
  if (!datos || (!est.secciones?.length && !Object.keys(est.campos || {}).length && !Object.keys(est.mapeoEstado || {}).length)) return datos
  const registros = { ...datos.registros }
  for (const sec of est.secciones || []) registros[sec.id] = datosEjemplo({ id: `${base.id}:${sec.id}`, secciones: [sec] }, nivel).registros[sec.id] || []
  for (const [sid, extras] of Object.entries(est.campos || {})) {
    const extra = datosEjemplo({ id: `${base.id}:${sid}:campos`, secciones: [{ id: sid, campos: extras }] }, nivel).registros[sid] || []
    registros[sid] = (registros[sid] || []).map((r, i) => ({ ...r, valores: { ...r.valores, ...(extra[i]?.valores || {}) } }))
  }
  // Opciones de estado renombradas o quitadas: cada registro pasa a su nueva opción (nunca queda sin estado).
  for (const [sid, porCampo] of Object.entries(est.mapeoEstado || {})) registros[sid] = mapearEstados(registros[sid] || [], porCampo)
  return { ...datos, registros }
}
function mapearEstados(registros, porCampo) {
  return registros.map((r) => {
    let valores = r.valores
    for (const [cid, mapa] of Object.entries(porCampo)) { let v = valores[cid], n = 0; while (mapa[v] && n++ < 10) v = mapa[v]; if (v !== valores[cid]) valores = { ...valores, [cid]: v } }
    return valores === r.valores ? r : { ...r, valores }
  })
}

/** Lo que la PERSONA agregó, editó o borró por chat (D50), aplicado sobre los registros: { nuevos: {fuente: [reg]},
 * cambios: {fuente: {id: {campo: valor}}}, borrados: {fuente: [id]}, n }. Las claves son la sección DUEÑA de los datos
 * (s.fuente || s.id). Los registros de la persona no llevan «ejemplo»: «Borrar ejemplos» nunca los toca. */
export function aplicarDatos(datos, delta, mapeoEstado = {}) {
  if (!datos || !delta || (!delta.nuevos && !delta.cambios && !delta.borrados)) return datos
  const registros = { ...datos.registros }
  const fuentes = new Set([...Object.keys(delta.nuevos || {}), ...Object.keys(delta.cambios || {}), ...Object.keys(delta.borrados || {})])
  for (const f of fuentes) {
    const fuera = new Set(delta.borrados?.[f] || []), cambios = delta.cambios?.[f] || {}
    registros[f] = [...(registros[f] || []), ...(delta.nuevos?.[f] || [])]
      .filter((r) => !fuera.has(r.id))
      .map((r) => (cambios[r.id] ? { ...r, valores: { ...r.valores, ...cambios[r.id] } } : r))
    // Si después Shifu renombró o quitó una opción de estado, lo de la persona también pasa a la nueva (se calcula al leer:
    // así deshacer ese cambio de estructura devuelve sus valores originales).
    if (mapeoEstado?.[f]) registros[f] = mapearEstados(registros[f], mapeoEstado[f])
  }
  return { ...datos, registros }
}
