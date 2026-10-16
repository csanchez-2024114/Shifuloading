export default {
  id: 'cotizaciones',
  para: 'Seguir cada cotización que mandas, cuánto vale y en qué paso va hasta que la aprueban',
  palabras: ['cotizaciones', 'presupuestos', 'propuestas de precio', 'cotizar a clientes', 'ofertas enviadas'],
  seccion: {
    titulo: 'Cotizaciones', icono: 'documento', vista: 'tablero',
    opciones: { por: 'estado', titulo: 'cliente', detalle: 'concepto' },
    campos: [
      { id: 'cliente', nombre: 'Cliente', tipo: 'texto' },
      { id: 'concepto', nombre: 'Concepto', tipo: 'texto', ejemplos: ['Mantenimiento anual', 'Paquete básico web', 'Evento corporativo', 'Remodelación baño', 'Curso empresarial'] },
      { id: 'monto', nombre: 'Monto', tipo: 'dinero', rango: [800, 85000] },
      { id: 'enviada', nombre: 'Enviada', tipo: 'fecha', rango: [-90, 15] },
      { id: 'vence', nombre: 'Válida hasta', tipo: 'fecha', rango: [-30, 45] },
      { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Borrador', 'Enviada', 'En revisión', 'Aceptada', 'Rechazada', 'Vencida'] },
    ],
  },
  piezas: [
    { vista: 'kpis', opciones: { por: 'estado', suma: 'monto', vencen: 'vence', dias: 7, estado: 'estado', excluir: ['Aceptada', 'Rechazada', 'Vencida'] }, ancho: 12 },
    { vista: 'tablero', opciones: { por: 'estado', titulo: 'cliente', detalle: 'monto' }, ancho: 8, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'embudo', estado: 'estado', funcion: 'conteo' }, ancho: 4, alto: 2 },
  ],
}
