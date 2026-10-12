/* Vocabulario del CRM que no depende de ningún servidor: etapas, columnas de tareas y los nombres de las secciones por rubro. */

export const ETAPAS = ['Nuevo', 'En contacto', 'Interesado', 'Cliente']
export const COLUMNAS = [['porHacer', 'Por hacer'], ['enCurso', 'En curso'], ['hecho', 'Hecho']]

/* Cada CRM nombra sus secciones con el lenguaje del rubro. Orden: contactos, cobros, trabajo, actividad y equipo. */
const SECCIONES = {
  servicios: ['Clientes', 'Facturación', 'Proyectos', 'Bitácora', 'Equipo'],
  agencia: ['Clientes', 'Presupuestos y pagos', 'Campañas', 'Línea de tiempo', 'Talento'],
  comercio: ['Compradores', 'Caja', 'Pedidos', 'Movimiento', 'Vendedores'],
  salud: ['Pacientes', 'Pagos y consultas', 'Tratamientos', 'Historial', 'Especialistas'],
  educacion: ['Alumnos', 'Mensualidades', 'Clases', 'Novedades', 'Docentes'],
  tecnologia: ['Cuentas', 'Suscripciones', 'Desarrollo', 'Registro', 'Equipo técnico'],
  inmobiliaria: ['Interesados', 'Comisiones y pagos', 'Propiedades', 'Visitas', 'Asesores'],
  otro: ['Contactos', 'Cobros', 'Proyectos', 'Actividad', 'Equipo'],
}
const ORDEN = { contactos: 0, cobros: 1, desarrollo: 2, actividad: 3, rrhh: 4 }
const FIJAS = { importar: 'Importar datos', automatizaciones: 'Automatizaciones' }

/** Nombre de una sección: el que la persona le puso (`sobrescritos`) o el que corresponde a su rubro. */
export const tituloSeccion = (rubro, id, sobrescritos = {}) => sobrescritos[id] || FIJAS[id] || (SECCIONES[rubro] || SECCIONES.otro)[ORDEN[id]]
export const IDS_SECCION = ['contactos', 'cobros', 'desarrollo', 'actividad', 'rrhh', 'importar', 'automatizaciones']
