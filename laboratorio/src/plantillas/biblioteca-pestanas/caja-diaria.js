export default {
  id: 'caja-diaria',
  para: 'Cuadrar entradas y salidas de cada día para saber cuánto quedó en caja al cierre',
  palabras: ['caja diaria', 'corte de caja', 'arqueo', 'movimientos del día', 'efectivo en caja'],
  seccion: {
    titulo: 'Caja diaria', icono: 'caja', vista: 'tabla',
    campos: [
      { id: 'concepto', nombre: 'Concepto', tipo: 'texto', ejemplos: ['Venta mostrador', 'Depósito banco', 'Retiro efectivo', 'Pago proveedor', 'Propina repartidor', 'Apertura turno'] },
      { id: 'tipo', nombre: 'Tipo', tipo: 'estado', opciones: ['Entrada', 'Salida', 'Ajuste', 'Cierre'] },
      { id: 'monto', nombre: 'Monto', tipo: 'dinero', rango: [50, 25000] },
      { id: 'fecha', nombre: 'Fecha', tipo: 'fecha', rango: [-90, 0] },
      { id: 'responsable', nombre: 'Responsable', tipo: 'texto', ejemplos: ['Ana caja 1', 'Turno mañana', 'Gerente', 'Cajero tarde', 'Auxiliar'] },
    ],
  },
  piezas: [
    { vista: 'kpis', opciones: { por: 'tipo', suma: 'monto', hoy: 'fecha' }, ancho: 12 },
    { vista: 'grafico', opciones: { tipo: 'cascada', fecha: 'fecha', valor: 'monto', funcion: 'suma', meses: 3 }, ancho: 8, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'calendario', fecha: 'fecha', funcion: 'conteo' }, ancho: 4, alto: 2 },
  ],
}
