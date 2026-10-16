const fijas = [
  { id: 'actividad', titulo: 'Historial', grupo: 1, icono: 'actividad', vista: 'feed' },
  { id: 'equipo', titulo: 'Equipo', grupo: 1, icono: 'equipo', vista: 'equipo' },
  { id: 'automatizaciones', titulo: 'Automatizaciones', grupo: 2, icono: 'rayo', vista: 'interruptores' },
]

export default {
  id: 'firma-contable',
  nombre: 'Firma contable',
  para: 'Contadores y firmas contables: clientes, declaraciones y vencimientos fiscales',
  asignacion: {
    rubros: ['servicios'],
    ciclos: ['recurrente', 'cotizacion'],
    objetivos: ['seguimientos', 'reportes'],
    negocios: ['Despacho contable', 'Contador independiente', 'Firma de impuestos', 'Asesoría fiscal'],
  },
  inicio: [
    { vista: 'kpis', seccion: 'declaraciones', opciones: { por: 'estado', suma: 'monto', vencen: 'vence', dias: 15, estado: 'estado', excluir: ['Presentada', 'Pagada'] }, ancho: 12 },
    { vista: 'tablero', seccion: 'declaraciones', opciones: { por: 'estado', titulo: 'cliente', detalle: 'tipo' }, ancho: 8, alto: 2 },
    { vista: 'grafico', seccion: 'declaraciones', opciones: { tipo: 'dona' }, ancho: 4, alto: 2 },
    { vista: 'vencimientos', seccion: 'obligaciones', opciones: { fecha: 'vence', titulo: 'obligacion', detalle: 'cliente', dias: 15, estado: 'estado', excluir: ['Presentada'] }, ancho: 8, alto: 2 },
    { vista: 'grafico', seccion: 'declaraciones', opciones: { tipo: 'barras' }, ancho: 4, alto: 2 },
  ],
  secciones: [
    { id: 'clientes', titulo: 'Clientes', grupo: 0, icono: 'usuarios', vista: 'tabla',
      campos: [
        { id: 'nombre', nombre: 'Nombre', tipo: 'texto' },
        { id: 'telefono', nombre: 'Teléfono', tipo: 'texto' },
        { id: 'empresa', nombre: 'Empresa', tipo: 'texto' },
        { id: 'regimen', nombre: 'Régimen', tipo: 'texto', ejemplos: ['Régimen general', 'Pequeño contribuyente', 'Régimen simplificado', 'Persona física', 'Asociación', 'Régimen de confianza'] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Prospecto', 'Activo', 'En cierre', 'Moroso', 'Baja'] },
        { id: 'honorario', nombre: 'Honorario', tipo: 'dinero', rango: [400, 6000] },
        { id: 'alta', nombre: 'Alta', tipo: 'fecha', rango: [-400, 0] },
      ] },
    { id: 'declaraciones', titulo: 'Declaraciones', grupo: 0, icono: 'documento', vista: 'tablero', opciones: { por: 'estado', titulo: 'cliente', detalle: 'tipo' },
      campos: [
        { id: 'cliente', nombre: 'Cliente', tipo: 'texto' },
        { id: 'tipo', nombre: 'Tipo', tipo: 'texto', ejemplos: ['IVA mensual', 'Renta anual', 'Retenciones', 'Pago provisional', 'Informativa', 'Impuesto de planilla'] },
        { id: 'periodo', nombre: 'Periodo', tipo: 'texto', ejemplos: ['Enero 2026', 'Febrero 2026', 'Marzo 2026', 'Primer trimestre', 'Año 2025', 'Abril 2026'] },
        { id: 'vence', nombre: 'Vence', tipo: 'fecha', rango: [-15, 45] },
        { id: 'monto', nombre: 'Monto', tipo: 'dinero', rango: [500, 40000] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Por preparar', 'En revisión', 'Con observaciones', 'Presentada', 'Pagada'] },
      ] },
    { id: 'obligaciones', titulo: 'Vencimientos fiscales', grupo: 0, icono: 'reloj', vista: 'vencimientos', opciones: { fecha: 'vence', titulo: 'obligacion', detalle: 'cliente', dias: 30, estado: 'estado', excluir: ['Presentada'] },
      campos: [
        { id: 'obligacion', nombre: 'Obligación', tipo: 'texto', ejemplos: ['IVA del mes', 'Renta anual', 'Retenciones', 'Seguro social', 'Impuesto municipal', 'Declaración informativa'] },
        { id: 'cliente', nombre: 'Cliente', tipo: 'texto' },
        { id: 'periodo', nombre: 'Periodo', tipo: 'texto', ejemplos: ['Enero 2026', 'Febrero 2026', 'Marzo 2026', 'Primer trimestre', 'Año 2025', 'Abril 2026'] },
        { id: 'vence', nombre: 'Vence', tipo: 'fecha', rango: [-10, 60] },
        { id: 'monto', nombre: 'Monto', tipo: 'dinero', rango: [300, 25000] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Próxima', 'En preparación', 'Presentada', 'Vencida'] },
      ] },
    ...fijas,
  ],
}
