/* Laboratorio de plantillas (solo en desarrollo): probar cada plantilla con distintos datos, anchos y temas.
 * Todo lo elegido vive en la URL, así un caso exacto se comparte copiando el enlace. */
import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { PLANTILLAS } from '../plantillas/semillas'
import { validarPlantilla } from '../plantillas/validar'
import { ROTAS } from './rotas'
import { ESTILOS } from '../plantillas/estilos'
import { PAISES } from '../plantillas/regional'
import { asignar } from '../plantillas/asignar'
import './laboratorio.css'

const ANCHOS = [360, 390, 768, 1024, 1280, 1440]
const ALTO = { 360: 760, 390: 844, 768: 1024, 1024: 768, 1280: 800, 1440: 900 }
const COMPARAR = [360, 768, 1280]
const DATOS = [['vacio', 'Vacío'], ['pocos', 'Pocos (8)'], ['muchos', 'Muchos (220)']]

let VEL = '2.2'
let PAIS = 'gt'
let RECORRIDO = false
const urlVista = (plantilla, datos, tema, estilo, extra = '') => `/vista?plantilla=${plantilla}&datos=${datos}&tema=${tema}&estilo=${estilo}&vel=${VEL}&pais=${PAIS}${extra}${RECORRIDO ? '&recorrido=1' : ''}`

/** Un iframe con el ancho real del dispositivo, escalado para que quepa en el espacio disponible. */
function Marco({ src, ancho, titulo, maxAncho }) {
  const alto = ALTO[ancho] || 800
  const escala = Math.min(1, maxAncho / ancho)
  return (
    <figure className="lab-marco">
      <figcaption>{titulo} · {ancho}px{escala < 1 ? ` (al ${Math.round(escala * 100)}%)` : ''} <a href={src} target="_blank" rel="noreferrer">abrir ↗</a></figcaption>
      <div style={{ width: ancho * escala, height: alto * escala }}>
        <iframe title={`${titulo} a ${ancho}px`} src={src} style={{ width: ancho, height: alto, transform: `scale(${escala})` }} />
      </div>
    </figure>
  )
}

/** Videos de revisión (laboratorio/grabaciones): se graban con servidor/grabar.mjs y se revisan antes de mostrarse. */
function Grabaciones() {
  const [lista, setLista] = useState(null)
  useEffect(() => { fetch('/api/lab/grabaciones').then((r) => r.json()).then(setLista).catch(() => setLista([])) }, [])
  if (!lista) return <p className="lab-nota">Cargando…</p>
  if (!lista.length) return <p className="lab-nota">Todavía no hay grabaciones.</p>
  return (
    <div className="lab-grab">{lista.map((g) => (
      <figure key={g.id} className="lab-marco">
        <figcaption>{g.id} · {g.archivos.filter((a) => a.endsWith('.mp4')).map((a) => <a key={a} href={`/grabaciones/${g.id}/${a}`} target="_blank" rel="noreferrer">{a.replace('.mp4', '')}</a>)}{g.archivos.includes('eventos.txt') && <a href={`/grabaciones/${g.id}/eventos.txt`} target="_blank" rel="noreferrer">eventos</a>}</figcaption>
        {g.archivos.includes('escritorio-1440x900.mp4') && <video src={`/grabaciones/${g.id}/escritorio-1440x900.mp4`} controls preload="metadata" />}
      </figure>
    ))}</div>
  )
}

