const fijas = [
  { id: 'actividad', titulo: 'Historial', grupo: 1, icono: 'actividad', vista: 'feed' },
  { id: 'equipo', titulo: 'Equipo', grupo: 1, icono: 'equipo', vista: 'equipo' },
  { id: 'automatizaciones', titulo: 'Automatizaciones', grupo: 2, icono: 'rayo', vista: 'interruptores' },
]

export default {
  id: 'seguros',
  nombre: 'Seguros',
  para: 'Agencias y corredores de seguros: pólizas activas, renovaciones y siniestros',
  asignacion: {
    rubros: ['servicios', 'otro'],
    ciclos: ['recurrente', 'mezcla', 'cotizacion'],
    objetivos: ['seguimientos', 'reportes', 'contactos', 'equipo'],
    negocios: ['Agencia de seguros general', 'Corredor de autos y hogar', 'Asesor de seguros de vida', 'Broker de seguros empresariales'],
  },
  // Renovaciones por vencer arriba junto al tablero de pólizas; abajo embudo de cartera y montos de siniestros por tipo.
  inicio: [
    { vista: 'vencimientos', seccion: 'renovaciones', opciones: { fecha: 'vence', titulo: 'poliza', detalle: 'cliente', dias: 45, estado: 'estado', excluir: ['Renovada', 'No renovó'] }, ancho: 8, alto: 2 },
    { vista: 'tablero', seccion: 'polizas', opciones: { por: 'estado', titulo: 'poliza', detalle: 'cliente' }, ancho: 4, alto: 2 },
    { vista: 'kpis', seccion: 'polizas', opciones: { por: 'estado', suma: 'prima' }, ancho: 12 },
    { vista: 'grafico', seccion: 'polizas', opciones: { tipo: 'embudo' }, ancho: 6, alto: 2 },
    { vista: 'grafico', seccion: 'siniestros', opciones: { tipo: 'barras', agrupar: 'tipo', valor: 'monto', funcion: 'suma' }, ancho: 6, alto: 2 },
  ],
  secciones: [
    { id: 'polizas', titulo: 'Pólizas', grupo: 0, icono: 'documento', vista: 'tablero', opciones: { por: 'estado', titulo: 'poliza', detalle: 'cliente' },
      campos: [
        { id: 'poliza', nombre: 'Póliza', tipo: 'texto', ejemplos: ['AUTO-4412', 'HOGAR-2210', 'VIDA-8891', 'SALUD-3340', 'EMP-1102', 'RC-5567'] },
        { id: 'cliente', nombre: 'Cliente', tipo: 'texto' },
        { id: 'ramo', nombre: 'Ramo', tipo: 'texto', ejemplos: ['Automóvil', 'Hogar', 'Vida', 'Salud', 'Empresarial', 'Responsabilidad civil'] },
        { id: 'prima', nombre: 'Prima', tipo: 'dinero', rango: [200, 15000] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Cotización', 'Activa', 'En mora', 'Suspendida', 'Cancelada'] },
        { id: 'inicio', nombre: 'Inicio', tipo: 'fecha', rango: [-365, 30] },
      ] },
    { id: 'renovaciones', titulo: 'Renovaciones', grupo: 0, icono: 'reloj', vista: 'vencimientos', opciones: { fecha: 'vence', titulo: 'poliza', detalle: 'cliente', dias: 45, estado: 'estado', excluir: ['Renovada', 'No renovó'] },
      campos: [
        { id: 'poliza', nombre: 'Póliza', tipo: 'texto', ejemplos: ['AUTO-4412', 'HOGAR-2210', 'VIDA-8891', 'SALUD-3340', 'EMP-1102', 'RC-5567'] },
        { id: 'cliente', nombre: 'Cliente', tipo: 'texto' },
        { id: 'vence', nombre: 'Vence', tipo: 'fecha', rango: [-5, 60] },
        { id: 'prima', nombre: 'Prima', tipo: 'dinero', rango: [250, 18000] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Por avisar', 'Contactado', 'En negociación', 'Renovada', 'No renovó'] },
      ] },
    { id: 'siniestros', titulo: 'Siniestros', grupo: 0, icono: 'actividad', vista: 'tabla',
      campos: [
        { id: 'poliza', nombre: 'Póliza', tipo: 'texto', ejemplos: ['AUTO-4412', 'HOGAR-2210', 'VIDA-8891', 'SALUD-3340', 'EMP-1102', 'RC-5567'] },
        { id: 'cliente', nombre: 'Cliente', tipo: 'texto' },
        { id: 'tipo', nombre: 'Tipo', tipo: 'texto', ejemplos: ['Choque ligero', 'Robo parcial', 'Daño por agua', 'Incendio', 'Gastos médicos', 'Responsabilidad tercero'] },
        { id: 'monto', nombre: 'Monto', tipo: 'dinero', rango: [500, 50000] },
        { id: 'fecha', nombre: 'Fecha', tipo: 'fecha', rango: [-60, 0] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Reportado', 'En peritaje', 'Aprobado', 'Pagado', 'Rechazado'] },
      ] },
    ...fijas,
  ],
}
