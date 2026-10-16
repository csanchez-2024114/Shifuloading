export default {
  id: 'quejas-y-soporte',
  para: 'Atender quejas y tickets de soporte hasta resolverlas y medir tiempos de respuesta',
  palabras: ['quejas', 'soporte', 'tickets', 'reclamos de clientes', 'mesa de ayuda'],
  seccion: {
    titulo: 'Quejas y soporte', icono: 'rayo', vista: 'tablero',
    opciones: { por: 'estado', titulo: 'cliente', detalle: 'asunto' },
    campos: [
      { id: 'cliente', nombre: 'Cliente', tipo: 'texto' },
      { id: 'asunto', nombre: 'Asunto', tipo: 'texto', ejemplos: ['Producto defectuoso', 'Cobro duplicado', 'Demora en entrega', 'Garantía no aplicada', 'Mal trato en tienda'] },
      { id: 'prioridad', nombre: 'Prioridad', tipo: 'estado', opciones: ['Baja', 'Media', 'Alta', 'Crítica'] },
      { id: 'abierto', nombre: 'Abierto', tipo: 'fecha', rango: [-90, 0] },
      { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Nuevo', 'En análisis', 'En proceso', 'Esperando cliente', 'Resuelto', 'Cerrado'] },
    ],
  },
  piezas: [
    { vista: 'tablero', opciones: { por: 'estado', titulo: 'cliente', detalle: 'asunto' }, ancho: 8, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'columnas-apiladas', estado: 'estado', fecha: 'abierto', funcion: 'conteo', meses: 6 }, ancho: 4, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'radar', estado: 'prioridad', funcion: 'conteo' }, ancho: 6, alto: 2 },
  ],
}
