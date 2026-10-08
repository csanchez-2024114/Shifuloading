import { FaFacebookF, FaInstagram, FaLinkedinIn, FaPinterestP, FaTiktok, FaXTwitter, FaYoutube } from 'react-icons/fa6'
import Logo from './Logo'

const COLUMNAS = [
  ['Shifu', ['¿Qué es Shifu?', 'Shifu Editions', 'Inversores']],
  ['Ecosistema', ['Documentación para desarrolladores', 'Tienda de temas', 'Tienda de aplicaciones', 'Partners', 'Afiliados']],
  ['Recursos', ['Blog', 'Comparar Shifu', 'Herramientas gratis', 'Registro de cambios']],
  ['Atención al cliente', ['Centro de ayuda', 'Foro de la comunidad', 'Contratar a un partner', 'Estado del servicio']],
]
const LEGAL = ['Términos del servicio', 'Legal', 'Política de privacidad', 'Mapa del sitio', 'Tus opciones de privacidad']

export default function Footer() {
  return (
    <footer className="pie">
      <div className="pie-grid">
        <div className="pie-logo"><Logo height={34} texto={false} /></div>
        {COLUMNAS.map(([t, items]) => (
          <div key={t} className="pie-col">
            <b>{t}</b>
            <ul>{items.map((i) => <li key={i}><a href="#inicio">{i}</a></li>)}</ul>
          </div>
        ))}
      </div>
      <div className="pie-base">
        <span className="pie-region">🌐 Guatemala | Español</span>
        <nav className="pie-legal">{LEGAL.map((l) => <a key={l} href="#inicio">{l}</a>)}</nav>
        <div className="pie-redes" aria-label="Redes sociales">
          {[FaFacebookF, FaXTwitter, FaYoutube, FaInstagram, FaTiktok, FaLinkedinIn, FaPinterestP].map((I, k) => <a key={k} href="#inicio" aria-label="Red social"><I size={15} /></a>)}
        </div>
      </div>
    </footer>
  )
}
