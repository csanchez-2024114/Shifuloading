export default {
  id: 'entregas',
  para: 'Seguir cada entrega o envío: quién recibe, cuándo sale y si ya llegó a destino',
  palabras: ['entregas', 'envíos', 'reparto', 'paquetería', 'ruta de entrega'],
  seccion: {
    titulo: 'Entregas', icono: 'camion', vista: 'tablero',
    opciones: { por: 'estado', titulo: 'cliente', detalle: 'direccion' },
    campos: [
      { id: 'cliente', nombre: 'Cliente', tipo: 'texto' },
      { id: 'direccion', nombre: 'Dirección', tipo: 'texto', ejemplos: ['Col. Centro #45', 'Bodega industrial', 'Sucursal sur', 'Domicilio particular', 'Punto de recolección'] },
      { id: 'guia', nombre: 'Guía', tipo: 'texto', ejemplos: ['DHL-88221', 'Ruta 15', 'Mensajería local', 'Sin guía', 'Pickup tienda'] },
      { id: 'programada', nombre: 'Programada', tipo: 'fecha', rango: [-15, 20] },
      { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Por surtir', 'En ruta', 'Intento fallido', 'Entregada', 'Devuelta', 'Cancelada'] },
    ],
  },
  piezas: [
    { vista: 'tablero', opciones: { por: 'estado', titulo: 'cliente', detalle: 'programada' }, ancho: 8, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'embudo', estado: 'estado', funcion: 'conteo' }, ancho: 4, alto: 2 },
    { vista: 'agenda', opciones: { fecha: 'programada', titulo: 'cliente', detalle: 'direccion' }, ancho: 12, alto: 2 },
  ],
}
