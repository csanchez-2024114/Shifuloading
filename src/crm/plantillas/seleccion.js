/* Las piezas elegidas en el lienzo (D39: doble clic en PC, mantener presionado en táctil; `useSeleccion` del laboratorio)
 * esperan aquí hasta el siguiente mensaje del chat, que las lleva en `contexto.seleccion` con el formato del laboratorio:
 * [{ tipo: 'bloque', id, nombre }]. Las deja DisenoCrm (que oye 'lab-piezas'), las muestra ChatDiseno y las toma CrmPage
 * al enviar. Al soltarlas se avisa con 'lab-piezas-usadas', y `useSeleccion` borra su marca del lienzo. */
import { useSyncExternalStore } from 'react'

let elegidas = []
const oyentes = new Set()
const avisar = () => { for (const f of oyentes) f() }

export const fijarPiezas = (piezas) => { elegidas = Array.isArray(piezas) ? piezas : []; avisar() }
export const soltarPiezas = () => { elegidas = []; avisar(); window.dispatchEvent(new Event('lab-piezas-usadas')) }
const suscribir = (f) => { oyentes.add(f); return () => oyentes.delete(f) }
export const usePiezas = () => useSyncExternalStore(suscribir, () => elegidas)

/** Para el mensaje que sale: el prefijo que ve la persona en su burbuja (como en el laboratorio) y lo que va al servidor.
 * null si no hay nada elegido. Las suelta: cada selección va con un solo mensaje. */
export function tomarPiezas() {
  if (!elegidas.length) return null
  const seleccion = elegidas.map(({ tipo, id, nombre }) => ({ tipo, id, nombre }))
  soltarPiezas()
  return { prefijo: `[${seleccion.map((x) => x.nombre || x.tipo).join(', ')}] `, contexto: { seleccion } }
}
