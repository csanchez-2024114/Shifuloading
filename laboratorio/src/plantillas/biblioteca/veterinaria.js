const fijas = [
  { id: 'actividad', titulo: 'Historial', grupo: 1, icono: 'actividad', vista: 'feed' },
  { id: 'equipo', titulo: 'Equipo', grupo: 1, icono: 'equipo', vista: 'equipo' },
  { id: 'automatizaciones', titulo: 'Automatizaciones', grupo: 2, icono: 'rayo', vista: 'interruptores' },
]

export default {
  id: 'veterinaria',
  nombre: 'Veterinaria',
  para: 'Clínicas veterinarias: citas del día, expediente de mascotas y vacunas por vencer',
  asignacion: {
    rubros: ['salud', 'servicios'],
    ciclos: ['rapida', 'recurrente'],
    objetivos: ['seguimientos', 'contactos', 'reportes'],
    negocios: ['Clínica veterinaria', 'Consultorio de mascotas', 'Hospital veterinario', 'Veterinaria de barrio'],
  },
  inicio: [
    { vista: 'kpis', seccion: 'citas', opciones: { por: 'estado', suma: 'costo', hoy: 'fecha' }, ancho: 12 },
    { vista: 'agenda', seccion: 'citas', opciones: { fecha: 'fecha', hora: 'hora', titulo: 'mascota', detalle: 'motivo', dias: 7 }, ancho: 8, alto: 2 },
    { vista: 'grafico', seccion: 'citas', opciones: { tipo: 'calor-hora' }, ancho: 4, alto: 2 },
    { vista: 'vencimientos', seccion: 'vacunas', opciones: { fecha: 'proxima', titulo: 'mascota', detalle: 'vacuna', dias: 21, estado: 'estado', excluir: ['Aplicada'] }, ancho: 8, alto: 2 },
    { vista: 'grafico', seccion: 'vacunas', opciones: { tipo: 'dona' }, ancho: 4, alto: 2 },
  ],
  secciones: [
    { id: 'citas', titulo: 'Citas', grupo: 0, icono: 'calendario', vista: 'agenda', opciones: { fecha: 'fecha', hora: 'hora', titulo: 'mascota', detalle: 'motivo', dias: 14 },
      campos: [
        { id: 'mascota', nombre: 'Mascota', tipo: 'texto', ejemplos: ['Luna (perra)', 'Milo (gato)', 'Rocky (perro)', 'Nala (gata)', 'Coco (conejo)', 'Kiwi (ave)'] },
        { id: 'cliente', nombre: 'Dueño', tipo: 'texto' },
        { id: 'motivo', nombre: 'Motivo', tipo: 'texto', ejemplos: ['Consulta general', 'Vacunación', 'Desparasitación', 'Control', 'Herida', 'Chequeo dental'] },
        { id: 'veterinario', nombre: 'Veterinario', tipo: 'texto', ejemplos: ['Dra. Paz', 'Dr. Morales', 'Dra. León', 'Dr. Ortiz', 'Dra. Rojas', 'Dr. Méndez'] },
        { id: 'fecha', nombre: 'Fecha', tipo: 'fecha', rango: [-2, 14] },
        { id: 'hora', nombre: 'Hora', tipo: 'hora' },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Agendada', 'En sala', 'En consulta', 'Atendida', 'No asistió'] },
        { id: 'costo', nombre: 'Costo', tipo: 'dinero', rango: [150, 2500] },
      ] },
    { id: 'mascotas', titulo: 'Mascotas', grupo: 0, icono: 'usuarios', vista: 'tabla',
      campos: [
        { id: 'mascota', nombre: 'Mascota', tipo: 'texto', ejemplos: ['Luna (perra)', 'Milo (gato)', 'Rocky (perro)', 'Nala (gata)', 'Coco (conejo)', 'Kiwi (ave)'] },
        { id: 'cliente', nombre: 'Dueño', tipo: 'texto' },
        { id: 'especie', nombre: 'Especie', tipo: 'texto', ejemplos: ['Perro', 'Gato', 'Ave', 'Conejo', 'Hámster', 'Reptil'] },
        { id: 'raza', nombre: 'Raza', tipo: 'texto', ejemplos: ['Mestizo', 'Labrador', 'Siamés', 'Caniche', 'Persa', 'Criollo'] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Sana', 'En observación', 'En tratamiento', 'Hospitalizada'] },
        { id: 'ultima', nombre: 'Última visita', tipo: 'fecha', rango: [-180, 0] },
      ] },
    { id: 'vacunas', titulo: 'Vacunas', grupo: 0, icono: 'reloj', vista: 'vencimientos', opciones: { fecha: 'proxima', titulo: 'mascota', detalle: 'vacuna', dias: 30, estado: 'estado', excluir: ['Aplicada'] },
      campos: [
        { id: 'mascota', nombre: 'Mascota', tipo: 'texto', ejemplos: ['Luna (perra)', 'Milo (gato)', 'Rocky (perro)', 'Nala (gata)', 'Coco (conejo)', 'Kiwi (ave)'] },
        { id: 'cliente', nombre: 'Dueño', tipo: 'texto' },
        { id: 'vacuna', nombre: 'Vacuna', tipo: 'texto', ejemplos: ['Rabia', 'Parvovirus', 'Moquillo', 'Triple felina', 'Leptospirosis', 'Bordetella'] },
        { id: 'proxima', nombre: 'Próxima', tipo: 'fecha', rango: [-20, 50] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Programada', 'Por vencer', 'Vencida', 'Aplicada'] },
        { id: 'costo', nombre: 'Costo', tipo: 'dinero', rango: [80, 600] },
      ] },
    ...fijas,
  ],
}
