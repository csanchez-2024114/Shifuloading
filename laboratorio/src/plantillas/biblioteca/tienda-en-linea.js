const fijas = [
  { id: 'actividad', titulo: 'Historial', grupo: 1, icono: 'actividad', vista: 'feed' },
  { id: 'equipo', titulo: 'Equipo', grupo: 1, icono: 'equipo', vista: 'equipo' },
  { id: 'automatizaciones', titulo: 'Automatizaciones', grupo: 2, icono: 'rayo', vista: 'interruptores' },
]

export default {
  id: 'tienda-en-linea',
  nombre: 'Tienda en línea',
  para: 'Tiendas online y e-commerce: pedidos por preparar, envíos en ruta y devoluciones',
  asignacion: {
    rubros: ['comercio', 'tecnologia'],
    ciclos: ['rapida', 'mezcla'],
    objetivos: ['seguimientos', 'reportes', 'integraciones', 'contactos'],
    negocios: ['Tienda de ropa online', 'Marketplace de productos locales', 'Tienda de electrónicos', 'Boutique con envíos a domicilio'],
  },
  // Tablero de pedidos y entregas del día arriba; ventas en el tiempo y motivos de devolución abajo.
  inicio: [
    { vista: 'tablero', seccion: 'pedidos', opciones: { por: 'estado', titulo: 'pedido', detalle: 'cliente' }, ancho: 8, alto: 3 },
    { vista: 'vencimientos', seccion: 'envios', opciones: { fecha: 'entrega', titulo: 'pedido', detalle: 'destino', dias: 7, estado: 'estado', excluir: ['Entregado', 'Devuelto'] }, ancho: 4, alto: 3 },
    { vista: 'grafico', seccion: 'pedidos', opciones: { tipo: 'linea-area', fecha: 'fecha', valor: 'total', funcion: 'suma' }, ancho: 8, alto: 2 },
    { vista: 'grafico', seccion: 'devoluciones', opciones: { tipo: 'pastel', agrupar: 'motivo' }, ancho: 4, alto: 2 },
  ],
  secciones: [
    { id: 'pedidos', titulo: 'Pedidos', grupo: 0, icono: 'caja', vista: 'tablero', opciones: { por: 'estado', titulo: 'pedido', detalle: 'cliente' },
      campos: [
        { id: 'pedido', nombre: 'Pedido', tipo: 'texto', ejemplos: ['PED-1042', 'PED-1043', 'PED-1044', 'PED-1045', 'PED-1046', 'PED-1047'] },
        { id: 'cliente', nombre: 'Cliente', tipo: 'texto' },
        { id: 'producto', nombre: 'Producto', tipo: 'texto', ejemplos: ['Camisa linen M', 'Auriculares BT', 'Zapatillas 40', 'Set cocina 5 pzs', 'Mochila urbana', 'Lámpara LED'] },
        { id: 'total', nombre: 'Total', tipo: 'dinero', rango: [15, 450] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Nuevo', 'Pagado', 'Preparando', 'Enviado', 'Entregado', 'Cancelado'] },
        { id: 'fecha', nombre: 'Fecha', tipo: 'fecha', rango: [-120, 1] },
      ] },
    { id: 'envios', titulo: 'Envíos', grupo: 0, icono: 'camion', vista: 'vencimientos', opciones: { fecha: 'entrega', titulo: 'pedido', detalle: 'destino', dias: 10, estado: 'estado', excluir: ['Entregado', 'Devuelto'] },
      campos: [
        { id: 'pedido', nombre: 'Pedido', tipo: 'texto', ejemplos: ['PED-1042', 'PED-1043', 'PED-1044', 'PED-1045', 'PED-1046', 'PED-1047'] },
        { id: 'destino', nombre: 'Destino', tipo: 'texto', ejemplos: ['Zona 10', 'Mixco', 'Antigua', 'Quetzaltenango', 'Escuintla', 'Villa Nueva'] },
        { id: 'paqueteria', nombre: 'Paquetería', tipo: 'texto', ejemplos: ['Cargo Express', 'Forza', 'Guatex', 'Propio', 'Uber Connect', 'Motorizado'] },
        { id: 'entrega', nombre: 'Entrega', tipo: 'fecha', rango: [-3, 12] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Por recoger', 'En tránsito', 'En ruta', 'Entregado', 'Devuelto'] },
      ] },
    { id: 'devoluciones', titulo: 'Devoluciones', grupo: 0, icono: 'reloj', vista: 'tabla',
      campos: [
        { id: 'pedido', nombre: 'Pedido', tipo: 'texto', ejemplos: ['PED-1038', 'PED-1039', 'PED-1040', 'PED-1041', 'PED-1035', 'PED-1036'] },
        { id: 'motivo', nombre: 'Motivo', tipo: 'texto', ejemplos: ['Talla incorrecta', 'Producto dañado', 'No es lo esperado', 'Llegó tarde', 'Color distinto', 'Defecto de fábrica'] },
        { id: 'monto', nombre: 'Monto', tipo: 'dinero', rango: [15, 350] },
        { id: 'fecha', nombre: 'Fecha', tipo: 'fecha', rango: [-20, 2] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Solicitada', 'En revisión', 'Aprobada', 'Reembolso', 'Rechazada'] },
      ] },
    ...fijas,
  ],
}
