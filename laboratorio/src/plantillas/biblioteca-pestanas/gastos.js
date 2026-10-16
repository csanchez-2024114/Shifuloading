export default {
  id: 'gastos',
  para: 'Registrar en qué se va el dinero del negocio y revisar gastos por categoría cada mes',
  palabras: ['gastos', 'egresos', 'en qué gasto', 'control de gastos', 'salidas de dinero'],
  seccion: {
    titulo: 'Gastos', icono: 'caja', vista: 'tabla',
    campos: [
      { id: 'concepto', nombre: 'Concepto', tipo: 'texto', ejemplos: ['Renta local', 'Nómina quincena', 'Internet y teléfono', 'Gasolina reparto', 'Publicidad redes', 'Material de oficina'] },
      { id: 'categoria', nombre: 'Categoría', tipo: 'texto', ejemplos: ['Operación', 'Nómina', 'Marketing', 'Logística', 'Impuestos', 'Mantenimiento'] },
      { id: 'monto', nombre: 'Monto', tipo: 'dinero', rango: [80, 45000] },
      { id: 'fecha', nombre: 'Fecha', tipo: 'fecha', rango: [-120, 5] },
      { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Pendiente', 'Pagado', 'Programado', 'En revisión', 'Rechazado'] },
    ],
  },
  piezas: [
    { vista: 'grafico', opciones: { tipo: 'columnas', fecha: 'fecha', valor: 'monto', funcion: 'suma', agrupar: 'mes' }, ancho: 8, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'barras', estado: 'estado', valor: 'monto', funcion: 'suma' }, ancho: 4, alto: 2 },
    { vista: 'tabla', opciones: { orden: 'fecha' }, ancho: 12, alto: 2 },
  ],
}
