/* Laboratorio de plantillas (solo en desarrollo): probar cada plantilla con distintos datos, anchos y temas.
 * Todo lo elegido vive en la URL, así un caso exacto se comparte copiando el enlace. */
import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { PLANTILLAS } from '../plantillas/semillas'
import { validarPlantilla } from '../plantillas/validar'
import { ROTAS } from './rotas'
import './laboratorio.css'

const ANCHOS = [360, 390, 768, 1024, 1280, 1440]
const ALTO = { 360: 760, 390: 844, 768: 1024, 1024: 768, 1280: 800, 1440: 900 }
const COMPARAR = [360, 768, 1280]
const DATOS = [['vacio', 'Vacío'], ['pocos', 'Pocos (8)'], ['muchos', 'Muchos (220)']]

const urlVista = (plantilla, datos, tema) => `/laboratorio/vista?plantilla=${plantilla}&datos=${datos}&tema=${tema}`

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

export default function LaboratorioPage() {
  const [q, setQ] = useSearchParams()
  const plantilla = q.get('plantilla') || 'embudo'
  const datos = q.get('datos') || 'pocos'
  const tema = q.get('tema') || 'oscuro'
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

        <h2>Datos</h2>
        <div className="lab-botones">{DATOS.map(([v, t]) => <button key={v} type="button" className={datos === v ? 'on' : ''} onClick={() => fijar('datos', v)}>{t}</button>)}</div>
        <h2>Tema</h2>
        <div className="lab-botones">{[['oscuro', 'Oscuro'], ['claro', 'Claro']].map(([v, t]) => <button key={v} type="button" className={tema === v ? 'on' : ''} onClick={() => fijar('tema', v)}>{t}</button>)}</div>
        <h2>Modo</h2>
        <div className="lab-botones">{[['una', 'Un ancho'], ['comparar', 'Comparar 3 anchos'], ['todas', 'Todas las plantillas']].map(([v, t]) => <button key={v} type="button" className={modo === v ? 'on' : ''} onClick={() => fijar('modo', v)}>{t}</button>)}</div>
        {modo !== 'comparar' && (
          <>
            <h2>Ancho</h2>
            <div className="lab-botones">{ANCHOS.map((a) => <button key={a} type="button" className={ancho === a ? 'on' : ''} onClick={() => fijar('ancho', a)}>{a}</button>)}</div>
          </>
        )}
        <p className="lab-validez">{errores.length ? `✗ ${errores.length} errores de validación` : '✓ Plantilla válida'}</p>
      </aside>

      <main className="lab-zona" ref={zona}>
        {modo === 'una' && <Marco src={urlVista(plantilla, datos, tema)} ancho={ancho} titulo={todas.find((p) => p.id === plantilla)?.nombre} maxAncho={disp - 8} />}
        {modo === 'comparar' && (
          <div className="lab-fila">{COMPARAR.map((a) => <Marco key={a} src={urlVista(plantilla, datos, tema)} ancho={a} titulo={a < 700 ? 'Móvil' : a < 1000 ? 'Tablet' : 'Escritorio'} maxAncho={(disp - 32) * (a / COMPARAR.reduce((s, x) => s + x, 0))} />)}</div>
        )}
        {modo === 'todas' && (
          <div className="lab-rejilla">{PLANTILLAS.map((p) => <Marco key={p.id} src={urlVista(p.id, datos, tema)} ancho={ancho} titulo={p.nombre} maxAncho={ancho < 700 ? (disp - 48) / 3 : (disp - 24) / 2} />)}</div>
        )}
      </main>
    </div>
  )
}
