export default {
  id: 'pedidos',
  para: 'Controlar los pedidos de tus clientes desde que entran hasta que los entregas o cancelas',
  palabras: ['pedidos', 'órdenes de compra', 'ventas por surtir', 'qué pidieron', 'seguimiento de pedidos'],
  seccion: {
    titulo: 'Pedidos', icono: 'camion', vista: 'tablero',
    opciones: { por: 'estado', titulo: 'cliente', detalle: 'producto' },
    campos: [
      { id: 'cliente', nombre: 'Cliente', tipo: 'texto' },
      { id: 'producto', nombre: 'Producto', tipo: 'texto', ejemplos: ['Combo familiar', 'Servicio express', 'Kit promocional', 'Pedido mayoreo', 'Suscripción mensual'] },
      { id: 'total', nombre: 'Total', tipo: 'dinero', rango: [120, 18000] },
      { id: 'fecha', nombre: 'Fecha', tipo: 'fecha', rango: [-90, 10] },
      { id: 'entrega', nombre: 'Entrega', tipo: 'fecha', rango: [-20, 30] },
      { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Recibido', 'En preparación', 'Listo', 'En ruta', 'Entregado', 'Cancelado'] },
    ],
  },
  piezas: [
    { vista: 'tablero', opciones: { por: 'estado', titulo: 'cliente', detalle: 'total' }, ancho: 8, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'columnas-apiladas', estado: 'estado', fecha: 'fecha', funcion: 'conteo', meses: 6 }, ancho: 4, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'linea', fecha: 'fecha', valor: 'total', funcion: 'suma' }, ancho: 12, alto: 2 },
  ],
}
