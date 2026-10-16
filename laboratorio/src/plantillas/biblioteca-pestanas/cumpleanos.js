export default {
  id: 'cumpleanos',
  para: 'Llevar cumpleaños de clientes y colaboradores para felicitarlos y fidelizar',
  palabras: ['cumpleaños', 'fechas de cumple', 'felicitar clientes', 'aniversarios personales', 'quién cumple este mes'],
  seccion: {
    titulo: 'Cumpleaños', icono: 'calendario', vista: 'agenda',
    opciones: { fecha: 'fecha', titulo: 'nombre', detalle: 'tipo' },
    campos: [
      { id: 'nombre', nombre: 'Nombre', tipo: 'texto' },
      { id: 'tipo', nombre: 'Tipo', tipo: 'estado', opciones: ['Cliente', 'Colaborador', 'Proveedor', 'Socio'] },
      { id: 'fecha', nombre: 'Fecha', tipo: 'fecha', rango: [-180, 180] },
      { id: 'nota', nombre: 'Nota', tipo: 'texto', ejemplos: ['Enviar promoción', 'Llamar por la mañana', 'Tarjeta en mostrador', 'Regalo corporativo', 'Mensaje WhatsApp'] },
    ],
  },
  piezas: [
    { vista: 'agenda', opciones: { fecha: 'fecha', titulo: 'nombre', detalle: 'tipo' }, ancho: 8, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'calendario', fecha: 'fecha', funcion: 'conteo' }, ancho: 4, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'barra-100', estado: 'tipo', funcion: 'conteo' }, ancho: 6, alto: 2 },
  ],
}
