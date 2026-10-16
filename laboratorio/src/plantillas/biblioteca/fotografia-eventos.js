const fijas = [
  { id: 'actividad', titulo: 'Historial', grupo: 1, icono: 'actividad', vista: 'feed' },
  { id: 'equipo', titulo: 'Equipo', grupo: 1, icono: 'equipo', vista: 'equipo' },
  { id: 'automatizaciones', titulo: 'Automatizaciones', grupo: 2, icono: 'rayo', vista: 'interruptores' },
]

export default {
  id: 'fotografia-eventos',
  nombre: 'Fotografía y eventos',
  para: 'Estudios de foto y organizadores: sesiones, eventos próximos y pagos pendientes',
  asignacion: {
    rubros: ['servicios', 'agencia'],
    ciclos: ['cotizacion', 'mezcla', 'recurrente'],
    objetivos: ['seguimientos', 'cotizaciones', 'reportes', 'equipo'],
    negocios: ['Estudio fotográfico', 'Fotógrafo de bodas', 'Organizador de eventos', 'Productora de video social'],
  },
  // Calendario de eventos arriba; al lado el flujo de edición; abajo cobros y tipos de sesión.
  inicio: [
    { vista: 'agenda', seccion: 'eventos', opciones: { fecha: 'fecha', hora: 'hora', titulo: 'evento', detalle: 'cliente', dias: 21 }, ancho: 8, alto: 2 },
    { vista: 'tablero', seccion: 'sesiones', opciones: { por: 'estado', titulo: 'sesion', detalle: 'cliente' }, ancho: 4, alto: 2 },
    { vista: 'kpis', seccion: 'sesiones', opciones: { por: 'estado', suma: 'anticipo' }, ancho: 12 },
    { vista: 'grafico', seccion: 'pagos', opciones: { tipo: 'linea-area', fecha: 'fecha', valor: 'monto', funcion: 'suma' }, ancho: 8, alto: 2 },
    { vista: 'grafico', seccion: 'sesiones', opciones: { tipo: 'pastel', agrupar: 'paquete' }, ancho: 4, alto: 2 },
  ],
  secciones: [
    { id: 'sesiones', titulo: 'Sesiones', grupo: 0, icono: 'tablero', vista: 'tablero', opciones: { por: 'estado', titulo: 'sesion', detalle: 'cliente' },
      campos: [
        { id: 'sesion', nombre: 'Sesión', tipo: 'texto', ejemplos: ['Retrato familiar', 'Quinceañera', 'Producto e-commerce', 'Maternity', 'Graduación', 'Corporativo'] },
        { id: 'cliente', nombre: 'Cliente', tipo: 'texto' },
        { id: 'fecha', nombre: 'Fecha', tipo: 'fecha', rango: [-5, 45] },
        { id: 'anticipo', nombre: 'Anticipo', tipo: 'dinero', rango: [100, 1500] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Cotizada', 'Reservada', 'Realizada', 'Editando', 'Entregada'] },
        { id: 'paquete', nombre: 'Paquete', tipo: 'texto', ejemplos: ['Básico 1h', 'Premium 3h', 'All day', 'Estudio + exteriores', 'Con video', 'Álbum impreso'] },
      ] },
    { id: 'eventos', titulo: 'Eventos', grupo: 0, icono: 'calendario', vista: 'agenda', opciones: { fecha: 'fecha', hora: 'hora', titulo: 'evento', detalle: 'cliente', dias: 21 },
      campos: [
        { id: 'evento', nombre: 'Evento', tipo: 'texto', ejemplos: ['Boda jardín', 'XV años salón', 'Lanzamiento marca', 'Cumpleaños 50', 'Conferencia anual', 'Baby shower'] },
        { id: 'cliente', nombre: 'Cliente', tipo: 'texto' },
        { id: 'fecha', nombre: 'Fecha', tipo: 'fecha', rango: [-7, 60] },
        { id: 'hora', nombre: 'Hora', tipo: 'hora' },
        { id: 'lugar', nombre: 'Lugar', tipo: 'texto', ejemplos: ['Salón Vista Real', 'Hotel Intercontinental', 'Jardín Los Pinos', 'Plaza Central', 'Casa particular', 'Centro de convenciones'] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Por confirmar', 'Confirmado', 'En curso', 'Cerrado', 'Cancelado'] },
      ] },
    { id: 'pagos', titulo: 'Pagos', grupo: 0, icono: 'tarjeta', vista: 'tabla',
      campos: [
        { id: 'cliente', nombre: 'Cliente', tipo: 'texto' },
        { id: 'concepto', nombre: 'Concepto', tipo: 'texto', ejemplos: ['Anticipo boda', 'Saldo sesión', 'Paquete álbum', 'Video highlight', 'Horas extra', 'Retoque adicional'] },
        { id: 'monto', nombre: 'Monto', tipo: 'dinero', rango: [150, 8000] },
        { id: 'fecha', nombre: 'Fecha', tipo: 'fecha', rango: [-180, 15] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Pendiente', 'Parcial', 'Pagado', 'Vencido'] },
      ] },
    ...fijas,
  ],
}
