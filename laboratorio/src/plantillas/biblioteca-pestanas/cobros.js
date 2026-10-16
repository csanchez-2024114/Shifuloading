// Pestaña de la biblioteca (D30, nivel 2). Ejemplo de referencia para los agentes.
export default {
  id: 'cobros',
  para: 'Llevar lo que cada cliente te debe, cuándo vence y si ya pagó',
  palabras: ['cobros', 'cuentas por cobrar', 'pagos pendientes', 'quién me debe', 'deudas de clientes'],
  seccion: {
    titulo: 'Cobros', icono: 'tarjeta', vista: 'vencimientos',
    opciones: { fecha: 'vence', titulo: 'cliente', detalle: 'concepto', dias: 30, estado: 'estado', excluir: ['Pagado'] },
    campos: [
      { id: 'cliente', nombre: 'Cliente', tipo: 'texto' },
      { id: 'concepto', nombre: 'Concepto', tipo: 'texto', ejemplos: ['Factura de octubre', 'Anticipo del proyecto', 'Saldo pendiente', 'Mensualidad', 'Servicio extra'] },
      { id: 'monto', nombre: 'Monto', tipo: 'dinero', rango: [150, 12000] },
      { id: 'emitido', nombre: 'Emitido', tipo: 'fecha', rango: [-120, 0] },
      { id: 'vence', nombre: 'Vence', tipo: 'fecha', rango: [-20, 40] },
      { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Pendiente', 'Recordado', 'Pago parcial', 'Pagado', 'Incobrable'] },
    ],
  },
  piezas: [
    { vista: 'kpis', opciones: { por: 'estado', suma: 'monto', vencen: 'vence', dias: 7, estado: 'estado', excluir: ['Pagado'] }, ancho: 12 },
    { vista: 'vencimientos', opciones: { fecha: 'vence', titulo: 'cliente', detalle: 'monto', dias: 30, estado: 'estado', excluir: ['Pagado'] }, ancho: 8, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'dona', estado: 'estado', valor: 'monto', funcion: 'suma' }, ancho: 4, alto: 2 },
  ],
}
