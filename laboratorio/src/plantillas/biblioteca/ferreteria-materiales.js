const fijas = [
  { id: 'actividad', titulo: 'Historial', grupo: 1, icono: 'actividad', vista: 'feed' },
  { id: 'equipo', titulo: 'Equipo', grupo: 1, icono: 'equipo', vista: 'equipo' },
  { id: 'automatizaciones', titulo: 'Automatizaciones', grupo: 2, icono: 'rayo', vista: 'interruptores' },
]

export default {
  id: 'ferreteria-materiales',
  nombre: 'Ferretería y materiales',
  para: 'Ferreterías y tiendas de materiales: ventas del día, stock bajo y créditos por cobrar',
  asignacion: {
    rubros: ['comercio'],
    ciclos: ['rapida', 'recurrente', 'mezcla'],
    objetivos: ['reportes', 'seguimientos', 'contactos'],
    negocios: ['Ferretería de barrio', 'Tienda de materiales de construcción', 'Distribuidora de pintura y herramientas', 'Depósito de cemento y agregados'],
  },
  // Mostrador: ventas del día, qué falta en anaquel y créditos que vencen esta semana.
  inicio: [
    { vista: 'kpis', seccion: 'ventas', opciones: { por: 'estado', suma: 'total', hoy: 'fecha' }, ancho: 12 },
    { vista: 'tablero', seccion: 'ventas', opciones: { por: 'estado', titulo: 'producto', detalle: 'cliente' }, ancho: 6, alto: 2 },
    { vista: 'grafico', seccion: 'inventario', opciones: { tipo: 'barras', agrupar: 'estado', valor: 'cantidad', funcion: 'suma' }, ancho: 6, alto: 2 },
    { vista: 'vencimientos', seccion: 'creditos', opciones: { fecha: 'vence', titulo: 'cliente', detalle: 'concepto', dias: 10, estado: 'estado', excluir: ['Pagado', 'Cancelado'] }, ancho: 8, alto: 2 },
    { vista: 'grafico', seccion: 'ventas', opciones: { tipo: 'linea', fecha: 'fecha', valor: 'total', funcion: 'suma' }, ancho: 4, alto: 2 },
  ],
  secciones: [
    { id: 'ventas', titulo: 'Ventas', grupo: 0, icono: 'tablero', vista: 'tablero', opciones: { por: 'estado', titulo: 'producto', detalle: 'cliente' },
      campos: [
        { id: 'producto', nombre: 'Producto', tipo: 'texto', ejemplos: ['Cemento gris 42.5', 'Varilla 3/8"', 'Pintura blanca 1 gal', 'Taladro percutor', 'Tubería PVC 1/2"', 'Block 15x20x40'] },
        { id: 'cliente', nombre: 'Cliente', tipo: 'texto' },
        { id: 'cantidad', nombre: 'Cantidad', tipo: 'numero', rango: [1, 80] },
        { id: 'total', nombre: 'Total', tipo: 'dinero', rango: [50, 8500] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Cotizada', 'Pagada', 'Crédito', 'Entregada', 'Cancelada'] },
        { id: 'fecha', nombre: 'Fecha', tipo: 'fecha', rango: [-120, 2] },
      ] },
    { id: 'inventario', titulo: 'Inventario', grupo: 0, icono: 'caja', vista: 'tabla',
      campos: [
        { id: 'producto', nombre: 'Producto', tipo: 'texto', ejemplos: ['Cemento gris 42.5', 'Arena de río', 'Pintura látex', 'Broca concreta', 'Cable THW 12', 'Llave stillson 14"'] },
        { id: 'cantidad', nombre: 'Cantidad', tipo: 'numero', rango: [0, 200] },
        { id: 'minimo', nombre: 'Mínimo', tipo: 'numero', rango: [5, 30] },
        { id: 'costo', nombre: 'Costo', tipo: 'dinero', rango: [5, 1500] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Disponible', 'Bajo', 'Agotado', 'Pedido'] },
      ] },
    { id: 'creditos', titulo: 'Créditos', grupo: 0, icono: 'tarjeta', vista: 'vencimientos', opciones: { fecha: 'vence', titulo: 'cliente', detalle: 'concepto', dias: 30, estado: 'estado', excluir: ['Pagado', 'Cancelado'] },
      campos: [
        { id: 'cliente', nombre: 'Cliente', tipo: 'texto' },
        { id: 'concepto', nombre: 'Concepto', tipo: 'texto', ejemplos: ['Material obra casa', 'Herramientas taller', 'Pintura local', 'Cemento remesa', 'Pedido constructor', 'Compra quincenal'] },
        { id: 'monto', nombre: 'Monto', tipo: 'dinero', rango: [200, 12000] },
        { id: 'vence', nombre: 'Vence', tipo: 'fecha', rango: [-10, 45] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Pendiente', 'Parcial', 'Vencido', 'Pagado', 'Cancelado'] },
      ] },
    ...fijas,
  ],
}
