export default {
  id: 'inventario',
  para: 'Saber qué productos tienes, cuánto queda en bodega y cuándo conviene reordenar',
  palabras: ['inventario', 'stock', 'productos en bodega', 'control de existencias', 'qué me queda'],
  seccion: {
    titulo: 'Inventario', icono: 'tabla', vista: 'tablero',
    opciones: { por: 'estado', titulo: 'producto', detalle: 'categoria' },
    campos: [
      { id: 'producto', nombre: 'Producto', tipo: 'texto', ejemplos: ['Aceite 20W50', 'Filtro de aire', 'Playera talla M', 'Cable HDMI 2m', 'Harina integral 1kg', 'Shampoo anticaspa'] },
      { id: 'categoria', nombre: 'Categoría', tipo: 'texto', ejemplos: ['Refacciones', 'Ropa', 'Abarrotes', 'Electrónica', 'Limpieza', 'Herramientas'] },
      { id: 'existencia', nombre: 'Existencia', tipo: 'numero', rango: [0, 500] },
      { id: 'costo', nombre: 'Costo unitario', tipo: 'dinero', rango: [15, 2500] },
      { id: 'minimo', nombre: 'Mínimo', tipo: 'numero', rango: [2, 50] },
      { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Disponible', 'Bajo stock', 'Por pedir', 'Agotado', 'Descontinuado'] },
    ],
  },
  piezas: [
    { vista: 'tablero', opciones: { por: 'estado', titulo: 'producto', detalle: 'existencia' }, ancho: 8, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'barras', estado: 'estado', funcion: 'conteo' }, ancho: 4, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'histograma', valor: 'existencia', funcion: 'conteo' }, ancho: 6, alto: 2 },
  ],
}
