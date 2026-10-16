const fijas = [
  { id: 'actividad', titulo: 'Historial', grupo: 1, icono: 'actividad', vista: 'feed' },
  { id: 'equipo', titulo: 'Equipo', grupo: 1, icono: 'equipo', vista: 'equipo' },
  { id: 'automatizaciones', titulo: 'Automatizaciones', grupo: 2, icono: 'rayo', vista: 'interruptores' },
]

export default {
  id: 'software-saas',
  nombre: 'Software y SaaS',
  para: 'Empresas de software: cuentas activas, demos agendadas y renovaciones de suscripción',
  asignacion: {
    rubros: ['tecnologia', 'servicios'],
    ciclos: ['recurrente', 'cotizacion', 'mezcla'],
    objetivos: ['seguimientos', 'reportes', 'integraciones', 'equipo'],
    negocios: ['Plataforma SaaS B2B', 'Software a medida con soporte', 'Distribuidor de licencias en la nube'],
  },
  // Pipeline de cuentas y renovaciones arriba; agenda de demos y embudo de conversión abajo; altas de clientes en el tiempo.
  inicio: [
    { vista: 'tablero', seccion: 'cuentas', opciones: { por: 'estado', titulo: 'empresa', detalle: 'plan' }, ancho: 8, alto: 3 },
    { vista: 'vencimientos', seccion: 'renovaciones', opciones: { fecha: 'vence', titulo: 'empresa', detalle: 'plan', dias: 45, estado: 'estado', excluir: ['Renovada', 'Perdida'] }, ancho: 4, alto: 3 },
    { vista: 'agenda', seccion: 'demos', opciones: { fecha: 'fecha', hora: 'hora', titulo: 'empresa', detalle: 'producto', dias: 14 }, ancho: 6, alto: 2 },
    { vista: 'grafico', seccion: 'demos', opciones: { tipo: 'embudo' }, ancho: 3, alto: 2 },
    { vista: 'grafico', seccion: 'cuentas', opciones: { tipo: 'linea-area', fecha: 'alta' }, ancho: 3, alto: 2 },
  ],
  secciones: [
    { id: 'cuentas', titulo: 'Cuentas', grupo: 0, icono: 'tablero', vista: 'tablero', opciones: { por: 'estado', titulo: 'empresa', detalle: 'plan' },
      campos: [
        { id: 'empresa', nombre: 'Empresa', tipo: 'texto' },
        { id: 'contacto', nombre: 'Contacto', tipo: 'texto', ejemplos: ['Ana López', 'Carlos Méndez', 'María Ruiz', 'Pedro Soto', 'Laura Vega', 'Diego Campos'] },
        { id: 'plan', nombre: 'Plan', tipo: 'texto', ejemplos: ['Básico', 'Profesional', 'Empresa', 'Anual', 'Mensual', 'Enterprise'] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Prueba', 'Activa', 'En riesgo', 'Pausada', 'Cancelada'] },
        { id: 'mrr', nombre: 'MRR', tipo: 'dinero', rango: [29, 2500] },
        { id: 'alta', nombre: 'Alta', tipo: 'fecha', rango: [-330, 0] },
        { id: 'renovacion', nombre: 'Renovación', tipo: 'fecha', rango: [-15, 90] },
      ] },
    { id: 'demos', titulo: 'Demos', grupo: 0, icono: 'calendario', vista: 'agenda', opciones: { fecha: 'fecha', hora: 'hora', titulo: 'empresa', detalle: 'producto', dias: 14 },
      campos: [
        { id: 'empresa', nombre: 'Empresa', tipo: 'texto' },
        { id: 'producto', nombre: 'Producto', tipo: 'texto', ejemplos: ['CRM', 'Facturación', 'Inventario', 'Portal clientes', 'App móvil', 'Módulo reportes'] },
        { id: 'fecha', nombre: 'Fecha', tipo: 'fecha', rango: [-7, 21] },
        { id: 'hora', nombre: 'Hora', tipo: 'hora' },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Agendada', 'Realizada', 'Reprogramada', 'No asistió', 'Convertida'] },
        { id: 'responsable', nombre: 'Responsable', tipo: 'texto', ejemplos: ['Ventas norte', 'Ventas centro', 'Soporte comercial', 'Gerencia', 'Partner canal', 'Inside sales'] },
      ] },
    { id: 'renovaciones', titulo: 'Renovaciones', grupo: 0, icono: 'reloj', vista: 'vencimientos', opciones: { fecha: 'vence', titulo: 'empresa', detalle: 'plan', dias: 45, estado: 'estado', excluir: ['Renovada', 'Perdida'] },
      campos: [
        { id: 'empresa', nombre: 'Empresa', tipo: 'texto' },
        { id: 'plan', nombre: 'Plan', tipo: 'texto', ejemplos: ['Básico anual', 'Pro mensual', 'Empresa anual', 'Add-on usuarios', 'Soporte premium', 'Paquete completo'] },
        { id: 'vence', nombre: 'Vence', tipo: 'fecha', rango: [-5, 60] },
        { id: 'monto', nombre: 'Monto', tipo: 'dinero', rango: [199, 18000] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Por renovar', 'En negociación', 'Renovada', 'Perdida'] },
      ] },
    ...fijas,
  ],
}
