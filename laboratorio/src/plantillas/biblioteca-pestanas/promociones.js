export default {
  id: 'promociones',
  para: 'Administrar promociones y descuentos activos, vigencia y cuánto han vendido',
  palabras: ['promociones', 'descuentos', 'ofertas', 'cupones', '2x1 y rebajas'],
  seccion: {
    titulo: 'Promociones', icono: 'rayo', vista: 'tablero',
    opciones: { por: 'estado', titulo: 'nombre', detalle: 'descuento' },
    campos: [
      { id: 'nombre', nombre: 'Nombre', tipo: 'texto', ejemplos: ['10% primer compra', '2x1 viernes', 'Envío gratis', 'Mes del niño', 'Cliente frecuente'] },
      { id: 'descuento', nombre: 'Descuento', tipo: 'texto', ejemplos: ['15%', '$100 pesos', 'Producto gratis', '3 meses sin interés', 'Mitad de precio'] },
      { id: 'ventas', nombre: 'Ventas con promo', tipo: 'dinero', rango: [0, 95000] },
      { id: 'desde', nombre: 'Desde', tipo: 'fecha', rango: [-60, 15] },
      { id: 'hasta', nombre: 'Hasta', tipo: 'fecha', rango: [-30, 60] },
      { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Borrador', 'Activa', 'Pausada', 'Agotada', 'Finalizada'] },
    ],
  },
  piezas: [
    { vista: 'tablero', opciones: { por: 'estado', titulo: 'nombre', detalle: 'ventas' }, ancho: 8, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'linea-tendencia', fecha: 'desde', valor: 'ventas', funcion: 'suma' }, ancho: 4, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'medidor', estado: 'estado' }, ancho: 4, alto: 2 },
  ],
}
