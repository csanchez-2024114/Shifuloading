export default {
  id: 'tareas',
  para: 'Repasar qué tiene pendiente tu equipo, quién lo hace y qué prioridad tiene cada cosa',
  palabras: ['tareas', 'pendientes', 'to-do del equipo', 'qué hay que hacer', 'lista de actividades'],
  seccion: {
    titulo: 'Tareas', icono: 'tablero', vista: 'tablero',
    opciones: { por: 'estado', titulo: 'titulo', detalle: 'responsable' },
    campos: [
      { id: 'titulo', nombre: 'Título', tipo: 'texto', ejemplos: ['Actualizar precios', 'Llamar a proveedor', 'Revisar inventario', 'Publicar oferta', 'Capacitar nuevo'] },
      { id: 'responsable', nombre: 'Responsable', tipo: 'texto', ejemplos: ['Ana', 'Bodega', 'Marketing', 'Gerencia', 'Soporte'] },
      { id: 'prioridad', nombre: 'Prioridad', tipo: 'estado', opciones: ['Baja', 'Media', 'Alta', 'Urgente'] },
      { id: 'limite', nombre: 'Fecha límite', tipo: 'fecha', rango: [-10, 45] },
      { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Por hacer', 'En progreso', 'En revisión', 'Hecha', 'Bloqueada'] },
    ],
  },
  piezas: [
    { vista: 'tablero', opciones: { por: 'estado', titulo: 'titulo', detalle: 'responsable' }, ancho: 8, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'radar', estado: 'prioridad', funcion: 'conteo' }, ancho: 4, alto: 2 },
    { vista: 'vencimientos', opciones: { fecha: 'limite', titulo: 'titulo', detalle: 'responsable', dias: 14, estado: 'estado', excluir: ['Hecha'] }, ancho: 12, alto: 2 },
  ],
}
