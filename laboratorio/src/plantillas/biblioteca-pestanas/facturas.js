export default {
  id: 'facturas',
  para: 'Llevar las facturas que emites, lo que falta por cobrar y las fechas límite de pago',
  palabras: ['facturas', 'facturación', 'cfdi pendientes', 'facturas por cobrar', 'mis facturas'],
  seccion: {
    titulo: 'Facturas', icono: 'documento', vista: 'vencimientos',
    opciones: { fecha: 'vence', titulo: 'cliente', detalle: 'folio', dias: 30, estado: 'estado', excluir: ['Pagada', 'Cancelada'] },
    campos: [
      { id: 'cliente', nombre: 'Cliente', tipo: 'texto' },
      { id: 'folio', nombre: 'Folio', tipo: 'texto', ejemplos: ['A-1042', 'FAC-2024-089', 'B-5501', 'E-220', 'Nota 15'] },
      { id: 'monto', nombre: 'Monto', tipo: 'dinero', rango: [350, 95000] },
      { id: 'emitida', nombre: 'Emitida', tipo: 'fecha', rango: [-120, 0] },
      { id: 'vence', nombre: 'Vence', tipo: 'fecha', rango: [-25, 45] },
      { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Borrador', 'Timbrada', 'Enviada', 'Pagada parcial', 'Pagada', 'Cancelada'] },
    ],
  },
  piezas: [
    { vista: 'kpis', opciones: { por: 'estado', suma: 'monto', vencen: 'vence', dias: 7, estado: 'estado', excluir: ['Pagada', 'Cancelada'] }, ancho: 12 },
    { vista: 'vencimientos', opciones: { fecha: 'vence', titulo: 'cliente', detalle: 'monto', dias: 30, estado: 'estado', excluir: ['Pagada', 'Cancelada'] }, ancho: 8, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'columnas', fecha: 'emitida', valor: 'monto', funcion: 'suma', agrupar: 'mes' }, ancho: 4, alto: 2 },
  ],
}
