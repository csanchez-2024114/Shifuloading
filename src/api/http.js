import { API_URL, CLAVE_TOKEN } from './config'

export class ErrorApi extends Error {
  constructor(estado, mensaje, detalle) { super(mensaje); this.estado = estado; this.detalle = detalle }
}

export const token = {
  leer: () => { try { return localStorage.getItem(CLAVE_TOKEN) } catch { return null } },
  guardar: (t) => { try { localStorage.setItem(CLAVE_TOKEN, t) } catch { /* sin almacenamiento */ } },
  borrar: () => { try { localStorage.removeItem(CLAVE_TOKEN) } catch { /* sin almacenamiento */ } },
}

/** Una sola puerta de salida hacia el servidor: JSON, token en la cabecera y errores uniformes. */
export async function pedir(metodo, ruta, cuerpo) {
  const t = token.leer()
  let res
  try {
    res = await fetch(`${API_URL}${ruta}`, {
      method: metodo,
      headers: { 'Content-Type': 'application/json', ...(t ? { Authorization: `Bearer ${t}` } : {}) },
      body: cuerpo === undefined ? undefined : JSON.stringify(cuerpo),
    })
  } catch {
    throw new ErrorApi(0, 'Sin conexión con el servidor')
  }
  if (res.status === 204) return null
  const datos = await res.json().catch(() => null)
  if (!res.ok) throw new ErrorApi(res.status, datos?.mensaje || 'Algo salió mal', datos)
  return datos
}
