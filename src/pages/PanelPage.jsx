import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  LuBellRing, LuChartPie, LuFileText, LuHandshake, LuLayoutDashboard, LuListChecks, LuPlug, LuSend, LuSettings, LuSparkles,
  LuUsers, LuWorkflow,
} from 'react-icons/lu'
import ShifuAvatar from '../components/ShifuAvatar'
import { recomendar } from '../brief/preguntas'
import { leerBorrador } from '../brief/borrador'
import '../panel.css'

/* Pantalla principal del CRM de Shifu: saludo, anillo de la IA y 9 acciones. Se arma con lo que la persona contó en el cuestionario:
 * usa su nombre y marca como "Sugerido" las tarjetas que le tocan. Las acciones se conectarán cuando exista el servidor. */

const MENU = [
  { id: 'dashboard', t: 'Dashboard', Icono: LuLayoutDashboard },
  { id: 'contactos', t: 'Contactos', Icono: LuUsers },
  { id: 'negocios', t: 'Negocios', Icono: LuHandshake },
  { id: 'ajustes', t: 'Ajustes', Icono: LuSettings },
]

// `claves` son las recomendaciones del cuestionario que hacen "Sugerida" a una tarjeta.
const ACCIONES = [
  { t: 'Ver contactos', d: 'Todos tus clientes en un lugar', Icono: LuUsers, claves: ['contactos', 'importar'] },
  { t: 'Mover negocios', d: 'Tu pipeline, etapa por etapa', Icono: LuHandshake, claves: ['reportes'] },
  { t: 'Dar seguimiento', d: 'A quién toca escribirle hoy', Icono: LuBellRing, claves: ['seguimientos'] },
  { t: 'Crear cotización', d: 'Arma y envía una en minutos', Icono: LuFileText, claves: ['cotizaciones'] },
  { t: 'Agendar actividad', d: 'Llamadas, reuniones y tareas', Icono: LuListChecks, claves: [] },
  { t: 'Ver reportes', d: 'Cómo van tus ventas', Icono: LuChartPie, claves: ['reportes'] },
  { t: 'Automatizar mensajes', d: 'Respuestas y recordatorios con IA', Icono: LuWorkflow, claves: ['ia'] },
  { t: 'Conectar canales', d: 'WhatsApp, correo y más', Icono: LuPlug, claves: ['integraciones'] },
  { t: 'Ajustes de tu CRM', d: 'Etapas, campos y equipo', Icono: LuSettings, claves: ['arma', 'plantilla', 'equipo'] },
]

const SUGERENCIAS = ['¿A quién debo contactar hoy?', '¿Qué me recomiendas hoy?', 'Crea una cotización nueva']


function saludoDelDia() {
  const h = new Date().getHours()
  return h < 12 ? 'Buenos días ☀️' : h < 19 ? 'Buenas tardes 🌤️' : 'Buenas noches 🌙'
}

export default function PanelPage() {
  const resp = useMemo(() => leerBorrador()?.resp || {}, [])
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
    return 'Todavía no estoy conectado a los datos de tu CRM. Cuando Shifu tenga su servidor, aquí te respondo con tus clientes y cifras reales.'
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
                {chat.length === 0 && (
                  <div className="as-vacio">
                    <img className="mascota-vacio" src="/img/shifu-cuerpo.webp" alt="Shifu te saluda" width="92" height="93" />
                    <p>¿En qué te ayudo hoy{nombre ? `, ${nombre}` : ''}?</p>
                  </div>
                )}
                {chat.map((m, k) => (m.de === 'shifu'
                  ? <div key={k} className="fila-p-shifu"><ShifuAvatar size={30} /><div className="burbuja-p burbuja-p-shifu">{m.t}</div></div>
                  : <div key={k} className="burbuja-p burbuja-p-dueno">{m.t}</div>))}
                {escribiendo && <div className="fila-p-shifu"><ShifuAvatar size={30} /><div className="burbuja-p burbuja-p-shifu pensando"><i /><i /><i /></div></div>}
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
