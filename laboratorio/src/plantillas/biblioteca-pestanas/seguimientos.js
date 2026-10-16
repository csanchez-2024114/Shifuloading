export default {
  id: 'seguimientos',
  para: 'No perder el hilo con cada cliente: qué toca hacer y cuándo volver a escribirle o llamarle',
  palabras: ['seguimientos', 'dar seguimiento', 'próximo paso con cliente', 'recordar llamar', 'pendientes de contacto'],
  seccion: {
    titulo: 'Seguimientos', icono: 'actividad', vista: 'vencimientos',
    opciones: { fecha: 'proximo', titulo: 'cliente', detalle: 'nota', dias: 14, estado: 'estado', excluir: ['Hecho', 'Cancelado'] },
    campos: [
      { id: 'cliente', nombre: 'Cliente', tipo: 'texto' },
      { id: 'nota', nombre: 'Nota', tipo: 'texto', ejemplos: ['Enviar cotización actualizada', 'Confirmar instalación', 'Pedir referencia bancaria', 'Recordar pago', 'Agendar demo'] },
      { id: 'proximo', nombre: 'Próximo', tipo: 'fecha', rango: [-15, 30] },
      { id: 'ultimo', nombre: 'Último contacto', tipo: 'fecha', rango: [-90, 0] },
      { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Pendiente', 'Hoy', 'Atrasado', 'Hecho', 'Cancelado'] },
    ],
  },
  piezas: [
    { vista: 'vencimientos', opciones: { fecha: 'proximo', titulo: 'cliente', detalle: 'nota', dias: 14, estado: 'estado', excluir: ['Hecho', 'Cancelado'] }, ancho: 8, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'barras', estado: 'estado', funcion: 'conteo' }, ancho: 4, alto: 2 },
    { vista: 'kpis', opciones: { por: 'estado', vencen: 'proximo', dias: 3, estado: 'estado', excluir: ['Hecho', 'Cancelado'] }, ancho: 12 },
  ],
}
