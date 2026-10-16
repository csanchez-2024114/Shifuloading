export default {
  id: 'metas-de-venta',
  para: 'Poner metas de venta por periodo y ver cuánto llevas contra lo que te propusiste',
  palabras: ['metas de venta', 'objetivos comerciales', 'cuota de ventas', 'meta mensual', 'cuánto falta para la meta'],
  seccion: {
    titulo: 'Metas de venta', icono: 'tablero', vista: 'tabla',
    campos: [
      { id: 'periodo', nombre: 'Periodo', tipo: 'texto', ejemplos: ['Enero 2025', 'Q1 2025', 'Semana 12', 'Black Friday', 'Temporada escolar'] },
      { id: 'responsable', nombre: 'Responsable', tipo: 'texto', ejemplos: ['Tienda centro', 'Vendedor Carlos', 'Canal online', 'Sucursal norte', 'Equipo completo'] },
      { id: 'meta', nombre: 'Meta', tipo: 'dinero', rango: [15000, 500000] },
      { id: 'avance', nombre: 'Avance', tipo: 'dinero', rango: [5000, 480000] },
      { id: 'cierre', nombre: 'Cierre', tipo: 'fecha', rango: [-60, 60] },
      { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Planeada', 'En curso', 'En riesgo', 'Lograda', 'No alcanzada'] },
    ],
  },
  piezas: [
    { vista: 'grafico', opciones: { tipo: 'meta', fecha: 'cierre', valor: 'avance', funcion: 'suma', meta: 'meta' }, ancho: 4, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'medidor', estado: 'estado' }, ancho: 4, alto: 2 },
    { vista: 'tabla', opciones: {}, ancho: 8, alto: 2 },
  ],
}
