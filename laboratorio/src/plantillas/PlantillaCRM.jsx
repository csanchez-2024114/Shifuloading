/* Dibuja un CRM completo a partir de una plantilla (estructura + vistas) y unos datos. Usa el mismo marco visual que
 * CrmPage (.mc, .mc-top, .mc-menu, .mc-main y los temas de crm-extra.css) para que lo que se prueba sea lo que se integra.
 * Si la plantilla no pasa `validarPlantilla`, muestra los errores en vez de dibujarla mal. */
import { useState } from 'react'
import { flushSync } from 'react-dom'
import Logo from '@base/components/Logo'
import { LuLayoutDashboard, LuUsers, LuCalendarDays, LuPackage, LuCreditCard, LuFolderKanban, LuTable, LuActivity, LuIdCard, LuZap, LuFileText, LuTruck, LuCalendarClock } from 'react-icons/lu'
import { COMPONENTES, AnimarContext, VelContext } from './vistas'
import { ESTILOS } from './estilos'
import { validarPlantilla, camposDe } from './validar'
import { registrosDe } from './datosEjemplo'
import '@base/crm.css'
import '@base/crm-extra.css'
import './plantillas.css'
import './estilos.css'

const ICONOS = { usuarios: LuUsers, calendario: LuCalendarDays, caja: LuPackage, tarjeta: LuCreditCard, tablero: LuFolderKanban, tabla: LuTable,
  actividad: LuActivity, equipo: LuIdCard, rayo: LuZap, documento: LuFileText, camion: LuTruck, reloj: LuCalendarClock }
const GRUPOS = ['Estructura', 'Medición y equipo', 'Automatizaciones']
// Cada plantilla tiene su color de firma, tomado de la misma paleta de marca (no se agregan colores).
const ACENTO = { embudo: '#22d3a6', agenda: '#7c5cff', pedidos: '#f5a623', membresias: '#3fb8ff', proyectos: '#b06cff', simple: '#22d3a6' }
// Bloques que se le pueden "pedir a Shifu" en el inicio: los de la propia plantilla más los que su estructura permite.
const nombreBloque = (w, porId) => `${TITULO_VISTA[w.vista] || w.vista} · ${porId[w.seccion]?.titulo}`
/** Cambia el DOM con una transición animada (View Transitions) cuando el navegador la soporta; si no, cambia directo. */
const conTransicion = (fn) => (document.startViewTransition && !window.matchMedia('(prefers-reduced-motion: reduce)').matches
  ? document.startViewTransition(() => flushSync(fn)) : fn())
// Rejilla de 12 columnas: anchos posibles de un bloque y su nombre para el botón.
const ANCHOS_COL = [3, 4, 6, 8, 12]
const ANCHO_COMPLETO = ['kpis', 'tablero', 'agenda']
/** Tamaño inicial: resumen, tablero y agenda a lo ancho; lo demás a media columna; si queda uno solo en su fila, a lo ancho. */
function conTamano(bloques) {
  const medios = bloques.filter((b) => !ANCHO_COMPLETO.includes(b.vista))
  const solo = medios.length % 2 === 1 ? medios[medios.length - 1].uid : null
  return bloques.map((b) => ({ ...b,
    ancho: b.ancho || (ANCHO_COMPLETO.includes(b.vista) || b.uid === solo ? 12 : 6),
    alto: b.alto || (b.vista === 'kpis' ? 1 : b.vista === 'tablero' || b.vista === 'agenda' ? 2 : 2) }))
}
const TITULO_VISTA = { kpis: 'Resumen', tablero: 'Por etapa', agenda: 'Próximos días', vencimientos: 'Por vencer', grafica: 'Gráfica', tabla: 'Lista' }

