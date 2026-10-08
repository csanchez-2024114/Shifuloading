import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  LuBookOpen, LuChartPie, LuCodeXml, LuDatabase, LuFileText, LuHeart, LuInbox, LuLayoutDashboard, LuLayoutGrid,
  LuMegaphone, LuMonitor, LuSend, LuSettings, LuSparkles,
} from 'react-icons/lu'
import { CLAVE, recomendar } from '../brief/preguntas'
import '../panel.css'

/* Pantalla principal de Shifu: saludo, anillo de la IA y 9 acciones. Se arma con lo que la persona contó en el cuestionario:
 * usa su nombre y marca como "Sugerido" las tarjetas que le tocan. Las acciones se conectarán cuando exista el servidor. */

const MENU = [
  { id: 'dashboard', t: 'Dashboard', Icono: LuLayoutDashboard },
  { id: 'catalogo', t: 'Catálogo', Icono: LuLayoutGrid },
  { id: 'marketing', t: 'Marketing', Icono: LuMegaphone },
  { id: 'ajustes', t: 'Ajustes', Icono: LuSettings },
]

// `claves` son las recomendaciones del cuestionario que hacen "Sugerida" a una tarjeta.
const ACCIONES = [
  { t: 'Analizar ventas', d: 'Qué se vende y cuánto te deja', Icono: LuChartPie, claves: ['reportes'] },
  { t: 'Crear nueva colección', d: 'Agrupa productos para lanzarlos', Icono: LuBookOpen, claves: ['catalogo', 'plantilla', 'lanza'] },
  { t: 'Ver clientes fieles', d: 'Quiénes te compran seguido', Icono: LuHeart, claves: ['vender'] },
  { t: 'Procesar órdenes', d: 'Pedidos por preparar y enviar', Icono: LuMonitor, claves: [] },
  { t: 'Crear nueva orden', d: 'Registra una venta a mano', Icono: LuInbox, claves: [] },
  { t: 'Ver base de clientes', d: 'Todos tus contactos en un lugar', Icono: LuDatabase, claves: [] },
  { t: 'Administrar productos', d: 'Precios, fotos y existencias', Icono: LuCodeXml, claves: ['inventario'] },
  { t: 'Crear nueva factura', d: 'Cobra y envía el comprobante', Icono: LuFileText, claves: ['pagos'] },
  { t: 'Ajustes de tu tienda', d: 'Canales, mercados y pagos', Icono: LuSettings, claves: ['mercados', 'canales'] },
]

const SUGERENCIAS = ['¿Cómo van mis ventas?', '¿Qué me recomiendas hoy?', 'Crea una colección nueva']

const leer = () => { try { return JSON.parse(localStorage.getItem(CLAVE)) || {} } catch { return {} } }

function saludoDelDia() {
  const h = new Date().getHours()
  return h < 12 ? 'Buenos días ☀️' : h < 19 ? 'Buenas tardes 🌤️' : 'Buenas noches 🌙'
}

