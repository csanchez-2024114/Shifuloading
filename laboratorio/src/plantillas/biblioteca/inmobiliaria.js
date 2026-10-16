const fijas = [
  { id: 'actividad', titulo: 'Historial', grupo: 1, icono: 'actividad', vista: 'feed' },
  { id: 'equipo', titulo: 'Equipo', grupo: 1, icono: 'equipo', vista: 'equipo' },
  { id: 'automatizaciones', titulo: 'Automatizaciones', grupo: 2, icono: 'rayo', vista: 'interruptores' },
]

export default {
  id: 'inmobiliaria',
  nombre: 'Inmobiliaria',
  para: 'Agencias inmobiliarias: catálogo de propiedades, visitas agendadas y prospectos en seguimiento',
  asignacion: {
    rubros: ['inmobiliaria', 'servicios'],
    ciclos: ['cotizacion', 'mezcla'],
    objetivos: ['seguimientos', 'contactos', 'cotizaciones', 'reportes'],
    negocios: ['Agencia de casas y departamentos', 'Corredor de terrenos', 'Desarrolladora con inventario', 'Rentas vacacionales'],
  },
  // El agente prioriza inventario en venta, visitas de la semana y el embudo de prospectos antes que totales sueltos.
  inicio: [
    { vista: 'kpis', seccion: 'prospectos', opciones: { por: 'etapa' }, ancho: 12 },
    { vista: 'tablero', seccion: 'propiedades', opciones: { por: 'estado', titulo: 'propiedad', detalle: 'ubicacion' }, ancho: 8, alto: 2 },
    { vista: 'grafico', seccion: 'propiedades', opciones: { tipo: 'embudo' }, ancho: 4, alto: 2 },
    { vista: 'agenda', seccion: 'visitas', opciones: { fecha: 'fecha', hora: 'hora', titulo: 'propiedad', detalle: 'prospecto', dias: 7 }, ancho: 6, alto: 2 },
    { vista: 'grafico', seccion: 'prospectos', opciones: { tipo: 'barras', agrupar: 'interes', valor: 'presupuesto', funcion: 'suma' }, ancho: 6, alto: 2 },
  ],
  secciones: [
    { id: 'propiedades', titulo: 'Propiedades', grupo: 0, icono: 'tabla', vista: 'tabla',
      campos: [
        { id: 'propiedad', nombre: 'Propiedad', tipo: 'texto', ejemplos: ['Casa en Condominio Vista Real', 'Depto. 2 hab. Zona 14', 'Terreno 500 m² Carretera', 'Local comercial Centro', 'Bodega industrial', 'Casa de playa'] },
        { id: 'tipo', nombre: 'Tipo', tipo: 'estado', opciones: ['Casa', 'Departamento', 'Terreno', 'Local', 'Bodega', 'Otro'] },
        { id: 'operacion', nombre: 'Operación', tipo: 'estado', opciones: ['Venta', 'Renta', 'Renta vacacional'] },
        { id: 'precio', nombre: 'Precio', tipo: 'dinero', rango: [350000, 4500000] },
        { id: 'ubicacion', nombre: 'Ubicación', tipo: 'texto', ejemplos: ['Zona 10', 'Antigua Guatemala', 'Fraijanes', 'Mixco', 'Puerto San José', 'Carretera a El Salvador'] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Disponible', 'Reservada', 'En negociación', 'Vendida', 'Rentada'] },
      ] },
    { id: 'visitas', titulo: 'Visitas', grupo: 0, icono: 'calendario', vista: 'agenda', opciones: { fecha: 'fecha', hora: 'hora', titulo: 'propiedad', detalle: 'prospecto', dias: 14 },
      campos: [
        { id: 'propiedad', nombre: 'Propiedad', tipo: 'texto', ejemplos: ['Casa en Condominio Vista Real', 'Depto. 2 hab. Zona 14', 'Terreno 500 m² Carretera', 'Local comercial Centro', 'Bodega industrial', 'Casa de playa'] },
        { id: 'prospecto', nombre: 'Prospecto', tipo: 'texto', ejemplos: ['Elena Torres', 'Miguel Sandoval', 'Patricia Ríos', 'Fernando Aguilar', 'Gabriela León', 'Ricardo Méndez'] },
        { id: 'fecha', nombre: 'Fecha', tipo: 'fecha', rango: [-3, 21] },
        { id: 'hora', nombre: 'Hora', tipo: 'hora' },
        { id: 'agente', nombre: 'Agente', tipo: 'texto', ejemplos: ['Roberto L.', 'Sofía M.', 'Jorge H.', 'Lucía P.', 'Andrés C.', 'Valeria N.'] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Agendada', 'Confirmada', 'Realizada', 'Reprogramada', 'Cancelada'] },
      ] },
    { id: 'prospectos', titulo: 'Prospectos', grupo: 0, icono: 'usuarios', vista: 'tablero', opciones: { por: 'etapa', titulo: 'nombre', detalle: 'interes' },
      campos: [
        { id: 'nombre', nombre: 'Nombre', tipo: 'texto' },
        { id: 'telefono', nombre: 'Teléfono', tipo: 'texto' },
        { id: 'interes', nombre: 'Interés', tipo: 'texto', ejemplos: ['Casa familiar 3 hab.', 'Depto. cerca del trabajo', 'Terreno para construir', 'Local para negocio', 'Renta anual', 'Inversión'] },
        { id: 'presupuesto', nombre: 'Presupuesto', tipo: 'dinero', rango: [400000, 3500000] },
        { id: 'etapa', nombre: 'Etapa', tipo: 'estado', opciones: ['Nuevo', 'Contactado', 'Visitó', 'Negociación', 'Cierre', 'Perdido'] },
        { id: 'proximo', nombre: 'Próximo contacto', tipo: 'fecha', rango: [-7, 30] },
      ] },
    ...fijas,
  ],
}
