import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronDown } from './Iconos'
import Logo from './Logo'

/* Barra superior fija, con dos menús desplegables grandes ("Por qué Shifu" y "Productos"). */

const PRODUCTOS = [
  { titulo: 'Crea tu CRM', items: ['Constructor con IA', 'Plantillas por rubro', 'Etapas y campos a tu medida', 'Importar desde Excel', 'Shifu IA'] },
  { titulo: 'Organiza a tus clientes', items: ['Contactos', 'Negocios y pipeline', 'Seguimientos', 'Cotizaciones', 'Actividades y tareas'] },
  { titulo: 'Comunícate y automatiza', items: ['WhatsApp y correo', 'Mensajes con IA', 'Recordatorios', 'Formularios web', 'Flujos de trabajo'] },
  { titulo: 'Mide y decide', items: ['Reportes', 'Panel de ventas', 'Pronósticos', 'Equipo y metas'] },
  { titulo: 'Conecta', items: ['Integraciones', 'API', 'Webhooks'] },
]
const EXTENDER = [
  ['Galería de plantillas', 'CRMs listos para tu industria'],
  ['Directorio de integraciones', 'Conecta las herramientas que ya usas'],
  ['Shifu.dev', 'Documentación, API y más'],
]

function MenuPorQue() {
  return (
    <div className="mega mega-porque">
      <div className="mega-tarjetas">
        {[
          ['Empieza rápido', 'Tu CRM listo en minutos, no en semanas.', 'g1'],
          ['Cambia a Shifu', 'Trae tus contactos desde Excel y no pierdas ningún seguimiento.', 'g2'],
          ['Los equipos de ventas confían en nosotros', 'Da igual el tamaño de tu negocio: tu CRM crece contigo.', 'g3'],
        ].map(([t, d, g]) => (
          <a key={t} href="#inicio" className="mega-card">
            <span className={`mega-arte ${g}`} />
            <b>{t}</b><small>{d}</small>
          </a>
        ))}
      </div>
      <div className="mega-lado">
        <span className="mega-etq">Incluido en todos los CRM</span>
        <div className="mega-pago"><span className="chip-pago">shifu sync</span></div>
        <b>Tus contactos siempre al día</b><small>Se completan y actualizan solos.</small>
        <div className="mega-ia"><span className="mega-ia-arte" /><b>Shifu IA</b></div>
        <small>Tu asistente de ventas con IA</small>
      </div>
    </div>
  )
}

function MenuProductos() {
  return (
    <div className="mega mega-prod">
      <div className="mega-cols">
        {PRODUCTOS.map((c) => (
          <div key={c.titulo} className="mega-col">
            <span className="mega-etq">{c.titulo}</span>
            <ul>{c.items.map((i) => <li key={i}><a href="#inicio"><i className="mega-pto" />{i}</a></li>)}</ul>
          </div>
        ))}
        <div className="mega-col mega-novedad">
          <span className="mega-etq">Innovación constante</span>
          <span className="mega-novedad-arte" />
          <b>Shifu Editions</b>
          <small>Más de 150 actualizaciones al año.</small>
        </div>
      </div>
      <div className="mega-pie">
        <span className="mega-etq">Personalizar y extender Shifu</span>
        {EXTENDER.map(([t, d]) => <a key={t} href="#inicio"><b>{t}</b><small>{d}</small></a>)}
      </div>
    </div>
  )
}

export default function Nav() {
  const [abierto, setAbierto] = useState(null)         // 'porque' | 'prod' | null
  const [fondo, setFondo] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    const f = () => setFondo(window.scrollY > 24)
    f(); window.addEventListener('scroll', f, { passive: true })
    const fuera = (e) => { if (ref.current && !ref.current.contains(e.target)) setAbierto(null) }
    const esc = (e) => { if (e.key === 'Escape') setAbierto(null) }
    document.addEventListener('mousedown', fuera); document.addEventListener('keydown', esc)
    return () => { window.removeEventListener('scroll', f); document.removeEventListener('mousedown', fuera); document.removeEventListener('keydown', esc) }
  }, [])

  const alternar = (k) => setAbierto((a) => (a === k ? null : k))

  return (
    <header className={`nav ${fondo || abierto ? 'nav-fondo' : ''}`} ref={ref}>
      <div className="nav-barra">
        <div className="nav-izq">
          <Link to="/" aria-label="Shifu"><Logo height={34} /></Link>
          <nav className="nav-menu">
            <button type="button" className={`nav-enlace ${abierto === 'porque' ? 'nav-enlace-on' : ''}`} aria-expanded={abierto === 'porque'} onClick={() => alternar('porque')}>
              Por qué Shifu<ChevronDown />
            </button>
            <button type="button" className={`nav-enlace ${abierto === 'prod' ? 'nav-enlace-on' : ''}`} aria-expanded={abierto === 'prod'} onClick={() => alternar('prod')}>
              Productos<ChevronDown />
            </button>
            <a href="#planes" className="nav-enlace" onClick={() => setAbierto(null)}>Precios</a>
            <a href="#empresas" className="nav-enlace" onClick={() => setAbierto(null)}>Enterprise</a>
          </nav>
        </div>
        <div className="nav-der">
          <Link to="/login" className="nav-enlace">Iniciar sesión</Link>
          <Link to="/login" className="btn-pildora">Comenzar gratis</Link>
        </div>
      </div>
      {abierto === 'porque' && <MenuPorQue />}
      {abierto === 'prod' && <MenuProductos />}
    </header>
  )
}
