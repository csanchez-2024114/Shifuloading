export default {
  id: 'reuniones',
  para: 'Agendar reuniones con clientes o tu equipo y ver qué viene esta semana en un solo lugar',
  palabras: ['reuniones', 'junta con cliente', 'citas de trabajo', 'agenda de reuniones', 'calendario de juntas'],
  seccion: {
    titulo: 'Reuniones', icono: 'calendario', vista: 'agenda',
    opciones: { fecha: 'fecha', hora: 'hora', titulo: 'asunto', detalle: 'participantes' },
    campos: [
      { id: 'asunto', nombre: 'Asunto', tipo: 'texto', ejemplos: ['Revisión de avance', 'Presentación propuesta', 'Alta de proveedor', 'Cierre de mes', 'Onboarding cliente'] },
      { id: 'participantes', nombre: 'Participantes', tipo: 'texto', ejemplos: ['Dueño y contador', 'Cliente ABC', 'Equipo ventas', 'Socios', 'Proveedor logística'] },
      { id: 'fecha', nombre: 'Fecha', tipo: 'fecha', rango: [-30, 60] },
      { id: 'hora', nombre: 'Hora', tipo: 'hora' },
      { id: 'lugar', nombre: 'Lugar', tipo: 'texto', ejemplos: ['Oficina', 'Zoom', 'Sucursal norte', 'Cafetería centro', 'En sitio cliente'] },
      { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Programada', 'Confirmada', 'En curso', 'Realizada', 'Reprogramada', 'Cancelada'] },
    ],
  },
  piezas: [
    { vista: 'agenda', opciones: { fecha: 'fecha', hora: 'hora', titulo: 'asunto', detalle: 'participantes' }, ancho: 8, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'linea-area', fecha: 'fecha', funcion: 'conteo' }, ancho: 4, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'pastel', estado: 'estado', funcion: 'conteo' }, ancho: 4, alto: 2 },
  ],
}
