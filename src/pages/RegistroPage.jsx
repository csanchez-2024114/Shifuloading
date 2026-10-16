import { useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { HAY_SERVIDOR, auth } from '../api'
import { borradorTerminado, borrarBorrador } from '../brief/borrador'
import Logo from '../components/Logo'

const CORREO_OK = /^\S+@\S+\.\S+$/

/** Las mismas reglas que pide el servidor, para avisar antes de enviar. Devuelve el texto del problema o '' si todo está bien. */
export function revisarRegistro({ nombre, apellido, correo, clave }) {
  if (nombre.trim().length < 2) return 'Escribe tu nombre (mínimo 2 letras).'
  if (apellido.trim().length < 2) return 'Escribe tu apellido (mínimo 2 letras).'
  if (!CORREO_OK.test(correo.trim())) return 'Escribe un correo válido, por ejemplo nombre@correo.com.'
  if (clave.length < 8) return 'La contraseña debe tener al menos 8 caracteres.'
  if (!/[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]/.test(clave) || !/\d/.test(clave)) return 'La contraseña debe tener al menos una letra y un número.'
  return ''
}

function mensaje(e) {
  if (e?.estado === 400) return e.message || 'Esa cuenta ya existe.'
  if (e?.estado === 429) return 'Demasiados intentos. Espera un minuto e inténtalo de nuevo.'
  if (e?.estado === 0) return 'No pudimos conectarnos. Revisa tu conexión e inténtalo de nuevo.'
  return e?.message || 'No pudimos crear tu cuenta. Inténtalo de nuevo.'
}

/* Último paso del cuestionario: la persona ya contó su negocio, ahora crea su cuenta para guardar el CRM que Shifu va a armar.
 * Solo existe con servidor; sin servidor (modo de prueba) no hay cuentas y se sigue directo al CRM. */
export default function RegistroPage() {
  const nav = useNavigate()
  const { state } = useLocation()
  // Si viene del inicio de sesión porque ese correo no tiene cuenta, ya trae el correo escrito.
  const [f, setF] = useState({ nombre: '', apellido: '', correo: state?.correo || '', clave: '' })
  const [ver, setVer] = useState(false)
  const [aviso, setAviso] = useState('')
  const [enviando, setEnviando] = useState(false)
  // Solo se arma el CRM con el cuestionario si la persona llegó AHORA de terminarlo (state.cargar). Un borrador viejo que haya quedado en este
  // navegador (de otra persona o de otra cuenta) no se usa: antes creaba el CRM de un desconocido con respuestas ajenas.
  const brief = state?.cargar ? borradorTerminado()?.resp : undefined

  if (!HAY_SERVIDOR) return <Navigate to="/bienvenida" replace />
  if (auth.haySesion()) return <Navigate to="/mi-crm" replace state={{ cargar: !!brief }} />

  const poner = (campo) => (e) => setF((x) => ({ ...x, [campo]: e.target.value }))
  const enviar = async (e) => {
    e.preventDefault()
    if (enviando) return
    const problema = revisarRegistro(f)
    if (problema) { setAviso(problema); return }
    setAviso(''); setEnviando(true)
    try {
      await auth.registrar({ nombre: f.nombre.trim(), apellido: f.apellido.trim(), correo: f.correo.trim(), clave: f.clave })
      // Con el cuestionario contestado se arma el CRM; si no (llegó directo), primero a contestarlo.
      if (brief) nav('/mi-crm', { replace: true, state: { cargar: true } })
      else { borrarBorrador(); nav('/bienvenida', { replace: true }) } // sin cuestionario propio: cualquier borrador que haya aquí es de otra persona
    } catch (err) {
      setAviso(mensaje(err))
      setEnviando(false)
    }
  }

  return (
    <div className="login">
      <Link to="/" className="login-logo" aria-label="Shifu"><Logo height={26} /></Link>

      <main className="login-centro">
        <form className="login-tarjeta" onSubmit={enviar} noValidate>
          <h1>Crea tu cuenta</h1>
          <p className="login-sub">{brief?.nombre ? `Para guardar el CRM de ${brief.nombre}` : 'Para empezar con Shifu'}</p>
          {state?.sinCuenta && state?.correo && <p className="login-info" role="status">No encontramos una cuenta con <b>{state.correo}</b>. Créala en un minuto: es gratis.</p>}

          <div className="login-fila2">
            <div>
              <label htmlFor="nombre" className="login-label">Nombre</label>
              <input id="nombre" autoComplete="given-name" autoFocus value={f.nombre} onChange={poner('nombre')} maxLength={50} className="login-input" />
            </div>
            <div>
              <label htmlFor="apellido" className="login-label">Apellido</label>
              <input id="apellido" autoComplete="family-name" value={f.apellido} onChange={poner('apellido')} maxLength={50} className="login-input" />
            </div>
          </div>

          <label htmlFor="correo" className="login-label">Correo electrónico</label>
          <input id="correo" type="email" autoComplete="email" value={f.correo} onChange={poner('correo')} className="login-input" />

          <label htmlFor="clave" className="login-label">Contraseña</label>
          <div className="login-clave">
            <input id="clave" type={ver ? 'text' : 'password'} autoComplete="new-password" value={f.clave} onChange={poner('clave')} className="login-input" aria-describedby="clave-ayuda" />
            <button type="button" onClick={() => setVer(!ver)} aria-pressed={ver}>{ver ? 'Ocultar' : 'Mostrar'}</button>
          </div>
          <p id="clave-ayuda" className="login-ayuda-campo">Mínimo 8 caracteres, con una letra y un número.</p>

          {aviso && <p className="login-aviso" role="alert">{aviso}</p>}

          <button type="submit" className="login-btn-oscuro" disabled={enviando}>{enviando ? 'Creando tu cuenta…' : 'Crear mi cuenta'}</button>

          <p className="login-nuevo">¿Ya tienes cuenta? <Link to="/login">Inicia sesión</Link></p>
        </form>
      </main>

      <p className="login-legal">
        Si continúas, aceptas los <strong>Términos</strong> y la <strong>Política de privacidad</strong> de Shifu.
      </p>
    </div>
  )
}
