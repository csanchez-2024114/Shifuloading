/* Lo que va DENTRO del iframe del laboratorio: un CRM a pantalla completa con la plantilla, los datos y el tema de la URL.
 * Va en un iframe para que las @media respondan al ancho elegido, igual que en un teléfono o una tablet de verdad. */
import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import PlantillaCRM from '../plantillas/PlantillaCRM'
import { GaleriaGraficos } from '../plantillas/graficos'
import { VelContext } from '../plantillas/vistas'
import { fijarRegion } from '../plantillas/regional'
import { plantillaPorId } from '../plantillas/semillas'
import { datosEjemplo } from '../plantillas/datosEjemplo'
import { ROTAS } from './rotas'

export default function VistaPage() {
  const [q] = useSearchParams()
  const id = q.get('plantilla') || 'embudo'
  const recorrido = q.get('recorrido') === '1'
  const [nivel, setNivel] = useState(q.get('datos') || (recorrido ? 'muchos' : 'pocos'))
  const nivelInicial = q.get('datos') || 'pocos'
  const tema = q.get('tema') === 'claro' ? 'claro' : 'oscuro'
  const estilo = q.get('estilo') || 'vivo-compacto'
  const vel = Number(q.get('vel')) || 2.2
  const pais = q.get('pais') || 'gt'
  const plantilla = plantillaPorId(id) || ROTAS.find((p) => p.id === id)
  const datos = useMemo(() => (plantilla ? datosEjemplo(plantilla, nivel) : null), [plantilla, nivel])
  useEffect(() => { document.documentElement.style.colorScheme = tema === 'claro' ? 'light' : 'dark' }, [tema])
  if (!plantilla) return <p style={{ padding: 24 }}>No existe la plantilla «{id}».</p>
  if (q.get('galeria')) { fijarRegion(pais); return <VelContext.Provider value={vel}><GaleriaGraficos key={pais} plantilla={plantilla} datos={datos} tema={tema} vel={vel} /></VelContext.Provider> }
  return <PlantillaCRM key={`${id}-${nivelInicial}-${estilo}-${vel}-${pais}`} recorrido={recorrido} onBorrarEjemplos={() => setNivel('vacio')} plantilla={plantilla} datos={datos} nivel={nivel} tema={tema} estilo={estilo} vel={vel} pais={pais} negocio="Negocio de prueba" />
}
