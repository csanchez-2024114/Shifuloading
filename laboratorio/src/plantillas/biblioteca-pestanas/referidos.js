export default {
  id: 'referidos',
  para: 'Dar seguimiento a clientes que refieren otros y las recompensas que les corresponden',
  palabras: ['referidos', 'programa de referidos', 'recomienda y gana', 'clientes que refieren', 'bonos por referencia'],
  seccion: {
    titulo: 'Referidos', icono: 'usuarios', vista: 'tabla',
    campos: [
      { id: 'referente', nombre: 'Referente', tipo: 'texto', ejemplos: ['Cliente VIP Ana', 'Socio comercial', 'Empleado ventas', 'Distribuidor norte', 'Amigo del dueño'] },
      { id: 'referido', nombre: 'Referido', tipo: 'texto', ejemplos: ['Nuevo cliente Pyme', 'Familiar del referente', 'Empresa vecina', 'Contacto WhatsApp', 'Lead feria'] },
      { id: 'recompensa', nombre: 'Recompensa', tipo: 'dinero', rango: [100, 5000] },
      { id: 'fecha', nombre: 'Fecha', tipo: 'fecha', rango: [-120, 10] },
      { id: 'estado', nombre: 'Estado', tipo: 'estado', opciones: ['Registrado', 'En prueba', 'Compró', 'Recompensa pendiente', 'Pagada', 'Inválido'] },
    ],
  },
  piezas: [
    { vista: 'tabla', opciones: { orden: 'fecha' }, ancho: 8, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'embudo', estado: 'estado', funcion: 'conteo' }, ancho: 4, alto: 2 },
    { vista: 'grafico', opciones: { tipo: 'columnas', fecha: 'fecha', valor: 'recompensa', funcion: 'suma', agrupar: 'mes' }, ancho: 6, alto: 2 },
  ],
}
