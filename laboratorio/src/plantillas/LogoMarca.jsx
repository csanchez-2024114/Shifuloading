/* El logo del negocio en el encabezado (D20). Lo usan el laboratorio (PlantillaCRM) y el CRM real (LogoNegocio). */
import { useEffect, useState } from 'react'

/** Logo del negocio. Si es oscuro y el tema es oscuro (o claro sobre claro), muestra una versión de alto contraste automática. */
export default function LogoMarca({ src, tema }) {
  const [luz, setLuz] = useState(null) // luminancia media de los píxeles visibles del logo (0 negro … 1 blanco)
  useEffect(() => {
    const img = new Image(); img.onload = () => {
      const c = document.createElement('canvas'); c.width = 64; c.height = Math.max(1, Math.round(64 * img.height / img.width))
      const x = c.getContext('2d'); x.drawImage(img, 0, 0, c.width, c.height)
      const d = x.getImageData(0, 0, c.width, c.height).data; let t = 0, n = 0
      for (let i = 0; i < d.length; i += 4) if (d[i + 3] > 40) { t += (0.2126 * d[i] + 0.7152 * d[i + 1] + 0.0722 * d[i + 2]) / 255; n++ }
      setLuz(n ? t / n : 0.5)
    }; img.src = src
  }, [src])
  const invertir = luz !== null && ((tema === 'oscuro' && luz < 0.35) || (tema === 'claro' && luz > 0.8))
  return <img className="pl-logo" src={src} alt="Logo del negocio" style={invertir ? { filter: tema === 'oscuro' ? 'brightness(0) invert(1)' : 'brightness(0)' } : undefined} />
}
