export default {
  id: 'turnos',
  para: 'Programar turnos de trabajo y ver quién cubre cada horario en la semana',
  palabras: ['turnos', 'horarios de trabajo', 'roster', 'quién trabaja mañana', 'cuadrante de turnos'],
  seccion: {
    titulo: 'Turnos', icono: 'reloj', vista: 'agenda',
    opciones: { fecha: 'fecha', hora: 'inicio', titulo: 'colaborador', detalle: 'area' },
    campos: [
      { id: 'colaborador', nombre: 'Colaborador', tipo: 'texto', ejemplos: ['Ana recepción', 'Carlos bodega', 'María caja', 'Equipo nocturno', 'Reparto zona 1'] },
      { id: 'area', nombre: 'Área', tipo: 'texto', ejemplos: ['Mostrador', 'Cocina', 'Almacén', 'Call center', 'Limpieza', 'Seguridad'] },
      { id: 'fecha', nombre: 'Fecha', tipo: 'fecha', rango: [-14, 30] },
      { id: 'inicio', nombre: 'Inicio', tipo: 'hora' },
      { id: 'fin', nombre: 'Fin', tipo: 'hora' },
      { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Programado', 'Confirmado', 'Cubierto', 'Cambio solicitado', 'Ausente'] },
    ],
  },
  piezas: [
    { vista: 'agenda', opciones: { fecha: 'fecha', hora: 'inicio', titulo: 'colaborador', detalle: 'area' }, ancho: 8, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'barras-apiladas', estado: 'estado', fecha: 'fecha', funcion: 'conteo', meses: 2 }, ancho: 4, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'pastel', estado: 'area', funcion: 'conteo' }, ancho: 4, alto: 2 },
  ],
}
