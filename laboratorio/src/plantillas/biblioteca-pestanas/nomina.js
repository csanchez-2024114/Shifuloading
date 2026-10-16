export default {
  id: 'nomina',
  para: 'Llevar pagos de nómina por colaborador, periodo y si ya se dispersó el sueldo',
  palabras: ['nómina', 'sueldos', 'pago de personal', 'planilla', 'quincena'],
  seccion: {
    titulo: 'Nómina', icono: 'tarjeta', vista: 'tabla',
    campos: [
      { id: 'colaborador', nombre: 'Colaborador', tipo: 'texto', ejemplos: ['María López', 'Juan Pérez', 'Ana García', 'Pedro Ruiz', 'Laura Díaz'] },
      { id: 'periodo', nombre: 'Periodo', tipo: 'texto', ejemplos: ['1ra quincena ene', '2da quincena ene', 'Semana 3', 'Bono trimestre', 'Aguinaldo'] },
      { id: 'neto', nombre: 'Neto a pagar', tipo: 'dinero', rango: [3500, 28000] },
      { id: 'pago', nombre: 'Fecha pago', tipo: 'fecha', rango: [-90, 15] },
      { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Calculada', 'Autorizada', 'Pagada', 'Incidencia', 'Cancelada'] },
    ],
  },
  piezas: [
    { vista: 'tabla', opciones: { orden: 'pago' }, ancho: 8, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'columnas', fecha: 'pago', valor: 'neto', funcion: 'suma', agrupar: 'mes' }, ancho: 4, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'estadisticas', valor: 'neto' }, ancho: 6, alto: 2 },
  ],
}