export default function PanelPage() {
  const resp = useMemo(() => leer().resp || {}, [])
  const plan = useMemo(() => recomendar(resp), [resp])
  const claves = useMemo(() => new Set(plan.map((p) => p.clave)), [plan])
  const nombre = (resp.nombre || '').trim()

  const [aviso, setAviso] = useState('')
  const [abierto, setAbierto] = useState(false)
  const [texto, setTexto] = useState('')
  const [chat, setChat] = useState([])
  const [escribiendo, setEscribiendo] = useState(false)
  const temporizador = useRef(null)
  const fin = useRef(null)
  const campo = useRef(null)

  useEffect(() => () => { clearTimeout(temporizador.current) }, [])
  useEffect(() => { fin.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }) }, [chat, escribiendo])
  useEffect(() => { if (abierto) campo.current?.focus() }, [abierto])

  // "/" abre la barra de la IA desde cualquier parte, como en las apps de escritorio.
  useEffect(() => {
    const f = (e) => { if (e.key === '/' && !['INPUT', 'TEXTAREA'].includes(e.target.tagName)) { e.preventDefault(); setAbierto(true) } if (e.key === 'Escape') setAbierto(false) }
    window.addEventListener('keydown', f)
    return () => window.removeEventListener('keydown', f)
  }, [])

  const avisar = (m) => { setAviso(m); clearTimeout(temporizador.current); temporizador.current = setTimeout(() => setAviso(''), 3200) }

  const responder = (pregunta) => {
    const q = pregunta.toLowerCase()
    if (/recomiend|sugier|empiezo|hago hoy/.test(q)) {
      const r = plan[0]
      return `Te sugiero esto primero: ${r.emoji} ${r.titulo}. ${r.porque}.`
    }
    return 'Todavía no estoy conectado a los datos de tu tienda. Cuando Shifu tenga su servidor, aquí te respondo con tus cifras reales.'
  }
  const enviar = (pregunta) => {
    const p = pregunta.trim()
    if (!p || escribiendo) return
    setTexto(''); setChat((c) => [...c, { de: 'dueno', t: p }]); setEscribiendo(true)
    setTimeout(() => { setEscribiendo(false); setChat((c) => [...c, { de: 'shifu', t: responder(p) }]) }, 1100)
  }

  return (
    <div className="panel">
      <div className="panel-fondo" aria-hidden="true"><i className="pf-a" /><i className="pf-b" /></div>

      <nav className="panel-menu" aria-label="Menú principal">
        <Link to="/" className="panel-marca" aria-label="Shifu"><i>S</i></Link>
        <ul>
          {MENU.map(({ id, t, Icono }, k) => (
            <li key={id}>
              <button type="button" className={`pm-item ${k === 0 ? 'pm-on' : ''}`} aria-current={k === 0 ? 'page' : undefined}
                onClick={() => k > 0 && avisar(`${t} se abrirá aquí cuando Shifu tenga su servidor.`)}>
                <Icono size={22} /><span>{t}</span>
              </button>
            </li>
          ))}
        </ul>
        <Link to="/bienvenida" className="pm-pie" title="Volver a contestar el cuestionario">Cuestionario</Link>
      </nav>

      <main className="panel-main">
        <header className="panel-cab">
          <p className="panel-saludo">{saludoDelDia()}</p>
          <h1>Hola, {nombre || 'bienvenido'}</h1>
          <span className="panel-avatar" aria-hidden="true">{(nombre[0] || 'S').toUpperCase()}</span>
        </header>

        <section className="ia" aria-label="Shifu IA">
          <div className="ia-fila">
            <span className="ia-linea" aria-hidden="true" />
            <button type="button" className={`orbe-ia ${abierto ? 'orbe-on' : ''}`} onClick={() => setAbierto((a) => !a)} aria-expanded={abierto} aria-label="Hablar con Shifu IA">
              <i className="anillo a1" /><i className="anillo a2" /><i className="anillo a3" /><i className="nucleo"><LuSparkles size={26} /></i>
            </button>
            <span className="ia-linea" aria-hidden="true" />
          </div>
          {!abierto && <p className="ia-pista">Toca el anillo o presiona <kbd>/</kbd> para hablar con Shifu IA</p>}

          {abierto && (
            <div className="asistente" role="dialog" aria-label="Conversación con Shifu IA">
              <div className="as-chat" aria-live="polite">
                {chat.length === 0 && <p className="as-vacio">¿En qué te ayudo hoy{nombre ? `, ${nombre}` : ''}? 👋</p>}
                {chat.map((m, k) => <div key={k} className={`burbuja-p burbuja-p-${m.de}`}>{m.t}</div>)}
                {escribiendo && <div className="burbuja-p burbuja-p-shifu pensando"><i /><i /><i /></div>}
                <div ref={fin} />
              </div>
              {chat.length === 0 && <div className="as-sug">{SUGERENCIAS.map((s) => <button key={s} type="button" onClick={() => enviar(s)}>{s}</button>)}</div>}
              <form className="as-form" onSubmit={(e) => { e.preventDefault(); enviar(texto) }}>
                <input ref={campo} value={texto} onChange={(e) => setTexto(e.target.value)} placeholder="Pregúntale lo que quieras a Shifu…" maxLength={200} aria-label="Escribe tu pregunta" />
                <button type="submit" disabled={!texto.trim() || escribiendo} aria-label="Enviar"><LuSend size={18} /></button>
              </form>
            </div>
          )}
        </section>

        <section className="cartas" aria-label="Acciones rápidas">
          {ACCIONES.map(({ t, d, Icono, claves: cl }, k) => {
            const sugerida = cl.some((c) => claves.has(c))
            return (
              <button key={t} type="button" className={`carta ${sugerida ? 'carta-sug' : ''}`} style={{ animationDelay: `${0.1 + k * 0.05}s` }}
                onClick={() => avisar(`"${t}" se abrirá aquí cuando Shifu tenga su servidor.`)}>
                <span className="carta-ico"><Icono size={22} /></span>
                <span className="carta-t">{t}</span>
                <small>{d}</small>
                {sugerida && <em className="carta-badge">✨ Sugerido</em>}
              </button>
            )
          })}
        </section>
      </main>

      {aviso && <div className="panel-aviso" role="status">💡 {aviso}</div>}
    </div>
  )
}
