/* Dibuja un CRM completo a partir de una plantilla (estructura + vistas) y unos datos. Usa el mismo marco visual que
 * CrmPage (.mc, .mc-top, .mc-menu, .mc-main y los temas de crm-extra.css) para que lo que se prueba sea lo que se integra.
 * Si la plantilla no pasa `validarPlantilla`, muestra los errores en vez de dibujarla mal. */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { flushSync } from 'react-dom'
import Logo from '@base/components/Logo'
import { LuLayoutDashboard, LuUsers, LuCalendarDays, LuPackage, LuCreditCard, LuFolderKanban, LuTable, LuActivity, LuIdCard, LuZap, LuFileText, LuTruck, LuCalendarClock } from 'react-icons/lu'
import { COMPONENTES, AnimarContext, VelContext, FichaContext } from './vistas'
import Ficha from './ficha'
import { useSeleccion } from './seleccion'
import { ESTILOS } from './estilos'
import { validarPlantilla, camposDe } from './validar'
import { registrosDe, datosEjemplo } from './datosEjemplo'
import ChatLab, { GUION, GUION_TOMA } from './ChatLab'
import Recorrido, { pasosDe } from './Recorrido'
import { fijarRegion } from './regional'
import { tokensDeMarca, cargarFuentes } from './marca'
import { plantillaEfectiva } from './edicion'
import { Grafico, GRAFICOS } from './graficos'
import '@base/crm.css'
import '@base/crm-extra.css'
import '@base/crm-captura.css'
import './plantillas.css'
import './estilos.css'
import './marca-base.css'

const ICONOS = { usuarios: LuUsers, calendario: LuCalendarDays, caja: LuPackage, tarjeta: LuCreditCard, tablero: LuFolderKanban, tabla: LuTable,
  actividad: LuActivity, equipo: LuIdCard, rayo: LuZap, documento: LuFileText, camion: LuTruck, reloj: LuCalendarClock }
