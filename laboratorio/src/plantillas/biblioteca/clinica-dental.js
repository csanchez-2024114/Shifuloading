const fijas = [
  { id: 'actividad', titulo: 'Historial', grupo: 1, icono: 'actividad', vista: 'feed' },
  { id: 'equipo', titulo: 'Equipo', grupo: 1, icono: 'equipo', vista: 'equipo' },
  { id: 'automatizaciones', titulo: 'Automatizaciones', grupo: 2, icono: 'rayo', vista: 'interruptores' },
]

export default {
  id: 'clinica-dental',
  nombre: 'Clínica dental',
  para: 'Consultorios y clínicas dentales: agenda de citas, tratamientos en curso y pacientes',
  asignacion: {
    rubros: ['salud', 'servicios'],
    ciclos: ['recurrente', 'rapida'],
    objetivos: ['seguimientos', 'contactos', 'reportes', 'equipo'],
    negocios: ['Consultorio dental familiar', 'Clínica de ortodoncia', 'Centro de implantes', 'Odontopediatría'],
  },
  inicio: [
    { vista: 'kpis', seccion: 'citas', opciones: { por: 'estado', hoy: 'fecha' }, ancho: 12 },
    { vista: 'agenda', seccion: 'citas', opciones: { fecha: 'fecha', hora: 'hora', titulo: 'paciente', detalle: 'motivo', dias: 7 }, ancho: 8, alto: 2 },
    { vista: 'grafico', seccion: 'citas', opciones: { tipo: 'dona' }, ancho: 4, alto: 2 },
    { vista: 'tablero', seccion: 'tratamientos', opciones: { por: 'estado', titulo: 'paciente', detalle: 'tratamiento' }, ancho: 8, alto: 2 },
    { vista: 'grafico', seccion: 'tratamientos', opciones: { tipo: 'columnas' }, ancho: 4, alto: 2 },
  ],
  secciones: [
    { id: 'citas', titulo: 'Citas', grupo: 0, icono: 'calendario', vista: 'agenda', opciones: { fecha: 'fecha', hora: 'hora', titulo: 'paciente', detalle: 'motivo', dias: 14 },
      campos: [
        { id: 'paciente', nombre: 'Paciente', tipo: 'texto', ejemplos: ['María González', 'Carlos Pérez', 'Ana Martínez', 'Luis Herrera', 'Sofía Ramírez', 'Diego Castillo'] },
        { id: 'motivo', nombre: 'Motivo', tipo: 'texto', ejemplos: ['Limpieza', 'Dolor muela', 'Revisión ortodoncia', 'Extracción', 'Blanqueamiento', 'Urgencia'] },
        { id: 'fecha', nombre: 'Fecha', tipo: 'fecha', rango: [-2, 21] },
        { id: 'hora', nombre: 'Hora', tipo: 'hora' },
        { id: 'doctor', nombre: 'Doctor', tipo: 'texto', ejemplos: ['Dra. Martínez', 'Dr. López', 'Dra. Hernández', 'Dr. Ramírez', 'Dra. Morales', 'Dr. Castillo'] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Por confirmar', 'Confirmada', 'En consulta', 'Atendida', 'No asistió'] },
      ] },
    { id: 'tratamientos', titulo: 'Tratamientos', grupo: 0, icono: 'tablero', vista: 'tablero', opciones: { por: 'estado', titulo: 'paciente', detalle: 'tratamiento' },
      campos: [
        { id: 'paciente', nombre: 'Paciente', tipo: 'texto', ejemplos: ['María González', 'Carlos Pérez', 'Ana Martínez', 'Luis Herrera', 'Sofía Ramírez', 'Diego Castillo'] },
        { id: 'tratamiento', nombre: 'Tratamiento', tipo: 'texto', ejemplos: ['Ortodoncia brackets', 'Implante unitario', 'Endodoncia', 'Corona cerámica', 'Carillas', 'Periodoncia'] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Presupuesto', 'Aceptado', 'En curso', 'Pausado', 'Finalizado'] },
        { id: 'inicio', nombre: 'Inicio', tipo: 'fecha', rango: [-90, 14] },
        { id: 'sesiones', nombre: 'Sesiones', tipo: 'numero', rango: [1, 24] },
        { id: 'total', nombre: 'Total', tipo: 'dinero', rango: [800, 45000] },
      ] },
    { id: 'pacientes', titulo: 'Pacientes', grupo: 0, icono: 'usuarios', vista: 'tabla',
      campos: [
        { id: 'nombre', nombre: 'Nombre', tipo: 'texto' },
        { id: 'telefono', nombre: 'Teléfono', tipo: 'texto' },
        { id: 'ultima', nombre: 'Última visita', tipo: 'fecha', rango: [-365, 0] },
        { id: 'tipo', nombre: 'Tipo', tipo: 'estado', opciones: ['Nuevo', 'Recurrente', 'Inactivo'] },
        { id: 'notas', nombre: 'Notas', tipo: 'texto', ejemplos: ['Alérgico a anestesia X', 'Bruxismo', 'Embarazo', 'Menor de edad', 'Pago en cuotas', 'Seguro dental'] },
      ] },
    ...fijas,
  ],
}
