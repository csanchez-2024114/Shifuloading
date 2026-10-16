export default {
  id: 'documentos',
  para: 'Guardar documentos clave del negocio y saber cuáles están vigentes o faltan por subir',
  palabras: ['documentos', 'archivos del negocio', 'expedientes', 'papeles importantes', 'repositorio de docs'],
  seccion: {
    titulo: 'Documentos', icono: 'documento', vista: 'tabla',
    campos: [
      { id: 'nombre', nombre: 'Nombre', tipo: 'texto', ejemplos: ['Acta constitutiva', 'RFC empresa', 'Póliza seguro', 'Contrato arrendamiento', 'Licencia sanitaria'] },
      { id: 'categoria', nombre: 'Categoría', tipo: 'texto', ejemplos: ['Legal', 'Fiscal', 'RH', 'Operación', 'Marketing', 'Seguros'] },
      { id: 'vigencia', nombre: 'Vigencia', tipo: 'fecha', rango: [-30, 365] },
      { id: 'responsable', nombre: 'Responsable', tipo: 'texto', ejemplos: ['Contador', 'Gerencia', 'RH', 'Legal externo', 'Administración'] },
      { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Vigente', 'Por actualizar', 'Vencido', 'En trámite', 'Archivado'] },
    ],
  },
  piezas: [
    { vista: 'tabla', opciones: { orden: 'nombre' }, ancho: 8, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'arbol', estado: 'categoria', funcion: 'conteo' }, ancho: 4, alto: 2 },
    { vista: 'vencimientos', opciones: { fecha: 'vigencia', titulo: 'nombre', detalle: 'categoria', dias: 45, estado: 'estado', excluir: ['Archivado'] }, ancho: 12, alto: 2 },
  ],
}
