const fijas = [
  { id: 'actividad', titulo: 'Historial', grupo: 1, icono: 'actividad', vista: 'feed' },
  { id: 'equipo', titulo: 'Equipo', grupo: 1, icono: 'equipo', vista: 'equipo' },
  { id: 'automatizaciones', titulo: 'Automatizaciones', grupo: 2, icono: 'rayo', vista: 'interruptores' },
]

export default {
  id: 'escuela-academia',
  nombre: 'Escuela o academia',
  para: 'Escuelas, academias y centros de capacitación: alumnos inscritos, cursos activos y cobro de mensualidades',
  asignacion: {
    rubros: ['educacion', 'servicios'],
    ciclos: ['recurrente', 'mezcla'],
    objetivos: ['seguimientos', 'contactos', 'reportes', 'equipo'],
    negocios: ['Academia de idiomas', 'Escuela de música', 'Centro de computación', 'Preparatoria con cursos extra'],
  },
  inicio: [
    { vista: 'kpis', seccion: 'alumnos', opciones: { por: 'estado', vencen: 'proximo', dias: 7, estado: 'estado', excluir: ['Baja'] }, ancho: 12 },
    { vista: 'vencimientos', seccion: 'pagos', opciones: { fecha: 'vence', titulo: 'alumno', detalle: 'concepto', dias: 14, estado: 'estado', excluir: ['Pagado'] }, ancho: 8, alto: 2 },
    { vista: 'grafico', seccion: 'alumnos', opciones: { tipo: 'dona' }, ancho: 4, alto: 2 },
    { vista: 'tablero', seccion: 'cursos', opciones: { por: 'estado', titulo: 'curso', detalle: 'nivel' }, ancho: 8, alto: 2 },
    { vista: 'grafico', seccion: 'cursos', opciones: { tipo: 'columnas' }, ancho: 4, alto: 2 },
  ],
  secciones: [
    { id: 'alumnos', titulo: 'Alumnos', grupo: 0, icono: 'usuarios', vista: 'tabla',
      campos: [
        { id: 'nombre', nombre: 'Nombre', tipo: 'texto' },
        { id: 'telefono', nombre: 'Teléfono', tipo: 'texto' },
        { id: 'curso', nombre: 'Curso', tipo: 'texto', ejemplos: ['Inglés intermedio', 'Piano nivel 1', 'Excel avanzado', 'Matemáticas bachillerato', 'Robótica junior', 'Francés básico'] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Activo', 'Moroso', 'Pausa', 'Baja', 'Egresado'] },
        { id: 'inscripcion', nombre: 'Inscripción', tipo: 'fecha', rango: [-400, 0] },
        { id: 'proximo', nombre: 'Próximo pago', tipo: 'fecha', rango: [-10, 30] },
      ] },
    { id: 'cursos', titulo: 'Cursos', grupo: 0, icono: 'tablero', vista: 'tablero', opciones: { por: 'estado', titulo: 'curso', detalle: 'nivel' },
      campos: [
        { id: 'curso', nombre: 'Curso', tipo: 'texto', ejemplos: ['Inglés intermedio', 'Piano nivel 1', 'Excel avanzado', 'Matemáticas bachillerato', 'Robótica junior', 'Francés básico'] },
        { id: 'nivel', nombre: 'Nivel', tipo: 'texto', ejemplos: ['Básico', 'Intermedio', 'Avanzado', 'Infantil', 'Teens', 'Adultos'] },
        { id: 'horario', nombre: 'Horario', tipo: 'texto', ejemplos: ['Lun y Mié 4pm', 'Mar y Jue 6pm', 'Sáb 9am', 'Lun a Vie 7am', 'Virtual martes', 'Sáb 11am'] },
        { id: 'cupo', nombre: 'Cupo', tipo: 'numero', rango: [8, 25] },
        { id: 'inscritos', nombre: 'Inscritos', tipo: 'numero', rango: [0, 25] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Por iniciar', 'En curso', 'Completo', 'Finalizado'] },
        { id: 'mensualidad', nombre: 'Mensualidad', tipo: 'dinero', rango: [350, 2800] },
      ] },
    { id: 'pagos', titulo: 'Pagos', grupo: 0, icono: 'caja', vista: 'tabla',
      campos: [
        { id: 'alumno', nombre: 'Alumno', tipo: 'texto', ejemplos: ['Valentina Cruz', 'Mateo Flores', 'Isabella Ruiz', 'Santiago Mejía', 'Camila Ortiz', 'Sebastián Vásquez'] },
        { id: 'concepto', nombre: 'Concepto', tipo: 'texto', ejemplos: ['Mensualidad marzo', 'Inscripción', 'Material didáctico', 'Examen certificación', 'Mensualidad abril', 'Recargo mora'] },
        { id: 'monto', nombre: 'Monto', tipo: 'dinero', rango: [200, 3500] },
        { id: 'vence', nombre: 'Vence', tipo: 'fecha', rango: [-15, 30] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Pendiente', 'Pagado', 'Vencido', 'Condonado'] },
      ] },
    ...fijas,
  ],
}
