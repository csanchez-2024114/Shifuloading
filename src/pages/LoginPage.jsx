import { useState } from 'react'
import { Link } from 'react-router-dom'
import { FaApple, FaFacebook, FaWhatsapp } from 'react-icons/fa6'
import { FcGoogle } from 'react-icons/fc'
import { ClaveDeAcceso } from '../components/Iconos'
import Logo from '../components/Logo'

/* Pantalla de inicio de sesión. Por ahora es solo la pantalla: no se conecta a ningún servidor. */
export default function LoginPage() {
  const [correo, setCorreo] = useState('')
  const [aviso, setAviso] = useState('')

  const continuar = (e) => {
    e.preventDefault()
    setAviso(correo.trim() ? '' : 'Escribe tu correo electrónico.')
  }

  return (
    <div className="login">
      <Link to="/" className="login-logo" aria-label="Shifu"><Logo height={26} /></Link>

      <main className="login-centro">
        <form className="login-tarjeta" onSubmit={continuar} noValidate>
          <h1>Iniciar sesión</h1>
          <p className="login-sub">Continuar a Shifu</p>

          <label htmlFor="correo" className="login-label">Correo electrónico</label>
          <input id="correo" type="email" autoComplete="email" autoFocus value={correo}
            onChange={(e) => setCorreo(e.target.value)} className="login-input" />
          {aviso && <p className="login-aviso" role="alert">{aviso}</p>}

          <button type="submit" className="login-btn-oscuro">Continuar con correo electrónico</button>

          <div className="login-o"><span>o</span></div>

          <button type="button" className="login-btn-claro">
            <ClaveDeAcceso /> Iniciar sesión con clave de acceso
          </button>

          <div className="login-sociales">
            <button type="button" aria-label="Continuar con Google"><FcGoogle size={20} /></button>
            <button type="button" aria-label="Continuar con Apple"><FaApple size={20} /></button>
            <button type="button" aria-label="Continuar con Facebook"><FaFacebook size={20} color="#1877f2" /></button>
            <button type="button" aria-label="Continuar con WhatsApp"><FaWhatsapp size={20} color="#25d366" /></button>
          </div>

          <p className="login-nuevo">¿Primera vez en Shifu? <Link to="/bienvenida">Empezar →</Link></p>
        </form>

        <p className="login-ayuda">¿Necesitas ayuda?</p>
      </main>

      <p className="login-legal">
        Si continúas, aceptas los <strong>Términos</strong> y la <strong>Política de privacidad</strong>,
        así como recibir correos electrónicos de marketing de Shifu. Puedes cancelar la suscripción en cualquier momento.
      </p>
    </div>
  )
}
