const fijas = [
  { id: 'actividad', titulo: 'Historial', grupo: 1, icono: 'actividad', vista: 'feed' },
  { id: 'equipo', titulo: 'Equipo', grupo: 1, icono: 'equipo', vista: 'equipo' },
  { id: 'automatizaciones', titulo: 'Automatizaciones', grupo: 2, icono: 'rayo', vista: 'interruptores' },
]

export default {
  id: 'despacho-abogados',
  nombre: 'Despacho de abogados',
  para: 'Despachos de abogados: casos en trámite, audiencias próximas y honorarios por cobrar',
  asignacion: {
    rubros: ['servicios'],
    ciclos: ['cotizacion', 'recurrente'],
    objetivos: ['seguimientos', 'cotizaciones', 'reportes'],
    negocios: ['Despacho de abogados', 'Bufete familiar', 'Estudio jurídico laboral', 'Abogado independiente'],
  },
  inicio: [
    { vista: 'kpis', seccion: 'casos', opciones: { por: 'estado', suma: 'honorarios' }, ancho: 12 },
    { vista: 'tablero', seccion: 'casos', opciones: { por: 'estado', titulo: 'asunto', detalle: 'cliente' }, ancho: 8, alto: 2 },
    { vista: 'grafico', seccion: 'casos', opciones: { tipo: 'embudo' }, ancho: 4, alto: 2 },
    { vista: 'agenda', seccion: 'audiencias', opciones: { fecha: 'fecha', hora: 'hora', titulo: 'asunto', detalle: 'juzgado', dias: 14 }, ancho: 6, alto: 2 },
    { vista: 'vencimientos', seccion: 'honorarios', opciones: { fecha: 'vence', titulo: 'cliente', detalle: 'concepto', dias: 15, estado: 'estado', excluir: ['Pagado'] }, ancho: 6, alto: 2 },
  ],
  secciones: [
    { id: 'casos', titulo: 'Casos', grupo: 0, icono: 'tablero', vista: 'tablero', opciones: { por: 'estado', titulo: 'asunto', detalle: 'cliente' },
      campos: [
        { id: 'asunto', nombre: 'Asunto', tipo: 'texto', ejemplos: ['Divorcio de mutuo acuerdo', 'Despido injustificado', 'Cobro de deuda', 'Contrato de arrendamiento', 'Pensión de alimentos', 'Constitución de sociedad'] },
        { id: 'cliente', nombre: 'Cliente', tipo: 'texto' },
        { id: 'materia', nombre: 'Materia', tipo: 'texto', ejemplos: ['Civil', 'Familiar', 'Laboral', 'Mercantil', 'Penal', 'Administrativo'] },
        { id: 'abogado', nombre: 'Abogado', tipo: 'texto', ejemplos: ['Lic. Ana López', 'Lic. Carlos Pérez', 'Lic. Sofía Ramírez', 'Lic. Diego Morales', 'Lic. Camila Ortiz', 'Lic. Jorge Méndez'] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Consulta', 'En trámite', 'Audiencia', 'Sentencia', 'Cerrado'] },
        { id: 'apertura', nombre: 'Apertura', tipo: 'fecha', rango: [-180, 5] },
        { id: 'honorarios', nombre: 'Honorarios', tipo: 'dinero', rango: [1500, 25000] },
      ] },
    { id: 'audiencias', titulo: 'Audiencias', grupo: 0, icono: 'calendario', vista: 'agenda', opciones: { fecha: 'fecha', hora: 'hora', titulo: 'asunto', detalle: 'juzgado', dias: 21 },
      campos: [
        { id: 'asunto', nombre: 'Asunto', tipo: 'texto', ejemplos: ['Divorcio de mutuo acuerdo', 'Despido injustificado', 'Cobro de deuda', 'Contrato de arrendamiento', 'Pensión de alimentos', 'Constitución de sociedad'] },
        { id: 'cliente', nombre: 'Cliente', tipo: 'texto' },
        { id: 'juzgado', nombre: 'Juzgado', tipo: 'texto', ejemplos: ['Juzgado civil', 'Juzgado de paz', 'Tribunal laboral', 'Juzgado de familia', 'Centro de mediación', 'Sala civil'] },
        { id: 'fecha', nombre: 'Fecha', tipo: 'fecha', rango: [-3, 30] },
        { id: 'hora', nombre: 'Hora', tipo: 'hora' },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Por preparar', 'Programada', 'Reprogramada', 'Celebrada', 'Cerrada'] },
      ] },
    { id: 'honorarios', titulo: 'Honorarios', grupo: 0, icono: 'tarjeta', vista: 'vencimientos', opciones: { fecha: 'vence', titulo: 'cliente', detalle: 'concepto', dias: 30, estado: 'estado', excluir: ['Pagado'] },
      campos: [
        { id: 'cliente', nombre: 'Cliente', tipo: 'texto' },
        { id: 'concepto', nombre: 'Concepto', tipo: 'texto', ejemplos: ['Anticipo', 'Consulta', 'Escrito', 'Audiencia', 'Éxito del caso', 'Gastos del tribunal'] },
        { id: 'asunto', nombre: 'Asunto', tipo: 'texto', ejemplos: ['Divorcio de mutuo acuerdo', 'Despido injustificado', 'Cobro de deuda', 'Contrato de arrendamiento', 'Pensión de alimentos', 'Constitución de sociedad'] },
        { id: 'monto', nombre: 'Monto', tipo: 'dinero', rango: [400, 12000] },
        { id: 'vence', nombre: 'Vence', tipo: 'fecha', rango: [-10, 40] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Por facturar', 'Facturado', 'Vencido', 'Pagado'] },
      ] },
    ...fijas,
  ],
}
