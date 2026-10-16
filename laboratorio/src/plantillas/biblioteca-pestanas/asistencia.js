export default {
  id: 'asistencia',
  para: 'Registrar asistencia del personal por día y detectar faltas o retardos a tiempo',
  palabras: ['asistencia', 'control de asistencia', 'faltas y retardos', 'entrada y salida', 'quién vino hoy'],
  seccion: {
    titulo: 'Asistencia', icono: 'reloj', vista: 'tabla',
    campos: [
      { id: 'colaborador', nombre: 'Colaborador', tipo: 'texto', ejemplos: ['Turno mañana', 'Recepción', 'Bodega', 'Ventas piso', 'Repartidor 2'] },
      { id: 'fecha', nombre: 'Fecha', tipo: 'fecha', rango: [-90, 0] },
      { id: 'entrada', nombre: 'Entrada', tipo: 'hora' },
      { id: 'salida', nombre: 'Salida', tipo: 'hora' },
      { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Presente', 'Retardo', 'Falta justificada', 'Falta', 'Permiso', 'Descanso'] },
    ],
  },
  piezas: [
    { vista: 'tabla', opciones: { orden: 'fecha' }, ancho: 8, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'area-apilada', estado: 'estado', fecha: 'fecha', funcion: 'conteo', meses: 3 }, ancho: 4, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'barras', estado: 'estado', funcion: 'conteo' }, ancho: 6, alto: 2 },
  ],
}
