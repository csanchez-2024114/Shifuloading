const fijas = [
  { id: 'actividad', titulo: 'Historial', grupo: 1, icono: 'actividad', vista: 'feed' },
  { id: 'equipo', titulo: 'Equipo', grupo: 1, icono: 'equipo', vista: 'equipo' },
  { id: 'automatizaciones', titulo: 'Automatizaciones', grupo: 2, icono: 'rayo', vista: 'interruptores' },
]

export default {
  id: 'restaurante',
  nombre: 'Restaurante',
  para: 'Restaurantes y cocinas: pedidos a domicilio, reservas de mesa y clientes frecuentes',
  asignacion: {
    rubros: ['comercio', 'servicios'],
    ciclos: ['rapida', 'recurrente', 'mezcla'],
    objetivos: ['seguimientos', 'contactos', 'reportes'],
    negocios: ['Restaurante de comida corrida', 'Pizzería con delivery', 'Cafetería con reservas', 'Marisquería a domicilio'],
  },
  // Cocina y salón en paralelo: pedidos en curso a la izquierda, mesas reservadas a la derecha; abajo ventas por platillo y clientes nuevos.
  inicio: [
    { vista: 'kpis', seccion: 'pedidos', opciones: { por: 'estado', suma: 'total', hoy: 'entrega' }, ancho: 12 },
    { vista: 'tablero', seccion: 'pedidos', opciones: { por: 'estado', titulo: 'cliente', detalle: 'platillo' }, ancho: 8, alto: 2 },
    { vista: 'agenda', seccion: 'reservas', opciones: { fecha: 'fecha', hora: 'hora', titulo: 'cliente', detalle: 'personas', dias: 7 }, ancho: 4, alto: 2 },
    { vista: 'grafico', seccion: 'pedidos', opciones: { tipo: 'barras', agrupar: 'platillo', valor: 'total', funcion: 'suma' }, ancho: 6, alto: 2 },
    { vista: 'grafico', seccion: 'clientes', opciones: { tipo: 'linea-area' }, ancho: 6, alto: 2 },
  ],
  secciones: [
    { id: 'pedidos', titulo: 'Pedidos a domicilio', grupo: 0, icono: 'caja', vista: 'tablero', opciones: { por: 'estado', titulo: 'cliente', detalle: 'platillo' },
      campos: [
        { id: 'cliente', nombre: 'Cliente', tipo: 'texto' },
        { id: 'platillo', nombre: 'Platillo', tipo: 'texto', ejemplos: ['Pizza familiar', 'Enchiladas verdes', 'Parrillada mixta', 'Pasta alfredo', 'Tacos al pastor', 'Sopa de mariscos'] },
        { id: 'direccion', nombre: 'Dirección', tipo: 'texto', ejemplos: ['Colonia Centro #12', 'Zona 4 torre B', 'Residencial Las Flores', 'Av. Reforma 45', 'Condado Naranjo', 'Carretera a El Salvador km 8'] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Recibido', 'En cocina', 'En camino', 'Entregado', 'Cancelado'] },
        { id: 'entrega', nombre: 'Entrega', tipo: 'fecha', rango: [-1, 2] },
        { id: 'total', nombre: 'Total', tipo: 'dinero', rango: [80, 850] },
      ] },
    { id: 'reservas', titulo: 'Reservas', grupo: 0, icono: 'calendario', vista: 'agenda', opciones: { fecha: 'fecha', hora: 'hora', titulo: 'cliente', detalle: 'personas', dias: 14 },
      campos: [
        { id: 'cliente', nombre: 'Cliente', tipo: 'texto' },
        { id: 'fecha', nombre: 'Fecha', tipo: 'fecha', rango: [0, 21] },
        { id: 'hora', nombre: 'Hora', tipo: 'hora' },
        { id: 'personas', nombre: 'Personas', tipo: 'numero', rango: [2, 12] },
        { id: 'mesa', nombre: 'Mesa', tipo: 'texto', ejemplos: ['Terraza 3', 'Salón 5', 'Barra 2', 'Privado A', 'Jardín 1', 'Ventana 4'] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Por confirmar', 'Confirmada', 'En mesa', 'Finalizada', 'No llegó'] },
      ] },
    { id: 'clientes', titulo: 'Clientes', grupo: 0, icono: 'usuarios', vista: 'tabla',
      campos: [
        { id: 'nombre', nombre: 'Nombre', tipo: 'texto' },
        { id: 'telefono', nombre: 'Teléfono', tipo: 'texto' },
        { id: 'preferencia', nombre: 'Preferencia', tipo: 'texto', ejemplos: ['Sin picante', 'Vegetariano', 'Sin gluten', 'Extra queso', 'Para llevar frecuente', 'Celebraciones'] },
        { id: 'tipo', nombre: 'Tipo', tipo: 'estado', opciones: ['Nuevo', 'Frecuente', 'Corporativo'] },
        { id: 'alta', nombre: 'Alta', tipo: 'fecha', rango: [-365, 0] },
      ] },
    ...fijas,
  ],
}
