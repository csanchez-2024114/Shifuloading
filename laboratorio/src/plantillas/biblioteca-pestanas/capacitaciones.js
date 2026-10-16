export default {
  id: 'capacitaciones',
  para: 'Planear capacitaciones del equipo, fechas y quién ya terminó cada curso',
  palabras: ['capacitaciones', 'cursos al personal', 'entrenamiento', 'formación del equipo', 'talleres internos'],
  seccion: {
    titulo: 'Capacitaciones', icono: 'equipo', vista: 'tablero',
    opciones: { por: 'estado', titulo: 'curso', detalle: 'participante' },
    campos: [
      { id: 'curso', nombre: 'Curso', tipo: 'texto', ejemplos: ['Inducción nuevos', 'Manejo de caja', 'Seguridad industrial', 'Ventas consultivas', 'Primeros auxilios'] },
      { id: 'participante', nombre: 'Participante', tipo: 'texto', ejemplos: ['Todo el equipo', 'Ventas', 'Nuevo ingreso', 'Gerentes', 'Bodega completa'] },
      { id: 'inicio', nombre: 'Inicio', tipo: 'fecha', rango: [-60, 45] },
      { id: 'duracion', nombre: 'Horas', tipo: 'numero', rango: [2, 40] },
      { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Planeada', 'En curso', 'Completada', 'Reprogramada', 'Cancelada'] },
    ],
  },
  piezas: [
    { vista: 'tablero', opciones: { por: 'estado', titulo: 'curso', detalle: 'participante' }, ancho: 8, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'linea', fecha: 'inicio', funcion: 'conteo' }, ancho: 4, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'dispersion', valor: 'duracion', valor2: 'duracion', x: 'inicio' }, ancho: 6, alto: 2 },
  ],
}
