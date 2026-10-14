/* Lo que va DENTRO del iframe del laboratorio: un CRM a pantalla completa con la plantilla, los datos y el tema de la URL.
 * Va en un iframe para que las @media respondan al ancho elegido, igual que en un teléfono o una tablet de verdad. */
import { useEffect, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import PlantillaCRM from '../plantillas/PlantillaCRM'
import { plantillaPorId } from '../plantillas/semillas'
import { datosEjemplo } from '../plantillas/datosEjemplo'
import { ROTAS } from './rotas'

export default function VistaPage() {
  const [q] = useSearchParams()
  const id = q.get('plantilla') || 'embudo'
  const nivel = q.get('datos') || 'pocos'
  const tema = q.get('tema') === 'claro' ? 'claro' : 'oscuro'
  const estilo = q.get('estilo') || 'actual'
  const plantilla = plantillaPorId(id) || ROTAS.find((p) => p.id === id)
  const datos = useMemo(() => (plantilla ? datosEjemplo(plantilla, nivel) : null), [plantilla, nivel])
  useEffect(() => { document.documentElement.style.colorScheme = tema === 'claro' ? 'light' : 'dark' }, [tema])
  if (!plantilla) return <p style={{ padding: 24 }}>No existe la plantilla «{id}».</p>
  return <PlantillaCRM key={`${id}-${nivel}`} plantilla={plantilla} datos={datos} tema={tema} estilo={estilo} negocio="Negocio de prueba" />
}