export default function PlantillaCRM({ plantilla, datos, tema = 'oscuro', estilo = 'vivo-compacto', vel = 2.2, negocio = 'Mi negocio' }) {
  const [vista, setVista] = useState('inicio')
  const def = ESTILOS.find((e) => e.id === estilo) || ESTILOS[0]
  const animado = def.base === 'vivo'
  // El inicio es editable como lo haría la IA: se quitan y se agregan bloques, y el resto se reacomoda animado.
  const [bloques, setBloques] = useState(() => conTamano(plantilla.inicio.map((w, i) => ({ ...w, uid: `b${i}` }))))
  // Cambiar el tamaño de un bloque (ancho en columnas de 12, alto en filas). El resto se reacomoda animado.
  const redimensionar = (uid, eje, paso) => conTransicion(() => setBloques((bs) => bs.map((b) => {
    if (b.uid !== uid) return b
    if (eje === 'ancho') { const i = ANCHOS_COL.indexOf(b.ancho); return { ...b, ancho: ANCHOS_COL[Math.max(0, Math.min(ANCHOS_COL.length - 1, i + paso))] } }
    return { ...b, alto: Math.max(1, Math.min(4, b.alto + paso)) }
  })))
  const [quitados, setQuitados] = useState([])
  const [saliendo, setSaliendo] = useState([])
  // Quitar: primero corre la animación de salida del bloque y después el resto se reacomoda (View Transition).
  const quitar = (uid) => {
    const fuera = () => conTransicion(() => { const b = bloques.find((x) => x.uid === uid); setBloques((bs) => bs.filter((x) => x.uid !== uid)); setQuitados((q) => [...q, b]); setSaliendo((s) => s.filter((x) => x !== uid)) })
    if (!animado || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return fuera()
    setSaliendo((s) => [...s, uid]); setTimeout(fuera, 700 * vel)
  }
  const poner = (uid) => conTransicion(() => { const b = quitados.find((x) => x.uid === uid); setQuitados((q) => q.filter((x) => x.uid !== uid)); setBloques((bs) => [...bs, { ...b, nuevo: true }]) })
  // Si los bloques de media columna son impares, el último queda solo en su fila: ocupa el ancho completo (sin hueco).
  const ir = (id) => conTransicion(() => setVista(id))
  const errores = validarPlantilla(plantilla)
  const porId = Object.fromEntries(plantilla.secciones.map((s) => [s.id, s]))
  const actual = porId[vista]
  const dibujar = (s, nombreVista, opciones) => {
    const V = COMPONENTES[nombreVista]
    return V ? <V seccion={s} campos={camposDe(s, porId)} registros={registrosDe(s, datos)} opciones={opciones || {}} datos={datos} /> : null
  }
  return (
    <AnimarContext.Provider value={animado}><VelContext.Provider value={vel}>
    <div className="mc pl" data-tema={tema} data-estilo={def.base} data-densidad={def.densidad} data-plantilla={plantilla.id} style={{ '--acento': ACENTO[plantilla.id] || '#22d3a6', '--vel': vel }}>
      <header className="mc-top">
        <Logo height={24} color="var(--tx)" />
        <span className="mc-negocio">{negocio}</span>
        <span className="pl-plantilla" title={plantilla.para}>Plantilla: {plantilla.nombre}</span>
      </header>
      <div className="mc-cuerpo">
        <nav className="mc-menu" aria-label="Secciones">
          <div className="mc-grupo">
            <ul><li><button type="button" className={vista === 'inicio' ? 'on' : ''} aria-current={vista === 'inicio' ? 'page' : undefined} onClick={() => ir('inicio')}><LuLayoutDashboard aria-hidden="true" />Inicio</button></li></ul>
          </div>
          {GRUPOS.map((g, gi) => {
            const items = plantilla.secciones.filter((s) => s.grupo === gi)
            if (!items.length) return null
            return (
              <div key={g} className="mc-grupo">
                <h2>{g}</h2>
                <ul>
                  {items.map((s) => {
                    const I = ICONOS[s.icono] || LuTable
                    return <li key={s.id}><button type="button" className={vista === s.id ? 'on' : ''} aria-current={vista === s.id ? 'page' : undefined} onClick={() => ir(s.id)}><I aria-hidden="true" />{s.titulo}</button></li>
                  })}
                </ul>
              </div>
            )
          })}
        </nav>
        <main className="mc-main" key={vista}>
          {errores.length > 0 && (
            <div className="pl-errores" role="alert"><b>Esta plantilla no es válida ({errores.length})</b><ul>{errores.map((e) => <li key={e}>{e}</li>)}</ul></div>
          )}
          {errores.length === 0 && vista === 'inicio' && (
            <>
              <div className="mc-cab"><div><h1>Inicio</h1><p>{plantilla.para}</p></div></div>
              <div className="pl-inicio">
                {bloques.map((w, i) => (
                  <section key={w.uid} className={`pl-bloque pl-bloque-${w.vista}${saliendo.includes(w.uid) ? ' saliendo' : ''}${w.nuevo ? ' nuevo' : ''}`} style={{ '--i': w.nuevo ? 0 : i, '--ancho': w.ancho, '--alto': w.alto, viewTransitionName: `pl-${w.uid}` }} data-ancho={w.ancho}>
                    <h2>{nombreBloque(w, porId)}</h2>
                    {animado && <button type="button" className="pl-quitar" onClick={() => quitar(w.uid)} aria-label={`Quitar ${nombreBloque(w, porId)}`}>×</button>}
                    {animado && w.vista !== 'kpis' && (
                      <div className="pl-tamano" role="group" aria-label={`Tamaño de ${nombreBloque(w, porId)}`}>
                        <span>Ancho</span>
                        <button type="button" disabled={w.ancho === ANCHOS_COL[0]} onClick={() => redimensionar(w.uid, 'ancho', -1)} aria-label="Más angosto">−</button>
                        <button type="button" disabled={w.ancho === 12} onClick={() => redimensionar(w.uid, 'ancho', 1)} aria-label="Más ancho">+</button>
                        <span>Alto</span>
                        <button type="button" disabled={w.alto === 1} onClick={() => redimensionar(w.uid, 'alto', -1)} aria-label="Más bajo">−</button>
                        <button type="button" disabled={w.alto === 4} onClick={() => redimensionar(w.uid, 'alto', 1)} aria-label="Más alto">+</button>
                      </div>
                    )}
                    {dibujar(porId[w.seccion], w.vista, w.opciones)}
                  </section>
                ))}
                {animado && quitados.length > 0 && (
                  <div className="pl-agregar" style={{ viewTransitionName: 'pl-agregar' }}>
                    <span>Pedirle a Shifu que vuelva a poner:</span>
                    {quitados.map((w) => <button key={w.uid} type="button" onClick={() => poner(w.uid)}>＋ {nombreBloque(w, porId)}</button>)}
                  </div>
                )}
              </div>
            </>
          )}
          {errores.length === 0 && actual && (
            <>
              <div className="mc-cab">
                <div><h1>{actual.titulo}</h1>{(actual.campos || actual.fuente) && <p>{registrosDe(actual, datos).length ? `${registrosDe(actual, datos).length.toLocaleString('es')} registros.` : 'Todavía no hay registros.'}</p>}</div>
                {actual.campos && <button type="button" className="btn-pildora">Agregar</button>}
              </div>
              <div className="pl-seccion">{dibujar(actual, actual.vista, actual.opciones)}</div>
            </>
          )}
        </main>
      </div>
    </div>
    </VelContext.Provider></AnimarContext.Provider>
  )
}
