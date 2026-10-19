/* El logo del negocio en el encabezado del CRM (lista 38). El CRM solo trae `marca.logo_id`; la imagen se pide aparte
 * (GET /crm/logo/{id}) una sola vez por id: el id sale del contenido, así que la misma imagen nunca se vuelve a bajar.
 * Mientras llega, o si no se puede leer, se ve `respaldo` (el logo de Shifu): nunca un hueco ni una imagen rota. */
import { useEffect, useState } from 'react'
import LogoMarca from '@lab/plantillas/LogoMarca'
import { crm as api } from '../../api'

const cache = new Map() // id → Promise<data URL | null>
const leer = (id) => {
  if (!cache.has(id)) cache.set(id, api.logo(id).then((r) => r?.imagen || null).catch(() => { cache.delete(id); return null }))
  return cache.get(id)
}

export default function LogoNegocio({ id, tema, respaldo = null }) {
  const [src, setSrc] = useState(null)
  useEffect(() => {
    let vivo = true
    setSrc(null)
    if (id) leer(id).then((s) => { if (vivo) setSrc(s) })
    return () => { vivo = false }
  }, [id])
  return src ? <LogoMarca src={src} tema={tema} /> : respaldo
}
