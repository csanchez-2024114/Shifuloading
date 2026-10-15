import { useState } from 'react'
import { Link } from 'react-router-dom'
import Nav from '../components/Nav'

/* Directorio de integraciones. Solo se marca "Disponible" lo que de verdad funciona hoy; lo demás es "Próximamente" (nada se promete como hecho). */
const INTEGRACIONES = [
  { id: 'excel', icono: '📊', t: 'Excel y hojas de cálculo', estado: 'disponible', grupo: 'Traer tus datos',
    d: 'Sube un archivo .csv, .tsv, .xls o .xlsx y Shifu crea tus contactos de una vez, sin que los escribas uno por uno.' },
  { id: 'notas', icono: '📝', t: 'Notas y texto pegado', estado: 'disponible', grupo: 'Traer tus datos',
    d: 'Pega una lista de nombres desde tus notas o un chat y Shifu la ordena y la convierte en contactos.' },
  { id: 'imagenes', icono: '📸', t: 'Capturas e imágenes', estado: 'disponible', grupo: 'Traer tus datos',
    d: 'Toma una foto o una captura de una tabla, una lista o una libreta: Shifu la lee y la guarda en tu CRM.' },
  { id: 'correo', icono: '✉️', t: 'Avisos por correo', estado: 'disponible', grupo: 'Avisos',
    d: 'Los recordatorios de seguimiento y el resumen de tu semana también te llegan a tu correo, además de la campana dentro de Shifu.' },
  { id: 'internet', icono: '🌐', t: 'Búsqueda en internet', estado: 'disponible', grupo: 'Avisos',
    d: 'Si le preguntas por el clima, un dato o una noticia, Shifu lo busca en internet y te lo cuenta en el mismo chat.' },
  { id: 'api', icono: '🔌', t: 'API de Shifu', estado: 'disponible', grupo: 'Para tu equipo técnico', enlace: '/desarrolladores',
    d: 'Conecta tu CRM con cualquier otro sistema usando la API. Te explicamos qué es y cómo se usa, paso a paso.' },
  { id: 'whatsapp', icono: '💬', t: 'WhatsApp', estado: 'pronto', grupo: 'Canales',
    d: 'Guardar los mensajes y chats de cada cliente en su ficha, y que Shifu cree el contacto cuando alguien te escribe.' },
  { id: 'calendario', icono: '📅', t: 'Google Calendar', estado: 'pronto', grupo: 'Canales',
    d: 'Que tus citas y llamadas agendadas aparezcan en tu calendario y se sincronicen solas.' },
  { id: 'gmail', icono: '📥', t: 'Gmail (bandeja de entrada)', estado: 'pronto', grupo: 'Canales',
    d: 'Ver en la ficha de cada cliente los correos que se han escrito.' },
  { id: 'sheets', icono: '📈', t: 'Google Sheets en vivo', estado: 'pronto', grupo: 'Traer tus datos',
    d: 'Mantener una hoja de Google al día con tus contactos, sin subir archivos.' },
  { id: 'cobros', icono: '💳', t: 'Cobros y pagos', estado: 'pronto', grupo: 'Dinero',
    d: 'Registrar lo que te deben y que Shifu te avise de los cobros vencidos.' },
  { id: 'webhooks', icono: '🔔', t: 'Webhooks del CRM', estado: 'pronto', grupo: 'Para tu equipo técnico', enlace: '/desarrolladores',
    d: 'Que Shifu avise a tu sistema cuando entra un contacto nuevo o cambia de etapa.' },
]

const FILTROS = [['todas', 'Todas'], ['disponible', 'Disponibles hoy'], ['pronto', 'Próximamente']]

export default function InfoIntegraciones() {
  const [filtro, setFiltro] = useState('todas')
  const lista = INTEGRACIONES.filter((i) => filtro === 'todas' || i.estado === filtro)
  const hoy = INTEGRACIONES.filter((i) => i.estado === 'disponible').length

  return (
    <div className="home info">
      <Nav />
      <main className="info-main">
        <header className="info-cab">
          <Link to="/" className="info-volver">← Volver al inicio</Link>
          <h1>Directorio de integraciones</h1>
          <p>Lo que Shifu ya conecta hoy y lo que viene en camino. Marcamos con claridad qué funciona ya y qué todavía no, para que sepas qué esperar.</p>
          <p className="info-cifra"><b>{hoy}</b> disponibles hoy · <b>{INTEGRACIONES.length - hoy}</b> en camino</p>
        </header>

        <div className="info-filtros" role="tablist" aria-label="Filtrar integraciones">
          {FILTROS.map(([k, t]) => (
            <button key={k} type="button" role="tab" aria-selected={filtro === k} className={filtro === k ? 'on' : ''} onClick={() => setFiltro(k)}>{t}</button>
          ))}
        </div>

        <div className="info-rejilla">
          {lista.map((i) => (
            <article key={i.id} className={`info-card ${i.estado}`}>
              <div className="info-card-cab">
                <span className="info-ico" aria-hidden="true">{i.icono}</span>
                <span className={`info-etq ${i.estado}`}>{i.estado === 'disponible' ? 'Disponible' : 'Próximamente'}</span>
              </div>
              <h2>{i.t}</h2>
              <small>{i.grupo}</small>
              <p>{i.d}</p>
              {i.enlace && <Link to={i.enlace} className="info-mas">Ver más →</Link>}
            </article>
          ))}
        </div>

        <section className="info-cta">
          <h2>Empieza con lo que ya funciona</h2>
          <p>Crea tu CRM en minutos y trae tus contactos desde tu Excel o tus notas.</p>
          <Link to="/login" className="btn-pildora btn-grande">Comenzar gratis</Link>
        </section>
      </main>
    </div>
  )
}
