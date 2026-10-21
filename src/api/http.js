import { API_URL, CLAVE_REFRESCO, CLAVE_TOKEN } from './config'

export class ErrorApi extends Error {
  constructor(estado, mensaje, detalle) { super(mensaje); this.estado = estado; this.detalle = detalle }
}

const leer = (k) => { try { return localStorage.getItem(k) } catch { return null } }
const poner = (k, v) => { try { localStorage.setItem(k, v) } catch { /* sin almacenamiento */ } }
const quitar = (k) => { try { localStorage.removeItem(k) } catch { /* sin almacenamiento */ } }

/** Las dos llaves de la sesión: la de acceso (corta, va en cada petición) y la de renovación (larga, solo para pedir otra de acceso). */
export const token = {
  acceso: () => leer(CLAVE_TOKEN),
  refresco: () => leer(CLAVE_REFRESCO),
  guardar: ({ acceso, refresco }) => { if (acceso) poner(CLAVE_TOKEN, acceso); if (refresco) poner(CLAVE_REFRESCO, refresco) },
  borrar: () => { quitar(CLAVE_TOKEN); quitar(CLAVE_REFRESCO) },
}

/** Aviso global: la sesión ya no se puede renovar. La app lo escucha (App.jsx) y manda al inicio de sesión. */
export const SESION_VENCIDA = 'shifu:sesion-vencida'

let renovando = null // si varias peticiones fallan a la vez, se renueva una sola vez y todas esperan el mismo resultado

async function renovar() {
  const r = token.refresco()
  if (!r) return false
  if (!renovando) {
    renovando = fetch(`${API_URL}/auth/refresh`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ refresh_token: r }) })
      .then(async (res) => {
        if (!res.ok) return false
        const d = await res.json().catch(() => null)
        if (!d?.access_token) return false
        token.guardar({ acceso: d.access_token, refresco: d.refresh_token })
        return true
      })
      .catch(() => false)
      .finally(() => { renovando = null })
  }
  return renovando
}

/** Texto para mostrar a partir de lo que responde el servidor: { mensaje } en el CRM, { detail } (texto o lista) en el resto. */
function textoDeError(datos) {
  if (typeof datos?.mensaje === 'string') return datos.mensaje
  if (typeof datos?.detail === 'string') return datos.detail
  if (Array.isArray(datos?.detail) && datos.detail[0]?.msg) return datos.detail[0].msg
  return 'Algo salió mal'
}

async function enviar(metodo, ruta, cuerpo) {
  const t = token.acceso()
  try {
    return await fetch(`${API_URL}${ruta}`, {
      method: metodo,
      headers: { 'Content-Type': 'application/json', ...(t ? { Authorization: `Bearer ${t}` } : {}) },
      body: cuerpo === undefined ? undefined : JSON.stringify(cuerpo),
    })
  } catch {
    throw new ErrorApi(0, 'Sin conexión con el servidor')
  }
}

/** Hace la petición con la sesión: si la llave de acceso venció, la renueva una vez y repite. */
async function conSesion(metodo, ruta, cuerpo, publico) {
  let res = await enviar(metodo, ruta, cuerpo)
  if (res.status === 401 && !publico) {
    if (await renovar()) {
      res = await enviar(metodo, ruta, cuerpo)
    } else {
      token.borrar()
      window.dispatchEvent(new Event(SESION_VENCIDA))
      throw new ErrorApi(401, 'Tu sesión venció. Inicia sesión de nuevo.')
    }
  }
  return res
}

/** Una sola puerta de salida hacia el servidor: JSON, token en la cabecera, renovación automática de la sesión y errores uniformes.
 *  `publico: true` es para las rutas de entrar (login, registro), que no llevan sesión ni se reintentan. */
export async function pedir(metodo, ruta, cuerpo, { publico = false } = {}) {
  const res = await conSesion(metodo, ruta, cuerpo, publico)
  if (res.status === 204) return null
  const datos = await res.json().catch(() => null)
  if (!res.ok) throw new ErrorApi(res.status, textoDeError(datos), datos)
  return datos
}

/** El nombre que manda el servidor en Content-Disposition (filename* en UTF-8 primero; si no, filename). */
function nombreDeArchivo(cabecera) {
  const utf = /filename\*=UTF-8''([^;]+)/i.exec(cabecera || '')
  if (utf) { try { return decodeURIComponent(utf[1]) } catch { /* sigue con el simple */ } }
  return /filename="([^"]+)"/i.exec(cabecera || '')?.[1] || null
}

/** Un archivo del servidor (GET con la sesión): { blob, nombre }. Los errores, como en `pedir`. */
export async function pedirArchivo(ruta) {
  const res = await conSesion('GET', ruta)
  if (!res.ok) {
    const datos = await res.json().catch(() => null)
    throw new ErrorApi(res.status, textoDeError(datos), datos)
  }
  return { blob: await res.blob(), nombre: nombreDeArchivo(res.headers.get('Content-Disposition')) }
}
