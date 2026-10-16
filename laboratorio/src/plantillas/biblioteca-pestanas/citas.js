export default {
  id: 'citas',
  para: 'Reservar y confirmar citas con clientes sin encimar horarios ni olvidar a nadie',
  palabras: ['citas', 'agendar cita', 'calendario de citas', 'horarios con clientes', 'reservaciones'],
  seccion: {
    titulo: 'Citas', icono: 'calendario', vista: 'agenda',
    opciones: { fecha: 'fecha', hora: 'hora', titulo: 'cliente', detalle: 'servicio' },
    campos: [
      { id: 'cliente', nombre: 'Cliente', tipo: 'texto' },
      { id: 'servicio', nombre: 'Servicio', tipo: 'texto', ejemplos: ['Consulta inicial', 'Corte y peinado', 'Mantenimiento', 'Valoración', 'Entrega de pedido', 'Asesoría'] },
      { id: 'fecha', nombre: 'Fecha', tipo: 'fecha', rango: [-14, 45] },
      { id: 'hora', nombre: 'Hora', tipo: 'hora' },
      { id: 'duracion', nombre: 'Duración (min)', tipo: 'numero', rango: [15, 180] },
      { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Solicitada', 'Confirmada', 'En sala', 'Atendida', 'No asistió', 'Cancelada'] },
    ],
  },
  piezas: [
    { vista: 'agenda', opciones: { fecha: 'fecha', hora: 'hora', titulo: 'cliente', detalle: 'servicio' }, ancho: 8, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'columnas', fecha: 'fecha', funcion: 'conteo', agrupar: 'mes' }, ancho: 4, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'medidor', estado: 'estado' }, ancho: 4, alto: 2 },
  ],
}
