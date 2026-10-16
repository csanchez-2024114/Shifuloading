const fijas = [
  { id: 'actividad', titulo: 'Historial', grupo: 1, icono: 'actividad', vista: 'feed' },
  { id: 'equipo', titulo: 'Equipo', grupo: 1, icono: 'equipo', vista: 'equipo' },
  { id: 'automatizaciones', titulo: 'Automatizaciones', grupo: 2, icono: 'rayo', vista: 'interruptores' },
]

export default {
  id: 'transporte-mensajeria',
  nombre: 'Transporte y mensajería',
  para: 'Empresas de envíos y mensajería: paquetes en ruta, rutas del día y repartidores',
  asignacion: {
    rubros: ['servicios', 'comercio', 'otro'],
    ciclos: ['rapida', 'recurrente'],
    objetivos: ['seguimientos', 'reportes', 'equipo', 'integraciones'],
    negocios: ['Mensajería urbana', 'Paquetería regional', 'Courier express', 'Reparto de última milla'],
  },
  // KPIs del día, paquetes en curso junto a rutas programadas; embudo de estados y carga por repartidor.
  inicio: [
    { vista: 'kpis', seccion: 'envios', opciones: { por: 'estado', suma: 'tarifa', hoy: 'entrega' }, ancho: 12 },
    { vista: 'tablero', seccion: 'envios', opciones: { por: 'estado', titulo: 'guia', detalle: 'destino' }, ancho: 8, alto: 2 },
    { vista: 'vencimientos', seccion: 'rutas', opciones: { fecha: 'salida', titulo: 'ruta', detalle: 'zona', dias: 5, estado: 'estado', excluir: ['Completada', 'Cancelada'] }, ancho: 4, alto: 2 },
    { vista: 'grafico', seccion: 'envios', opciones: { tipo: 'embudo' }, ancho: 3, alto: 2 },
    { vista: 'grafico', seccion: 'repartidores', opciones: { tipo: 'barras', agrupar: 'nombre', valor: 'entregas', funcion: 'suma' }, ancho: 3, alto: 2 },
    { vista: 'tabla', seccion: 'repartidores', opciones: {}, ancho: 6, alto: 2 },
  ],
  secciones: [
    { id: 'envios', titulo: 'Envíos', grupo: 0, icono: 'camion', vista: 'tablero', opciones: { por: 'estado', titulo: 'guia', detalle: 'destino' },
      campos: [
        { id: 'guia', nombre: 'Guía', tipo: 'texto', ejemplos: ['GT-88201', 'GT-88202', 'GT-88203', 'GT-88204', 'GT-88205', 'GT-88206'] },
        { id: 'cliente', nombre: 'Cliente', tipo: 'texto' },
        { id: 'destino', nombre: 'Destino', tipo: 'texto', ejemplos: ['Zona 4', 'Mixco', 'Amatitlán', 'Escuintla', 'Cobán', 'Puerto Barrios'] },
        { id: 'tarifa', nombre: 'Tarifa', tipo: 'dinero', rango: [25, 450] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Recibido', 'En bodega', 'En ruta', 'Entregado', 'Incidencia'] },
        { id: 'entrega', nombre: 'Entrega', tipo: 'fecha', rango: [-2, 8] },
      ] },
    { id: 'rutas', titulo: 'Rutas', grupo: 0, icono: 'calendario', vista: 'vencimientos', opciones: { fecha: 'salida', titulo: 'ruta', detalle: 'zona', dias: 7, estado: 'estado', excluir: ['Completada', 'Cancelada'] },
      campos: [
        { id: 'ruta', nombre: 'Ruta', tipo: 'texto', ejemplos: ['Norte AM', 'Sur PM', 'Centro express', 'Occidente', 'Interior día 1', 'Última milla zona 10'] },
        { id: 'zona', nombre: 'Zona', tipo: 'texto', ejemplos: ['Zona 1-4', 'Mixco-San Juan', 'Carretera al Pacífico', 'Quetzaltenango', 'Petén', 'Costa Sur'] },
        { id: 'salida', nombre: 'Salida', tipo: 'fecha', rango: [-3, 10] },
        { id: 'paquetes', nombre: 'Paquetes', tipo: 'numero', rango: [5, 80] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Programada', 'En curso', 'Completada', 'Cancelada'] },
      ] },
    { id: 'repartidores', titulo: 'Repartidores', grupo: 0, icono: 'equipo', vista: 'tabla',
      campos: [
        { id: 'nombre', nombre: 'Nombre', tipo: 'texto' },
        { id: 'telefono', nombre: 'Teléfono', tipo: 'texto' },
        { id: 'vehiculo', nombre: 'Vehículo', tipo: 'texto', ejemplos: ['Moto Honda', 'Panel Nissan', 'Camioneta Hilux', 'Bicicleta eléctrica', 'Moto TVS', 'Van Ford'] },
        { id: 'entregas', nombre: 'Entregas hoy', tipo: 'numero', rango: [0, 35] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Disponible', 'En ruta', 'Descanso', 'Fuera de servicio'] },
      ] },
    ...fijas,
  ],
}
