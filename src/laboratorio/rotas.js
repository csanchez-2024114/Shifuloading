/* Plantillas rotas a propósito: sirven para comprobar que el cerco (validar.js) las rechaza con un mensaje claro. Solo laboratorio. */
import { PLANTILLAS } from '../plantillas/semillas'

const base = PLANTILLAS.find((p) => p.id === 'simple')

export const ROTAS = [
  { ...base, id: 'rota-vista', nombre: 'Rota: vista que no existe',
    secciones: base.secciones.map((s) => (s.id === 'clientes' ? { ...s, vista: 'calendario' } : s)) },
  { ...base, id: 'rota-tablero', nombre: 'Rota: tablero sin campo de estado',
    secciones: base.secciones.map((s) => (s.id === 'tareas' ? { ...s, opciones: { por: 'tarea', titulo: 'tarea' } } : s)) },
  { ...base, id: 'rota-inicio', nombre: 'Rota: inicio apunta a una sección inexistente',
    inicio: [...base.inicio, { vista: 'agenda', seccion: 'citas', opciones: { fecha: 'fecha' } }] },
]
