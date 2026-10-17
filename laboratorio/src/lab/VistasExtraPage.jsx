/* Página de laboratorio: muestra las vistas extra en 4 tamaños de bloque (no conectada a rutas). */
import { useMemo } from 'react'
import { COMPONENTES_EXTRA } from '../plantillas/vistas-extra'
import { camposDe } from '../plantillas/validar'
import { registrosDe } from '../plantillas/datosEjemplo'
import { AnimarContext } from '../plantillas/vistas'
import '@base/crm.css'
import '@base/crm-extra.css'
import '../plantillas/plantillas.css'
import '../plantillas/estilos.css'
import '../plantillas/vistas-extra.css'

const TAMANOS = [
  { id: 'xs', w: 220, h: 170 },
  { id: 's', w: 340, h: 260 },
  { id: 'm', w: 520, h: 360 },
  { id: 'l', w: 900, h: 380 },
]

/** Opciones razonables según los tipos de campo de la sección (como elegiría la IA). */
function opcionesExtra(campos) {
  const de = (t) => campos.find((c) => c.tipo === t)?.id
  const textos = campos.filter((c) => !['estado', 'fecha', 'hora', 'numero', 'dinero'].includes(c.tipo)).map((c) => c.id)
  const titulo = textos[0] || campos[0]?.id
  const detalle = textos[1]
  const estado = de('estado')
  const cEstado = campos.find((c) => c.id === estado)
  const terminados = cEstado?.opciones?.slice(-2) || []
  const urgentes = cEstado?.opciones?.slice(0, 1) || []

  return [
    { vista: 'calendario_mes', opciones: { fecha: de('fecha'), titulo, estado } },
    { vista: 'tablero_dinero', opciones: { por: estado, suma: de('dinero') || de('numero'), titulo, detalle, dias_en: de('fecha') } },
    {
      vista: 'cifra',
      opciones: {
        funcion: de('dinero') || de('numero') ? 'suma' : 'conteo',
        valor: de('dinero') || de('numero'),
        fecha: de('fecha'),
        periodo: 'mes',
        meta: 10000,
        ayuda: 'Número calculado de los registros de la sección',
      },
    },
    { vista: 'atencion', opciones: { fecha: de('fecha'), estado, excluir: terminados } },
    { vista: 'franjas', opciones: { fecha: de('fecha'), estado, titulo, detalle, urgentes } },
    { vista: 'matriz', opciones: { filas: titulo, columnas: estado } },
  ].filter((v) => {
    const def = {
      calendario_mes: () => de('fecha'),
      tablero_dinero: () => estado && (de('dinero') || de('numero')),
      cifra: () => true,
      atencion: () => de('fecha'),
      franjas: () => de('fecha'),
      matriz: () => titulo && estado,
    }
    return def[v.vista]?.()
  })
}

export default function VistasExtraPage({ plantilla, datos, tema }) {
  const porId = useMemo(() => Object.fromEntries(plantilla.secciones.map((s) => [s.id, s])), [plantilla])
  const seccion = useMemo(
    () => plantilla.secciones.find((s) => s.campos?.length && !s.fuente),
    [plantilla],
  )
  const campos = seccion ? camposDe(seccion, porId) : []
  const registros = seccion ? registrosDe(seccion, datos) : []
  const piezas = useMemo(() => opcionesExtra(campos), [campos])

  if (!seccion) {
    return <p style={{ color: 'var(--tx)' }}>La plantilla no tiene una sección con campos para probar las vistas extra.</p>
  }

  return (
    <AnimarContext.Provider value={false}>
      <div className="mc pl" data-tema={tema} data-estilo="vivo" data-densidad="compacto" style={{ padding: 16, minHeight: '100vh' }}>
        <p style={{ color: 'var(--tx2)', fontSize: 13, marginBottom: 16 }}>
          Vistas extra · {seccion.titulo} · {piezas.length} vistas × {TAMANOS.length} tamaños
        </p>
        {piezas.map((p) => {
          const V = COMPONENTES_EXTRA[p.vista]
          const el = <V seccion={seccion} campos={campos} registros={registros} opciones={p.opciones} datos={datos} />
          return (
            <div key={p.vista} style={{ marginBottom: 20 }}>
              <h3 style={{ color: 'var(--tx)', fontSize: 14, margin: '0 0 10px' }}>{p.vista}</h3>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'flex-start' }}>
                {TAMANOS.map((t) => (
                  <section
                    key={t.id}
                    className="pl-bloque"
                    style={{
                      width: t.w,
                      height: t.h,
                      overflow: 'hidden',
                      boxSizing: 'border-box',
                      containerType: 'size',
                      display: 'flex',
                      flexDirection: 'column',
                    }}
                  >
                    <h2>{p.vista} · {t.id}</h2>
                    <div style={{ flex: 1, minHeight: 0, position: 'relative' }}>{el}</div>
                  </section>
                ))}
              </div>
            </div>
          )
        })}
      </div>
    </AnimarContext.Provider>
  )
}
