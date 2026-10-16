/* Pantalla única del laboratorio: TODO lo que estamos haciendo y mostrando, en un solo lugar.
 * Demos con la IA real, plantillas (con sus atajos), panel de pruebas, grabaciones en video y estado medido. */
import { useEffect, useState } from 'react'
import { PLANTILLAS } from '../plantillas/semillas'
import { PAISES } from '../plantillas/regional'
import './hub.css'

const DEMOS = [
  { t: 'Demo IA · flujo completo', d: '8 pedidos reales seguidos: marca, crear inventario, embudo, mover, algo que no existe, campo nuevo, quitar.', q: 'plantilla=clinica-dental&datos=muchos&demo=1', e: '🤖' },
  { t: 'Toma de diseño (estilo Alan)', d: 'Pedir un inicio nuevo → ficha → cambio en la confirmación → «sí» → se arma por código.', q: 'plantilla=membresias&datos=muchos&demo=toma', e: '📝' },
  { t: 'Usuario nuevo · recorrido', d: 'Primera entrada: CRM armado por el cuestionario con datos de ejemplo, recorrido guiado y borrado de ejemplos.', q: 'plantilla=veterinaria&datos=muchos&recorrido=1', e: '👋' },
  { t: 'Vista sin datos (sombría)', d: 'Cómo se ve el CRM antes del primer registro.', q: 'plantilla=taller-mecanico&datos=vacio', e: '🌫️' },
  { t: 'Galería de gráficos', d: 'Los 43 tipos de gráfico con datos reales de la plantilla.', q: 'plantilla=proyectos&datos=muchos&galeria=1', e: '📊' },
  { t: 'Chat libre con Shifu', d: 'El CRM con el chat abierto para probar cualquier pedido: diseño, marca (colores, logo, enlaces, PDF), crear secciones…', q: 'plantilla=membresias&datos=muchos', e: '💬' },
]
const ESTADO = [
  ['Toma de diseño · banco estricto', '5/5 guiones (92% en 25 corridas)', '2026-10-16'],
  ['Chat de diseño · banco de 15 pedidos', '15/15 · 2.3 s promedio', '2026-10-16'],
  ['Filtro de calidad de plantillas', '27/27', '2026-10-16'],
  ['IA de Carlos vs agente Shifu (CRM)', '1.5 s vs 7.5 s por respuesta', '2026-10-15'],
]

export default function HubPage() {
  const [tema, setTema] = useState(() => { try { return localStorage.getItem('hub-tema') || 'claro' } catch { return 'claro' } })
  const [pais, setPais] = useState('gt')
  const [grab, setGrab] = useState([])
  const [filtro, setFiltro] = useState('')
  useEffect(() => { try { localStorage.setItem('hub-tema', tema) } catch { /* sin almacenamiento */ } }, [tema])
  useEffect(() => { fetch('/api/lab/grabaciones').then((r) => r.json()).then(setGrab).catch(() => setGrab([])) }, [])
  const url = (q) => `/vista?${q}&tema=${tema}&pais=${pais}`
  const lista = PLANTILLAS.filter((p) => `${p.nombre} ${p.para}`.toLowerCase().includes(filtro.toLowerCase()))
  return (
    <div className="hub">
      <header className="hub-cab">
        <div><h1>Laboratorio Shifu</h1><p>Rama <b>david</b> · todo lo que estamos probando, en un solo lugar. Cada enlace abre en otra pestaña.</p></div>
        <div className="hub-ctrl">
          <label>Tema <select value={tema} onChange={(e) => setTema(e.target.value)}><option value="claro">Claro</option><option value="oscuro">Oscuro</option></select></label>
          <label>País <select value={pais} onChange={(e) => setPais(e.target.value)}>{Object.entries(PAISES).map(([k, v]) => <option key={k} value={k}>{v.nombre}</option>)}</select></label>
          <a className="hub-btn" href="/panel" target="_blank" rel="noreferrer">Panel de pruebas ↗</a>
        </div>
      </header>

      <section><h2>Demos en vivo <small>IA real · gastan créditos de OpenAI</small></h2>
        <div className="hub-rej">{DEMOS.map((x) => (
          <a key={x.t} className="hub-card" href={url(x.q)} target="_blank" rel="noreferrer"><span className="hub-e">{x.e}</span><b>{x.t}</b><small>{x.d}</small></a>
        ))}</div>
      </section>

      <section><h2>Estado medido <small>lo último verificado</small></h2>
        <table className="hub-tabla"><tbody>{ESTADO.map(([a, b, c]) => <tr key={a}><td>{a}</td><td><b>{b}</b></td><td>{c}</td></tr>)}</tbody></table>
      </section>

      <section><h2>Grabaciones en video <small>revisadas antes de mostrarse · 4 resoluciones</small></h2>
        {!grab.length && <p className="hub-nota">Todavía no hay grabaciones en laboratorio/grabaciones.</p>}
        <div className="hub-rej">{grab.map((g) => (
          <div key={g.id} className="hub-card hub-video">
            <b>{g.id}</b>
            {g.archivos.includes('escritorio-1440x900.mp4') && <video src={`/grabaciones/${g.id}/escritorio-1440x900.mp4`} controls preload="metadata" />}
            <small>{g.archivos.filter((a) => a.endsWith('.mp4')).map((a) => <a key={a} href={`/grabaciones/${g.id}/${a}`} target="_blank" rel="noreferrer">{a.replace('.mp4', '')}</a>)}{g.archivos.includes('eventos.txt') && <a href={`/grabaciones/${g.id}/eventos.txt`} target="_blank" rel="noreferrer">eventos</a>}</small>
          </div>
        ))}</div>
      </section>

      <section><h2>Plantillas ({PLANTILLAS.length}) <input className="hub-buscar" placeholder="Buscar…" value={filtro} onChange={(e) => setFiltro(e.target.value)} /></h2>
        <div className="hub-rej hub-plant">{lista.map((p) => (
          <div key={p.id} className="hub-card">
            <b>{p.nombre}</b><small>{p.para}</small>
            <div className="hub-acc">
              <a href={url(`plantilla=${p.id}&datos=muchos`)} target="_blank" rel="noreferrer">Abrir</a>
              <a href={url(`plantilla=${p.id}&datos=muchos&recorrido=1`)} target="_blank" rel="noreferrer">Recorrido</a>
              <a href={url(`plantilla=${p.id}&datos=muchos&demo=toma`)} target="_blank" rel="noreferrer">Toma</a>
              <a href={url(`plantilla=${p.id}&datos=vacio`)} target="_blank" rel="noreferrer">Sin datos</a>
              <a href={url(`plantilla=${p.id}&datos=muchos&galeria=1`)} target="_blank" rel="noreferrer">Gráficos</a>
            </div>
          </div>
        ))}</div>
      </section>
    </div>
  )
}
