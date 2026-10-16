export default {
  id: 'devoluciones',
  para: 'Gestionar devoluciones y cambios que piden tus clientes y el estado de cada solicitud',
  palabras: ['devoluciones', 'cambios de producto', 'nota de crédito', 'cliente quiere devolver', 'reembolsos'],
  seccion: {
    titulo: 'Devoluciones', icono: 'camion', vista: 'tablero',
    opciones: { por: 'estado', titulo: 'cliente', detalle: 'motivo' },
    campos: [
      { id: 'cliente', nombre: 'Cliente', tipo: 'texto' },
      { id: 'producto', nombre: 'Producto', tipo: 'texto', ejemplos: ['Playera talla L', 'Mouse inalámbrico', 'Crema facial', 'Zapatos número 8', 'Kit herramientas'] },
      { id: 'motivo', nombre: 'Motivo', tipo: 'texto', ejemplos: ['Talla incorrecta', 'Llegó dañado', 'No era lo esperado', 'Error de pedido', 'Garantía'] },
      { id: 'monto', nombre: 'Monto', tipo: 'dinero', rango: [80, 12000] },
      { id: 'solicitud', nombre: 'Solicitud', tipo: 'fecha', rango: [-60, 10] },
      { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Solicitada', 'Autorizada', 'En tránsito', 'Recibida', 'Reembolsada', 'Rechazada'] },
    ],
  },
  piezas: [
    { vista: 'tablero', opciones: { por: 'estado', titulo: 'cliente', detalle: 'monto' }, ancho: 8, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'linea-tendencia', fecha: 'solicitud', valor: 'monto', funcion: 'suma' }, ancho: 4, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'barras-apiladas', estado: 'estado', fecha: 'solicitud', funcion: 'conteo', meses: 6 }, ancho: 12, alto: 2 },
  ],
}
