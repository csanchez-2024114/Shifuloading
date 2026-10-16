const fijas = [
  { id: 'actividad', titulo: 'Historial', grupo: 1, icono: 'actividad', vista: 'feed' },
  { id: 'equipo', titulo: 'Equipo', grupo: 1, icono: 'equipo', vista: 'equipo' },
  { id: 'automatizaciones', titulo: 'Automatizaciones', grupo: 2, icono: 'rayo', vista: 'interruptores' },
]

export default {
  id: 'organizacion-sin-lucro',
  nombre: 'Organización sin fines de lucro',
  para: 'ONG y fundaciones: donantes, donaciones recibidas y voluntarios activos',
  asignacion: {
    rubros: ['otro', 'servicios'],
    ciclos: ['recurrente', 'mezcla'],
    objetivos: ['contactos', 'seguimientos', 'reportes', 'equipo'],
    negocios: ['Fundación social', 'Asociación comunitaria', 'ONG de apoyo educativo'],
  },
  inicio: [
    { vista: 'kpis', seccion: 'donaciones', opciones: { por: 'estado', suma: 'monto' }, ancho: 12 },
    { vista: 'tablero', seccion: 'donaciones', opciones: { por: 'estado', titulo: 'cliente', detalle: 'campana' }, ancho: 8, alto: 2 },
    { vista: 'grafico', seccion: 'donaciones', opciones: { tipo: 'dona' }, ancho: 4, alto: 2 },
    { vista: 'tabla', seccion: 'voluntarios', opciones: {}, ancho: 8, alto: 2 },
    { vista: 'grafico', seccion: 'donantes', opciones: { tipo: 'columnas' }, ancho: 4, alto: 2 },
  ],
  secciones: [
    { id: 'donantes', titulo: 'Donantes', grupo: 0, icono: 'usuarios', vista: 'tabla',
      campos: [
        { id: 'nombre', nombre: 'Nombre', tipo: 'texto' },
        { id: 'telefono', nombre: 'Teléfono', tipo: 'texto' },
        { id: 'tipo', nombre: 'Tipo', tipo: 'estado', opciones: ['Persona', 'Empresa', 'Institución', 'Anónimo recurrente'] },
        { id: 'interes', nombre: 'Interés', tipo: 'texto', ejemplos: ['Educación', 'Salud', 'Medio ambiente', 'Alimentación', 'Vivienda', 'Niñez'] },
        { id: 'alta', nombre: 'Alta', tipo: 'fecha', rango: [-400, 0] },
      ] },
    { id: 'donaciones', titulo: 'Donaciones', grupo: 0, icono: 'caja', vista: 'tablero', opciones: { por: 'estado', titulo: 'cliente', detalle: 'campana' },
      campos: [
        { id: 'cliente', nombre: 'Donante', tipo: 'texto' },
        { id: 'campana', nombre: 'Campaña', tipo: 'texto', ejemplos: ['Navidad solidaria', 'Becas escolares', 'Emergencia inundación', 'Comedores', 'Reforestación', 'Apoyo médico'] },
        { id: 'monto', nombre: 'Monto', tipo: 'dinero', rango: [50, 25000] },
        { id: 'fecha', nombre: 'Fecha', tipo: 'fecha', rango: [-60, 0] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Prometida', 'Recibida', 'En proceso', 'Aplicada'] },
      ] },
    { id: 'voluntarios', titulo: 'Voluntarios', grupo: 0, icono: 'equipo', vista: 'tabla',
      campos: [
        { id: 'nombre', nombre: 'Nombre', tipo: 'texto' },
        { id: 'telefono', nombre: 'Teléfono', tipo: 'texto' },
        { id: 'rol', nombre: 'Rol', tipo: 'texto', ejemplos: ['Logística', 'Capacitación', 'Recaudación', 'Comunicación', 'Terreno', 'Administración'] },
        { id: 'disponibilidad', nombre: 'Disponibilidad', tipo: 'texto', ejemplos: ['Sábados', 'Entre semana', 'Fines de semana', 'Mañanas', 'Tardes', 'Eventos puntuales'] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Activo', 'En pausa', 'Nuevo', 'Inactivo'] },
      ] },
    ...fijas,
  ],
}
