import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { HAY_SERVIDOR, auth } from '../api'
import { borrarBorrador } from '../brief/borrador'
import Logo from '../components/Logo'

/* Las pantallas que acompañan al inicio de sesión: la vuelta de Google, pedir el enlace para cambiar la contraseña
 * y poner la contraseña nueva. Usan la misma tarjeta que LoginPage. */

const CORREO_OK = /^\S+@\S+\.\S+$/

function mensaje(e) {
  if (e?.estado === 429) return 'Demasiados intentos. Espera un minuto e inténtalo de nuevo.'
  if (e?.estado === 0) return 'No pudimos conectarnos. Revisa tu conexión e inténtalo de nuevo.'
  if (e?.estado >= 500) return 'El envío de correos no está disponible ahora. Inténtalo más tarde.'
  return e?.message || 'No pudimos continuar. Inténtalo de nuevo.'
}

function Tarjeta({ titulo, sub, children, onSubmit }) {
  return (
    <div className="login">
      <Link to="/" className="login-logo" aria-label="Shifu"><Logo height={26} /></Link>
      <main className="login-centro">
        <form className="login-tarjeta" onSubmit={onSubmit} noValidate>
          <h1>{titulo}</h1>
          {sub && <p className="login-sub">{sub}</p>}
          {children}
        </form>
      </main>
    </div>
  )
}

/** /entrar: aquí vuelve el servidor después de Google, con las llaves en el fragmento (#at=…&rt=…). */
export function EntrarConGoogle() {
  const nav = useNavigate()
  useEffect(() => {
    const p = new URLSearchParams(window.location.hash.slice(1))
    window.history.replaceState(null, '', window.location.pathname) // que las llaves no queden en la barra ni en el historial
    if (auth.sesionDeGoogle({ acceso: p.get('at'), refresco: p.get('rt') })) {
      borrarBorrador() // como al entrar con contraseña: un cuestionario viejo de este navegador no es de esta persona
      nav('/mi-crm', { replace: true })
    } else nav('/login?error=sesion', { replace: true })
  }, [nav])
  return <Tarjeta titulo="Entrando…" sub="Un momento" />
}

/** /olvide-clave: pide el correo y manda el enlace para crear otra contraseña. */
export function OlvideClave() {
  const { state } = useLocation()
  const [correo, setCorreo] = useState(state?.correo || '')
  const [aviso, setAviso] = useState('')
  const [enviado, setEnviado] = useState(false)
  const [enviando, setEnviando] = useState(false)

  const enviar = async (e) => {
    e.preventDefault()
    if (enviando) return
    if (!HAY_SERVIDOR) { setAviso('Cambiar la contraseña necesita el servidor.'); return }
    if (!CORREO_OK.test(correo.trim())) { setAviso('Escribe un correo válido, por ejemplo nombre@correo.com.'); return }
    setAviso(''); setEnviando(true)
    try { await auth.olvideClave(correo.trim()); setEnviado(true) } catch (err) { setAviso(mensaje(err)) }
    setEnviando(false)
  }

  if (enviado) {
    return (
      <Tarjeta titulo="Revisa tu correo">
        <p className="login-info">Si hay una cuenta con <strong>{correo.trim()}</strong>, te enviamos un enlace para crear otra contraseña. Vale por una hora.</p>
        <p className="login-volver"><Link to="/login">← Volver a iniciar sesión</Link></p>
      </Tarjeta>
    )
  }
  return (
    <Tarjeta titulo="¿Olvidaste tu contraseña?" sub="Te enviamos un enlace para crear otra" onSubmit={enviar}>
      <label htmlFor="correo" className="login-label">Correo electrónico</label>
      <input id="correo" type="email" autoComplete="email" autoFocus value={correo}
        onChange={(e) => setCorreo(e.target.value)} className="login-input" />
      {aviso && <p className="login-aviso" role="alert">{aviso}</p>}
      <button type="submit" className="login-btn-oscuro" disabled={enviando}>{enviando ? 'Enviando…' : 'Enviar enlace'}</button>
      <p className="login-volver"><Link to="/login">← Volver a iniciar sesión</Link></p>
    </Tarjeta>
  )
}

/** /reset-password?token=…: el enlace del correo. Pone la contraseña nueva y manda a iniciar sesión. */
export function NuevaClave() {
  const [params] = useSearchParams()
  const enlace = params.get('token') || ''
  const [clave, setClave] = useState('')
  const [repetir, setRepetir] = useState('')
  const [verClave, setVerClave] = useState(false)
  const [aviso, setAviso] = useState('')
  const [listo, setListo] = useState(false)
  const [enviando, setEnviando] = useState(false)

  const guardar = async (e) => {
    e.preventDefault()
    if (enviando) return
    if (clave.length < 8) { setAviso('La contraseña necesita al menos 8 caracteres.'); return }
    if (clave !== repetir) { setAviso('Las dos contraseñas no coinciden.'); return }
    setAviso(''); setEnviando(true)
    try { await auth.nuevaClave({ enlace, clave }); setListo(true) } catch (err) { setAviso(mensaje(err)) }
    setEnviando(false)
  }

  if (enlace.length < 32) {
    return (
      <Tarjeta titulo="Enlace no válido">
        <p className="login-aviso" role="alert">Este enlace está incompleto. Pide uno nuevo.</p>
        <p className="login-volver"><Link to="/olvide-clave">Pedir otro enlace</Link></p>
      </Tarjeta>
    )
  }
  if (listo) {
    return (
      <Tarjeta titulo="Contraseña cambiada">
        <p className="login-info">Ya puedes iniciar sesión con tu contraseña nueva.</p>
        <p className="login-volver"><Link to="/login">Iniciar sesión →</Link></p>
      </Tarjeta>
    )
  }
  return (
    <Tarjeta titulo="Crea tu contraseña nueva" sub="Al menos 8 caracteres" onSubmit={guardar}>
      <label htmlFor="clave" className="login-label">Contraseña nueva</label>
      <div className="login-clave">
        <input id="clave" type={verClave ? 'text' : 'password'} autoComplete="new-password" autoFocus value={clave}
          onChange={(e) => setClave(e.target.value)} className="login-input" />
        <button type="button" onClick={() => setVerClave(!verClave)} aria-pressed={verClave}>{verClave ? 'Ocultar' : 'Mostrar'}</button>
      </div>
      <label htmlFor="repetir" className="login-label">Repítela</label>
      <input id="repetir" type={verClave ? 'text' : 'password'} autoComplete="new-password" value={repetir}
        onChange={(e) => setRepetir(e.target.value)} className="login-input" />
      {aviso && <p className="login-aviso" role="alert">{aviso}</p>}
      {aviso && /inválido|expirado|procesado/i.test(aviso) && <p className="login-volver"><Link to="/olvide-clave">Pedir otro enlace</Link></p>}
      <button type="submit" className="login-btn-oscuro" disabled={enviando}>{enviando ? 'Guardando…' : 'Guardar contraseña'}</button>
    </Tarjeta>
  )
}
