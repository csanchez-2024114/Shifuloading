const fijas = [
  { id: 'actividad', titulo: 'Historial', grupo: 1, icono: 'actividad', vista: 'feed' },
  { id: 'equipo', titulo: 'Equipo', grupo: 1, icono: 'equipo', vista: 'equipo' },
  { id: 'automatizaciones', titulo: 'Automatizaciones', grupo: 2, icono: 'rayo', vista: 'interruptores' },
]

export default {
  id: 'agencia-marketing',
  nombre: 'Agencia de marketing',
  para: 'Agencias de marketing: clientes, campañas en curso y entregables por publicar',
  asignacion: {
    rubros: ['agencia', 'servicios'],
    ciclos: ['cotizacion', 'recurrente', 'mezcla'],
    objetivos: ['seguimientos', 'reportes', 'cotizaciones'],
    negocios: ['Agencia de marketing', 'Estudio de redes sociales', 'Agencia de pauta digital', 'Consultora de contenido'],
  },
  inicio: [
    { vista: 'kpis', seccion: 'campanas', opciones: { por: 'estado', suma: 'presupuesto' }, ancho: 12 },
    { vista: 'grafico', seccion: 'campanas', opciones: { tipo: 'gantt' }, ancho: 12, alto: 2 },
    { vista: 'vencimientos', seccion: 'entregables', opciones: { fecha: 'entrega', titulo: 'pieza', detalle: 'cliente', dias: 7, estado: 'estado', excluir: ['Publicado'] }, ancho: 8, alto: 2 },
    { vista: 'grafico', seccion: 'entregables', opciones: { tipo: 'dona' }, ancho: 4, alto: 2 },
  ],
  secciones: [
    { id: 'clientes', titulo: 'Clientes', grupo: 0, icono: 'usuarios', vista: 'tabla',
      campos: [
        { id: 'nombre', nombre: 'Contacto', tipo: 'texto' },
        { id: 'telefono', nombre: 'Teléfono', tipo: 'texto' },
        { id: 'marca', nombre: 'Marca', tipo: 'texto', ejemplos: ['Café Luna', 'Dental Sonrisa', 'Panadería La Espiga', 'Moda Ixchel', 'Gimnasio Norte', 'Clínica Vida'] },
        { id: 'sector', nombre: 'Sector', tipo: 'texto', ejemplos: ['Restaurantes', 'Comercio', 'Salud', 'Educación', 'Bienestar', 'Servicios profesionales'] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Prospecto', 'Activo', 'En pausa', 'Cerrado'] },
        { id: 'mensualidad', nombre: 'Mensualidad', tipo: 'dinero', rango: [1500, 12000] },
      ] },
    { id: 'campanas', titulo: 'Campañas', grupo: 0, icono: 'tablero', vista: 'tablero', opciones: { por: 'estado', titulo: 'campana', detalle: 'cliente' },
      campos: [
        { id: 'campana', nombre: 'Campaña', tipo: 'texto', ejemplos: ['Lanzamiento de verano', 'Redes del mes', 'Promoción 2x1', 'Ofertas de fin de año', 'Captación de prospectos', 'Recompra'] },
        { id: 'cliente', nombre: 'Cliente', tipo: 'texto' },
        { id: 'canal', nombre: 'Canal', tipo: 'texto', ejemplos: ['Instagram', 'Facebook', 'Google Ads', 'TikTok', 'YouTube', 'WhatsApp'] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Propuesta', 'Aprobada', 'Activa', 'En pausa', 'Cerrada'] },
        { id: 'inicio', nombre: 'Inicio', tipo: 'fecha', rango: [-45, 20] },
        { id: 'fin', nombre: 'Fin', tipo: 'fecha', rango: [-10, 90] },
        { id: 'presupuesto', nombre: 'Presupuesto', tipo: 'dinero', rango: [3000, 40000] },
      ] },
    { id: 'entregables', titulo: 'Entregables', grupo: 0, icono: 'documento', vista: 'vencimientos', opciones: { fecha: 'entrega', titulo: 'pieza', detalle: 'cliente', dias: 14, estado: 'estado', excluir: ['Publicado'] },
      campos: [
        { id: 'pieza', nombre: 'Pieza', tipo: 'texto', ejemplos: ['Video corto de producto', 'Carrusel de consejos', 'Historia del día', 'Anuncio para pauta', 'Página de campaña', 'Informe mensual'] },
        { id: 'cliente', nombre: 'Cliente', tipo: 'texto' },
        { id: 'campana', nombre: 'Campaña', tipo: 'texto', ejemplos: ['Lanzamiento de verano', 'Redes del mes', 'Promoción 2x1', 'Ofertas de fin de año', 'Captación de prospectos', 'Recompra'] },
        { id: 'responsable', nombre: 'Responsable', tipo: 'texto', ejemplos: ['Ana López', 'Carlos Pérez', 'Sofía Ramírez', 'Diego Morales', 'Camila Ortiz', 'Jorge Méndez'] },
        { id: 'entrega', nombre: 'Entrega', tipo: 'fecha', rango: [-5, 21] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Por hacer', 'En diseño', 'En revisión', 'Aprobado', 'Publicado'] },
      ] },
    ...fijas,
  ],
}
