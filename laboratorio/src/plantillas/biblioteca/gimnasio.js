const fijas = [
  { id: 'actividad', titulo: 'Historial', grupo: 1, icono: 'actividad', vista: 'feed' },
  { id: 'equipo', titulo: 'Equipo', grupo: 1, icono: 'equipo', vista: 'equipo' },
  { id: 'automatizaciones', titulo: 'Automatizaciones', grupo: 2, icono: 'rayo', vista: 'interruptores' },
]

export default {
  id: 'gimnasio',
  nombre: 'Gimnasio',
  para: 'Gimnasios y estudios fitness: membresías activas, clases grupales y renovaciones',
  asignacion: {
    rubros: ['servicios', 'comercio'],
    ciclos: ['recurrente', 'rapida'],
    objetivos: ['seguimientos', 'contactos', 'reportes', 'equipo'],
    negocios: ['Gimnasio de barrio', 'Estudio de yoga y pilates', 'CrossFit box', 'Centro de entrenamiento personal'],
  },
  inicio: [
    { vista: 'kpis', seccion: 'membresias', opciones: { por: 'estado', vencen: 'vence', dias: 7, estado: 'estado', excluir: ['Cancelada'] }, ancho: 12 },
    { vista: 'vencimientos', seccion: 'membresias', opciones: { fecha: 'vence', titulo: 'nombre', detalle: 'plan', dias: 14, estado: 'estado', excluir: ['Cancelada'] }, ancho: 8, alto: 2 },
    { vista: 'grafico', seccion: 'membresias', opciones: { tipo: 'dona' }, ancho: 4, alto: 2 },
    { vista: 'agenda', seccion: 'clases', opciones: { fecha: 'fecha', hora: 'hora', titulo: 'clase', detalle: 'entrenador', dias: 7 }, ancho: 8, alto: 2 },
    { vista: 'grafico', seccion: 'membresias', opciones: { tipo: 'linea-area', fecha: 'alta', valor: 'monto', funcion: 'suma' }, ancho: 4, alto: 2 },
  ],
  secciones: [
    { id: 'membresias', titulo: 'Membresías', grupo: 0, icono: 'tarjeta', vista: 'tabla',
      campos: [
        { id: 'nombre', nombre: 'Nombre', tipo: 'texto' },
        { id: 'telefono', nombre: 'Teléfono', tipo: 'texto' },
        { id: 'plan', nombre: 'Plan', tipo: 'texto', ejemplos: ['Mensual básico', 'Mensual plus', 'Trimestral', 'Anual', 'Pareja', 'Estudiante'] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Activa', 'Pausada', 'Por vencer', 'Cancelada'] },
        { id: 'alta', nombre: 'Alta', tipo: 'fecha', rango: [-400, 0] },
        { id: 'vence', nombre: 'Vence', tipo: 'fecha', rango: [-5, 45] },
        { id: 'monto', nombre: 'Monto', tipo: 'dinero', rango: [250, 4500] },
      ] },
    { id: 'clases', titulo: 'Clases', grupo: 0, icono: 'calendario', vista: 'agenda', opciones: { fecha: 'fecha', hora: 'hora', titulo: 'clase', detalle: 'entrenador', dias: 14 },
      campos: [
        { id: 'clase', nombre: 'Clase', tipo: 'texto', ejemplos: ['Spinning', 'Funcional', 'Yoga', 'Zumba', 'CrossFit WOD', 'Box'] },
        { id: 'entrenador', nombre: 'Entrenador', tipo: 'texto', ejemplos: ['Carlos M.', 'Ana R.', 'Luis P.', 'María G.', 'Diego S.', 'Paola V.'] },
        { id: 'fecha', nombre: 'Fecha', tipo: 'fecha', rango: [-7, 14] },
        { id: 'hora', nombre: 'Hora', tipo: 'hora' },
        { id: 'cupo', nombre: 'Cupo', tipo: 'numero', rango: [8, 30] },
        { id: 'inscritos', nombre: 'Inscritos', tipo: 'numero', rango: [0, 30] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Programada', 'En curso', 'Completa', 'Cancelada'] },
      ] },
    { id: 'visitas', titulo: 'Visitas y prueba', grupo: 0, icono: 'usuarios', vista: 'tablero', opciones: { por: 'estado', titulo: 'nombre', detalle: 'interes' },
      campos: [
        { id: 'nombre', nombre: 'Nombre', tipo: 'texto' },
        { id: 'telefono', nombre: 'Teléfono', tipo: 'texto' },
        { id: 'interes', nombre: 'Interés', tipo: 'texto', ejemplos: ['Pérdida de peso', 'Ganar masa', 'Rehabilitación', 'Clases grupales', 'Entrenador personal', 'Plan familiar'] },
        { id: 'fecha', nombre: 'Visita', tipo: 'fecha', rango: [-14, 7] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Agendada', 'Asistió', 'Interesado', 'Inscrito', 'No interesado'] },
      ] },
    ...fijas,
  ],
}
