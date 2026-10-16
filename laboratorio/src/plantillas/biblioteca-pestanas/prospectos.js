export default {
  id: 'prospectos',
  para: 'Organizar posibles clientes, de dónde vienen y en qué etapa van antes de cerrar la venta',
  palabras: ['prospectos', 'leads', 'posibles clientes', 'pipeline de ventas', 'gente interesada'],
  seccion: {
    titulo: 'Prospectos', icono: 'usuarios', vista: 'tablero',
    opciones: { por: 'etapa', titulo: 'nombre', detalle: 'origen' },
    campos: [
      { id: 'nombre', nombre: 'Nombre', tipo: 'texto' },
      { id: 'empresa', nombre: 'Empresa', tipo: 'texto' },
      { id: 'origen', nombre: 'Origen', tipo: 'texto', ejemplos: ['Recomendación', 'Facebook', 'Feria local', 'Google', 'Llamada fría', 'WhatsApp'] },
      { id: 'valor', nombre: 'Valor estimado', tipo: 'dinero', rango: [1000, 120000] },
      { id: 'contacto', nombre: 'Último contacto', tipo: 'fecha', rango: [-90, 0] },
      { id: 'etapa', nombre: 'Etapa', tipo: 'estado', opciones: ['Nuevo', 'Contactado', 'Calificado', 'Propuesta', 'Negociación', 'Ganado', 'Perdido'] },
    ],
  },
  piezas: [
    { vista: 'tablero', opciones: { por: 'etapa', titulo: 'nombre', detalle: 'valor' }, ancho: 8, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'embudo', estado: 'etapa', funcion: 'conteo' }, ancho: 4, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'arbol', estado: 'origen', valor: 'valor', funcion: 'suma' }, ancho: 6, alto: 2 },
  ],
}
