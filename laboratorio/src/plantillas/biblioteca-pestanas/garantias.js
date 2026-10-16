export default {
  id: 'garantias',
  para: 'Registrar garantías de productos vendidos y dar seguimiento hasta cerrar cada caso',
  palabras: ['garantías', 'reclamar garantía', 'productos en garantía', 'vigencia de garantía', 'casos de garantía'],
  seccion: {
    titulo: 'Garantías', icono: 'documento', vista: 'vencimientos',
    opciones: { fecha: 'vence', titulo: 'cliente', detalle: 'producto', dias: 45, estado: 'estado', excluir: ['Cerrada', 'Rechazada'] },
    campos: [
      { id: 'cliente', nombre: 'Cliente', tipo: 'texto' },
      { id: 'producto', nombre: 'Producto', tipo: 'texto', ejemplos: ['Laptop 14"', 'Celular modelo X', 'Licuadora industrial', 'Colchón king', 'Aire acondicionado'] },
      { id: 'compra', nombre: 'Fecha compra', tipo: 'fecha', rango: [-365, -30] },
      { id: 'vence', nombre: 'Vence', tipo: 'fecha', rango: [-30, 180] },
      { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Vigente', 'En revisión', 'En taller', 'Aprobada', 'Cerrada', 'Rechazada'] },
    ],
  },
  piezas: [
    { vista: 'vencimientos', opciones: { fecha: 'vence', titulo: 'cliente', detalle: 'producto', dias: 45, estado: 'estado', excluir: ['Cerrada', 'Rechazada'] }, ancho: 8, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'pastel', estado: 'estado', funcion: 'conteo' }, ancho: 4, alto: 2 },
    { vista: 'kpis', opciones: { por: 'estado', vencen: 'vence', dias: 14, estado: 'estado', excluir: ['Cerrada', 'Rechazada'] }, ancho: 12 },
  ],
}
