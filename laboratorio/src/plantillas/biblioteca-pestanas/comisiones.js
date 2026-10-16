export default {
  id: 'comisiones',
  para: 'Calcular y pagar comisiones de tu equipo según ventas cerradas y reglas que definas',
  palabras: ['comisiones', 'pago por venta', 'comisiones vendedores', 'bonos por cierre', 'cuánto les toca'],
  seccion: {
    titulo: 'Comisiones', icono: 'tarjeta', vista: 'tablero',
    opciones: { por: 'estado', titulo: 'vendedor', detalle: 'venta' },
    campos: [
      { id: 'vendedor', nombre: 'Vendedor', tipo: 'texto', ejemplos: ['Carlos M.', 'Equipo norte', 'María ventas', 'Jorge mostrador', 'Laura digital'] },
      { id: 'venta', nombre: 'Venta', tipo: 'texto', ejemplos: ['Contrato anual', 'Pedido #882', 'Renovación', 'Paquete premium', 'Mayoreo zona sur'] },
      { id: 'base', nombre: 'Base', tipo: 'dinero', rango: [500, 40000] },
      { id: 'comision', nombre: 'Comisión', tipo: 'dinero', rango: [50, 8000] },
      { id: 'fecha', nombre: 'Fecha', tipo: 'fecha', rango: [-90, 10] },
      { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Calculada', 'Aprobada', 'Pagada', 'En disputa', 'Anulada'] },
    ],
  },
  piezas: [
    { vista: 'tablero', opciones: { por: 'estado', titulo: 'vendedor', detalle: 'comision' }, ancho: 8, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'barras', estado: 'estado', valor: 'comision', funcion: 'suma' }, ancho: 4, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'posiciones', texto: 'vendedor', valor: 'comision', funcion: 'suma', top: 5 }, ancho: 6, alto: 2 },
  ],
}