const GRUPOS = ['Estructura', 'Medición y equipo', 'Automatizaciones']
// Cada plantilla tiene su color de firma, tomado de la misma paleta de marca (no se agregan colores).
const ACENTO = { embudo: '#22d3a6', agenda: '#7c5cff', pedidos: '#f5a623', membresias: '#3fb8ff', proyectos: '#b06cff', simple: '#22d3a6' }
// Bloques que se le pueden "pedir a Shifu" en el inicio: los de la propia plantilla más los que su estructura permite.
const nombreBloque = (w, porId) => `${w.vista === 'grafico' ? GRAFICOS[w.opciones?.tipo]?.nombre || 'Gráfico' : TITULO_VISTA[w.vista] || w.vista} · ${porId[w.seccion]?.titulo ?? ''}`
/** Cambia el DOM con una transición animada (View Transitions) cuando el navegador la soporta; si no, cambia directo. */
// Si llega un cambio mientras otra transición sigue animando, la anterior se salta (el navegador la cancela y
// rechaza sus promesas con "Transition was skipped"): es esperado, así que se atrapa y no ensucia la consola.
const conTransicion = (fn) => {
  if (!document.startViewTransition || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return fn()
  const t = document.startViewTransition(() => flushSync(fn))
  for (const p of [t.ready, t.finished, t.updateCallbackDone]) p?.catch(() => {})
  return t
}
const ANCHO_COMPLETO = ['kpis', 'tablero', 'agenda']
/** Tamaño inicial: resumen, tablero y agenda a lo ancho; lo demás a media columna; si queda uno solo en su fila, a lo ancho. */
function conTamano(bloques) {
  const medios = bloques.filter((b) => !ANCHO_COMPLETO.includes(b.vista))
  const solo = medios.length % 2 === 1 ? medios[medios.length - 1].uid : null
  return bloques.map((b) => ({ ...b,
    ancho: b.ancho || (ANCHO_COMPLETO.includes(b.vista) || b.uid === solo ? 12 : 6),
    alto: b.alto || (b.vista === 'kpis' ? 1 : b.vista === 'tablero' || b.vista === 'agenda' ? 2 : 2) }))
}
/** Datos de ejemplo para lo que Shifu agregó: cada sección nueva y cada campo nuevo tiene su propia semilla, así los
 * datos que ya estaban no cambian al agregar algo (no "saltan" los números). Sin ejemplos (nivel vacío) no se inventa nada. */
function extenderDatos(datos, base, est, nivel) {
  if (!datos || (!est.secciones?.length && !Object.keys(est.campos || {}).length && !Object.keys(est.mapeoEstado || {}).length)) return datos
  const registros = { ...datos.registros }
  for (const sec of est.secciones || []) registros[sec.id] = datosEjemplo({ id: `${base.id}:${sec.id}`, secciones: [sec] }, nivel).registros[sec.id] || []
  for (const [sid, extras] of Object.entries(est.campos || {})) {
    const extra = datosEjemplo({ id: `${base.id}:${sid}:campos`, secciones: [{ id: sid, campos: extras }] }, nivel).registros[sid] || []
    registros[sid] = (registros[sid] || []).map((r, i) => ({ ...r, valores: { ...r.valores, ...(extra[i]?.valores || {}) } }))
  }
  // Opciones de estado renombradas o quitadas: cada registro pasa a su nueva opción (nunca queda sin estado).
  for (const [sid, porCampo] of Object.entries(est.mapeoEstado || {})) {
    registros[sid] = (registros[sid] || []).map((r) => {
      let valores = r.valores
      for (const [cid, mapa] of Object.entries(porCampo)) { let v = valores[cid], n = 0; while (mapa[v] && n++ < 10) v = mapa[v]; if (v !== valores[cid]) valores = { ...valores, [cid]: v } }
      return valores === r.valores ? r : { ...r, valores }
    })
  }
  return { ...datos, registros }
}

/** Logo del negocio. Si es oscuro y el tema es oscuro (o claro sobre claro), muestra una versión de alto contraste automática. */
function LogoMarca({ src, tema }) {
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
const TITULO_VISTA = { kpis: 'Resumen', tablero: 'Por etapa', agenda: 'Próximos días', vencimientos: 'Por vencer', grafica: 'Gráfica', tabla: 'Lista' }

export default function PlantillaCRM({ plantilla: plantillaBase, datos: datosBase, nivel = 'pocos', tema = 'oscuro', estilo = 'vivo-compacto', vel = 2.2, negocio = 'Mi negocio', pais = 'gt', recorrido = false, onBorrarEjemplos, demo = false }) {
  const [enRecorrido, setEnRecorrido] = useState(recorrido)
  // Formatos (moneda, miles, fechas, horas) según la configuración regional de la persona: se fija antes de dibujar.
  fijarRegion(pais)
  const [vista, setVista] = useState('inicio')
  const def = ESTILOS.find((e) => e.id === estilo) || ESTILOS[0]
  const animado = def.base === 'vivo'
  // El inicio SOLO lo cambia la IA (chat): recibe un estado nuevo y la pantalla se transforma animada.
  const [bloques, setBloques] = useState(() => conTamano(plantillaBase.inicio.map((w, i) => ({ ...w, uid: `b${i}` }))))
  const [saliendo, setSaliendo] = useState([])
  // Marca del negocio (D19): la cambia solo Shifu. Base = tokens actuales; la marca los reemplaza y el código cuida el contraste.
  const [marca, setMarca] = useState({})
  // Estructura que Shifu cambió (secciones nuevas, campos, ocultas, nombres). La plantilla efectiva = base + esto.
  const [estructura, setEstructura] = useState({})
  const plantilla = useMemo(() => plantillaEfectiva(plantillaBase, { estructura }), [plantillaBase, estructura])
  const datos = useMemo(() => extenderDatos(datosBase, plantillaBase, estructura, nivel), [datosBase, plantillaBase, estructura, nivel])
  useEffect(() => { cargarFuentes(marca) }, [marca])
  const [chatAbierto, setChatAbierto] = useState(true)
  // Ficha abierta (D28): { seccion, registro } o null.
  const [abierta, setAbierta] = useState(null)
  const abrirFicha = useCallback((seccion, registro) => setAbierta({ seccion, registro }), [])
  const cerrarFicha = useCallback(() => setAbierta(null), [])
  // Elegir piezas con doble clic (PC) o manteniendo presionado (táctil) para editarlas con Shifu (D39).
  const raiz = useRef(null)
  const { modo: eligiendoPiezas, barra: barraSeleccion } = useSeleccion(raiz)
  // Cascadas de entrada solo al cargar o al cambiar de sección; al aplicar cambios de Shifu se apaga para no re-animar lo que no cambió.
  const [entrada, setEntrada] = useState(() => animado)
  const ir = (id) => conTransicion(() => { if (animado) setEntrada(true); setVista(id) })
  /** Aplica el estado que devolvió Shifu: lo que se va sale primero (desenfoque), después el resto se reacomoda y lo nuevo nace. */
  const aplicarEstado = (nuevo) => {
    const bloquesBase = nuevo.bloques ?? ultimo.current?.bloques ?? bloques.map(({ nuevo: _n, ...b }) => b)
    ultimo.current = { vista: nuevo.vista || vista, marca: nuevo.marca ?? marca, estructura: nuevo.estructura ?? estructura, bloques: bloquesBase.map(({ nuevo: _n, ...b }) => b), toma: nuevo.toma, puntos: nuevo.puntos }
    if (!nuevo.bloques) return
    if (animado) setEntrada(false)
    if (nuevo.estructura) setEstructura(nuevo.estructura)
    if (nuevo.marca) setMarca(nuevo.marca)
    const ids = new Set(nuevo.bloques.map((b) => b.uid))
    const viejos = new Set(bloques.map((b) => b.uid))
    const fuera = bloques.filter((b) => !ids.has(b.uid)).map((b) => b.uid)
    const final = () => conTransicion(() => {
      setSaliendo([])
      setBloques(nuevo.bloques.map((b) => (viejos.has(b.uid) ? { ...b, nuevo: false } : { ...b, nuevo: true })))
      if (nuevo.vista && nuevo.vista !== vista) setVista(nuevo.vista)
    })
    if (!fuera.length || !animado || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return final()
    setSaliendo(fuera); setTimeout(final, 700 * vel)
  }
  const ultimo = useRef(null) // el último estado aplicado (puede no haberse dibujado todavía por la transición)
  const estadoParaIA = () => ultimo.current || ({ vista, marca, estructura, bloques: bloques.map(({ nuevo: _n, ...b }) => b), toma: ultimo.current?.toma })
  const errores = validarPlantilla(plantilla)
  const porId = Object.fromEntries(plantilla.secciones.map((s) => [s.id, s]))
  const actual = porId[vista]
  // Vista "sombría" (D25): sin datos, la misma vista se dibuja con datos fantasma, apagada, y un mensaje encima. Así cada
  // vista y gráfico muestra su forma (qué va a ver) sin fingir números: los datos fantasma no se leen ni se pueden tocar.
  const fantasma = useMemo(() => extenderDatos(datosEjemplo(plantillaBase, 'pocos'), plantillaBase, estructura, 'pocos'), [plantillaBase, estructura])
  const dibujarCon = (s, nombreVista, opciones, d) => {
    if (nombreVista === 'grafico') return <Grafico key={opciones?.tipo} tipo={opciones?.tipo} seccion={s} campos={camposDe(s, porId)} registros={registrosDe(s, d)} opciones={opciones || {}} />
    const V = COMPONENTES[nombreVista]
    return V ? <V seccion={s} campos={camposDe(s, porId)} registros={registrosDe(s, d)} opciones={opciones || {}} datos={d} /> : null
  }
  const dibujar = (s, nombreVista, opciones) => {
    // Un bloque cuya sección se acaba de quitar sigue unos instantes en pantalla (animación de salida): se dibuja vacío.
    if (!s) return null
    const sinDatos = (s.campos || s.fuente) && !registrosDe(s, datos).length
    if (!sinDatos) return dibujarCon(s, nombreVista, opciones, datos)
    return (
      <div className="pl-sombra">
        <div className="pl-sombra-forma" aria-hidden="true" inert="">{dibujarCon(s, nombreVista, opciones, fantasma)}</div>
        <p className="pl-sombra-msg"><b>Todavía no hay datos</b><span>Se llena con tu primer registro en {s.titulo}.</span></p>
      </div>
    )
  }
  return (
    <AnimarContext.Provider value={animado}><VelContext.Provider value={vel}><FichaContext.Provider value={abrirFicha}>
    <div ref={raiz} className={`mc pl${chatAbierto ? ' con-chat' : ''}${eligiendoPiezas ? ' eligiendo' : ''}`} data-tema={tema} data-estilo={def.base} data-densidad={def.densidad} data-plantilla={plantilla.id} style={{ '--acento': ACENTO[plantilla.id] || '#22d3a6', '--vel': vel, ...tokensDeMarca(marca, tema).vars }}>
      <header className="mc-top">
        {marca.logo ? <LogoMarca src={marca.logo} tema={tema} /> : <Logo height={24} color="var(--tx)" />}
        <span className="mc-negocio">{marca.nombre || negocio}</span>
        <span className="pl-plantilla" title={plantilla.para}>Plantilla: {plantilla.nombre}</span>
      </header>
      <div className="mc-cuerpo">
        <nav className="mc-menu" aria-label="Secciones">
          <div className="mc-grupo">
            <ul><li><button type="button" className={vista === 'inicio' ? 'on' : ''} aria-current={vista === 'inicio' ? 'page' : undefined} data-seccion="inicio" onClick={() => ir('inicio')}><LuLayoutDashboard aria-hidden="true" />Inicio</button></li></ul>
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
                    return <li key={s.id}><button type="button" className={vista === s.id ? 'on' : ''} aria-current={vista === s.id ? 'page' : undefined} data-seccion={s.id} onClick={() => ir(s.id)}><I aria-hidden="true" />{s.titulo}</button></li>
                  })}
                </ul>
              </div>
            )
          })}
        </nav>
        <main className="mc-main" key={vista} data-animar={entrada && animado ? '' : undefined}>
          {errores.length > 0 && (
            <div className="pl-errores" role="alert"><b>Esta plantilla no es válida ({errores.length})</b><ul>{errores.map((e) => <li key={e}>{e}</li>)}</ul></div>
          )}
          {errores.length === 0 && vista === 'inicio' && (
            <>
              <div className="mc-cab"><div><h1>Inicio</h1><p>{plantilla.para}</p></div></div>
              <div className="pl-inicio">
                {bloques.map((w, i) => (
                  <section key={w.uid} className={`pl-bloque pl-bloque-${w.vista}${saliendo.includes(w.uid) ? ' saliendo' : ''}${w.nuevo ? ' nuevo' : ''}`} data-bloque={w.uid} data-animar={w.nuevo && animado ? '' : undefined} style={{ '--i': w.nuevo ? 0 : i, '--ancho': w.ancho, '--alto': w.alto, viewTransitionName: `pl-${w.uid}` }} data-ancho={w.ancho}>
                    <h2>{nombreBloque(w, porId)}</h2>
                    {dibujar(porId[w.seccion], w.vista, w.opciones)}
                  </section>
                ))}
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
      {barraSeleccion}
      {abierta && <Ficha plantilla={plantilla} datos={datos} seccionId={abierta.seccion} registroId={abierta.registro} onCerrar={cerrarFicha} onAbrir={abrirFicha} />}
      {enRecorrido && vista === 'inicio' && <Recorrido pasos={pasosDe(plantilla, bloques, porId)} onSaltar={() => setEnRecorrido(false)} onTerminar={() => { setEnRecorrido(false); onBorrarEjemplos?.() }} />}
      <ChatLab contexto={{ plantilla, bloques, marca, toma: ultimo.current?.toma, vista, datos }} guion={demo === 'toma' ? GUION_TOMA : demo ? GUION : null} tema={tema} plantilla={plantilla} estadoActual={estadoParaIA} onEstado={aplicarEstado} seccionActual={actual?.titulo || 'Inicio'} onAbierto={(a) => conTransicion(() => setChatAbierto(a))} />
    </div>
    </FichaContext.Provider></VelContext.Provider></AnimarContext.Provider>
  )
}
