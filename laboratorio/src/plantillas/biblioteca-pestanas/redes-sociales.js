export default {
  id: 'redes-sociales',
  para: 'Organizar publicaciones en redes, fechas de salida y qué contenido ya salió',
  palabras: ['redes sociales', 'publicaciones', 'contenido digital', 'calendario de posts', 'instagram y facebook'],
  seccion: {
    titulo: 'Redes sociales', icono: 'actividad', vista: 'agenda',
    opciones: { fecha: 'fecha', hora: 'hora', titulo: 'titulo', detalle: 'red' },
    campos: [
      { id: 'titulo', nombre: 'Título', tipo: 'texto', ejemplos: ['Oferta fin de semana', 'Tips del producto', 'Testimonio cliente', 'Reel behind scenes', 'Sorteo mes'] },
      { id: 'red', nombre: 'Red', tipo: 'estado', opciones: ['Facebook', 'Instagram', 'TikTok', 'LinkedIn', 'YouTube'] },
      { id: 'fecha', nombre: 'Fecha', tipo: 'fecha', rango: [-30, 45] },
      { id: 'hora', nombre: 'Hora', tipo: 'hora' },
      { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Borrador', 'Programado', 'Publicado', 'Fallido', 'Archivado'] },
    ],
  },
  piezas: [
    { vista: 'agenda', opciones: { fecha: 'fecha', hora: 'hora', titulo: 'titulo', detalle: 'red' }, ancho: 8, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'columnas-apiladas', estado: 'estado', fecha: 'fecha', funcion: 'conteo', meses: 3 }, ancho: 4, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'barras', estado: 'red', funcion: 'conteo' }, ancho: 6, alto: 2 },
  ],
}