export default function LaboratorioPage() {
  const [q, setQ] = useSearchParams()
  const plantilla = q.get('plantilla') || 'embudo'
  const datos = q.get('datos') || 'pocos'
  const tema = q.get('tema') || 'oscuro'
  const estilo = q.get('estilo') || 'vivo-compacto'
  VEL = q.get('vel') || '2.2'
  PAIS = q.get('pais') || 'gt'
  RECORRIDO = q.get('recorrido') === '1'
  const [brief, setBrief] = useState({ rubro: 'salud', ciclo: 'recurrente', objetivos: ['seguimientos'], queVendes: 'consultas y vacunas para mascotas' })
  const asig = asignar(brief)
  const modo = q.get('modo') || 'una'
  const ancho = Number(q.get('ancho')) || 1280
  const fijar = (k, v) => { const n = new URLSearchParams(q); n.set(k, v); setQ(n, { replace: true }) }

  // Ancho disponible para escalar los marcos.
  const zona = useRef(null)
  const [disp, setDisp] = useState(1000)
  useEffect(() => {
    const ro = new ResizeObserver(([e]) => setDisp(e.contentRect.width))
    if (zona.current) ro.observe(zona.current)
    return () => ro.disconnect()
  }, [])

  const todas = [...PLANTILLAS, ...ROTAS]
  const errores = validarPlantilla(todas.find((p) => p.id === plantilla))

  return (
    <div className="lab">
      <aside className="lab-panel">
        <h1>Laboratorio de plantillas</h1>
        <p className="lab-nota">Solo en desarrollo. Datos de ejemplo, nada se guarda.</p>

        <h2>Demos y vistas</h2>
        <ul className="lab-lista">{[
          ['demo', '🤖 Demo IA · flujo completo', '8 pedidos reales: marca, crear, embudo, mover, algo que no existe, quitar'],
          ['toma', '📝 Toma de diseño', 'Pedir un inicio nuevo → ficha → ajuste → «sí» → se arma'],
          ['nuevo', '👋 Usuario nuevo · primer ingreso', 'Recorrido con datos de ejemplo que se borran al final'],
          ['vacio', '🌫️ Sin datos (sombría)', 'Cómo se ve antes del primer registro'],
          ['una', '💬 Chat libre con Shifu', 'Probar cualquier pedido (marca, enlaces, PDF, crear secciones…)'],
          ['galeria', '📊 Galería de gráficos', 'Los 43 tipos con datos de la plantilla'],
          ['grabaciones', '🎬 Grabaciones en video', 'Revisadas antes de mostrarse, en 4 resoluciones'],
        ].map(([v, t, d]) => <li key={v}><button type="button" className={modo === v ? 'on' : ''} onClick={() => fijar('modo', v)}><b>{t}</b><small>{d}</small></button></li>)}</ul>
        <h2>Simular cuestionario (asignación)</h2>
        <div className="lab-brief">
          <select value={brief.rubro} onChange={(e) => setBrief({ ...brief, rubro: e.target.value })} aria-label="Rubro">{['servicios', 'agencia', 'comercio', 'salud', 'educacion', 'tecnologia', 'inmobiliaria', 'otro'].map((r) => <option key={r}>{r}</option>)}</select>
          <select value={brief.ciclo} onChange={(e) => setBrief({ ...brief, ciclo: e.target.value })} aria-label="Ciclo">{['cotizacion', 'rapida', 'recurrente', 'mezcla'].map((r) => <option key={r}>{r}</option>)}</select>
          <input value={brief.queVendes} onChange={(e) => setBrief({ ...brief, queVendes: e.target.value })} placeholder="¿Qué vendes?" aria-label="Qué vendes" />
          <div className="lab-botones">{['seguimientos', 'contactos', 'reportes', 'cotizaciones', 'equipo'].map((o) => <button key={o} type="button" className={brief.objetivos.includes(o) ? 'on' : ''} onClick={() => setBrief({ ...brief, objetivos: brief.objetivos.includes(o) ? brief.objetivos.filter((x) => x !== o) : [...brief.objetivos, o] })}>{o}</button>)}</div>
          <ol>{asig.opciones.map((o, k) => <li key={o.id}><button type="button" className={plantilla === o.id ? 'on' : ''} onClick={() => fijar('plantilla', o.id)}><b>{k === 0 && !asig.ambiguo ? '★ ' : ''}{o.nombre}</b> · {o.puntos} pts<small>{o.porque.join(', ') || 'sin coincidencias'}</small></button></li>)}</ol>
          {asig.ambiguo && <p className="lab-nota">Caso ambiguo: Shifu mostraría estas opciones en vez de elegir sola (D6).</p>}
          <div className="lab-botones"><button type="button" className={RECORRIDO ? 'on' : ''} onClick={() => fijar('recorrido', RECORRIDO ? '0' : '1')}>{RECORRIDO ? '✓ Recorrido de primera entrada' : 'Ver como primera entrada (recorrido)'}</button></div>
        </div>

        <h2>Plantilla</h2>
        <ul className="lab-lista">
          {PLANTILLAS.map((p) => {
            const n = validarPlantilla(p).length
            return <li key={p.id}><button type="button" className={plantilla === p.id ? 'on' : ''} onClick={() => fijar('plantilla', p.id)}><b>{p.nombre}</b><small>{p.para}</small>{n > 0 && <em>{n} errores</em>}</button></li>
          })}
        </ul>
        <details className="lab-rotas"><summary>Rotas a propósito (prueban el validador)</summary>
          <ul className="lab-lista">{ROTAS.map((p) => <li key={p.id}><button type="button" className={plantilla === p.id ? 'on' : ''} onClick={() => fijar('plantilla', p.id)}><b>{p.nombre}</b></button></li>)}</ul>
        </details>

        <h2>Estilo</h2>
        <ul className="lab-lista">{ESTILOS.filter((e) => !e.oculto).map((e) => <li key={e.id}><button type="button" className={estilo === e.id ? 'on' : ''} onClick={() => fijar('estilo', e.id)}><b>{e.nombre}</b><small>{e.idea}</small></button></li>)}</ul>

        <h2>Velocidad de animación</h2>
        <div className="lab-botones">{[['1', 'Rápida'], ['1.6', 'Calmada'], ['2.2', 'Lenta'], ['3', 'Muy lenta']].map(([v, t]) => <button key={v} type="button" className={VEL === v ? 'on' : ''} onClick={() => fijar('vel', v)}>{t}</button>)}</div>
        <p className="lab-nota">Para volver a ver la entrada, recarga el marco (o cambia de sección).</p>

        <h2>País del negocio (configuración)</h2>
        <div className="lab-botones">{Object.entries(PAISES).map(([v, p]) => <button key={v} type="button" className={PAIS === v ? 'on' : ''} onClick={() => fijar('pais', v)}>{p.nombre}</button>)}</div>
        <p className="lab-nota">Moneda, miles, fechas y horas salen de aquí (como en la configuración del CRM).</p>

        <h2>Datos</h2>
        <div className="lab-botones">{DATOS.map(([v, t]) => <button key={v} type="button" className={datos === v ? 'on' : ''} onClick={() => fijar('datos', v)}>{t}</button>)}</div>
        <h2>Tema</h2>
        <div className="lab-botones">{[['oscuro', 'Oscuro'], ['claro', 'Claro']].map(([v, t]) => <button key={v} type="button" className={tema === v ? 'on' : ''} onClick={() => fijar('tema', v)}>{t}</button>)}</div>
        <h2>Comparar</h2>
        <div className="lab-botones">{[['comparar', 'Comparar 3 anchos'], ['todas', 'Todas las plantillas']].map(([v, t]) => <button key={v} type="button" className={modo === v ? 'on' : ''} onClick={() => fijar('modo', v)}>{t}</button>)}</div>
        {modo !== 'comparar' && (
          <>
            <h2>Ancho</h2>
            <div className="lab-botones">{ANCHOS.map((a) => <button key={a} type="button" className={ancho === a ? 'on' : ''} onClick={() => fijar('ancho', a)}>{a}</button>)}</div>
          </>
        )}
        <p className="lab-validez">{errores.length ? `✗ ${errores.length} errores de validación` : '✓ Plantilla válida'}</p>
      </aside>

      <main className="lab-zona" ref={zona}>
        {modo === 'una' && <Marco src={urlVista(plantilla, datos, tema, estilo)} ancho={ancho} titulo={todas.find((p) => p.id === plantilla)?.nombre} maxAncho={disp - 8} />}
        {modo === 'demo' && <Marco src={urlVista(plantilla, datos, tema, estilo, '&demo=1')} ancho={ancho} titulo="Demo IA: 8 pedidos reales seguidos (crear, modificar, branding, algo que no existe, quitar)" maxAncho={disp - 8} />}
        {modo === 'nuevo' && <Marco src={urlVista(plantilla, 'muchos', tema, estilo, '&recorrido=1')} ancho={ancho} titulo="Primera entrada de un usuario nuevo" maxAncho={disp - 8} />}
        {modo === 'toma' && <Marco src={urlVista(plantilla, 'muchos', tema, estilo, '&demo=toma')} ancho={ancho} titulo="Toma de diseño: ficha → ajuste → «sí» → se arma por código (IA real)" maxAncho={disp - 8} />}
        {modo === 'vacio' && <Marco src={urlVista(plantilla, 'vacio', tema, estilo)} ancho={ancho} titulo="Sin datos: vista sombría" maxAncho={disp - 8} />}
        {modo === 'grabaciones' && <Grabaciones />}
        {modo === 'galeria' && <Marco src={urlVista(plantilla, datos, tema, estilo, '&galeria=1')} ancho={ancho} titulo="Galería de gráficos" maxAncho={disp - 8} />}
        {modo === 'comparar' && (
          <div className="lab-fila">{COMPARAR.map((a) => <Marco key={a} src={urlVista(plantilla, datos, tema, estilo)} ancho={a} titulo={a < 700 ? 'Móvil' : a < 1000 ? 'Tablet' : 'Escritorio'} maxAncho={(disp - 32) * (a / COMPARAR.reduce((s, x) => s + x, 0))} />)}</div>
        )}
        {modo === 'todas' && (
          <div className="lab-rejilla">{PLANTILLAS.map((p) => <Marco key={p.id} src={urlVista(p.id, datos, tema, estilo)} ancho={ancho} titulo={p.nombre} maxAncho={ancho < 700 ? (disp - 48) / 3 : (disp - 24) / 2} />)}</div>
        )}
        {modo === 'estilos' && (
          <div className="lab-rejilla">{ESTILOS.map((e) => <Marco key={e.id} src={urlVista(plantilla, datos, tema, e.id)} ancho={ancho} titulo={e.nombre} maxAncho={ancho < 700 ? (disp - 48) / 3 : (disp - 24) / 2} />)}</div>
        )}
      </main>
    </div>
  )
}
