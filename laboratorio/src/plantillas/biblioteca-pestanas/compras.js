export default {
  id: 'compras',
  para: 'Ordenar compras a proveedores, montos y fechas esperadas de llegada a tu negocio',
  palabras: ['compras', 'órdenes de compra', 'pedidos a proveedor', 'abastecimiento', 'requisiciones'],
  seccion: {
    titulo: 'Compras', icono: 'caja', vista: 'tablero',
    opciones: { por: 'estado', titulo: 'proveedor', detalle: 'concepto' },
    campos: [
      { id: 'proveedor', nombre: 'Proveedor', tipo: 'texto' },
      { id: 'concepto', nombre: 'Concepto', tipo: 'texto', ejemplos: ['Insumos mensuales', 'Mercancía temporada', 'Refacciones urgentes', 'Empaques', 'Equipo nuevo'] },
      { id: 'monto', nombre: 'Monto', tipo: 'dinero', rango: [500, 85000] },
      { id: 'pedido', nombre: 'Fecha pedido', tipo: 'fecha', rango: [-90, 5] },
      { id: 'llegada', nombre: 'Llegada esperada', tipo: 'fecha', rango: [-10, 30] },
      { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Borrador', 'Enviada', 'Confirmada', 'En tránsito', 'Recibida', 'Cancelada'] },
    ],
  },
  piezas: [
    { vista: 'tablero', opciones: { por: 'estado', titulo: 'proveedor', detalle: 'monto' }, ancho: 8, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'columnas', fecha: 'pedido', valor: 'monto', funcion: 'suma', agrupar: 'mes' }, ancho: 4, alto: 2 },
    { vista: 'kpis', opciones: { por: 'estado', suma: 'monto', vencen: 'llegada', dias: 5, estado: 'estado', excluir: ['Recibida', 'Cancelada'] }, ancho: 12 },
  ],
}
