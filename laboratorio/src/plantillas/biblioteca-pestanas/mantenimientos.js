export default {
  id: 'mantenimientos',
  para: 'Programar mantenimiento de equipos o instalaciones y no saltarte revisiones',
  palabras: ['mantenimientos', 'mantenimiento preventivo', 'servicio de equipo', 'revisiones técnicas', 'calendario de mantenimiento'],
  seccion: {
    titulo: 'Mantenimientos', icono: 'equipo', vista: 'vencimientos',
    opciones: { fecha: 'programado', titulo: 'equipo', detalle: 'tipo', dias: 30, estado: 'estado', excluir: ['Hecho', 'Cancelado'] },
    campos: [
      { id: 'equipo', nombre: 'Equipo', tipo: 'texto', ejemplos: ['Aire acondicionado', 'Camioneta reparto', 'Computadora caja', 'Horno industrial', 'Elevador'] },
      { id: 'tipo', nombre: 'Tipo', tipo: 'texto', ejemplos: ['Preventivo', 'Correctivo', 'Calibración', 'Limpieza profunda', 'Revisión anual'] },
      { id: 'proveedor', nombre: 'Proveedor', tipo: 'texto' },
      { id: 'costo', nombre: 'Costo', tipo: 'dinero', rango: [200, 25000] },
      { id: 'programado', nombre: 'Programado', tipo: 'fecha', rango: [-20, 90] },
      { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Programado', 'En curso', 'Hecho', 'Atrasado', 'Cancelado'] },
    ],
  },
  piezas: [
    { vista: 'vencimientos', opciones: { fecha: 'programado', titulo: 'equipo', detalle: 'tipo', dias: 30, estado: 'estado', excluir: ['Hecho', 'Cancelado'] }, ancho: 8, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'columnas', fecha: 'programado', valor: 'costo', funcion: 'suma', agrupar: 'mes' }, ancho: 4, alto: 2 },
    { vista: 'kpis', opciones: { por: 'estado', suma: 'costo', vencen: 'programado', dias: 7, estado: 'estado', excluir: ['Hecho', 'Cancelado'] }, ancho: 12 },
  ],
}
