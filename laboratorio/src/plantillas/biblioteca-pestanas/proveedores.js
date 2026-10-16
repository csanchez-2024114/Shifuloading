export default {
  id: 'proveedores',
  para: 'Tener a la mano quién te surte, qué vende y cómo contactarlo cuando hace falta pedir',
  palabras: ['proveedores', 'quién me surte', 'lista de proveedores', 'contactos de compras', 'distribuidores'],
  seccion: {
    titulo: 'Proveedores', icono: 'usuarios', vista: 'tabla',
    campos: [
      { id: 'proveedor', nombre: 'Proveedor', tipo: 'texto' },
      { id: 'rubro', nombre: 'Rubro', tipo: 'texto', ejemplos: ['Papelería', 'Alimentos', 'Refacciones', 'Uniformes', 'Empaques', 'Químicos de limpieza'] },
      { id: 'contacto', nombre: 'Contacto', tipo: 'texto', ejemplos: ['Lic. Martínez', 'Sra. López ventas', 'WhatsApp bodega', 'Ejecutivo zona norte', 'Mostrador central'] },
      { id: 'plazo', nombre: 'Plazo de entrega', tipo: 'numero', rango: [1, 21] },
      { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Activo', 'En evaluación', 'Preferente', 'Suspendido', 'Nuevo'] },
    ],
  },
  piezas: [
    { vista: 'tabla', opciones: { orden: 'proveedor' }, ancho: 8, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'pastel', estado: 'estado', funcion: 'conteo' }, ancho: 4, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'posiciones', texto: 'rubro', funcion: 'conteo', top: 5 }, ancho: 6, alto: 2 },
  ],
}
