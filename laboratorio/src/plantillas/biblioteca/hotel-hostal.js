const fijas = [
  { id: 'actividad', titulo: 'Historial', grupo: 1, icono: 'actividad', vista: 'feed' },
  { id: 'equipo', titulo: 'Equipo', grupo: 1, icono: 'equipo', vista: 'equipo' },
  { id: 'automatizaciones', titulo: 'Automatizaciones', grupo: 2, icono: 'rayo', vista: 'interruptores' },
]

export default {
  id: 'hotel-hostal',
  nombre: 'Hotel y hostal',
  para: 'Hoteles y hostales: reservas, habitaciones disponibles y huéspedes en casa',
  asignacion: {
    rubros: ['servicios', 'comercio'],
    ciclos: ['rapida', 'recurrente'],
    objetivos: ['contactos', 'reportes', 'seguimientos'],
    negocios: ['Hotel boutique', 'Hostal turístico', 'Posada familiar'],
  },
  // El recepcionista mira primero el mapa de habitaciones y las salidas del día; abajo ingresos por habitación y origen de huéspedes.
  inicio: [
    { vista: 'kpis', seccion: 'reservas', opciones: { por: 'estado', suma: 'total', hoy: 'llegada' }, ancho: 12 },
    { vista: 'tablero', seccion: 'habitaciones', opciones: { por: 'estado', titulo: 'numero', detalle: 'tipo' }, ancho: 6, alto: 2 },
    { vista: 'vencimientos', seccion: 'reservas', opciones: { fecha: 'salida', titulo: 'cliente', detalle: 'habitacion', dias: 5, estado: 'estado', excluir: ['Finalizada', 'Cancelada'] }, ancho: 6, alto: 2 },
    { vista: 'grafico', seccion: 'reservas', opciones: { tipo: 'barras', agrupar: 'habitacion', valor: 'total', funcion: 'suma' }, ancho: 8, alto: 2 },
    { vista: 'grafico', seccion: 'huespedes', opciones: { tipo: 'pastel', agrupar: 'procedencia' }, ancho: 4, alto: 2 },
  ],
  secciones: [
    { id: 'reservas', titulo: 'Reservas', grupo: 0, icono: 'calendario', vista: 'tablero', opciones: { por: 'estado', titulo: 'cliente', detalle: 'habitacion' },
      campos: [
        { id: 'cliente', nombre: 'Huésped', tipo: 'texto' },
        { id: 'habitacion', nombre: 'Habitación', tipo: 'texto', ejemplos: ['101', '102', '201 doble', '302 suite', 'Dormitorio A', 'Dormitorio B'] },
        { id: 'llegada', nombre: 'Llegada', tipo: 'fecha', rango: [-2, 30] },
        { id: 'salida', nombre: 'Salida', tipo: 'fecha', rango: [0, 14] },
        { id: 'total', nombre: 'Total', tipo: 'dinero', rango: [25, 450] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Confirmada', 'En casa', 'Por salir', 'Finalizada', 'Cancelada'] },
      ] },
    { id: 'habitaciones', titulo: 'Habitaciones', grupo: 0, icono: 'tabla', vista: 'tabla',
      campos: [
        { id: 'numero', nombre: 'Número', tipo: 'texto', ejemplos: ['101', '102', '201', '202', '301', '302'] },
        { id: 'tipo', nombre: 'Tipo', tipo: 'texto', ejemplos: ['Individual', 'Doble', 'Triple', 'Suite', 'Dormitorio compartido', 'Familiar'] },
        { id: 'capacidad', nombre: 'Capacidad', tipo: 'numero', rango: [1, 6] },
        { id: 'tarifa', nombre: 'Tarifa noche', tipo: 'dinero', rango: [18, 180] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Disponible', 'Ocupada', 'Limpieza', 'Mantenimiento', 'Fuera de servicio'] },
      ] },
    { id: 'huespedes', titulo: 'Huéspedes', grupo: 0, icono: 'usuarios', vista: 'tabla',
      campos: [
        { id: 'nombre', nombre: 'Nombre', tipo: 'texto' },
        { id: 'telefono', nombre: 'Teléfono', tipo: 'texto' },
        { id: 'procedencia', nombre: 'Procedencia', tipo: 'texto', ejemplos: ['Ciudad de Guatemala', 'Antigua', 'El Salvador', 'México', 'Europa', 'Estados Unidos'] },
        { id: 'visitas', nombre: 'Visitas', tipo: 'numero', rango: [1, 20] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['En casa', 'Reserva futura', 'Frecuente', 'Inactivo'] },
      ] },
    ...fijas,
  ],
}
