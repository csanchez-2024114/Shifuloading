import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { HAY_SERVIDOR, auth } from '../api'
import { FaApple, FaFacebook, FaWhatsapp } from 'react-icons/fa6'
import { FcGoogle } from 'react-icons/fc'
import { ClaveDeAcceso } from '../components/Iconos'
import Logo from '../components/Logo'

const CORREO_OK = /^\S+@\S+\.\S+$/

/** Texto claro para cada cosa que puede salir mal al entrar. */
function mensajeDeEntrada(e) {
  if (e?.estado === 401) return 'Correo o contraseña incorrectos.'
  if (e?.estado === 429) return 'Demasiados intentos. Espera un minuto e inténtalo de nuevo.'
  if (e?.estado === 0) return 'No pudimos conectarnos. Revisa tu conexión e inténtalo de nuevo.'
  return e?.message || 'No pudimos continuar. Inténtalo de nuevo.'
}

/* Pantalla de inicio de sesión. Con servidor: primero el correo y luego la contraseña (como en Shopify). Sin servidor (modo de
 * prueba) solo pide el correo y manda al cuestionario. */
export default function LoginPage() {
  const [correo, setCorreo] = useState('')
  const [clave, setClave] = useState('')
  const [verClave, setVerClave] = useState(false)
  const [paso, setPaso] = useState('correo')
  const [aviso, setAviso] = useState('')
  const [enviando, setEnviando] = useState(false)
  const nav = useNavigate()

  const continuar = async (e) => {
    e.preventDefault()
    if (enviando) return
    if (!correo.trim()) { setAviso('Escribe tu correo electrónico.'); return }
    setAviso('')

    if (!HAY_SERVIDOR) {
      setEnviando(true)
      try {
        const r = await auth.continuarConCorreo(correo.trim())
        nav(r?.existe ? '/mi-crm' : '/bienvenida')
      } catch (err) { setAviso(mensajeDeEntrada(err)); setEnviando(false) }
      return
    }

    if (!CORREO_OK.test(correo.trim())) { setAviso('Escribe un correo válido, por ejemplo nombre@correo.com.'); return }
    if (paso === 'correo') { setPaso('clave'); return }
    if (!clave) { setAviso('Escribe tu contraseña.'); return }
    setEnviando(true)
    try {
      await auth.iniciarSesion({ correo: correo.trim(), clave })
      nav('/mi-crm')
    } catch (err) {
      setAviso(mensajeDeEntrada(err))
      setEnviando(false)
    }
  }

  const enClave = HAY_SERVIDOR && paso === 'clave'

  return (
    <div className="login">
      <Link to="/" className="login-logo" aria-label="Shifu"><Logo height={26} /></Link>

      <main className="login-centro">
        <form className="login-tarjeta" onSubmit={continuar} noValidate>
          <h1>Iniciar sesión</h1>
          <p className="login-sub">Continuar a Shifu</p>

          {enClave ? (
            <>
              <div className="login-correo-fijo">
                <span>{correo.trim()}</span>
                <button type="button" onClick={() => { setPaso('correo'); setClave(''); setAviso('') }}>Cambiar</button>
              </div>
              <label htmlFor="clave" className="login-label">Contraseña</label>
              <div className="login-clave">
                <input id="clave" type={verClave ? 'text' : 'password'} autoComplete="current-password" autoFocus value={clave}
                  onChange={(e) => setClave(e.target.value)} className="login-input" />
                <button type="button" onClick={() => setVerClave(!verClave)} aria-pressed={verClave}>{verClave ? 'Ocultar' : 'Mostrar'}</button>
              </div>
            </>
          ) : (
            <>
              <label htmlFor="correo" className="login-label">Correo electrónico</label>
              <input id="correo" type="email" autoComplete="email" autoFocus value={correo}
                onChange={(e) => setCorreo(e.target.value)} className="login-input" />
            </>
          )}
          {aviso && <p className="login-aviso" role="alert">{aviso}</p>}

          <button type="submit" className="login-btn-oscuro" disabled={enviando}>
            {enClave ? (enviando ? 'Entrando…' : 'Iniciar sesión') : 'Continuar con correo electrónico'}
          </button>

          {!enClave && (
            <>
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
            </>
          )}

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
