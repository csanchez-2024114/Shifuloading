/* Guardar (D57), lado del navegador: el id del espacio (en este navegador) y leer/guardar cada parte en el servidor.
 * Se guarda poco después de cada cambio (agrupando los seguidos) y, si falla la red, se reintenta en el siguiente cambio. */
const CLAVE = 'shifu-lab-espacio'

/** El id del espacio de este navegador (se crea la primera vez). Sin almacenamiento (modo privado), uno por pestaña. */
export function espacio() {
  try {
    let id = localStorage.getItem(CLAVE)
    if (!id) { id = crypto.randomUUID(); localStorage.setItem(CLAVE, id) }
    return id
  } catch { return (espacio.temporal ||= crypto.randomUUID()) }
}

export async function cargar() {
  try { const r = await fetch(`/api/lab/guardado/${espacio()}`); return r.ok ? await r.json() : {} } catch { return {} }
}

const pendientes = {}
/** Guarda una parte («experiencia», «crm» o «chat») ~0,6 s después del último cambio. */
export function guardar(parte, valor) {
  clearTimeout(pendientes[parte])
  pendientes[parte] = setTimeout(() => {
    fetch(`/api/lab/guardado/${espacio()}/${parte}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(valor) })
      .catch(() => { /* sin red: se vuelve a intentar con el próximo cambio */ })
  }, 600)
}

/** Empezar de nuevo: se borra el CRM guardado de este espacio. */
export async function borrarTodo() {
  for (const t of Object.values(pendientes)) clearTimeout(t)
  try { await fetch(`/api/lab/guardado/${espacio()}`, { method: 'DELETE' }) } catch { /* sin red: queda el archivo; el próximo guardado lo pisa */ }
}
