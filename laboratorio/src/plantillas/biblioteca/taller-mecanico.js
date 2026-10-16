/* Plantilla de ejemplo de la biblioteca (referencia para los agentes que crean plantillas). */
const fijas = [
  { id: 'actividad', titulo: 'Historial', grupo: 1, icono: 'actividad', vista: 'feed' },
  { id: 'equipo', titulo: 'Equipo', grupo: 1, icono: 'equipo', vista: 'equipo' },
  { id: 'automatizaciones', titulo: 'Automatizaciones', grupo: 2, icono: 'rayo', vista: 'interruptores' },
]

export default {
  id: 'taller-mecanico',
  nombre: 'Taller mecánico',
  para: 'Talleres de autos y motos: órdenes de trabajo, repuestos y clientes que vuelven',
  asignacion: {
    rubros: ['servicios', 'comercio'],
    ciclos: ['cotizacion', 'recurrente'],
    objetivos: ['seguimientos', 'cotizaciones', 'reportes'],
    negocios: ['Taller de autos', 'Taller de motos', 'Centro de servicio rápido de aceite', 'Taller de enderezado y pintura'],
  },
  // Un taller vive del tablero de órdenes: va arriba y grande; al lado lo que se entrega pronto; abajo dinero y repuestos.
  inicio: [
    { vista: 'tablero', seccion: 'ordenes', opciones: { por: 'estado', titulo: 'vehiculo', detalle: 'cliente' }, ancho: 8, alto: 3 },
    { vista: 'vencimientos', seccion: 'ordenes', opciones: { fecha: 'entrega', titulo: 'vehiculo', detalle: 'servicio', dias: 7, estado: 'estado', excluir: ['Entregado'] }, ancho: 4, alto: 3 },
    { vista: 'grafico', seccion: 'ordenes', opciones: { tipo: 'barras', agrupar: 'servicio', valor: 'total', funcion: 'suma' }, ancho: 6, alto: 2 },
    { vista: 'grafico', seccion: 'clientes', opciones: { tipo: 'linea-area' }, ancho: 6, alto: 2 },
  ],
  secciones: [
    { id: 'ordenes', titulo: 'Órdenes de trabajo', grupo: 0, icono: 'tablero', vista: 'tablero', opciones: { por: 'estado', titulo: 'vehiculo', detalle: 'cliente' },
      campos: [
        { id: 'vehiculo', nombre: 'Vehículo', tipo: 'texto', ejemplos: ['Toyota Hilux 2018', 'Honda Civic 2015', 'Nissan Sentra 2020', 'Mazda 3 2017', 'Yamaha FZ 2021', 'Kia Picanto 2019'] },
        { id: 'cliente', nombre: 'Cliente', tipo: 'texto' },
        { id: 'servicio', nombre: 'Servicio', tipo: 'texto', ejemplos: ['Cambio de aceite', 'Frenos', 'Alineación y balanceo', 'Diagnóstico', 'Cambio de embrague', 'Afinamiento'] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Recibido', 'Diagnóstico', 'Esperando repuesto', 'En reparación', 'Listo', 'Entregado'] },
        { id: 'entrega', nombre: 'Entrega', tipo: 'fecha', rango: [-3, 10] },
        { id: 'total', nombre: 'Total', tipo: 'dinero', rango: [150, 6000] },
      ] },
    { id: 'clientes', titulo: 'Clientes', grupo: 0, icono: 'usuarios', vista: 'tabla',
      campos: [
        { id: 'nombre', nombre: 'Nombre', tipo: 'texto' }, { id: 'telefono', nombre: 'Teléfono', tipo: 'texto' },
        { id: 'tipo', nombre: 'Tipo', tipo: 'estado', opciones: ['Nuevo', 'Frecuente', 'Flota'] }, { id: 'alta', nombre: 'Alta', tipo: 'fecha', rango: [-330, 0] },
      ] },
    { id: 'repuestos', titulo: 'Repuestos', grupo: 0, icono: 'caja', vista: 'tabla',
      campos: [
        { id: 'repuesto', nombre: 'Repuesto', tipo: 'texto', ejemplos: ['Filtro de aceite', 'Pastillas de freno', 'Bujías', 'Batería 12V', 'Llanta 15"', 'Faja de distribución'] },
        { id: 'cantidad', nombre: 'Cantidad', tipo: 'numero', rango: [0, 40] }, { id: 'minimo', nombre: 'Mínimo', tipo: 'numero', rango: [2, 10] },
        { id: 'costo', nombre: 'Costo', tipo: 'dinero', rango: [20, 1200] },
      ] },
    ...fijas,
  ],
}
