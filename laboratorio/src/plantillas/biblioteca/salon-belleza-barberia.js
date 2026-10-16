const fijas = [
  { id: 'actividad', titulo: 'Historial', grupo: 1, icono: 'actividad', vista: 'feed' },
  { id: 'equipo', titulo: 'Equipo', grupo: 1, icono: 'equipo', vista: 'equipo' },
  { id: 'automatizaciones', titulo: 'Automatizaciones', grupo: 2, icono: 'rayo', vista: 'interruptores' },
]

export default {
  id: 'salon-belleza-barberia',
  nombre: 'Salón y barbería',
  para: 'Salones de belleza y barberías: agenda del día, servicios y clientas que regresan',
  asignacion: {
    rubros: ['servicios', 'comercio'],
    ciclos: ['rapida', 'recurrente'],
    objetivos: ['seguimientos', 'contactos', 'reportes', 'equipo'],
    negocios: ['Barbería de barrio', 'Salón de uñas y pestañas', 'Spa urbano con citas', 'Peluquería unisex'],
  },
  inicio: [
    { vista: 'kpis', seccion: 'citas', opciones: { por: 'estado', hoy: 'fecha', suma: 'precio' }, ancho: 12 },
    { vista: 'agenda', seccion: 'citas', opciones: { fecha: 'fecha', hora: 'hora', titulo: 'cliente', detalle: 'servicio', dias: 7 }, ancho: 12, alto: 2 },
    { vista: 'grafico', seccion: 'citas', opciones: { tipo: 'calendario' }, ancho: 6, alto: 2 },
    { vista: 'grafico', seccion: 'servicios', opciones: { tipo: 'pastel' }, ancho: 6, alto: 2 },
  ],
  secciones: [
    { id: 'citas', titulo: 'Agenda de citas', grupo: 0, icono: 'calendario', vista: 'agenda', opciones: { fecha: 'fecha', hora: 'hora', titulo: 'cliente', detalle: 'servicio', dias: 14 },
      campos: [
        { id: 'cliente', nombre: 'Cliente', tipo: 'texto' },
        { id: 'servicio', nombre: 'Servicio', tipo: 'texto', ejemplos: ['Corte caballero', 'Tinte completo', 'Manicure gel', 'Barba y contorno', 'Alisado', 'Peinado evento'] },
        { id: 'estilista', nombre: 'Estilista', tipo: 'texto', ejemplos: ['Ana R.', 'Luis M.', 'Karla S.', 'Diego P.', 'María V.', 'Roberto L.'] },
        { id: 'fecha', nombre: 'Fecha', tipo: 'fecha', rango: [-60, 30] },
        { id: 'hora', nombre: 'Hora', tipo: 'hora' },
        { id: 'precio', nombre: 'Precio', tipo: 'dinero', rango: [80, 1200] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Por confirmar', 'Confirmada', 'En silla', 'Terminada', 'No llegó'] },
      ] },
    { id: 'servicios', titulo: 'Servicios', grupo: 0, icono: 'tabla', vista: 'tabla',
      campos: [
        { id: 'servicio', nombre: 'Servicio', tipo: 'texto', ejemplos: ['Corte dama', 'Corte caballero', 'Tinte raíz', 'Depilación ceja', 'Pedicure spa', 'Tratamiento keratina'] },
        { id: 'categoria', nombre: 'Categoría', tipo: 'estado', opciones: ['Corte', 'Color', 'Uñas', 'Barba', 'Tratamiento', 'Evento'] },
        { id: 'duracion', nombre: 'Duración (min)', tipo: 'numero', rango: [15, 180] },
        { id: 'precio', nombre: 'Precio', tipo: 'dinero', rango: [60, 2500] },
        { id: 'activo', nombre: 'Disponible', tipo: 'estado', opciones: ['Sí', 'Temporalmente no', 'Retirado'] },
      ] },
    { id: 'clientes', titulo: 'Clientes', grupo: 0, icono: 'usuarios', vista: 'tabla',
      campos: [
        { id: 'nombre', nombre: 'Nombre', tipo: 'texto' },
        { id: 'telefono', nombre: 'Teléfono', tipo: 'texto' },
        { id: 'ultima', nombre: 'Última visita', tipo: 'fecha', rango: [-180, 0] },
        { id: 'frecuencia', nombre: 'Frecuencia', tipo: 'estado', opciones: ['Nueva', 'Cada mes', 'Esporádica', 'Inactiva'] },
        { id: 'preferencia', nombre: 'Preferencia', tipo: 'texto', ejemplos: ['Sin amoníaco', 'Solo con Ana', 'Corte bajo fade', 'Uñas cortas', 'Recordar cumpleaños', 'Pago transferencia'] },
      ] },
    ...fijas,
  ],
}
