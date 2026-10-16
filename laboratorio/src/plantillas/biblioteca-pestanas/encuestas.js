export default {
  id: 'encuestas',
  para: 'Lanzar encuestas a clientes y revisar respuestas y satisfacción por campaña',
  palabras: ['encuestas', 'satisfacción del cliente', 'nps', 'formularios de opinión', 'preguntas a clientes'],
  seccion: {
    titulo: 'Encuestas', icono: 'tabla', vista: 'tabla',
    campos: [
      { id: 'encuesta', nombre: 'Encuesta', tipo: 'texto', ejemplos: ['Post-compra', 'NPS trimestral', 'Evento inauguración', 'Servicio soporte', 'Calidad producto'] },
      { id: 'respondente', nombre: 'Respondente', tipo: 'texto', ejemplos: ['Cliente anónimo', 'María G.', 'Empresa XYZ', 'Encuesta mostrador', 'Email masivo'] },
      { id: 'puntaje', nombre: 'Puntaje', tipo: 'numero', rango: [0, 10] },
      { id: 'fecha', nombre: 'Fecha', tipo: 'fecha', rango: [-120, 5] },
      { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Enviada', 'Parcial', 'Completada', 'Analizada', 'Cerrada'] },
    ],
  },
  piezas: [
    { vista: 'tabla', opciones: { orden: 'fecha' }, ancho: 8, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'histograma', valor: 'puntaje', funcion: 'conteo' }, ancho: 4, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'linea-area', fecha: 'fecha', valor: 'puntaje', funcion: 'promedio' }, ancho: 6, alto: 2 },
  ],
}
