import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { HAY_SERVIDOR, auth } from '../api'
import { FaApple, FaFacebook, FaWhatsapp } from 'react-icons/fa6'
import { FcGoogle } from 'react-icons/fc'
import { ClaveDeAcceso } from '../components/Iconos'
import { borrarBorrador } from '../brief/borrador'
import Logo from '../components/Logo'

const CORREO_OK = /^\S+@\S+\.\S+$/

/** Texto claro para cada cosa que puede salir mal al entrar. */
function mensajeDeEntrada(e) {
  if (e?.estado === 401) return 'Correo o contraseña incorrectos.'
  if (e?.estado === 429) return 'Demasiados intentos. Espera un minuto e inténtalo de nuevo.'
  if (e?.estado === 0) return 'No pudimos conectarnos. Revisa tu conexión e inténtalo de nuevo.'
  return e?.message || 'No pudimos continuar. Inténtalo de nuevo.'
}

/** Lo que pasó si la persona vuelve de Google sin poder entrar (?error=… que pone el servidor). */
const ERRORES_GOOGLE = {
  google_denied: 'Cancelaste el inicio de sesión con Google.',
  google_off: 'Entrar con Google todavía no está disponible. Usa tu correo.',
  server_config: 'Entrar con Google todavía no está disponible. Usa tu correo.',
  google_verify: 'Google no pudo confirmar tu correo. Inténtalo de nuevo o usa tu correo.',
  no_email: 'Tu cuenta de Google no compartió un correo. Usa tu correo.',
  sesion: 'No pudimos abrir tu sesión con Google. Inténtalo de nuevo.',
}

/* Pantalla de inicio de sesión. Con servidor: primero el correo y luego la contraseña (como en Shopify). Sin servidor (modo de
 * prueba) solo pide el correo y manda al cuestionario. */
export default function LoginPage() {
  const [correo, setCorreo] = useState('')
  const [clave, setClave] = useState('')
  const [verClave, setVerClave] = useState(false)
  const [paso, setPaso] = useState('correo')
  const [params] = useSearchParams()
  const errorGoogle = params.get('error')
  const [aviso, setAviso] = useState(errorGoogle ? (ERRORES_GOOGLE[errorGoogle] || 'No pudimos entrar con Google. Inténtalo de nuevo.') : '')
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
    if (paso === 'correo') {
      // Sin cuenta con ese correo no hay contraseña que pedir: se manda a crearla, con el correo ya escrito.
      setEnviando(true)
      try {
        if (await auth.correoExiste(correo.trim())) { setPaso('clave'); setEnviando(false) }
        else { borrarBorrador(); nav('/registro', { state: { correo: correo.trim(), sinCuenta: true } }) } // lo que haya quedado aquí no es de esta persona
      } catch (err) { setAviso(mensajeDeEntrada(err)); setEnviando(false) }
      return
    }
    if (!clave) { setAviso('Escribe tu contraseña.'); return }
    setEnviando(true)
    try {
      await auth.iniciarSesion({ correo: correo.trim(), clave })
      borrarBorrador() // un cuestionario viejo de este navegador no debe tocar la cuenta de quien entra
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
              <p className="login-olvide"><Link to="/olvide-clave" state={{ correo: correo.trim() }}>¿Olvidaste tu contraseña?</Link></p>
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
                <button type="button" aria-label="Continuar con Google"
                  onClick={() => { if (HAY_SERVIDOR) window.location.assign(auth.urlGoogle()); else setAviso('Entrar con Google necesita el servidor.') }}><FcGoogle size={20} /></button>
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
