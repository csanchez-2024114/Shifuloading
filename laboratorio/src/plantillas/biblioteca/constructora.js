const fijas = [
  { id: 'actividad', titulo: 'Historial', grupo: 1, icono: 'actividad', vista: 'feed' },
  { id: 'equipo', titulo: 'Equipo', grupo: 1, icono: 'equipo', vista: 'equipo' },
  { id: 'automatizaciones', titulo: 'Automatizaciones', grupo: 2, icono: 'rayo', vista: 'interruptores' },
]

export default {
  id: 'constructora',
  nombre: 'Constructora',
  para: 'Constructoras y contratistas: obras en curso, avances de obra y proveedores',
  asignacion: {
    rubros: ['servicios', 'inmobiliaria', 'otro'],
    ciclos: ['cotizacion', 'mezcla', 'recurrente'],
    objetivos: ['cotizaciones', 'seguimientos', 'reportes', 'equipo'],
    negocios: ['Constructora residencial', 'Empresa de remodelaciones', 'Contratista de obras civiles'],
  },
  // El día a día: tablero de obras, entregas próximas y avance físico vs presupuesto por etapa.
  inicio: [
    { vista: 'tablero', seccion: 'obras', opciones: { por: 'estado', titulo: 'obra', detalle: 'cliente' }, ancho: 8, alto: 2 },
    { vista: 'vencimientos', seccion: 'obras', opciones: { fecha: 'entrega', titulo: 'obra', detalle: 'ubicacion', dias: 21, estado: 'estado', excluir: ['Entregada'] }, ancho: 4, alto: 2 },
    { vista: 'kpis', seccion: 'obras', opciones: { por: 'estado', suma: 'presupuesto' }, ancho: 12 },
    { vista: 'grafico', seccion: 'obras', opciones: { tipo: 'barras', agrupar: 'estado', valor: 'presupuesto', funcion: 'suma' }, ancho: 6, alto: 2 },
    { vista: 'grafico', seccion: 'avances', opciones: { tipo: 'linea-area', fecha: 'fecha', valor: 'porcentaje', funcion: 'promedio' }, ancho: 6, alto: 2 },
  ],
  secciones: [
    { id: 'obras', titulo: 'Obras', grupo: 0, icono: 'tablero', vista: 'tablero', opciones: { por: 'estado', titulo: 'obra', detalle: 'cliente' },
      campos: [
        { id: 'obra', nombre: 'Obra', tipo: 'texto', ejemplos: ['Casa Los Pinos', 'Edificio Centro', 'Bodega industrial', 'Remodelación oficinas', 'Ampliación local', 'Fraccionamiento etapa 2'] },
        { id: 'cliente', nombre: 'Cliente', tipo: 'texto' },
        { id: 'ubicacion', nombre: 'Ubicación', tipo: 'texto', ejemplos: ['Zona 10', 'Carretera al Atlántico', 'Condado Naranjo', 'Antigua Guatemala', 'Mixco', 'Villa Nueva'] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Cotización', 'Preparación', 'En obra', 'Acabados', 'Entregada'] },
        { id: 'entrega', nombre: 'Entrega', tipo: 'fecha', rango: [-10, 120] },
        { id: 'presupuesto', nombre: 'Presupuesto', tipo: 'dinero', rango: [25000, 850000] },
      ] },
    { id: 'avances', titulo: 'Avances', grupo: 0, icono: 'documento', vista: 'tabla',
      campos: [
        { id: 'obra', nombre: 'Obra', tipo: 'texto', ejemplos: ['Casa Los Pinos', 'Edificio Centro', 'Bodega industrial', 'Remodelación oficinas', 'Ampliación local', 'Fraccionamiento etapa 2'] },
        { id: 'fecha', nombre: 'Fecha', tipo: 'fecha', rango: [-365, 0] },
        { id: 'porcentaje', nombre: 'Avance %', tipo: 'numero', rango: [5, 100] },
        { id: 'actividad', nombre: 'Actividad', tipo: 'texto', ejemplos: ['Cimentación', 'Estructura', 'Instalaciones', 'Enchapes', 'Pintura', 'Entrega llaves'] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Reportado', 'Revisado', 'Aprobado', 'Con observaciones'] },
      ] },
    { id: 'proveedores', titulo: 'Proveedores', grupo: 0, icono: 'camion', vista: 'tabla',
      campos: [
        { id: 'nombre', nombre: 'Proveedor', tipo: 'texto' },
        { id: 'telefono', nombre: 'Teléfono', tipo: 'texto' },
        { id: 'material', nombre: 'Material', tipo: 'texto', ejemplos: ['Cemento y agregados', 'Acero estructural', 'Block y ladrillo', 'Tubería PVC', 'Cable eléctrico', 'Pintura y recubrimientos'] },
        { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Activo', 'En evaluación', 'Preferido', 'Suspendido'] },
      ] },
    ...fijas,
  ],
}
