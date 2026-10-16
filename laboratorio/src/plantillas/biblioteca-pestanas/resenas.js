export default {
  id: 'resenas',
  para: 'Recopilar reseñas y calificaciones de clientes para mejorar servicio y reputación',
  palabras: ['reseñas', 'opiniones de clientes', 'calificaciones', 'estrellas en google', 'qué dicen de nosotros'],
  seccion: {
    titulo: 'Reseñas', icono: 'actividad', vista: 'tabla',
    campos: [
      { id: 'cliente', nombre: 'Cliente', tipo: 'texto' },
      { id: 'canal', nombre: 'Canal', tipo: 'texto', ejemplos: ['Google', 'Facebook', 'WhatsApp', 'En tienda', 'TripAdvisor', 'Mercado Libre'] },
      { id: 'calificacion', nombre: 'Calificación', tipo: 'numero', rango: [1, 5] },
      { id: 'comentario', nombre: 'Comentario', tipo: 'texto', ejemplos: ['Excelente atención', 'Llegó tarde el pedido', 'Muy recomendable', 'Precios justos', 'Volvería a comprar'] },
      { id: 'fecha', nombre: 'Fecha', tipo: 'fecha', rango: [-120, 5] },
      { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Nueva', 'Leída', 'Respondida', 'En seguimiento', 'Cerrada'] },
    ],
  },
  piezas: [
    { vista: 'tabla', opciones: { orden: 'fecha' }, ancho: 8, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'histograma', valor: 'calificacion', funcion: 'conteo' }, ancho: 4, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'barras', estado: 'canal', valor: 'calificacion', funcion: 'promedio' }, ancho: 6, alto: 2 },
  ],
}
