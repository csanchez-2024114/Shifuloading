const fijas = [
  { id: 'actividad', titulo: 'Historial', grupo: 1, icono: 'actividad', vista: 'feed' },
  { id: 'equipo', titulo: 'Equipo', grupo: 1, icono: 'equipo', vista: 'equipo' },
  { id: 'automatizaciones', titulo: 'Automatizaciones', grupo: 2, icono: 'rayo', vista: 'interruptores' },
]

export default {
  id: 'consultorio-medico',
  nombre: 'Consultorio médico general',
  para: 'Consultorios de medicina general: pacientes, citas del día y seguimientos pendientes',
  asignacion: {
    rubros: ['salud'],
    ciclos: ['rapida', 'recurrente'],
    objetivos: ['seguimientos', 'contactos', 'reportes'],
    negocios: ['Consultorio de familia', 'Clínica de barrio', 'Centro de atención primaria'],
  },
  inicio: [
    { vista: 'kpis', seccion: 'citas', opciones: { por: 'estado', hoy: 'fecha' }, ancho: 12 },
    { vista: 'agenda', seccion: 'citas', opciones: { fecha: 'fecha', hora: 'hora', titulo: 'cliente', detalle: 'motivo', dias: 7 }, ancho: 8, alto: 2 },
    { vista: 'grafico', seccion: 'citas', opciones: { tipo: 'dona' }, ancho: 4, alto: 2 },
    { vista: 'vencimientos', seccion: 'seguimientos', opciones: { fecha: 'proxima', titulo: 'cliente', detalle: 'motivo', dias: 14, estado: 'estado', excluir: ['Cerrado'] }, ancho: 8, alto: 2 },
    { vista: 'grafico', seccion: 'pacientes', opciones: { tipo: 'columnas' }, ancho: 4, alto: 2 },
  ],
  secciones: [
    { id: 'pacientes', titulo: 'Pacientes', grupo: 0, icono: 'usuarios', vista: 'tabla',
      campos: [
        { id: 'nombre', nombre: 'Nombre', tipo: 'texto' },
        { id: 'telefono', nombre: 'Teléfono', tipo: 'texto' },
        { id: 'edad', nombre: 'Edad', tipo: 'numero', rango: [1, 95] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Activo', 'En tratamiento', 'Control periódico', 'Inactivo'] },
        { id: 'alta', nombre: 'Alta', tipo: 'fecha', rango: [-365, 0] },
      ] },
    { id: 'citas', titulo: 'Citas', grupo: 0, icono: 'calendario', vista: 'agenda', opciones: { fecha: 'fecha', hora: 'hora', titulo: 'cliente', detalle: 'motivo', dias: 14 },
      campos: [
        { id: 'cliente', nombre: 'Paciente', tipo: 'texto' },
        { id: 'motivo', nombre: 'Motivo', tipo: 'texto', ejemplos: ['Control general', 'Dolor abdominal', 'Chequeo anual', 'Renovar receta', 'Curación', 'Certificado médico'] },
        { id: 'fecha', nombre: 'Fecha', tipo: 'fecha', rango: [-3, 21] },
        { id: 'hora', nombre: 'Hora', tipo: 'hora' },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Por confirmar', 'Confirmada', 'En consulta', 'Atendida', 'No asistió'] },
      ] },
    { id: 'seguimientos', titulo: 'Seguimientos', grupo: 0, icono: 'reloj', vista: 'vencimientos', opciones: { fecha: 'proxima', titulo: 'cliente', detalle: 'motivo', dias: 30, estado: 'estado', excluir: ['Cerrado'] },
      campos: [
        { id: 'cliente', nombre: 'Paciente', tipo: 'texto' },
        { id: 'motivo', nombre: 'Motivo', tipo: 'texto', ejemplos: ['Control presión', 'Resultados de laboratorio', 'Seguimiento diabetes', 'Postoperatorio', 'Vacunación', 'Referencia especialista'] },
        { id: 'proxima', nombre: 'Próxima cita', tipo: 'fecha', rango: [-2, 45] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Pendiente', 'Agendado', 'Cerrado'] },
      ] },
    ...fijas,
  ],
}
