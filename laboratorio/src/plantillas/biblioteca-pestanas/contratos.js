export default {
  id: 'contratos',
  para: 'Vigilar contratos con clientes o proveedores y cuándo toca renovar o revisar',
  palabras: ['contratos', 'vigencia de contrato', 'renovaciones', 'acuerdos firmados', 'contratos por vencer'],
  seccion: {
    titulo: 'Contratos', icono: 'documento', vista: 'vencimientos',
    opciones: { fecha: 'vence', titulo: 'parte', detalle: 'tipo', dias: 60, estado: 'estado', excluir: ['Vencido', 'Terminado'] },
    campos: [
      { id: 'parte', nombre: 'Parte', tipo: 'texto', ejemplos: ['Cliente Corporativo SA', 'Arrendador local', 'Proveedor IT', 'Franquiciante', 'Servicios limpieza'] },
      { id: 'tipo', nombre: 'Tipo', tipo: 'texto', ejemplos: ['Servicio mensual', 'Arrendamiento', 'Distribución', 'Mantenimiento', 'Confidencialidad'] },
      { id: 'monto', nombre: 'Monto mensual', tipo: 'dinero', rango: [2000, 120000] },
      { id: 'inicio', nombre: 'Inicio', tipo: 'fecha', rango: [-400, -30] },
      { id: 'vence', nombre: 'Vence', tipo: 'fecha', rango: [-30, 180] },
      { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Vigente', 'Por renovar', 'En negociación', 'Renovado', 'Vencido', 'Terminado'] },
    ],
  },
  piezas: [
    { vista: 'vencimientos', opciones: { fecha: 'vence', titulo: 'parte', detalle: 'tipo', dias: 60, estado: 'estado', excluir: ['Vencido', 'Terminado'] }, ancho: 8, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'kpi', fecha: 'vence', valor: 'monto', funcion: 'suma' }, ancho: 4, alto: 2 },
    { vista: 'kpis', opciones: { por: 'estado', suma: 'monto', vencen: 'vence', dias: 30, estado: 'estado', excluir: ['Vencido', 'Terminado'] }, ancho: 12 },
  ],
}
