/* Plantillas visuales iniciales del CRM. Cada plantilla es SOLO estructura y vista: qué secciones hay, qué campos tienen,
 * con qué vista del catálogo se dibuja cada una y qué muestra la pantalla de inicio. Nunca lleva datos de clientes.
 *
 * Tipos de campo: texto · numero · dinero · fecha · hora · estado (con `opciones`).
 * `estado` es el tipo que hoy no existe en las secciones propias: aquí se prueba qué vistas necesita.
 * Grupos del menú: 0 Estructura · 1 Medición y equipo · 2 Automatizaciones (como en CrmPage).
 * Las vistas válidas y lo que exige cada una están en `validar.js`. */

const clientes = (nombre = 'Clientes', etapas = ['Nuevo', 'En contacto', 'Interesado', 'Cliente']) => ({
  id: 'clientes', titulo: nombre, grupo: 0, icono: 'usuarios', vista: 'tabla',
  campos: [
    { id: 'nombre', nombre: 'Nombre', tipo: 'texto' },
    { id: 'telefono', nombre: 'Teléfono', tipo: 'texto' },
    { id: 'etapa', nombre: 'Etapa', tipo: 'estado', opciones: etapas },
    { id: 'alta', nombre: 'Alta', tipo: 'fecha' },
  ],
})

const fijas = [
  { id: 'actividad', titulo: 'Historial', grupo: 1, icono: 'actividad', vista: 'feed' },
  { id: 'equipo', titulo: 'Equipo', grupo: 1, icono: 'equipo', vista: 'equipo' },
  { id: 'automatizaciones', titulo: 'Automatizaciones', grupo: 2, icono: 'rayo', vista: 'interruptores' },
]

