export default {
  id: 'campanas',
  para: 'Planear campañas de marketing, presupuesto y resultados que vas midiendo',
  palabras: ['campañas', 'marketing', 'promoción en redes', 'campaña publicitaria', 'lanzamientos'],
  seccion: {
    titulo: 'Campañas', icono: 'rayo', vista: 'tablero',
    opciones: { por: 'estado', titulo: 'nombre', detalle: 'canal' },
    campos: [
      { id: 'nombre', nombre: 'Nombre', tipo: 'texto', ejemplos: ['Buen fin', 'Día de las madres', 'Apertura sucursal', 'Descuento verano', 'Referidos marzo'] },
      { id: 'canal', nombre: 'Canal', tipo: 'texto', ejemplos: ['Facebook Ads', 'Google', 'Email', 'WhatsApp', 'Volantes', 'Influencers'] },
      { id: 'presupuesto', nombre: 'Presupuesto', tipo: 'dinero', rango: [1500, 80000] },
      { id: 'inicio', nombre: 'Inicio', tipo: 'fecha', rango: [-90, 30] },
      { id: 'fin', nombre: 'Fin', tipo: 'fecha', rango: [-60, 60] },
      { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Idea', 'Planeada', 'Activa', 'Pausada', 'Finalizada', 'Cancelada'] },
    ],
  },
  piezas: [
    { vista: 'tablero', opciones: { por: 'estado', titulo: 'nombre', detalle: 'presupuesto' }, ancho: 8, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'columnas-100', estado: 'estado', fecha: 'inicio', funcion: 'conteo', meses: 6 }, ancho: 4, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'burbujas', estado: 'canal', valor: 'presupuesto', funcion: 'suma' }, ancho: 6, alto: 2 },
  ],
}
