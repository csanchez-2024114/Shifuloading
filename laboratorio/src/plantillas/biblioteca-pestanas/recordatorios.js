export default {
  id: 'recordatorios',
  para: 'Programar avisos importantes para ti o tu equipo y ver qué vence pronto',
  palabras: ['recordatorios', 'avisos', 'no olvidar', 'alarmas del negocio', 'pendientes con fecha'],
  seccion: {
    titulo: 'Recordatorios', icono: 'reloj', vista: 'vencimientos',
    opciones: { fecha: 'cuando', titulo: 'titulo', detalle: 'para_quien', dias: 21, estado: 'estado', excluir: ['Listo'] },
    campos: [
      { id: 'titulo', nombre: 'Título', tipo: 'texto', ejemplos: ['Renovar póliza', 'Pagar predial', 'Pedir insumos', 'Felicitar cliente VIP', 'Revisar contrato'] },
      { id: 'para_quien', nombre: 'Para quién', tipo: 'texto', ejemplos: ['Gerente', 'Contabilidad', 'Todos', 'Bodega', 'Recepción'] },
      { id: 'cuando', nombre: 'Cuándo', tipo: 'fecha', rango: [-10, 90] },
      { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Programado', 'Próximo', 'Vencido', 'Listo', 'Pospuesto'] },
    ],
  },
  piezas: [
    { vista: 'vencimientos', opciones: { fecha: 'cuando', titulo: 'titulo', detalle: 'para_quien', dias: 21, estado: 'estado', excluir: ['Listo'] }, ancho: 8, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'anillos', estado: 'estado', funcion: 'conteo' }, ancho: 4, alto: 2 },
    { vista: 'kpis', opciones: { por: 'estado', vencen: 'cuando', dias: 7, estado: 'estado', excluir: ['Listo'] }, ancho: 12 },
  ],
}