export const PLANTILLAS = [
  {
    id: 'embudo', nombre: 'Embudo de ventas', para: 'Servicios profesionales, inmobiliaria, tecnología: ventas con cotización',
    inicio: [
      { vista: 'kpis', seccion: 'clientes', opciones: { por: 'etapa' } },
      { vista: 'tablero', seccion: 'clientes', opciones: { por: 'etapa', titulo: 'nombre', detalle: 'telefono' } },
      { vista: 'grafica', seccion: 'cotizaciones', opciones: { tipo: 'barras', por: 'estado', suma: 'monto' } },
    ],
    secciones: [
      { ...clientes('Clientes', ['Nuevo', 'Contactado', 'Propuesta', 'Negociación', 'Ganado', 'Perdido']), vista: 'tablero', opciones: { por: 'etapa', titulo: 'nombre', detalle: 'telefono' } },
      { id: 'seguimientos', titulo: 'Seguimientos', grupo: 0, icono: 'reloj', vista: 'vencimientos', opciones: { fecha: 'cuando', titulo: 'quien', dias: 14 },
        campos: [{ id: 'quien', nombre: 'Con quién', tipo: 'texto' }, { id: 'cuando', nombre: 'Cuándo', tipo: 'fecha' }, { id: 'nota', nombre: 'Nota', tipo: 'texto' }] },
      { id: 'cotizaciones', titulo: 'Cotizaciones', grupo: 0, icono: 'documento', vista: 'tabla',
        campos: [{ id: 'cliente', nombre: 'Cliente', tipo: 'texto' }, { id: 'monto', nombre: 'Monto', tipo: 'dinero' },
          { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Borrador', 'Enviada', 'Aceptada', 'Rechazada'] }, { id: 'enviada', nombre: 'Enviada', tipo: 'fecha' }] },
      ...fijas,
    ],
  },
  {
    id: 'agenda', nombre: 'Agenda y citas', para: 'Salud y bienestar, spa, clínica, educación: clientes que reservan',
    inicio: [
      { vista: 'kpis', seccion: 'citas', opciones: { por: 'estado', hoy: 'fecha' } },
      { vista: 'agenda', seccion: 'citas', opciones: { fecha: 'fecha', hora: 'hora', titulo: 'cliente', detalle: 'servicio', dias: 7 } },
    ],
    secciones: [
      { id: 'citas', titulo: 'Agenda', grupo: 0, icono: 'calendario', vista: 'agenda', opciones: { fecha: 'fecha', hora: 'hora', titulo: 'cliente', detalle: 'servicio', dias: 7 },
        campos: [{ id: 'cliente', nombre: 'Cliente', tipo: 'texto' }, { id: 'servicio', nombre: 'Servicio', tipo: 'texto' },
          { id: 'fecha', nombre: 'Fecha', tipo: 'fecha' }, { id: 'hora', nombre: 'Hora', tipo: 'hora' },
          { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Por confirmar', 'Confirmada', 'Atendida', 'No asistió'] }] },
      clientes('Clientas', ['Primera visita', 'Recurrente', 'Inactiva']),
      { id: 'paquetes', titulo: 'Paquetes y tratamientos', grupo: 0, icono: 'tablero', vista: 'tablero', opciones: { por: 'estado', titulo: 'cliente', detalle: 'paquete' },
        campos: [{ id: 'cliente', nombre: 'Cliente', tipo: 'texto' }, { id: 'paquete', nombre: 'Paquete', tipo: 'texto' },
          { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Iniciado', 'En curso', 'Terminado'] }, { id: 'sesiones', nombre: 'Sesiones', tipo: 'numero' }] },
      ...fijas,
    ],
  },
  {
    id: 'pedidos', nombre: 'Pedidos y entregas', para: 'Comercio, comida, encargos: pedidos que se preparan y se entregan',
    inicio: [
      { vista: 'kpis', seccion: 'pedidos', opciones: { por: 'estado', suma: 'anticipo' } },
      { vista: 'vencimientos', seccion: 'pedidos', opciones: { fecha: 'entrega', titulo: 'cliente', detalle: 'producto', dias: 7, estado: 'estado', excluir: ['Entregado'] } },
      { vista: 'grafica', seccion: 'pedidos', opciones: { tipo: 'dona', por: 'estado' } },
    ],
    secciones: [
      { id: 'pedidos', titulo: 'Pedidos', grupo: 0, icono: 'caja', vista: 'tablero', opciones: { por: 'estado', titulo: 'cliente', detalle: 'producto' },
        campos: [{ id: 'cliente', nombre: 'Cliente', tipo: 'texto' }, { id: 'producto', nombre: 'Producto', tipo: 'texto' },
          { id: 'entrega', nombre: 'Entrega', tipo: 'fecha' }, { id: 'anticipo', nombre: 'Anticipo', tipo: 'dinero' },
          { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Recibido', 'En producción', 'Listo', 'Entregado'] }] },
      clientes('Clientes', ['Nuevo', 'Frecuente', 'Mayorista']),
      { id: 'inventario', titulo: 'Inventario', grupo: 0, icono: 'tabla', vista: 'tabla',
        campos: [{ id: 'producto', nombre: 'Producto', tipo: 'texto' }, { id: 'cantidad', nombre: 'Cantidad', tipo: 'numero' }, { id: 'minimo', nombre: 'Mínimo', tipo: 'numero' }] },
      { id: 'proveedores', titulo: 'Proveedores', grupo: 0, icono: 'camion', vista: 'tabla',
        campos: [{ id: 'nombre', nombre: 'Proveedor', tipo: 'texto' }, { id: 'producto', nombre: 'Qué surte', tipo: 'texto' }, { id: 'telefono', nombre: 'Teléfono', tipo: 'texto' }] },
      ...fijas,
    ],
  },
  {
    id: 'membresias', nombre: 'Membresías', para: 'Gimnasios, spas con membresía, academias, suscripciones',
    inicio: [
      { vista: 'kpis', seccion: 'miembros', opciones: { por: 'estado', vencen: 'vence', dias: 7, estado: 'estado', excluir: ['Cancelada'] } },
      { vista: 'vencimientos', seccion: 'miembros', opciones: { fecha: 'vence', titulo: 'nombre', detalle: 'plan', dias: 30, estado: 'estado', excluir: ['Cancelada'] } },
      { vista: 'grafica', seccion: 'miembros', opciones: { tipo: 'linea', fecha: 'alta' } },
    ],
    secciones: [
      { id: 'miembros', titulo: 'Miembros', grupo: 0, icono: 'usuarios', vista: 'tabla',
        campos: [{ id: 'nombre', nombre: 'Nombre', tipo: 'texto' }, { id: 'plan', nombre: 'Plan', tipo: 'texto' },
          { id: 'alta', nombre: 'Alta', tipo: 'fecha' }, { id: 'vence', nombre: 'Vence', tipo: 'fecha' },
          { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Activa', 'Pausada', 'Cancelada'] }] },
      { id: 'vencimientos', titulo: 'Vencimientos', grupo: 0, icono: 'reloj', vista: 'vencimientos', fuente: 'miembros', opciones: { fecha: 'vence', titulo: 'nombre', detalle: 'plan', dias: 30, estado: 'estado', excluir: ['Cancelada'] } },
      { id: 'pagos', titulo: 'Pagos', grupo: 1, icono: 'tarjeta', vista: 'tabla',
        campos: [{ id: 'miembro', nombre: 'Miembro', tipo: 'texto' }, { id: 'monto', nombre: 'Monto', tipo: 'dinero' }, { id: 'fecha', nombre: 'Fecha', tipo: 'fecha' }] },
      ...fijas,
    ],
  },
  {
    id: 'proyectos', nombre: 'Proyectos y campañas', para: 'Agencias, estudios creativos, tecnología: proyectos con propuesta',
    inicio: [
      { vista: 'kpis', seccion: 'cotizaciones', opciones: { por: 'estado', suma: 'monto' } },
      { vista: 'tablero', seccion: 'proyectos', opciones: { por: 'estado', titulo: 'proyecto', detalle: 'cliente' } },
      { vista: 'vencimientos', seccion: 'campanas', opciones: { fecha: 'fin', titulo: 'campana', detalle: 'cliente', dias: 14 } },
    ],
    secciones: [
      { id: 'proyectos', titulo: 'Proyectos', grupo: 0, icono: 'tablero', vista: 'tablero', opciones: { por: 'estado', titulo: 'proyecto', detalle: 'cliente' },
        campos: [{ id: 'proyecto', nombre: 'Proyecto', tipo: 'texto' }, { id: 'cliente', nombre: 'Cliente', tipo: 'texto' },
          { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Propuesta', 'Aprobado', 'En curso', 'En revisión', 'Entregado'] }, { id: 'entrega', nombre: 'Entrega', tipo: 'fecha' }] },
      { id: 'cotizaciones', titulo: 'Cotizaciones', grupo: 0, icono: 'documento', vista: 'tabla',
        campos: [{ id: 'cliente', nombre: 'Cliente', tipo: 'texto' }, { id: 'monto', nombre: 'Monto', tipo: 'dinero' },
          { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Enviada', 'Aceptada', 'Rechazada'] }, { id: 'enviada', nombre: 'Enviada', tipo: 'fecha' }] },
      { id: 'campanas', titulo: 'Campañas activas', grupo: 0, icono: 'calendario', vista: 'tabla',
        campos: [{ id: 'campana', nombre: 'Campaña', tipo: 'texto' }, { id: 'cliente', nombre: 'Cliente', tipo: 'texto' },
          { id: 'inicio', nombre: 'Inicio', tipo: 'fecha' }, { id: 'fin', nombre: 'Fin', tipo: 'fecha' }, { id: 'presupuesto', nombre: 'Presupuesto', tipo: 'dinero' }] },
      clientes('Clientes', ['Prospecto', 'Activo', 'Pausado']),
      ...fijas,
    ],
  },
  {
    id: 'simple', nombre: 'Simple', para: 'Quien empieza o quiere lo mínimo: clientes y tareas',
    inicio: [
      { vista: 'kpis', seccion: 'clientes', opciones: { por: 'etapa' } },
      { vista: 'tablero', seccion: 'tareas', opciones: { por: 'estado', titulo: 'tarea' } },
    ],
    secciones: [
      clientes(),
      { id: 'tareas', titulo: 'Tareas', grupo: 0, icono: 'tablero', vista: 'tablero', opciones: { por: 'estado', titulo: 'tarea' },
        campos: [{ id: 'tarea', nombre: 'Tarea', tipo: 'texto' }, { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Por hacer', 'En curso', 'Hecho'] }] },
      ...fijas,
    ],
  },
]

// Biblioteca ampliada: una plantilla por archivo en ./biblioteca (las crean agentes y pasan el filtro de calidad).
const BIBLIO = Object.values(import.meta.glob('./biblioteca/*.js', { eager: true })).map((m) => m.default).filter(Boolean)
PLANTILLAS.push(...BIBLIO.filter((b) => !PLANTILLAS.some((p) => p.id === b.id)))

// Biblioteca de pestañas (D30 nivel 2): cada una se puede ver SOLA en el laboratorio, como un CRM mínimo con esa pestaña y
// sus piezas sugeridas en el inicio. Material interno (D49): el usuario nunca las elige; la IA parte de ellas.
const PEST = Object.values(import.meta.glob('./biblioteca-pestanas/*.js', { eager: true })).map((m) => m.default).filter(Boolean)
export const PESTANAS_VISTA = PEST.map((p) => ({
  id: `pestana-${p.id}`, nombre: p.seccion.titulo, para: p.para, interna: 'pestana',
  inicio: p.piezas.map((w) => ({ ...w, seccion: p.id })),
  secciones: [{ ...p.seccion, id: p.id, grupo: 0 }, ...fijas],
}))

export const plantillaPorId = (id) => PLANTILLAS.find((p) => p.id === id) || PESTANAS_VISTA.find((p) => p.id === id)
